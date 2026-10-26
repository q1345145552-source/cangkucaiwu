"""Append-only quantity movements. Warehouse lock serializes all stock writers.

No historical receipt replay is backfilled. Unknown openings and costs stay unknown.
"""
from decimal import Decimal, InvalidOperation, localcontext
from datetime import datetime
import re
from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select, func
from app.models import (InventoryAccount as Account, InventoryMovement as Movement,
                        InventoryReceiptLink as ReceiptLink, InventoryOperation as Operation,
                        InventoryPolicy as Policy, StandardSKU, PurchaseReceiptEvent, PurchaseOrder)
from app.core.permissions import Role
from app.core.timezone import thai_now
from app.services import sku_catalog as catalog
from app.services.purchase_matching import scope_lock
from app.services.payable_creation import fingerprint, number
from app.services.data_history import record_history
from app.services.inventory_migration import ensure_inventory


def owner(user):
    if user.role != Role.WAREHOUSE_ADMIN:
        raise HTTPException(403, '只有仓库管理员可以确认期初、审核盘点、核对入库、冲销或修改库存配置')


def quantity(value, zero=False):
    if isinstance(value, bool) or not re.fullmatch(r'\d+(?:\.\d{1,8})?', str(value)):
        raise HTTPException(400, '数量须为非负普通小数，最多8位小数，不支持自动舍入')
    try:
        v = Decimal(str(value))
    except InvalidOperation:
        raise HTTPException(400, '数量格式不正确')
    if not v.is_finite() or v >= Decimal('10000000000000000') or (v < 0 if zero else v <= 0):
        raise HTTPException(400, '数量超出范围或不是正数')
    return v


def qty(value):
    return format(Decimal(value).normalize(), 'f')


def reason(value):
    return catalog.label(value, '原因或用途', 1000)


def changed(message, key, status=409):
    return HTTPException(status, {'code': 'inventory_changed', 'message': message,
                                 'request_key': key, 'not_executed': True})


def account_version(wid, sku_id, unit, row=None):
    return fingerprint({'warehouse_id': wid, 'sku_id': sku_id, 'base_unit': unit,
                        'account_id': row.id if row else None, 'revision': row.revision if row else 0,
                        'quantity': qty(row.recorded_quantity) if row else '0',
                        'opening_confirmed': row.opening_confirmed if row else False})


def account_data(row):
    return {'id': row.id, 'warehouse_id': row.warehouse_id, 'sku_id': row.sku_id,
            'sku': row.sku_snapshot, 'base_unit': row.base_unit,
            'unit_label': catalog.UNITS.get(row.base_unit, row.base_unit),
            'recorded_quantity': qty(row.recorded_quantity),
            'available_quantity': qty(row.recorded_quantity) if row.opening_confirmed else None,
            'opening_confirmed': row.opening_confirmed, 'opening_at': row.opening_at,
            'version': account_version(row.warehouse_id, row.sku_id, row.base_unit, row),
            'amount': None, 'currency': None, 'valuation_status': '待配置，未确认成本',
            'note': '真实期初已确认；数量按流水累计' if row.opening_confirmed else '期初未确认；仅显示已知变动，不能作为当前库存或领用额度'}


def movement_data(row):
    return {k: qty(getattr(row, k)) if k in ('quantity', 'balance_after') else getattr(row, k)
            for k in ('id', 'warehouse_id', 'account_id', 'kind', 'quantity', 'balance_after',
                      'reference_id', 'reverses_id', 'source_type', 'source_id', 'source_line_id',
                      'source_snapshot', 'occurred_at', 'reason', 'operator_id', 'operator_name',
                      'status', 'cost_amount', 'cost_currency', 'created_at')}


def link_data(row):
    return {k: qty(getattr(row, k)) if k == 'original_quantity' else getattr(row, k)
            for k in ('id', 'warehouse_id', 'receipt_event_id', 'purchase_order_id', 'line_id',
                      'original_quantity', 'original_unit', 'source_fingerprint', 'source_snapshot',
                      'status', 'pending_reason', 'movement_id', 'resolution', 'created_at')}


async def owned(db, model, ident, wid, lock=False):
    q = select(model).where(model.id == ident)
    if lock:
        q = q.with_for_update()
    row = (await db.execute(q)).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, '本仓未找到该库存或来源记录')
    if row.warehouse_id != wid:
        raise HTTPException(403, '无权访问其他仓库的库存或来源记录')
    return row


async def find_account(db, wid, sku_id, unit):
    return (await db.execute(select(Account).where(Account.warehouse_id == wid,
                  Account.sku_id == sku_id, Account.base_unit == unit).with_for_update())).scalar_one_or_none()


async def get_account(db, wid, sku, unit, snapshot=None):
    row = await find_account(db, wid, sku.id, unit)
    if row is None:
        row = Account(warehouse_id=wid, sku_id=sku.id, base_unit=unit,
                      sku_snapshot=snapshot or catalog.sku_data(sku), recorded_quantity=0,
                      opening_confirmed=False, revision=0)
        db.add(row)
        await db.flush()
    return row


async def begin(db, wid, user, kind, resource, payload, request_key):
    key = number(request_key, '请求编号', 100)
    signature = fingerprint({'kind': kind, 'resource': resource, 'payload': jsonable_encoder(payload)})
    await scope_lock(db, wid)
    await ensure_inventory(await db.connection())
    old = (await db.execute(select(Operation).where(Operation.warehouse_id == wid,
            Operation.operator_id == user.id, Operation.request_key == key))).scalar_one_or_none()
    if old:
        if old.request_fingerprint != signature:
            raise HTTPException(409, '原库存请求已成功且内容不同，请查看原流水；未重复执行')
        return {'replay': {**old.response, 'replayed': True}}
    return {'warehouse_id': wid, 'user': user, 'kind': kind, 'key': key, 'signature': signature}


async def finish(db, ticket, response):
    row = Operation(warehouse_id=ticket['warehouse_id'], operator_id=ticket['user'].id,
                    kind=ticket['kind'], request_key=ticket['key'],
                    request_fingerprint=ticket['signature'], response={})
    db.add(row)
    await db.flush()
    result = {**response, 'operation_id': row.id}
    result.setdefault('id', row.id)
    row.response = jsonable_encoder(result)
    await record_history(db, module='inventory', record_id=response.get('movement_id') or response.get('record_id') or row.id,
                         operation_type=ticket['kind'], operator=ticket['user'],
                         after={'request_key': ticket['key'], **jsonable_encoder(result)},
                         warehouse_id=ticket['warehouse_id'])
    await db.flush()
    return result


def check_version(row, wid, sku_id, unit, expected, ticket):
    if expected != account_version(wid, sku_id, unit, row):
        raise changed('库存已变化，请重新读取后确认；原请求未执行', ticket['key'])


async def append(db, account, user, kind, delta, occurred_at, why, *, source_type='manual',
                 source_id=None, line_id=None, snapshot=None, reference_id=None, reverses_id=None):
    with localcontext() as ctx:
        ctx.prec = 48
        balance = Decimal(account.recorded_quantity) + delta
    if balance < 0 or balance >= Decimal('10000000000000000'):
        raise HTTPException(409, '库存不足或数量超出范围，未生成流水')
    row = Movement(warehouse_id=account.warehouse_id, account_id=account.id, kind=kind,
                   quantity=delta, balance_after=balance, opening_token='opening' if kind == 'opening' else None,
                   occurred_at=occurred_at, reason=why, operator_id=user.id,
                   operator_name=user.display_name or user.username, status='active',
                   source_type=source_type, source_id=source_id, source_line_id=line_id,
                   source_snapshot=jsonable_encoder(snapshot or {'sku': account.sku_snapshot, 'base_unit': account.base_unit}),
                   reference_id=reference_id, reverses_id=reverses_id, cost_amount=None, cost_currency=None)
    db.add(row)
    account.recorded_quantity = balance
    account.revision += 1
    await db.flush()
    return row


async def opening(db, wid, user, *, sku_id, base_unit, opening_quantity, occurred_at,
                  confirmed, expected_version, change_reason, request_key):
    owner(user)
    value = quantity(opening_quantity, zero=True)
    unit = catalog.unit(base_unit)
    why = reason(change_reason)
    if not confirmed:
        raise HTTPException(400, '请明确确认这是已核实的真实期初，不得从采购历史推算')
    if occurred_at.tzinfo is None or occurred_at > thai_now():
        raise HTTPException(400, '期初时间必须带时区且不能在未来')
    ticket = await begin(db, wid, user, 'opening', [sku_id, unit],
                         [qty(value), occurred_at, expected_version, why, confirmed], request_key)
    if ticket.get('replay'):
        return ticket['replay']
    sku = await owned(db, StandardSKU, sku_id, wid)
    row = await find_account(db, wid, sku_id, unit)
    check_version(row, wid, sku_id, unit, expected_version, ticket)
    if row and row.opening_confirmed:
        raise changed('该库存已确认期初，不能覆盖；后续差异须走盘点调整', ticket['key'])
    if row is None and (sku.base_unit != unit or not sku.active):
        raise changed('新增期初须使用当前有效SKU的基本单位，不允许猜换算', ticket['key'], 400)
    if row:
        first = (await db.execute(select(func.min(Movement.occurred_at)).where(Movement.account_id == row.id))).scalar_one()
        if first and occurred_at > first:
            raise changed('期初基准时间不能晚于首笔库存变动，以免把收货重复算入期初', ticket['key'], 400)
    row = row or await get_account(db, wid, sku, unit)
    entry = await append(db, row, user, 'opening', value, occurred_at, why,
                         snapshot={'explicit_confirmation': True, 'sku': row.sku_snapshot,
                                   'base_unit': unit, 'opening_quantity': qty(value), 'at': occurred_at})
    row.opening_confirmed = True
    row.opening_at = occurred_at
    await db.flush()
    return await finish(db, ticket, {'movement_id': entry.id, 'account': account_data(row),
                                    'message': '真实期初已确认，未推算历史库存或成本'})


async def issue(db, wid, user, account_id, *, issued_quantity, expected_version, purpose, request_key):
    value, why = quantity(issued_quantity), reason(purpose)
    ticket = await begin(db, wid, user, 'issue', account_id, [qty(value), expected_version, why], request_key)
    if ticket.get('replay'):
        return ticket['replay']
    row = await owned(db, Account, account_id, wid, True)
    check_version(row, wid, row.sku_id, row.base_unit, expected_version, ticket)
    if not row.opening_confirmed:
        raise changed('真实期初未确认，不能把已知变动当作可用库存领用', ticket['key'], 400)
    if value > row.recorded_quantity:
        raise changed('库存不足，不能领用超过当前可用数量', ticket['key'], 400)
    entry = await append(db, row, user, 'issue', -value, thai_now(), why)
    return await finish(db, ticket, {'movement_id': entry.id, 'movement': movement_data(entry),
                                    'account': account_data(row), 'message': '领用已记录；未生成资金支出或费用'})


async def return_issue(db, wid, user, movement_id, *, returned_quantity, expected_version, return_reason, request_key):
    value, why = quantity(returned_quantity), reason(return_reason)
    ticket = await begin(db, wid, user, 'return', movement_id, [qty(value), expected_version, why], request_key)
    if ticket.get('replay'):
        return ticket['replay']
    original = await owned(db, Movement, movement_id, wid, True)
    row = await owned(db, Account, original.account_id, wid, True)
    check_version(row, wid, row.sku_id, row.base_unit, expected_version, ticket)
    if original.kind != 'issue' or original.status != 'active':
        raise changed('只能退回一笔有效领用，不能给无来源或已冲销领用退回', ticket['key'], 400)
    returned = (await db.execute(select(func.coalesce(func.sum(Movement.quantity), 0)).where(
        Movement.reference_id == original.id, Movement.kind == 'return', Movement.status == 'active'))).scalar_one()
    if returned + value > -original.quantity:
        raise changed('退回数量不能超过这笔领用尚未退回的数量', ticket['key'], 400)
    entry = await append(db, row, user, 'return', value, thai_now(), why,
                         reference_id=original.id, source_type='issue_return', source_id=original.id)
    return await finish(db, ticket, {'movement_id': entry.id, 'movement': movement_data(entry),
                                    'account': account_data(row), 'message': '退回已记录，原领用流水保留'})


async def reverse(db, wid, user, movement_id, *, expected_version, reverse_reason, request_key):
    owner(user)
    why = reason(reverse_reason)
    ticket = await begin(db, wid, user, 'reverse', movement_id, [expected_version, why], request_key)
    if ticket.get('replay'):
        return ticket['replay']
    original = await owned(db, Movement, movement_id, wid, True)
    row = await owned(db, Account, original.account_id, wid, True)
    check_version(row, wid, row.sku_id, row.base_unit, expected_version, ticket)
    if original.status != 'active' or original.kind not in ('issue', 'receipt', 'return'):
        raise changed('该流水已冲销或属于不可直接冲销的期初/冲销记录，请保留历史并走相应调整', ticket['key'], 400)
    if original.kind == 'issue' and (await db.execute(select(Movement.id).where(
        Movement.reference_id == original.id, Movement.kind == 'return', Movement.status == 'active'))).first():
        raise changed('该领用已有有效退回，请先核对并冲销退回记录，不能重复恢复库存', ticket['key'], 400)
    if row.recorded_quantity - original.quantity < 0:
        raise changed('当前库存不足以冲销这笔入库或退回；不能形成负库存', ticket['key'], 400)
    entry = await append(db, row, user, 'reversal', -original.quantity, thai_now(), why,
                         reverses_id=original.id, source_type='movement_reversal', source_id=original.id,
                         snapshot={'original': movement_data(original), 'reason': why})
    original.status = 'reversed'
    if original.kind == 'receipt':
        link = (await db.execute(select(ReceiptLink).where(ReceiptLink.warehouse_id == wid,
                    ReceiptLink.movement_id == original.id))).scalar_one_or_none()
        if link:
            link.status = 'reversed'
    await db.flush()
    return await finish(db, ticket, {'movement_id': entry.id, 'movement': movement_data(entry),
                                    'account': account_data(row),
                                    'message': '库存已以反向流水冲销，原记录保留；未撤销采购实收或应付，不影响资金账'})


async def policy(db, wid):
    row = (await db.execute(select(Policy).where(Policy.warehouse_id == wid))).scalar_one_or_none()
    value = {'warehouse_id': wid, 'valuation_method': row.valuation_method if row else 'unconfigured',
             'revision': row.revision if row else 0}
    if value['valuation_method'] not in ('unconfigured', 'quantity_only'):
        raise HTTPException(503, '库存计价配置异常，未假定成本为零')
    return {**value, 'version': fingerprint(value), 'amount': None,
            'note': '本轮仅数量台账；FIFO/均价及真实成本尚未选择或实现，金额待配置，不借用今天报价，不进资金支出'}


async def set_policy(db, wid, user, *, valuation_method, expected_version, change_reason, request_key):
    owner(user)
    why = reason(change_reason)
    if valuation_method not in ('unconfigured', 'quantity_only'):
        raise HTTPException(400, '本轮仅支持待配置或明确仅数量模式，不能假装FIFO/均价已就绪')
    ticket = await begin(db, wid, user, 'policy', 'current', [valuation_method, expected_version, why], request_key)
    if ticket.get('replay'):
        return ticket['replay']
    old = await policy(db, wid)
    if old['version'] != expected_version:
        raise changed('库存配置已变化，请重新读取；原请求未执行', ticket['key'])
    row = (await db.execute(select(Policy).where(Policy.warehouse_id == wid))).scalar_one_or_none()
    if row is None:
        row = Policy(warehouse_id=wid, revision=0)
        db.add(row)
    row.valuation_method, row.updated_by, row.reason = valuation_method, user.id, why
    row.revision += 1
    row.updated_at = thai_now()
    await db.flush()
    return await finish(db, ticket, {'before': old, 'policy': await policy(db, wid),
                                    'message': '库存数量/待配置策略已保存，未选择计价法或改写历史成本'})


def frozen_mapping(po, event_row):
    matches = [x for x in (po.items or []) if x.get('line_id') == event_row['line_id']]
    if len(matches) != 1:
        raise HTTPException(400, '缺少唯一稳定采购行，不能猜配库存')
    mapping = matches[0].get('sku_mapping') or {}
    snap = mapping.get('sku_snapshot') or {}
    sku_id = mapping.get('standard_sku_id')
    if mapping.get('comparable') is not True or type(sku_id) is not int or snap.get('id') != sku_id or snap.get('warehouse_id') != po.warehouse_id:
        raise HTTPException(400, '原采购行没有可靠的冻结SKU映射，需老板明确核对')
    if not isinstance(snap.get('attributes'), dict) or not snap['attributes'] or not snap.get('code') or not snap.get('name') or not re.fullmatch('[a-f0-9]{64}',snap.get('version','')):
        raise HTTPException(400, '冻结SKU身份或规格证据不完整，不能猜配入库')
    unit = catalog.unit(snap.get('base_unit'))
    factor = quantity(mapping.get('base_unit_factor'))
    if factor != quantity(snap.get('base_unit_factor')) or catalog.unit(event_row.get('unit'),False) is None or catalog.unit(event_row.get('unit'),False) != catalog.unit(snap.get('original_unit'),False):
        raise HTTPException(400, '冻结换算或原收货单位不一致，需老板按原始证据核对')
    return sku_id, unit, factor, snap


async def post_link(db, link, sku, unit, factor, user, at, why, snapshot):
    with localcontext() as ctx:
        ctx.prec = 48
        value = Decimal(link.original_quantity) * factor
    value = quantity(qty(value))
    account = await get_account(db, link.warehouse_id, sku, unit, snapshot)
    if fingerprint(account.sku_snapshot.get('attributes')) != fingerprint(snapshot.get('attributes')):
        raise HTTPException(409, 'SKU规格版本与现有台账不同，请明确使用不同SKU，不能把不同实物混在同一库存')
    if account.opening_confirmed and at < account.opening_at:
        raise HTTPException(409, '收货时点早于已确认期初，不能假定未包含而重复入库，请核实期初范围')
    entry = await append(db, account, user, 'receipt', value, at, why, source_type='purchase_receipt',
                         source_id=link.receipt_event_id, line_id=link.line_id,
                         snapshot={**link.source_snapshot, 'confirmed_sku': snapshot,
                                   'base_unit': unit, 'base_unit_factor': qty(factor), 'base_quantity': qty(value)})
    link.status, link.movement_id, link.pending_reason = 'recorded', entry.id, None
    await db.flush()
    return entry, account


async def record_receipt(db, po, event, user):
    """Caller holds the same warehouse lock and has verified the inventory schema.

    Only invoked for a NEW actual receipt event, never an old request replay.
    Missing historical mapping queues evidence, without fabricating an opening.
    """
    result = {'recorded_lines': 0, 'pending_lines': 0, 'receipt_event_id': event.id}
    for row in event.items:
        old = (await db.execute(select(ReceiptLink).where(ReceiptLink.warehouse_id == po.warehouse_id,
               ReceiptLink.receipt_event_id == event.id, ReceiptLink.line_id == row['line_id']))).scalar_one_or_none()
        if old:
            result['recorded_lines' if old.status in ('recorded', 'reversed') else 'pending_lines'] += 1
            continue
        snapshot = {'warehouse_id': po.warehouse_id, 'purchase_order_id': po.id,
                    'purchase_order_number': po.order_number, 'purchase_currency': po.currency,
                    'supplier_id': po.supplier_id,
                    'receipt_event_id': event.id, 'receipt_fingerprint': event.request_fingerprint,
                    'received_at': event.received_at, 'operator_id': event.operator_id, 'item': row}
        link = ReceiptLink(warehouse_id=po.warehouse_id, receipt_event_id=event.id,
                    purchase_order_id=po.id, line_id=row['line_id'], original_quantity=row['quantity'],
                    original_unit=row.get('unit'), source_fingerprint=fingerprint(jsonable_encoder(snapshot)),
                    source_snapshot=jsonable_encoder(snapshot), status='pending')
        db.add(link)
        await db.flush()
        try:
            sku_id, unit, factor, frozen = frozen_mapping(po, row)
            sku = await owned(db, StandardSKU, sku_id, po.warehouse_id)
            existing = await find_account(db, po.warehouse_id, sku.id, unit)
            if existing and fingerprint(existing.sku_snapshot.get('attributes')) != fingerprint(frozen.get('attributes')):
                raise HTTPException(400, '冻结SKU规格与已有台账不同，需老板按实物核对，未混加数量')
        except HTTPException as error:
            link.pending_reason = str(error.detail)
            result['pending_lines'] += 1
            continue
        # Invalid precision or a capacity overflow is not a silent stock omission.
        await post_link(db, link, sku, unit, factor, user, event.received_at,
                        '采购实际收货，按原冻结SKU及基本单位换算入库', frozen)
        result['recorded_lines'] += 1
    result['note'] = '仅新收货变动；缺期初不假设零，缺可靠映射列待核对；未记录成本或资金支出'
    return result


async def resolve_receipt(db, wid, user, ident, *, sku_id, base_unit_factor, expected_source_fingerprint, expected_sku_version,
                          confirmation_reason, request_key):
    owner(user)
    factor, why = quantity(base_unit_factor), reason(confirmation_reason)
    ticket = await begin(db, wid, user, 'resolve_receipt', ident,
                         [sku_id, qty(factor), expected_source_fingerprint, expected_sku_version, why], request_key)
    if ticket.get('replay'):
        return ticket['replay']
    link = await owned(db, ReceiptLink, ident, wid, True)
    if link.status != 'pending' or link.source_fingerprint != expected_source_fingerprint:
        raise changed('待核对来源已变化或已处理，请重新读取；原请求未执行', ticket['key'])
    event = await owned(db, PurchaseReceiptEvent, link.receipt_event_id, wid)
    po = await owned(db, PurchaseOrder, link.purchase_order_id, wid)
    if event.status != 'active' or event.purchase_order_id != po.id or event.request_fingerprint != link.source_snapshot['receipt_fingerprint']:
        raise changed('原收货依据已失效，不能据此补记库存', ticket['key'])
    items = [x for x in event.items if x.get('line_id') == link.line_id]
    if (fingerprint(link.source_snapshot) != link.source_fingerprint or len(items) != 1
            or Decimal(str(items[0]['quantity'])) != link.original_quantity):
        raise changed('原收货行或冻结来源校验不一致，请先核实，未补记库存', ticket['key'])
    sku = await owned(db, StandardSKU, sku_id, wid)
    if catalog.sku_data(sku)['version'] != expected_sku_version:
        raise changed('所选SKU规格或基本单位已变化，请重新核实；原请求未执行', ticket['key'])
    existing = await find_account(db, wid, sku.id, sku.base_unit)
    if existing and fingerprint(existing.sku_snapshot.get('attributes')) != fingerprint(catalog.sku_data(sku).get('attributes')):
        raise changed('所选SKU规格与现有台账不同，不能合并不同实物，请核对并使用不同SKU', ticket['key'])
    if existing and existing.opening_confirmed and event.received_at < existing.opening_at:
        raise changed('这笔收货早于已确认期初，不能猜测是否包含而再次入库，请核实期初范围', ticket['key'])
    entry, account = await post_link(db, link, sku, sku.base_unit, factor, user, event.received_at,
                                    why, catalog.sku_data(sku))
    link.resolution = jsonable_encoder({'confirmed_by': user.id, 'confirmed_at': thai_now(),
                       'reason': why, 'sku_id': sku.id, 'base_unit_factor': qty(factor),
                       'original_source': link.source_snapshot})
    await db.flush()
    return await finish(db, ticket, {'movement_id': entry.id, 'account': account_data(account),
                                    'source': link_data(link), 'message': '按老板明确核对结果补记入库；原采购快照不改'})

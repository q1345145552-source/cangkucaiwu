"""Reviewed physical counts and explicit per-account thresholds; never cash/expense writes."""
from sqlalchemy import select
from app.models import InventoryStocktake as Count, InventoryControl as Control, InventoryAccount
from app.core.timezone import thai_now
from app.services import inventory as stock
from app.services.payable_creation import fingerprint
from datetime import datetime, timezone
from fastapi.encoders import jsonable_encoder


def version(data):
    return fingerprint(jsonable_encoder(data, custom_encoder={datetime: lambda v: v.astimezone(timezone.utc).isoformat()}))


def count_data(row):
    data = {k: getattr(row, k) for k in ('id', 'warehouse_id', 'account_id', 'account_version', 'snapshot',
        'counted_at', 'reason', 'created_by', 'creator_name', 'status', 'reviewed_by', 'reviewer_name',
        'reviewed_at', 'review_reason', 'adjustment_id', 'created_at')}
    data.update(book_quantity=stock.qty(row.book_quantity), counted_quantity=stock.qty(row.counted_quantity),
                difference=stock.qty(row.counted_quantity-row.book_quantity))
    return {**data, 'version': version(data)}


async def submit_count(db, wid, user, account_id, *, counted_quantity, expected_version, count_reason, request_key):
    value, why = stock.quantity(counted_quantity, zero=True), stock.reason(count_reason)
    ticket = await stock.begin(db, wid, user, 'stocktake', account_id, [stock.qty(value), expected_version, why], request_key)
    if ticket.get('replay'): return ticket['replay']
    account = await stock.owned(db, InventoryAccount, account_id, wid, True)
    stock.check_version(account, wid, account.sku_id, account.base_unit, expected_version, ticket)
    if not account.opening_confirmed:
        raise stock.changed('请先核实真实期初，不能把未知账面数量当作盘点基准', ticket['key'], 400)
    row = Count(warehouse_id=wid, account_id=account.id, book_quantity=account.recorded_quantity,
                counted_quantity=value, account_version=expected_version, snapshot=stock.account_data(account),
                counted_at=thai_now(), reason=why, created_by=user.id, creator_name=user.display_name or user.username,
                status='pending')
    # Snapshot contains datetimes; retain the exact JSON-serializable server snapshot.
    from fastapi.encoders import jsonable_encoder
    row.snapshot = jsonable_encoder(row.snapshot)
    db.add(row); await db.flush()
    return await stock.finish(db, ticket, {'data': count_data(row), 'record_id': row.id, 'account': stock.account_data(account),
                                         'message': '盘点已登记待老板审核，库存尚未调整'})


async def review_count(db, wid, user, ident, *, decision, expected_count_version, review_reason, request_key):
    stock.owner(user); why = stock.reason(review_reason)
    ticket = await stock.begin(db, wid, user, 'stocktake_review', ident,
                              [decision, expected_count_version, why], request_key)
    if ticket.get('replay'): return ticket['replay']
    row = await stock.owned(db, Count, ident, wid, True)
    if row.status != 'pending' or count_data(row)['version'] != expected_count_version:
        raise stock.changed('该盘点已审核或已变化，请查看原记录；未重复调整', ticket['key'])
    account = await stock.owned(db, InventoryAccount, row.account_id, wid, True)
    if decision == 'approve':
        stock.check_version(account, wid, account.sku_id, account.base_unit, row.account_version, ticket)
        if not account.opening_confirmed:
            raise stock.changed('盘点基准已失效，请重新核实真实期初', ticket['key'])
        adjustment = await stock.append(db, account, user, 'stocktake_adjustment',
            row.counted_quantity-row.book_quantity, thai_now(), why, source_type='stocktake', source_id=row.id,
            snapshot={'stocktake_id': row.id, 'book_quantity': stock.qty(row.book_quantity),
                      'counted_quantity': stock.qty(row.counted_quantity), 'counted_at': row.counted_at,
                      'count_reason': row.reason, 'review_reason': why, 'original_account': row.snapshot})
        row.status, row.adjustment_id = 'approved', adjustment.id
    elif decision == 'reject': row.status = 'rejected'
    else: raise stock.changed('审核动作不正确', ticket['key'], 400)
    row.reviewed_by, row.reviewer_name = user.id, user.display_name or user.username
    row.reviewed_at, row.review_reason = thai_now(), why
    await db.flush()
    return await stock.finish(db, ticket, {'data': count_data(row), 'record_id': row.id, 'account': stock.account_data(account),
        'movement_id': row.adjustment_id, 'message': '盘点已审核，新增调整流水，原流水未改' if decision=='approve' else '盘点已驳回，库存未调整'})


async def controls(db, wid, account_id):
    row = (await db.execute(select(Control).where(Control.warehouse_id==wid, Control.account_id==account_id))).scalar_one_or_none()
    data = {'warehouse_id': wid, 'account_id': account_id,
            'minimum_quantity': stock.qty(row.minimum_quantity) if row and row.minimum_quantity is not None else None,
            'receipt_usage_ratio': stock.qty(row.receipt_usage_ratio) if row and row.receipt_usage_ratio is not None else None,
            'stockpiling_note': row.stockpiling_note if row else '', 'revision': row.revision if row else 0,
            'reason': row.reason if row else '', 'updated_by': row.updated_by if row else None,
            'updated_at': row.updated_at if row else None}
    return {**data, 'version': version(data)}


async def set_controls(db, wid, user, account_id, *, minimum_quantity, receipt_usage_ratio,
                       stockpiling_note, expected_version, change_reason, request_key):
    stock.owner(user); why = stock.reason(change_reason)
    minimum = stock.quantity(minimum_quantity, zero=True) if minimum_quantity is not None else None
    ratio = stock.quantity(receipt_usage_ratio) if receipt_usage_ratio is not None else None
    note = stockpiling_note.strip()
    if ratio is not None and (ratio <= 1 or not note):
        from fastapi import HTTPException
        raise HTTPException(400, '收货用量比须大于1，并填写备货计划或核实说明；不把买多直接认定违规')
    ticket = await stock.begin(db, wid, user, 'inventory_controls', account_id,
                              [stock.qty(minimum) if minimum is not None else None,
                               stock.qty(ratio) if ratio is not None else None, note, expected_version, why], request_key)
    if ticket.get('replay'): return ticket['replay']
    await stock.owned(db, InventoryAccount, account_id, wid, True)
    before = await controls(db, wid, account_id)
    if before['version'] != expected_version:
        raise stock.changed('本仓该SKU库存阈值已变化，请重新读取；未覆盖旧设置', ticket['key'])
    row = (await db.execute(select(Control).where(Control.warehouse_id==wid, Control.account_id==account_id))).scalar_one_or_none()
    if row is None:
        row = Control(warehouse_id=wid, account_id=account_id, revision=0); db.add(row)
    row.minimum_quantity, row.receipt_usage_ratio, row.stockpiling_note = minimum, ratio, note
    row.reason, row.updated_by, row.updated_at = why, user.id, thai_now(); row.revision += 1
    await db.flush()
    return await stock.finish(db, ticket, {'before': before, 'controls': await controls(db, wid, account_id),
                                         'message': '该仓SKU基本单位的库存提醒设置已保存，不改变库存或账目'})

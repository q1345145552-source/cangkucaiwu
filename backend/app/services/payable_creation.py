"""One payable registration channel. No payment, balance, or historical repair logic."""
import hashlib
import json
import math
from datetime import datetime, timedelta
from sqlalchemy import select, func, Numeric, cast, or_
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException
from app.models import Warehouse, PayableBill, PurchaseOrder
from app.core.payable_constraints import missing_guards
from app.core.timezone import thai_now
from app.config import get_settings
from app.services.supplier_payable_read import can_read_bills
from app.services.data_history import record_history
from app.services.wallet import money


def normalized(value):
    # Only surrounding ASCII whitespace: no case-folding, punctuation removal or Unicode substitutions.
    return str(value or '').strip(' \t\r\n')


def normalized_column(db, column):
    return func.btrim(column, ' \t\r\n') if db.bind.dialect.name == 'postgresql' else func.trim(column, ' \t\r\n')


async def flush_unique(db):
    try:
        await db.flush()
    except IntegrityError:
        raise HTTPException(409, '并发登记或历史唯一身份冲突，未新增第二张应付；请刷新核对原单')


def number(value, label='账单编号', limit=50):
    if not normalized(value) or len(str(value)) > limit or '\x00' in str(value):
        raise HTTPException(400, f'{label}必填且不能超过{limit}字')
    return normalized(value)


def valid_date(value, label):
    try:
        result = datetime.fromisoformat(normalized(value))
        if result.tzinfo is not None:
            raise ValueError('bill dates are local dates')
        return result
    except (TypeError, ValueError):
        raise HTTPException(400, f'{label}格式不正确，请填写有效日期')


def valid_amount(value, label='金额'):
    try:
        if not math.isfinite(value) or value <= 0:
            raise ValueError()
    except (ValueError, TypeError):
        raise HTTPException(400, f'{label}必须是大于零的有限数字')
    return value


def fingerprint(values):
    return hashlib.sha256(json.dumps(values, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()


def invoice_identity(value, user):
    if not value:
        return None, None
    try:
        data = json.loads(value) if isinstance(value, str) else value
        if not isinstance(data, dict) or data.get('verified') is not True:
            raise ValueError()
        original = {key: data[key] for key in ('issuer_identifier', 'series', 'number')}
        if any(not isinstance(v, str) or not normalized(v) or len(v) > 150 or '\x00' in v for v in original.values()):
            raise ValueError()
    except (ValueError, TypeError, KeyError):
        raise HTTPException(400, '请核对供应商官方识别号、发票类型/系列及完整发票号；无法确认身份请留空')
    return {**original, 'verified_by': user.id, 'verified_at': thai_now().isoformat()}, fingerprint({k: normalized(v) for k,v in original.items()})


async def creation_lock(db, warehouse_id):
    # Consistent order across manual registration, approval and association: warehouse -> purchase -> bill.
    await db.execute(select(Warehouse.id).where(Warehouse.id == warehouse_id).with_for_update())
    missing = await missing_guards(await db.connection())
    if missing:
        raise HTTPException(409, {'code': 'payable_constraints_blocked', 'message': '历史冲突或迁移未完成，新增及关联应付已停止；请管理员运行只读核对脚本', 'missing_guards': missing})


async def purchase_by_number(db, warehouse_id, value):
    rows = (await db.execute(select(PurchaseOrder).where(PurchaseOrder.warehouse_id == warehouse_id,
        normalized_column(db,PurchaseOrder.order_number) == number(value, '采购单号')).order_by(PurchaseOrder.id).with_for_update())).scalars().all()
    if not rows:
        raise HTTPException(404, '本仓未找到该采购单')
    if len(rows) != 1:
        raise HTTPException(409, {'code': 'purchase_number_conflict', 'message': '本仓有多条同号采购，请管理员核对，未自动选择',
            'purchase_ids': [p.id for p in rows]})
    return rows[0]


async def active_purchase_bill(db, po, *, allow_bill_id=None):
    rows = (await db.execute(select(PayableBill).where(PayableBill.purchase_order_id == po.id,
        func.coalesce(PayableBill.status, 'pending') != 'voided').order_by(PayableBill.id))).scalars().all()
    if len(rows) > 1 or any(b.warehouse_id != po.warehouse_id for b in rows):
        raise HTTPException(409, '采购历史存在多张有效应付或仓库关联冲突，请管理员核对；未自动修复')
    if rows:
        b = rows[0]
        if b.id == allow_bill_id and po.payable_bill_id == b.id:
            return b
        if po.payable_bill_id != b.id or b.supplier_id != po.supplier_id or b.currency != po.currency:
            raise HTTPException(409, '采购与应付历史关联不一致，请管理员核对；未自动修复')
        return b
    if po.payable_bill_id:
        # Preserve the previous rule: no silent reuse of a purchase whose original bill was voided/missing.
        raise HTTPException(409, '该采购已关联历史或作废账单，本轮不自动重开；请保留原单并另建采购')
    return None


async def creation_replay(db, warehouse_id, key, signature):
    number(key, '请求编号', 100)
    rows = (await db.execute(select(PayableBill).where(PayableBill.warehouse_id == warehouse_id,
        PayableBill.create_request_key == key))).scalars().all()
    if len(rows) > 1:
        raise HTTPException(409, '历史请求编号冲突，请管理员核对')
    if not rows:
        return None
    if rows[0].create_request_fingerprint != signature:
        raise HTTPException(409, f'该请求已登记且内容不同，请查看原账单 #{rows[0].id}；未重复新增')
    return rows[0]


async def check_duplicates(db, bill, user, confirmation=None, *, exclude_id=None):
    window = get_settings().PAYABLE_DUPLICATE_WINDOW_DAYS
    if not isinstance(window, int) or window < 0:
        raise HTTPException(503, '疑似重复日期窗口配置无效，请管理员核对')
    try:
        first_day=bill.bill_date.date()-timedelta(days=window)
        last_day=bill.bill_date.date()+timedelta(days=window)
    except OverflowError:
        raise HTTPException(503, '疑似重复日期窗口超出日期支持范围，请管理员核对')
    predicates = [normalized_column(db,PayableBill.bill_number) == normalized(bill.bill_number)]
    within = ((cast(PayableBill.amount, Numeric(20,2)) == money(bill.amount)) & (PayableBill.currency == bill.currency)
        & (func.date(PayableBill.bill_date) >= first_day)
        & (func.date(PayableBill.bill_date) <= last_day))
    predicates.append(within)
    q = select(PayableBill).where(PayableBill.warehouse_id == bill.warehouse_id,
        or_((PayableBill.supplier_id == bill.supplier_id) & or_(*predicates[:2]),
            PayableBill.invoice_identity_key == bill.invoice_identity_key if bill.invoice_identity_key else False))
    if exclude_id is not None:
        q = q.where(PayableBill.id != exclude_id)
    rows = (await db.execute(q.order_by(PayableBill.id))).scalars().all()
    candidates = []
    hard = False
    for b in rows:
        reasons = []
        if b.supplier_id == bill.supplier_id and normalized(b.bill_number) == normalized(bill.bill_number):
            reasons.append('同供应商账单编号相同（非发票身份结论）')
        if (b.supplier_id == bill.supplier_id and b.currency == bill.currency and money(b.amount) == money(bill.amount)
                and abs((b.bill_date.date()-bill.bill_date.date()).days) <= window):
            reasons.append(f'同供应商、币种、金额且账单日期相距不超过{window}天')
        if bill.invoice_identity_key and b.invoice_identity_key == bill.invoice_identity_key:
            if b.status != 'voided': hard = True
            reasons.append('已核实的同一完整发票身份' if b.status != 'voided' else '同一已作废发票，重开须本次说明')
        candidates.append({'id': b.id, 'bill_number': b.bill_number, 'bill_date': b.bill_date.isoformat(),
            'amount': b.amount, 'currency': b.currency, 'status': b.status, 'reasons': reasons})
    if not candidates:
        return None
    if not can_read_bills(user):
        raise HTTPException(403, '发现重复风险，请有应付账款或付款计划读取权限的人员核对')
    challenge = {'code': 'payable_invoice_duplicate' if hard else 'payable_duplicate_confirmation',
        'message': '该真实供应商的同一发票已有有效应付，不能重复登记' if hard else '发现疑似重复，请逐项核对；不同业务可填写本次原因后继续',
        'hard_duplicate': hard, 'candidates': candidates, 'window_days': window}
    if hard:
        raise HTTPException(409, challenge)
    data = confirmation or {}
    if isinstance(data, str):
        try: data = json.loads(data)
        except (ValueError, TypeError): data = {}
    ids = [c['id'] for c in candidates]
    if (not isinstance(data, dict) or data.get('candidate_ids') != ids
            or not isinstance(data.get('reason'), str) or not data['reason'].strip()
            or len(data['reason']) > 1000):
        raise HTTPException(409, challenge)
    return {'operator_id': user.id, 'operator_name': user.display_name, 'confirmed_at': thai_now().isoformat(),
        'reason': data['reason'], 'candidates': candidates, 'candidate_ids': ids, 'window_days': window}


async def register_bill(db, bill, user, confirmation=None):
    number(bill.bill_number)
    valid_amount(bill.amount)
    bill.duplicate_confirmation = await check_duplicates(db, bill, user, confirmation)
    db.add(bill)
    await flush_unique(db)  # Unique indexes enforce this even if a writer bypassed the application check.
    if bill.duplicate_confirmation:
        await record_history(db, module='payable', record_id=bill.id, operator=user,
            operation_type='duplicate_confirm', after=bill.duplicate_confirmation, warehouse_id=bill.warehouse_id)
    return bill


async def register_purchase_bill(db, po, bill, user, confirmation=None):
    if await active_purchase_bill(db, po):
        raise HTTPException(409, '该采购单已有有效应付，不能再登记')
    bill.create_request_key = f'purchase:{po.id}'
    bill.create_request_fingerprint = fingerprint({'purchase_id': po.id})
    await register_bill(db, bill, user, confirmation)
    po.payable_bill_id = bill.id
    await db.flush()
    return bill

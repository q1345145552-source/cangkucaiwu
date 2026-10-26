"""Read-only purchase/bill linkage and supplier totals over existing records."""
from datetime import date
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select, or_
from app.database import get_db
from app.core.permissions import get_current_user, Role
from app.core.timezone import thai_today
from app.core.menu_registry import MENU_PERMISSIONS_BY_KEY
from app.models import PayableBill, PayablePayment, PaymentAccount, PurchaseOrder, Supplier, User, Warehouse
from app.services.money_period import money_period
from app.services.wallet import money, day
from app.services.warehouse_summary import warehouse_scope


async def current_supplier_warehouse(request: Request, user=Depends(get_current_user), db=Depends(get_db)):
    if user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF):
        raise HTTPException(403, '无权访问')
    warehouses = await warehouse_scope(db, user, request.headers.get('X-Warehouse-ID'))
    if len(warehouses) != 1:
        raise HTTPException(400, '请选择单个仓库查看采购与应付')
    return warehouses[0].id


def can_read_bills(user):
    labels = {MENU_PERMISSIONS_BY_KEY[k].label for k in ('payable', 'payment_plans')}
    return user.role == Role.WAREHOUSE_ADMIN or bool(labels.intersection(user.extra_permissions or []))


async def owned(db, model, ident, warehouse_id, label):
    obj = await db.get(model, ident)
    if obj is None:
        raise HTTPException(404, f'{label}不存在')
    if obj.warehouse_id != warehouse_id:
        raise HTTPException(403, f'无权查看其他仓库的{label}')
    return obj


async def checked_link(db, bill, po, warehouse_id):
    if (bill.warehouse_id != warehouse_id or po.warehouse_id != warehouse_id
            or bill.purchase_order_id != po.id or po.payable_bill_id != bill.id
            or bill.supplier_id != po.supplier_id or bill.currency != po.currency):
        raise HTTPException(409, '采购单与应付账单历史关联不一致，请管理员核对；未自动修正')


def bill_values(b):
    return {'id': b.id, 'warehouse_id': b.warehouse_id, 'supplier_id': b.supplier_id,
        'bill_number': b.bill_number, 'bill_date': b.bill_date, 'due_date': b.due_date,
        'currency': b.currency, 'amount': b.amount, 'paid_amount': b.paid_amount,
        'remaining_amount': float(money(b.amount) - money(b.paid_amount)) if b.paid_amount is not None else None, 'status': b.status,
        'need_boss_confirm': b.need_boss_confirm, 'purchase_order_id': b.purchase_order_id,
        'payment_voucher': b.payment_voucher, 'bill_attachment': b.bill_attachment,
        'remark': b.remark, 'detail': b.detail}


async def bill_detail(db, bill_id, warehouse_id):
    b = await owned(db, PayableBill, bill_id, warehouse_id, '账单')
    supplier = await owned(db, Supplier, b.supplier_id, warehouse_id, '供应商')
    po = None
    if b.purchase_order_id:
        po = await db.get(PurchaseOrder, b.purchase_order_id)
        if po is None: raise HTTPException(409, '关联采购单缺失，请管理员核对')
        await checked_link(db, b, po, warehouse_id)
    elif (await db.execute(select(PurchaseOrder.id).where(PurchaseOrder.payable_bill_id == b.id))).first():
        raise HTTPException(409, '采购单与应付账单历史关联不一致，请管理员核对')
    rows = (await db.execute(select(PayablePayment).where(PayablePayment.bill_id == b.id)
        .order_by(PayablePayment.paid_at, PayablePayment.id))).scalars().all()
    payments = []
    for p in rows:
        account = await db.get(PaymentAccount, p.account_id)
        if (p.warehouse_id != warehouse_id or p.currency != b.currency or account is None
                or account.warehouse_id != warehouse_id or (account.currency or 'THB') != p.currency):
            raise HTTPException(409, '逐笔付款的仓库、账户或币种关联异常，请管理员核对')
        operator = await db.get(User, p.operator_id)
        payments.append({'id': p.id, 'amount': float(p.amount), 'currency': p.currency,
            'account_name': account.account_name, 'paid_at': p.paid_at,
            'payment_method': p.payment_method, 'operator_name': operator.display_name if operator else '操作人档案缺失'})
    recorded = sum((money(p.amount) for p in rows), money(0))
    legacy = (money(b.legacy_paid_amount) if b.legacy_paid_amount is not None else money(b.paid_amount) - recorded) if b.paid_amount is not None else None
    warnings = []
    if legacy is None:
        warnings.append('累计已付未记录，历史付款及剩余应付需核对')
    elif legacy < 0 or legacy + recorded != money(b.paid_amount):
        warnings.append('账单累计与逐笔付款合计不一致，请管理员核对')
    return {**bill_values(b), 'supplier_name': supplier.name,
        'purchase_order_number': po.order_number if po else None,
        'payments': payments, 'recorded_payment_total': float(recorded),
        'legacy_paid_amount': float(legacy) if legacy is not None and legacy >= 0 else None,
        'legacy_paid_at': b.legacy_paid_at if b.legacy_paid_amount is not None else (b.paid_at if not rows else None),
        'legacy_note': '历史累计付款，缺逐笔明细；不与逐笔重复计算',
        'voucher_scope': '账单级凭证，不代表某一次逐笔付款', 'warnings': warnings}


async def purchase_detail(db, po_id, warehouse_id, user):
    po = await owned(db, PurchaseOrder, po_id, warehouse_id, '采购单')
    supplier = await owned(db, Supplier, po.supplier_id, warehouse_id, '供应商')
    warehouse = await db.get(Warehouse, warehouse_id)
    # Only explicit existing IDs are used. A supplier permission alone does not disclose bill/payment data.
    bill = None
    message = '待审批，尚未生成应付账单' if po.status == 'pending' else '尚未关联应付账单'
    if po.payable_bill_id:
        linked = await db.get(PayableBill, po.payable_bill_id)
        if linked is None: raise HTTPException(409, '关联账单缺失，请管理员核对')
        await checked_link(db, linked, po, warehouse_id)
        if can_read_bills(user):
            bill = await bill_detail(db, po.payable_bill_id, warehouse_id)
            message = None
        else: message = '没有应付账款或付款计划读取权限，付款信息不展示'
    elif (await db.execute(select(PayableBill.id).where(PayableBill.purchase_order_id == po.id))).first():
        raise HTTPException(409, '采购单与应付账单历史关联不一致，请管理员核对')
    return {'id': po.id, 'order_number': po.order_number, 'warehouse_id': po.warehouse_id,
        'warehouse_name': warehouse.name if warehouse else None,
        'supplier_id': po.supplier_id, 'supplier_name': supplier.name,
        'status': po.status, 'flow_status': po.flow_status, 'receipt_status': po.receipt_status,
        'items': po.items, 'total_amount': po.total_amount, 'currency': po.currency,
        'created_at': po.created_at, 'received_at': po.received_at, 'arrival_photo': po.arrival_photo,
        'sent_at': po.sent_at, 'receipt_uploaded_at': po.receipt_uploaded_at, 'shipped_at': po.shipped_at,
        'receipt_file': po.receipt_file, 'remark': po.remark, 'reject_reason': po.reject_reason,
        'bill': bill, 'bill_message': message, 'can_read_payable': can_read_bills(user)}


def filtered_bills(db, warehouse_id, *, start_date=None, end_date=None, month=None,
                   supplier_id=None, currency=None, status=None, source=None,
                   purchase_order_number=None, effective_only=False):
    start, end = money_period(month, start_date, end_date, default_start=date(1900, 1, 1), default_end=date.max)
    b = PayableBill
    q = select(b).where(b.warehouse_id == warehouse_id, day(db, b.bill_date) >= start, day(db, b.bill_date) <= end)
    for column, value in ((b.supplier_id, supplier_id), (b.currency, currency), (b.status, status), (b.source, source)):
        if value: q = q.where(column == value)
    if purchase_order_number:
        q = q.where(b.purchase_order_id.in_(select(PurchaseOrder.id).where(
            PurchaseOrder.warehouse_id == warehouse_id, PurchaseOrder.order_number == purchase_order_number.strip())))
    if effective_only:
        q = q.outerjoin(PurchaseOrder, PurchaseOrder.id == b.purchase_order_id).where(b.status != 'voided',
            or_(b.purchase_order_id.is_(None), (PurchaseOrder.status == 'confirmed') &
                (PurchaseOrder.warehouse_id == b.warehouse_id)))
    return q, start, end


async def bill_link_warnings(db, bills, warehouse_id):
    """Flag bad historical links without removing their existing effective debt or repairing it."""
    if not bills:
        return {}
    po_ids = {b.purchase_order_id for b in bills if b.purchase_order_id}
    bill_ids = {b.id for b in bills}
    orders = (await db.execute(select(PurchaseOrder).where(or_(
        PurchaseOrder.id.in_(po_ids), PurchaseOrder.payable_bill_id.in_(bill_ids))))).scalars().all()
    by_id = {p.id: p for p in orders}
    reverse = {p.payable_bill_id for p in orders if p.payable_bill_id}
    supplier_ids = set((await db.execute(select(Supplier.id).where(Supplier.warehouse_id == warehouse_id))).scalars())
    warnings = {}
    for b in bills:
        p = by_id.get(b.purchase_order_id)
        bad = b.supplier_id not in supplier_ids
        if b.purchase_order_id:
            bad = bad or p is None or (p.warehouse_id, p.supplier_id, p.currency, p.payable_bill_id) != (
                warehouse_id, b.supplier_id, b.currency, b.id)
        elif b.id in reverse:
            bad = True
        if bad:
            warnings[b.id] = '历史关联异常，请管理员核对；本单仍计入原有效应付范围，未自动修正'
    return warnings


async def supplier_totals(db, warehouse_id, **filters):
    q, start, end = filtered_bills(db, warehouse_id, effective_only=True, **filters)
    rows = (await db.execute(q.order_by(PayableBill.id))).scalars().all()
    suppliers = {s.id: s.name for s in (await db.execute(select(Supplier).where(Supplier.warehouse_id == warehouse_id))).scalars()}
    link_warnings = await bill_link_warnings(db, rows, warehouse_id)
    groups = {}
    for b in rows:
        key = (b.supplier_id, b.currency or 'THB')
        group = groups.setdefault(key, {'supplier_id': b.supplier_id, 'supplier_name': suppliers.get(b.supplier_id, '供应商关联异常'),
            'currency': key[1], 'bill_count': 0, 'total_amount': money(0), 'paid_amount': money(0),
            'unpaid_amount': money(0), 'overdue_amount': money(0), 'unknown_payment_count': 0,
            'link_warning_count': 0, 'link_warning_bill_ids': []})
        group['bill_count'] += 1
        group['total_amount'] += money(b.amount)
        if b.id in link_warnings:
            group['link_warning_count'] += 1
            group['link_warning_bill_ids'].append(b.id)
        if b.paid_amount is None:
            group['unknown_payment_count'] += 1
            continue
        remaining = money(b.amount) - money(b.paid_amount)
        group['paid_amount'] += money(b.paid_amount)
        group['unpaid_amount'] += remaining
        if b.due_date and b.due_date.date() < thai_today() and remaining > 0: group['overdue_amount'] += remaining
    totals = {k: {} for k in ('month_total', 'month_paid', 'month_unpaid', 'overdue')}
    unknown_counts = {}
    result = []
    for key, g in sorted(groups.items()):
        for field, name in [('total_amount', 'month_total'), ('paid_amount', 'month_paid'), ('unpaid_amount', 'month_unpaid'), ('overdue_amount', 'overdue')]:
            totals[name][key[1]] = totals[name].get(key[1], money(0)) + g[field]
        unknown_counts[key[1]] = unknown_counts.get(key[1], 0) + g['unknown_payment_count']
        for field in ('paid_amount', 'unpaid_amount', 'overdue_amount'):
            g['known_' + field] = g[field]
            if g['unknown_payment_count']:
                g[field] = None
        result.append({k: float(v) if hasattr(v, 'quantize') else v for k, v in g.items()})
    output = {'supplier_summary': result, 'start_date': str(start), 'end_date': str(end),
        'date_basis': '账单日期；有效应付；累计已付含历史；逾期是剩余应付的子集', 'warehouse_id': warehouse_id,
        'unknown_payment_count_by_currency': unknown_counts, 'link_warning_count': len(link_warnings)}
    for key, values in totals.items():
        values = {c: float(n) for c, n in values.items()}
        if key != 'month_total':
            output[key + '_known_by_currency'] = dict(values)
            values = {c: None if unknown_counts[c] else value for c, value in values.items()}
        output[key + '_by_currency'] = values
        output['overdue_total' if key == 'overdue' else key] = next(iter(values.values())) if len(values) == 1 else None if values else 0
    return output

"""Read-only transfer disclosure, counted from one original transfer, never its two flow legs."""
from fastapi import Depends, HTTPException, Request
from sqlalchemy import func, or_, select

from app.core.permissions import get_current_user
from app.database import get_db
from app.models import AccountTransfer, PaymentAccount
from app.services.wallet import money


async def selected_wallet_warehouses(request: Request, account_id: int | None = None, user=Depends(get_current_user), db=Depends(get_db)):
    from app.services.warehouse_summary import warehouse_scope
    ids = [w.id for w in await warehouse_scope(db, user, request.headers.get('X-Warehouse-ID'))]
    if account_id is not None and (await db.execute(select(PaymentAccount.id).where(
            PaymentAccount.id == account_id, PaymentAccount.warehouse_id.in_(ids)))).scalar_one_or_none() is None:
        raise HTTPException(403, '无权访问所选账户')
    return ids


async def transfer_summary(db, warehouse_ids, start, end, *, account_id=None, currency=None,
                           source=None, flow_type=None, unassigned=False, include=True):
    t = AccountTransfer
    filters = [t.warehouse_id.in_(warehouse_ids), t.transfer_date >= start, t.transfer_date <= end]
    if account_id is not None:
        own = (await db.execute(select(PaymentAccount.id).where(PaymentAccount.id == account_id,
            PaymentAccount.warehouse_id.in_(warehouse_ids)))).scalar_one_or_none()
        if own is None:
            raise HTTPException(403, '无权访问所选账户')
        if flow_type == 'income': filters.append(t.to_account_id == account_id)
        elif flow_type == 'expense': filters.append(t.from_account_id == account_id)
        else: filters.append(or_(t.from_account_id == account_id, t.to_account_id == account_id))
    if currency: filters.append(t.currency == currency)
    # Category/employee/customer-only views and non-transfer sources cannot contain transfers.
    if not include or unassigned or source not in (None, '', 'transfer'):
        rows = []
    else:
        rows = (await db.execute(select(t.currency, func.count(t.id), func.sum(t.amount)).where(
            *filters).group_by(t.currency).order_by(t.currency))).all()
    return {'label': '内部转账', 'excluded_from_income_expense': True,
        'scope_label': '涉及该账户的调拨额' if account_id is not None else '所选仓库及期间的调拨额',
        'by_currency': {c: float(money(value)) for c, count, value in rows},
        'count_by_currency': {c: count for c, count, value in rows}, 'total_count': sum(n for c, n, v in rows)}


def transfer_record_filters(options):
    return dict(account_id=options.get('account_id'), currency=options.get('currency'), source=options.get('source'),
        include=not any(options.get(k) is not None and options.get(k) != '' for k in
            ('category_id', 'category_group', 'cost_category', 'customer_id', 'supplier_id', 'search')))


def append_transfer_sheet(workbook, summary):
    sheet = workbook.create_sheet('内部转账（不计收支）')
    sheet.append(['范围', '币种', '笔数', '调拨金额', '说明'])
    for cur in sorted({'THB', 'CNY'} | set(summary['by_currency'])):
        sheet.append([summary['scope_label'], cur, summary['count_by_currency'].get(cur, 0),
            summary['by_currency'].get(cur, 0), '不计入收入、支出、净收支或成本；每笔转账只计一次'])
    for col in ('A', 'E'): sheet.column_dimensions[col].width = 55

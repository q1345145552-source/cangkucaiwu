"""仪表盘与成本报表共用的应付实付只读口径，不写账单、账户或流水。"""
from datetime import date

from sqlalchemy import Date, Numeric, cast, func, select, type_coerce

from app.models.payable import PayableBill
from app.models.supplier import PurchaseOrder


def procurement_payment_rows(db, warehouse_ids):
    bill = PayableBill
    # paid_at 是带时区的付款时间，PostgreSQL 按泰国业务日期划分月份。
    paid_day = func.date(func.timezone("Asia/Bangkok", bill.paid_at)) if db.bind.dialect.name == "postgresql" else func.date(bill.paid_at)
    return select(
        bill.id.label("bill_id"), bill.warehouse_id.label("warehouse_id"),
        bill.bill_number.label("bill_number"), bill.supplier_id.label("supplier_id"),
        type_coerce(paid_day, Date).label("payment_date"),
        cast(bill.paid_amount, Numeric(18, 2)).label("amount"),
        func.coalesce(bill.currency, "THB").label("currency"),
    ).outerjoin(PurchaseOrder, bill.purchase_order_id == PurchaseOrder.id).where(
        bill.warehouse_id.in_(warehouse_ids), bill.status != "voided",
        bill.paid_amount > 0, bill.paid_at.is_not(None),
        bill.purchase_order_id.is_(None) | (PurchaseOrder.status == "confirmed"),
    ).subquery("procurement_payments")


async def procurement_payment_totals(db, warehouse_ids, start: date, end: date):
    """两端包含；按 paid_at 所属业务日过滤，只合计 paid_amount。"""
    rows = procurement_payment_rows(db, warehouse_ids)
    return (await db.execute(select(rows.c.currency, func.sum(rows.c.amount)).where(
        rows.c.payment_date >= start, rows.c.payment_date <= end,
    ).group_by(rows.c.currency))).all()

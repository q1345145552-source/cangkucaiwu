"""采购实际付款的公共口径：应付逐笔付款及采购用途的垫款归还。"""
from sqlalchemy import select, func
from app.services.wallet import procurement_rows as procurement_payment_rows, flow_query


async def procurement_payment_totals(db, warehouse_ids, start, end):
    rows = flow_query(db, warehouse_ids)
    return (await db.execute(select(rows.c.currency, func.sum(rows.c.amount)).where(
        rows.c.date >= start, rows.c.date <= end, rows.c.category_name == "采购",
        rows.c.type == "expense", rows.c.status == "active", rows.c.is_internal_transfer.is_(False),
    ).group_by(rows.c.currency))).all()

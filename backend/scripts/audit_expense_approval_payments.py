"""只读列出旧费用付款疑点；不猜付款人、不补账、不修改历史状态。

显式设置 EXPENSE_APPROVAL_AUDIT_DATABASE_URL 后运行；连接事务强制只读。
"""
import asyncio
import json
import os

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.models.expense_approval import ExpenseApproval


async def collect_anomalies(db):
    rows = (await db.execute(select(ExpenseApproval).order_by(ExpenseApproval.id))).scalars().all()
    result = []
    for row in rows:
        reasons = []
        if row.status == "completed":
            reasons.append("旧版免审批直接完成，实际付款需人工核对")
        if row.status == "paid":
            if row.payer_id is None or row.paid_at is None:
                reasons.append("已付款但缺付款人或付款时间")
            if row.fund_source == "fund" and row.fund_item_id is None:
                reasons.append("缺少旧备用金开销关联，不能据此断定未扣款")
            if row.fund_source == "company" and row.expense_record_id is None:
                reasons.append("已付款但缺公司支出关联")
        if row.status in ("pending", "rejected", "approved") and (row.expense_record_id or row.fund_item_id):
            reasons.append("尚未付款但已有关联记账记录")
        if reasons:
            result.append({"id": row.id, "warehouse_id": row.warehouse_id, "status": row.status,
                "amount": row.amount, "currency": row.currency or "THB", "fund_source": row.fund_source,
                "expense_record_id": row.expense_record_id, "fund_item_id": row.fund_item_id,
                "payer_id": row.payer_id, "paid_at": row.paid_at.isoformat() if row.paid_at else None,
                "reasons": reasons})
    return result


async def main():
    url = os.environ.get("EXPENSE_APPROVAL_AUDIT_DATABASE_URL")
    if not url:
        raise SystemExit("请显式设置只读核查连接 EXPENSE_APPROVAL_AUDIT_DATABASE_URL")
    engine = create_async_engine(url)
    try:
        async with async_sessionmaker(engine)() as db:
            await db.execute(text("SET TRANSACTION READ ONLY"))
            rows = await collect_anomalies(db)
            print(json.dumps({"read_only": True, "count": len(rows), "data": rows}, ensure_ascii=False, indent=2))
            await db.rollback()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

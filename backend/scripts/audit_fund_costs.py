"""只读审计旧备用金合计，可在加新字段之前/之后运行；不改任何数据。

容器内：python scripts/audit_fund_costs.py
按仓库、币种分别输出；按分类名识别的正式支出仅列为待人工核对，不猜测关联。
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import and_, cast, func, inspect, literal, Numeric, select, text
from app.database import async_session_factory, _get_engine
from app.models.employee_advance import EmployeeAdvance
from app.models.expense_fund import ExpenseFund, ExpenseFundItem, ExpenseFundDisbursement
from app.models.income_expense import ExpenseRecord, IncomeExpenseCategory


async def audit(db, warehouse_ids=None):
    def schema(session):
        reader = inspect(session.connection())
        return {name: {c["name"] for c in reader.get_columns(name)} if reader.has_table(name) else set()
            for name in ("expense_fund_items", "employee_advances", "expense_fund_disbursements")}
    columns = await db.run_sync(schema)
    f, i, a, d, e, c = ExpenseFund, ExpenseFundItem, EmployeeAdvance, ExpenseFundDisbursement, ExpenseRecord, IncomeExpenseCategory
    old_item = i.cost_record_only.is_(False) if "cost_record_only" in columns["expense_fund_items"] else literal(True)
    scope = f.warehouse_id.in_(warehouse_ids) if warehouse_ids is not None else literal(True)
    joined = {"fund_item_id", "expense_record_id", "expense_tracking_enabled"} <= columns["employee_advances"]
    not_prepaid = ~select(a.id).where(a.fund_item_id == i.id, a.expense_tracking_enabled.is_(True),
        a.warehouse_id == f.warehouse_id).exists() if joined else literal(True)
    async def grouped(query):
        rows = (await db.execute(query)).all()
        return [{"warehouse_id": r[0], "currency": r[1], "count": r[2], "amount": round(float(r[3] or 0), 2)} for r in rows]
    def item_query(*conditions):
        cur = func.coalesce(i.currency, "THB")
        return select(f.warehouse_id, cur, func.count(i.id), func.sum(cast(i.amount, Numeric(18, 2))))\
            .join(f, f.id == i.fund_id).where(scope, old_item, *conditions)\
            .group_by(f.warehouse_id, cur).order_by(f.warehouse_id, cur)
    expense_scope = e.warehouse_id.in_(warehouse_ids) if warehouse_ids is not None else literal(True)
    no_new_disbursement = ~select(d.id).where(d.expense_record_id == e.id).exists() if columns["expense_fund_disbursements"] else literal(True)
    e_cur = func.coalesce(e.currency, "THB")
    named = select(e.warehouse_id, e_cur, func.count(e.id), func.sum(cast(e.amount, Numeric(18, 2))))\
        .join(c, and_(c.id == e.category_id, c.warehouse_id == e.warehouse_id))\
        .where(expense_scope, c.name.like("%备用金%"), no_new_disbursement)\
        .group_by(e.warehouse_id, e_cur).order_by(e.warehouse_id, e_cur)
    known = []
    if joined:
        q = select(e.warehouse_id, e_cur, func.count(e.id), func.sum(cast(e.amount, Numeric(18, 2))))\
            .join(a, and_(a.expense_record_id == e.id, a.warehouse_id == e.warehouse_id))\
            .join(i, i.id == a.fund_item_id).where(expense_scope, a.source == "fund", old_item)\
            .group_by(e.warehouse_id, e_cur).order_by(e.warehouse_id, e_cur)
        known = await grouped(q)
    return {"legacy_merged_operating_costs": await grouped(item_query(i.review_status == "approved", not_prepaid)),
        "legacy_ledger_item_rows": await grouped(item_query()),
        "formal_expenses_with_fund_category_name": await grouped(named),
        "known_fund_source_employee_advance_expenses": known,
        "notes": ["合并成本与资金流水引用同一条开销时不是两条数据库支出，不能把这些合计重复相加。",
            "按分类名称检出的正式支出须人工确认来源；不按名字或金额猜测关联。", "此审计只读，不回填或删除历史账目。"]}


async def main():
    async with async_session_factory()() as db:
        if db.bind.dialect.name == "postgresql":
            await db.execute(text("SET TRANSACTION READ ONLY"))
        print(json.dumps(await audit(db), ensure_ascii=False, indent=2))
        await db.rollback()
    await _get_engine().dispose()


if __name__ == "__main__":
    asyncio.run(main())

"""采购实付：真实请求、跨月、作废、多币种、只读和旧盈亏保护。"""
import asyncio
import ast
from contextlib import asynccontextmanager
from datetime import date, datetime
import json
from pathlib import Path
import subprocess
import types

import pytest
from sqlalchemy import event, select

from app.database import Base
from app.models.income_expense import ExpenseRecord, IncomeExpenseCategory
from app.models.payable import PayableBill
from app.models.supplier import PurchaseOrder, Supplier
from app.services.procurement_payments import procurement_payment_rows, procurement_payment_totals
import app.api.v1.dashboard as dashboard
from tests.test_round2_permissions import auth, set_perms
from tests.test_round3_permissions import hr_environment

RANGE = {"start_date": "2026-10-01", "end_date": "2026-10-31"}


@asynccontextmanager
async def environment(tmp_path, monkeypatch):
    async with hr_environment(tmp_path, monkeypatch) as (engine, f, c):
        @event.listens_for(engine.sync_engine, "connect")
        def functions(conn, _):
            conn.create_function("to_char", 2, lambda value, fmt: str(value)[:7] if value else None)
        await engine.dispose()
        monkeypatch.setattr(dashboard, "thai_today", lambda: date(2026, 10, 19))
        await set_perms(f, 3, ["报表中心"])
        await set_perms(f, 4, ["报表中心"])
        async with f() as db:
            db.add_all([Supplier(id=i, warehouse_id=i, name=f"隔离供应商{i}") for i in (1, 2)])
            db.add_all([
                IncomeExpenseCategory(id=80, warehouse_id=1, type="expense", category_group="operating", name="采购"),
                IncomeExpenseCategory(id=81, warehouse_id=1, type="expense", category_group="operating", name="其他费用"),
            ])
            await db.flush()
            db.add(ExpenseRecord(warehouse_id=1, category_id=80, account_id=1, amount=250, currency="THB",
                expense_date=datetime(2026, 10, 8), remark="原独立手工采购，未与应付单关联"))
            db.add(ExpenseRecord(warehouse_id=1, category_id=81, account_id=1, amount=750, currency="THB",
                expense_date=datetime(2026, 10, 8), remark="原运营支出"))
            db.add_all([
                PayableBill(id=1, warehouse_id=1, supplier_id=1, bill_number="TEST-OCT-UNPAID",
                    bill_date=datetime(2026, 10, 4), due_date=datetime(2026, 11, 1), amount=1000, paid_amount=0, status="pending", currency="THB"),
                PayableBill(id=2, warehouse_id=1, supplier_id=1, bill_number="TEST-SEP-PAID-OCT",
                    bill_date=datetime(2026, 9, 20), due_date=datetime(2026, 11, 1), amount=3000, paid_amount=3000,
                    paid_at=datetime(2026, 10, 10, 12), status="paid", currency="THB"),
            ])
            await db.commit()
        yield engine, f, c


async def snapshot(factory):
    async with factory() as db:
        return {table.name: [tuple(row) for row in (await db.execute(select(table).order_by(*table.primary_key.columns))).all()]
            for table in Base.metadata.sorted_tables}


async def read_views(c, uid=1):
    cockpit = await c.get("/api/v1/dashboard/cockpit", headers=auth(uid))
    report = await c.get("/api/v1/reports/cost-funds-debt", headers=auth(uid), params=RANGE)
    assert cockpit.status_code == report.status_code == 200, (cockpit.text, report.text)
    return cockpit.json(), report.json()


def category(report, name, currency="THB"):
    block = next(b for b in report["currencies"] if b["currency"] == currency)
    return next((r for r in block["costs"]["data"] if r["name"] == name), {"count": 0, "amount": 0})


@pytest.mark.parametrize("uid", [1, 3, 4])
def test_unpaid_excluded_cross_month_paid_included_shared_report_and_other_dashboard_data_unchanged(tmp_path, monkeypatch, uid):
    async def run():
        async with environment(tmp_path, monkeypatch) as (_, f, c):
            before = await snapshot(f)
            # 在相同隔离库运行基线 cockpit，逐字段对比非采购部分。
            root = Path(__file__).resolve().parents[2]
            baseline = types.ModuleType("old_dashboard_procurement")
            exec(compile(subprocess.check_output(["git", "show", "7dbf327:backend/app/api/v1/dashboard.py"], cwd=root), "old_dashboard_procurement", "exec"), baseline.__dict__)
            baseline.thai_today = lambda: date(2026, 10, 19)
            async with f() as db:
                from app.models import User
                user = await db.get(User, uid); user._warehouse_ids = [1]
                old = await baseline.dashboard_cockpit(user, db)
                old_trends = await baseline.dashboard_trends(user, db)
            now, report = await read_views(c, uid)
            assert old["finance"]["procurement"]["expense"] == [{"currency": "THB", "amount": 1000}]
            assert now["finance"]["procurement"]["expense"] == [{"currency": "THB", "amount": 3000}]
            assert now["finance"]["month"]["procurement_expense"] == [{"currency": "THB", "amount": 3000}]
            assert category(report, "采购") == {"name": "采购", "count": 1, "amount": 3000}
            assert category(report, "手工采购") == {"name": "手工采购", "count": 1, "amount": 250}
            for copy in (old, now):
                copy["finance"]["month"].pop("procurement_expense")
                copy["finance"]["procurement"].pop("expense")
            assert now == old  # 运营、收入、月度总支出/盈亏、余额、待办、人效等完全未改。
            assert now["finance"]["month"]["operating_expense"] == [{"currency": "THB", "amount": 1000}]
            assert now["finance"]["month"]["income"] == [{"currency": "THB", "amount": 100}]
            assert now["finance"]["month"]["profit"] == [{"currency": "THB", "amount": -1900}]
            trends = (await c.get("/api/v1/dashboard/trends", headers=auth(uid))).json()
            assert sum(r["amount"] for r in trends["procurement_suppliers"]["THB"]) == 3000
            assert sum(r["amount"] for r in old_trends["procurement_suppliers"]["THB"]) == 1000
            trends.pop("procurement_suppliers"); old_trends.pop("procurement_suppliers")
            assert trends == old_trends  # 收入、支出趋势等其余图表逐字段保持原样。
            costs = (await c.get("/api/v1/reports/cost-funds-debt/costs", headers=auth(uid),
                params={**RANGE, "cost_category": "采购"})).json()
            assert costs["total"] == 1 and costs["totals_by_currency"]["THB"] == 3000
            row = costs["data"][0]
            assert row["source"] == "payable" and row["source_id"] == 2 and row["id"] == "payable-2" and row["is_read_only"]
            assert row["remark"] == "TEST-SEP-PAID-OCT" and row["date"] == "2026-10-10"
            async with f() as db:
                assert (await db.get(PayableBill, 1)).paid_amount == 0
                assert len((await db.execute(select(ExpenseRecord))).scalars().all()) == 2  # 只读投影，不自动补支出。
            assert await snapshot(f) == before
            if uid == 1:
                print("PROCUREMENT_MONTH", json.dumps({"unpaid_bill": "TEST-OCT-UNPAID", "unpaid_amount": 1000,
                    "cross_month_bill": "TEST-SEP-PAID-OCT", "paid_in_october": 3000, "dashboard_before": 1000,
                    "dashboard_after": 3000, "report_purchase": 3000, "manual_purchase_preserved": 250,
                    "operating_expense_before_after": [1000, 1000], "income_before_after": [100, 100],
                    "profit_before_after": [-1900, -1900], "database_unchanged": True}, ensure_ascii=False))
    asyncio.run(run())


def test_partial_payment_not_bill_total_and_date_currency_warehouse_void_guards(tmp_path, monkeypatch):
    async def run():
        async with environment(tmp_path, monkeypatch) as (_, f, c):
            async with f() as db:
                cases = [
                    (3, 1, "PARTIAL", 9000, 400.25, datetime(2026, 10, 12), "partially_paid", "THB"),
                    (4, 1, "VOIDED", 700, 700, datetime(2026, 10, 12), "voided", "THB"),
                    (5, 1, "PRIOR-PAID", 800, 800, datetime(2026, 9, 30), "paid", "THB"),
                    (6, 1, "NEXT-PAID", 900, 900, datetime(2026, 11, 1), "paid", "THB"),
                    (7, 1, "UNKNOWN-DATE", 600, 600, None, "paid", "THB"),
                    (8, 2, "OTHER-WH", 10000, 10000, datetime(2026, 10, 12), "paid", "THB"),
                    (9, 1, "CNY", 200, 200, datetime(2026, 10, 1), "paid", "CNY"),
                    (10, 1, "MONTH-END", 50, 50, datetime(2026, 10, 31, 23, 59, 59), "paid", "THB"),
                ]
                for bid, wid, number, total, paid, when, status, cur in cases:
                    db.add(PayableBill(id=bid, warehouse_id=wid, supplier_id=wid, bill_number=number,
                        bill_date=datetime(2026, 10, 1), due_date=datetime(2026, 11, 1), amount=total,
                        paid_amount=paid, paid_at=when, status=status, currency=cur))
                db.add(PurchaseOrder(id=1, warehouse_id=1, supplier_id=1, order_number="DRAFT-PO", status="draft", total_amount=500, items=[]))
                await db.flush()
                db.add(PayableBill(id=11, warehouse_id=1, supplier_id=1, bill_number="DRAFT-PO-BILL", purchase_order_id=1,
                    bill_date=datetime(2026, 10, 1), due_date=datetime(2026, 11, 1), amount=500, paid_amount=500,
                    paid_at=datetime(2026, 10, 12), status="paid", currency="THB"))
                await db.commit()
                totals = dict(await procurement_payment_totals(db, [1], date(2026, 10, 1), date(2026, 10, 31)))
                assert totals == {"THB": 3450.25, "CNY": 200}
            before = await snapshot(f)
            cockpit, report = await read_views(c)
            assert {r["currency"]: r["amount"] for r in cockpit["finance"]["procurement"]["expense"]} == {"THB": 3450.25, "CNY": 200}
            assert category(report, "采购")["amount"] == 3450.25 and category(report, "采购", "CNY")["amount"] == 200
            assert await snapshot(f) == before
    asyncio.run(run())


def test_payable_balances_ledger_and_all_other_dashboard_functions_unchanged():
    root = Path(__file__).resolve().parents[2]
    for path in ("backend/app/api/v1/payable.py", "backend/app/api/v1/income_expense.py", "backend/app/services/account_balances.py",
                 "backend/app/api/v1/payroll.py", "backend/app/services/payroll_expense.py"):
        assert (root / path).read_bytes() == subprocess.check_output(["git", "show", "7dbf327:" + path], cwd=root)
    for path, allowed in (("backend/app/api/v1/dashboard.py", {"dashboard_cockpit", "dashboard_trends"}),
                          ("backend/app/services/cost_funds_debt.py", {"cost_query", "cost_list", "report"})):
        def functions(source):
            return {n.name: ast.dump(n, include_attributes=False) for n in ast.parse(source).body
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name not in allowed}
        assert functions((root / path).read_text()) == functions(subprocess.check_output(["git", "show", "7dbf327:" + path], cwd=root, text=True))

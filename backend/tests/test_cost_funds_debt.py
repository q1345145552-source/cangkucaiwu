"""三张账：真实请求、多币种、跨模块一致与只读快照。"""
import asyncio
from datetime import date, datetime
from pathlib import Path
from contextlib import asynccontextmanager
from decimal import Decimal
import json
import pytest
from sqlalchemy import select, event
from app.models import User, UserWarehouse, CashAdvance, PaymentAccount
from app.models.income_expense import IncomeExpenseCategory, IncomeRecord, ExpenseRecord
from app.models.expense_fund import ExpenseFund, ExpenseFundItem
from app.database import Base
from app.services import cost_funds_debt as service
from tests.test_reimbursement_payments import environment as previous, approved as reimb, pay, upload
from tests.test_cash_advance_repayments import approved as loan, repay, voucher
from tests.test_round2_permissions import auth, set_perms

BASE = "/api/v1/reports/cost-funds-debt"
RANGE = {"start_date": "2026-10-01", "end_date": "2026-10-31"}


@asynccontextmanager
async def environment(tmp_path, monkeypatch):
    async with previous(tmp_path, monkeypatch) as (engine, f, c):
        async with f() as db:
            (await db.get(ExpenseFund, 1)).receive_date = datetime(2026, 9, 30)
            # 前轮基线运营支出750；增加真实工资、采购、报销、备用金成本和普通收入。
            db.add_all([IncomeExpenseCategory(id=80, warehouse_id=1, type="expense", category_group="operating", name="采购"),
                IncomeExpenseCategory(id=81, warehouse_id=1, type="income", category_group="operating", name="仓储费")])
            db.add(ExpenseRecord(warehouse_id=1, category_id=80, account_id=1, amount=250, currency="THB", expense_date=datetime(2026, 10, 8), remark="采购成本"))
            db.add(IncomeRecord(warehouse_id=1, category_id=81, account_id=1, amount=500, currency="THB", income_date=datetime(2026, 10, 8), remark="真实账户收入"))
            db.add(ExpenseFundItem(fund_id=1, expense_date=datetime(2026, 10, 8), amount=1000, currency="THB", category="运输费", description="已通过备用金成本", review_status="approved"))
            db.add(ExpenseFundItem(fund_id=1, expense_date=datetime(2026, 10, 8), amount=9999, currency="THB", category="其他", description="驳回的不算成本", review_status="rejected"))
            db.add(PaymentAccount(id=5, warehouse_id=1, account_name="人民币银行", account_type="bank", account_number="CNY5", currency="CNY", opening_balance=4000, status="inactive"))
            db.add(ExpenseRecord(warehouse_id=1, category_id=80, account_id=4, amount=300, currency="CNY", expense_date=datetime(2026, 10, 8), remark="人民币采购"))
            db.add(User(id=7, username="warehouse2-admin", display_name="仓2老板", role="warehouse_admin", password_hash="unused", warehouse_id=2))
            db.add(UserWarehouse(user_id=7, warehouse_id=2))
            await db.commit()
        aid = await loan(c, amount=10000)
        rid = await reimb(c, amount=2000)
        assert (await pay(c, rid, await upload(c, rid), funding_source="cash_advance", payment_account_id=None, cash_advance_id=aid)).status_code == 200
        rid2 = await reimb(c, amount=2000)
        assert (await pay(c, rid2, await upload(c, rid2))).status_code == 200
        # 账户工资路径沿用前轮原接口；用当前已确认的工资单2，实发1234.56。
        r = await c.post("/api/v1/payroll/2/disburse", headers=auth(1), json={"funding_source": "company_account", "account_id": 1})
        assert r.status_code == 200, r.text
        yield engine, f, c, aid


async def snapshot(f):
    async with f() as db:
        return {t.name: [tuple(row) for row in (await db.execute(select(t).order_by(*t.primary_key.columns))).all()]
            for t in Base.metadata.sorted_tables}


def test_report_costs_accounts_debt_details_and_no_writes(tmp_path, monkeypatch):
    async def run():
        async with environment(tmp_path, monkeypatch) as (engine, f, c, aid):
            before = await snapshot(f)
            r = await c.get(BASE, headers=auth(1), params=RANGE)
            assert r.status_code == 200, r.text
            data = r.json()
            thb = next(x for x in data["currencies"] if x["currency"] == "THB")
            cny = next(x for x in data["currencies"] if x["currency"] == "CNY")
            costs = (await c.get(BASE + "/costs", headers=auth(1), params={**RANGE, "page_size": 200})).json()
            print("REPORT_INITIAL", json.dumps(data, ensure_ascii=False))
            assert thb["costs"]["total"] == costs["totals_by_currency"]["THB"] == 7234.56
            assert cny["costs"]["total"] == costs["totals_by_currency"]["CNY"] == 300
            assert sum((money(x["amount"]) for x in costs["data"] if x["currency"] == "THB"), Decimal(0)) == Decimal("7234.56")
            for block in data["currencies"]:
                for account in block["funds"]["data"]:
                    flows = (await c.get(BASE + "/flows", headers=auth(1), params={**RANGE, "account_id": account["account_id"], "currency": block["currency"]})).json()
                    assert flows["income_by_currency"].get(block["currency"], 0) == account["inflow"]
                    assert flows["expense_by_currency"].get(block["currency"], 0) == account["outflow"]
                    assert money(account["opening_balance"]) + money(account["inflow"]) - money(account["outflow"]) == money(account["closing_balance"])
                loans = (await c.get(BASE + "/advances", headers=auth(1), params={**RANGE, "currency": block["currency"]})).json()
                assert sum(x["outstanding_amount"] for x in loans["data"]) == block["debt"]["total"]["outstanding_amount"]
            assert thb["debt"]["total"]["outstanding_amount"] == 10000
            rec = thb["reconciliation"]
            assert rec["cash_advance_cost"] == 2000 and rec["expense_fund_cost"] == 1000
            assert sum(x["amount"] for x in rec["details"]) == 3000 and rec["detail_count"] == 2
            assert await snapshot(f) == before
    asyncio.run(run())


def money(v): return Decimal(str(v)).quantize(Decimal('.01'))


def block(data, cur="THB"): return next(x for x in data["currencies"] if x["currency"] == cur)


def test_original_formula_balances_and_non_cost_repayment_stays_red(tmp_path, monkeypatch):
    async def run():
        async with environment(tmp_path, monkeypatch) as (_, f, c, aid):
            old = block((await c.get(BASE, headers=auth(1), params=RANGE)).json())
            assert old["reconciliation"]["balanced"]
            assert [old["reconciliation"][k] for k in ("cost_total", "company_outflow", "difference")] == [7234.56, 4234.56, 3000]
            returned = await repay(c, aid, await voucher(c), amount="1000")
            assert returned.status_code == 200, returned.text
            now = block((await c.get(BASE, headers=auth(1), params=RANGE)).json())
            r = now["reconciliation"]
            assert not r["balanced"] and r["unreconciled_difference"] == -1000
            assert [r[k] for k in ("cost_total", "company_outflow", "difference", "non_company_cost")] == [7234.56, 5234.56, 2000, 3000]
            assert r["non_cost_outflows"] == [{"name": "垫款归还", "count": 1, "amount": 1000}]
            assert now["debt"]["total"] == {"amount": 10000, "repaid_amount": 1000, "outstanding_amount": 9000}
            listing = (await c.get("/api/v1/cash-advances", headers=auth(1), params={**RANGE, "status": "confirmed"})).json()
            assert sum(x["outstanding_amount"] for x in listing["data"]) == 9000
            revoked = await c.post(f"/api/v1/cash-advances/repayments/{returned.json()['repayment']['id']}/revoke", headers=auth(1), json={"reason": "归还测试恢复"})
            assert revoked.status_code == 200
            restored = block((await c.get(BASE, headers=auth(1), params=RANGE)).json())
            assert restored == old
            print("THREE_BOOKS_DIFF", json.dumps({"before": old["reconciliation"], "after_repay": r, "debt_after_repay": now["debt"]["total"]}, ensure_ascii=False))
    asyncio.run(run())


def test_fund_withdrawal_unassigned_and_weekly_dates(tmp_path, monkeypatch):
    async def run():
        async with environment(tmp_path, monkeypatch) as (_, f, c, aid):
            week = {"start_date": "2026-10-05", "end_date": "2026-10-11"}
            r = await c.get(BASE, headers=auth(1), params=week)
            assert r.status_code == 200
            thb, cny = block(r.json()), block(r.json(), "CNY")
            assert thb["costs"]["total"] == 1250 and cny["costs"]["total"] == 300
            assert thb["reconciliation"]["company_outflow"] == 250 and thb["reconciliation"]["difference"] == 1000
            assert thb["reconciliation"]["balanced"] and thb["debt"]["total"]["outstanding_amount"] == 0
            async with f() as db:
                (await db.get(ExpenseFund, 1)).receive_date = datetime(2026, 10, 18)
                await db.commit()
            thb = block((await c.get(BASE, headers=auth(1), params=RANGE)).json())
            assert thb["funds"]["unassigned"]["outflow"] == 5000
            assert thb["reconciliation"]["unreconciled_difference"] == -5000
            assert thb["reconciliation"]["non_cost_outflows"] == [{"name": "备用金领用（未指定账户）", "count": 1, "amount": 5000}]
            unassigned = (await c.get(BASE + "/flows", headers=auth(1), params={**RANGE, "unassigned": True})).json()
            assert unassigned["expense_by_currency"] == {"THB": 5000}
            assert all(x["account_id"] is None for x in unassigned["data"])
            print("THREE_BOOKS_WEEK", json.dumps({"range": week, "THB": {"cost": 1250, "company_outflow": 250, "difference": 1000}, "CNY": {"cost": 300}}, ensure_ascii=False))
    asyncio.run(run())


@pytest.mark.parametrize("uid,grant,expected", [(1, False, 200), (2, True, 403), (3, True, 200), (3, False, 403), (4, True, 200), (4, False, 403), (5, True, 403)])
def test_reports_permission_does_not_grant_business_writes(tmp_path, monkeypatch, uid, grant, expected):
    async def run():
        async with environment(tmp_path, monkeypatch) as (_, f, c, aid):
            await set_perms(f, uid, ["报表中心"] if grant else [])
            before = await snapshot(f)
            for suffix in ("", "/costs", "/flows", "/advances"):
                r = await c.get(BASE + suffix, headers=auth(uid), params=RANGE)
                assert r.status_code == expected, r.text
                if expected == 200 and suffix == "":
                    assert r.json() == (await c.get(BASE, headers=auth(1), params=RANGE)).json()
            assert await snapshot(f) == before
            if uid in (3, 4) and grant:
                assert (await c.post("/api/v1/reimbursement/1/pay", headers=auth(uid), json={})).status_code == 403
                assert (await c.post("/api/v1/cash-advances", headers=auth(uid), json={"advance_date": "2026-10-18", "amount": 100, "purpose": "salary"})).status_code == 403
    asyncio.run(run())


def test_warehouse_scope_and_bad_dates_and_full_snapshot_select_only(tmp_path, monkeypatch):
    async def run():
        async with environment(tmp_path, monkeypatch) as (engine, f, c, aid):
            before = await snapshot(f)
            statements = []
            def guard(conn, cursor, sql, params, context, many):
                statements.append(sql)
                assert sql.lstrip().upper().startswith(("SELECT", "WITH", "PRAGMA")), sql
            event.listen(engine.sync_engine, "before_cursor_execute", guard)
            try:
                r = await c.get(BASE, headers=auth(7), params={**RANGE, "warehouse_id": 1})
                assert r.status_code == 200
                assert r.json()["warehouse_ids"] == [2]
                assert block(r.json())["costs"]["total"] == 0
                assert block(r.json())["debt"]["total"]["outstanding_amount"] == 0
                for suffix in ("/costs", "/flows", "/advances"):
                    r = await c.get(BASE + suffix, headers=auth(7), params=RANGE)
                    assert r.status_code == 200 and r.json()["total"] == 0
                assert (await c.get(BASE, headers={**auth(1), "X-Warehouse-ID": "all"}, params=RANGE)).status_code == 400
                for params in ({"start_date": "2026-02-30"}, {"start_date": "2026-10-20", "end_date": "2026-10-10"}):
                    assert (await c.get(BASE, headers=auth(1), params=params)).status_code == 400
                for suffix in ("/costs", "/flows", "/advances"):
                    assert (await c.get(BASE + suffix, headers=auth(1), params={"page": 0})).status_code == 422
            finally: event.remove(engine.sync_engine, "before_cursor_execute", guard)
            assert statements and await snapshot(f) == before
    asyncio.run(run())


def test_pagination_category_exact_payer_and_shared_list_projection(tmp_path, monkeypatch):
    async def run():
        async with environment(tmp_path, monkeypatch) as (_, f, c, aid):
            whole = (await c.get(BASE + "/costs", headers=auth(1), params=RANGE)).json()
            seen = []
            for page in range(1, 5):
                p = (await c.get(BASE + "/costs", headers=auth(1), params={**RANGE, "page": page, "page_size": 2})).json()
                assert p["total"] == whole["total"] and p["totals_by_currency"] == whole["totals_by_currency"]
                seen.extend((x["source"], x["source_id"]) for x in p["data"])
            assert len(set(seen)) == len(seen) == whole["total"] == 8
            shared = (await c.get("/api/v1/income-expense/expense", headers=auth(1), params={**RANGE, "cost_view": "unified", "category_group": "operating", "page_size": 25})).json()
            assert shared == whole
            for category in ("员工工资", "报销", "采购", "备用金开销"):
                r = (await c.get(BASE + "/costs", headers=auth(1), params={**RANGE, "cost_category": category, "currency": "THB"})).json()
                assert all(x["category_name"] == category for x in r["data"])
            rows = (await c.get(BASE + "/advances", headers=auth(1), params={**RANGE, "payer_id": 4})).json()
            assert rows["total"] == 1 and rows["data"][0]["id"] == aid
            assert rows["data"][0]["reimbursement_used_amount"] == 2000 and rows["data"][0]["available_amount"] == 8000
            assert (await c.get(BASE + "/advances", headers=auth(1), params={**RANGE, "payer_id": 6})).json()["total"] == 0
            report = (await c.get(BASE + "/flows", headers=auth(1), params={**RANGE, "account_id": 1})).json()
            raw = (await c.get("/api/v1/income-expense/ledger", headers=auth(1), params={**RANGE, "flow_scope": "company", "account_id": 1})).json()
            assert report == raw
    asyncio.run(run())

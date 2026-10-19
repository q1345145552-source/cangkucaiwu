"""逐笔拨付只记一次成本/资金，后续开销只记录，真实请求和隔离数据库。"""
from tests.financial_reversal_test_support import without_disabled_gate
import asyncio
from contextlib import asynccontextmanager
from datetime import date, datetime
from decimal import Decimal
import json
from pathlib import Path
import subprocess

from fastapi import HTTPException
import pytest
from sqlalchemy import event, func, select

from app.models import User, PaymentAccount
from app.models.expense_fund import ExpenseFund, ExpenseFundItem, ExpenseFundDisbursement, FundRechargeRequest
from app.models.income_expense import ExpenseRecord, IncomeExpenseCategory
from app.models.employee_advance import EmployeeAdvance
from app.models.data_change_history import DataChangeHistory
from app.services import fund_disbursement as s
from scripts.audit_fund_costs import audit
from tests.test_round2_permissions import auth, set_perms, png
from tests.test_round3_permissions import hr_environment, snapshot

BASE = "/api/v1/expense-fund"
RANGE = {"start_date": "2026-10-01", "end_date": "2026-10-31"}


@asynccontextmanager
async def environment(tmp_path, monkeypatch):
    async with hr_environment(tmp_path, monkeypatch) as (engine, f, c):
        @event.listens_for(engine.sync_engine, "connect")
        def functions(conn, _):
            conn.create_function("to_char", 2, lambda value, fmt: str(value)[:7] if value else None)
        await engine.dispose()
        async with f() as db:
            a = await db.get(PaymentAccount, 1)
            a.account_name, a.account_type, a.opening_balance, a.currency, a.status = "测试现金", "cash", 20000, "THB", "active"
            db.add(PaymentAccount(id=3, warehouse_id=1, account_name="人民币账户", account_type="bank",
                account_number="CNY", opening_balance=30000, currency="CNY", status="active"))
            await db.commit()
        await set_perms(f, 4, ["备用金管理", "员工预支"])
        r = await c.post(BASE + "/accounts", headers=auth(1), json={"employee_id": 4, "fund_limit": 20000})
        assert r.status_code == 200, r.text
        yield engine, f, c, r.json()["id"]


async def topup(c, fid, *, uid=1, amount=10000, **extra):
    return await c.post(f"{BASE}/accounts/{fid}/topup", headers=auth(uid), json={
        "amount": amount, "payment_account_id": 1, "receive_date": "2026-10-10", **extra})


async def spend(c, fid, *, amount=2000):
    return await c.post(f"{BASE}/accounts/{fid}/items", headers=auth(4), json={
        "amount": amount, "expense_date": "2026-10-11", "category": "耗材", "currency": "THB", "description": "购买包装耗材"})


async def values(c, fid):
    raw = await c.get("/api/v1/income-expense/expense", headers=auth(1), params={**RANGE, "category_group": "operating"})
    unified = await c.get("/api/v1/income-expense/expense", headers=auth(1), params={**RANGE, "category_group": "operating", "cost_view": "unified"})
    flow = await c.get("/api/v1/income-expense/ledger?source=expense_fund", headers=auth(1))
    company = await c.get("/api/v1/income-expense/ledger", headers=auth(1), params={**RANGE, "flow_scope": "company", "flow_type": "expense"})
    accounts = await c.get("/api/v1/accounts", headers=auth(1))
    funds = await c.get(BASE + "/accounts", headers=auth(1))
    for r in (raw, unified, flow, company, accounts, funds):
        assert r.status_code == 200, r.text
    return {"expense_count": raw.json()["total"], "expense_amount": sum(r["amount"] for r in raw.json()["data"]),
        "unified_count": unified.json()["total"], "unified_amount": unified.json()["totals_by_currency"].get("THB", 0),
        "flow_count": flow.json()["total"], "flow_amount": flow.json()["total_expense"],
        "company_flow_count": company.json()["total"], "company_flow_amount": company.json()["expense_by_currency"].get("THB", 0),
        "company_cash": next(a["current_balance"] for a in accounts.json()["data"] if a["id"] == 1),
        "fund": next(a for a in funds.json()["data"] if a["id"] == fid)}


def test_10000_disburse_2000_spend_one_cost_one_flow_and_bidirectional_links(tmp_path, monkeypatch):
    async def run():
        async with environment(tmp_path, monkeypatch) as (_, f, c, fid):
            old_payroll = await snapshot(f)
            r = await topup(c, fid)
            assert r.status_code == 200, r.text
            paid = r.json()
            assert paid["expense_record_id"] and paid["disbursement_id"] and paid["account_balance"] == 10000
            after_pay = await values(c, fid)
            assert after_pay["expense_count"] == after_pay["unified_count"] == after_pay["flow_count"] == after_pay["company_flow_count"] == 1
            assert after_pay["expense_amount"] == after_pay["unified_amount"] == after_pay["flow_amount"] == after_pay["company_flow_amount"] == 10000
            assert after_pay["company_cash"] == 10000 and after_pay["fund"]["total_topped_up"] == 10000 and after_pay["fund"]["available"] == 10000
            item = await spend(c, fid)
            assert item.status_code == 200, item.text
            iid = item.json()["id"]
            assert item.json()["cost_record_only"] and item.json()["disbursement_sources"] == [{"disbursement_id": paid["disbursement_id"], "amount": 2000, "label": f"拨付 #{paid['disbursement_id']}"}]
            up = await c.post(f"{BASE}/accounts/{fid}/items/{iid}/upload-receipt", headers=auth(4), files={"file": ("receipt.png", png(), "image/png")})
            assert up.status_code == 200, up.text
            after_spend = await values(c, fid)
            for key in ("expense_count", "unified_count", "flow_count", "company_flow_count", "expense_amount", "unified_amount", "flow_amount", "company_flow_amount", "company_cash"):
                assert after_spend[key] == after_pay[key]
            assert after_spend["fund"]["total_spent"] == 2000 and after_spend["fund"]["available"] == 8000
            review = await c.post(BASE + "/review/batch", headers=auth(1), json={"item_ids": [iid], "action": "approve"})
            assert review.status_code == 200, review.text
            final = await values(c, fid)
            assert final == after_spend  # 审核通过同样不再新增成本或资金记录。
            history = await c.get(f"{BASE}/accounts/{fid}/disbursements", headers=auth(1))
            assert history.status_code == 200, history.text
            row = history.json()["data"][0]
            assert row["expense_record_id"] == paid["expense_record_id"] and row["used_amount"] == 2000
            assert row["items"][0]["item_id"] == iid and row["items"][0]["receipt"] == up.json()["receipt"]
            for view in ("records", "unified"):
                cost = (await c.get("/api/v1/income-expense/expense", headers=auth(1), params={**RANGE, "cost_view": view})).json()["data"][0]
                assert cost["fund_disbursement_id"] == paid["disbursement_id"] and cost["fund_id"] == fid and cost["is_read_only"]
            async with f() as db:
                exp = await db.get(ExpenseRecord, paid["expense_record_id"])
                cat = await db.get(IncomeExpenseCategory, exp.category_id)
                assert cat.name == "备用金拨付" and cat.category_group == "operating"
                assert exp.expense_date == datetime(2026, 10, 10) and "supervisor" in exp.remark and "仓1" in exp.remark
                assert await db.get(ExpenseFundItem, iid)
            report = await c.get("/api/v1/reports/cost-funds-debt", headers=auth(1), params=RANGE)
            assert report.status_code == 200, report.text
            thb = next(b for b in report.json()["currencies"] if b["currency"] == "THB")
            assert thb["costs"]["total"] == 10000 and thb["reconciliation"]["company_outflow"] == 10000 and thb["reconciliation"]["balanced"]
            previews = (await c.get("/api/v1/reports/previews", headers=auth(1), params=RANGE)).json()
            assert previews["previews"]["income-expense"]["total_expense"] == 10000
            monthly = (await c.get("/api/v1/income-expense/monthly-summary", headers=auth(1), params=RANGE)).json()
            assert monthly["total_expense"] == 10000
            assert (await c.post(BASE + "/recharge/request", headers=auth(4), json={"amount": 500})).status_code == 200
            requests = (await c.get(BASE + "/recharge/requests", headers=auth(1))).json()["data"]
            assert requests[0]["available"] == 8000
            assert await snapshot(f) == old_payroll
            print("FUND_DISBURSEMENT_MAIN", json.dumps({"payment_response": paid,
                "after_disbursement": after_pay, "after_spend_2000": after_spend,
                "after_approve": final, "final_cost_total": thb["costs"]["total"]}, ensure_ascii=False))
    asyncio.run(run())


@pytest.mark.parametrize("uid", [1, 3, 4])
def test_original_roles_and_recharge_approval_one_expense_and_repeat_denied(tmp_path, monkeypatch, uid):
    async def run():
        async with environment(tmp_path, monkeypatch) as (_, f, c, fid):
            await set_perms(f, uid, ["备用金管理"])
            req = await c.post(BASE + "/recharge/request", headers=auth(4), json={"amount": 1000, "reason": "日常耗材"})
            assert req.status_code == 200, req.text
            rid = req.json()["id"]
            r = await c.post(BASE + "/recharge/review", headers=auth(uid), json={"request_id": rid,
                "action": "approve", "payment_account_id": 1, "receive_date": "2026-10-12"})
            assert r.status_code == 200 and r.json()["recharge_request_id"] == rid, r.text
            repeat = await c.post(BASE + "/recharge/review", headers=auth(uid), json={"request_id": rid, "action": "approve", "payment_account_id": 1})
            assert repeat.status_code == 400 and repeat.json()["detail"] == "该申请已处理"
            async with f() as db:
                assert (await db.execute(select(func.count()).select_from(ExpenseRecord))).scalar_one() == 1
                assert (await db.execute(select(func.count()).select_from(ExpenseFundDisbursement))).scalar_one() == 1
            direct = await topup(c, fid, uid=uid, amount=500)
            assert direct.status_code == 200, direct.text
            await set_perms(f, uid, [])
            if uid != 1:
                assert (await topup(c, fid, uid=uid, amount=1)).status_code == 403
    asyncio.run(run())


@pytest.mark.parametrize("case,detail", [(None, "请选择备用金拨付账户"), (2, "付款账户不存在或不属于当前仓库"), (3, "付款账户币种必须与备用金账户一致"), (999, "付款账户不存在或不属于当前仓库"), ("inactive", "付款账户已停用"), ("poor", "付款账户余额不足")])
def test_account_guards_leave_all_three_ledgers_unchanged(tmp_path, monkeypatch, case, detail):
    async def run():
        async with environment(tmp_path, monkeypatch) as (_, f, c, fid):
            if case in ("inactive", "poor"):
                async with f() as db:
                    account = await db.get(PaymentAccount, 1)
                    if case == "inactive": account.status = "inactive"
                    else: account.opening_balance = 500
                    await db.commit()
            r = await topup(c, fid, payment_account_id=1 if isinstance(case, str) else case)
            assert r.status_code == 400 and r.json()["detail"] == detail, r.text
            async with f() as db:
                fund = await db.get(ExpenseFund, fid)
                assert fund.amount == fund.remaining_balance == 0
                assert (await db.execute(select(func.count()).select_from(ExpenseRecord))).scalar_one() == 0
                assert (await db.execute(select(func.count()).select_from(ExpenseFundDisbursement))).scalar_one() == 0
    asyncio.run(run())


@pytest.mark.parametrize("via_request", [False, True])
def test_history_failure_rolls_back_account_fund_expense_and_approval(tmp_path, monkeypatch, via_request):
    async def run():
        async with environment(tmp_path, monkeypatch) as (_, f, c, fid):
            rid = None
            if via_request:
                rid = (await c.post(BASE + "/recharge/request", headers=auth(4), json={"amount": 1000})).json()["id"]
            async def fail(db, **kwargs):
                await db.flush()
                raise HTTPException(500, "模拟拨付留痕失败")
            monkeypatch.setattr(s, "record_history", fail)
            r = await c.post(BASE + "/recharge/review", headers=auth(1), json={"request_id": rid, "action": "approve", "payment_account_id": 1}) if via_request else await topup(c, fid)
            assert r.status_code == 500, r.text
            state = await values(c, fid)
            assert state["company_cash"] == 20000 and state["fund"]["available"] == 0 and state["expense_count"] == state["flow_count"] == 0
            async with f() as db:
                assert (await db.execute(select(func.count()).select_from(ExpenseFundDisbursement))).scalar_one() == 0
                if rid: assert (await db.get(FundRechargeRequest, rid)).status == "pending"
    asyncio.run(run())


def test_legacy_audit_preserved_and_new_spending_does_not_change_old_totals(tmp_path, monkeypatch):
    async def run():
        async with environment(tmp_path, monkeypatch) as (engine, f, c, fid):
            async with f() as db:
                fund = await db.get(ExpenseFund, fid)
                fund.amount = fund.remaining_balance = 5000
                fund.receive_date = datetime(2026, 10, 1)
                for amount, status in [(1000, "approved"), (500, "approved"), (300, "pending"), (200, "rejected")]:
                    db.add(ExpenseFundItem(fund_id=fid, expense_date=datetime(2026, 10, 3), category="历史耗材",
                        amount=amount, currency="THB", description="历史记录", review_status=status, cost_record_only=False))
                cat = IncomeExpenseCategory(warehouse_id=1, type="expense", name="历史备用金开销", category_group="operating", status="active")
                db.add(cat); await db.flush()
                db.add(ExpenseRecord(warehouse_id=1, category_id=cat.id, account_id=1, amount=400, currency="THB", expense_date=datetime(2026, 10, 2), remark="历史人工登记，不猜测来源"))
                await db.commit()
                before = await audit(db, [1])
                old_rows = [tuple(r) for r in (await db.execute(select(ExpenseFundItem.__table__).order_by(ExpenseFundItem.id))).all()]
            async with engine.begin() as conn:
                await s.backfill_fund_disbursement_categories(conn)
                await s.backfill_fund_disbursement_categories(conn)
            assert before["legacy_merged_operating_costs"] == [{"warehouse_id": 1, "currency": "THB", "count": 2, "amount": 1500}]
            assert before["legacy_ledger_item_rows"] == [{"warehouse_id": 1, "currency": "THB", "count": 4, "amount": 2000}]
            assert before["formal_expenses_with_fund_category_name"] == [{"warehouse_id": 1, "currency": "THB", "count": 1, "amount": 400}]
            paid = await topup(c, fid, amount=1000)
            assert paid.status_code == 200, paid.text
            item = await spend(c, fid, amount=200)
            assert item.status_code == 200, item.text
            async with f() as db:
                after = await audit(db, [1])
                assert before == after
                assert [tuple(r) for r in (await db.execute(select(ExpenseFundItem.__table__).where(ExpenseFundItem.cost_record_only == False).order_by(ExpenseFundItem.id))).all()] == old_rows
            state = await values(c, fid)
            assert state["expense_amount"] == 1400 and state["unified_amount"] == 2900  # 原正式400+旧合并1500+新拨付1000，没加新开销200。
            assert (await c.get(f"{BASE}/accounts/{fid}/items", headers=auth(1))).json()["data"]
            print("FUND_LEGACY_AUDIT", json.dumps({"before": before, "after": after,
                "after_new_disbursement_and_spend": state}, ensure_ascii=False))
    asyncio.run(run())


def test_fifo_sources_multiple_disbursements_and_cross_warehouse(tmp_path, monkeypatch):
    async def run():
        async with environment(tmp_path, monkeypatch) as (_, f, c, fid):
            a = (await topup(c, fid, amount=3000)).json()["disbursement_id"]
            assert (await spend(c, fid, amount=2500)).status_code == 200
            b = (await topup(c, fid, amount=5000)).json()["disbursement_id"]
            item = await spend(c, fid, amount=1500)
            assert item.status_code == 200, item.text
            assert [(p["disbursement_id"], p["amount"]) for p in item.json()["disbursement_sources"]] == [(a, 500), (b, 1000)]
            state = await values(c, fid)
            assert state["expense_amount"] == state["flow_amount"] == 8000 and state["fund"]["available"] == 4000
            async with f() as db:
                other = ExpenseFund(warehouse_id=2, employee_id=6, amount=0, remaining_balance=0, receive_date=datetime(2026, 10, 1), purpose="外仓")
                db.add(other); await db.commit(); other_id = other.id
            assert (await topup(c, other_id, amount=1)).status_code == 403
            assert (await c.get(f"{BASE}/accounts/{other_id}/disbursements", headers=auth(1))).status_code == 404
            # 只能从业务模块维护联动支出，不能绕过拨付随意改变金额或删支出。
            eid = (await c.get(f"{BASE}/accounts/{fid}/disbursements", headers=auth(1))).json()["data"][0]["expense_record_id"]
            blocked = await c.delete(f"/api/v1/income-expense/expense/{eid}", headers=auth(1))
            assert blocked.status_code == 400 and "备用金拨付联动支出" in blocked.text
            blocked = await c.delete("/api/v1/accounts/1", headers=auth(1))
            assert blocked.status_code == 400 and "备用金拨付记录" in blocked.text
    asyncio.run(run())


def test_new_fund_employee_advance_dedup_is_read_only_payroll_and_reimbursement_code_unchanged(tmp_path, monkeypatch):
    async def run():
        async with environment(tmp_path, monkeypatch) as (_, f, c, fid):
            assert (await topup(c, fid)).status_code == 200
            r = await c.post("/api/v1/employee-advances", headers=auth(1), json={"employee_id": 1,
                "amount": 1000, "advance_date": "2026-10-11", "source": "fund", "fund_account_id": fid})
            assert r.status_code == 200 and r.json()["expense_record_id"], r.text
            state = await values(c, fid)
            assert state["expense_count"] == state["flow_count"] == 1 and state["expense_amount"] == state["unified_amount"] == state["flow_amount"] == 10000
            async with f() as db:
                assert (await db.execute(select(func.count()).select_from(ExpenseRecord))).scalar_one() == 2  # 预支原有写入保留，只在查询去重。
                assert (await db.execute(select(func.count()).select_from(EmployeeAdvance))).scalar_one() == 1
            assert state["fund"]["available"] == 9000
    asyncio.run(run())
    root = Path(__file__).resolve().parents[2]
    for path in ("backend/app/api/v1/payroll.py", "backend/app/services/payroll_expense.py", "backend/app/api/v1/employee_advance.py",
        "backend/app/services/employee_advance_expense.py", "backend/app/api/v1/reimbursement.py", "backend/app/services/reimbursement_payment.py"):
        assert without_disabled_gate((root / path).read_text()).encode() == subprocess.check_output(["git", "show", f"ee327fa:{path}"], cwd=root)


def test_all_warehouse_admin_review_uses_request_warehouse_not_primary(tmp_path, monkeypatch):
    async def run():
        from app.models import UserWarehouse
        async with environment(tmp_path, monkeypatch) as (_, f, c, fid):
            async with f() as db:
                db.add(UserWarehouse(user_id=1, warehouse_id=2))
                db.add(User(id=7, username="other_supervisor", display_name="另一仓主管", role="supervisor", password_hash="unused", warehouse_id=2, extra_permissions=["备用金管理"]))
                db.add(UserWarehouse(user_id=7, warehouse_id=2))
                (await db.get(PaymentAccount, 2)).opening_balance = 20000
                await db.commit()
            headers = {**auth(1), "X-Warehouse-ID": "2"}
            r = await c.post(BASE + "/accounts", headers=headers, json={"employee_id": 7, "fund_limit": 20000})
            assert r.status_code == 200, r.text
            req = await c.post(BASE + "/recharge/request", headers=auth(7), json={"amount": 1000})
            assert req.status_code == 200, req.text
            result = await c.post(BASE + "/recharge/review", headers={**auth(1), "X-Warehouse-ID": "all"},
                json={"request_id": req.json()["id"], "action": "approve", "payment_account_id": 2})
            assert result.status_code == 200 and result.json()["warehouse_id"] == 2, result.text
    asyncio.run(run())


def test_cny_disbursement_cost_flow_and_remaining_are_not_mixed_with_thb(tmp_path, monkeypatch):
    async def run():
        async with environment(tmp_path, monkeypatch) as (_, f, c, fid):
            async with f() as db:
                (await db.get(ExpenseFund, fid)).currency = "CNY"
                await db.commit()
            paid = await topup(c, fid, amount=1000, payment_account_id=3)
            assert paid.status_code == 200 and paid.json()["account_balance"] == 29000, paid.text
            item = await c.post(f"{BASE}/accounts/{fid}/items", headers=auth(4), json={"amount": 200,
                "expense_date": "2026-10-11", "category": "耗材", "currency": "CNY", "description": "人民币耗材"})
            assert item.status_code == 200, item.text
            r = await c.get("/api/v1/reports/cost-funds-debt", headers=auth(1), params=RANGE)
            assert r.status_code == 200, r.text
            cny = next(b for b in r.json()["currencies"] if b["currency"] == "CNY")
            thb = next(b for b in r.json()["currencies"] if b["currency"] == "THB")
            assert cny["costs"]["total"] == cny["reconciliation"]["company_outflow"] == 1000
            assert cny["funds"]["data"][0]["closing_balance"] == 29000
            assert thb["costs"]["total"] == thb["reconciliation"]["company_outflow"] == 0
            fund = (await c.get(BASE + "/accounts", headers=auth(1))).json()["data"][0]
            assert fund["available"] == 800
    asyncio.run(run())

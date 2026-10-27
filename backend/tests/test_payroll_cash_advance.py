"""资金来源真实接口回归：垫款记成本不动资金，公司账户只扣一次。"""
import ast
import asyncio
import json
import subprocess
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models import PaymentAccount, CashAdvance
from app.models.payroll import PayrollRecord
from app.models.income_expense import ExpenseRecord
from app.models.data_change_history import DataChangeHistory
import app.services.payroll_expense as service
import app.api.v1.payroll as payroll_api
from tests.test_round2_permissions import auth, set_perms
from tests.test_cash_advance_repayments import environment as repayment_environment, approved, voucher, repay
from tests.test_cash_advances import finance_snapshot
from tests.round3_flow_support import prepare_payroll, historical_payroll, assert_disabled, DeferredChecks


@asynccontextmanager
async def environment(tmp_path, monkeypatch):
    async with repayment_environment(tmp_path, monkeypatch) as (engine, factory, c):
        async with factory() as db:
            (await db.get(PayrollRecord, 2)).net_pay = 7000
            db.add(PaymentAccount(id=3, warehouse_id=1, account_name="测试银行", account_type="bank",
                account_number="test-bank", currency="THB", opening_balance=20000, status="active"))
            await db.commit()
        await prepare_payroll(factory,c,2)
        yield factory, c


async def balances(c):
    r = await c.get("/api/v1/accounts", headers=auth(1))
    assert r.status_code == 200, r.text
    return {a["id"]: a["current_balance"] for a in r.json()["data"]}


async def ledger(c):
    r = await c.get("/api/v1/income-expense/ledger", headers=auth(1))
    assert r.status_code == 200, r.text
    return r.json()


async def costs(c):
    r = await c.get("/api/v1/income-expense/expense?category_group=operating", headers=auth(1))
    assert r.status_code == 200, r.text
    data = r.json()
    return {"count": data["total"], "amount": sum(r["amount"] for r in data["data"]), "data": data["data"]}


async def disburse(c, aid, *, rid=2, uid=3, **fields):
    return await c.post(f"/api/v1/payroll/{rid}/disburse", headers=auth(uid), json={
        "funding_source": "cash_advance", "cash_advance_id": aid, **fields,
    })


async def usage(c, aid):
    r = await c.get(f"/api/v1/cash-advances/{aid}/repayments", headers=auth(1))
    assert r.status_code == 200, r.text
    return r.json()


def test_cost_7000_company_accounts_and_ledger_unchanged_then_revoke(tmp_path, monkeypatch):
    async def run():
        async with environment(tmp_path, monkeypatch) as (f, c):
            aid = await approved(c, amount=10000)
            before = await finance_snapshot(f)
            before_balances, before_ledger, before_costs = await balances(c), await ledger(c), await costs(c)
            paid = await disburse(c, aid)
            assert paid.status_code == 200, paid.text
            data = paid.json()
            assert data["cash_advance_id"] == aid and data["account_id"] is None and data["net_pay"] == 7000
            expense_id = data["expense_record_id"]
            after_costs = await costs(c)
            deferred=DeferredChecks()
            with deferred.check("7000 salary cost row/count/amount/source"):
                assert (after_costs["count"], after_costs["amount"]) == (3, 7750)
                assert expense_id is not None, data
                expense = next(x for x in after_costs["data"] if x["id"] == expense_id)
                assert expense["category_name"] == "员工工资" and expense["amount"] == 7000 and expense["account_id"] is None
                assert expense["cash_advance_id"] == aid and expense["funding_source"] == "cash_advance"
            assert await balances(c) == before_balances == {1: 10000, 3: 20000}
            assert await ledger(c) == before_ledger
            used = await usage(c, aid)
            assert used["advance"]["outstanding_amount"] == 10000 and used["advance"]["repaid_amount"] == 0
            assert used["payroll_usage"]["payroll_used_amount"] == 7000 and used["payroll_usage"]["payroll_available_amount"] == 3000
            assert [(x["payroll_record_id"], x["amount"]) for x in used["payroll_usage"]["data"]] == [(2, 7000)]
            loan_list = (await c.get("/api/v1/cash-advances", headers=auth(1))).json()["data"]
            assert next(x for x in loan_list if x["id"] == aid)["payroll_used_amount"] == 7000
            report = await c.get("/api/v1/reports/income-expense?start_date=2026-10-01&end_date=2026-10-31", headers=auth(1))
            with deferred.check("7000 report cost total"):
                assert report.status_code == 200 and report.json()["total_expense_by_currency"] == {"THB": 7750}
            # The linked cost cannot be changed/deleted from the ordinary expense page.
            with deferred.check("linked cost edit protection requires generated expense"):
                assert expense_id is not None, data
                denied = await c.delete(f"/api/v1/income-expense/expense/{expense_id}", headers=auth(1))
                assert denied.status_code == 400 and "工资联动支出" in denied.text
            duplicate = await disburse(c, aid)
            assert duplicate.status_code == 400
            revoked = await historical_payroll(f,c,2)
            assert revoked["reversed_cash_advance_id"] == aid
            after_revoke = await usage(c, aid)
            assert after_revoke["payroll_usage"]["data"] == []
            assert after_revoke["payroll_usage"]["payroll_used_amount"] == 0
            assert after_revoke["payroll_usage"]["payroll_available_amount"] == 10000
            assert after_revoke["advance"]["outstanding_amount"] == 10000
            assert await costs(c) == before_costs and await ledger(c) == before_ledger and await balances(c) == before_balances
            async with f() as db:
                r = await db.get(PayrollRecord, 2)
                assert r.status == "confirmed" and not r.disbursed and r.cash_advance_id is None and r.expense_record_id is None and r.net_pay == 7000
                assert expense_id is None or await db.get(ExpenseRecord, expense_id) is None
                operations = (await db.execute(select(DataChangeHistory.operation_type).where(
                    DataChangeHistory.module == "cash_advances", DataChangeHistory.record_id == aid,
                ))).scalars().all()
                assert "payroll_use" in operations and "payroll_use_revoke" in operations
            after = await finance_snapshot(f)
            for name in before:
                if name != "payroll_records": assert before[name] == after[name], name
            assert [r for r in before["payroll_records"] if r[0] != 2] == [r for r in after["payroll_records"] if r[0] != 2]
            deferred.finish()
            print("PAYROLL_ADVANCE_MONEY", json.dumps({"paid": data, "cost_before": before_costs["amount"],
                "cost_after": after_costs["amount"], "balances_before": before_balances, "balances_after": before_balances,
                "ledger_count_before": before_ledger["total"], "ledger_count_after": before_ledger["total"],
                "usage": used["payroll_usage"], "outstanding": used["advance"]["outstanding_amount"],
                "revoked": revoked, "cost_after_revoke": (await costs(c))["amount"], "usage_after_revoke": after_revoke["payroll_usage"]}, ensure_ascii=False))
    asyncio.run(run())


def test_company_account_deducts_once_and_revoke_restores_with_same_cost_and_flow(tmp_path, monkeypatch):
    async def run():
        async with environment(tmp_path, monkeypatch) as (f, c):
            before_ledger = await ledger(c)
            r = await c.post("/api/v1/payroll/2/disburse", headers=auth(3), json={"account_id": 1})
            assert r.status_code == 200, r.text
            assert r.json()["funding_source"] == "company_account" and r.json()["cash_advance_id"] is None
            assert await balances(c) == {1: 3000, 3: 20000}
            changed_currency = await c.put("/api/v1/accounts/1", headers=auth(1), json={
                "account_name": "测试现金", "account_type": "cash", "account_number": "cash", "currency": "CNY",
            })
            assert changed_currency.status_code == 400 and "该账户已有资金记录，不能修改币种" in changed_currency.text
            assert (await costs(c))["amount"] == 7750
            flow = await ledger(c)
            assert flow["total"] == before_ledger["total"] + 1 and flow["total_expense"] == before_ledger["total_expense"] + 7000
            again = await c.post("/api/v1/payroll/2/disburse", headers=auth(3), json={"account_id": 1})
            assert again.status_code == 400 and (await balances(c))[1] == 3000
            await historical_payroll(f,c,2)
            assert await balances(c) == {1: 10000, 3: 20000}
            assert (await costs(c))["amount"] == 750 and await ledger(c) == before_ledger
            async with f() as db:
                assert (await db.get(PaymentAccount, 1)).opening_balance == 10750
            print("PAYROLL_COMPANY_MONEY", {"before": 10000, "paid": 3000, "revoked": 10000, "expense_added": 7000, "flow_added": 7000})
    asyncio.run(run())


@pytest.mark.parametrize("kind", ["insufficient", "pending", "rejected", "repaid", "currency", "foreign", "missing", "mixed", "company_mixed"])
def test_invalid_funding_never_changes_any_money(tmp_path, monkeypatch, kind):
    async def run():
        async with environment(tmp_path, monkeypatch) as (f, c):
            aid = await approved(c, amount=1000 if kind == "insufficient" else 10000, currency="CNY" if kind == "currency" else "THB")
            async with f() as db:
                a = await db.get(CashAdvance, aid)
                if kind in ("pending", "rejected"): a.status = kind
                if kind == "repaid": a.status, a.repaid_amount = "repaid", a.amount
                if kind == "foreign": a.warehouse_id = 2
                await db.commit()
            fields = {"account_id": 1} if kind == "mixed" else {}
            if kind == "company_mixed": fields = {"funding_source": "company_account", "account_id": 1}
            before = await finance_snapshot(f)
            r = await disburse(c, None if kind == "missing" else aid, **fields)
            assert r.status_code == 400, r.text
            if kind == "insufficient": assert r.json()["detail"] == "垫款单剩余金额不足"
            if kind == "currency":
                assert "币种" in r.json()["detail"]
                assert (await usage(c, aid))["payroll_usage"]["payroll_available_amount"] == 0
            assert await finance_snapshot(f) == before and await balances(c) == {1: 10000, 3: 20000}
    asyncio.run(run())


def test_reuse_limit_batch_total_idempotence_and_revoke_releases_capacity(tmp_path, monkeypatch):
    async def run():
        async with environment(tmp_path, monkeypatch) as (f, c):
            aid = await approved(c, amount=10000)
            assert (await disburse(c, aid)).status_code == 200
            async with f() as db:
                r = await db.get(PayrollRecord, 1)
                r.status, r.net_pay = "confirmed", 4000
                await db.commit()
            await prepare_payroll(f,c,1)
            r = await disburse(c, aid, rid=1)
            assert r.status_code == 400 and r.json()["detail"] == "垫款单剩余金额不足"
            async with f() as db:
                (await db.get(PayrollRecord, 1)).net_pay = 3000
                await db.commit()
            await prepare_payroll(f,c,1)
            invalid = await c.post("/api/v1/payroll/batch-disburse",headers=auth(3),json={"record_ids":[1,2,2,3],"funding_source":"cash_advance","cash_advance_id":aid})
            assert invalid.status_code==400
            body = {"record_ids": [1], "funding_source": "cash_advance", "cash_advance_id": aid}
            r = await c.post("/api/v1/payroll/batch-disburse", headers=auth(3), json=body)
            assert r.status_code == 200 and r.json()["count"] == 1 and r.json()["total_net"] == 3000
            assert (await usage(c, aid))["payroll_usage"]["payroll_used_amount"] == 10000
            retry = await c.post("/api/v1/payroll/batch-disburse", headers=auth(3), json=body)
            assert retry.status_code == 409
            assert (await usage(c, aid))["advance"]["outstanding_amount"] == 10000
            assert await balances(c) == {1: 10000, 3: 20000}
            await historical_payroll(f,c,1)
            assert (await usage(c, aid))["payroll_usage"]["payroll_available_amount"] == 3000
    asyncio.run(run())


@pytest.mark.parametrize("fail", [False, True])
def test_batch_aggregate_budget_and_atomic_rollback(tmp_path, monkeypatch, fail):
    async def run():
        async with environment(tmp_path, monkeypatch) as (f, c):
            aid = await approved(c, amount=10000 if fail else 7500)
            async with f() as db:
                r = await db.get(PayrollRecord, 1)
                r.status, r.net_pay = "confirmed", 1000
                await db.commit()
            await prepare_payroll(f,c,1)
            before = await finance_snapshot(f)
            if fail:
                original = service.record_history
                calls = 0
                async def broken(db, **kwargs):
                    nonlocal calls
                    await original(db, **kwargs)
                    if kwargs["module"] == "cash_advances" and kwargs["operation_type"] == "payroll_use":
                        calls += 1
                        if calls == 2: raise HTTPException(500, "模拟第二笔成本失败")
                monkeypatch.setattr(service, "record_history", broken)
            r = await c.post("/api/v1/payroll/batch-disburse", headers=auth(3), json={
                "record_ids": [1, 2], "funding_source": "cash_advance", "cash_advance_id": aid,
            })
            assert r.status_code == (500 if fail else 400), r.text
            assert await finance_snapshot(f) == before
            assert (await usage(c, aid))["payroll_usage"]["payroll_used_amount"] == 0
            assert await balances(c) == {1: 10000, 3: 20000}
    asyncio.run(run())


def test_failed_revoke_restores_cost_usage_and_loan_link(tmp_path, monkeypatch):
    async def run():
        async with environment(tmp_path, monkeypatch) as (f, c):
            aid = await approved(c, amount=10000)
            assert (await disburse(c, aid)).status_code == 200
            before = await finance_snapshot(f)
            async def broken(db, **kwargs):
                await db.flush()
                raise HTTPException(500, "模拟撤销日志失败")
            monkeypatch.setattr(payroll_api, "record_history", broken)
            r = await c.post("/api/v1/payroll/2/revoke-disbursement", headers=auth(1))
            assert r.status_code == 400 and "撤销功能已停用" in r.text and await finance_snapshot(f) == before
            assert (await usage(c, aid))["payroll_usage"]["payroll_used_amount"] == 7000
    asyncio.run(run())


def test_supervisor_with_only_payroll_grant_and_cross_warehouse_rejected(tmp_path, monkeypatch):
    async def run():
        async with environment(tmp_path, monkeypatch) as (f, c):
            aid = await approved(c, amount=10000)
            await set_perms(f, 3, ["工资"])
            sources = await c.get("/api/v1/payroll/cash-advance-sources", headers=auth(3))
            assert sources.status_code == 200 and [x["id"] for x in sources.json()["data"]] == [aid]
            foreign = await disburse(c, aid, rid=10, uid=3)
            assert foreign.status_code == 404
            mixed = await c.post("/api/v1/payroll/batch-disburse", headers=auth(3), json={
                "record_ids": [2, 10], "funding_source": "cash_advance", "cash_advance_id": aid,
            })
            assert mixed.status_code == 403
            assert (await disburse(c, aid, uid=3)).status_code == 200
    asyncio.run(run())


@pytest.mark.parametrize("uid", [2, 4, 5])
def test_old_disbursement_role_restrictions_preserved(tmp_path, monkeypatch, uid):
    async def run():
        async with environment(tmp_path, monkeypatch) as (f, c):
            aid = await approved(c, amount=10000)
            await set_perms(f, uid, ["工资"])
            assert (await disburse(c, aid, uid=uid)).status_code == 403
            assert (await c.get("/api/v1/payroll/cash-advance-sources", headers=auth(uid))).status_code == 403
            assert await balances(c) == {1: 10000, 3: 20000}
    asyncio.run(run())


def test_repay_after_salary_changes_debt_and_funds_but_never_salary_cost(tmp_path, monkeypatch):
    async def run():
        async with environment(tmp_path, monkeypatch) as (f, c):
            aid = await approved(c, amount=10000)
            assert (await disburse(c, aid)).status_code == 200
            path = await voucher(c)
            paid = await repay(c, aid, path, amount="7000")
            assert paid.status_code == 200, paid.text
            assert paid.json()["advance"]["outstanding_amount"] == 3000
            assert (await costs(c))["amount"] == 7750
            assert await balances(c) == {1: 3000, 3: 20000}
            assert (await ledger(c))["total_expense"] == 7750  # 750原成本资金＋7000实际归还
            assert (await usage(c, aid))["payroll_usage"]["payroll_used_amount"] == 7000
            assert (await usage(c, aid))["payroll_usage"]["payroll_available_amount"] == 3000
    asyncio.run(run())


def test_no_payroll_calculation_or_other_financial_module_changes():
    root=Path(__file__).resolve().parents[2]
    old=subprocess.check_output(['git','show','e6cc888:backend/app/api/v1/payroll.py'],cwd=root,text=True)
    new=(root/'backend/app/api/v1/payroll.py').read_text()
    def core(source):
        return {n.name:ast.dump(n,include_attributes=False) for n in ast.parse(source).body
                if isinstance(n,ast.AsyncFunctionDef) and n.name in ('_compute_employee_records','_rollback_advance_deductions')}
    assert core(old)==core(new)

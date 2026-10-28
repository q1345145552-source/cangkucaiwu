from tests.round3_flow_support import DeferredChecks
"""归还只改变账户资金和债务，不增加运营成本；使用独立数据库真实请求。"""
import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime, date
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import select, event
from app.models import CashAdvance, CashAdvanceRepayment, PaymentAccount, User, UserWarehouse
from app.models.income_expense import ExpenseRecord
from app.models.data_change_history import DataChangeHistory
import app.api.v1.cash_advance as api
import app.services.image_utils as images
from tests.test_round2_permissions import auth, set_perms, png
from tests.test_round3_permissions import hr_environment, snapshot
from tests.test_cash_advances import finance_snapshot, URL
from tests.permission_round6.legal_cash_fixture import create
from tests.round3_flow_support import grants, verify_approve_cash, historical_cash


@asynccontextmanager
async def environment(tmp_path, monkeypatch):
    original_save = images.save_image
    async with hr_environment(tmp_path, monkeypatch) as (engine, factory, c):
        monkeypatch.setattr(images, "save_image", original_save)
        monkeypatch.setattr(api, "UPLOAD_DIR", str(tmp_path / "uploads"))
        @event.listens_for(engine.sync_engine, "connect")
        def functions(conn, _): conn.create_function("to_char", 2, lambda value, fmt: str(value)[:7] if value else None)
        await engine.dispose()
        async with factory() as db:
            account = await db.get(PaymentAccount, 1)
            account.opening_balance, account.account_name, account.account_type = 10750, "测试现金", "cash"
            account.status, account.currency = "active", "THB"
            for amount in (500, 250):
                db.add(ExpenseRecord(warehouse_id=1, category_id=1, account_id=1, amount=amount, currency="THB", expense_date=datetime(2026, 10, 18), remark="原有运营支出"))
            await db.commit()
        await grants(factory)
        await set_perms(factory,4,["垫款单"])
        c.synthetic_factory=factory
        yield engine, factory, c


async def approved(c, **fields):
    r = await create(c, 4, payer_id=4, **fields); assert r.status_code == 200, r.text
    aid = r.json()["id"]
    assert r.json()["status"] == "pending" and r.json()["reviewed_by_id"] is None
    confirmed=await verify_approve_cash(c.synthetic_factory,c,aid)
    assert confirmed.json()["status"]=="confirmed" and confirmed.json()["reviewed_by_id"]==1
    return aid


async def voucher(c):
    r = await c.post(URL + "/repayment-voucher", headers=auth(1), files={"file": ("还款.png", png(), "image/png")})
    assert r.status_code == 200, r.text
    return r.json()["path"]


async def repay(c, aid, path, **fields):
    return await c.post(f"{URL}/{aid}/repayments", headers=auth(3), json={
        "repayment_date": "2026-10-18", "amount": "3000.00", "account_id": 1,
        "payment_method": "cash", "voucher_path": path, **fields,
    })


async def cost_totals(c):
    result = {}
    for path in ("/income-expense/expense?category_group=operating", "/income-expense/monthly-summary?start_date=2026-10-01&end_date=2026-10-31&category_group=operating", "/reports/income-expense?start_date=2026-10-01&end_date=2026-10-31"):
        r = await c.get("/api/v1" + path, headers=auth(1)); assert r.status_code == 200, r.text
        result[path] = r.json()
    return result


async def balance(c):
    r = await c.get("/api/v1/accounts", headers=auth(1)); assert r.status_code == 200
    return next(x for x in r.json()["data"] if x["id"] == 1)


async def ledger(c):
    r = await c.get("/api/v1/income-expense/ledger?source=cash_advance_repayment", headers=auth(1))
    assert r.status_code == 200, r.text
    return r.json()


def test_full_repayment_money_ledger_and_costs_exactly_unchanged(tmp_path, monkeypatch):
    async def run():
        deferred=DeferredChecks()
        async with environment(tmp_path, monkeypatch) as (_, f, c):
            aid = await approved(c); path = await voucher(c)
            before = await finance_snapshot(f); costs = await cost_totals(c); old_balance = await balance(c)
            r = await repay(c, aid, path, request_key="full-repayment-1"); assert r.status_code == 200, r.text
            data = r.json()
            assert data["repayment"]["amount"] == 3000 and data["repayment"]["account_id"] == 1 and data["repayment"]["status"] == "active"
            assert data["advance"]["status"] == "repaid" and data["advance"]["repaid_amount"] == 3000 and data["advance"]["outstanding_amount"] == 0
            assert data["account"]["current_balance"] == 7000
            after = await balance(c)
            assert old_balance["current_balance"] == 10000 and after["current_balance"] == 7000
            assert after["opening_balance"] == old_balance["opening_balance"] == 10750
            flows = await ledger(c)
            assert flows["total"] == 1 and flows["total_expense"] == 3000 and len(flows["data"]) == 1
            with deferred.check('test_full_repayment_money_ledger_and_costs_exactly_unchanged:100'):
                assert flows["data"][0]["amount"] == 3000 and flows["data"][0]["is_non_cost_flow"] is True
            assert flows["data"][0]["remark"] == f"归还垫款 #{aid}" and flows["data"][0]["account_name"] == "测试现金"
            same_day = await c.get("/api/v1/income-expense/ledger?source=cash_advance_repayment&start_date=2026-10-18&end_date=2026-10-18", headers=auth(1))
            assert same_day.status_code == 200 and same_day.json()["total"] == 1 and same_day.json()["total_expense"] == 3000
            with deferred.check('test_full_repayment_money_ledger_and_costs_exactly_unchanged:104'):
                assert await cost_totals(c) == costs and await finance_snapshot(f) == before
            assert (await c.get(URL + "/summary", headers=auth(1))).json()["total_outstanding"] == 0
            assert (await c.get(URL + "/summary", headers=auth(1))).json()["payer_count"] == 0
            # Same request key is a retry, not a second payment or a second deduction.
            retry = await repay(c, aid, path, request_key="full-repayment-1")
            assert retry.status_code == 200 and retry.json()["repayment"]["id"] == data["repayment"]["id"]
            assert (await ledger(c))["total"] == 1
            paid = await repay(c, aid, path)
            assert paid.status_code == 400 and paid.json()["detail"] == "该垫款单已还清"
            async with f() as db:
                logs = (await db.execute(select(DataChangeHistory).where(DataChangeHistory.operation_type == "repay"))).scalars().all()
                assert len(logs) == 1 and logs[0].after_data["repayment"]["amount"] == 3000 and logs[0].operator_id == 3
            report_expense = costs["/reports/income-expense?start_date=2026-10-01&end_date=2026-10-31"]["total_expense_by_currency"]
            with deferred.check('test_full_repayment_money_ledger_and_costs_exactly_unchanged:117'):
                assert report_expense == {"THB": 750}
            counts = costs["/income-expense/expense?category_group=operating"]
            with deferred.check('test_full_repayment_money_ledger_and_costs_exactly_unchanged:119'):
                assert counts["total"] == 2 and sum(x["amount"] for x in counts["data"]) == 750
            print("REPAYMENT_FULL", json.dumps({"response": data, "balance_before": old_balance["current_balance"], "balance_after": after["current_balance"], "ledger": flows, "cost_before": {"count": 2, "amount": 750}, "cost_after": (await cost_totals(c))["/income-expense/expense?category_group=operating"], "report_expense_before": report_expense, "report_expense_after": (await cost_totals(c))["/reports/income-expense?start_date=2026-10-01&end_date=2026-10-31"]["total_expense_by_currency"], "reports_unchanged": await cost_totals(c)==costs}, ensure_ascii=False))
        deferred.finish()
    asyncio.run(run())


def test_partial_repayment_reversal_keeps_voided_flow_and_restores_balance(tmp_path, monkeypatch):
    async def run():
        async with environment(tmp_path, monkeypatch) as (_, f, c):
            aid = await approved(c); path = await voucher(c); costs = await cost_totals(c); original = await finance_snapshot(f)
            r = await repay(c, aid, path, amount="1000", request_key="partial-payment"); assert r.status_code == 200, r.text
            part = r.json(); rid = part["repayment"]["id"]
            assert part["advance"]["status"] == "confirmed" and part["advance"]["status_label"] == "部分归还" and part["advance"]["outstanding_amount"] == 2000
            assert part["account"]["current_balance"] == 9000
            assert (await ledger(c))["total_expense"] == 1000
            filtered = await c.get(URL + "?status=partially_repaid", headers=auth(1)); assert filtered.json()["total"] == 1
            assert (await c.get(URL + "/summary", headers=auth(1))).json()["total_outstanding"] == 2000
            revoked = await historical_cash(f,c,rid)
            assert revoked["advance"]["status"] == "confirmed" and revoked["advance"]["status_label"] == "已确认"
            assert revoked["advance"]["repaid_amount"] == 0 and revoked["advance"]["outstanding_amount"] == 3000
            assert revoked["account"]["current_balance"] == 10000
            assert revoked["repayment"]["status"] == "revoked" and revoked["repayment"]["revoked_by_id"] == 1 and revoked["repayment"]["revoked_at"]
            flows = await ledger(c)
            assert flows["total"] == 1 and flows["total_expense"] == 0 and flows["card_expense"] == 0
            assert flows["data"][0]["status_label"] == "已冲销" and "账户选错" in flows["data"][0]["remark"]
            assert await cost_totals(c) == costs and await finance_snapshot(f) == original
            history = (await c.get(f"{URL}/{aid}/repayments", headers=auth(1))).json()
            assert history["total"] == 1 and history["active_count"] == 0 and history["data"][0]["status"] == "revoked"
            duplicate = await c.post(f"{URL}/repayments/{rid}/revoke", headers=auth(1), json={"reason": "再撤"})
            assert duplicate.status_code == 400 and "撤销功能已停用" in duplicate.json()["detail"]
            retry = await repay(c, aid, path, amount="1000", request_key="partial-payment")
            assert retry.status_code == 400 and "已撤销" in retry.json()["detail"]
            assert (await balance(c))["current_balance"] == 10000
            print("REPAYMENT_REVOKE", json.dumps({"partial": part, "revoked": revoked, "ledger": flows, "cost_before": 750, "cost_after": 750}, ensure_ascii=False))
    asyncio.run(run())


@pytest.mark.parametrize("uid", [2, 3, 4, 5])
def test_admin_only_repayment_upload_accounts_and_revoke(tmp_path, monkeypatch, uid):
    async def run():
        async with environment(tmp_path, monkeypatch) as (_, f, c):
            await set_perms(f, uid, ["垫款单"])
            aid = await approved(c); path = await voucher(c)
            made = (await repay(c, aid, path, amount="1000")).json(); rid = made["repayment"]["id"]
            for method, endpoint, kwargs in [
                ("POST", f"/{aid}/repayments", {"json": {"amount": 1000, "account_id": 1, "payment_method": "cash", "voucher_path": path}}),
                ("POST", f"/repayments/{rid}/revoke", {"json": {"reason": "不能撤"}}),
                ("GET", "/repayment-accounts", {}),
                ("POST", "/repayment-voucher", {"files": {"file": ("test.png", png(), "image/png")}}),
            ]:
                r = await c.request(method, URL + endpoint, headers=auth(uid), **kwargs)
                expected = 400 if "/revoke" in endpoint and uid in (3,4) else 200 if uid==3 else 403
                assert r.status_code == expected, r.text
                if expected==400: assert "撤销功能已停用" in r.text
                if expected==403:
                    message="超级管理员请使用各仓库管理员账号操作" if uid==2 else "无权访问" if uid==5 else "该动作超出当前角色职责上限"
                    assert r.json()=={"detail":message}
            listing = await c.get(f"{URL}/{aid}/repayments", headers=auth(uid))
            assert listing.status_code == (200 if uid == 3 else 403)
            assert (await balance(c))["current_balance"] == (8000 if uid==3 else 9000)
    asyncio.run(run())


@pytest.mark.parametrize("fields,message", [({"amount": "3500"}, "不能超过剩余未还"), ({"account_id": None}, "请选择归还账户"), ({"voucher_path": None}, "请上传归还凭证照片"), ({"voucher_path": " "}, "请上传归还凭证照片"), ({"voucher_path": "uploads/2/2026-10-18/cash-advances/a.png"}, "凭证照片不属于当前仓库的垫款单"), ({"voucher_path": "uploads/1/2026-10-18/cash-advances/missing.png"}, "归还凭证照片不存在，请重新上传")])
def test_repayment_validation_no_partial_financial_writes(tmp_path, monkeypatch, fields, message):
    async def run():
        async with environment(tmp_path, monkeypatch) as (_, f, c):
            aid = await approved(c); path = await voucher(c)
            before = await finance_snapshot(f)
            r = await repay(c, aid, path, **fields)
            assert r.status_code == 400 and r.json()["detail"] == message, r.text
            assert (await ledger(c))["total"] == 0 and (await balance(c))["current_balance"] == 10000
            assert await finance_snapshot(f) == before
    asyncio.run(run())


def test_pending_rejected_inactive_cross_warehouse_and_currency_are_blocked(tmp_path, monkeypatch):
    async def run():
        async with environment(tmp_path, monkeypatch) as (_, f, c):
            path = await voucher(c)
            await set_perms(f, 4, ["垫款单"])
            pending = (await create(c, 4)).json()["id"]
            r = await repay(c, pending, path); assert r.status_code == 409 and "缺少有效核验或管理员批准" in r.json()["detail"]
            await c.post(f"{URL}/{pending}/reject", headers=auth(1), json={"reject_reason": "未确认"})
            assert (await repay(c, pending, path)).status_code == 409
            aid = await approved(c)
            assert (await repay(c, aid, path, account_id=2)).status_code == 400
            async with f() as db:
                account = await db.get(PaymentAccount, 1); account.status = "inactive"; await db.commit()
            r = await repay(c, aid, path); assert r.status_code == 400 and r.json()["detail"] == "归还账户已停用"
            async with f() as db:
                account = await db.get(PaymentAccount, 1); account.status = "active"; account.currency = "CNY"
                db.add(User(id=7, username="other-boss", display_name="外仓老板", role="warehouse_admin", warehouse_id=2, password_hash="unused")); db.add(UserWarehouse(user_id=7, warehouse_id=2)); await db.commit()
            r = await repay(c, aid, path); assert r.status_code == 400 and "币种必须与垫款单一致" in r.json()["detail"]
            r = await c.post(f"{URL}/{aid}/repayments", headers=auth(7), json={"amount": 1000, "account_id": 2, "payment_method": "cash", "voucher_path": path})
            assert r.status_code == 404
            assert (await c.get(f"{URL}/{aid}/repayments", headers=auth(7))).status_code == 404
            assert (await c.get(URL + "/repayment-accounts", headers=auth(7))).json()["data"][0]["id"] == 2
    asyncio.run(run())


def test_full_reversal_inactive_account_and_multiple_payments(tmp_path, monkeypatch):
    async def run():
        async with environment(tmp_path, monkeypatch) as (_, f, c):
            aid = await approved(c); path = await voucher(c)
            a = (await repay(c, aid, path, amount="1000")).json()
            b = (await repay(c, aid, path, amount="2000")).json()
            assert b["advance"]["status"] == "repaid" and b["account"]["current_balance"] == 7000
            async with f() as db:
                account = await db.get(PaymentAccount, 1); account.status = "inactive"; await db.commit()
            for row, remaining, expected in [(a, 1000, 8000), (b, 3000, 10000)]:
                r = await historical_cash(f,c,row["repayment"]["id"],"退回原账户：合成历史")
                assert r["advance"]["status"] == "confirmed" and r["advance"]["outstanding_amount"] == remaining and r["account"]["current_balance"] == expected
            assert (await ledger(c))["total_expense"] == 0
    asyncio.run(run())


def test_history_failure_rolls_back_repayment_and_revoke(tmp_path, monkeypatch):
    async def run():
        async with environment(tmp_path, monkeypatch) as (_, f, c):
            aid = await approved(c); path = await voucher(c)
            row = (await repay(c, aid, path, amount="1000")).json()
            before = await finance_snapshot(f)
            async def fail(db, **kwargs): raise HTTPException(500, "模拟日志失败")
            monkeypatch.setattr(api, "record_history", fail)
            assert (await repay(c, aid, path, amount="500")).status_code == 500
            assert (await c.post(f'{URL}/repayments/{row["repayment"]["id"]}/revoke', headers=auth(1), json={"reason": "回滚"})).status_code == 400
            assert (await ledger(c))["total_expense"] == 1000 and (await balance(c))["current_balance"] == 9000
            assert (await c.get(URL + "/summary", headers=auth(1))).json()["total_outstanding"] == 2000
            assert await finance_snapshot(f) == before
    asyncio.run(run())


def test_repayment_never_recalculates_and_manual_payroll_amount_stays_same(tmp_path, monkeypatch):
    async def run():
        from tests.test_round18_advance_review import prepare_work, calculate, period_record
        import app.api.v1.payroll as payroll
        async with environment(tmp_path, monkeypatch) as (_, f, c):
            monkeypatch.setattr(payroll, "thai_today", lambda: date(2026, 10, 20))
            await prepare_work(f); await calculate(c)
            old = await period_record(f); assert old.net_pay == 800
            before = await snapshot(f)
            aid = await approved(c); path = await voucher(c)
            assert (await repay(c, aid, path)).status_code == 200
            assert await snapshot(f) == before
            r = await c.post(f"/api/v1/payroll/{old.id}/recalc", headers=auth(3), json={"mode": "recalc", "void_reason": "归还垫款隔离验证"})
            assert r.status_code == 200 and (await period_record(f)).net_pay == 800
            print("REPAYMENT_PAYROLL", {"before": 800, "after_manual_recalc": 800})
    asyncio.run(run())


def test_currency_is_explicit_account_must_match_and_summary_never_adds_currencies(tmp_path, monkeypatch):
    async def run():
        deferred=DeferredChecks()
        async with environment(tmp_path, monkeypatch) as (_, f, c):
            thb = await approved(c)
            cny = await approved(c, currency="CNY")
            async with f() as db:
                db.add(PaymentAccount(id=3, warehouse_id=1, account_name="人民币现金", account_type="cash", account_number="CNY-CASH", currency="CNY", status="active", opening_balance=20000))
                await db.commit()
            summary = (await c.get(URL + "/summary", headers=auth(1))).json()
            assert summary["payer_count"] == 1 and len(summary["data"]) == 1
            assert summary["total_outstanding"] is None and summary["data"][0]["outstanding_amount"] is None
            assert summary["totals_by_currency"] == [{"currency": "CNY", "amount": 3000}, {"currency": "THB", "amount": 3000}]
            path = await voucher(c); costs = await cost_totals(c)
            wrong = await repay(c, cny, path, account_id=1)
            assert wrong.status_code == 400 and "币种必须与垫款单一致" in wrong.json()["detail"]
            paid = await repay(c, cny, path, account_id=3, payment_method="transfer")
            assert paid.status_code == 200 and paid.json()["repayment"]["currency"] == "CNY" and paid.json()["repayment"]["payment_method"] == "transfer" and paid.json()["account"]["current_balance"] == 17000
            assert (await balance(c))["current_balance"] == 10000
            # An account with effective payments cannot be relabelled to another currency or deleted.
            edit = await c.put("/api/v1/accounts/3", headers=auth(1), json={"account_name": "人民币现金", "account_type": "cash", "account_number": "CNY-CASH", "opening_balance": 20000, "currency": "THB"})
            assert edit.status_code == 400 and "不能修改币种" in edit.json()["detail"]
            delete = await c.delete("/api/v1/accounts/3", headers=auth(1))
            assert delete.status_code == 400 and "不能删除" in delete.json()["detail"]
            summary = (await c.get(URL + "/summary", headers=auth(1))).json()
            assert summary["totals_by_currency"] == [{"currency": "THB", "amount": 3000}]
            with deferred.check('test_currency_is_explicit_account_must_match_and_summary_never_adds_currencies:294'):
                assert await cost_totals(c) == costs
            print("REPAYMENT_CURRENCY", {"CNY_before": 20000, "CNY_after": 17000, "THB_unchanged": 10000, "remaining_THB": 3000})
        deferred.finish()
    asyncio.run(run())


@pytest.mark.parametrize("amount", [0, -1, "NaN", "Infinity", "1.001"])
def test_invalid_money_does_not_change_balance_or_create_flows(tmp_path, monkeypatch, amount):
    async def run():
        async with environment(tmp_path, monkeypatch) as (_, _, c):
            aid = await approved(c); path = await voucher(c)
            assert (await repay(c, aid, path, amount=amount)).status_code == 422
            assert (await ledger(c))["total"] == 0 and (await balance(c))["current_balance"] == 10000
    asyncio.run(run())

"""报销成本、公司资金、凭证、垫款和撤销的真实 HTTP/数据库验收。"""
import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models import PaymentAccount, CashAdvance, ExpenseFund, ExpenseFundItem
from app.models.reimbursement import Reimbursement, ReimbursementItem
from app.models.reimbursement_payment import ReimbursementPayment
from app.models.income_expense import ExpenseRecord
from app.models.payroll import PayrollRecord
from app.models.data_change_history import DataChangeHistory
from app.services import reimbursement_payment as service
from tests.test_round2_permissions import auth, set_perms, png
from tests.test_cash_advance_repayments import environment as prior_environment, approved as loan, voucher as loan_voucher, repay
from tests.test_cash_advances import finance_snapshot

BASE = "/api/v1/reimbursement"


@asynccontextmanager
async def environment(tmp_path, monkeypatch):
    async with prior_environment(tmp_path, monkeypatch) as (engine, f, c):
        monkeypatch.setattr(service, "UPLOAD_DIR", str(tmp_path / "uploads"))
        async with engine.begin() as conn:
            await service.backfill_reimbursement_categories(conn)
        await set_perms(f, 4, ["报销管理"])
        async with f() as db:
            db.add(PaymentAccount(id=3, warehouse_id=1, account_name="测试银行", account_type="bank", account_number="bank", opening_balance=20000, currency="THB", status="active"))
            db.add(PaymentAccount(id=4, warehouse_id=1, account_name="人民币账户", account_type="cash", account_number="cny", opening_balance=30000, currency="CNY", status="active"))
            db.add(ExpenseFund(id=1, warehouse_id=1, employee_id=4, receive_date=datetime(2026, 10, 18), amount=5000,
                purpose="原有测试备用金", remaining_balance=5000, currency="THB", status="active"))
            await db.commit()
        yield engine, f, c


async def approved(c, *, amount=2000, currency="THB", fund=False):
    r = await c.post(BASE, headers=auth(4), json={"submit_date": "2026-10-18", "currency": currency,
        "is_fund_linked": "1" if fund else "0", "items": [{"category": "交通费", "amount": amount, "description": "付款验收"}]})
    assert r.status_code == 200, r.text
    rid = r.json()["id"]
    detail = (await c.get(f"{BASE}/{rid}", headers=auth(1))).json()
    r = await c.post(f"{BASE}/{rid}/review", headers=auth(1), json={"items": [{"item_id": i["id"], "status": "approved"} for i in detail["items"]]})
    assert r.status_code == 200 and r.json()["approved_amount"] == amount, r.text
    return rid


async def upload(c, rid, uid=1):
    r = await c.post(BASE + "/payment-voucher", headers=auth(uid), data={"reimbursement_id": rid}, files={"file": ("付款凭证.png", png(), "image/png")})
    assert r.status_code == 200, r.text
    return r.json()["path"]


async def pay(c, rid, path, *, uid=1, **fields):
    return await c.post(f"{BASE}/{rid}/pay", headers=auth(uid), json={"funding_source": "company_account",
        "payment_account_id": 1, "payment_method": "cash", "payment_voucher_path": path, **fields})


async def balances(c):
    r = await c.get("/api/v1/accounts", headers=auth(1))
    assert r.status_code == 200, r.text
    return {a["id"]: a["current_balance"] for a in r.json()["data"]}


async def costs(c):
    r = await c.get("/api/v1/income-expense/expense?category_group=operating", headers=auth(1))
    assert r.status_code == 200, r.text
    data = r.json()
    return {"count": data["total"], "amount": sum(x["amount"] for x in data["data"]), "data": data["data"]}


async def ledger(c):
    r = await c.get("/api/v1/income-expense/ledger", headers=auth(1))
    assert r.status_code == 200, r.text
    return r.json()


async def snapshot(f):
    data = await finance_snapshot(f)
    async with f() as db:
        for model in (ReimbursementPayment, CashAdvance):
            data[model.__tablename__] = [tuple(r) for r in (await db.execute(select(model.__table__).order_by(model.id))).all()]
    return data


async def usage(c, aid):
    r = await c.get(f"/api/v1/cash-advances/{aid}/repayments", headers=auth(1))
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.usefixtures("retained_reversal_code")
def test_company_payment_2000_exactly_one_cost_and_one_flow_revoke_keeps_voided_flow(tmp_path, monkeypatch):
    async def run():
        async with environment(tmp_path, monkeypatch) as (_, f, c):
            rid = await approved(c)
            photo = await upload(c, rid)
            before, old_flows = await balances(c), await ledger(c)
            old_other = await snapshot(f)
            paid = await pay(c, rid, photo)
            assert paid.status_code == 200, paid.text
            data = paid.json()
            assert data["status"] == "paid" and data["account_balance"] == 8000
            assert data["payment"]["paid_by_id"] == 1 and data["payment"]["payment_voucher_path"] == photo
            expense_id = data["expense_record_id"]
            cost = await costs(c)
            assert (cost["count"], cost["amount"]) == (3, 2750)
            expense = next(x for x in cost["data"] if x["id"] == expense_id)
            assert expense["category_name"] == "报销" and expense["amount"] == 2000 and expense["reimbursement_id"] == rid
            assert await balances(c) == {**before, 1: 8000}
            flows = await ledger(c)
            assert flows["total"] == old_flows["total"] + 1 and flows["total_expense"] == old_flows["total_expense"] + 2000
            linked = [x for x in flows["data"] if x["source"] == "reimbursement"]
            assert len(linked) == 1 and linked[0]["remark"] == f"报销付款 #{rid}" and linked[0]["amount"] == 2000
            duplicate = await pay(c, rid, photo)
            assert duplicate.status_code == 400 and (await costs(c))["count"] == 3 and (await balances(c))[1] == 8000
            assert (await c.post(f"{BASE}/{rid}/submit", headers=auth(1))).status_code == 400
            assert (await c.delete(f"/api/v1/income-expense/expense/{expense_id}", headers=auth(1))).status_code == 400
            report = await c.get("/api/v1/reports/income-expense?start_date=2026-10-01&end_date=2026-10-31", headers=auth(1))
            assert report.status_code == 200 and report.json()["total_expense_by_currency"] == {"THB": 2750}
            detail = (await c.get(f"{BASE}/{rid}", headers=auth(1))).json()
            assert detail["expense_record_id"] == expense_id and detail["paid_by_id"] == 1 and detail["payment_account_id"] == 1
            revoked = await c.post(f"{BASE}/{rid}/revoke-payment", headers=auth(1), json={"reason": "付款账户选错"})
            assert revoked.status_code == 200, revoked.text
            assert revoked.json()["status"] == "approved" and revoked.json()["expense_record_id"] is None and revoked.json()["account_balance"] == 10000
            assert (await costs(c))["amount"] == 750 and await balances(c) == before
            canceled = await ledger(c)
            assert canceled["total"] == old_flows["total"] + 1 and canceled["total_expense"] == old_flows["total_expense"]
            row = next(x for x in canceled["data"] if x["source"] == "reimbursement")
            assert row["status_label"] == "已冲销" and "付款账户选错" in row["remark"]
            hist = (await c.get(f"{BASE}/{rid}/payments", headers=auth(1))).json()
            assert hist["total"] == 1 and hist["data"][0]["status"] == "revoked" and hist["data"][0]["revoked_by_id"] == 1
            assert (await c.post(f"{BASE}/{rid}/revoke-payment", headers=auth(1), json={"reason": "重复"})).status_code == 400
            after_other = await snapshot(f)
            for name in ("payroll_records", "employee_advances", "expense_funds", "expense_fund_items", "payable_bills"):
                assert after_other[name] == old_other[name], name
            print("REIMB_COMPANY", json.dumps({"response": data, "cost_before": 750, "cost_after": cost["amount"],
                "balances_before": before, "balances_after": {**before, 1: 8000}, "flows_before": old_flows["total"],
                "flows_after": flows["total"], "revoke": revoked.json(), "cost_after_revoke": 750,
                "flows_expense_after_revoke": canceled["total_expense"]}, ensure_ascii=False))
    asyncio.run(run())


@pytest.mark.usefixtures("retained_reversal_code")
def test_cash_advance_cost_only_usage_revoke_and_repay_do_not_duplicate_cost(tmp_path, monkeypatch):
    async def run():
        async with environment(tmp_path, monkeypatch) as (_, f, c):
            aid = await loan(c, amount=10000)
            rid = await approved(c)
            path = await upload(c, rid)
            before, flows_before = await balances(c), await ledger(c)
            paid = await pay(c, rid, path, funding_source="cash_advance", payment_account_id=None, cash_advance_id=aid)
            assert paid.status_code == 200, paid.text
            data = paid.json()
            assert data["cash_advance_id"] == aid and data["payment"]["payment_account_id"] is None
            assert (await costs(c))["amount"] == 2750 and (await costs(c))["count"] == 3
            assert await balances(c) == before and await ledger(c) == flows_before
            used = await usage(c, aid)
            assert used["advance"]["outstanding_amount"] == 10000
            assert used["reimbursement_usage"]["reimbursement_used_amount"] == 2000
            assert used["payroll_usage"]["available_amount"] == 8000
            assert used["reimbursement_usage"]["data"][0]["reimbursement_id"] == rid
            # 工资与报销合用同一额度；工资写路径/金额算法仍沿用原接口。
            async with f() as db:
                (await db.get(PayrollRecord, 2)).net_pay = 9000
                await db.commit()
            rejected = await c.post("/api/v1/payroll/2/disburse", headers=auth(1), json={"funding_source": "cash_advance", "cash_advance_id": aid})
            assert rejected.status_code == 400 and rejected.json()["detail"] == "垫款单剩余金额不足"
            revoked = await c.post(f"{BASE}/{rid}/revoke-payment", headers=auth(1), json={"reason": "改为公司账户付款"})
            assert revoked.status_code == 200 and revoked.json()["cash_advance_id"] is None
            assert (await costs(c))["amount"] == 750 and await balances(c) == before and await ledger(c) == flows_before
            assert (await usage(c, aid))["reimbursement_usage"]["data"] == []
            again = await pay(c, rid, path, funding_source="cash_advance", payment_account_id=None, cash_advance_id=aid)
            assert again.status_code == 200 and (await costs(c))["amount"] == 2750
            payment_photo = await loan_voucher(c)
            returned = await repay(c, aid, payment_photo, amount="2000")
            assert returned.status_code == 200 and (await costs(c))["amount"] == 2750
            assert (await balances(c))[1] == 8000
            print("REIMB_ADVANCE", json.dumps({"response": data, "cost_before": 750, "cost_after": 2750,
                "balances_before": before, "balances_after": before, "flows_before": flows_before["total"],
                "flows_after": flows_before["total"], "usage": used["reimbursement_usage"],
                "revoke": revoked.json(), "cost_after_revoke": 750}, ensure_ascii=False))
    asyncio.run(run())


@pytest.mark.usefixtures("retained_reversal_code")
def test_fund_path_does_not_deduct_twice_and_revoke_repay_refund_once(tmp_path, monkeypatch):
    async def run():
        async with environment(tmp_path, monkeypatch) as (_, f, c):
            rid = await approved(c, fund=True)
            before_cost, before_balance, before_flow = await costs(c), await balances(c), await ledger(c)
            async with f() as db: assert (await db.get(ExpenseFund, 1)).remaining_balance == 3000
            r = await c.post(f"{BASE}/{rid}/pay", headers=auth(1), json={"funding_source": "expense_fund"})
            assert r.status_code == 200, r.text
            assert r.json()["expense_record_id"] is None and r.json()["payment"]["funding_source"] == "expense_fund"
            assert await costs(c) == before_cost and await balances(c) == before_balance and await ledger(c) == before_flow
            async with f() as db: assert (await db.get(ExpenseFund, 1)).remaining_balance == 3000
            revoked = await c.post(f"{BASE}/{rid}/revoke-payment", headers=auth(1), json={"reason": "撤销备用金付款"})
            assert revoked.status_code == 200, revoked.text
            async with f() as db:
                assert (await db.get(ExpenseFund, 1)).remaining_balance == 5000
                assert (await db.get(Reimbursement, rid)).fund_item_id is None
                assert not (await db.execute(select(ExpenseFundItem))).scalars().all()
            retry = await c.post(f"{BASE}/{rid}/pay", headers=auth(1), json={"funding_source": "expense_fund"})
            assert retry.status_code == 200, retry.text
            async with f() as db:
                assert (await db.get(ExpenseFund, 1)).remaining_balance == 3000
                assert len((await db.execute(select(ExpenseFundItem))).scalars().all()) == 1
            assert await costs(c) == before_cost and await balances(c) == before_balance
            assert (await c.post(f"{BASE}/{rid}/pay", headers=auth(1), json={"funding_source": "expense_fund"})).status_code == 400
            async with f() as db: assert (await db.get(ExpenseFund, 1)).remaining_balance == 3000
            print("REIMB_FUND", {"before_pay": 3000, "after_pay": 3000, "after_revoke": 5000, "after_repay": 3000, "cost_unchanged": 750})
    asyncio.run(run())


@pytest.mark.parametrize("kind", ["no_voucher", "bad_voucher", "no_account", "foreign_account", "inactive_account", "currency", "no_advance", "small_advance", "foreign_advance", "advance_currency", "pending_advance", "mixed", "not_linked_fund"])
def test_validation_no_partial_money_changes(tmp_path, monkeypatch, kind):
    async def run():
        async with environment(tmp_path, monkeypatch) as (_, f, c):
            rid = await approved(c)
            path = await upload(c, rid)
            fields = {}
            if "advance" in kind or kind == "mixed":
                aid = await loan(c, amount=1000 if kind == "small_advance" else 10000, currency="CNY" if kind == "advance_currency" else "THB")
                fields.update(funding_source="cash_advance", cash_advance_id=aid, payment_account_id=None)
                async with f() as db:
                    if kind == "foreign_advance": (await db.get(CashAdvance, aid)).warehouse_id = 2
                    if kind == "pending_advance": (await db.get(CashAdvance, aid)).status = "pending"
                    await db.commit()
            if kind == "no_voucher": path = None
            if kind == "bad_voucher": path = "uploads/2/2026-10-18/reimbursement-payments/no.png"
            if kind == "no_account": fields["payment_account_id"] = None
            if kind == "foreign_account": fields["payment_account_id"] = 2
            if kind == "currency": fields["payment_account_id"] = 4
            if kind == "no_advance": fields["cash_advance_id"] = None
            if kind == "mixed": fields["payment_account_id"] = 1
            if kind == "not_linked_fund": fields.update(funding_source="expense_fund", payment_account_id=None)
            if kind == "inactive_account":
                async with f() as db:
                    (await db.get(PaymentAccount, 1)).status = "inactive"
                    await db.commit()
            before = await snapshot(f)
            r = await pay(c, rid, path, **fields)
            assert r.status_code == 400, r.text
            if kind == "no_voucher": assert r.json()["detail"] == "请上传付款凭证"
            if kind == "small_advance": assert r.json()["detail"] == "垫款单剩余金额不足"
            assert await snapshot(f) == before
    asyncio.run(run())


@pytest.mark.parametrize("source", ["company_account", "cash_advance", "expense_fund"])
@pytest.mark.usefixtures("retained_reversal_code")
def test_payment_and_revoke_failures_rollback_everything(tmp_path, monkeypatch, source):
    async def run():
        async with environment(tmp_path, monkeypatch) as (_, f, c):
            rid = await approved(c, fund=source == "expense_fund")
            path = await upload(c, rid)
            fields = {"funding_source": source}
            if source != "company_account": fields["payment_account_id"] = None
            if source == "cash_advance": fields["cash_advance_id"] = await loan(c, amount=10000)
            original = service.record_history
            async def broken(db, **kwargs):
                await original(db, **kwargs)
                await db.flush()
                if kwargs["module"] == "reimbursement": raise HTTPException(500, "模拟记账失败")
            before = await snapshot(f)
            monkeypatch.setattr(service, "record_history", broken)
            assert (await pay(c, rid, path, **fields)).status_code == 500
            assert await snapshot(f) == before
            monkeypatch.setattr(service, "record_history", original)
            assert (await pay(c, rid, path, **fields)).status_code == 200
            before = await snapshot(f)
            monkeypatch.setattr(service, "record_history", broken)
            r = await c.post(f"{BASE}/{rid}/revoke-payment", headers=auth(1), json={"reason": "回滚验收"})
            assert r.status_code == 500 and await snapshot(f) == before
    asyncio.run(run())


@pytest.mark.parametrize("uid", [3, 4, 5, 2])
@pytest.mark.usefixtures("retained_reversal_code")
def test_only_warehouse_admin_can_revoke(tmp_path, monkeypatch, uid):
    async def run():
        async with environment(tmp_path, monkeypatch) as (_, f, c):
            rid = await approved(c)
            path = await upload(c, rid)
            assert (await pay(c, rid, path)).status_code == 200
            await set_perms(f, uid, ["报销管理"])
            before = await snapshot(f)
            r = await c.post(f"{BASE}/{rid}/revoke-payment", headers=auth(uid), json={"reason": "越权"})
            assert r.status_code == 403 and await snapshot(f) == before
            if uid in (3, 4): assert r.json()["detail"] == "只有仓库管理员可以撤销报销付款"
    asyncio.run(run())


def test_cny_account_and_advance_are_independent_from_thb(tmp_path, monkeypatch):
    async def run():
        async with environment(tmp_path, monkeypatch) as (_, f, c):
            rid = await approved(c, currency="CNY")
            path = await upload(c, rid)
            sources = (await c.get(BASE + f"/payment-sources?reimbursement_id={rid}", headers=auth(1))).json()
            assert [a["id"] for a in sources["accounts"]] == [4]
            r = await pay(c, rid, path, payment_account_id=4)
            assert r.status_code == 200 and r.json()["account_balance"] == 28000
            assert (await balances(c))[1] == 10000
            rid2 = await approved(c, currency="CNY")
            aid = await loan(c, amount=10000, currency="CNY")
            photo = await upload(c, rid2)
            before = await balances(c)
            r = await pay(c, rid2, photo, funding_source="cash_advance", payment_account_id=None, cash_advance_id=aid)
            assert r.status_code == 200 and await balances(c) == before
            assert (await usage(c, aid))["reimbursement_usage"]["reimbursement_used_amount"] == 2000
    asyncio.run(run())


@pytest.mark.usefixtures("retained_reversal_code")
def test_fund_review_auto_payment_history_and_single_refund_after_reject_or_revoke(tmp_path, monkeypatch):
    async def run():
        async with environment(tmp_path, monkeypatch) as (_, f, c):
            async def make():
                r = await c.post(BASE, headers=auth(4), json={"submit_date": "2026-10-18", "currency": "THB", "is_fund_linked": "1", "items": [{"category": "交通费", "amount": 2000}]})
                assert r.status_code == 200, r.text
                detail = (await c.get(f"{BASE}/{r.json()['id']}", headers=auth(1))).json()
                return detail["id"], detail["fund_item_id"]
            async def remaining():
                async with f() as db: return (await db.get(ExpenseFund, 1)).remaining_balance
            async def review(item, action):
                return await c.post("/api/v1/expense-fund/review/batch", headers=auth(1), json={"item_ids": [item], "action": action, "remark": "备用金审核验收"})
            before_balances, before_costs = await balances(c), await costs(c)
            rid, item = await make()
            assert await remaining() == 3000
            r = await review(item, "approve")
            assert r.status_code == 200, r.text
            detail = (await c.get(f"{BASE}/{rid}", headers=auth(1))).json()
            assert detail["status"] == "paid" and detail["funding_source"] == "expense_fund"
            hist = (await c.get(f"{BASE}/{rid}/payments", headers=auth(1))).json()
            assert hist["total"] == 1 and hist["data"][0]["paid_by_id"] == 1
            assert await remaining() == 3000 and await costs(c) == before_costs and await balances(c) == before_balances
            assert (await review(item, "approve")).status_code == 200
            assert (await c.get(f"{BASE}/{rid}/payments", headers=auth(1))).json()["total"] == 1
            r = await review(item, "reject")
            assert r.status_code == 200, r.text
            assert await remaining() == 5000
            hist = (await c.get(f"{BASE}/{rid}/payments", headers=auth(1))).json()
            assert hist["data"][0]["status"] == "revoked"
            assert (await c.post(f"{BASE}/{rid}/revoke-payment", headers=auth(1), json={"reason": "防重复退款"})).status_code == 400
            assert await remaining() == 5000
            rid2, item2 = await make()
            assert (await review(item2, "approve")).status_code == 200
            r = await c.post(f"{BASE}/{rid2}/revoke-payment", headers=auth(1), json={"reason": "撤销备用金付款"})
            assert r.status_code == 200, r.text
            assert r.json()["status"] == "approved" and await remaining() == 5000
            assert (await review(item2, "reject")).status_code == 200
            assert await remaining() == 5000
            assert await costs(c) == before_costs and await balances(c) == before_balances
            print("REIMB_FUND_AUTO", {"after_create": 3000, "after_approve": 3000, "after_reject_or_revoke": 5000, "duplicate_refund": False})
    asyncio.run(run())


@pytest.mark.usefixtures("retained_reversal_code")
def test_legacy_paid_untouched_warehouse_scope_permissions_and_required_revoke_reason(tmp_path, monkeypatch):
    async def run():
        async with environment(tmp_path, monkeypatch) as (_, f, c):
            async with f() as db:
                db.add_all([Reimbursement(id=100, warehouse_id=1, employee_id=4, submit_date=datetime(2026, 10, 18), total_amount=1700,
                    currency="THB", status="paid", paid_at=datetime(2026, 10, 18)),
                    Reimbursement(id=101, warehouse_id=2, employee_id=4, submit_date=datetime(2026, 10, 18), total_amount=2000, currency="THB", status="approved")])
                await db.commit()
            before = await snapshot(f)
            hist = await c.get(BASE + "/100/payments", headers=auth(1))
            assert hist.status_code == 200 and hist.json()["is_legacy_payment"] and hist.json()["data"] == []
            revoke = await c.post(BASE + "/100/revoke-payment", headers=auth(1), json={"reason": "旧单不推断"})
            assert revoke.status_code == 400 and await snapshot(f) == before
            for method, route, kwargs in [
                ("get", BASE + "/101/payments", {}), ("get", BASE + "/payment-sources?reimbursement_id=101", {}),
                ("post", BASE + "/101/pay", {"json": {}}), ("post", BASE + "/101/revoke-payment", {"json": {"reason": "越仓"}}),
                ("post", BASE + "/payment-voucher", {"data": {"reimbursement_id": 101}, "files": {"file": ("x.png", png(), "image/png")}}),
            ]:
                response = await getattr(c, method)(route, headers=auth(1), **kwargs)
                assert response.status_code == 403, response.text
            rid = await approved(c)
            for uid in (3, 4):
                await set_perms(f, uid, [])
                assert (await c.get(BASE + f"/payment-sources?reimbursement_id={rid}", headers=auth(uid))).status_code == 403
                assert (await c.post(f"{BASE}/{rid}/pay", headers=auth(uid), json={})).json()["detail"].startswith("无此操作权限")
                await set_perms(f, uid, ["报销管理"])
            for uid in (2, 5):
                assert (await c.get(BASE + f"/payment-sources?reimbursement_id={rid}", headers=auth(uid))).status_code == 403
            photo = await upload(c, rid)
            assert (await pay(c, rid, photo, uid=3)).status_code == 200
            for body in ({}, {"reason": "   "}):
                resp = await c.post(f"{BASE}/{rid}/revoke-payment", headers=auth(1), json=body)
                assert resp.status_code == 400 and resp.json()["detail"] == "请填写撤销原因"
            assert (await c.post(f"{BASE}/{rid}/revoke-payment", headers=auth(1), json={"reason": "测试后恢复"})).status_code == 200
            assert (await pay(c, rid, photo, uid=4)).status_code == 200
    asyncio.run(run())


def test_loan_quota_already_used_by_payroll_blocks_reimbursement_and_category_backfill_idempotent(tmp_path, monkeypatch):
    async def run():
        async with environment(tmp_path, monkeypatch) as (engine, f, c):
            async with engine.begin() as conn:
                assert await service.backfill_reimbursement_categories(conn) == 0
            aid = await loan(c, amount=3000)
            r = await c.post("/api/v1/payroll/2/disburse", headers=auth(1), json={"funding_source": "cash_advance", "cash_advance_id": aid})
            assert r.status_code == 200, r.text
            rid = await approved(c)
            photo = await upload(c, rid)
            before = await snapshot(f)
            r = await pay(c, rid, photo, funding_source="cash_advance", payment_account_id=None, cash_advance_id=aid)
            assert r.status_code == 400 and r.json()["detail"] == "垫款单剩余金额不足"
            assert await snapshot(f) == before
    asyncio.run(run())


@pytest.mark.usefixtures("retained_reversal_code")
def test_decimal_item_sums_and_partially_approved_total_used_for_payment(tmp_path, monkeypatch):
    async def run():
        async with environment(tmp_path, monkeypatch) as (_, f, c):
            r = await c.post(BASE, headers=auth(4), json={"submit_date": "2026-10-18", "currency": "THB",
                "items": [{"category": "交通费", "amount": .1}, {"category": "餐费", "amount": .2}, {"category": "其他", "amount": 5}]})
            assert r.status_code == 200
            rid = r.json()["id"]
            detail = (await c.get(f"{BASE}/{rid}", headers=auth(1))).json()
            r = await c.post(f"{BASE}/{rid}/review", headers=auth(1), json={"items": [
                {"item_id": item["id"], "status": "approved" if i < 2 else "rejected"} for i, item in enumerate(detail["items"])]})
            assert r.status_code == 200 and r.json()["status"] == "partially_approved"
            photo = await upload(c, rid)
            r = await pay(c, rid, photo)
            assert r.status_code == 200, r.text
            assert r.json()["payment"]["amount"] == .3 and r.json()["account_balance"] == 9999.7
            assert (await costs(c))["amount"] == 750.3
            r = await c.post(f"{BASE}/{rid}/revoke-payment", headers=auth(1), json={"reason": "小数验收"})
            assert r.status_code == 200 and r.json()["status"] == "partially_approved" and r.json()["account_balance"] == 10000
    asyncio.run(run())

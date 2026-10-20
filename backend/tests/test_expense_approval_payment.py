"""本机真实 PostgreSQL：免审批不等于付款，确认付款原子且只发生一次。"""
import asyncio
import base64
import json
import os
import sys
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime
from pathlib import Path

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select, func, text

from app.main import app
from app.models import PaymentAccount, User
from app.models.expense_approval import ExpenseApproval
from app.models.expense_fund import ExpenseFund, ExpenseFundItem, SystemSetting
from app.models.income_expense import ExpenseRecord
from app.models.data_change_history import DataChangeHistory
from app.services.account_balances import current_account_balances
from app.services.employee_advance_funding import fund_available_amount
from app.services.wallet import flow_query
from app.core.timezone import THAI_TZ
from scripts.seed import _migrate_expense_approval_payment
from scripts.audit_expense_approval_payments import collect_anomalies
from tests.test_incoming_operations import environment, URL
from tests.test_round2_permissions import auth, png

pytestmark = pytest.mark.skipif(not URL, reason="Requires explicitly configured isolated PostgreSQL")
RESULTS = {}
IMAGE = "data:image/png;base64," + base64.b64encode(png()).decode()


def actual(key, value):
    RESULTS[key] = value
    if os.environ.get("EXPENSE_PAYMENT_TEST_REPORT"):
        Path(os.environ["EXPENSE_PAYMENT_TEST_REPORT"]).write_text(json.dumps(RESULTS, ensure_ascii=False, indent=2))


@asynccontextmanager
async def fee_environment(tmp_path, monkeypatch, *, fund=False):
    import app.api.v1.expense_approval as api
    monkeypatch.setattr(api, "thai_now", lambda: datetime(2026, 10, 20, 12, 0, tzinfo=THAI_TZ))
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    async with environment(tmp_path, monkeypatch) as (engine, factory, client):
        async with factory() as db:
            (await db.get(PaymentAccount, 1)).opening_balance = 1000
            for uid in (3, 4):
                (await db.get(User, uid)).extra_permissions = ["费用审批", "到账流水"]
            db.add(SystemSetting(warehouse_id=1, key="expense_approval_threshold", value="500"))
            if fund:
                db.add(ExpenseFund(id=1, warehouse_id=1, employee_id=4, receive_date=datetime(2026, 10, 1),
                    amount=1000, remaining_balance=1000, currency="THB", purpose="隔离测试备用金"))
            await db.commit()
        yield engine, factory, client


async def create(client, *, uid=1, **overrides):
    response = await client.post("/api/v1/expense-approvals", headers=auth(uid), json={
        "amount": 200, "purpose": "隔离测试小额耗材", "expense_date": "2026-09-30",
        "currency": "THB", "fund_source": "company", "payment_account_id": 1, **overrides})
    assert response.status_code == 200, response.text
    return response.json()


async def pay(client, aid, uid=1, **overrides):
    return await client.post(f"/api/v1/expense-approvals/{aid}/pay", headers=auth(uid),
        json={"voucher_base64": IMAGE, "payment_account_id": 1, **overrides})


async def numbers(factory):
    async with factory() as db:
        account = await db.get(PaymentAccount, 1)
        fund = await db.get(ExpenseFund, 1)
        q = flow_query(db, [1])
        flows = (await db.execute(select(q.c.source, q.c.date, q.c.amount, q.c.ref_no).where(
            q.c.status == "active", q.c.type == "expense", q.c.account_id == 1))).all()
        return {"company_balance": float((await current_account_balances(db, [account]))[1]),
            "expense_rows": (await db.execute(select(func.count(ExpenseRecord.id)))).scalar_one(),
            "wallet_payment_count": len(flows), "wallet_payment_amount": float(sum(r.amount for r in flows)),
            "wallet_dates": [r.date.isoformat() for r in flows],
            "fund_available": float(await fund_available_amount(db, fund)) if fund else None,
            "fund_items": (await db.execute(select(func.count(ExpenseFundItem.id)))).scalar_one(),
            "valid_payments": (await db.execute(select(func.count(ExpenseApproval.id)).where(ExpenseApproval.status == "paid"))).scalar_one(),
            "payment_history_count": (await db.execute(select(func.count(DataChangeHistory.id)).where(
                DataChangeHistory.module == "expense_approval", DataChangeHistory.operation_type == "pay"))).scalar_one()}


def test_company_small_fee_waits_for_payment_and_retries_return_original(tmp_path, monkeypatch):
    async def run():
        async with fee_environment(tmp_path, monkeypatch) as (_, factory, client):
            created = await create(client, uid=4)
            assert created["status"] == "approved" and "等待确认付款" in created["message"]
            before = await numbers(factory)
            assert before["company_balance"] == 1000 and before["valid_payments"] == before["expense_rows"] == before["wallet_payment_count"] == 0
            async with factory() as db:
                row = await db.get(ExpenseApproval, created["id"])
                assert row.payer_id is row.paid_at is row.approver_id is row.approved_at is None
            paid = await pay(client, created["id"])
            assert paid.status_code == 200, paid.text
            result = paid.json()
            assert result["payer_id"] == 1 and result["paid_at"] == "2026-10-20T12:00:00+07:00"
            after = await numbers(factory)
            assert after["company_balance"] == 800 and after["wallet_payment_amount"] == 200
            assert after["expense_rows"] == after["wallet_payment_count"] == after["valid_payments"] == after["payment_history_count"] == 1
            assert after["wallet_dates"] == ["2026-10-20"]
            for _ in range(3):
                retry = await pay(client, created["id"])
                assert retry.status_code == 200 and retry.json()["already_paid"]
                for key in ("payer_id", "paid_at", "expense_record_id", "payment_voucher", "ledger_ref_no"):
                    assert retry.json()[key] == result[key]
            assert await numbers(factory) == after
            mismatch = await pay(client, created["id"], payment_account_id=2)
            assert mismatch.status_code == 409
            rows = (await client.get("/api/v1/expense-approvals", headers=auth(1))).json()["data"]
            assert rows[0]["payer_id"] == 1 and rows[0]["payer_name"] == "测试账号1" and rows[0]["paid_at"]
            summary = (await client.get("/api/v1/expense-approvals/summary", headers=auth(1))).json()
            assert summary["approved_count"] == 0 and summary["paid_by_currency"] == [{"currency": "THB", "amount": 200}]
            actual("company_small_fee", {"created": created, "before_payment": before, "payment": result,
                "after_payment_and_three_retries": after, "summary": summary, "changed_account": mismatch.status_code})
    asyncio.run(run())


@pytest.mark.parametrize("fund", [False, True])
def test_real_concurrent_confirmation_only_charges_once(tmp_path, monkeypatch, fund):
    async def run():
        async with fee_environment(tmp_path, monkeypatch, fund=fund) as (_, factory, client):
            created = await create(client, fund_source="fund" if fund else "company", payment_account_id=None if fund else 1)
            before = await numbers(factory)
            gate = asyncio.Barrier(10)
            async def simultaneous():
                await gate.wait()
                return await pay(client, created["id"], payment_account_id=None if fund else 1)
            responses = await asyncio.gather(*(simultaneous() for _ in range(10)))
            assert all(r.status_code == 200 for r in responses), [(r.status_code, r.text) for r in responses]
            assert sum(not r.json()["already_paid"] for r in responses) == 1
            assert len({r.json()["fund_item_id" if fund else "expense_record_id"] for r in responses}) == 1
            after = await numbers(factory)
            assert after["valid_payments"] == after["payment_history_count"] == 1
            if fund:
                assert after["company_balance"] == 1000 and after["fund_available"] == 800 and after["fund_items"] == 1
                assert after["expense_rows"] == after["wallet_payment_count"] == 0
                async with factory() as db:
                    row = await db.get(ExpenseApproval, created["id"])
                    item = await db.get(ExpenseFundItem, row.fund_item_id)
                    assert item.receipt == row.payment_voucher and item.review_status == "approved" and item.cost_record_only
                again = await pay(client, created["id"], payment_account_id=None)
                assert again.status_code == 200 and again.json()["already_paid"]
            else:
                assert after["company_balance"] == 800 and after["expense_rows"] == after["wallet_payment_count"] == 1
            assert await numbers(factory) == after
            actual("concurrent_fund" if fund else "concurrent_company", {"requests": 10, "before": before,
                "first_payment_responses": 1, "reused_payment_responses": 9, "after": after})
    asyncio.run(run())


@pytest.mark.parametrize("fund", [False, True])
def test_different_fees_cannot_concurrently_overdraw_same_funds(tmp_path, monkeypatch, fund):
    async def run():
        async with fee_environment(tmp_path, monkeypatch, fund=fund) as (_, factory, client):
            ids = []
            for _ in range(2):
                row = await create(client, amount=700, fund_source="fund" if fund else "company", payment_account_id=None if fund else 1)
                approved = await client.post(f'/api/v1/expense-approvals/{row["id"]}/approve', headers=auth(1))
                assert approved.status_code == 200
                ids.append(row["id"])
            responses = await asyncio.gather(*(pay(client, aid, payment_account_id=None if fund else 1) for aid in ids))
            assert sorted(r.status_code for r in responses) == [200, 400]
            after = await numbers(factory)
            assert after["valid_payments"] == 1
            assert after["fund_available" if fund else "company_balance"] == 300
            actual("no_overdraw_fund" if fund else "no_overdraw_company", {"http": sorted(r.status_code for r in responses), "after": after})
    asyncio.run(run())


@pytest.mark.parametrize("fund", [False, True])
def test_pending_rejected_and_failed_payment_leave_all_money_unchanged(tmp_path, monkeypatch, fund):
    async def run():
        import app.services.data_history as history
        import app.api.v1.expense_approval as api
        async with fee_environment(tmp_path, monkeypatch, fund=fund) as (_, factory, client):
            initial = await numbers(factory)
            pending = await create(client, amount=600, fund_source="fund" if fund else "company", payment_account_id=None if fund else 1)
            assert pending["status"] == "pending"
            denied = await pay(client, pending["id"], payment_account_id=None if fund else 1)
            assert denied.status_code == 400
            assert (await client.post(f'/api/v1/expense-approvals/{pending["id"]}/reject', headers=auth(1), json={"note":"不予支付"})).status_code == 200
            assert (await pay(client, pending["id"], payment_account_id=None if fund else 1)).status_code == 400
            assert await numbers(factory) == initial
            row = await create(client, fund_source="fund" if fund else "company", payment_account_id=None if fund else 1)
            original = history.record_history
            async def fail_after_financial_writes(*args, **kwargs):
                raise RuntimeError("isolated failure after expense/fund item flush")
            monkeypatch.setattr(history, "record_history", fail_after_financial_writes)
            async with AsyncClient(transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://isolated-test") as faulty:
                failed = await pay(faulty, row["id"], payment_account_id=None if fund else 1)
                assert failed.status_code == 500
            assert await numbers(factory) == initial
            async with factory() as db:
                stored = await db.get(ExpenseApproval, row["id"])
                assert stored.status == "approved" and stored.payer_id is stored.paid_at is stored.expense_record_id is stored.fund_item_id is None
            monkeypatch.setattr(history, "record_history", original)
            original_save = api._save_voucher
            monkeypatch.setattr(api, "_save_voucher", lambda *args: None)
            assert (await pay(client, row["id"], payment_account_id=None if fund else 1)).status_code == 400
            assert await numbers(factory) == initial
            monkeypatch.setattr(api, "_save_voucher", original_save)
            assert (await pay(client, row["id"], payment_account_id=None if fund else 1)).status_code == 200
            actual("rollback_fund" if fund else "rollback_company", {"pending_pay": 400, "rejected_pay": 400,
                "after_flushed_writes_failure": 500, "before_and_after_failure": initial, "retry": await numbers(factory)})
    asyncio.run(run())


def test_roles_grants_warehouse_currency_and_voucher(tmp_path, monkeypatch):
    async def run():
        async with fee_environment(tmp_path, monkeypatch) as (_, factory, client):
            row = await create(client)
            statuses = {}
            for uid in (2, 3, 4, 5, 7):
                result = await pay(client, row["id"], uid=uid)
                statuses[str(uid)] = {"status": result.status_code, "body": result.json()}
                assert result.status_code == (404 if uid == 7 else 403)
            for uid in (2, 5):
                assert (await client.get("/api/v1/expense-approvals", headers=auth(uid))).status_code == 403
            for uid in (3, 4):
                assert (await client.get("/api/v1/expense-approvals", headers=auth(uid))).status_code == 200
                async with factory() as db:
                    (await db.get(User, uid)).extra_permissions = []
                    await db.commit()
                for method, path, body in [("get", "", None), ("get", "/summary", None), ("post", "", {"amount":200,"purpose":"无权限","expense_date":"2026-10-20"})]:
                    kwargs = {"json":body} if body else {}
                    denied = await getattr(client, method)("/api/v1/expense-approvals"+path, headers=auth(uid), **kwargs)
                    assert denied.status_code == 403 and "无此操作权限" in denied.text
            assert (await pay(client, row["id"], payment_account_id=2)).status_code == 400
            assert (await pay(client, row["id"], payment_account_id=None)).status_code == 400
            assert (await pay(client, row["id"], voucher_base64=None)).status_code == 400
            async with factory() as db:
                (await db.get(PaymentAccount, 1)).currency = "CNY"
                await db.commit()
            assert (await pay(client, row["id"])).status_code == 400
            after = await numbers(factory)
            assert after["valid_payments"] == after["expense_rows"] == after["wallet_payment_count"] == 0
            actual("permissions_and_isolation", {"payment_denials": statuses, "ungranted_finance_supervisor": 403,
                "wrong_warehouse_account":400,"wrong_currency":400,"missing_account":400,"missing_voucher":400,"after":after})
    asyncio.run(run())


@pytest.mark.parametrize("legacy", [False, True])
def test_additive_migration_repeat_savepoint_and_read_only_history(tmp_path, monkeypatch, legacy):
    async def run():
        async with fee_environment(tmp_path, monkeypatch) as (engine, factory, client):
            if legacy:
                async with engine.begin() as conn:
                    await conn.execute(text("ALTER TABLE expense_approvals DROP COLUMN fund_item_id"))
                    await conn.execute(text("INSERT INTO expense_approvals(warehouse_id,applicant_id,amount,currency,purpose,expense_date,payment_method,fund_source,status) VALUES(1,4,123,'THB','历史小额','2026-09-30','cash','fund','completed')"))
                async with engine.begin() as conn:
                    class FailOnce:
                        def begin_nested(self): return conn.begin_nested()
                        async def execute(self, statement):
                            if "CREATE UNIQUE INDEX" in str(statement):
                                return await conn.execute(text("SELECT * FROM intentionally_missing_table"))
                            return await conn.execute(statement)
                    with pytest.raises(Exception):
                        await _migrate_expense_approval_payment(FailOnce())
                    assert (await conn.execute(text("SELECT 1"))).scalar_one() == 1
            for _ in range(2):
                async with engine.begin() as conn: await _migrate_expense_approval_payment(conn)
            async with factory() as db:
                await db.execute(text("SET TRANSACTION READ ONLY"))
                rows = await collect_anomalies(db)
                assert len(rows) == int(legacy)
                if legacy:
                    assert rows[0]["amount"] == 123 and rows[0]["status"] == "completed" and rows[0]["fund_item_id"] is None
                await db.rollback()
            after = await numbers(factory)
            assert after["wallet_payment_count"] == after["fund_items"] == after["expense_rows"] == 0
            actual("migration_legacy" if legacy else "migration_new", {"runs": 2, "anomalies_read_only": rows, "unchanged_money": after})
    asyncio.run(run())


def test_full_seed_new_legacy_and_repeat_startup(tmp_path):
    async def run():
        import asyncpg
        admin = await asyncpg.connect(URL.replace("postgresql+asyncpg://", "postgresql://"))
        name = "fee_round2_startup_" + uuid.uuid4().hex
        await admin.execute("CREATE DATABASE " + name)
        test_url = URL.rsplit("/", 1)[0] + "/" + name
        connection = None
        try:
            backend = Path(__file__).resolve().parents[1]
            env = {**os.environ, "PYTHONPATH":str(backend), "DATABASE_URL":test_url,
                "SECRET_KEY":"isolated-fee-startup-no-production", "SEED_ADMIN_PASSWORD":"isolated-fee-seed-password"}
            results = {}
            for step in ("new_database", "legacy_upgrade", "restart"):
                if step == "legacy_upgrade":
                    connection = await asyncpg.connect(test_url.replace("postgresql+asyncpg://", "postgresql://"))
                    uid = await connection.fetchval("SELECT id FROM users ORDER BY id LIMIT 1")
                    wid = await connection.fetchval("SELECT id FROM warehouses ORDER BY id LIMIT 1")
                    await connection.execute("ALTER TABLE expense_approvals DROP COLUMN fund_item_id")
                    await connection.execute("INSERT INTO expense_approvals(warehouse_id,applicant_id,amount,currency,purpose,expense_date,payment_method,fund_source,status) VALUES($1,$2,123,'THB','历史费用','2026-09-30','cash','fund','completed')", wid, uid)
                process = await asyncio.create_subprocess_exec(sys.executable, "scripts/seed.py", cwd=backend, env=env,
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
                output, _ = await process.communicate()
                (tmp_path / f"seed-{step}.txt").write_bytes(output)
                assert process.returncode == 0, output.decode(errors="replace")[-4000:]
                results[step] = {"exit_code": process.returncode}
            old = await connection.fetchrow("SELECT status,amount,fund_item_id,payer_id,paid_at FROM expense_approvals WHERE purpose='历史费用'")
            assert dict(old) == {"status":"completed", "amount":123, "fund_item_id":None, "payer_id":None, "paid_at":None}
            assert await connection.fetchval("SELECT count(*) FROM pg_indexes WHERE indexname='uq_expense_approval_fund_item'") == 1
            results["historical_row_unchanged"] = dict(old)
            actual("full_startup", results)
        finally:
            if connection: await connection.close()
            await admin.execute("DROP DATABASE " + name)
            await admin.close()
    asyncio.run(run())


def test_cash_advance_wage_reimbursement_and_repayment_do_not_duplicate_wallet_cost(tmp_path, monkeypatch):
    async def run():
        from app.models import Employee, CashAdvance, IncomeExpenseCategory
        from app.models.payroll import PayrollRecord
        from app.models.reimbursement import Reimbursement
        from tests.test_cash_advance_repayments import voucher, repay
        from tests.test_reimbursement_payments import upload, pay as reimb_pay
        import app.api.v1.cash_advance as advances
        import app.services.reimbursement_payment as reimbursement
        async with fee_environment(tmp_path, monkeypatch) as (_, factory, client):
            monkeypatch.setattr(advances, "UPLOAD_DIR", str(tmp_path / "uploads"))
            monkeypatch.setattr(reimbursement, "UPLOAD_DIR", str(tmp_path / "uploads"))
            async with factory() as db:
                (await db.get(PaymentAccount, 1)).opening_balance = 20000
                db.add(Employee(id=1, warehouse_id=1, name="隔离测试员工", user_id=5, status="regular"))
                db.add(IncomeExpenseCategory(warehouse_id=1, type="expense", name="员工工资", category_group="operating", status="active"))
                await db.flush()
                db.add(PayrollRecord(id=1, warehouse_id=1, employee_id=1, period="2026-10", half="first_half", status="confirmed", net_pay=7000))
                db.add(Reimbursement(id=1, warehouse_id=1, employee_id=4, submit_date=datetime(2026,10,20), total_amount=2000, currency="THB", status="approved"))
                await db.commit()
            created = await client.post("/api/v1/cash-advances", headers=auth(1), json={
                "advance_date":"2026-10-20", "amount":"10000.00", "currency":"THB", "purpose":"salary", "payer_id":4})
            assert created.status_code == 200, created.text
            aid = created.json()["id"]
            initial = await numbers(factory)
            wages = await client.post("/api/v1/payroll/1/disburse", headers=auth(1), json={"funding_source":"cash_advance", "cash_advance_id":aid})
            assert wages.status_code == 200, wages.text
            reimb = await reimb_pay(client, 1, await upload(client,1), funding_source="cash_advance", payment_account_id=None, cash_advance_id=aid)
            assert reimb.status_code == 200, reimb.text
            used = await numbers(factory)
            assert used["company_balance"] == 20000 and used["wallet_payment_amount"] == used["expense_rows"] == 0
            async with factory() as db:
                debt_before = float((await db.get(CashAdvance, aid)).amount - (await db.get(CashAdvance, aid)).repaid_amount)
                business_before = (await db.get(PayrollRecord,1)).net_pay + (await db.get(Reimbursement,1)).total_amount
            returned = await repay(client, aid, await voucher(client), amount="9000.00", repayment_date="2026-10-20", request_key="fee-round2-repayment")
            assert returned.status_code == 200, returned.text
            final = await numbers(factory)
            assert final["company_balance"] == 11000 and final["wallet_payment_amount"] == 9000 and final["wallet_payment_count"] == 1
            assert final["expense_rows"] == 0  # Repayment is a wallet projection, not a duplicate ExpenseRecord.
            async with factory() as db:
                debt_after = float((await db.get(CashAdvance,aid)).amount - (await db.get(CashAdvance,aid)).repaid_amount)
                business_after = (await db.get(PayrollRecord,1)).net_pay + (await db.get(Reimbursement,1)).total_amount
            assert debt_before == 10000 and debt_after == 1000 and business_before == business_after == 9000
            report = await client.get("/api/v1/reports/income-expense", headers=auth(1), params={"start_date":"2026-10-01","end_date":"2026-10-31"})
            assert report.status_code == 200 and report.json()["total_expense_by_currency"] == {"THB":9000}
            actual("advance_regression", {"wages":7000,"reimbursement":2000,"business_occurrence_before_and_after_repayment":9000,
                "company_cashout_before_repayment":0,"company_cashout_after_repayment":9000,
                "debt_before_repayment":debt_before,"debt_after_repayment":debt_after,
                "initial":initial,"after_advance_use":used,"after_repayment":final,
                "note":"业务发生额仅核对原工资及报销事实；现有名为成本的报表沿用钱包支出口径，不存在独立权责成本账。"})
    asyncio.run(run())

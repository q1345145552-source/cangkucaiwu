"""新预支审批联动支出：真实 HTTP、工资不重复记账、旧数据和事务回滚。"""
import asyncio
import ast
from datetime import date, datetime
import json
from pathlib import Path
import subprocess
from tests.financial_reversal_test_support import without_disabled_gate, without_advance_void_query

from fastapi import HTTPException
import pytest
from sqlalchemy import select, func

from app.models import Employee, User, UserWarehouse, ClockInRecord
from app.models.employee_advance import EmployeeAdvance
from app.models.expense_fund import ExpenseFund, ExpenseFundItem
from app.models.income_expense import ExpenseRecord, IncomeExpenseCategory
from app.models.data_change_history import DataChangeHistory
from app.models.payroll import PayrollRecord
from app.services import employee_advance_expense as service
from app.services import cost_funds_debt as report
from tests.test_round2_permissions import auth, set_perms
from tests.test_round3_permissions import snapshot
from tests.advance_funding_test_support import funded_hr_environment as original_environment, funding_body
from contextlib import asynccontextmanager
from tests.round3_flow_support import money_state, DeferredChecks
import app.api.v1.payroll as payroll

BASE = "/api/v1/employee-advances"
BODY = {"employee_id": 1, "amount": 1000, "advance_date": "2026-10-16", "source": "supervisor", "funding_source": "company_account", "payment_account_id": 1}


@asynccontextmanager
async def hr_environment(tmp_path, monkeypatch):
    async with original_environment(tmp_path,monkeypatch) as values:
        async with values[1]() as db:
            for uid,role in ((94,'staff'),(95,'warehouse_admin')):
                db.add(User(id=uid,username=f'synthetic-independent-{uid}',display_name=f'SYN independent {uid}',role=role,warehouse_id=1,password_hash='unused',extra_permissions=['员工预支','工资']))
            await db.flush()
            db.add_all([UserWarehouse(user_id=94,warehouse_id=1),UserWarehouse(user_id=95,warehouse_id=1)])
            await db.commit()
        yield values

async def prepare_execution(f,c,aid):
    async with f() as db:creator=(await db.get(EmployeeAdvance,aid)).operator_id
    verifier=3 if creator==94 else 94
    before=await money_state(f)
    for action,uid in [('verify',verifier),('approve',95)]:
        r=await c.post(f'{BASE}/{aid}/{action}',headers=auth(uid))
        assert r.status_code==200,r.text
        assert await money_state(f)==before
    return verifier

async def execute(f,c,aid):
    uid=await prepare_execution(f,c,aid)
    r=await c.post(f'{BASE}/{aid}/execute',headers=auth(uid))
    assert r.status_code==200,r.text
    return r


async def expenses(f):
    async with f() as db:
        return (await db.execute(select(ExpenseRecord).order_by(ExpenseRecord.id))).scalars().all()


async def supervisor_self(f):
    await set_perms(f, 4, ["员工预支"])
    async with f() as db:
        u = await db.get(User, 4)
        u.attendance_enabled, u.attendance_employee_id = True, 1
        emp = await db.get(Employee, 1)
        emp.user_id, emp.status, emp.hire_date = 4, "regular", datetime(2026, 10, 16)
        for d in (16, 17, 18):
            for session, hour in ((1, 9), (2, 12), (3, 13), (4, 18)):
                db.add(ClockInRecord(user_id=4, warehouse_id=1, clock_date=date(2026, 10, d),
                    session=session, clocked_in_at=datetime(2026, 10, d, hour), status="normal"))
        await db.commit()


def test_self_pending_approve_once_and_payroll_never_writes_expense(tmp_path, monkeypatch):
    async def run():
        async with hr_environment(tmp_path, monkeypatch) as (_, f, c):
            monkeypatch.setattr(payroll, "thai_today", lambda: date(2026, 10, 20))
            import app.api.v1.employee_advance as advance_api
            monkeypatch.setattr(advance_api,"thai_now",lambda: datetime(2026,10,16))
            await supervisor_self(f)
            old_payroll = await snapshot(f)
            pending = await c.post(BASE, headers=auth(4), json=BODY)
            assert pending.status_code == 200, pending.text
            aid = pending.json()["id"]
            assert pending.json()["approval_status"] == "pending" and pending.json()["expense_record_id"] is None
            assert len(await expenses(f)) == 0
            approved = await execute(f,c,aid)
            assert approved.status_code == 200, approved.text
            eid = approved.json()["expense_record_id"]
            rows = await expenses(f)
            assert len(rows) == 1 and rows[0].id == eid and rows[0].amount == 1000
            assert rows[0].warehouse_id == 1 and rows[0].currency == "THB" and rows[0].account_id == 1
            assert rows[0].expense_date == datetime(2026, 10, 16) and "员工1" in rows[0].remark and "预支" in rows[0].remark
            async with f() as db:
                cat = await db.get(IncomeExpenseCategory, rows[0].category_id)
                assert (cat.name, cat.type, cat.category_group) == ("员工预支", "expense", "operating")
            repeat = await c.post(f"{BASE}/{aid}/approve", headers=auth(1))
            assert repeat.status_code == 400 and set(repeat.json()) == {"detail"}
            assert len(await expenses(f)) == 1 and await snapshot(f) == old_payroll
            # 先按原工资算法算出1200，再仅由原抵扣逻辑扣1000；成本仍只有原来一笔。
            calc = await c.post("/api/v1/payroll/calculate", headers=auth(3),
                json={"end_date": "2026-10-18", "employee_ids": [1]})
            assert calc.status_code == 200, calc.text
            async with f() as db:
                pay = (await db.execute(select(PayrollRecord).where(PayrollRecord.employee_id == 1,
                    PayrollRecord.settle_start_date == date(2026, 10, 16), PayrollRecord.voided == False))).scalar_one()
                assert (pay.base_pay, pay.advance_deduction, pay.net_pay) == (1200, 1000, 200)
            assert len(await expenses(f)) == 1
            recalc = await c.post(f"/api/v1/payroll/{pay.id}/recalc", headers=auth(3),
                json={"mode": "recalc", "void_reason": "验证预支抵扣不重复写支出"})
            assert recalc.status_code == 200, recalc.text
            assert len(await expenses(f)) == 1
            # 预支和两个支出查询口径都能互查，且分类金额/条数相同。
            listing = (await c.get(BASE, headers=auth(1))).json()["data"]
            assert next(r for r in listing if r["id"] == aid)["expense_record_id"] == eid
            for mode in ("records", "unified"):
                r = await c.get("/api/v1/income-expense/expense", headers=auth(1), params={
                    "category_group": "operating", "cost_view": mode, "start_date": "2026-10-01", "end_date": "2026-10-31"})
                assert r.status_code == 200, r.text
                assert r.json()["total"] == 1
                expense = r.json()["data"][0]
                assert expense["employee_advance_id"] == aid and expense["employee_id"] == 1 and expense["is_read_only"]
            current = await snapshot(f)
            assert [r for r in current if r[0] in {v[0] for v in old_payroll}] == old_payroll
            async with f() as db:
                final_pay = (await db.execute(select(PayrollRecord).where(PayrollRecord.employee_id == 1,
                    PayrollRecord.settle_start_date == date(2026, 10, 16), PayrollRecord.voided == False))).scalar_one()
                assert final_pay.net_pay == 200 and final_pay.advance_deduction == 1000
            assert (await c.post(f"/api/v1/payroll/{final_pay.id}/confirm", headers=auth(1))).status_code == 200
            paid = await c.post(f"/api/v1/payroll/{final_pay.id}/disburse", headers=auth(3), json={"account_id": 1})
            assert paid.status_code == 200, paid.text
            paid_costs = await expenses(f)
            assert len(paid_costs) == 2 and sum(r.amount for r in paid_costs) == 1200
            print("ADVANCE_EXPENSE_PAYROLL", json.dumps({"pending_expense_count": 0,
                "approve_response": approved.json(), "expense_date": "2026-10-16", "expense_remark": rows[0].remark,
                "approved_expense_count": 1, "expense_amount": 1000, "gross_pay": 1200,
                "advance_deduction": 1000, "net_pay": 200, "after_calc_and_recalc_expense_count": 1,
                "after_disburse_expense_count": 2, "after_disburse_total_cost": 1200}, ensure_ascii=False))
    asyncio.run(run())


@pytest.mark.parametrize("uid", [1, 3, 4])
def test_direct_approved_creation_and_rejected_never_cost(tmp_path, monkeypatch, uid):
    async def run():
        async with hr_environment(tmp_path, monkeypatch) as (_, f, c):
            if uid != 1:
                await set_perms(f, uid, ["员工预支"])
            if uid==4: await supervisor_self(f)
            r = await c.post(BASE, headers=auth(uid), json=BODY)
            assert r.status_code == 200 and r.json()["approval_status"] == "pending", r.text
            assert len(await expenses(f))==0
            r=await execute(f,c,r.json()["id"])
            assert r.json()["expense_record_id"] and len(await expenses(f)) == 1
            await supervisor_self(f)
            r = await c.post(BASE, headers=auth(4), json=BODY)
            rejected = await c.post(f"{BASE}/{r.json()['id']}/reject", headers=auth(1), json={"reject_reason": "不符合要求"})
            assert rejected.status_code == 200 and rejected.json()["expense_record_id"] is None
            assert len(await expenses(f)) == 1
    asyncio.run(run())


def test_legacy_approved_pending_rejected_never_backfilled(tmp_path, monkeypatch):
    async def run():
        async with hr_environment(tmp_path, monkeypatch) as (engine, f, c):
            async with f() as db:
                for status in ("approved", "pending", "rejected"):
                    db.add(EmployeeAdvance(warehouse_id=1, employee_id=1, amount=800,
                        advance_date=date(2026, 9, 1), period="2026-09", approval_status=status, source="supervisor"))
                await db.commit()
                old = (await db.execute(select(EmployeeAdvance))).scalars().all()
                pending_id = next(r.id for r in old if r.approval_status == "pending")
            async with engine.begin() as conn:
                await service.backfill_advance_categories(conn)
                await service.backfill_advance_categories(conn)
            assert len(await expenses(f)) == 0
            r = await c.post(f"{BASE}/{pending_id}/approve", headers=auth(1))
            assert r.status_code == 409 and set(r.json()) == {"detail"}
            async with f() as db:
                assert (await db.execute(select(func.count()).select_from(EmployeeAdvance))).scalar_one() == 3
                assert (await db.execute(select(func.count()).select_from(IncomeExpenseCategory).where(
                    IncomeExpenseCategory.name == "员工预支"))).scalar_one() == 2
                assert all(not a.expense_tracking_enabled and a.expense_record_id is None for a in (await db.execute(select(EmployeeAdvance))).scalars())
            assert len(await expenses(f)) == 0
            print("ADVANCE_EXPENSE_LEGACY", {"old_advance_count_before": 3, "old_advance_count_after": 3,
                "old_linked_expense_count": 0, "expense_count_before": 0, "expense_count_after": 0,
                "category_count_per_warehouse": 1})
    asyncio.run(run())


@pytest.mark.parametrize("source", ["supervisor", "fund"])
def test_delete_linked_cost_and_history_and_protect_manual_edits(tmp_path, monkeypatch, source):
    async def run():
        async with hr_environment(tmp_path, monkeypatch) as (_, f, c):
            body = funding_body(BODY, {"source": source})
            if source == "fund":
                async with f() as db:
                    db.add(ExpenseFund(id=8, warehouse_id=1, employee_id=1, amount=5000, remaining_balance=5000,
                        currency="THB", receive_date=datetime(2026, 10, 1), purpose="测试"))
                    await db.commit()
                body["fund_account_id"] = 8
            r = await c.post(BASE, headers=auth(94), json=body)
            assert r.status_code == 200, r.text
            r=await execute(f,c,r.json()["id"])
            aid, eid = r.json()["id"], r.json()["expense_record_id"]
            if source != "fund":
                denied = await c.delete(f"/api/v1/income-expense/expense/{eid}", headers=auth(1))
                assert denied.status_code == 400 and denied.json()["detail"] == "预支联动支出请在员工预支模块处理"
                denied = await c.put(f"/api/v1/income-expense/expense/{eid}", headers=auth(1), data={
                    "category_id": (await expenses(f))[0].category_id, "account_id": 1, "amount": 3000, "expense_date": "2026-10-16"})
                assert denied.status_code == 400 and "预支联动支出" in denied.text
            removed = await c.request("DELETE", f"{BASE}/{aid}", headers=auth(1), json={"void_reason": "测试作废"})
            assert removed.status_code == 200, removed.text
            assert len(await expenses(f)) == 0
            async with f() as db:
                assert (await db.get(EmployeeAdvance, aid)).status == "voided"
                if source == "fund":
                    assert (await db.execute(select(func.count()).select_from(ExpenseFundItem))).scalar_one() == 0
                logs = (await db.execute(select(DataChangeHistory).where(DataChangeHistory.module == "expense"))).scalars().all()
                assert [r.operation_type for r in logs] == ([] if source == "fund" else ["create", "delete"])
                assert all((r.after_data if r.operation_type == "create" else r.before_data)["employee_advance_id"] == aid for r in logs)
    asyncio.run(run())


@pytest.mark.parametrize("action", ["create", "approve", "delete"])
@pytest.mark.parametrize("source", ["supervisor", "fund"])
def test_expense_failure_rolls_back_both_sides(tmp_path, monkeypatch, action, source):
    async def run():
        async with hr_environment(tmp_path, monkeypatch) as (_, f, c):
            aid = None
            body = funding_body(BODY, {"source": source})
            if source == "fund":
                async with f() as db:
                    db.add(ExpenseFund(id=8, warehouse_id=1, employee_id=4, amount=5000, remaining_balance=5000,
                        currency="THB", receive_date=datetime(2026, 10, 1), purpose="回滚测试"))
                    await db.commit()
                body["fund_account_id"] = 8
            if action == "approve":
                await supervisor_self(f)
            creator=4 if action=="approve" else 94
            made=await c.post(BASE,headers=auth(creator),json=body)
            assert made.status_code==200,made.text
            aid=made.json()['id']
            executor=await prepare_execution(f,c,aid)
            if action=="delete":
                result=await c.post(f'{BASE}/{aid}/execute',headers=auth(executor))
                assert result.status_code==200,result.text
            before_expenses = [(r.id, r.amount) for r in await expenses(f)]
            async with f() as db:
                before_items = [tuple(r) for r in (await db.execute(select(ExpenseFundItem.__table__))).all()]
            async def broken(db, **kwargs):
                await db.flush()
                raise HTTPException(500, "模拟支出日志失败")
            if source == "fund":
                import app.api.v1.employee_advance as advance_api
                import app.services.employee_advance_funding as advance_funding
                monkeypatch.setattr(advance_api if action == "delete" else advance_funding, "record_history", broken)
            else:
                monkeypatch.setattr(service, "record_history", broken)
            if action in ("create","approve"):r=await c.post(f'{BASE}/{aid}/execute',headers=auth(executor))
            else:r=await c.request("DELETE",f'{BASE}/{aid}',headers=auth(1),json={"void_reason":"测试回滚"})
            assert r.status_code == 500, r.text
            assert [(r.id, r.amount) for r in await expenses(f)] == before_expenses
            async with f() as db:
                assert [tuple(r) for r in (await db.execute(select(ExpenseFundItem.__table__))).all()] == before_items
                if aid:
                    row = await db.get(EmployeeAdvance, aid)
                    assert row and row.approval_status == ("approved_ready" if action in ("create","approve") else "approved")
                else:
                    assert (await db.execute(select(func.count()).select_from(EmployeeAdvance))).scalar_one() == 0
                if action == "approve":
                    assert row.reviewer_id == 95 and row.reviewed_at is not None and row.expense_record_id is None
    asyncio.run(run())


def test_fund_advance_no_cost_preserves_currency_and_no_second_company_flow(tmp_path, monkeypatch):
    async def run():
        deferred=DeferredChecks()
        from app.models.recharge import ExchangeRate
        async with hr_environment(tmp_path, monkeypatch) as (_, f, c):
            await supervisor_self(f)
            async with f() as db:
                db.add(ExpenseFund(id=8, warehouse_id=1, employee_id=4, amount=5000, remaining_balance=5000,
                    currency="CNY", receive_date=datetime(2026, 9, 30), purpose="测试"))
                db.add(ExchangeRate(warehouse_id=1, from_currency="CNY", to_currency="THB", rate=5,
                    effective_from=datetime(2026, 9, 30)))
                await db.commit()
            r = await c.post(BASE, headers=auth(4), json=funding_body(BODY, {"source": "fund", "fund_account_id": 8}))
            assert r.status_code == 200 and r.json()["approval_status"] == "pending", r.text
            aid = r.json()["id"]
            async with f() as db:
                a = await db.get(EmployeeAdvance, aid)
                assert a.fund_item_id is None
                q = report.cost_query(db, [1])
                with deferred.check('original-pending-fund-zero-cost'):
                    assert not (await db.execute(select(q))).all()  # 未通过的也不能从备用金合并进成本。
            r = await execute(f,c,aid)
            assert r.status_code == 200, r.text
            rows = await expenses(f)
            assert len(rows) == 0
            async with f() as db:
                a = await db.get(EmployeeAdvance, aid)
                item = await db.get(ExpenseFundItem, a.fund_item_id)
                assert item.currency == "CNY" and item.amount == 1000
            async with f() as db:
                q = report.cost_query(db, [1])
                costs = (await db.execute(select(q))).mappings().all()
                # 资金来源轮：新备用金预支只记开销台账，不再生成成本记录。
                with deferred.check('original-executed-fund-zero-cost'):
                    assert costs == []
                q = report.flow_query(db, [1])
                flows = (await db.execute(select(q))).mappings().all()
                assert len(flows) == 1 and flows[0]["source"] == "expense_fund" and float(flows[0]["amount"]) == 5000
                fund = await db.get(ExpenseFund, 8)
                assert fund.remaining_balance == 5000  # 保留原备用金余额/开销计算方式。
        deferred.finish()
    asyncio.run(run())


def test_payroll_frontend_and_unrelated_write_code_unchanged():
    root = Path(__file__).resolve().parents[2]
    for path in ("backend/app/services/payroll_expense.py", "backend/app/services/employee_advance_expense.py", "backend/app/services/cost_funds_debt.py"):
        old=subprocess.check_output(["git","show",f"0e4d2f9b45f9850754b1996c9127a48d0ff2e816:{path}"],cwd=root).decode()
        assert (root/path).read_text()==old
    seed = ast.parse((root / "backend/scripts/seed.py").read_text())
    assert any(isinstance(n, ast.Call) and getattr(n.func, "id", "") == "_migrate_employee_advance_expenses" for n in ast.walk(seed))

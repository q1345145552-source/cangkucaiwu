"""作废代替硬删：真实接口、关联支出、工资保护、额度释放和事务回滚。"""
import asyncio
from datetime import date
import json

import pytest
from fastapi import HTTPException
from sqlalchemy import select, func

from app.models import SalaryTemplate
from app.models.employee_advance import EmployeeAdvance
from app.models.income_expense import ExpenseRecord
from app.models.expense_fund import ExpenseFund, ExpenseFundItem
from app.models.data_change_history import DataChangeHistory
from app.models.payroll import PayrollRecord
import app.api.v1.employee_advance as api
import app.api.v1.payroll as payroll
import app.services.employee_advance_expense as expenses
from tests.test_employee_advance_expense import BODY, supervisor_self
from tests.test_round2_permissions import auth, set_perms
from tests.test_round3_permissions import snapshot
from tests.advance_funding_test_support import funded_hr_environment as hr_environment, funding_body
from tests.test_round18_advance_review import add, calculate, prepare_work, period_record
from tests.round3_flow_support import execute_advance

BASE = "/api/v1/employee-advances"


async def create(client, uid=None, **extra):
    response = await client.post(BASE, headers=auth(126 if uid is None else uid), json=funding_body(BODY, extra))
    assert response.status_code == 200, response.text
    created=response.json()
    if uid is None:
        executed=await execute_advance(client.synthetic_factory,client,created["id"])
        created.update(executed.json())
    return created


async def void(client, aid, uid=1, body=None):
    return await client.request("DELETE", f"{BASE}/{aid}", headers=auth(uid),
        json={"void_reason": " 测试登记有误 "} if body is None else body)


async def all_money(factory):
    async with factory() as db:
        return [[tuple(row) for row in (await db.execute(select(model.__table__).order_by(model.id))).all()]
            for model in (EmployeeAdvance, ExpenseRecord, ExpenseFundItem, DataChangeHistory, PayrollRecord)]


def test_void_keeps_row_deletes_cost_releases_quota_and_never_recalculates(tmp_path, monkeypatch):
    async def run():
        async with hr_environment(tmp_path, monkeypatch) as (_, factory, client):
            async with factory() as db:
                template = await db.get(SalaryTemplate, 1)
                template.type, template.amount = "monthly", 10000
                await db.commit()
            old_salary = await snapshot(factory)
            created = await create(client)
            aid, eid = created["id"], created["expense_record_id"]
            assert eid
            async with factory() as db:
                assert (await db.execute(select(func.count()).select_from(ExpenseRecord))).scalar_one() == 1
            response = await void(client, aid)
            assert response.status_code == 200, response.text
            data = response.json()
            assert data["status"] == "voided" and data["voided_by"] == 1 and data["voided_at"]
            assert data["void_reason"] == "测试登记有误" and data["remaining_amount"] == 0
            assert data["approval_status"] == "approved" and data["expense_record_id"] is None
            async with factory() as db:
                row = await db.get(EmployeeAdvance, aid)
                assert row and row.amount == 1000 and row.status == "voided" and row.void_reason == "测试登记有误"
                assert row.voided_by == 1 and row.voided_at and row.deducted_amount == 0
                assert await db.get(ExpenseRecord, eid) is None
                assert (await db.execute(select(func.count()).select_from(EmployeeAdvance))).scalar_one() == 1
                assert (await db.execute(select(func.count()).select_from(ExpenseRecord))).scalar_one() == 0
                logs = (await db.execute(select(DataChangeHistory))).scalars().all()
                removed = next(r for r in logs if r.module == "expense" and r.operation_type == "delete")
                assert removed.before_data["amount"] == 1000 and removed.before_data["employee_advance_id"] == aid
                assert removed.after_data["reason"] == "作废预支：测试登记有误"
                log = next(r for r in logs if r.module == "employee_advances" and r.operation_type == "void")
                assert log.before_data["expense_record_id"] == eid and log.after_data["voided_by"] == 1
            listing = (await client.get(BASE, headers=auth(1))).json()["data"]
            assert len(listing) == 1 and listing[0]["is_voided"] and not listing[0]["can_void"]
            assert listing[0]["remaining_amount"] == 0 and listing[0]["voided_by_name"] == "warehouse_admin"
            summary = (await client.get(BASE + "/summary", headers=auth(1))).json()
            assert summary == {"total_by_currency": [], "debtor_count": 0}
            next_advance = await create(client, amount=10000)
            assert next_advance["limit_check"]["occupied_amount"] == 0
            assert next_advance["limit_check"]["available_amount"] == 10000
            assert await snapshot(factory) == old_salary
            print("ADVANCE_VOID_RESULT", json.dumps({"response": data, "expense_count_before": 1,
                "expense_count_after": 0, "row_still_exists": True, "original_amount": 1000,
                "available_after_void": 10000, "new_advance": 10000}, ensure_ascii=False))
    asyncio.run(run())


@pytest.mark.parametrize("body", [{}, {"void_reason": None}, {"void_reason": " \n\t "}, {"void_reason": "x" * 501}])
def test_reason_required_and_no_changes_on_rejection(tmp_path, monkeypatch, body):
    async def run():
        async with hr_environment(tmp_path, monkeypatch) as (_, factory, client):
            created = await create(client)
            before = await all_money(factory)
            response = await void(client, created["id"], body=body)
            assert response.status_code == 400
            assert response.json()["detail"] == ("作废原因不能超过500字" if len(body.get("void_reason") or "") > 500 else "请填写作废原因")
            assert await all_money(factory) == before
    asyncio.run(run())


@pytest.mark.parametrize("uid", [2, 3, 4, 5])
@pytest.mark.parametrize("grant", [False, True])
def test_only_warehouse_admin_can_void_regardless_of_permission(tmp_path, monkeypatch, uid, grant):
    async def run():
        async with hr_environment(tmp_path, monkeypatch) as (_, factory, client):
            created = await create(client)
            if uid in (3, 4):
                await set_perms(factory, uid, ["员工预支"] if grant else [])
            before = await all_money(factory)
            response = await void(client, created["id"], uid=uid)
            expected = "超级管理员请使用各仓库管理员账号操作" if uid==2 else "无权访问" if uid==5 else "该动作超出当前角色职责上限"
            assert response.status_code == 403 and response.json() == {"detail": expected}
            assert await all_money(factory) == before
    asyncio.run(run())


def test_foreign_warehouse_and_missing_ids_rejected(tmp_path, monkeypatch):
    async def run():
        async with hr_environment(tmp_path, monkeypatch) as (_, factory, client):
            aid = await add(factory, status="approved", wid=2, eid=2)
            before = await all_money(factory)
            for target in (aid, 999):
                response = await void(client, target)
                assert response.status_code == 404
            assert await all_money(factory) == before
    asyncio.run(run())


def test_void_pending_leaves_no_todo_no_debt_and_cannot_be_approved(tmp_path, monkeypatch):
    async def run():
        async with hr_environment(tmp_path, monkeypatch) as (_, factory, client):
            await supervisor_self(factory)
            created = await create(client, uid=4)
            aid = created["id"]
            assert created["approval_status"] == "pending"
            assert (await client.get("/api/v1/dashboard/boss-todos", headers=auth(1))).json()["advances"]["count"] == 1
            assert (await void(client, aid)).status_code == 200
            assert (await client.get("/api/v1/dashboard/boss-todos", headers=auth(1))).json()["advances"] == {"count": 0, "items": []}
            assert (await client.get(BASE + "/my-debt", headers=auth(4))).json() == {"total_by_currency": [], "data": []}
            before = await all_money(factory)
            for action in ("approve", "reject"):
                response = await client.post(f"{BASE}/{aid}/{action}", headers=auth(1), json={"reject_reason": "测试"})
                assert response.status_code == 400 and response.json()["detail"] == "该预支已作废，不能审批"
            repeated = await void(client, aid)
            assert repeated.status_code == 400 and repeated.json()["detail"] == "该预支已作废"
            assert await all_money(factory) == before
    asyncio.run(run())


def test_voided_advance_does_not_enter_new_salary(tmp_path, monkeypatch):
    async def run():
        async with hr_environment(tmp_path, monkeypatch) as (_, factory, client):
            monkeypatch.setattr(payroll, "thai_today", lambda: date(2026, 10, 20))
            await prepare_work(factory)
            old = await snapshot(factory)
            created = await create(client)
            assert (await void(client, created["id"])).status_code == 200
            assert await snapshot(factory) == old
            await calculate(client, "2026-10-18")
            record = await period_record(factory)
            assert (record.base_pay, record.advance_deduction, record.net_pay) == (1200, 0, 1200)
            assert json.loads(record.detail)["advance_deductions"] == []
            print("VOIDED_ADVANCE_PAYROLL", {"base_pay": record.base_pay, "advance_deduction": record.advance_deduction, "net_pay": record.net_pay})
    asyncio.run(run())


@pytest.mark.parametrize("amount,expected", [(1000, "该预支已随工资结清 不能作废"), (2000, "该预支已随工资抵扣 不能作废")])
def test_real_full_and_partial_payroll_deductions_cannot_be_voided(tmp_path, monkeypatch, amount, expected):
    async def run():
        async with hr_environment(tmp_path, monkeypatch) as (_, factory, client):
            monkeypatch.setattr(payroll, "thai_today", lambda: date(2026, 10, 20))
            await prepare_work(factory)
            created = await create(client, amount=amount)
            await calculate(client, "2026-10-18")
            before = await all_money(factory)
            response = await void(client, created["id"])
            assert response.status_code == 400 and response.json()["detail"] == expected
            assert await all_money(factory) == before
            print("USED_ADVANCE_VOID_BLOCKED", {"advance": amount, "response": response.json()})
    asyncio.run(run())


@pytest.mark.parametrize("voided,aggregate", [(False, 100), (True, 100), (False, 0)])
def test_payroll_link_prevents_void_even_if_counter_is_inconsistent(tmp_path, monkeypatch, voided, aggregate):
    async def run():
        async with hr_environment(tmp_path, monkeypatch) as (_, factory, client):
            created = await create(client)
            async with factory() as db:
                db.add(PayrollRecord(warehouse_id=1, employee_id=1, period="2026-10", status="confirmed",
                    voided=voided, advance_deduction=aggregate, net_pay=1100,
                    detail=json.dumps({"advance_deductions": [{"advance_id": created["id"], "amount": 100}]})))
                await db.commit()
            before = await all_money(factory)
            response = await void(client, created["id"])
            assert response.status_code == 400 and response.json()["detail"] == "该预支已随工资抵扣 不能作废"
            assert await all_money(factory) == before
    asyncio.run(run())


@pytest.mark.parametrize("failure", ["expense_log", "void_log"])
def test_void_transaction_rolls_back_cost_and_metadata_on_failure(tmp_path, monkeypatch, failure):
    async def run():
        async with hr_environment(tmp_path, monkeypatch) as (_, factory, client):
            created = await create(client)
            before = await all_money(factory)
            async def broken(db, **kwargs):
                await db.flush()
                raise HTTPException(500, "模拟留痕失败")
            monkeypatch.setattr(expenses if failure == "expense_log" else api, "record_history", broken)
            response = await void(client, created["id"])
            assert response.status_code == 500
            assert await all_money(factory) == before
    asyncio.run(run())


def test_void_fund_advance_cleans_only_its_precisely_linked_item(tmp_path, monkeypatch):
    async def run():
        from datetime import datetime
        async with hr_environment(tmp_path, monkeypatch) as (_, factory, client):
            async with factory() as db:
                db.add(ExpenseFund(id=8, warehouse_id=1, employee_id=1, amount=5000, remaining_balance=5000,
                    currency="THB", receive_date=datetime(2026, 10, 1), purpose="测试"))
                await db.commit()
            created = await create(client, source="fund", fund_account_id=8)
            async with factory() as db:
                item_id = (await db.get(EmployeeAdvance, created["id"])).fund_item_id
            assert (await void(client, created["id"])).status_code == 200
            async with factory() as db:
                row = await db.get(EmployeeAdvance, created["id"])
                assert row and row.is_voided and row.fund_item_id is None
                assert await db.get(ExpenseFundItem, item_id) is None
                assert (await db.get(ExpenseFund, 8)).remaining_balance == 5000
    asyncio.run(run())


@pytest.mark.parametrize("linked_cost", [False, True])
def test_legacy_flag_does_not_orphan_a_known_cost_or_backfill_a_missing_one(tmp_path, monkeypatch, linked_cost):
    async def run():
        async with hr_environment(tmp_path, monkeypatch) as (_, factory, client):
            if linked_cost:
                created = await create(client)
                aid, eid = created["id"], created["expense_record_id"]
                async with factory() as db:
                    (await db.get(EmployeeAdvance, aid)).expense_tracking_enabled = False
                    await db.commit()
            else:
                aid, eid = await add(factory, status="approved", amount=1000), None
            response = await void(client, aid)
            assert response.status_code == 200, response.text
            async with factory() as db:
                assert (await db.get(EmployeeAdvance, aid)).is_voided
                assert (await db.execute(select(func.count()).select_from(ExpenseRecord))).scalar_one() == 0
                if eid is not None:
                    assert await db.get(ExpenseRecord, eid) is None
    asyncio.run(run())

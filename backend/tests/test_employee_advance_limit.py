"""预支工资额度：真实登记接口、待审占用、余额恢复、币种与原工资抵扣。"""
import asyncio
from datetime import date, datetime, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.models import Employee, SalaryTemplate
from app.models.employee_advance import EmployeeAdvance
from app.models.expense_fund import ExpenseFund, ExpenseFundItem
from app.models.income_expense import ExpenseRecord
from app.models.recharge import ExchangeRate
from app.services.employee_advance_limit import monthly_salary_standard
import app.api.v1.payroll as payroll
from tests.test_employee_advance_expense import BODY, supervisor_self
from tests.test_round2_permissions import auth
from tests.test_round3_permissions import hr_environment, snapshot
from tests.test_round18_advance_review import add, calculate, period_record, prepare_work

BASE = "/api/v1/employee-advances"


async def salary(factory, kind="monthly", amount=10000):
    async with factory() as db:
        template = await db.get(SalaryTemplate, 1)
        template.type, template.amount = kind, amount
        await db.commit()


async def create(client, amount, uid=1, **extra):
    return await client.post(BASE, headers=auth(uid), json={**BODY, "amount": amount, **extra})


async def advances_and_costs(factory):
    async with factory() as db:
        return [[tuple(r) for r in (await db.execute(select(model.__table__).order_by(model.id))).all()]
                for model in (EmployeeAdvance, ExpenseRecord, ExpenseFundItem)]


@pytest.mark.parametrize("kind,amount,expected", [
    ("monthly", 10000, "10000.00"), ("daily", 400, "10400.00"),
    ("hourly", 400, "10400.00"), ("hourly", 80, "2080.00"),
    ("daily", 0.1, "2.60"), ("monthly", 0, "0.00"),
])
def test_template_monthly_standard_uses_existing_hourly_storage(kind, amount, expected):
    assert monthly_salary_standard(SimpleNamespace(type=kind, amount=amount)) == Decimal(expected)


@pytest.mark.parametrize("template", [None, SimpleNamespace(type="unknown", amount=400),
    SimpleNamespace(type="daily", amount=float("nan")), SimpleNamespace(type="monthly", amount=-1)])
def test_uncalculable_template_warns_instead_of_guessing(template):
    assert monthly_salary_standard(template) is None


def test_requested_monthly_10000_workflow_and_pending_reservation(tmp_path, monkeypatch):
    async def run():
        async with hr_environment(tmp_path, monkeypatch) as (_, factory, client):
            await supervisor_self(factory)
            await salary(factory)
            old_payroll = await snapshot(factory)
            first = await create(client, 8000)
            assert first.status_code == 200, first.text
            assert first.json()["approval_status"] == "approved"
            assert first.json()["limit_check"] == {
                "checked": True, "currency": "THB", "monthly_salary": 10000,
                "occupied_amount": 0, "requested_amount": 8000,
                "available_amount": 10000, "remaining_amount": 2000,
            }
            before = await advances_and_costs(factory)
            exceeded = await create(client, 3000)
            assert exceeded.status_code == 400
            assert exceeded.json() == {"detail": "预支合计不能超过当月工资，当前可用 2000.00 元"}
            assert await advances_and_costs(factory) == before
            pending = await create(client, 1000, uid=4)
            assert pending.status_code == 200 and pending.json()["approval_status"] == "pending", pending.text
            assert pending.json()["limit_check"]["remaining_amount"] == 1000
            boundary = await create(client, 1000, uid=4)
            assert boundary.status_code == 200 and boundary.json()["approval_status"] == "pending", boundary.text
            assert boundary.json()["limit_check"]["remaining_amount"] == 0
            before = await advances_and_costs(factory)
            exhausted = await create(client, 0.01)
            assert exhausted.status_code == 400
            assert exhausted.json() == {"detail": "预支合计不能超过当月工资，当前可用 0.00 元"}
            assert await advances_and_costs(factory) == before
            # 核验结清后的额度；不新增作废或删除动作，不改生产历史。
            async with factory() as db:
                rows = (await db.execute(select(EmployeeAdvance))).scalars().all()
                for row in rows:
                    row.status, row.deducted_amount = "deducted", row.amount
                await db.commit()
            after_settled = await create(client, 1000)
            assert after_settled.status_code == 200, after_settled.text
            assert after_settled.json()["limit_check"]["occupied_amount"] == 0
            assert await snapshot(factory) == old_payroll
            print("ADVANCE_LIMIT_WORKFLOW", json.dumps({
                "first_8000": first.json(), "then_3000": exceeded.json(),
                "pending_1000": pending.json(), "exact_10000": boundary.json(),
                "above_10000": exhausted.json(), "after_settled": after_settled.json(),
            }, ensure_ascii=False))
    asyncio.run(run())


@pytest.mark.parametrize("approval,status,amount,deducted,requested", [
    ("approved", "partial", 10000, 6000, 6000),
    ("approved", "deducted", 10000, 10000, 10000),
    ("rejected", "unpaid", 10000, 0, 10000),
    ("pending", "unpaid", 4000, 500, 6000),  # 待审全额占用，不重复计入已通过余额。
    ("approved", None, 4000, 0, 6000),
])
def test_occupancy_uses_remaining_approved_and_full_pending(tmp_path, monkeypatch, approval, status, amount, deducted, requested):
    async def run():
        async with hr_environment(tmp_path, monkeypatch) as (_, factory, client):
            await salary(factory)
            aid = await add(factory, status=approval, amount=amount)
            async with factory() as db:
                row = await db.get(EmployeeAdvance, aid)
                row.status, row.deducted_amount = status, deducted
                row.advance_date, row.period = date(2025, 1, 1), "2025-01"
                await db.commit()
            response = await create(client, requested)
            assert response.status_code == 200, response.text
            assert response.json()["limit_check"]["remaining_amount"] == 0
            denied = await create(client, 0.01)
            assert denied.status_code == 400 and "当前可用 0.00 元" in denied.text
    asyncio.run(run())


def test_rejection_releases_pending_quota_without_altering_payroll(tmp_path, monkeypatch):
    async def run():
        async with hr_environment(tmp_path, monkeypatch) as (_, factory, client):
            await supervisor_self(factory)
            await salary(factory)
            old = await snapshot(factory)
            pending = await create(client, 10000, uid=4)
            assert pending.status_code == 200 and pending.json()["approval_status"] == "pending"
            assert (await create(client, 1)).status_code == 400
            denied = await client.post(f"{BASE}/{pending.json()['id']}/reject", headers=auth(1),
                json={"reject_reason": "额度释放核验"})
            assert denied.status_code == 200
            response = await create(client, 10000)
            assert response.status_code == 200 and response.json()["limit_check"]["occupied_amount"] == 0
            assert await snapshot(factory) == old
    asyncio.run(run())


def test_legacy_over_limit_is_not_rewritten_but_new_registration_is_blocked(tmp_path, monkeypatch):
    async def run():
        async with hr_environment(tmp_path, monkeypatch) as (_, factory, client):
            await salary(factory)
            await add(factory, status="approved", amount=20000)
            original = await advances_and_costs(factory)
            response = await create(client, 1)
            assert response.status_code == 400 and "当前可用 0.00 元" in response.text
            assert await advances_and_costs(factory) == original
    asyncio.run(run())


@pytest.mark.parametrize("kind", ["daily", "hourly"])
def test_daily_and_hourly_registration_limit_is_26_days(tmp_path, monkeypatch, kind):
    async def run():
        async with hr_environment(tmp_path, monkeypatch) as (_, factory, client):
            await salary(factory, kind, 400)
            response = await create(client, 10400)
            assert response.status_code == 200 and response.json()["limit_check"]["monthly_salary"] == 10400
            denied = await create(client, 0.01)
            assert denied.status_code == 400
    asyncio.run(run())


def test_no_template_warns_and_registration_still_succeeds(tmp_path, monkeypatch):
    async def run():
        async with hr_environment(tmp_path, monkeypatch) as (_, factory, client):
            async with factory() as db:
                (await db.get(Employee, 1)).salary_template_id = None
                await db.commit()
            old = await snapshot(factory)
            response = await create(client, 99999)
            assert response.status_code == 200, response.text
            assert response.json()["message"] == "预支记录已创建；该员工没有薪资模板 无法校验预支上限"
            assert response.json()["limit_check"] == {
                "checked": False, "currency": "THB", "warning": "该员工没有薪资模板 无法校验预支上限",
            }
            assert await snapshot(factory) == old
            print("ADVANCE_LIMIT_NO_TEMPLATE", json.dumps(response.json(), ensure_ascii=False))
    asyncio.run(run())


def test_warehouse_and_employee_scope_not_shared_quota(tmp_path, monkeypatch):
    async def run():
        async with hr_environment(tmp_path, monkeypatch) as (_, factory, client):
            await salary(factory)
            await add(factory, status="approved", amount=99999, wid=2, eid=2)
            await add(factory, status="approved", amount=99999, wid=2, eid=1)
            response = await create(client, 10000)
            assert response.status_code == 200 and response.json()["limit_check"]["occupied_amount"] == 0
            denied = await create(client, 1, employee_id=2)
            assert denied.status_code == 404
    asyncio.run(run())


async def cny_fund_and_rates(factory, *, rates=True, inverse=False):
    async with factory() as db:
        db.add(ExpenseFund(id=8, warehouse_id=1, employee_id=1, amount=10000, remaining_balance=10000,
            currency="CNY", receive_date=datetime(2026, 10, 1), purpose="额度校验"))
        if rates:
            db.add(ExchangeRate(warehouse_id=1, from_currency="THB" if inverse else "CNY",
                to_currency="CNY" if inverse else "THB", rate=0.2 if inverse else 5,
                effective_from=datetime(2026, 10, 1, tzinfo=timezone.utc)))
        await db.commit()


@pytest.mark.parametrize("inverse", [False, True])
def test_cny_and_thb_share_quota_at_each_registration_date_rate(tmp_path, monkeypatch, inverse):
    async def run():
        async with hr_environment(tmp_path, monkeypatch) as (_, factory, client):
            await salary(factory)
            await cny_fund_and_rates(factory, inverse=inverse)
            first = await create(client, 1000, source="fund", fund_account_id=8)
            assert first.status_code == 200 and first.json()["limit_check"]["requested_amount"] == 5000, first.text
            async with factory() as db:
                db.add_all([
                    ExchangeRate(warehouse_id=1, from_currency="CNY", to_currency="THB", rate=6,
                        effective_from=datetime(2026, 10, 17, tzinfo=timezone.utc)),
                    ExchangeRate(warehouse_id=1, from_currency="CNY", to_currency="THB", rate=999,
                        effective_from=datetime(2026, 11, 1, tzinfo=timezone.utc)),
                    ExchangeRate(warehouse_id=2, from_currency="CNY", to_currency="THB", rate=999,
                        effective_from=datetime(2026, 10, 15, tzinfo=timezone.utc)),
                ])
                await db.commit()
            second = await create(client, 2000)
            assert second.status_code == 200 and second.json()["limit_check"]["occupied_amount"] == 5000
            third = await create(client, 500, source="fund", fund_account_id=8, advance_date="2026-10-18")
            assert third.status_code == 200, third.text
            assert third.json()["limit_check"]["requested_amount"] == 3000
            assert third.json()["limit_check"]["remaining_amount"] == 0
            before = await advances_and_costs(factory)
            denied = await create(client, 1, source="fund", fund_account_id=8, advance_date="2026-10-18")
            assert denied.status_code == 400 and "当前可用 0.00 元" in denied.text and "CNY" in denied.text
            assert await advances_and_costs(factory) == before
    asyncio.run(run())


@pytest.mark.parametrize("existing_cny", [False, True])
def test_missing_exchange_rate_cannot_silently_bypass_limit(tmp_path, monkeypatch, existing_cny):
    async def run():
        async with hr_environment(tmp_path, monkeypatch) as (_, factory, client):
            await salary(factory)
            await cny_fund_and_rates(factory, rates=False)
            if existing_cny:
                aid = await add(factory, status="pending", amount=1000)
                async with factory() as db:
                    (await db.get(EmployeeAdvance, aid)).currency = "CNY"
                    await db.commit()
            before = await advances_and_costs(factory)
            response = (await create(client, 100) if existing_cny
                        else await create(client, 100, source="fund", fund_account_id=8))
            assert response.status_code == 400 and "请先设置汇率后再登记预支" in response.text
            assert await advances_and_costs(factory) == before
    asyncio.run(run())


def test_actual_payroll_settlement_restores_quota_without_formula_changes(tmp_path, monkeypatch):
    async def run():
        async with hr_environment(tmp_path, monkeypatch) as (_, factory, client):
            monkeypatch.setattr(payroll, "thai_today", lambda: date(2026, 10, 20))
            await prepare_work(factory)
            old = await snapshot(factory)
            response = await create(client, 1000)
            assert response.status_code == 200
            assert (await create(client, 10400)).status_code == 400
            await calculate(client, "2026-10-18")
            pay = await period_record(factory)
            assert (pay.base_pay, pay.advance_deduction, pay.net_pay) == (1200, 1000, 200)
            response = await create(client, 10400)
            assert response.status_code == 200 and response.json()["limit_check"]["occupied_amount"] == 0
            current = await snapshot(factory)
            assert [r for r in current if r[0] in {v[0] for v in old}] == old
            print("ADVANCE_LIMIT_PAYROLL", {"gross_pay": 1200, "deduction": 1000, "net_pay": 200,
                "settled_quota_released": 1000, "new_advance": 10400})
    asyncio.run(run())


@pytest.mark.skipif(not os.environ.get("PGLITE_NODE"), reason="Requires embedded PostgreSQL")
def test_postgres_fx_thai_date_boundary_and_mixed_pending_quota():
    async def run():
        from sqlalchemy.dialects.postgresql import dialect
        from sqlalchemy.schema import CreateTable
        from app.services.employee_advance_limit import check_advance_limit, _rate_to_thb
        from tests.test_round12_migration_postgres import PostgreSQLConnection

        process = await asyncio.create_subprocess_exec(os.environ["PGLITE_NODE"],
            str(Path(__file__).with_name("postgres_bridge.cjs")),
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE)
        conn = PostgreSQLConnection(process)

        class DB:
            async def execute(self, statement):
                rows = await conn.execute(str(statement.compile(dialect=dialect(), compile_kwargs={"literal_binds": True})))
                values = []
                for row in rows:
                    if isinstance(row.get("advance_date"), str):
                        row["advance_date"] = date.fromisoformat(row["advance_date"][:10])
                    values.append(SimpleNamespace(**row))
                return SimpleNamespace(scalar_one_or_none=lambda: values[0] if values else None,
                    scalars=lambda: SimpleNamespace(all=lambda: values))

        try:
            for model in (SalaryTemplate, EmployeeAdvance, ExchangeRate):
                await conn.execute(str(CreateTable(model.__table__, include_foreign_key_constraints=[]).compile(dialect=dialect())))
            await conn.execute("""INSERT INTO salary_templates(id,warehouse_id,name,type,amount)
                VALUES(1,1,'月薪一万','monthly',10000)""")
            await conn.execute("""INSERT INTO exchange_rates(id,warehouse_id,from_currency,to_currency,rate,effective_from) VALUES
                (1,1,'CNY','THB',5,'2026-10-16 16:59:59+00'),
                (2,1,'CNY','THB',6,'2026-10-16 17:00:00+00'),
                (3,2,'CNY','THB',999,'2026-10-16 16:59:59+00')""")
            db = DB()
            assert await _rate_to_thb(db, 1, "CNY", date(2026, 10, 16)) == 5
            assert await _rate_to_thb(db, 1, "CNY", date(2026, 10, 17)) == 6
            await conn.execute("""INSERT INTO employee_advances(id,warehouse_id,employee_id,amount,currency,advance_date,period,half,source,status,approval_status) VALUES
                (1,1,1,1000,'CNY','2026-10-16','2026-10','second_half','fund','unpaid','approved'),
                (2,1,1,2000,'THB','2026-10-16','2026-10','second_half','supervisor','unpaid','pending')""")
            result = await check_advance_limit(db, SimpleNamespace(id=1, warehouse_id=1, salary_template_id=1),
                500, "CNY", date(2026, 10, 17))
            assert (result["occupied_amount"], result["requested_amount"], result["remaining_amount"]) == (7000, 3000, 0)
        finally:
            process.stdin.close()
            await process.wait()
    asyncio.run(run())

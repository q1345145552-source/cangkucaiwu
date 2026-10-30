"""Exercise the real payroll preparation with the existing isolated SQLite fixture."""
import asyncio
from datetime import date

import pytest

from app.api.v1 import payroll
from app.models import User, RestDay
from app.models.employee import EmployeeRestDate
from tests.test_round3_permissions import hr_environment


@pytest.mark.parametrize("case,expected", [
    ("active_new_date", {date(2026, 10, 10)}),
    ("cancelled_new_date", set()),
    ("legacy_only_date", set()),
    ("other_employee_date", set()),
])
def test_payroll_rest_source(tmp_path, monkeypatch, case, expected):
    async def run():
        monkeypatch.setattr(payroll, "thai_today", lambda: date(2026, 11, 2))
        async with hr_environment(tmp_path, monkeypatch) as (_, factory, _client):
            async with factory() as db:
                if case == "legacy_only_date":
                    db.add(RestDay(employee_id=1, warehouse_id=1, rest_date=date(2026, 10, 10)))
                else:
                    other = case == "other_employee_date"
                    db.add(EmployeeRestDate(employee_id=2 if other else 1,
                        warehouse_id=2 if other else 1, rest_date=date(2026, 10, 10),
                        is_rest=case != "cancelled_new_date", source="manual"))
                await db.commit()
                user = await db.get(User, 3)
                prep = await payroll._prepare_payroll(db, user, 1, payroll.CalculateRequest(
                    end_date="2026-10-31", recalc_employee_id=1, recalc_start_date="2026-10-01"))
                assert prep.get("early_return") is None, prep
                actual = prep["rest_by_emp"]
                assert actual == ({1: expected} if expected else {})
                print(f"{case}: rest_by_emp={actual}")
    asyncio.run(run())

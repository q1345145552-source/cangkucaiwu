"""Full-month fixtures, using only the isolated test database."""
from datetime import date, datetime
from sqlalchemy import select
from app.api.v1 import payroll
from app.services import monthly_payroll
from app.models import Employee, SalaryTemplate, ClockInRecord
from app.models.payroll import PayrollRecord
from app.core.timezone import THAI_TZ

async def complete_month(db, monkeypatch, target, end="18:00", amount=12400, mode="actual"):
    monkeypatch.setattr(payroll, "thai_today", lambda: date(2026, 11, 2))
    now = lambda: datetime(2026, 11, 2, 12, tzinfo=THAI_TZ)
    monkeypatch.setattr(payroll, "thai_now", now)
    monkeypatch.setattr(monthly_payroll, "thai_now", now)
    (await db.get(Employee, 1)).hire_date = datetime(2026, 10, 1)
    template = await db.get(SalaryTemplate, 1)
    template.type, template.amount = "monthly", amount
    template.monthly_deduction_mode, template.monthly_fixed_days = mode, 30
    # Preserve previous payroll rows; place historical fixtures before this month.
    for row in (await db.execute(select(PayrollRecord).where(PayrollRecord.employee_id == 1))).scalars():
        row.period = "2026-09"
        row.settle_start_date, row.settle_end_date = date(2026, 9, 1), date(2026, 9, 30)
    for day in range(1, 32):
        if day == target.day:continue
        for session, clock in enumerate(("09:00", "12:00", "13:00", end), 1):
            db.add(ClockInRecord(user_id=5, warehouse_id=1, clock_date=date(2026, 10, day),
                session=session, clocked_in_at=datetime.fromisoformat(f"2026-10-{day:02d}T{clock}"), status="normal"))

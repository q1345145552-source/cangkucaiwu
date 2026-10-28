from app.services.attendance_exemptions import valid_clock
"""Approved full-day leave guards shared by clock-in, calendar and payroll."""
from sqlalchemy import select, or_

from app.core.permissions import get_wh_id
from app.models.attendance import LeaveRequest
from app.models.clock_in_records import ClockInRecord
from app.models.employee import Employee
from app.services.employee_match import resolve_employee_user_map

CLOCK_WARNING = "该员工当天已有打卡记录 请确认是否需要处理"


def full_day_net_hours(info, clock_hours):
    return 0.0 if info and info.get("full") else clock_hours


async def approved_full_day_today(db, user, work_date):
    wh_id = get_wh_id(user)
    employees = (await db.execute(select(Employee).where(
        Employee.warehouse_id == wh_id, Employee.is_deleted == False,
    ))).scalars().all()
    _, user_to_emp = await resolve_employee_user_map(db, employees)
    employee_id = user_to_emp.get(user.id)
    if employee_id is None:
        return False
    return (await db.execute(select(LeaveRequest.id).where(
        LeaveRequest.warehouse_id == wh_id,
        LeaveRequest.employee_id == employee_id,
        LeaveRequest.leave_date == work_date,
        LeaveRequest.status == "approved",
        or_(LeaveRequest.duration_type.in_(("full", "")), LeaveRequest.duration_type.is_(None)),
    ).limit(1))).scalar_one_or_none() is not None


async def full_day_clock_warning(db, employee, start_date, end_date):
    """Report existing punches without changing them or the leave decision."""
    emp_to_user, _ = await resolve_employee_user_map(db, [employee])
    user_id = emp_to_user.get(employee.id)
    if user_id is None:
        return {}
    dates = (await db.execute(select(ClockInRecord.clock_date).where(valid_clock(),
        ClockInRecord.warehouse_id == employee.warehouse_id,
        ClockInRecord.user_id == user_id,
        ClockInRecord.clock_date >= start_date,
        ClockInRecord.clock_date <= end_date,
    ).distinct().order_by(ClockInRecord.clock_date))).scalars().all()
    return {"warning": CLOCK_WARNING, "clocked_dates": [d.isoformat() for d in dates]} if dates else {}

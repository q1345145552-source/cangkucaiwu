from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from app.database import get_db
from app.models.payroll import PayrollRecord
from app.models.employee import Employee
from app.models.clock_in_records import ClockInRecord
from app.models.attendance import LeaveRequest, RestDay, Absence
from app.models.overtime import OvertimeAssignment, OvertimeTask
from app.models.user import User
from app.core.permissions import get_current_user, get_wh_id, get_wh_ids, Role
from pydantic import BaseModel
from app.core.timezone import thai_now, thai_today
from datetime import datetime, date, timedelta
from typing import Optional, List
import calendar
import json

router = APIRouter()


class CalculateRequest(BaseModel):
    period: str  # YYYY-MM


@router.post("/calculate")
async def calculate_payroll(
    req: CalculateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in (Role.WAREHOUSE_ADMIN,):
        raise HTTPException(403, "只有仓库管理员可以计算工资")

    wh_id = get_wh_id(current_user)
    if not wh_id:
        raise HTTPException(400, "请先选择仓库")

    try:
        y, m = req.period.split("-")
        year, month = int(y), int(m)
    except:
        raise HTTPException(400, "月份格式错误，应为 YYYY-MM")

    if month < 1 or month > 12:
        raise HTTPException(400, "月份无效")

    # Check if payroll already calculated
    existing = (await db.execute(
        select(PayrollRecord).where(
            PayrollRecord.warehouse_id == wh_id,
            PayrollRecord.period == req.period,
        )
    )).scalars().all()
    if existing:
        raise HTTPException(400, f"{req.period} 的工资已计算过，请先删除旧记录再重新计算")

    # Get all active employees with user_id links
    employees = (await db.execute(
        select(Employee).where(
            Employee.warehouse_id == wh_id,
            Employee.status != "resigned",
        )
    )).scalars().all()

    if not employees:
        return {"message": "该仓库没有在职员工", "records": []}

    # Month boundaries
    month_start = date(year, month, 1)
    _, total_days = calendar.monthrange(year, month)
    month_end = date(year, month, total_days)

    # Build employee_id -> user_id mapping (via the formal link)
    emp_user_map = {}  # employee_id -> user_id
    user_emp_map = {}  # user_id -> employee_id
    emp_id_set = {e.id for e in employees}

    for e in employees:
        if e.user_id:
            emp_user_map[e.id] = e.user_id
            user_emp_map[e.user_id] = e.id

    # Fallback: name matching for employees without user_id link (warehouse-scoped)
    emp_names = {e.name: e.id for e in employees if e.id not in emp_user_map}
    if emp_names:
        labor_users = (await db.execute(
            select(User).where(
                User.role == "warehouse_labor",
                User.is_active == True,
                User.warehouse_id == wh_id,
            )
        )).scalars().all()
        for u in labor_users:
            if u.display_name in emp_names:
                eid = emp_names[u.display_name]
                emp_user_map[eid] = u.id
                user_emp_map[u.id] = eid

    all_user_ids = list(user_emp_map.keys())

    # Batch fetch all clock-in records for this month
    clock_records = []
    if all_user_ids:
        clock_records = (await db.execute(
            select(ClockInRecord).where(
                ClockInRecord.clock_date >= month_start,
                ClockInRecord.clock_date <= month_end,
                ClockInRecord.user_id.in_(all_user_ids),
            ).order_by(ClockInRecord.clock_date, ClockInRecord.session)
        )).scalars().all()

    # Group clock-ins by (employee_id, date)
    clock_by_emp_date = {}
    for cr in clock_records:
        eid = user_emp_map.get(cr.user_id)
        if not eid:
            continue
        key = (eid, cr.clock_date)
        if key not in clock_by_emp_date:
            clock_by_emp_date[key] = []
        clock_by_emp_date[key].append(cr)

    # Batch fetch leave/rest/absence
    leaves = (await db.execute(
        select(LeaveRequest).where(
            LeaveRequest.employee_id.in_(emp_id_set),
            LeaveRequest.leave_date >= month_start,
            LeaveRequest.leave_date <= month_end,
            LeaveRequest.status == "approved",
        )
    )).scalars().all()
    leave_by_emp = {}
    for lv in leaves:
        if lv.employee_id not in leave_by_emp:
            leave_by_emp[lv.employee_id] = set()
        leave_by_emp[lv.employee_id].add(lv.leave_date)

    rests = (await db.execute(
        select(RestDay).where(
            RestDay.employee_id.in_(emp_id_set),
            RestDay.rest_date >= month_start,
            RestDay.rest_date <= month_end,
        )
    )).scalars().all()
    rest_by_emp = {}
    for r in rests:
        if r.employee_id not in rest_by_emp:
            rest_by_emp[r.employee_id] = set()
        rest_by_emp[r.employee_id].add(r.rest_date)

    absences = (await db.execute(
        select(Absence).where(
            Absence.employee_id.in_(emp_id_set),
            Absence.absence_date >= month_start,
            Absence.absence_date <= month_end,
        )
    )).scalars().all()
    absence_by_emp = {}
    for a in absences:
        if a.employee_id not in absence_by_emp:
            absence_by_emp[a.employee_id] = set()
        absence_by_emp[a.employee_id].add(a.absence_date)

    # Batch fetch overtime earnings
    overtime_query = (
        select(
            OvertimeAssignment.employee_id,
            func.sum(OvertimeAssignment.earned_amount).label("total"),
            func.sum(OvertimeTask.hours).label("hours"),
        )
        .join(OvertimeTask, OvertimeTask.id == OvertimeAssignment.overtime_id)
        .where(
            OvertimeAssignment.employee_id.in_(emp_id_set),
            OvertimeAssignment.confirmed == True,
            OvertimeTask.date >= month_start,
            OvertimeTask.date <= month_end,
        )
        .group_by(OvertimeAssignment.employee_id)
    )
    overtime_rows = (await db.execute(overtime_query)).all()
    overtime_map = {r.employee_id: {"amount": r.total or 0, "hours": r.hours or 0} for r in overtime_rows}

    # Now calculate for each employee
    records = []
    for emp in employees:
        attendance_days = 0
        absence_days_count = 0
        late_half_count = 0  # 迟到半小时次数
        late_one_count = 0   # 迟到1小时次数
        leave_days_count = 0
        rest_days_count = 0

        # Iterate each day in the month
        current = month_start
        while current <= month_end:
            leave_set = leave_by_emp.get(emp.id, set())
            rest_set = rest_by_emp.get(emp.id, set())
            absence_set = absence_by_emp.get(emp.id, set())

            if current in rest_set:
                rest_days_count += 1
            elif current in leave_set:
                leave_days_count += 1
            elif current in absence_set:
                absence_days_count += 1
            else:
                # Check clock-in records
                key = (emp.id, current)
                sessions = clock_by_emp_date.get(key, [])
                session_count = len({c.session for c in sessions})

                if session_count >= 3:
                    # 3 or 4 sessions = full attendance
                    attendance_days += 1
                    # Count late penalties (session 1 only)
                    for cr in sessions:
                        if cr.session == 1:
                            if cr.status == "late_half":
                                late_half_count += 1
                            elif cr.status == "late_one":
                                late_one_count += 1
                elif session_count >= 1:
                    # 1 or 2 sessions = absence (不算出勤，算缺勤)
                    absence_days_count += 1
                # 0 sessions = neither attendance nor absence (just missing, no record)

            current += timedelta(days=1)

        # Calculate daily wage and hourly rate
        emp_status = emp.status or "trial"
        daily_wage = emp.daily_wage or 400
        base_salary = emp.base_salary or 12000

        if emp_status == "trial":
            hourly_rate = daily_wage / 8  # 日薪÷8
            effective_daily = daily_wage
            base_pay = daily_wage * attendance_days
        else:  # regular
            adjusted_days = total_days - 2
            if adjusted_days <= 0:
                adjusted_days = total_days
            effective_daily = base_salary / adjusted_days  # 日薪
            hourly_rate = effective_daily / 8  # 时薪
            base_pay = round(effective_daily * attendance_days, 2)

        # Late penalty: half hour = hourly_rate * 0.5, one hour = hourly_rate
        late_penalty_total = round(
            late_half_count * hourly_rate * 0.5 +
            late_one_count * hourly_rate,
            2
        )

        # Leave/Absence deductions
        leave_deduction = round(effective_daily * leave_days_count, 2)
        absence_deduction = round(effective_daily * absence_days_count, 2)

        # Overtime
        ot = overtime_map.get(emp.id, {})
        overtime_pay = ot.get("amount", 0)
        overtime_hours = ot.get("hours", 0)

        # Gross & net
        total_deductions = late_penalty_total + leave_deduction + absence_deduction
        gross_pay = base_pay + overtime_pay
        net_pay = round(gross_pay - total_deductions, 2)

        detail_data = {
            "attendance_days": attendance_days,
            "leave_days": leave_days_count,
            "rest_days": rest_days_count,
            "absence_days": absence_days_count,
            "late_half_count": late_half_count,
            "late_one_count": late_one_count,
            "hourly_rate": round(hourly_rate, 2),
            "effective_daily": round(effective_daily, 2),
            "late_penalty": late_penalty_total,
            "leave_deduction": leave_deduction,
            "absence_deduction": absence_deduction,
            "overtime_hours": overtime_hours,
            "overtime_pay": overtime_pay,
        }

        record = PayrollRecord(
            warehouse_id=wh_id,
            employee_id=emp.id,
            period=req.period,
            status="pending",
            total_days_in_month=total_days,
            attendance_days=attendance_days,
            leave_days=leave_days_count,
            rest_days=rest_days_count,
            absence_days=absence_days_count,
            employee_status=emp_status,
            daily_wage=daily_wage,
            base_salary=base_salary,
            base_pay=round(base_pay, 2),
            overtime_pay=round(overtime_pay, 2),
            overtime_hours=round(overtime_hours, 1),
            late_penalty=round(late_penalty_total, 2),
            leave_deduction=round(leave_deduction, 2),
            absence_deduction=round(absence_deduction, 2),
            gross_pay=round(gross_pay, 2),
            total_deductions=round(total_deductions, 2),
            net_pay=net_pay,
            detail=json.dumps(detail_data, ensure_ascii=False),
        )
        db.add(record)
        records.append(record)

    await db.flush()
    return {
        "message": f"已为 {len(records)} 名员工计算 {req.period} 工资",
        "period": req.period,
        "record_count": len(records),
    }

@router.get("")
async def list_payroll(
    period: str = None,
    status: str = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    wh_ids = get_wh_ids(current_user)
    query = select(PayrollRecord).where(PayrollRecord.warehouse_id.in_(wh_ids))
    count_q = select(func.count(PayrollRecord.id)).where(PayrollRecord.warehouse_id.in_(wh_ids))

    if period:
        query = query.where(PayrollRecord.period == period)
        count_q = count_q.where(PayrollRecord.period == period)
    if status:
        query = query.where(PayrollRecord.status == status)
        count_q = count_q.where(PayrollRecord.status == status)

    result = await db.execute(
        query.order_by(PayrollRecord.employee_id, PayrollRecord.period.desc())
    )
    records = result.scalars().all()

    # Get employee names
    emp_ids = {r.employee_id for r in records}
    emp_map = {}
    if emp_ids:
        emps = (await db.execute(select(Employee).where(Employee.id.in_(emp_ids)))).scalars().all()
        emp_map = {e.id: e for e in emps}

    return {
        "data": [{
            "id": r.id,
            "employee_id": r.employee_id,
            "disbursed": r.disbursed,
            "disbursed_at": r.disbursed_at.isoformat() if r.disbursed_at else None,
            "employee_name": emp_map.get(r.employee_id).name if emp_map.get(r.employee_id) else "",
            "employee_status": r.employee_status,
            "period": r.period,
            "status": r.status,
            "total_days_in_month": r.total_days_in_month,
            "attendance_days": r.attendance_days,
            "leave_days": r.leave_days,
            "rest_days": r.rest_days,
            "absence_days": r.absence_days,
            "daily_wage": r.daily_wage,
            "base_salary": r.base_salary,
            "base_pay": r.base_pay,
            "overtime_pay": r.overtime_pay,
            "overtime_hours": r.overtime_hours,
            "late_penalty": r.late_penalty,
            "leave_deduction": r.leave_deduction,
            "absence_deduction": r.absence_deduction,
            "gross_pay": r.gross_pay,
            "total_deductions": r.total_deductions,
            "net_pay": r.net_pay,
            "detail": json.loads(r.detail) if r.detail else {},
            "confirmed_at": r.confirmed_at.isoformat() if r.confirmed_at else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        } for r in records],
        "periods": await _get_available_periods(db, wh_ids),
    }


@router.get("/summary")
async def payroll_summary(
    period: str = Query(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    wh_ids = get_wh_ids(current_user)
    records = (await db.execute(
        select(PayrollRecord).where(
            PayrollRecord.warehouse_id.in_(wh_ids),
            PayrollRecord.period == period,
        )
    )).scalars().all()

    confirmed = sum(1 for r in records if r.status == "confirmed")
    total_net = sum(r.net_pay for r in records)
    total_gross = sum(r.gross_pay for r in records)
    total_ot = sum(r.overtime_pay for r in records)
    total_penalties = sum(r.late_penalty for r in records)

    return {
        "period": period,
        "employee_count": len(records),
        "confirmed_count": confirmed,
        "pending_count": len(records) - confirmed,
        "total_gross": round(total_gross, 2),
        "total_overtime": round(total_ot, 2),
        "total_penalties": round(total_penalties, 2),
        "total_net": round(total_net, 2),
    }


@router.post("/{record_id}/confirm")
async def confirm_payroll(
    record_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in (Role.WAREHOUSE_ADMIN,):
        raise HTTPException(403, "只有仓库管理员可以确认工资")

    wh_ids = get_wh_ids(current_user)
    r = (await db.execute(
        select(PayrollRecord).where(
            PayrollRecord.id == record_id,
            PayrollRecord.warehouse_id.in_(wh_ids),
        )
    )).scalar_one_or_none()
    if not r:
        raise HTTPException(404, "工资记录不存在")
    if r.status == "confirmed":
        raise HTTPException(400, "该工资单已确认")

    r.status = "confirmed"
    r.confirmed_by = current_user.id
    r.confirmed_at = thai_now()
    await db.flush()
    return {"message": "工资单已确认", "id": r.id, "net_pay": r.net_pay}


@router.post("/confirm-all")
async def confirm_all_payroll(
    period: str = Query(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in (Role.WAREHOUSE_ADMIN,):
        raise HTTPException(403, "只有仓库管理员可以确认工资")

    wh_ids = get_wh_ids(current_user)
    records = (await db.execute(
        select(PayrollRecord).where(
            PayrollRecord.warehouse_id.in_(wh_ids),
            PayrollRecord.period == period,
            PayrollRecord.status == "pending",
        )
    )).scalars().all()

    if not records:
        raise HTTPException(404, f"{period} 没有待确认的工资单")

    now = thai_now()
    total_net = 0
    for r in records:
        r.status = "confirmed"
        r.confirmed_by = current_user.id
        r.confirmed_at = now
        total_net += r.net_pay

    await db.flush()
    return {
        "message": f"已确认 {len(records)} 份工资单",
        "count": len(records),
        "total_net": round(total_net, 2),
    }


@router.delete("/{record_id}")
async def delete_payroll(
    record_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in (Role.WAREHOUSE_ADMIN,):
        raise HTTPException(403, "只有仓库管理员可以删除工资记录")

    wh_ids = get_wh_ids(current_user)
    r = (await db.execute(
        select(PayrollRecord).where(
            PayrollRecord.id == record_id,
            PayrollRecord.warehouse_id.in_(wh_ids),
        )
    )).scalar_one_or_none()
    if not r:
        raise HTTPException(404, "工资记录不存在")

    await db.delete(r)
    await db.flush()
    return {"message": "工资记录已删除"}


@router.delete("/period/{period}")
async def delete_period_payroll(
    period: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete all payroll records for a period (to allow recalculation)"""
    if current_user.role not in (Role.WAREHOUSE_ADMIN,):
        raise HTTPException(403, "只有仓库管理员可以操作")

    wh_ids = get_wh_ids(current_user)
    records = (await db.execute(
        select(PayrollRecord).where(
            PayrollRecord.warehouse_id.in_(wh_ids),
            PayrollRecord.period == period,
        )
    )).scalars().all()

    for r in records:
        await db.delete(r)
    await db.flush()

    return {"message": f"已删除 {period} 的 {len(records)} 条工资记录"}


# ═══ Disbursement ════════════════════════════

class DisburseRequest(BaseModel):
    signature_base64: Optional[str] = None  # 签字照片 base64


@router.post("/{record_id}/disburse")
async def disburse_payroll(
    record_id: int,
    req: DisburseRequest = DisburseRequest(),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in (Role.WAREHOUSE_ADMIN,):
        raise HTTPException(403, "只有仓库管理员可以发放工资")

    wh_ids = get_wh_ids(current_user)
    r = (await db.execute(
        select(PayrollRecord).where(
            PayrollRecord.id == record_id,
            PayrollRecord.warehouse_id.in_(wh_ids),
        )
    )).scalar_one_or_none()
    if not r:
        raise HTTPException(404, "工资记录不存在")
    if r.status != "confirmed":
        raise HTTPException(400, "请先确认工资单再发放")
    if r.disbursed:
        raise HTTPException(400, "该工资单已发放")

    # Save signature if provided
    sig_path = None
    if req.signature_base64:
        try:
            import os, uuid, base64
            header, data = req.signature_base64.split(",", 1) if "," in req.signature_base64 else ("", req.signature_base64)
            img_bytes = base64.b64decode(data)
            wh_id_str = str(r.warehouse_id)
            subdir = os.path.join("/app/uploads", wh_id_str, r.period, "signatures")
            os.makedirs(subdir, exist_ok=True)
            fname = f"{uuid.uuid4().hex}.png"
            with open(os.path.join(subdir, fname), "wb") as f:
                f.write(img_bytes)
            sig_path = f"uploads/{wh_id_str}/{r.period}/signatures/{fname}"
        except Exception:
            pass

    r.disbursed = True
    r.disbursed_at = thai_now()
    r.disbursed_by = current_user.id
    r.signature_path = sig_path
    await db.flush()

    from app.models.employee import Employee
    emp = (await db.execute(select(Employee).where(Employee.id == r.employee_id))).scalar_one_or_none()
    emp_name = emp.name if emp else ""

    return {
        "message": f"已向 {emp_name} 发放 {r.net_pay:.0f} 泰铢工资",
        "id": r.id,
        "net_pay": r.net_pay,
        "disbursed_at": r.disbursed_at.isoformat(),
    }


# ═══ Employee Self-View Payslip ═══════════════

@router.get("/my-payslip")
async def my_payslip(
    period: str = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Employee views their own payslip. Matches by display_name to employee name."""
    if current_user.role not in (Role.WAREHOUSE_LABOR,):
        raise HTTPException(403, "无权限")

    wh_id = get_wh_id(current_user)
    if not wh_id:
        raise HTTPException(400, "请先选择仓库")

    from app.models.employee import Employee

    # Find employee record matching this user
    emp = (await db.execute(
        select(Employee).where(
            Employee.warehouse_id == wh_id,
            Employee.name == current_user.display_name,
        )
    )).scalar_one_or_none()
    if not emp:
        return {"data": [], "message": "未找到员工档案"}

    query = select(PayrollRecord).where(
        PayrollRecord.warehouse_id == wh_id,
        PayrollRecord.employee_id == emp.id,
    )
    if period:
        query = query.where(PayrollRecord.period == period)

    result = await db.execute(query.order_by(PayrollRecord.period.desc()))
    records = result.scalars().all()

    return {
        "data": [{
            "id": r.id,
            "period": r.period,
            "status": r.status,
            "disbursed": r.disbursed,
            "disbursed_at": r.disbursed_at.isoformat() if r.disbursed_at else None,
            "employee_name": emp.name,
            "employee_status": r.employee_status,
            "total_days_in_month": r.total_days_in_month,
            "attendance_days": r.attendance_days,
            "leave_days": r.leave_days,
            "rest_days": r.rest_days,
            "absence_days": r.absence_days,
            "daily_wage": r.daily_wage,
            "base_salary": r.base_salary,
            "base_pay": r.base_pay,
            "overtime_pay": r.overtime_pay,
            "overtime_hours": r.overtime_hours,
            "late_penalty": r.late_penalty,
            "leave_deduction": r.leave_deduction,
            "absence_deduction": r.absence_deduction,
            "gross_pay": r.gross_pay,
            "total_deductions": r.total_deductions,
            "net_pay": r.net_pay,
            "detail": json.loads(r.detail) if r.detail else {},
            "created_at": r.created_at.isoformat() if r.created_at else None,
        } for r in records],
    }


async def _get_available_periods(db: AsyncSession, wh_ids: list) -> list:
    result = await db.execute(
        select(PayrollRecord.period)
        .where(PayrollRecord.warehouse_id.in_(wh_ids))
        .distinct()
        .order_by(PayrollRecord.period.desc())
    )
    return [r[0] for r in result.all()]

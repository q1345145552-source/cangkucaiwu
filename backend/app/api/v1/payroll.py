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
from app.core.timezone import thai_now, thai_today, THAI_TZ
from app.services.payroll_calc import compute_pay, late_penalty as _late_penalty
from datetime import datetime, date, timedelta, time
from typing import Optional, List
import calendar
import json

router = APIRouter()


class CalculateRequest(BaseModel):
    period: str  # YYYY-MM
    half: str = "first_half"  # first_half / second_half
    employee_ids: Optional[List[int]] = None  # 单人结算时指定
    end_date: Optional[str] = None  # 结算截止日 YYYY-MM-DD（单人/离职结算用）


class SingleSettleRequest(BaseModel):
    employee_id: int
    end_date: str  # YYYY-MM-DD


@router.post("/calculate")
async def calculate_payroll(
    req: CalculateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
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

    # 结算截止日：单人/离职结算用 end_date，正常周期用周期结束日
    _, total_days = calendar.monthrange(year, month)
    if req.end_date:
        try:
            settle_end = datetime.strptime(req.end_date, "%Y-%m-%d").date()
        except:
            raise HTTPException(400, "截止日期格式错误，应为 YYYY-MM-DD")
        if settle_end.year != year or settle_end.month != month:
            raise HTTPException(400, "截止日期必须在本周期内")
        period_end = settle_end
    elif req.half == "first_half":
        period_end = date(year, month, 15)
        settle_end = period_end
    else:
        period_end = date(year, month, total_days)
        settle_end = period_end

    # 周期开始日：上半月 1 号，下半月 16 号
    if req.half == "first_half":
        period_start = date(year, month, 1)
    else:
        period_start = date(year, month, 16)

    # 已计算过的员工（同周期同半月）：跳过，不再整单拦截
    existing = (await db.execute(
        select(PayrollRecord).where(
            PayrollRecord.warehouse_id == wh_id,
            PayrollRecord.period == req.period,
            PayrollRecord.half == req.half,
        )
    )).scalars().all()
    already_calc_emp_ids = {r.employee_id for r in existing}

    # 在职员工（排除已删除），单人结算时可限定
    emp_q = select(Employee).where(
        Employee.warehouse_id == wh_id,
        Employee.status != "resigned",
        Employee.is_deleted == False,
    )
    if req.employee_ids:
        emp_q = emp_q.where(Employee.id.in_(req.employee_ids))
    employees = (await db.execute(emp_q)).scalars().all()

    if not employees:
        return {"message": "该仓库没有可结算的在职员工", "records": [], "skipped": []}

    # 已离职但本期有结算记录 → 跳过并说明
    skipped_notes = []
    resigned_settled = (await db.execute(
        select(PayrollRecord.employee_id, Employee.name)
        .join(Employee, Employee.id == PayrollRecord.employee_id)
        .where(
            PayrollRecord.warehouse_id == wh_id,
            PayrollRecord.period == req.period,
            PayrollRecord.half == req.half,
            Employee.status == "resigned",
        )
    )).all()
    for eid, ename in resigned_settled:
        skipped_notes.append(f"{ename} 已离职结算，跳过")

    month_start = date(year, month, 1)
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

    # Batch fetch all clock-in records for this half-month period
    clock_records = []
    if all_user_ids:
        clock_records = (await db.execute(
            select(ClockInRecord).where(
                ClockInRecord.clock_date >= period_start,
                ClockInRecord.clock_date <= period_end,
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

    # Batch fetch leave/rest/absence for this half-month
    leaves = (await db.execute(
        select(LeaveRequest).where(
            LeaveRequest.employee_id.in_(emp_id_set),
            LeaveRequest.leave_date >= period_start,
            LeaveRequest.leave_date <= period_end,
            LeaveRequest.status == "approved",
        )
    )).scalars().all()
    leave_by_emp = {}  # emp_id -> {date: duration_type}
    for lv in leaves:
        if lv.employee_id not in leave_by_emp:
            leave_by_emp[lv.employee_id] = {}
        leave_by_emp[lv.employee_id][lv.leave_date] = lv.duration_type or "full"

    rests = (await db.execute(
        select(RestDay).where(
            RestDay.employee_id.in_(emp_id_set),
            RestDay.rest_date >= period_start,
            RestDay.rest_date <= period_end,
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
            Absence.absence_date >= period_start,
            Absence.absence_date <= period_end,
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
            OvertimeTask.date >= period_start,
            OvertimeTask.date <= period_end,
        )
        .group_by(OvertimeAssignment.employee_id)
    )
    overtime_rows = (await db.execute(overtime_query)).all()
    overtime_map = {r.employee_id: {"amount": r.total or 0, "hours": r.hours or 0} for r in overtime_rows}

    # ── 算工资前检查待补（打卡 1 次或 3 次的天） ──
    SESSION_CN = {1: "早上上班", 2: "中午休息结束", 3: "下午上班", 4: "下午下班"}

    def _local_time_of(dt):
        if dt is None:
            return None
        if getattr(dt, "tzinfo", None) is not None:
            return dt.astimezone(THAI_TZ).time()
        return dt.time()

    def _day_hours(sessions_sorted):
        n = len(sessions_sorted)
        times = [c.clocked_in_at for c in sessions_sorted]
        if n == 2:
            if times[0] is None or times[1] is None:
                return 0.0
            h = (times[1] - times[0]).total_seconds() / 3600.0
            t0 = _local_time_of(times[0])
            if t0 is not None and t0 < time(12, 0):
                h -= 1.0
            return max(h, 0.0)
        if n == 4:
            def _seg(a, b):
                if a is None or b is None:
                    return 0.0
                return max((b - a).total_seconds() / 3600.0, 0.0)
            return _seg(times[0], times[1]) + _seg(times[2], times[3])
        return 0.0

    pending_days = []
    for emp in employees:
        rest_set = rest_by_emp.get(emp.id, set())
        absence_set = absence_by_emp.get(emp.id, set())
        leave_map = leave_by_emp.get(emp.id, {})
        current = period_start
        while current <= period_end:
            if current in rest_set or current in absence_set:
                current += timedelta(days=1)
                continue
            lt = leave_map.get(current, None)
            if lt == "full":
                current += timedelta(days=1)
                continue
            sessions = clock_by_emp_date.get((emp.id, current), [])
            n = len({c.session for c in sessions})
            if n in (1, 3):
                have = {c.session for c in sessions}
                missing = [SESSION_CN[s] for s in (1, 2, 3, 4) if s not in have]
                pending_days.append({"employee": emp.name, "date": current.isoformat(), "missing": missing})
            current += timedelta(days=1)

    if pending_days:
        lines = [f"{p['employee']} {p['date']}（缺 {'、'.join(p['missing'])}）" for p in pending_days[:30]]
        more = f" 等共 {len(pending_days)} 天" if len(pending_days) > 30 else ""
        detail = f"本周期有 {len(pending_days)} 天打卡不完整，无法计算，请先补卡再计算：\n" + "\n".join(lines) + more
        raise HTTPException(400, detail=detail)

    # ── 按工时计算 ──
    records = []
    for emp in employees:
        if emp.id in already_calc_emp_ids:
            continue  # 本期已算过，跳过
        emp_status = emp.status or "trial"
        daily_wage = emp.daily_wage or 400
        base_salary = emp.base_salary or 12000
        promotion_date = getattr(emp, 'promotion_date', None)
        has_promotion_this_month = bool(
            promotion_date and promotion_date.year == year and promotion_date.month == month
        )
        promotion_day = promotion_date.day if has_promotion_this_month else 0

        adjusted_days = total_days - 2
        if adjusted_days <= 0:
            adjusted_days = total_days
        trial_hourly = daily_wage / 8.0
        regular_daily = base_salary / adjusted_days
        regular_hourly = regular_daily / 8.0

        trial_hours = 0.0
        regular_hours = 0.0
        late_half_count = 0
        late_one_count = 0
        rest_days_count = 0
        leave_days_count = 0
        absence_days_count = 0

        rest_set = rest_by_emp.get(emp.id, set())
        absence_set = absence_by_emp.get(emp.id, set())
        leave_map = leave_by_emp.get(emp.id, {})

        current = period_start
        while current <= period_end:
            if current in rest_set:
                rest_days_count += 1
                current += timedelta(days=1)
                continue
            if current in absence_set:
                absence_days_count += 1
                current += timedelta(days=1)
                continue
            lt = leave_map.get(current, None)
            if lt == "full":
                leave_days_count += 1
                current += timedelta(days=1)
                continue
            if lt is not None:
                leave_days_count += 1  # 半天/按小时请假也记一天请假，但工时按实际打卡算

            sessions = clock_by_emp_date.get((emp.id, current), [])
            sessions_sorted = sorted(sessions, key=lambda c: c.clocked_in_at or datetime.min)
            n = len({c.session for c in sessions_sorted})
            hours = _day_hours(sessions_sorted) if n in (2, 4) else 0.0

            if has_promotion_this_month:
                if current.day < promotion_day:
                    trial_hours += hours
                else:
                    regular_hours += hours
            else:
                if emp_status == "trial":
                    trial_hours += hours
                else:
                    regular_hours += hours

            for cr in sessions:
                if cr.session == 1:
                    if cr.status == "late_half":
                        late_half_count += 1
                    elif cr.status == "late_one":
                        late_one_count += 1

            current += timedelta(days=1)

        total_work_hours = trial_hours + regular_hours

        if has_promotion_this_month:
            work_pay = trial_hours * trial_hourly + regular_hours * regular_hourly
            if total_work_hours > 0:
                hourly_rate = (trial_hourly * trial_hours + regular_hourly * regular_hours) / total_work_hours
            else:
                hourly_rate = trial_hourly
            emp_status_label = f"试用期→正式(转正{promotion_day}日)"
        elif emp_status == "trial":
            hourly_rate = trial_hourly
            work_pay = total_work_hours * hourly_rate
            emp_status_label = "试用期"
        else:
            hourly_rate = regular_hourly
            work_pay = total_work_hours * hourly_rate
            emp_status_label = "正式员工"

        ot = overtime_map.get(emp.id, {})
        overtime_pay = float(ot.get("amount", 0) or 0)
        overtime_hours = float(ot.get("hours", 0) or 0)

        late_penalty_total = round(late_half_count * hourly_rate * 0.5 + late_one_count * hourly_rate, 2)
        work_pay = round(work_pay, 2)
        gross_pay = round(work_pay + overtime_pay, 2)
        total_deductions = round(late_penalty_total, 2)
        net_pay = round(max(work_pay - late_penalty_total + overtime_pay, 0), 2)

        detail_data = {
            "work_hours": round(total_work_hours, 2),
            "hourly_rate": round(hourly_rate, 2),
            "work_pay": work_pay,
            "late_penalty": late_penalty_total,
            "overtime_hours": round(overtime_hours, 1),
            "overtime_pay": round(overtime_pay, 2),
            "leave_days": leave_days_count,
            "rest_days": rest_days_count,
            "absence_days": absence_days_count,
            "late_half_count": late_half_count,
            "late_one_count": late_one_count,
        }

        record = PayrollRecord(
            warehouse_id=wh_id,
            half=req.half,
            employee_id=emp.id,
            period=req.period,
            settle_end_date=settle_end,
            status="pending",
            total_days_in_month=total_days,
            attendance_days=round(total_work_hours / 8.0, 2),
            leave_days=leave_days_count,
            rest_days=rest_days_count,
            absence_days=absence_days_count,
            employee_status=emp_status,
            daily_wage=daily_wage,
            base_salary=base_salary,
            base_pay=work_pay,
            overtime_pay=round(overtime_pay, 2),
            overtime_hours=round(overtime_hours, 1),
            late_penalty=late_penalty_total,
            leave_deduction=0,
            absence_deduction=0,
            gross_pay=gross_pay,
            total_deductions=total_deductions,
            net_pay=net_pay,
            detail=json.dumps(detail_data, ensure_ascii=False),
        )
        db.add(record)
        records.append(record)

    await db.flush()
    msg = f"已为 {len(records)} 名员工计算 {req.period} 工资"
    if skipped_notes:
        msg += "；" + "；".join(skipped_notes)
    return {
        "message": msg,
        "period": req.period,
        "record_count": len(records),
        "skipped": skipped_notes,
    }

@router.post("/single-settle")
async def single_settle(
    req: SingleSettleRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """单人结算：选员工 + 截止日期，从当前周期开始算到截止日。"""
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
        raise HTTPException(403, "只有仓库管理员/主管可以单人结算")

    wh_id = get_wh_id(current_user)
    if not wh_id:
        raise HTTPException(400, "请先选择仓库")

    try:
        d = datetime.strptime(req.end_date, "%Y-%m-%d").date()
    except:
        raise HTTPException(400, "截止日期格式错误，应为 YYYY-MM-DD")

    period = d.strftime("%Y-%m")
    half = "first_half" if d.day <= 15 else "second_half"
    return await calculate_payroll(
        CalculateRequest(period=period, half=half, employee_ids=[req.employee_id], end_date=req.end_date),
        current_user, db,
    )

@router.get("")
async def list_payroll(
    period: str = None,
    half: str = None,
    status: str = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    wh_id = get_wh_id(current_user)
    if wh_id is None:
        return {"data": [], "periods": []}
    query = select(PayrollRecord).where(PayrollRecord.warehouse_id == wh_id)
    count_q = select(func.count(PayrollRecord.id)).where(PayrollRecord.warehouse_id == wh_id)

    if period:
        query = query.where(PayrollRecord.period == period)
        count_q = count_q.where(PayrollRecord.period == period)
    if half:
        query = query.where(PayrollRecord.half == half)
        count_q = count_q.where(PayrollRecord.half == half)
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
            "half": r.half,
            "settle_end_date": r.settle_end_date.isoformat() if r.settle_end_date else None,
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
        "periods": await _get_available_periods(db, [wh_id]),
    }


@router.get("/summary")
async def payroll_summary(
    period: str = Query(...),
    half: str = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    wh_id = get_wh_id(current_user)
    if wh_id is None:
        return {"period": period, "employee_count": 0, "confirmed_count": 0, "pending_count": 0, "total_gross": 0, "total_overtime": 0, "total_penalties": 0, "total_net": 0}
    summary_q = select(PayrollRecord).where(
        PayrollRecord.warehouse_id == wh_id,
        PayrollRecord.period == period,
    )
    if half:
        summary_q = summary_q.where(PayrollRecord.half == half)
    records = (await db.execute(summary_q)).scalars().all()

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
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
        raise HTTPException(403, "只有仓库管理员可以确认工资")

    wh_id = get_wh_id(current_user)
    if wh_id is None:
        raise HTTPException(400, "请先选择仓库")
    r = (await db.execute(
        select(PayrollRecord).where(
            PayrollRecord.id == record_id,
            PayrollRecord.warehouse_id == wh_id,
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
    half: str = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
        raise HTTPException(403, "只有仓库管理员可以确认工资")

    wh_id = get_wh_id(current_user)
    if wh_id is None:
        raise HTTPException(400, "请先选择仓库")
    conf_q = select(PayrollRecord).where(
        PayrollRecord.warehouse_id == wh_id,
        PayrollRecord.period == period,
        PayrollRecord.status == "pending",
    )
    if half:
        conf_q = conf_q.where(PayrollRecord.half == half)
    records = (await db.execute(conf_q)).scalars().all()

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
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
        raise HTTPException(403, "只有仓库管理员可以删除工资记录")

    wh_id = get_wh_id(current_user)
    if wh_id is None:
        raise HTTPException(400, "请先选择仓库")
    r = (await db.execute(
        select(PayrollRecord).where(
            PayrollRecord.id == record_id,
            PayrollRecord.warehouse_id == wh_id,
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
    half: str = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete all payroll records for a period (to allow recalculation)"""
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
        raise HTTPException(403, "只有仓库管理员可以操作")

    wh_id = get_wh_id(current_user)
    if wh_id is None:
        return {"period": period, "employee_count": 0, "confirmed_count": 0, "pending_count": 0, "total_gross": 0, "total_overtime": 0, "total_penalties": 0, "total_net": 0}
    summary_q = select(PayrollRecord).where(
        PayrollRecord.warehouse_id == wh_id,
        PayrollRecord.period == period,
    )
    if half:
        summary_q = summary_q.where(PayrollRecord.half == half)
    records = (await db.execute(summary_q)).scalars().all()

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
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
        raise HTTPException(403, "只有仓库管理员可以发放工资")

    wh_id = get_wh_id(current_user)
    if wh_id is None:
        raise HTTPException(400, "请先选择仓库")
    r = (await db.execute(
        select(PayrollRecord).where(
            PayrollRecord.id == record_id,
            PayrollRecord.warehouse_id == wh_id,
        )
    )).scalar_one_or_none()
    if not r:
        raise HTTPException(404, "工资记录不存在")
    if r.status != "confirmed":
        raise HTTPException(400, "请先确认工资单再发放")
    if r.disbursed:
        raise HTTPException(400, "该工资单已发放")

    # Save signature if provided（压缩 + 缩略图）
    sig_path = None
    if req.signature_base64:
        try:
            import os, uuid, base64
            from app.services.image_utils import save_image
            header, data = req.signature_base64.split(",", 1) if "," in req.signature_base64 else ("", req.signature_base64)
            img_bytes = base64.b64decode(data)
            wh_id_str = str(r.warehouse_id)
            abs_subdir = os.path.join("/app/uploads", wh_id_str, r.period, "signatures")
            rel_subdir = f"uploads/{wh_id_str}/{r.period}/signatures"
            fname = f"{uuid.uuid4().hex}.png"
            result = save_image(img_bytes, abs_subdir, rel_subdir, fname)
            sig_path = result["path"]
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

    # Find employee record matching this user（排除已删除）
    emp = (await db.execute(
        select(Employee).where(
            Employee.warehouse_id == wh_id,
            Employee.name == current_user.display_name,
            Employee.is_deleted == False,
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
            "half": r.half,
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
        select(PayrollRecord.period, PayrollRecord.half)
        .where(PayrollRecord.warehouse_id.in_(wh_ids))
        .distinct()
        .order_by(PayrollRecord.period.desc(), PayrollRecord.half.desc())
    )
    return [{"period": r[0], "half": r[1], "label": f"{r[0]} {'上半月' if r[1] == 'first_half' else '下半月'}"} for r in result.all()]

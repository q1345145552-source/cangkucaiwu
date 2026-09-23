from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from app.database import get_db
from app.models.payroll import PayrollRecord
from app.models.employee import Employee
from app.models.employee_advance import EmployeeAdvance
from app.models.salary_template import SalaryTemplate
from app.models.deduction_template import DeductionTemplate
from app.models.employee_deduction import EmployeeDeduction, EmployeeFixedDeduction
from app.models.clock_in_records import ClockInRecord
from app.models.attendance import LeaveRequest, RestDay, Absence
from app.models.overtime import OvertimeAssignment, OvertimeTask
from app.models.user import User
from app.core.permissions import get_current_user, get_wh_id, get_wh_ids, Role
from pydantic import BaseModel
from app.core.timezone import thai_now, thai_today, THAI_TZ
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
    is_resignation: bool = False  # 离职结算：扣到实发0为止，剩余欠款老板认了


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
    return await _calc_payroll(db, current_user, wh_id, req)


async def _calc_payroll(db: AsyncSession, current_user: User, wh_id: int, req: CalculateRequest):
    """核心工资计算（周期/单人/离职共用）。wh_id 已由调用方校验。"""
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

    # 周期实际天数（含起止日）：按月模式按此折算周期基础
    period_days = (period_end - period_start).days + 1

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

    # ── 薪资模板检查：没有模板的员工先拦住 ──
    no_template = [e for e in employees if not e.salary_template_id]
    if no_template:
        names = "、".join(e.name for e in no_template)
        raise HTTPException(400, f"以下员工还没有设置薪资模板，请先设置：\n{names}")
    template_ids = {e.salary_template_id for e in employees if e.salary_template_id}
    template_map = {}
    if template_ids:
        ts = (await db.execute(select(SalaryTemplate).where(SalaryTemplate.id.in_(template_ids)))).scalars().all()
        template_map = {t.id: t for t in ts}

    # 扣款模板（考勤扣款规则，可留空 = 不扣考勤款）
    dt_ids = {e.deduction_template_id for e in employees if e.deduction_template_id}
    deduction_template_map = {}
    if dt_ids:
        dts = (await db.execute(select(DeductionTemplate).where(DeductionTemplate.id.in_(dt_ids)))).scalars().all()
        deduction_template_map = {t.id: t for t in dts}

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

    # Build employee_id -> user_id mapping（绑定账号 + 手机号/姓名兜底，未绑定也能结算）
    from app.services.employee_match import resolve_employee_user_map
    emp_user_map, user_emp_map = await resolve_employee_user_map(db, employees)
    emp_id_set = {e.id for e in employees}
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
    leave_by_emp = {}  # emp_id -> {date: (duration_type, hours, notified_at)}
    for lv in leaves:
        if lv.employee_id not in leave_by_emp:
            leave_by_emp[lv.employee_id] = {}
        leave_by_emp[lv.employee_id][lv.leave_date] = (lv.duration_type or "full", lv.hours, lv.notified_at)

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

    # 固定扣款（每月固定，下半月周期扣全额）
    fixed_rows = (await db.execute(
        select(EmployeeFixedDeduction).where(EmployeeFixedDeduction.employee_id.in_(emp_id_set))
    )).scalars().all()
    fixed_by_emp = {}
    for f in fixed_rows:
        fixed_by_emp.setdefault(f.employee_id, []).append({"id": f.id, "name": f.name, "amount": f.amount or 0})

    # 临时扣款（按扣款日期落入本周期）
    temp_rows = (await db.execute(
        select(EmployeeDeduction).where(
            EmployeeDeduction.employee_id.in_(emp_id_set),
            EmployeeDeduction.deduction_date >= period_start,
            EmployeeDeduction.deduction_date <= period_end,
        )
    )).scalars().all()
    temp_by_emp = {}
    for d in temp_rows:
        temp_by_emp.setdefault(d.employee_id, []).append({
            "id": d.id, "amount": d.amount or 0,
            "date": d.deduction_date.isoformat() if d.deduction_date else None,
            "reason": d.reason,
        })

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

    def _attendance_of_day(session_set, lt):
        """按打卡时段和请假计算某天的 (出勤, 请假, 缺勤) 天数，各 0/0.5/1。
        lt 为 leave duration_type：full/morning/afternoon/hours 或 None。
        上午=时段1+2，下午=时段3+4。
        """
        morning = {1, 2}
        afternoon = {3, 4}
        has_morning = morning <= session_set
        has_afternoon = afternoon <= session_set

        if lt == "full":
            return 0.0, 1.0, 0.0
        if lt == "morning":
            if has_afternoon:
                return 0.5, 0.5, 0.0
            return 0.0, 1.0, 0.0
        if lt == "afternoon":
            if has_morning:
                return 0.5, 0.5, 0.0
            return 0.0, 1.0, 0.0
        # hours 请假 / 无请假：按打卡时段判断
        if has_morning and has_afternoon:
            return 1.0, 0.0, 0.0
        if has_morning:
            return 0.5, 0.0, 0.5  # 上午2次无下午请假 → 出勤半天 + 旷工半天
        if has_afternoon:
            return 0.5, 0.0, 0.5  # 下午2次无上午请假 → 出勤半天 + 旷工半天
        return 0.0, 0.0, 1.0  # 无打卡 → 缺勤1天

    pending_days = []
    today = thai_today()
    for emp in employees:
        rest_set = rest_by_emp.get(emp.id, set())
        absence_set = absence_by_emp.get(emp.id, set())
        leave_map = leave_by_emp.get(emp.id, {})
        current = period_start
        while current <= period_end:
            if current >= today:
                break  # 今天还没过完、未来日子不检查打卡完整性
            if current in rest_set or current in absence_set:
                current += timedelta(days=1)
                continue
            lt_info = leave_map.get(current)
            lt = lt_info[0] if lt_info else None
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

    # ── 按员工薪资模板计算 ──
    records = []
    for emp in employees:
        if emp.id in already_calc_emp_ids:
            continue  # 本期已算过，跳过
        template = template_map.get(emp.salary_template_id)
        tt = template.type if template else "daily"
        template_amount = template.amount or 0

        # 扣款模板（可留空 = 不扣考勤款）
        deduction_tpl = deduction_template_map.get(emp.deduction_template_id)

        emp_status = emp.status or "trial"
        # 时薪：按小时/按天 = 日薪/8；按月 = 月薪/当月天数/8
        if tt == "monthly":
            hourly_rate = template_amount / total_days / 8.0
            daily_rate = template_amount / total_days  # 日薪 = 月薪 ÷ 当月天数
        else:
            hourly_rate = template_amount / 8.0
            daily_rate = template_amount  # 日薪 = 模板金额

        work_hours_total = 0.0
        attendance_days_total = 0.0
        late_half_count = 0
        late_one_count = 0
        early_half_count = 0
        early_one_count = 0
        absence_fine_days = 0.0
        rest_days_count = 0
        leave_days_count = 0.0
        absence_days_count = 0.0

        rest_set = rest_by_emp.get(emp.id, set())
        absence_set = absence_by_emp.get(emp.id, set())
        leave_map = leave_by_emp.get(emp.id, {})

        daily_list = []  # 逐天出勤明细
        late_list = []   # 迟到明细（金额在算出时薪后补齐）
        early_list = []  # 早退明细

        current = period_start
        while current <= period_end:
            if current in rest_set:
                rest_days_count += 1
                daily_list.append({"day": current.day, "date": current.isoformat(), "status": "rest", "attendance": 0.0, "hours": 0.0, "times": []})
                current += timedelta(days=1)
                continue
            if current in absence_set:
                absence_days_count += 1.0
                daily_list.append({"day": current.day, "date": current.isoformat(), "status": "absence", "attendance": 0.0, "hours": 0.0, "times": []})
                current += timedelta(days=1)
                continue

            lt_info = leave_map.get(current)
            lt = lt_info[0] if lt_info else None
            lv_hours = lt_info[1] if lt_info else None
            notified_at = lt_info[2] if lt_info else None
            sessions = clock_by_emp_date.get((emp.id, current), [])
            sessions_sorted = sorted(sessions, key=lambda c: c.clocked_in_at or datetime.min)
            sessions_by_session = sorted(sessions, key=lambda c: c.session)
            session_set = {c.session for c in sessions}
            n = len(session_set)
            hours = _day_hours(sessions_sorted) if n in (2, 4) else 0.0
            att, lv, ab = _attendance_of_day(session_set, lt)

            # 旷工自动判定：无打卡的天，当天18点起24小时内报备请假算有效，否则算旷工
            absent_fine_day = 0.0
            if n == 0 and lt is None:
                day_end = datetime.combine(current, time(18, 0), tzinfo=THAI_TZ)
                deadline = day_end + timedelta(hours=24)
                if thai_now() > deadline:
                    # 已过24小时仍未请假 → 旷工
                    att, lv, ab = 0.0, 0.0, 1.0
                    absent_fine_day = 1.0
                else:
                    # 宽限期内：不发钱，先不算旷工
                    att, lv, ab = 0.0, 0.0, 0.0
                    hours = 0.0
            elif n == 0 and lt == "full":
                day_end = datetime.combine(current, time(18, 0), tzinfo=THAI_TZ)
                deadline = day_end + timedelta(hours=24)
                notified = notified_at
                if notified is not None and getattr(notified, "tzinfo", None) is None:
                    notified = notified.replace(tzinfo=THAI_TZ)
                if notified is None or notified <= deadline:
                    # 报备在24小时内 → 有效请假
                    att, lv, ab = 0.0, 1.0, 0.0
                else:
                    # 报备超过24小时 → 旷工
                    att, lv, ab = 0.0, 0.0, 1.0
                    absent_fine_day = 1.0

            # 按小时请假：工时扣掉请假小时数，请假天数记成小时/8 的小数
            if lt == "hours" and lv_hours is not None:
                h = float(lv_hours)
                hours = max(hours - h, 0.0)  # 扣工时（按小时模式少拿钱）
                lv_days = round(h / 8.0, 4)
                if tt == "daily":
                    # 按天模式：够半天按半天算
                    if h >= 8.0:
                        lv, att = 1.0, 0.0
                    elif h >= 4.0:
                        lv, att = 0.5, 0.5
                    else:
                        lv, att = 0.0, 1.0
                else:
                    lv = lv_days
                    att = max(round(1.0 - lv_days, 4), 0.0)

            work_hours_total += hours
            attendance_days_total += att
            leave_days_count += lv
            absence_days_count += ab
            absence_fine_days += absent_fine_day

            # 该天打卡时间（按时段 1-4 顺序，HH:MM）
            times = []
            for c in sessions_by_session:
                t = _local_time_of(c.clocked_in_at)
                if t is not None:
                    times.append(t.strftime("%H:%M"))
            status = "normal"
            if absent_fine_day > 0:
                status = "absence"  # 旷工
            elif lt == "full" or lv == 1.0:
                status = "leave"
            elif ab == 1.0 and att == 0.0:
                status = "no_clock"
            elif att == 0.5:
                status = "half"
            elif ab == 0.5:
                status = "half"
            daily_list.append({"day": current.day, "date": current.isoformat(), "status": status, "attendance": round(att, 2), "hours": round(hours, 2), "times": times})

            for cr in sessions:
                if cr.session == 1:
                    if cr.status == "late_half":
                        late_half_count += 1
                        late_list.append({"day": current.day, "date": current.isoformat(), "type": "late_half"})
                    elif cr.status == "late_one":
                        late_one_count += 1
                        late_list.append({"day": current.day, "date": current.isoformat(), "type": "late_one"})

            # 早退判定：时段4（下班）打卡时间，17:30前早退半小时，17:00前早退1小时
            s4 = next((c for c in sessions if c.session == 4), None)
            if s4 is not None:
                t4 = _local_time_of(s4.clocked_in_at)
                if t4 is not None:
                    if t4 < time(17, 0):
                        early_one_count += 1
                        early_list.append({"day": current.day, "date": current.isoformat(), "type": "early_one"})
                    elif t4 < time(17, 30):
                        early_half_count += 1
                        early_list.append({"day": current.day, "date": current.isoformat(), "type": "early_half"})

            current += timedelta(days=1)

        # 上班工资按模板类型
        leave_deduction = 0.0
        absence_deduction = 0.0
        period_base = None
        if tt == "hourly":
            work_pay = work_hours_total * hourly_rate
        elif tt == "daily":
            work_pay = attendance_days_total * template_amount
        else:  # monthly
            daily_rate = template_amount / total_days
            # 周期基础 = 月薪 × 周期天数 ÷ 当月天数（半天/单人/离职结算按实际天数折算）
            period_base = template_amount * period_days / total_days
            leave_deduction = round(daily_rate * leave_days_count, 2)
            absence_deduction = round(daily_rate * absence_days_count, 2)
            # 上班工资 = 周期基础 - 缺勤扣款 - 请假扣款，下限保护不小于 0
            work_pay = max(period_base - leave_deduction - absence_deduction, 0.0)

        daily_wage = template_amount if tt in ("hourly", "daily") else (emp.daily_wage or 400)
        base_salary = template_amount if tt == "monthly" else (emp.base_salary or 12000)

        ot = overtime_map.get(emp.id, {})
        overtime_pay = float(ot.get("amount", 0) or 0)
        overtime_hours = float(ot.get("hours", 0) or 0)

        # ── 考勤扣款（按扣款模板；无模板则不扣）──
        if deduction_tpl is not None:
            late_half_mult = deduction_tpl.late_half_multiplier if deduction_tpl.late_half_multiplier is not None else 0.5
            late_one_mult = deduction_tpl.late_one_multiplier if deduction_tpl.late_one_multiplier is not None else 1.0
            early_half_mult = deduction_tpl.early_half_multiplier if deduction_tpl.early_half_multiplier is not None else 0.5
            early_one_mult = deduction_tpl.early_one_multiplier if deduction_tpl.early_one_multiplier is not None else 1.0
            absence_extra_mult = deduction_tpl.absence_extra_multiplier if deduction_tpl.absence_extra_multiplier is not None else 0.5
        else:
            late_half_mult = late_one_mult = early_half_mult = early_one_mult = absence_extra_mult = 0.0

        late_penalty_total = round(late_half_count * hourly_rate * late_half_mult + late_one_count * hourly_rate * late_one_mult, 2)
        late_details = []
        for l in late_list:
            amt = round(hourly_rate * late_half_mult, 2) if l["type"] == "late_half" else round(hourly_rate * late_one_mult, 2)
            late_details.append({"day": l["day"], "date": l["date"], "type": l["type"], "amount": amt})

        early_penalty_total = round(early_half_count * hourly_rate * early_half_mult + early_one_count * hourly_rate * early_one_mult, 2)
        early_details = []
        for l in early_list:
            amt = round(hourly_rate * early_half_mult, 2) if l["type"] == "early_half" else round(hourly_rate * early_one_mult, 2)
            early_details.append({"day": l["day"], "date": l["date"], "type": l["type"], "amount": amt})

        # 旷工额外罚 = 日薪 × 旷工倍数 × 旷工天数
        absence_fine_total = round(daily_rate * absence_extra_mult * absence_fine_days, 2)

        # 固定扣款：下半月周期扣全额，上半月不扣
        fixed_items = fixed_by_emp.get(emp.id, [])
        fixed_total = 0.0
        if req.half == "second_half":
            fixed_total = round(sum(f["amount"] for f in fixed_items), 2)

        # 临时扣款：本周期内按扣款日期全部扣
        temp_items = temp_by_emp.get(emp.id, [])
        temp_total = round(sum(d["amount"] for d in temp_items), 2)

        work_pay = round(work_pay, 2)
        gross_pay = round(work_pay + overtime_pay, 2)
        total_deductions = round(late_penalty_total + early_penalty_total + absence_fine_total + fixed_total + temp_total, 2)

        # ── 预支扣款 ──
        available = round(max(work_pay + overtime_pay - total_deductions, 0), 2)
        advance_deduction = 0.0
        advance_deductions = []  # 用于删除工资单时回退
        remaining_debt = 0.0

        # 找出所有还没扣完的预支（含往期 + 本期新预支），按日期从早到晚依次扣
        advances = (await db.execute(
            select(EmployeeAdvance).where(
                EmployeeAdvance.employee_id == emp.id,
                EmployeeAdvance.status != "deducted",
            ).order_by(EmployeeAdvance.advance_date.asc(), EmployeeAdvance.id.asc())
        )).scalars().all()

        remaining_pay = available
        for adv in advances:
            rem = round((adv.amount or 0) - (adv.deducted_amount or 0), 2)
            if rem <= 0:
                continue
            if remaining_pay <= 0:
                break
            deduct = round(min(rem, remaining_pay), 2)
            adv.deducted_amount = round((adv.deducted_amount or 0) + deduct, 2)
            advance_deduction = round(advance_deduction + deduct, 2)
            advance_deductions.append({"advance_id": adv.id, "amount": deduct})
            remaining_pay = round(remaining_pay - deduct, 2)

        # 更新预支状态
        for adv in advances:
            rem = round((adv.amount or 0) - (adv.deducted_amount or 0), 2)
            if rem <= 0:
                adv.status = "deducted"
            elif (adv.deducted_amount or 0) > 0:
                adv.status = "partial"
            else:
                adv.status = "unpaid"

        if req.is_resignation:
            # 离职结算：剩余欠款老板认了，不再追，全部标记已扣完
            for adv in advances:
                adv.deducted_amount = adv.amount or 0
                adv.status = "deducted"
            remaining_debt = 0.0
        else:
            remaining_debt = round(sum(max((adv.amount or 0) - (adv.deducted_amount or 0), 0) for adv in advances), 2)

        net_pay = round(max(available - advance_deduction, 0), 2)

        detail_data = {
            "work_hours": round(work_hours_total, 2),
            "hourly_rate": round(hourly_rate, 2),
            "attendance_days": round(attendance_days_total, 2),
            "work_pay": work_pay,
            "late_penalty": late_penalty_total,
            "early_penalty": early_penalty_total,
            "absence_fine": absence_fine_total,
            "absence_fine_days": absence_fine_days,
            "fixed_deduction": fixed_total,
            "fixed_deductions": fixed_items if req.half == "second_half" else [],
            "temp_deduction": temp_total,
            "temp_deductions": temp_items,
            "overtime_hours": round(overtime_hours, 1),
            "overtime_pay": round(overtime_pay, 2),
            "leave_days": round(leave_days_count, 2),
            "rest_days": rest_days_count,
            "absence_days": round(absence_days_count, 2),
            "leave_deduction": leave_deduction,
            "absence_deduction": absence_deduction,
            "late_half_count": late_half_count,
            "late_one_count": late_one_count,
            "early_half_count": early_half_count,
            "early_one_count": early_one_count,
            "salary_template_name": template.name if template else "",
            "salary_template_type": tt,
            "deduction_template_name": deduction_tpl.name if deduction_tpl else "",
            "daily_wage": round(template_amount, 2) if tt in ("hourly", "daily") else None,
            "base_salary": round(template_amount, 2) if tt == "monthly" else None,
            "period_days": period_days,
            "period_base": round(period_base, 2) if period_base is not None else None,
            "daily_hours": daily_list,
            "late_details": late_details,
            "early_details": early_details,
            "advance_deduction": advance_deduction,
            "remaining_debt": remaining_debt,
            "advance_deductions": advance_deductions,
        }

        record = PayrollRecord(
            warehouse_id=wh_id,
            half=req.half,
            employee_id=emp.id,
            period=req.period,
            settle_end_date=settle_end,
            status="pending",
            total_days_in_month=total_days,
            attendance_days=round(attendance_days_total, 2),
            leave_days=round(leave_days_count, 2),
            rest_days=rest_days_count,
            absence_days=round(absence_days_count, 2),
            employee_status=emp_status,
            daily_wage=daily_wage,
            base_salary=base_salary,
            base_pay=work_pay,
            overtime_pay=round(overtime_pay, 2),
            overtime_hours=round(overtime_hours, 1),
            late_penalty=late_penalty_total,
            early_penalty=early_penalty_total,
            leave_deduction=leave_deduction,
            absence_deduction=absence_deduction,
            absence_fine=absence_fine_total,
            fixed_deduction=fixed_total,
            temp_deduction=temp_total,
            advance_deduction=advance_deduction,
            remaining_debt=remaining_debt,
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


async def _rollback_advance_deductions(db: AsyncSession, record: PayrollRecord):
    """删除工资单时回退预支扣款（按 detail 里记录的明细回退，避免重复扣）。"""
    if not record.detail:
        return
    try:
        detail = json.loads(record.detail)
    except Exception:
        return
    for d in detail.get("advance_deductions", []) or []:
        adv = (await db.execute(
            select(EmployeeAdvance).where(EmployeeAdvance.id == d.get("advance_id"))
        )).scalar_one_or_none()
        if not adv:
            continue
        adv.deducted_amount = round(max((adv.deducted_amount or 0) - (d.get("amount") or 0), 0), 2)
        rem = round((adv.amount or 0) - adv.deducted_amount, 2)
        if rem <= 0:
            adv.status = "deducted" if adv.deducted_amount >= (adv.amount or 0) else "partial"
        elif adv.deducted_amount > 0:
            adv.status = "partial"
        else:
            adv.status = "unpaid"
    await db.flush()


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
            "early_penalty": r.early_penalty or 0,
            "leave_deduction": r.leave_deduction,
            "absence_deduction": r.absence_deduction,
            "absence_fine": r.absence_fine or 0,
            "fixed_deduction": r.fixed_deduction or 0,
            "temp_deduction": r.temp_deduction or 0,
            "advance_deduction": r.advance_deduction or 0,
            "remaining_debt": r.remaining_debt or 0,
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


class BatchIdsRequest(BaseModel):
    record_ids: List[int]


async def _batch_fetch(db: AsyncSession, wh_id: int, record_ids: List[int]):
    """拉取并校验：只返回当前仓库的记录；id 数量不符说明有越权/不存在记录。"""
    ids = list(dict.fromkeys(record_ids or []))
    if not ids:
        raise HTTPException(400, "请选择要操作的记录")
    records = (await db.execute(
        select(PayrollRecord).where(
            PayrollRecord.id.in_(ids),
            PayrollRecord.warehouse_id == wh_id,
        )
    )).scalars().all()
    if len(records) != len(ids):
        raise HTTPException(403, "包含无权操作的记录")
    return records


@router.post("/batch-confirm")
async def batch_confirm_payroll(
    req: BatchIdsRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
        raise HTTPException(403, "只有仓库管理员可以确认工资")
    wh_id = get_wh_id(current_user)
    if not wh_id:
        raise HTTPException(400, "请先选择仓库")
    records = await _batch_fetch(db, wh_id, req.record_ids)
    now = thai_now()
    cnt = 0
    for r in records:
        if r.status != "confirmed":
            r.status = "confirmed"
            r.confirmed_by = current_user.id
            r.confirmed_at = now
            cnt += 1
    await db.flush()
    return {"message": f"已确认 {cnt} 条", "count": cnt}


@router.post("/batch-disburse")
async def batch_disburse_payroll(
    req: BatchIdsRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
        raise HTTPException(403, "只有仓库管理员可以发放工资")
    wh_id = get_wh_id(current_user)
    if not wh_id:
        raise HTTPException(400, "请先选择仓库")
    records = await _batch_fetch(db, wh_id, req.record_ids)
    now = thai_now()
    cnt = 0
    for r in records:
        # 只发放已确认的；已发放的跳过不重复处理
        if r.status == "confirmed" and not r.disbursed:
            r.disbursed = True
            r.disbursed_at = now
            r.disbursed_by = current_user.id
            cnt += 1
    await db.flush()
    return {"message": f"已发放 {cnt} 条", "count": cnt}


@router.post("/batch-delete")
async def batch_delete_payroll(
    req: BatchIdsRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
        raise HTTPException(403, "只有仓库管理员可以删除工资记录")
    wh_id = get_wh_id(current_user)
    if not wh_id:
        raise HTTPException(400, "请先选择仓库")
    records = await _batch_fetch(db, wh_id, req.record_ids)
    for r in records:
        await _rollback_advance_deductions(db, r)
        await db.delete(r)
    await db.flush()
    return {"message": f"已删除 {len(records)} 条", "count": len(records)}


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

    await _rollback_advance_deductions(db, r)
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
        await _rollback_advance_deductions(db, r)
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
            "early_penalty": r.early_penalty or 0,
            "leave_deduction": r.leave_deduction,
            "absence_deduction": r.absence_deduction,
            "absence_fine": r.absence_fine or 0,
            "fixed_deduction": r.fixed_deduction or 0,
            "temp_deduction": r.temp_deduction or 0,
            "advance_deduction": r.advance_deduction or 0,
            "remaining_debt": r.remaining_debt or 0,
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

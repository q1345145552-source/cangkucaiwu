"""Independent monthly settlement. Shared attendance helpers remain read-only."""
import calendar
import json
from datetime import date, datetime, timedelta
from fastapi import HTTPException
from sqlalchemy import select
from app.core.timezone import THAI_TZ, thai_now
from app.models.payroll import PayrollRecord
from app.models.employee_advance import EmployeeAdvance, AdvanceApprovalStatus
from app.models.overtime import OvertimeTask, OvertimeAssignment
from app.services.half_day_leave import is_half_day_leave, half_day_leave_hours
from app.services.full_day_leave import full_day_net_hours
from app.services.early_departure_leave import leave_covers_early_departure
from app.services.hourly_leave import hourly_leave_net_hours, is_hourly_leave, hourly_clock_hours


def monthly_rest_dates(template, start, end):
    """Derive all configured dates, including a fifth weekday; never write RestDay."""
    result = set()
    current = start
    while current <= end:
        if (template.monthly_rest_pattern == "weekly" and
            (current.weekday() + 1) % 7 in (template.monthly_rest_weekdays or [])) or (
            template.monthly_rest_pattern == "monthly" and
            current.day in (template.monthly_rest_monthdays or [])):
            result.add(current)
        current += timedelta(days=1)
    return result


async def compute_monthly_record(db, wh_id, req, prep, emp):
    from app.api.v1.payroll import _leave_summary, _day_hours, _attendance_of_day, _local_time_of
    emp_start = prep["emp_start"]
    period_end = prep["period_end"]
    batch_end = prep["batch_end"]
    total_days = prep["total_days"]
    period = prep["period"]
    half = prep["half"]
    template_map = prep["template_map"]
    deduction_template_map = prep["deduction_template_map"]
    clock_by_emp_date = prep["clock_by_emp_date"]
    leave_by_emp = prep["leave_by_emp"]
    rest_by_emp = prep["rest_by_emp"]
    absence_by_emp = prep["absence_by_emp"]
    fixed_by_emp = prep["fixed_by_emp"]
    temp_by_emp = prep["temp_by_emp"]
    early_half_time = prep["early_half_time"]
    early_one_time = prep["early_one_time"]
    afternoon_end_time = prep["afternoon_end_time"]
    standard_hours = prep["standard_hours"]
    exempt_dates = prep["exempt_dates"]
    from app.services.attendance_exemptions import exemption_hours

    template = template_map.get(emp.salary_template_id)
    tt = "monthly"
    template_amount = template.amount or 0
    # 本员工实际区间（起点按水位线，结束日统一）
    emp_start_date = emp_start[emp.id]
    emp_period_days = (period_end - emp_start_date).days + 1

    # 扣款模板（可留空 = 不扣考勤款）
    deduction_tpl = deduction_template_map.get(emp.deduction_template_id)

    emp_status = emp.status or "trial"
    # Deduction unit follows the template; a leave day is always eight hours.
    if emp_start_date.day != 1 or period_end != date(emp_start_date.year, emp_start_date.month, calendar.monthrange(emp_start_date.year, emp_start_date.month)[1]) or req.is_resignation:
        raise HTTPException(400, "月薪暂只支持完整自然月结算，半月、跨月及离职结算请等待折算规则确认")
    if template.monthly_deduction_mode == "fixed" and template.monthly_fixed_days and template.monthly_fixed_days > 0:
        divisor = template.monthly_fixed_days
    elif template.monthly_deduction_mode == "actual":
        divisor = calendar.monthrange(emp_start_date.year, emp_start_date.month)[1]
    else:
        raise HTTPException(400, "请先在月薪模板设置有效的扣款天数模式和固定天数")
    daily_rate = template_amount / divisor
    hourly_rate = daily_rate / 8.0

    work_hours_total = 0.0
    attendance_days_total = 0.0
    late_half_count = 0
    late_one_count = 0
    early_half_count = 0
    early_one_count = 0
    absence_fine_days = 0.0
    absence_fine_list = []
    rest_days_count = 0
    leave_days_count = 0.0
    absence_days_count = 0.0
    monthly_leave_deduction = 0.0
    monthly_absence_deduction = 0.0

    rest_set = rest_by_emp.get(emp.id, set()) | monthly_rest_dates(template, emp_start_date, period_end)
    absence_set = absence_by_emp.get(emp.id, set())
    leave_map = leave_by_emp.get(emp.id, {})

    daily_list = []  # 逐天出勤明细
    late_list = []   # 迟到明细（金额在算出时薪后补齐）
    early_list = []  # 早退明细

    current = emp_start_date
    while current <= period_end:
        if current in exempt_dates:
            hours, leave_hours = exemption_hours(leave_map.get(current), current, prep["work_sched"])
            att, lv = hours / 8.0, leave_hours / 8.0
            work_hours_total += hours
            attendance_days_total += att
            leave_days_count += lv
            monthly_leave_deduction += lv * daily_rate
            daily_list.append({"day": current.day, "date": current.isoformat(), "status": "exempt",
                               "attendance": round(att, 4), "hours": hours, "leave_hours": leave_hours,
                               "times": [], "note": "已豁免，打卡保留但不参与计算"})
            current += timedelta(days=1)
            continue
        if current in rest_set and _leave_summary(leave_map.get(current)) is None:
            rest_days_count += 1
            daily_list.append({"day": current.day, "date": current.isoformat(), "status": "rest", "attendance": 0.0, "hours": 0.0, "times": []})
            current += timedelta(days=1)
            continue
        if current in absence_set:
            absence_days_count += 1.0
            monthly_absence_deduction += daily_rate
            # 手动缺勤也按旷工罚款：旷工倍数 × 当天日薪 × 1天（跟自动判旷工算法一致）
            absence_fine_days += 1.0
            absence_fine_list.append({"date": current.isoformat(), "days": 1.0})
            daily_list.append({"day": current.day, "date": current.isoformat(), "status": "absence", "attendance": 0.0, "hours": 0.0, "times": []})
            current += timedelta(days=1)
            continue

        lt_info = leave_map.get(current)
        lt = _leave_summary(lt_info)
        lv_hours = lt_info["hours"] if (lt_info and lt_info.get("hours_has")) else None
        notified_at = lt_info.get("notified_at") if lt_info else None
        sessions = clock_by_emp_date.get((emp.id, current), [])
        sessions_sorted = sorted(sessions, key=lambda c: c.clocked_in_at or datetime.min)
        sessions_by_session = sorted(sessions, key=lambda c: c.session)
        session_set = {c.session for c in sessions}
        n = len(session_set)
        hours = _day_hours(sessions_sorted) if n in (2, 4) else 0.0
        att, lv, ab = _attendance_of_day(session_set, lt)

        # 旷工自动判定：无打卡的天，当天下班时间起24小时内报备请假算有效，否则算旷工
        absent_fine_day = 0.0
        if n == 0 and lt is None:
            day_end = datetime.combine(current, afternoon_end_time, tzinfo=THAI_TZ)
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
            day_end = datetime.combine(current, afternoon_end_time, tzinfo=THAI_TZ)
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
        elif n == 2 and lt is None:
            # 半天旷工：上午2次无下午请假，或下午2次无上午请假（缺勤半天）
            absent_fine_day = 0.5

        # Same net-hour decision as the calendar; no second deduction for early departure.
        if is_hourly_leave(lt_info):
            h = None if lt_info.get("hourly_missing") else lv_hours
            hours = hourly_leave_net_hours(
                hourly_clock_hours(sessions_sorted), h, sessions_sorted[-1].clocked_in_at if sessions_sorted else None,
                current, prep["work_sched"], standard_hours,
            )
            if h is None or h >= 8.0:
                lv, att, ab = 1.0, 0.0, 0.0
            else:
                lv = min(max(float(h), 0.0), 8.0) / 8.0
                att = hours / standard_hours
                # Approved leave and missing attendance cannot cover the same hours.
                ab = min(ab, max(1.0 - lv - att, 0.0))


        if is_half_day_leave(lt_info):
            half_leave_hours, hours = half_day_leave_hours(sessions_sorted, lt_info, current, prep["work_sched"])
            att = hours / standard_hours
            lv = min(max(half_leave_hours, 0.0), 8.0) / 8.0
            ab = 0.0


        hours = full_day_net_hours(lt_info, hours)
        work_hours_total += hours
        attendance_days_total += att
        leave_days_count += lv
        absence_days_count += ab
        absence_fine_days += absent_fine_day
        if absent_fine_day > 0:
            absence_fine_list.append({"date": current.isoformat(), "days": absent_fine_day})
        monthly_leave_deduction += lv * daily_rate
        monthly_absence_deduction += ab * daily_rate

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
        daily_list.append({"day": current.day, "date": current.isoformat(), "status": status, "attendance": round(att, 4) if (is_hourly_leave(lt_info) or is_half_day_leave(lt_info)) else round(att, 2), "hours": round(hours, 2), "times": times})

        for cr in sessions:
            if cr.session == 1:
                if cr.status == "late_half":
                    late_half_count += 1
                    late_list.append({"day": current.day, "date": current.isoformat(), "type": "late_half"})
                elif cr.status == "late_one":
                    late_one_count += 1
                    late_list.append({"day": current.day, "date": current.isoformat(), "type": "late_one"})

        # 早退判定：时段4（下班）打卡时间，按扣款模板的红线判断
        s4 = next((c for c in sessions if c.session == 4), None)
        if s4 is not None and not leave_covers_early_departure(lt_info, s4.clocked_in_at, current, prep["work_sched"]):
            t4 = _local_time_of(s4.clocked_in_at)
            if t4 is not None:
                if t4 < early_one_time:
                    early_one_count += 1
                    early_list.append({"day": current.day, "date": current.isoformat(), "type": "early_one"})
                elif t4 < early_half_time:
                    early_half_count += 1
                    early_list.append({"day": current.day, "date": current.isoformat(), "type": "early_half"})

        current += timedelta(days=1)

    # Full natural-month salary; rest dates do not reduce the base.
    period_base = float(template_amount)
    monthly_breakdown = [{"start": emp_start_date.isoformat(), "end": period_end.isoformat(),
                          "days": emp_period_days, "month_days": total_days, "amount": period_base}]
    leave_deduction = round(monthly_leave_deduction, 2)
    absence_deduction = round(monthly_absence_deduction, 2)
    work_pay = max(period_base - leave_deduction - absence_deduction, 0.0)
    daily_wage = emp.daily_wage or 400
    base_salary = template_amount
    # Confirmed task hours only, excluding rest dates. Do not reuse daily earned amounts.
    ot_rows = (await db.execute(select(OvertimeTask.date, OvertimeTask.hours).join(
        OvertimeAssignment, OvertimeAssignment.overtime_id == OvertimeTask.id
    ).where(OvertimeTask.warehouse_id == wh_id, OvertimeAssignment.employee_id == emp.id,
            OvertimeAssignment.confirmed == True, OvertimeTask.date >= emp_start_date,
            OvertimeTask.date <= period_end))).all()
    overtime_hours = sum(float(row.hours or 0) for row in ot_rows if row.date not in rest_set)
    overtime_pay = round(overtime_hours * float(template.monthly_overtime_hour_fee or 0), 2)

    # ── 考勤扣款（按扣款模板；无模板则不扣）──
    if deduction_tpl is not None:
        late_half_mult = deduction_tpl.late_half_multiplier if deduction_tpl.late_half_multiplier is not None else 0.5
        late_one_mult = deduction_tpl.late_one_multiplier if deduction_tpl.late_one_multiplier is not None else 1.0
        early_half_mult = deduction_tpl.early_half_multiplier if deduction_tpl.early_half_multiplier is not None else 0.5
        early_one_mult = deduction_tpl.early_one_multiplier if deduction_tpl.early_one_multiplier is not None else 1.0
        absence_extra_mult = deduction_tpl.absence_extra_multiplier if deduction_tpl.absence_extra_multiplier is not None else 0.5
    else:
        late_half_mult = late_one_mult = early_half_mult = early_one_mult = absence_extra_mult = 0.0

    late_penalty_total = 0.0
    late_details = []
    for l in late_list:
        mult = late_half_mult if l["type"] == "late_half" else late_one_mult
        amt = round(hourly_rate * mult, 2)
        late_penalty_total += amt
        late_details.append({"day": l["day"], "date": l["date"], "type": l["type"], "amount": amt})
    late_penalty_total = round(late_penalty_total, 2)

    early_penalty_total = 0.0
    early_details = []
    for l in early_list:
        mult = early_half_mult if l["type"] == "early_half" else early_one_mult
        amt = round(hourly_rate * mult, 2)
        early_penalty_total += amt
        early_details.append({"day": l["day"], "date": l["date"], "type": l["type"], "amount": amt})
    early_penalty_total = round(early_penalty_total, 2)

    # 旷工额外罚 = 每天各自的日薪 × 旷工倍数 × 该天旷工天数
    absence_fine_total = 0.0
    for a in absence_fine_list:
        amt = round(daily_rate * absence_extra_mult * a["days"], 2)
        absence_fine_total += amt
    absence_fine_total = round(absence_fine_total, 2)

    # 固定扣款：按天折算，每个自然月分别折算再相加（与薪资模板类型无关）
    fixed_items = fixed_by_emp.get(emp.id, [])
    fixed_total = 0.0
    fixed_details = []
    for f in fixed_items:
        amt = f["amount"] or 0
        prorated = 0.0
        seg_start = emp_start_date
        while seg_start <= period_end:
            seg_month_end = date(seg_start.year, seg_start.month, calendar.monthrange(seg_start.year, seg_start.month)[1])
            seg_end = min(period_end, seg_month_end)
            seg_days = (seg_end - seg_start).days + 1
            seg_month_days = calendar.monthrange(seg_start.year, seg_start.month)[1]
            prorated += amt * seg_days / seg_month_days
            seg_start = seg_end + timedelta(days=1)
        prorated = round(prorated, 2)
        fixed_total += prorated
        fixed_details.append({"id": f["id"], "name": f["name"], "amount": f["amount"], "deducted": prorated})
    fixed_total = round(fixed_total, 2)

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
            EmployeeAdvance.approval_status == AdvanceApprovalStatus.APPROVED.value,
            EmployeeAdvance.not_voided(),
        ).order_by(EmployeeAdvance.advance_date.asc(), EmployeeAdvance.id.asc()).with_for_update()
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
        "fixed_deductions": fixed_details,
        "temp_deduction": temp_total,
        "temp_deductions": temp_items,
        "overtime_hours": round(overtime_hours, 1),
        "overtime_pay": round(overtime_pay, 2),
        "leave_days": round(leave_days_count, 2),
        "rest_days": rest_days_count,
        "absence_days": round(absence_days_count, 2),
        "leave_deduction": leave_deduction,
        "absence_deduction": absence_deduction,
        "monthly_breakdown": monthly_breakdown,
        "late_half_count": late_half_count,
        "late_one_count": late_one_count,
        "early_half_count": early_half_count,
        "early_one_count": early_one_count,
        "salary_template_name": template.name if template else "",
        "salary_template_type": tt,
        "deduction_template_name": deduction_tpl.name if deduction_tpl else "",
        "daily_wage": None,
        "base_salary": round(template_amount, 2),
        "period_days": emp_period_days,
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
        half=half,
        employee_id=emp.id,
        period=period,
        settle_start_date=emp_start_date,
        settle_end_date=batch_end,
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
    return record


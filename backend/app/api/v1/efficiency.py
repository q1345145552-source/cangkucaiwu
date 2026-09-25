from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.models.labor_efficiency import EfficiencyOrderCount, EfficiencyManualHour
from app.models.employee import Employee
from app.models.salary_template import SalaryTemplate
from app.models.clock_in_records import ClockInRecord
from app.models.overtime import OvertimeTask, OvertimeAssignment
from app.models.user import User
from app.models.expense_fund import SystemSetting
from app.models.recharge import RechargeDeclaration
from app.models.warehouse import Warehouse
from app.core.permissions import get_current_user, get_wh_id, get_wh_ids, Role
from app.core.timezone import thai_today, THAI_TZ
from pydantic import BaseModel
from datetime import datetime, date, time, timedelta
from typing import Optional
import calendar

router = APIRouter()

DEFAULT_STANDARD = 450  # 1人次最低单数（默认，未设置月度标准时使用）
CROSS_CHECK_THRESHOLD = 50.0  # 订单数与充值金额环比偏差阈值（百分点）


class OrderCountSet(BaseModel):
    date: str  # YYYY-MM-DD（某天）
    order_count: int


class StandardSet(BaseModel):
    standard: float
    month: Optional[str] = None  # YYYY-MM；不传则设置默认值


class ManualHourSet(BaseModel):
    employee_id: int
    date: str  # YYYY-MM-DD
    hours: float


class ManualHourDelete(BaseModel):
    employee_id: int
    date: str  # YYYY-MM-DD


# ═══ Helpers ════════════════════════════

def _local_time(dt) -> time:
    """返回打卡时间在泰国时区的一天内时刻。"""
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(THAI_TZ).time()
    return dt.time()


def _calc_daily_hours(records) -> tuple:
    """按打卡次数计算单日工时。返回 (hours, status)。
    - 2 次: 第2次 - 第1次（上午两段或下午两段，中间均不含午休，直接相减）
    - 4 次: (第2次-第1次) + (第4次-第3次)
    - 1 或 3 次: 无法计算 → 待补
    records 需按 clocked_in_at 升序。"""
    n = len(records)
    times = [r.clocked_in_at for r in records]
    if n == 2:
        if times[0] is None or times[1] is None:
            return None, "pending"
        hours = (times[1] - times[0]).total_seconds() / 3600.0
        return max(hours, 0.0), "normal"
    if n == 4:
        if any(t is None for t in times):
            return None, "pending"
        h1 = (times[1] - times[0]).total_seconds() / 3600.0
        h2 = (times[3] - times[2]).total_seconds() / 3600.0
        return max(h1, 0.0) + max(h2, 0.0), "normal"
    return None, "pending"


def _effective_day(info: dict) -> tuple:
    """根据打卡状态 + 手动补录，返回 (source, effective_hours)。
    source: clock(打卡算出) / manual(手动补录) / pending(待补) / none(无数据)。"""
    cs = info["clock_status"]
    if cs == "normal":
        return "clock", info["clock_hours"]
    if cs == "pending":
        if info["manual_hours"] is not None:
            return "manual", info["manual_hours"]
        return "pending", None
    return "none", None


def _hourly_rate(template, month_date: date) -> float:
    """员工时薪，按薪资模板取。hourly/daily = 金额/8；monthly = 金额/当月天数/8。无模板返回 0。"""
    if template is None:
        return 0.0
    amount = template.amount or 0
    tt = template.type
    if tt == "monthly":
        days_in_month = calendar.monthrange(month_date.year, month_date.month)[1]
        daily = amount / days_in_month if days_in_month else 0.0
    else:  # hourly / daily
        daily = amount
    return daily / 8.0


def _employee_regular_hours(uid, daily: dict, monday: date, sunday: date) -> float:
    """某员工一周的正常工时（打卡算出 + 手动补录，不含加班）。"""
    total = 0.0
    d = monday
    while d <= sunday:
        info = daily.get((uid, d))
        if info:
            _source, eff = _effective_day(info)
            if eff is not None:
                total += eff
        d += timedelta(days=1)
    return total


def _parse_week_start(s: str) -> date:
    try:
        d = datetime.strptime(s, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        raise HTTPException(400, "周起始日期格式错误，应为 YYYY-MM-DD")
    if d.weekday() != 0:
        raise HTTPException(400, "周起始日期必须是周一")
    return d


def _current_monday() -> date:
    today = thai_today()
    return today - timedelta(days=today.weekday())


def _month_bounds(month_str: str) -> tuple:
    try:
        y, m = month_str.split("-")
        year, month = int(y), int(m)
    except (ValueError, TypeError):
        raise HTTPException(400, "月份格式错误，应为 YYYY-MM")
    if month < 1 or month > 12:
        raise HTTPException(400, "月份无效")
    month_start = date(year, month, 1)
    if month == 12:
        month_end = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        month_end = date(year, month + 1, 1) - timedelta(days=1)
    return month_start, month_end


def _weeks_in_month(month_start: date, month_end: date) -> list:
    """返回当月所有周一日期（周一落在当月内的周）。"""
    weeks = []
    first_monday = month_start + timedelta(days=(7 - month_start.weekday()) % 7)
    d = first_monday
    while d <= month_end:
        weeks.append(d)
        d += timedelta(days=7)
    return weeks


async def _get_standard(db: AsyncSession, wh_id: int, month_str: Optional[str] = None) -> float:
    """月度标准：优先按月单独设置，其次用旧的默认值，最后用全局默认 450。"""
    if month_str:
        monthly = (await db.execute(
            select(SystemSetting).where(
                SystemSetting.warehouse_id == wh_id,
                SystemSetting.key == f"efficiency_standard_{month_str}",
            )
        )).scalar_one_or_none()
        if monthly:
            try:
                return float(monthly.value)
            except (ValueError, TypeError):
                pass
    setting = (await db.execute(
        select(SystemSetting).where(
            SystemSetting.warehouse_id == wh_id,
            SystemSetting.key == "efficiency_standard",
        )
    )).scalar_one_or_none()
    try:
        return float(setting.value) if setting else float(DEFAULT_STANDARD)
    except (ValueError, TypeError):
        return float(DEFAULT_STANDARD)


async def _get_daily_orders(db: AsyncSession, wh_id: int, start: date, end: date) -> dict:
    """一段时间内每天的订单数，返回 {date: order_count}。"""
    rows = (await db.execute(
        select(EfficiencyOrderCount).where(
            EfficiencyOrderCount.warehouse_id == wh_id,
            EfficiencyOrderCount.date >= start,
            EfficiencyOrderCount.date <= end,
        )
    )).scalars().all()
    return {r.date: int(r.order_count) for r in rows}


async def _get_period_order_count(db: AsyncSession, wh_id: int, start: date, end: date) -> int:
    """一段时间内每天的订单数加总。"""
    result = (await db.execute(
        select(func.coalesce(func.sum(EfficiencyOrderCount.order_count), 0)).where(
            EfficiencyOrderCount.warehouse_id == wh_id,
            EfficiencyOrderCount.date >= start,
            EfficiencyOrderCount.date <= end,
        )
    )).scalar()
    return int(result or 0)


async def _compute_overtime_hours(db: AsyncSession, wh_id: int, start: date, end: date) -> float:
    result = (await db.execute(
        select(func.sum(OvertimeTask.hours))
        .join(OvertimeAssignment, OvertimeAssignment.overtime_id == OvertimeTask.id)
        .where(
            OvertimeAssignment.confirmed == True,
            OvertimeTask.warehouse_id == wh_id,
            OvertimeTask.date >= start,
            OvertimeTask.date <= end,
        )
    )).scalar()
    return float(result or 0)


async def _recharge_total(db: AsyncSession, wh_id: int, start: date, end: date) -> float:
    """一段时间内该仓库的充值金额合计。"""
    result = (await db.execute(
        select(func.sum(RechargeDeclaration.amount)).where(
            RechargeDeclaration.warehouse_id == wh_id,
            func.date(RechargeDeclaration.declare_date) >= start,
            func.date(RechargeDeclaration.declare_date) <= end,
        )
    )).scalar()
    return float(result or 0)


async def _compute_cross_check(db: AsyncSession, wh_id: int, monday: date) -> dict:
    """订单数交叉校验：对比本周订单数环比 vs 充值金额环比。"""
    sunday = monday + timedelta(days=6)
    prev_monday = monday - timedelta(days=7)
    prev_sunday = monday - timedelta(days=1)

    cur_order = await _get_period_order_count(db, wh_id, monday, sunday)
    prev_order = await _get_period_order_count(db, wh_id, prev_monday, prev_sunday)
    cur_recharge = await _recharge_total(db, wh_id, monday, sunday)
    prev_recharge = await _recharge_total(db, wh_id, prev_monday, prev_sunday)

    result = {
        "order_count": cur_order,
        "prev_order_count": prev_order,
        "recharge_amount": round(cur_recharge, 2),
        "prev_recharge_amount": round(prev_recharge, 2),
        "threshold": CROSS_CHECK_THRESHOLD,
    }

    if cur_order <= 0:
        result["status"] = "no_data"
        result["order_pct"] = None
        result["recharge_pct"] = None
        result["deviation"] = None
        result["message"] = "本周尚未录入订单数，暂无校验"
        return result

    order_pct = round((cur_order - prev_order) / prev_order * 100.0, 1) if prev_order > 0 else None
    recharge_pct = round((cur_recharge - prev_recharge) / prev_recharge * 100.0, 1) if prev_recharge > 0 else None
    result["order_pct"] = order_pct
    result["recharge_pct"] = recharge_pct

    if order_pct is None or recharge_pct is None:
        result["status"] = "insufficient"
        result["deviation"] = None
        result["message"] = "上一期订单数或充值金额为 0，暂无法环比校验"
        return result

    deviation = round(abs(order_pct - recharge_pct), 1)
    result["deviation"] = deviation
    if deviation > CROSS_CHECK_THRESHOLD:
        result["status"] = "warning"
        result["message"] = f"订单数环比 {order_pct:+}%，充值金额环比 {recharge_pct:+}%，偏差 {deviation}pp，订单数可能有问题，请核实"
    else:
        result["status"] = "ok"
        result["message"] = f"订单数环比 {order_pct:+}%，充值金额环比 {recharge_pct:+}%，偏差 {deviation}pp，正常"
    return result


async def _compute_week(db: AsyncSession, wh_id: int, monday: date, sunday: date,
                        include_employees: bool = True) -> dict:
    # 所有员工（含离职，排除已删除）；离职员工仅在其有工时的周计入统计
    emps = (await db.execute(
        select(Employee).where(Employee.warehouse_id == wh_id, Employee.is_deleted == False)
    )).scalars().all()

    # 薪资模板映射（人工成本按模板取，无模板的员工时薪按 0 计）
    template_ids = {e.salary_template_id for e in emps if e.salary_template_id}
    template_map = {}
    if template_ids:
        ts = (await db.execute(select(SalaryTemplate).where(SalaryTemplate.id.in_(template_ids)))).scalars().all()
        template_map = {t.id: t for t in ts}

    # user_id -> employee 映射（正式关联 + 姓名回退）
    user_emp = {}   # user_id -> Employee
    emp_user = {}   # employee_id -> user_id
    for e in emps:
        if e.user_id:
            emp_user[e.id] = e.user_id
            user_emp[e.user_id] = e
    emp_names = {e.name: e for e in emps if e.id not in emp_user}
    if emp_names:
        labor_users = (await db.execute(
            select(User).where(
                User.role == "warehouse_labor",
                User.is_active == True,
                User.warehouse_id == wh_id,
            )
        )).scalars().all()
        for u in labor_users:
            if u.display_name in emp_names and u.id not in user_emp:
                e = emp_names[u.display_name]
                emp_user[e.id] = u.id
                user_emp[u.id] = e

    # 该仓该周所有打卡记录
    records = (await db.execute(
        select(ClockInRecord).where(
            ClockInRecord.warehouse_id == wh_id,
            ClockInRecord.clock_date >= monday,
            ClockInRecord.clock_date <= sunday,
        ).order_by(ClockInRecord.clock_date, ClockInRecord.clocked_in_at)
    )).scalars().all()

    by_user_date = {}
    for r in records:
        by_user_date.setdefault((r.user_id, r.clock_date), []).append(r)

    # 该仓该周所有手动补录工时
    supps = (await db.execute(
        select(EfficiencyManualHour).where(
            EfficiencyManualHour.warehouse_id == wh_id,
            EfficiencyManualHour.date >= monday,
            EfficiencyManualHour.date <= sunday,
        )
    )).scalars().all()
    supp_map = {(s.employee_id, s.date): s for s in supps}

    daily = {}  # (user_id, date) -> {clock_count, clock_hours, clock_status, manual_hours, supplement_id}
    for key, recs in by_user_date.items():
        recs_sorted = sorted(recs, key=lambda x: x.clocked_in_at)
        hours, status = _calc_daily_hours(recs_sorted)
        daily[key] = {
            "clock_count": len(recs_sorted),
            "clock_hours": hours,
            "clock_status": status,
            "manual_hours": None,
            "supplement_id": None,
        }

    # 把手动补录工时挂到对应的 (user_id, date)（仅待补天有效）
    for (emp_id, d), s in supp_map.items():
        uid = emp_user.get(emp_id)
        if uid is None:
            continue
        info = daily.get((uid, d))
        if info is not None and info["clock_status"] == "pending":
            info["manual_hours"] = s.hours
            info["supplement_id"] = s.id

    # 确定计入统计的员工：在职全算；离职仅算该周有打卡或补录的
    clock_uids = {k[0] for k in daily.keys()}
    supp_emp_ids = {k[0] for k in supp_map.keys()}
    included_emps = []
    for e in emps:
        uid = emp_user.get(e.id)
        has_hours = (uid in clock_uids) or (e.id in supp_emp_ids)
        if (e.status or "") != "resigned" or has_hours:
            included_emps.append(e)

    # 汇总
    regular_total = 0.0
    pending_days = 0
    for info in daily.values():
        if info["clock_status"] == "normal":
            regular_total += (info["clock_hours"] or 0.0)
        elif info["clock_status"] == "pending":
            if info["manual_hours"] is not None:
                regular_total += info["manual_hours"]
            else:
                pending_days += 1

    overtime_hours = await _compute_overtime_hours(db, wh_id, monday, sunday)
    order_count = await _get_period_order_count(db, wh_id, monday, sunday)
    standard = await _get_standard(db, wh_id, monday.strftime("%Y-%m"))

    # 人工成本 = Σ(员工正常工时 × 时薪)，时薪按薪资模板取
    labor_cost = 0.0
    for e in included_emps:
        uid = emp_user.get(e.id)
        if not uid:
            continue
        tpl = template_map.get(e.salary_template_id)
        labor_cost += _employee_regular_hours(uid, daily, monday, sunday) * _hourly_rate(tpl, monday)
    labor_cost = round(labor_cost, 2)

    total_hours = round(regular_total + overtime_hours, 2)
    person_times = round(total_hours / 8.0, 1)
    efficiency = round(order_count / person_times, 1) if person_times > 0 else 0.0
    below_standard = efficiency < standard
    cost_per_order = round(labor_cost / order_count, 2) if order_count > 0 else 0.0
    overtime_ratio = round(overtime_hours / total_hours * 100.0, 1) if total_hours > 0 else 0.0

    result = {
        "regular_hours": round(regular_total, 2),
        "overtime_hours": round(overtime_hours, 2),
        "total_hours": total_hours,
        "person_times": person_times,
        "order_count": order_count,
        "efficiency": efficiency,
        "standard": standard,
        "below_standard": below_standard,
        "pending_days": pending_days,
        "labor_cost": labor_cost,
        "cost_per_order": cost_per_order,
        "overtime_ratio": overtime_ratio,
    }

    if include_employees:
        employees = []
        seen_uids = set()
        for e in included_emps:
            uid = emp_user.get(e.id)
            days = []
            emp_hours = 0.0
            if uid:
                seen_uids.add(uid)
                d = monday
                while d <= sunday:
                    info = daily.get((uid, d))
                    if info:
                        source, eff = _effective_day(info)
                        days.append({
                            "date": d.isoformat(), "clock_count": info["clock_count"],
                            "source": source, "hours": eff,
                            "manual_hours": info["manual_hours"], "supplement_id": info["supplement_id"],
                        })
                        if eff is not None:
                            emp_hours += eff
                    else:
                        days.append({"date": d.isoformat(), "clock_count": 0, "source": "none",
                                     "hours": None, "manual_hours": None, "supplement_id": None})
                    d += timedelta(days=1)
            employees.append({
                "employee_id": e.id, "name": e.name, "user_id": uid,
                "status": e.status, "total_hours": round(emp_hours, 1), "days": days,
            })
        # 有打卡但没有匹配到员工档案的 user_id
        unmatched_uids = [uid for uid in {k[0] for k in daily.keys()} if uid not in seen_uids]
        if unmatched_uids:
            us = (await db.execute(select(User).where(User.id.in_(unmatched_uids)))).scalars().all()
            name_map = {u.id: u.display_name for u in us}
            for uid in unmatched_uids:
                employees.append({
                    "employee_id": None, "name": name_map.get(uid) or "未关联员工",
                    "user_id": uid, "total_hours": 0.0, "days": [],
                })
        result["employees"] = employees

    return result


async def _aggregate_month(db: AsyncSession, wh_id: int, month_str: str) -> dict:
    """按月汇总各周订单数与工时（周一在当月内的周）。"""
    month_start, month_end = _month_bounds(month_str)
    weeks = _weeks_in_month(month_start, month_end)
    agg = {
        "regular_hours": 0.0, "overtime_hours": 0.0, "total_hours": 0.0,
        "order_count": 0, "pending_days": 0, "labor_cost": 0.0,
    }
    week_rows = []
    for monday in weeks:
        sunday = monday + timedelta(days=6)
        wd = await _compute_week(db, wh_id, monday, sunday, include_employees=False)
        week_rows.append({
            "week_start": monday.isoformat(),
            "week_end": sunday.isoformat(),
            "regular_hours": wd["regular_hours"],
            "overtime_hours": wd["overtime_hours"],
            "total_hours": wd["total_hours"],
            "person_times": wd["person_times"],
            "order_count": wd["order_count"],
            "efficiency": wd["efficiency"],
            "pending_days": wd["pending_days"],
            "labor_cost": wd["labor_cost"],
            "cost_per_order": wd["cost_per_order"],
            "overtime_ratio": wd["overtime_ratio"],
        })
        agg["regular_hours"] += wd["regular_hours"]
        agg["overtime_hours"] += wd["overtime_hours"]
        agg["total_hours"] += wd["total_hours"]
        agg["order_count"] += wd["order_count"]
        agg["pending_days"] += wd["pending_days"]
        agg["labor_cost"] += wd["labor_cost"]

    standard = await _get_standard(db, wh_id, month_str)
    # 月订单数 = 当月每天的订单数加总（直接按天汇总，非按周）
    month_order_count = await _get_period_order_count(db, wh_id, month_start, month_end)
    total_hours = round(agg["total_hours"], 2)
    person_times = round(total_hours / 8.0, 1)
    efficiency = round(month_order_count / person_times, 1) if person_times > 0 else 0.0
    labor_cost = round(agg["labor_cost"], 2)
    cost_per_order = round(labor_cost / month_order_count, 2) if month_order_count > 0 else 0.0
    overtime_ratio = round(agg["overtime_hours"] / total_hours * 100.0, 1) if total_hours > 0 else 0.0
    return {
        "regular_hours": round(agg["regular_hours"], 2),
        "overtime_hours": round(agg["overtime_hours"], 2),
        "total_hours": total_hours,
        "person_times": person_times,
        "order_count": month_order_count,
        "efficiency": efficiency,
        "standard": standard,
        "below_standard": efficiency < standard,
        "pending_days": agg["pending_days"],
        "labor_cost": labor_cost,
        "cost_per_order": cost_per_order,
        "overtime_ratio": overtime_ratio,
        "weeks": week_rows,
    }


# ═══ Endpoints ════════════════════════════

@router.get("/summary")
async def get_summary(
    view: str = Query("week"),
    week_start: str = None,
    month: str = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPER_ADMIN, Role.SUPERVISOR):
        raise HTTPException(403, "只有管理员可以查看人效管理")

    wh_id = get_wh_id(current_user)

    if view == "month":
        if not month:
            month = thai_today().strftime("%Y-%m")
        month_start, month_end = _month_bounds(month)
        if not wh_id:
            return {
                "view": "month", "month": month,
                "period_label": f"{month_start.year}年{month_start.month}月",
                "regular_hours": 0.0, "overtime_hours": 0.0, "total_hours": 0.0,
                "person_times": 0.0, "order_count": 0, "efficiency": 0.0,
                "standard": float(DEFAULT_STANDARD), "below_standard": True, "pending_days": 0,
                "labor_cost": 0.0, "cost_per_order": 0.0, "overtime_ratio": 0.0,
                "weeks": [],
            }
        agg = await _aggregate_month(db, wh_id, month)
        return {
            "view": "month", "month": month,
            "period_label": f"{month_start.year}年{month_start.month}月",
            **agg,
        }

    # week view
    if not week_start:
        week_start = _current_monday().isoformat()
    monday = _parse_week_start(week_start)
    sunday = monday + timedelta(days=6)
    standard = await _get_standard(db, wh_id, monday.strftime("%Y-%m")) if wh_id else float(DEFAULT_STANDARD)
    if not wh_id:
        return {
            "view": "week", "week_start": monday.isoformat(), "week_end": sunday.isoformat(),
            "period_label": _week_label(monday, sunday),
            "regular_hours": 0.0, "overtime_hours": 0.0, "total_hours": 0.0,
            "person_times": 0.0, "order_count": 0, "efficiency": 0.0,
            "standard": standard, "below_standard": True, "pending_days": 0,
            "labor_cost": 0.0, "cost_per_order": 0.0, "overtime_ratio": 0.0,
            "cross_check": None,
            "employees": [],
        }
    wd = await _compute_week(db, wh_id, monday, sunday, include_employees=True)
    cross_check = await _compute_cross_check(db, wh_id, monday)
    return {
        "view": "week", "week_start": monday.isoformat(), "week_end": sunday.isoformat(),
        "period_label": _week_label(monday, sunday),
        "cross_check": cross_check,
        **wd,
    }


def _week_label(monday: date, sunday: date) -> str:
    return f"{monday.isoformat()} ~ {sunday.isoformat()}"


@router.get("/trend")
async def get_trend(
    weeks: int = Query(12, ge=1, le=52),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPER_ADMIN, Role.SUPERVISOR):
        raise HTTPException(403, "只有管理员可以查看人效趋势")
    wh_id = get_wh_id(current_user)

    current = _current_monday()
    rows = []
    if wh_id:
        for i in range(weeks - 1, -1, -1):
            monday = current - timedelta(days=7 * i)
            sunday = monday + timedelta(days=6)
            wd = await _compute_week(db, wh_id, monday, sunday, include_employees=False)
            rows.append({
                "week_start": monday.isoformat(),
                "week_end": sunday.isoformat(),
                "efficiency": wd["efficiency"],
                "order_count": wd["order_count"],
                "person_times": wd["person_times"],
                "total_hours": wd["total_hours"],
                "overtime_hours": wd["overtime_hours"],
                "labor_cost": wd["labor_cost"],
            })
    return {"weeks": rows}


@router.get("/compare")
async def get_compare(
    view: str = Query("week"),
    week_start: str = None,
    month: str = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPER_ADMIN, Role.SUPERVISOR):
        raise HTTPException(403, "只有管理员可以查看多仓库对比")

    wh_ids = get_wh_ids(current_user)
    if not wh_ids:
        return {"view": view, "warehouses": [], "count": 0}

    # 仓库名称
    whs = (await db.execute(select(Warehouse).where(Warehouse.id.in_(wh_ids)))).scalars().all()
    name_map = {w.id: w.name for w in whs}

    results = []
    if view == "month":
        if not month:
            month = thai_today().strftime("%Y-%m")
        for wid in wh_ids:
            agg = await _aggregate_month(db, wid, month)
            results.append({
                "warehouse_id": wid,
                "warehouse_name": name_map.get(wid, ""),
                **{k: agg[k] for k in (
                    "regular_hours", "overtime_hours", "total_hours", "person_times",
                    "order_count", "efficiency", "standard", "below_standard",
                    "labor_cost", "cost_per_order", "overtime_ratio", "pending_days",
                )},
            })
    else:
        if not week_start:
            week_start = _current_monday().isoformat()
        monday = _parse_week_start(week_start)
        sunday = monday + timedelta(days=6)
        for wid in wh_ids:
            wd = await _compute_week(db, wid, monday, sunday, include_employees=False)
            results.append({
                "warehouse_id": wid,
                "warehouse_name": name_map.get(wid, ""),
                **{k: wd[k] for k in (
                    "regular_hours", "overtime_hours", "total_hours", "person_times",
                    "order_count", "efficiency", "standard", "below_standard",
                    "labor_cost", "cost_per_order", "overtime_ratio", "pending_days",
                )},
            })

    # 按人效降序排序，方便横向比较
    results.sort(key=lambda x: x.get("efficiency") or 0, reverse=True)
    return {"view": view, "week_start": week_start if view != "month" else None,
            "month": month if view == "month" else None, "warehouses": results, "count": len(results)}


@router.get("/daily-orders")
async def get_daily_orders(
    month: str = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPER_ADMIN, Role.SUPERVISOR):
        raise HTTPException(403, "只有管理员可以查看订单数")
    wh_id = get_wh_id(current_user)
    if not month:
        month = thai_today().strftime("%Y-%m")
    month_start, month_end = _month_bounds(month)
    if not wh_id:
        return {"month": month, "daily": {}}
    daily_map = await _get_daily_orders(db, wh_id, month_start, month_end)
    return {"month": month, "daily": {d.isoformat(): c for d, c in daily_map.items()}}


@router.put("/order-count")
async def set_order_count(
    req: OrderCountSet,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPER_ADMIN, Role.SUPERVISOR):
        raise HTTPException(403, "只有管理员可以录入订单数")
    wh_id = get_wh_id(current_user)
    if not wh_id:
        raise HTTPException(400, "请先选择仓库")
    try:
        d = datetime.strptime(req.date, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        raise HTTPException(400, "日期格式错误，应为 YYYY-MM-DD")
    if req.order_count < 0:
        raise HTTPException(400, "订单数不能为负数")

    row = (await db.execute(
        select(EfficiencyOrderCount).where(
            EfficiencyOrderCount.warehouse_id == wh_id,
            EfficiencyOrderCount.date == d,
        )
    )).scalar_one_or_none()
    if row:
        row.order_count = req.order_count
        row.updated_by = current_user.id
    else:
        db.add(EfficiencyOrderCount(
            warehouse_id=wh_id,
            date=d,
            order_count=req.order_count,
            updated_by=current_user.id,
        ))
    await db.flush()
    return {"message": f"已保存 {d.isoformat()} 订单数 {req.order_count}", "date": d.isoformat(), "order_count": req.order_count}


@router.get("/standard")
async def get_standard(
    month: str = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPER_ADMIN, Role.SUPERVISOR):
        raise HTTPException(403, "只有管理员可以查看人效标准")
    wh_id = get_wh_id(current_user)
    standard = await _get_standard(db, wh_id, month) if wh_id else float(DEFAULT_STANDARD)
    return {"standard": standard, "month": month}


@router.get("/standards")
async def get_standards(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPER_ADMIN, Role.SUPERVISOR):
        raise HTTPException(403, "只有管理员可以查看人效标准")
    wh_id = get_wh_id(current_user)
    default = await _get_standard(db, wh_id) if wh_id else float(DEFAULT_STANDARD)
    monthly = {}
    if wh_id:
        rows = (await db.execute(
            select(SystemSetting).where(
                SystemSetting.warehouse_id == wh_id,
                SystemSetting.key.like("efficiency_standard_%"),
            )
        )).scalars().all()
        for r in rows:
            month_key = r.key.replace("efficiency_standard_", "")
            if len(month_key) == 7:
                try:
                    monthly[month_key] = float(r.value)
                except (ValueError, TypeError):
                    pass
    return {"default": default, "monthly": monthly}


@router.put("/standard")
async def set_standard(
    req: StandardSet,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPER_ADMIN, Role.SUPERVISOR):
        raise HTTPException(403, "只有管理员可以修改人效标准")
    wh_id = get_wh_id(current_user)
    if not wh_id:
        raise HTTPException(400, "请先选择仓库")
    if req.standard < 0:
        raise HTTPException(400, "标准值不能为负数")

    if req.month:
        try:
            y, m = req.month.split("-")
            _year, _month = int(y), int(m)
            if _month < 1 or _month > 12:
                raise ValueError
        except (ValueError, TypeError):
            raise HTTPException(400, "月份格式错误，应为 YYYY-MM")
        key = f"efficiency_standard_{req.month}"
    else:
        key = "efficiency_standard"

    setting = (await db.execute(
        select(SystemSetting).where(
            SystemSetting.warehouse_id == wh_id,
            SystemSetting.key == key,
        )
    )).scalar_one_or_none()
    if setting:
        setting.value = str(req.standard)
        setting.updated_by = current_user.id
    else:
        db.add(SystemSetting(
            warehouse_id=wh_id,
            key=key,
            value=str(req.standard),
            updated_by=current_user.id,
        ))
    await db.flush()
    label = f"{req.month} 月" if req.month else "默认"
    return {"message": f"人效标准（{label}）已设为 {req.standard}", "standard": req.standard, "month": req.month}


@router.put("/manual-hour")
async def set_manual_hour(
    req: ManualHourSet,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPER_ADMIN, Role.SUPERVISOR):
        raise HTTPException(403, "只有管理员可以补录工时")
    wh_id = get_wh_id(current_user)
    if not wh_id:
        raise HTTPException(400, "请先选择仓库")

    try:
        d = datetime.strptime(req.date, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        raise HTTPException(400, "日期格式错误，应为 YYYY-MM-DD")
    if req.hours < 0:
        raise HTTPException(400, "工时不能为负数")

    emp = (await db.execute(
        select(Employee).where(Employee.id == req.employee_id, Employee.warehouse_id == wh_id, Employee.is_deleted == False)
    )).scalar_one_or_none()
    if not emp:
        raise HTTPException(400, "员工不存在或不属于当前仓库")

    row = (await db.execute(
        select(EfficiencyManualHour).where(
            EfficiencyManualHour.employee_id == req.employee_id,
            EfficiencyManualHour.date == d,
        )
    )).scalar_one_or_none()
    if row:
        row.hours = req.hours
        row.operator_id = current_user.id
    else:
        db.add(EfficiencyManualHour(
            warehouse_id=wh_id,
            employee_id=req.employee_id,
            date=d,
            hours=req.hours,
            operator_id=current_user.id,
        ))
    await db.flush()
    return {
        "message": f"已补录 {emp.name} {d.isoformat()} 工时 {req.hours}h",
        "employee_id": req.employee_id, "date": d.isoformat(), "hours": req.hours,
    }


@router.delete("/manual-hour")
async def delete_manual_hour(
    employee_id: int = Query(...),
    date: str = Query(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPER_ADMIN, Role.SUPERVISOR):
        raise HTTPException(403, "只有管理员可以清除补录")
    wh_id = get_wh_id(current_user)
    if not wh_id:
        raise HTTPException(400, "请先选择仓库")

    try:
        d = datetime.strptime(date, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        raise HTTPException(400, "日期格式错误，应为 YYYY-MM-DD")

    row = (await db.execute(
        select(EfficiencyManualHour).where(
            EfficiencyManualHour.employee_id == employee_id,
            EfficiencyManualHour.date == d,
            EfficiencyManualHour.warehouse_id == wh_id,
        )
    )).scalar_one_or_none()
    if row:
        await db.delete(row)
        await db.flush()
    return {"message": "已清除补录", "employee_id": employee_id, "date": d.isoformat()}

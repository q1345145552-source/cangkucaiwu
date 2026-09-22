from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from app.database import get_db
from app.models.overtime import OvertimeTask, OvertimeAssignment
from app.models.employee import Employee
from app.models.user import User
from app.core.permissions import get_current_user, get_wh_id, get_wh_ids, Role
from app.core.messages import t, get_request_lang
from pydantic import BaseModel, field_validator
from app.core.timezone import thai_now, thai_today
from datetime import datetime, date
from typing import Optional, List

router = APIRouter()


# ═══ Schemas ════════════════════════════

class OvertimeCreate(BaseModel):
    employee_ids: List[int]
    date: str  # YYYY-MM-DD
    start_time: str  # HH:MM
    end_time: str  # HH:MM
    hourly_rate: float = 75

    @field_validator("start_time", "end_time")
    @classmethod
    def validate_time_format(cls, v: str) -> str:
        try:
            datetime.strptime(v, "%H:%M")
        except ValueError:
            raise ValueError(f"时间格式错误: {v}，应为 HH:MM")
        return v


class OvertimeLimitSet(BaseModel):
    max_hours: float


# 加班费固定算法：整小时部分 75泰铢/小时，不足1小时零头固定 37泰铢
def _calc_overtime_pay(total_minutes: int) -> float:
    full_hours = total_minutes // 60
    remainder = total_minutes % 60
    return full_hours * 75 + (37 if remainder > 0 else 0)


# ═══ Admin: Create Overtime ═══════════

@router.post("")
async def create_overtime(
    req: OvertimeCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
        raise HTTPException(403, "只有仓库管理员可以发起加班")

    wh_id = get_wh_id(current_user)
    if not wh_id:
        raise HTTPException(400, "请先选择仓库")

    # Parse date
    try:
        ot_date = datetime.strptime(req.date, "%Y-%m-%d").date()
    except:
        raise HTTPException(400, "日期格式错误")

    # Calculate hours
    try:
        start_h, start_m = map(int, req.start_time.split(":"))
        end_h, end_m = map(int, req.end_time.split(":"))
        total_minutes = (end_h * 60 + end_m) - (start_h * 60 + start_m)
        if total_minutes <= 0:
            raise HTTPException(400, "结束时间必须晚于开始时间")
        hours = total_minutes / 60
    except (ValueError, TypeError):
        raise HTTPException(400, "时间格式错误")

    # Validate employees belong to this warehouse（排除已删除）
    employees = (await db.execute(
        select(Employee).where(
            Employee.id.in_(req.employee_ids),
            Employee.warehouse_id == wh_id,
            Employee.status != "resigned",
            Employee.is_deleted == False,
        )
    )).scalars().all()
    if len(employees) != len(req.employee_ids):
        raise HTTPException(400, "部分员工不存在或已离职")

    # Check monthly overtime limit（按员工档案统计，不管有没有登录账号都检查）
    limit_hours = await _get_monthly_limit(db, wh_id)

    for emp in employees:
        month_overtime = await _get_monthly_overtime_hours_by_employee(db, emp.id, ot_date)
        if month_overtime + hours > limit_hours:
            raise HTTPException(
                400,
                f"员工 {emp.name} 本月累计加班 {month_overtime:.1f}h，"
                f"加上本次 {hours:.1f}h 将超过上限 {limit_hours:.0f}h"
            )

    # Create overtime task
    task = OvertimeTask(
        warehouse_id=wh_id,
        date=ot_date,
        start_time=req.start_time,
        end_time=req.end_time,
        hours=hours,
        hourly_rate=75,
        status="pending",
        created_by=current_user.id,
    )
    db.add(task)
    await db.flush()

    # Create assignments
    earned = _calc_overtime_pay(total_minutes)
    for emp in employees:
        linked_user = await _find_linked_user(db, emp)
        assignment = OvertimeAssignment(
            overtime_id=task.id,
            employee_id=emp.id,
            user_id=linked_user.id if linked_user else None,
            earned_amount=earned,
        )
        db.add(assignment)

    await db.flush()
    return {
        "message": "加班任务创建成功",
        "id": task.id,
        "hours": hours,
        "employee_count": len(employees),
        "total_amount": round(earned * len(employees), 2),
    }


# ═══ Employee: Confirm Attendance ═══════════

@router.post("/{overtime_id}/confirm")
async def confirm_overtime(
    overtime_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    lang = get_request_lang(request)
    if current_user.role not in (Role.WAREHOUSE_LABOR,):
        raise HTTPException(403, t("overtime_only_labor", lang))

    wh_id = get_wh_id(current_user)
    if not wh_id:
        raise HTTPException(400, "请先选择仓库")

    task = (await db.execute(
        select(OvertimeTask).where(
            OvertimeTask.id == overtime_id,
            OvertimeTask.warehouse_id == wh_id,
        )
    )).scalar_one_or_none()
    if not task:
        raise HTTPException(404, "加班任务不存在")

    # 先找到登录用户对应的员工档案（绑定账号优先，姓名兜底），再按员工档案找分配记录
    emp = await _find_employee_for_user(db, wh_id, current_user)
    if not emp:
        raise HTTPException(400, "未找到您的员工档案，无法确认加班")

    assignment = (await db.execute(
        select(OvertimeAssignment).where(
            OvertimeAssignment.overtime_id == overtime_id,
            OvertimeAssignment.employee_id == emp.id,
        )
    )).scalar_one_or_none()
    if not assignment:
        raise HTTPException(400, "您未被分配该加班任务")

    if assignment.confirmed:
        raise HTTPException(400, "您已确认过该加班任务")

    assignment.confirmed = True
    assignment.confirmed_at = thai_now()
    await db.flush()

    # Check if all confirmed → mark task completed
    all_confirmed = (await db.execute(
        select(func.count(OvertimeAssignment.id)).where(
            OvertimeAssignment.overtime_id == overtime_id,
            OvertimeAssignment.confirmed == False,
        )
    )).scalar()
    if all_confirmed == 0:
        task.status = "completed"

    await db.flush()
    return {
        "message": t("overtime_confirm_success", lang, amount=f"{assignment.earned_amount:.0f}"),
        "earned_amount": assignment.earned_amount,
        "confirmed_at": assignment.confirmed_at.isoformat(),
    }


# ═══ List Overtime Tasks ═══════════

@router.get("")
async def list_overtimes(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    status: str = None,
    month: str = None,  # YYYY-MM
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role == Role.WAREHOUSE_LABOR:
        # Employees see their assigned tasks（按员工档案匹配，账号换绑也能看到）
        emp = await _find_employee_for_user(db, get_wh_id(current_user), current_user)
        if not emp:
            return {"data": [], "total": 0, "page": page, "page_size": page_size}
        query = (
            select(OvertimeTask)
            .join(OvertimeAssignment, OvertimeAssignment.overtime_id == OvertimeTask.id)
            .where(OvertimeAssignment.employee_id == emp.id)
            .distinct()
        )
        count_q = (
            select(func.count(func.distinct(OvertimeTask.id)))
            .join(OvertimeAssignment, OvertimeAssignment.overtime_id == OvertimeTask.id)
            .where(OvertimeAssignment.employee_id == emp.id)
        )
    else:
        wh_ids = get_wh_ids(current_user)
        query = select(OvertimeTask).where(OvertimeTask.warehouse_id.in_(wh_ids))
        count_q = select(func.count(OvertimeTask.id)).where(OvertimeTask.warehouse_id.in_(wh_ids))

    if status:
        query = query.where(OvertimeTask.status == status)
        count_q = count_q.where(OvertimeTask.status == status)
    if month:
        try:
            y, m = month.split("-")
            month_start = date(int(y), int(m), 1)
            if m == "12":
                month_end = date(int(y) + 1, 1, 1)
            else:
                month_end = date(int(y), int(m) + 1, 1)
            query = query.where(OvertimeTask.date >= month_start, OvertimeTask.date < month_end)
            count_q = count_q.where(OvertimeTask.date >= month_start, OvertimeTask.date < month_end)
        except:
            pass

    total = (await db.execute(count_q)).scalar()
    result = await db.execute(
        query.order_by(OvertimeTask.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    tasks = result.unique().scalars().all()

    # Collect linked user info
    creator_ids = {t.created_by for t in tasks}
    creators = {}
    if creator_ids:
        us = (await db.execute(select(User).where(User.id.in_(creator_ids)))).scalars().all()
        creators = {u.id: u.display_name for u in us}

    task_ids = [t.id for t in tasks]
    assign_map = {}
    if task_ids:
        assigns = (await db.execute(
            select(OvertimeAssignment).where(OvertimeAssignment.overtime_id.in_(task_ids))
        )).scalars().all()
        emp_ids = {a.employee_id for a in assigns}
        emps = {}
        if emp_ids:
            es = (await db.execute(select(Employee).where(Employee.id.in_(emp_ids)))).scalars().all()
            emps = {e.id: e.name for e in es}
        for a in assigns:
            if a.overtime_id not in assign_map:
                assign_map[a.overtime_id] = []
            assign_map[a.overtime_id].append({
                "id": a.id,
                "employee_id": a.employee_id,
                "employee_name": emps.get(a.employee_id, ""),
                "confirmed": a.confirmed,
                "confirmed_at": a.confirmed_at.isoformat() if a.confirmed_at else None,
                "earned_amount": a.earned_amount,
            })

    return {
        "data": [{
            "id": t.id,
            "warehouse_id": t.warehouse_id,
            "date": t.date.isoformat(),
            "start_time": t.start_time,
            "end_time": t.end_time,
            "hours": t.hours,
            "hourly_rate": t.hourly_rate,
            "status": t.status,
            "created_by": t.created_by,
            "creator_name": creators.get(t.created_by, ""),
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "assignments": assign_map.get(t.id, []),
            "confirmed_count": sum(1 for a in assign_map.get(t.id, []) if a["confirmed"]),
            "total_assignments": len(assign_map.get(t.id, [])),
        } for t in tasks],
        "total": total or 0,
        "page": page,
    }


# ═══ Pending Tasks for Current User ═══════════

@router.get("/pending")
async def pending_overtimes(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in (Role.WAREHOUSE_LABOR,):
        raise HTTPException(403, "无权限")

    wh_id = get_wh_id(current_user)
    if not wh_id:
        return {"data": [], "pending_count": 0}

    # 先找到员工档案，再按员工档案找未确认的分配（账号换绑也能找到）
    emp = await _find_employee_for_user(db, wh_id, current_user)
    if not emp:
        return {"data": [], "pending_count": 0}

    # Find tasks where this employee has unconfirmed assignments
    sub = (
        select(OvertimeAssignment.overtime_id)
        .where(
            OvertimeAssignment.employee_id == emp.id,
            OvertimeAssignment.confirmed == False,
        )
        .subquery()
    )
    tasks = (await db.execute(
        select(OvertimeTask).where(
            OvertimeTask.id.in_(select(sub.c.overtime_id)),
            OvertimeTask.warehouse_id == wh_id,
        ).order_by(OvertimeTask.date.desc())
    )).scalars().all()

    return {
        "data": [{
            "id": t.id,
            "date": t.date.isoformat(),
            "start_time": t.start_time,
            "end_time": t.end_time,
            "hours": t.hours,
            "hourly_rate": t.hourly_rate,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        } for t in tasks],
        "pending_count": len(tasks),
    }


# ═══ Monthly Overtime Hours for Employee ═══════════

@router.get("/monthly-hours")
async def monthly_hours(
    month: str = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if month is None:
        month = thai_today().strftime("%Y-%m")

    if current_user.role == Role.WAREHOUSE_LABOR:
        emp = await _find_employee_for_user(db, get_wh_id(current_user), current_user)
        if not emp:
            return {"month": month, "total_hours": 0, "employee_id": None}
        hours = await _get_monthly_overtime_hours_by_employee(db, emp.id, month + "-01")
        return {"month": month, "total_hours": round(hours, 1), "employee_id": emp.id}

    wh_ids = get_wh_ids(current_user)
    y, m = month.split("-")
    month_start = date(int(y), int(m), 1)
    if m == "12":
        month_end = date(int(y) + 1, 1, 1)
    else:
        month_end = date(int(y), int(m) + 1, 1)

    rows = (await db.execute(
        select(
            OvertimeAssignment.employee_id,
            func.sum(OvertimeTask.hours).label("total_hours"),
            func.sum(OvertimeAssignment.earned_amount).label("total_amount"),
            func.count(OvertimeAssignment.id).label("task_count"),
        )
        .join(OvertimeTask, OvertimeTask.id == OvertimeAssignment.overtime_id)
        .where(
            OvertimeTask.warehouse_id.in_(wh_ids),
            OvertimeAssignment.confirmed == True,
            OvertimeTask.date >= month_start,
            OvertimeTask.date < month_end,
        )
        .group_by(OvertimeAssignment.employee_id)
    )).all()

    emp_ids = [r.employee_id for r in rows]
    emp_map = {}
    if emp_ids:
        es = (await db.execute(select(Employee).where(Employee.id.in_(emp_ids)))).scalars().all()
        emp_map = {e.id: e.name for e in es}

    return {
        "month": month,
        "data": [{
            "employee_id": r.employee_id,
            "employee_name": emp_map.get(r.employee_id, ""),
            "total_hours": round(r.total_hours or 0, 1),
            "total_amount": r.total_amount or 0,
            "task_count": r.task_count or 0,
        } for r in rows],
    }


# ═══ Monthly Overtime Limit ═══════════

@router.get("/limit")
async def get_overtime_limit(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    wh_id = get_wh_id(current_user)
    if not wh_id:
        return {"max_hours": 50}
    limit = await _get_monthly_limit(db, wh_id)
    return {"max_hours": limit, "warehouse_id": wh_id}


@router.put("/limit")
async def set_overtime_limit(
    req: OvertimeLimitSet,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
        raise HTTPException(403, "只有仓库管理员可以设置加班上限")

    wh_id = get_wh_id(current_user)
    if not wh_id:
        raise HTTPException(400, "请先选择仓库")

    from app.models.expense_fund import SystemSetting
    setting = (await db.execute(
        select(SystemSetting).where(
            SystemSetting.warehouse_id == wh_id,
            SystemSetting.key == "overtime_monthly_limit",
        )
    )).scalar_one_or_none()

    if setting:
        setting.value = str(req.max_hours)
        setting.updated_by = current_user.id
        setting.updated_at = thai_now()
    else:
        setting = SystemSetting(
            warehouse_id=wh_id,
            key="overtime_monthly_limit",
            value=str(req.max_hours),
            updated_by=current_user.id,
        )
        db.add(setting)

    await db.flush()
    return {"message": f"加班上限已设为 {req.max_hours:.0f} 小时/月", "max_hours": req.max_hours}


# ═══ Delete Overtime Task ═══════════

@router.delete("/{overtime_id}")
async def delete_overtime(
    overtime_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
        raise HTTPException(403, "只有仓库管理员可以删除加班任务")

    wh_ids = get_wh_ids(current_user)
    task = (await db.execute(
        select(OvertimeTask).where(
            OvertimeTask.id == overtime_id,
            OvertimeTask.warehouse_id.in_(wh_ids),
        )
    )).scalar_one_or_none()
    if not task:
        raise HTTPException(404, "加班任务不存在")

    # Delete assignments first (cascade should handle, but explicit is safer)
    assigns = (await db.execute(
        select(OvertimeAssignment).where(OvertimeAssignment.overtime_id == overtime_id)
    )).scalars().all()
    for a in assigns:
        await db.delete(a)

    await db.delete(task)
    await db.flush()
    return {"message": "加班任务已删除"}


# ═══ Helpers ═══════════

async def _find_linked_user(db: AsyncSession, emp: Employee):
    """Find the User linked to this employee via Employee.user_id, fallback to name/phone"""
    # Primary: use formal Employee.user_id link
    if emp.user_id:
        user = (await db.execute(
            select(User).where(
                User.id == emp.user_id,
                User.role == "warehouse_labor",
                User.is_active == True,
            )
        )).scalar_one_or_none()
        if user:
            return user
    # Fallback 1: name matching within same warehouse
    user = (await db.execute(
        select(User).where(
            User.warehouse_id == emp.warehouse_id,
            User.display_name == emp.name,
            User.role == "warehouse_labor",
            User.is_active == True,
        )
    )).scalar_one_or_none()
    if not user and emp.phone:
        user = (await db.execute(
            select(User).where(
                User.username == emp.phone,
                User.role == "warehouse_labor",
                User.is_active == True,
            )
        )).scalar_one_or_none()
    return user


async def _find_employee_for_user(db: AsyncSession, wh_id: int, user: User):
    """登录用户 → 员工档案：优先绑定账号(user_id)，姓名兜底。"""
    emp = (await db.execute(
        select(Employee).where(
            Employee.warehouse_id == wh_id,
            Employee.user_id == user.id,
            Employee.is_deleted == False,
        )
    )).scalar_one_or_none()
    if not emp:
        emp = (await db.execute(
            select(Employee).where(
                Employee.warehouse_id == wh_id,
                Employee.name == user.display_name,
                Employee.is_deleted == False,
            )
        )).scalar_one_or_none()
    return emp


async def _get_monthly_overtime_hours_by_employee(db: AsyncSession, employee_id: int, month_str_or_date) -> float:
    """按员工档案统计某员工本月已分配的加班小时数（不管账号，不管是否确认）。"""
    if isinstance(month_str_or_date, str):
        d = datetime.strptime(month_str_or_date, "%Y-%m-%d").date()
    else:
        d = month_str_or_date
    month_start = d.replace(day=1)
    if month_start.month == 12:
        month_end = month_start.replace(year=month_start.year + 1, month=1, day=1)
    else:
        month_end = month_start.replace(month=month_start.month + 1, day=1)

    result = (await db.execute(
        select(func.sum(OvertimeTask.hours))
        .join(OvertimeAssignment, OvertimeTask.id == OvertimeAssignment.overtime_id)
        .where(
            OvertimeAssignment.employee_id == employee_id,
            OvertimeTask.date >= month_start,
            OvertimeTask.date < month_end,
        )
    )).scalar()
    return float(result or 0)


async def _get_monthly_limit(db: AsyncSession, warehouse_id: int) -> float:
    from app.models.expense_fund import SystemSetting
    setting = (await db.execute(
        select(SystemSetting).where(
            SystemSetting.warehouse_id == warehouse_id,
            SystemSetting.key == "overtime_monthly_limit",
        )
    )).scalar_one_or_none()
    try:
        return float(setting.value) if setting else 50
    except (ValueError, TypeError):
        return 50


async def _get_monthly_overtime_hours(db: AsyncSession, user_id: int, month_str_or_date) -> float:
    if isinstance(month_str_or_date, str):
        d = datetime.strptime(month_str_or_date, "%Y-%m-%d").date()
    else:
        d = month_str_or_date
    month_start = d.replace(day=1)
    if month_start.month == 12:
        month_end = month_start.replace(year=month_start.year + 1, month=1, day=1)
    else:
        month_end = month_start.replace(month=month_start.month + 1, day=1)

    result = (await db.execute(
        select(func.sum(OvertimeTask.hours))
        .join(OvertimeAssignment, OvertimeTask.id == OvertimeAssignment.overtime_id)
        .where(
            OvertimeAssignment.user_id == user_id,
            OvertimeAssignment.confirmed == True,
            OvertimeTask.date >= month_start,
            OvertimeTask.date < month_end,
        )
    )).scalar()
    total = result or 0
    return float(total)

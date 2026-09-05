from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from app.database import get_db
from app.models.attendance import LeaveRequest, RestDay, Absence
from app.models.employee import Employee
from app.models.clock_in_records import ClockInRecord
from app.models.user import User
from app.models.warehouse import Warehouse

from app.core.permissions import get_current_user, get_wh_id, get_wh_ids, Role
from pydantic import BaseModel
from app.core.timezone import thai_now, thai_today
from datetime import datetime, date, timedelta
from typing import Optional, List
import os, uuid

router = APIRouter()

UPLOAD_DIR = "/app/uploads"

# ═══ Leave Request ════════════════════════════
class LeaveCreate(BaseModel):
    leave_date: str  # YYYY-MM-DD
    reason: Optional[str] = None

@router.post("/leaves")
async def create_leave(
    leave_date: str = Form(...),
    reason: str = Form(None),
    file: UploadFile = File(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in (Role.WAREHOUSE_LABOR, Role.STAFF):
        raise HTTPException(403, "无权限")

    wh_id = get_wh_id(current_user)
    if not wh_id:
        raise HTTPException(400, "请先选择仓库")

    # Find employee record for this user
    emp = (await db.execute(
        select(Employee).where(Employee.warehouse_id == wh_id, Employee.phone == current_user.username)
    )).scalar_one_or_none()
    if not emp:
        # Try matching by name
        emp = (await db.execute(
            select(Employee).where(Employee.warehouse_id == wh_id, Employee.name == current_user.display_name)
        )).scalar_one_or_none()
    if not emp:
        raise HTTPException(400, "未找到您的员工档案，请联系管理员")

    try:
        leave_dt = datetime.strptime(leave_date, "%Y-%m-%d").date()
    except:
        raise HTTPException(400, "日期格式错误")

    # Check max 1 sick leave per month
    range_start = leave_dt.replace(day=1)
    month_leaves = (await db.execute(
        select(func.count(LeaveRequest.id)).where(
            LeaveRequest.employee_id == emp.id,
            LeaveRequest.leave_date >= range_start,
            LeaveRequest.leave_date < (range_start.replace(month=range_start.month % 12 + 1, day=1) if range_start.month < 12 else range_start.replace(year=range_start.year + 1, month=1, day=1)),
            LeaveRequest.status != "rejected",
        )
    )).scalar()
    if (month_leaves or 0) >= 1:
        raise HTTPException(400, "本月已请过一次病假，每月最多1天")

    # Check duplicate date
    dup = (await db.execute(
        select(LeaveRequest).where(
            LeaveRequest.employee_id == emp.id,
            LeaveRequest.leave_date == leave_dt,
            LeaveRequest.status != "rejected",
        )
    )).scalar_one_or_none()
    if dup:
        raise HTTPException(400, "该日期已提交请假申请")

    # Save photo
    photo_path = None
    if file:
        try:
            ext = file.filename.split(".")[-1].lower() if file.filename else "jpg"
            content = await file.read()
            today_str = thai_today().isoformat()
            subdir = os.path.join(UPLOAD_DIR, str(wh_id), today_str, "leaves")
            os.makedirs(subdir, exist_ok=True)
            fname = f"{uuid.uuid4().hex}.{ext}"
            fpath = os.path.join(subdir, fname)
            with open(fpath, "wb") as f:
                f.write(content)
            photo_path = f"uploads/{wh_id}/{today_str}/leaves/{fname}"
        except:
            pass

    lr = LeaveRequest(
        warehouse_id=wh_id, employee_id=emp.id,
        leave_date=leave_dt, leave_type="sick",
        photo_path=photo_path, reason=reason, status="pending",
    )
    db.add(lr)
    await db.flush()
    return {"message": "请假申请已提交，等待审批", "id": lr.id}

@router.get("/leaves")
async def list_leaves(
    start_date: str = None,
    end_date: str = None,
    status: str = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(LeaveRequest, Employee.name).join(Employee, LeaveRequest.employee_id == Employee.id)
    if current_user.role == Role.SUPER_ADMIN:
        pass  # super_admin sees all
    elif current_user.role in (Role.WAREHOUSE_LABOR, Role.STAFF):
        wh_id = get_wh_id(current_user)
        # Use user_id link first, fallback to name matching
        emp = (await db.execute(
            select(Employee).where(
                Employee.warehouse_id == wh_id,
                Employee.user_id == current_user.id,
            )
        )).scalar_one_or_none()
        if not emp:
            emp = (await db.execute(
                select(Employee).where(Employee.warehouse_id == wh_id, Employee.name == current_user.display_name)
            )).scalar_one_or_none()
        if emp:
            query = query.where(LeaveRequest.employee_id == emp.id)
        else:
            return {"data": []}
    else:
        # Use active (header-selected) warehouse for warehouse_admin
        active_wh = get_wh_id(current_user)
        if active_wh:
            query = query.where(LeaveRequest.warehouse_id == active_wh)

    if start_date:
        query = query.where(LeaveRequest.leave_date >= datetime.strptime(start_date, "%Y-%m-%d").date())
    if end_date:
        query = query.where(LeaveRequest.leave_date <= datetime.strptime(end_date, "%Y-%m-%d").date())
    if status:
        query = query.where(LeaveRequest.status == status)

    result = await db.execute(query.order_by(LeaveRequest.created_at.desc()))
    rows = result.all()
    return {"data": [{
        "id": r.id, "employee_id": r.employee_id, "employee_name": name,
        "leave_date": r.leave_date.isoformat(), "leave_type": r.leave_type,
        "photo_path": r.photo_path, "status": r.status, "reason": r.reason,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    } for r, name in rows]}

@router.put("/leaves/{leave_id}/approve")
async def approve_leave(leave_id: int, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if current_user.role not in (Role.WAREHOUSE_ADMIN,):
        raise HTTPException(403, "只有管理员可以审批")
    lr = (await db.execute(select(LeaveRequest).where(LeaveRequest.id == leave_id))).scalar_one_or_none()
    if not lr: raise HTTPException(404, "请假申请不存在")
    wh_ids = get_wh_ids(current_user)
    if lr.warehouse_id not in wh_ids: raise HTTPException(403, "无权审批其他仓库的申请")
    lr.status = "approved"
    lr.reviewed_by = current_user.id
    lr.reviewed_at = thai_now()
    await db.flush()
    return {"message": "已批准"}

@router.put("/leaves/{leave_id}/reject")
async def reject_leave(leave_id: int, reason: str = Form(None), current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if current_user.role not in (Role.WAREHOUSE_ADMIN,):
        raise HTTPException(403, "只有管理员可以审批")
    lr = (await db.execute(select(LeaveRequest).where(LeaveRequest.id == leave_id))).scalar_one_or_none()
    if not lr: raise HTTPException(404, "请假申请不存在")
    wh_ids = get_wh_ids(current_user)
    if lr.warehouse_id not in wh_ids: raise HTTPException(403, "无权审批其他仓库的申请")
    lr.status = "rejected"
    lr.reason = reason or lr.reason
    lr.reviewed_by = current_user.id
    lr.reviewed_at = thai_now()
    await db.flush()
    return {"message": "已驳回"}

# ═══ Rest Days ════════════════════════════════
class RestDayCreate(BaseModel):
    employee_id: int
    rest_dates: List[str]  # YYYY-MM-DD list

@router.post("/rest-days")
async def set_rest_days(
    req: RestDayCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in (Role.WAREHOUSE_ADMIN,):
        raise HTTPException(403, "只有管理员可以设置休息日")
    wh_id = get_wh_id(current_user)
    if not wh_id: raise HTTPException(400, "请先选择仓库")

    # Validate employee
    emp = (await db.execute(select(Employee).where(Employee.id == req.employee_id, Employee.warehouse_id == wh_id))).scalar_one_or_none()
    if not emp: raise HTTPException(404, "员工不存在")

    # Check current month rest day count
    if req.rest_dates:
        first_date = datetime.strptime(req.rest_dates[0], "%Y-%m-%d").date().replace(day=1)
        existing = (await db.execute(
            select(func.count(RestDay.id)).where(
                RestDay.employee_id == req.employee_id,
                RestDay.rest_date >= first_date,
                RestDay.rest_date < (first_date.replace(month=first_date.month % 12 + 1, day=1) if first_date.month < 12 else first_date.replace(year=first_date.year + 1, month=1, day=1)),
            )
        )).scalar() or 0
        if existing + len(req.rest_dates) > 2:
            raise HTTPException(400, f"每月最多2天休息日，当前已设置{existing}天，不能再增加{len(req.rest_dates)}天")

    added = 0
    for ds in req.rest_dates:
        try:
            dt = datetime.strptime(ds, "%Y-%m-%d").date()
        except:
            continue
        dup = (await db.execute(
            select(RestDay).where(RestDay.employee_id == req.employee_id, RestDay.rest_date == dt)
        )).scalar_one_or_none()
        if not dup:
            db.add(RestDay(warehouse_id=wh_id, employee_id=req.employee_id, rest_date=dt, created_by=current_user.id))
            added += 1
    await db.flush()
    return {"message": f"已设置 {added} 天休息日", "added": added}

@router.get("/rest-days")
async def list_rest_days(
    start_date: str = None,
    end_date: str = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.STAFF, Role.WAREHOUSE_LABOR, Role.SUPER_ADMIN):
        raise HTTPException(403, "无权限")

    query = select(RestDay, Employee.name).join(Employee, RestDay.employee_id == Employee.id)
    if current_user.role == Role.WAREHOUSE_ADMIN:
        active_wh = get_wh_id(current_user)
        if active_wh:
            query = query.where(RestDay.warehouse_id == active_wh)
    else:
        wh_id = get_wh_id(current_user)
        emp = (await db.execute(
            select(Employee.id).where(Employee.warehouse_id == wh_id, Employee.name == current_user.display_name)
        )).scalar_one_or_none()
        if emp:
            query = query.where(RestDay.employee_id == emp)
        else:
            return {"data": []}

    if start_date:
        query = query.where(RestDay.rest_date >= datetime.strptime(start_date, "%Y-%m-%d").date())
    if end_date:
        query = query.where(RestDay.rest_date <= datetime.strptime(end_date, "%Y-%m-%d").date())

    result = await db.execute(query.order_by(RestDay.rest_date))
    rows = result.all()
    return {"data": [{
        "id": r.id, "employee_id": r.employee_id, "employee_name": name,
        "rest_date": r.rest_date.isoformat(),
    } for r, name in rows]}

@router.delete("/rest-days/{rest_day_id}")
async def delete_rest_day(rest_day_id: int, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if current_user.role not in (Role.WAREHOUSE_ADMIN,):
        raise HTTPException(403, "只有管理员可以操作")
    rd = (await db.execute(select(RestDay).where(RestDay.id == rest_day_id))).scalar_one_or_none()
    if not rd: raise HTTPException(404, "休息日不存在")
    wh_ids = get_wh_ids(current_user)
    if rd.warehouse_id not in wh_ids: raise HTTPException(403, "无权操作")
    await db.delete(rd)
    await db.flush()
    return {"message": "已删除"}

# ═══ Absence ════════════════════════════════
class AbsenceCreate(BaseModel):
    employee_id: int
    absence_date: str
    reason: Optional[str] = None

@router.post("/absences")
async def mark_absence(
    req: AbsenceCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in (Role.WAREHOUSE_ADMIN,):
        raise HTTPException(403, "只有管理员可以标记")
    wh_id = get_wh_id(current_user)
    if not wh_id: raise HTTPException(400, "请先选择仓库")

    emp = (await db.execute(select(Employee).where(Employee.id == req.employee_id, Employee.warehouse_id == wh_id))).scalar_one_or_none()
    if not emp: raise HTTPException(404, "员工不存在")

    try:
        dt = datetime.strptime(req.absence_date, "%Y-%m-%d").date()
    except:
        raise HTTPException(400, "日期格式错误")

    dup = (await db.execute(
        select(Absence).where(Absence.employee_id == req.employee_id, Absence.absence_date == dt)
    )).scalar_one_or_none()
    if dup: raise HTTPException(400, "该日期已标记为未到")

    a = Absence(warehouse_id=wh_id, employee_id=req.employee_id, absence_date=dt, reason=req.reason, marked_by=current_user.id)
    db.add(a)
    await db.flush()
    return {"message": "已标记未到", "id": a.id}

@router.delete("/absences/{absence_id}")
async def remove_absence(absence_id: int, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if current_user.role not in (Role.WAREHOUSE_ADMIN,):
        raise HTTPException(403, "无权限")
    a = (await db.execute(select(Absence).where(Absence.id == absence_id))).scalar_one_or_none()
    if not a: raise HTTPException(404, "记录不存在")
    wh_ids = get_wh_ids(current_user)
    if a.warehouse_id not in wh_ids: raise HTTPException(403, "无权操作")
    await db.delete(a)
    await db.flush()
    return {"message": "已删除"}

# ═══ Calendar View ════════════════════════════
@router.get("/calendar")
async def get_calendar(
    start_date: str = None,
    end_date: str = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.STAFF, Role.WAREHOUSE_LABOR, Role.SUPER_ADMIN):
        raise HTTPException(403, "无权限")

    # 默认：当月 1 号到当天
    if start_date:
        try:
            range_start = datetime.strptime(start_date, "%Y-%m-%d").date()
        except:
            raise HTTPException(400, "开始日期格式错误 YYYY-MM-DD")
    else:
        range_start = thai_today().replace(day=1)
    if end_date:
        try:
            range_end = datetime.strptime(end_date, "%Y-%m-%d").date()
        except:
            raise HTTPException(400, "结束日期格式错误 YYYY-MM-DD")
    else:
        range_end = thai_today()
    if range_start > range_end:
        raise HTTPException(400, "开始日期不能晚于结束日期")

    wh_id = get_wh_id(current_user)
    wh_ids = get_wh_ids(current_user)

    # Get employees scoped to the active warehouse
    emp_query = select(Employee).where(Employee.status != "resigned")
    if current_user.role == Role.SUPER_ADMIN:
        pass  # super_admin sees all employees
    elif current_user.role == Role.WAREHOUSE_ADMIN:
        # Use active (header-selected) warehouse, not all warehouses
        active_wh_id = get_wh_id(current_user)
        if active_wh_id:
            emp_query = emp_query.where(Employee.warehouse_id == active_wh_id)
        else:
            emp_query = emp_query.where(Employee.warehouse_id.in_(wh_ids))
    elif current_user.role in (Role.STAFF, Role.WAREHOUSE_LABOR):
        emp = (await db.execute(
            select(Employee.id).where(Employee.warehouse_id == wh_id, Employee.name == current_user.display_name)
        )).scalar_one_or_none()
        if emp:
            emp_query = emp_query.where(Employee.id == emp)
        else:
            return {"employees": [], "events": [], "start_date": start_date, "end_date": end_date}

    emps = (await db.execute(emp_query.order_by(Employee.name))).scalars().all()
    emp_ids = [e.id for e in emps]

    # Build employee_id -> user_id mapping (match by employee name to user display_name)
    # Build employee_id <-> user_id mapping via the formal Employee.user_id link (NOT name matching)
    emp_to_user = {}  # employee_id -> user_id
    user_to_emp = {}  # user_id -> employee_id
    for e in emps:
        if e.user_id:
            emp_to_user[e.id] = e.user_id
            user_to_emp[e.user_id] = e.id

    # Get all clock-in records for this month, filtered by warehouse_id AND user_ids
    user_ids = list(emp_to_user.values())
    if user_ids:
        clock_records = (await db.execute(
            select(ClockInRecord).where(
                ClockInRecord.warehouse_id.in_(wh_ids),
                ClockInRecord.user_id.in_(user_ids),
                ClockInRecord.clock_date >= range_start,
                ClockInRecord.clock_date <= range_end,
            )
        )).scalars().all()
    else:
        clock_records = []
    clock_map = {}
    for cr in clock_records:
        eid = user_to_emp.get(cr.user_id)
        if eid:
            k = (eid, cr.clock_date)
            if k not in clock_map:
                clock_map[k] = []
            clock_map[k].append(cr)

    # Get leave requests (filtered by warehouse)
    leaves = (await db.execute(
        select(LeaveRequest).where(
            LeaveRequest.warehouse_id.in_(wh_ids),
            LeaveRequest.employee_id.in_(emp_ids),
            LeaveRequest.leave_date >= range_start,
            LeaveRequest.leave_date <= range_end,
            LeaveRequest.status == "approved",
        )
    )).scalars().all()
    leave_set = {(l.employee_id, l.leave_date) for l in leaves}

    # Get rest days (filtered by warehouse)
    rests = (await db.execute(
        select(RestDay).where(
            RestDay.warehouse_id.in_(wh_ids),
            RestDay.employee_id.in_(emp_ids),
            RestDay.rest_date >= range_start,
            RestDay.rest_date <= range_end,
        )
    )).scalars().all()
    rest_set = {(r.employee_id, r.rest_date) for r in rests}

    # Get absences (filtered by warehouse)
    absences = (await db.execute(
        select(Absence).where(
            Absence.warehouse_id.in_(wh_ids),
            Absence.employee_id.in_(emp_ids),
            Absence.absence_date >= range_start,
            Absence.absence_date <= range_end,
        )
    )).scalars().all()
    absence_map = {(a.employee_id, a.absence_date): a for a in absences}

    # Build calendar data
    days = []
    current = range_start
    while current <= range_end:
        day_data = {"date": current.isoformat(), "employees": {}}
        for e in emps:
            key = (e.id, current)
            # Try clock_in via employee_id matching (we need user_id mapping)
            # For now: if employee has a linked user via same name, use that
            # Actually, let me fix: ClockInRecord uses user_id not employee_id
            # We need to match employees to users. Let's do it differently.
            pass
        days.append(day_data)
        current += timedelta(days=1)

    # Better approach: return lists of events mapped by date+employee
    events = {}
    for e in emps:
        for d in range((range_end - range_start).days + 1):
            dt = range_start + timedelta(days=d)
            statuses = []

            # Check leave/rest/absence FIRST (applies to all dates)
            if (e.id, dt) in leave_set:
                statuses.append("leave")
            elif (e.id, dt) in rest_set:
                statuses.append("rest")
            elif (e.id, dt) in absence_map:
                statuses.append("absent")
            # Then check clock-in
            elif (e.id, dt) in clock_map:
                sessions = clock_map[(e.id, dt)]
                has_late = any(cr.status in ("late_half", "late_one") for cr in sessions)
                statuses.append("late" if has_late else "present")
            elif dt <= thai_today():
                # Past date without clock-in
                statuses.append("missing")
            else:
                statuses.append("future")

            status_name_db = statuses[0] if statuses else "future"
            # Map DB names to Chinese
            status_cn = {
                "present": "正常出勤", "late": "迟到", "leave": "请假",
                "rest": "休息日", "absent": "未到", "missing": "未打卡",
                "future": "未到"
            }
            key_str = f"{dt.isoformat()}_{e.id}"
            events[key_str] = {
                "date": dt.isoformat(),
                "employee_id": e.id,
                "employee_name": e.name,
                "status": status_name_db,
                "status_label": status_cn.get(status_name_db, status_name_db),
                "detail": "",
            }
            if (e.id, dt) in absence_map:
                events[key_str]["detail"] = absence_map[(e.id, dt)].reason or ""

    return {
        "start_date": range_start.isoformat(),
        "end_date": range_end.isoformat(),
        "employees": [{"id": e.id, "name": e.name, "position": e.position} for e in emps],
        "events": list(events.values()),
        "summary": {
            "leave_count": len(leave_set),
            "rest_count": len(rest_set),
            "absence_count": len(absences),
        }
    }

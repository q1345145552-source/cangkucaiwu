from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from app.database import get_db
from app.models.attendance import LeaveRequest, RestDay, Absence
from app.models.employee import Employee
from app.models.clock_in_records import ClockInRecord
from app.models.user import User
from app.models.warehouse import Warehouse

from app.core.permissions import get_current_user, get_wh_id, get_wh_ids, Role
from app.core.messages import t, get_request_lang
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
    request: Request,
    leave_date: str = Form(...),
    leave_type: str = Form("sick"),
    reason: str = Form(None),
    duration_type: str = Form("full"),
    hours: str = Form(None),
    file: UploadFile = File(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    lang = get_request_lang(request)
    if current_user.role not in (Role.WAREHOUSE_LABOR, Role.STAFF):
        raise HTTPException(403, t("no_permission", lang))

    if leave_type not in ("sick", "personal"):
        raise HTTPException(400, t("leave_type_invalid", lang))

    if duration_type not in ("full", "morning", "afternoon", "hours"):
        raise HTTPException(400, t("leave_duration_invalid", lang))

    hours_val = None
    if duration_type == "hours":
        try:
            hours_val = float(hours) if hours else None
        except (ValueError, TypeError):
            raise HTTPException(400, t("hours_invalid", lang))
        if hours_val is None or hours_val <= 0:
            raise HTTPException(400, t("please_enter_leave_hours", lang))

    wh_id = get_wh_id(current_user)
    if not wh_id:
        raise HTTPException(400, t("please_select_warehouse", lang))

    # Find employee record for this user（排除已删除）
    emp = (await db.execute(
        select(Employee).where(Employee.warehouse_id == wh_id, Employee.phone == current_user.username, Employee.is_deleted == False)
    )).scalar_one_or_none()
    if not emp:
        # Try matching by name
        emp = (await db.execute(
            select(Employee).where(Employee.warehouse_id == wh_id, Employee.name == current_user.display_name, Employee.is_deleted == False)
        )).scalar_one_or_none()
    if not emp:
        raise HTTPException(400, t("employee_not_found_contact_admin", lang))

    try:
        leave_dt = datetime.strptime(leave_date, "%Y-%m-%d").date()
    except:
        raise HTTPException(400, t("invalid_date_format", lang))

    # Check duplicate date（同一天不可重复申请）
    dup = (await db.execute(
        select(LeaveRequest).where(
            LeaveRequest.employee_id == emp.id,
            LeaveRequest.leave_date == leave_dt,
            LeaveRequest.status != "rejected",
        )
    )).scalar_one_or_none()
    if dup:
        raise HTTPException(400, t("leave_already_submitted", lang))

    # Save photo（可选，压缩 + 缩略图）
    photo_path = None
    if file:
        try:
            from app.services.image_utils import save_image
            ext = file.filename.split(".")[-1].lower() if file.filename else "jpg"
            content = await file.read()
            today_str = thai_today().isoformat()
            abs_subdir = os.path.join(UPLOAD_DIR, str(wh_id), today_str, "leaves")
            rel_subdir = f"uploads/{wh_id}/{today_str}/leaves"
            fname = f"{uuid.uuid4().hex}.{ext}"
            result = save_image(content, abs_subdir, rel_subdir, fname)
            photo_path = result["path"]
        except:
            pass

    lr = LeaveRequest(
        warehouse_id=wh_id, employee_id=emp.id,
        leave_date=leave_dt, leave_type=leave_type,
        photo_path=photo_path, reason=reason, status="pending",
        duration_type=duration_type, hours=hours_val,
    )
    db.add(lr)
    await db.flush()
    return {"message": t("leave_submitted", lang), "id": lr.id}

class LeaveBatchCreate(BaseModel):
    employee_id: int
    start_date: str  # YYYY-MM-DD
    end_date: str    # YYYY-MM-DD
    leave_type: str = "sick"  # sick / personal
    reason: Optional[str] = None
    duration_type: str = "full"  # full/morning/afternoon/hours
    hours: Optional[float] = None

@router.post("/leaves/admin-record")
async def admin_record_leave(
    req: LeaveBatchCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """仓库管理员/主管代员工录请假：选日期范围，每天生成一条，直接生效(已通过)，不走审批。"""
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
        raise HTTPException(403, "只有管理员或主管可以代录请假")
    if req.leave_type not in ("sick", "personal"):
        raise HTTPException(400, "请假类型无效")
    if req.duration_type not in ("full", "morning", "afternoon", "hours"):
        raise HTTPException(400, "请假时长类型无效")
    hours_val = req.hours
    if req.duration_type == "hours" and (hours_val is None or hours_val <= 0):
        raise HTTPException(400, "请填写请假小时数")

    wh_id = get_wh_id(current_user)
    if not wh_id:
        raise HTTPException(400, "请先选择仓库")

    try:
        start = datetime.strptime(req.start_date, "%Y-%m-%d").date()
        end = datetime.strptime(req.end_date, "%Y-%m-%d").date()
    except:
        raise HTTPException(400, "日期格式错误")
    if start > end:
        raise HTTPException(400, "开始日期不能晚于结束日期")
    if (end - start).days > 365:
        raise HTTPException(400, "日期范围过大")

    emp = (await db.execute(
        select(Employee).where(Employee.id == req.employee_id, Employee.warehouse_id == wh_id, Employee.is_deleted == False)
    )).scalar_one_or_none()
    if not emp:
        raise HTTPException(404, "员工不存在")

    created = 0
    skipped = 0
    cur = start
    while cur <= end:
        dup = (await db.execute(
            select(LeaveRequest).where(
                LeaveRequest.employee_id == req.employee_id,
                LeaveRequest.leave_date == cur,
                LeaveRequest.status != "rejected",
            )
        )).scalar_one_or_none()
        if dup:
            skipped += 1
        else:
            db.add(LeaveRequest(
                warehouse_id=wh_id, employee_id=req.employee_id,
                leave_date=cur, leave_type=req.leave_type,
                reason=req.reason, status="approved",
                duration_type=req.duration_type, hours=hours_val,
                reviewed_by=current_user.id, reviewed_at=thai_now(),
            ))
            created += 1
        cur += timedelta(days=1)
    await db.flush()
    return {"message": f"已代录 {created} 条请假，跳过 {skipped} 天", "created": created, "skipped": skipped}

@router.get("/leaves")
async def list_leaves(
    start_date: str = None,
    end_date: str = None,
    status: str = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    query = select(LeaveRequest, Employee.name).join(Employee, LeaveRequest.employee_id == Employee.id)
    if current_user.role in (Role.WAREHOUSE_LABOR, Role.STAFF):
        wh_id = get_wh_id(current_user)
        # Use user_id link first, fallback to name matching
        emp = (await db.execute(
            select(Employee).where(
                Employee.warehouse_id == wh_id,
                Employee.user_id == current_user.id,
                Employee.is_deleted == False,
            )
        )).scalar_one_or_none()
        if not emp:
            emp = (await db.execute(
                select(Employee).where(Employee.warehouse_id == wh_id, Employee.name == current_user.display_name, Employee.is_deleted == False)
            )).scalar_one_or_none()
        if emp:
            query = query.where(LeaveRequest.employee_id == emp.id)
        else:
            return {"data": []}
    else:
        # Use active (header-selected) warehouse for warehouse_admin/supervisor
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
        "duration_type": r.duration_type or "full", "hours": r.hours,
        "photo_path": r.photo_path, "status": r.status, "reason": r.reason,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    } for r, name in rows]}

@router.put("/leaves/{leave_id}/approve")
async def approve_leave(leave_id: int, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
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
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
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
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
        raise HTTPException(403, "只有管理员可以设置休息日")
    wh_id = get_wh_id(current_user)
    if not wh_id: raise HTTPException(400, "请先选择仓库")

    # Validate employee（排除已删除）
    emp = (await db.execute(select(Employee).where(Employee.id == req.employee_id, Employee.warehouse_id == wh_id, Employee.is_deleted == False))).scalar_one_or_none()
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
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF, Role.WAREHOUSE_LABOR):
        raise HTTPException(403, "无权限")

    query = select(RestDay, Employee.name).join(Employee, RestDay.employee_id == Employee.id)
    if current_user.role in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
        active_wh = get_wh_id(current_user)
        if active_wh:
            query = query.where(RestDay.warehouse_id == active_wh)
    else:
        wh_id = get_wh_id(current_user)
        emp = (await db.execute(
            select(Employee.id).where(Employee.warehouse_id == wh_id, Employee.name == current_user.display_name, Employee.is_deleted == False)
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
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
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
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
        raise HTTPException(403, "只有管理员可以标记")
    wh_id = get_wh_id(current_user)
    if not wh_id: raise HTTPException(400, "请先选择仓库")

    emp = (await db.execute(select(Employee).where(Employee.id == req.employee_id, Employee.warehouse_id == wh_id, Employee.is_deleted == False))).scalar_one_or_none()
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
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
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
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF, Role.WAREHOUSE_LABOR):
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

    # Get employees scoped to the active warehouse（含已删除，有考勤/请假记录的仍显示）
    emp_query = select(Employee).where(Employee.status != "resigned")
    if current_user.role in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
        # Use active (header-selected) warehouse, not all warehouses
        active_wh_id = get_wh_id(current_user)
        if active_wh_id:
            emp_query = emp_query.where(Employee.warehouse_id == active_wh_id)
        else:
            emp_query = emp_query.where(Employee.warehouse_id.in_(wh_ids))
    elif current_user.role in (Role.STAFF, Role.WAREHOUSE_LABOR):
        emp = (await db.execute(
            select(Employee.id).where(Employee.warehouse_id == wh_id, Employee.name == current_user.display_name, Employee.is_deleted == False)
        )).scalar_one_or_none()
        if emp:
            emp_query = emp_query.where(Employee.id == emp)
        else:
            return {"employees": [], "events": [], "start_date": start_date, "end_date": end_date}

    emps = (await db.execute(emp_query.order_by(Employee.name))).scalars().all()
    emp_ids = [e.id for e in emps]

    # Build employee_id <-> user_id mapping（含未绑定账号的兜底匹配：手机号=用户名 / 姓名=显示名）
    from app.services.employee_match import resolve_employee_user_map
    emp_to_user, user_to_emp = await resolve_employee_user_map(db, emps)

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
    leave_map = {(l.employee_id, l.leave_date): (l.duration_type or "full") for l in leaves}

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

    # 已删除的员工：只在范围内有考勤记录（打卡/请假/休息/缺勤）的才显示，避免空白行
    deleted_emp_ids = {e.id for e in emps if e.is_deleted}
    if deleted_emp_ids:
        deleted_with_records = set()
        for eid in deleted_emp_ids:
            has = False
            for d in range((range_end - range_start).days + 1):
                dt = range_start + timedelta(days=d)
                if (eid, dt) in clock_map or (eid, dt) in leave_set or (eid, dt) in rest_set or (eid, dt) in absence_map:
                    has = True
                    break
            if has:
                deleted_with_records.add(eid)
        emps = [e for e in emps if not e.is_deleted or e.id in deleted_with_records]
        emp_ids = [e.id for e in emps]

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

            # Check rest / absence first（全天性质）
            session_count = 0
            has_late = False
            if (e.id, dt) in rest_set:
                status_name_db = "rest"
            elif (e.id, dt) in absence_map:
                status_name_db = "absent"
            else:
                sessions = clock_map.get((e.id, dt), [])
                session_set = {c.session for c in sessions}
                session_count = len(session_set)
                has_late = any(cr.status in ("late_half", "late_one") for cr in sessions)
                lt = leave_map.get((e.id, dt))
                morning = {1, 2}
                afternoon = {3, 4}
                has_morning = morning <= session_set
                has_afternoon = afternoon <= session_set

                if lt == "full":
                    status_name_db = "leave"
                elif lt == "morning":
                    # 上午请假 + 下午打满2次卡 → 半天；否则按请假
                    status_name_db = "half" if has_afternoon else "leave"
                elif lt == "afternoon":
                    # 下午请假 + 上午打满2次卡 → 半天；否则按请假
                    status_name_db = "half" if has_morning else "leave"
                elif has_morning and has_afternoon:
                    status_name_db = "late" if has_late else "present"
                elif session_count == 2 and (has_morning or has_afternoon):
                    # 只打满一个半天（上午或下午2次卡），另一半没请假 → 半天旷工
                    status_name_db = "half_absence"
                elif session_count in (1, 2, 3):
                    status_name_db = "partial"
                elif session_count == 0:
                    status_name_db = "missing" if dt <= thai_today() else "future"
                else:
                    status_name_db = "partial"

            # Map DB names to Chinese
            status_cn = {
                "present": "正常出勤", "late": "迟到", "leave": "请假",
                "rest": "休息日", "absent": "未到", "missing": "未打卡",
                "partial": "部分打卡", "half": "半天", "half_absence": "半天旷工",
                "future": "未到"
            }
            key_str = f"{dt.isoformat()}_{e.id}"
            events[key_str] = {
                "date": dt.isoformat(),
                "employee_id": e.id,
                "employee_name": e.name,
                "status": status_name_db,
                "status_label": status_cn.get(status_name_db, status_name_db),
                "session_count": session_count,
                "has_late": has_late,
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

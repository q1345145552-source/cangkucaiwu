from app.services.attendance_exemptions import valid_clock
from app.core.round4_access import independent_employee
from app.services.half_day_leave import is_half_day_leave, half_day_leave_hours
from app.services.full_day_leave import full_day_net_hours, full_day_clock_warning
from app.services.hourly_leave import hourly_leave_net_hours, is_hourly_leave, hourly_clock_hours
from app.core.employee_access import employee_access, employee_view, attendance_supervisor
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from app.database import get_db
from app.models.attendance import LeaveRequest, RestDay, Absence
from app.models.salary_template import SalaryTemplate
from app.models.employee import Employee, EmployeeRestDate
from app.models.clock_in_records import ClockInRecord
from app.models.user import User
from app.models.warehouse import Warehouse

from app.core.permissions import get_current_user, check_staff_permission, check_staff_permission_any, get_wh_id, get_wh_ids, Role
from app.core.messages import t, get_request_lang
from pydantic import BaseModel
from app.core.timezone import thai_now, thai_today
from app.services.schedule import get_work_schedule
from datetime import datetime, date, timedelta
from typing import Optional, List, Literal
import os, uuid

from app.core.menu_registry import MENU_PERMISSIONS_BY_KEY

_ATTENDANCE_PERMISSION = MENU_PERMISSIONS_BY_KEY["attendance"].label
_LEAVE_PERMISSION = MENU_PERMISSIONS_BY_KEY["leave"].label

router = APIRouter()

UPLOAD_DIR = "/app/uploads"


def _clock_hours_of_day(records) -> float:
    """按打卡记录计算单日打卡工时（与工资端 _day_hours 口径一致）：
    - 4 条：(第2-第1) + (第4-第3)
    - 2 条：第2-第1
    records 需按 clocked_in_at 升序。"""
    n = len(records)
    times = [r.clocked_in_at for r in records]
    if n == 4:
        total = 0.0
        for a, b in ((0, 1), (2, 3)):
            if times[a] is not None and times[b] is not None:
                total += max((times[b] - times[a]).total_seconds() / 3600.0, 0.0)
        return total
    if n == 2:
        if times[0] is not None and times[1] is not None:
            return max((times[1] - times[0]).total_seconds() / 3600.0, 0.0)
        return 0.0
    return 0.0


def _hhmm_minutes(hhmm):
    try:
        h, m = str(hhmm).split(":")
        return int(h) * 60 + int(m)
    except (ValueError, TypeError):
        return None


def _standard_daily_hours(sched: dict) -> float:
    """当天应有工时 = 上午(午休开始-早上上班) + 下午(下午下班-午休结束)；异常回退 8 小时。"""
    ms = _hhmm_minutes(sched.get("morning_start"))
    nb = _hhmm_minutes(sched.get("noon_break_start"))
    ne = _hhmm_minutes(sched.get("noon_break_end"))
    ae = _hhmm_minutes(sched.get("afternoon_end"))
    morning = (nb - ms) if (ms is not None and nb is not None and nb > ms) else 0
    afternoon = (ae - ne) if (ne is not None and ae is not None and ae > ne) else 0
    total_min = morning + afternoon
    return total_min / 60.0 if total_min > 0 else 8.0


def _fmt_hours(h: float) -> str:
    """小时数格式化为字符串：整数不留小数，最多保留 2 位小数。"""
    if h is None:
        return ""
    h2 = round(float(h), 2)
    if h2 == int(h2):
        return str(int(h2))
    return f"{h2:.2f}".rstrip("0").rstrip(".")

async def _ensure_no_absence(db, employee_id, warehouse_id, start, end):
    # Share the employee lock with absence/leave/makeup writes before checking.
    await db.execute(select(Employee.id).where(Employee.id == employee_id).with_for_update())
    found = (await db.execute(select(Absence.id).where(
        Absence.employee_id == employee_id, Absence.warehouse_id == warehouse_id,
        Absence.absence_date >= start, Absence.absence_date <= end,
    ).limit(1))).scalar_one_or_none()
    if found is not None:
        raise HTTPException(400, "此人当天已标缺勤，不能同时录请假，请先撤销缺勤")


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
    current_user: User = Depends(employee_access(_LEAVE_PERMISSION, self_only=True)),
    db: AsyncSession = Depends(get_db),
):
    lang = get_request_lang(request)
    if not employee_view(current_user) and current_user.role != Role.STAFF:
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

    unexpected = set(await request.form()) - {'leave_date', 'leave_type', 'reason', 'duration_type', 'hours', 'file'}
    if unexpected:
        raise HTTPException(400, '请假申请包含不允许的字段')
    emp = current_user._attendance_employee
    await db.execute(select(Employee).where(Employee.id == emp.id).with_for_update())

    try:
        leave_dt = datetime.strptime(leave_date, "%Y-%m-%d").date()
    except:
        raise HTTPException(400, t("invalid_date_format", lang))

    await _ensure_no_absence(db, emp.id, wh_id, leave_dt, leave_dt)

    # Check duplicate date（同一天不可重复申请）
    dup = (await db.execute(
        select(LeaveRequest).where(
            LeaveRequest.employee_id == emp.id,
            LeaveRequest.leave_date == leave_dt,
            LeaveRequest.status.in_(("pending", "approved")),
        )
    )).scalars().first()
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
        notified_at=thai_now(),  # 员工自己申请：报备时间=申请时间
    )
    db.add(lr)
    await db.flush()
    return {"message": t("leave_submitted", lang), "id": lr.id}

class LeaveBatchCreate(BaseModel):
    model_config = {"extra": "forbid"}
    employee_id: int
    start_date: str  # YYYY-MM-DD
    end_date: str    # YYYY-MM-DD
    leave_type: str = "sick"  # sick / personal
    reason: Optional[str] = None
    duration_type: str = "full"  # full/morning/afternoon/hours
    hours: Optional[float] = None
    notified_at: Optional[str] = None  # 实际报备时间 YYYY-MM-DD 或 YYYY-MM-DDTHH:MM

@router.post("/leaves/admin-record")
async def admin_record_leave(
    req: LeaveBatchCreate,
    current_user: User = Depends(check_staff_permission(_LEAVE_PERMISSION)),
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
    if emp.status == "resigned":
        raise HTTPException(400, "该员工已离职，不能代录请假")

    await independent_employee(db, current_user, emp.id)

    # 实际报备时间：默认今天；支持 YYYY-MM-DD 或 YYYY-MM-DDTHH:MM
    notified_at = thai_now()
    if req.notified_at:
        try:
            notified_at = datetime.fromisoformat(req.notified_at)
        except (ValueError, TypeError):
            try:
                notified_at = datetime.strptime(req.notified_at, "%Y-%m-%d")
            except (ValueError, TypeError):
                notified_at = thai_now()

    await _ensure_no_absence(db, emp.id, wh_id, start, end)

    # Preflight the whole range: reject duplicates before creating any records.
    dup = (await db.execute(
        select(LeaveRequest.id).where(
            LeaveRequest.warehouse_id == wh_id,
            LeaveRequest.employee_id == req.employee_id,
            LeaveRequest.leave_date >= start,
            LeaveRequest.leave_date <= end,
            LeaveRequest.status.in_(("approved", "pending")),
        ).limit(1)
    )).scalar_one_or_none()
    if dup is not None:
        raise HTTPException(400, "该员工这一天已有请假记录")

    created = 0
    skipped = 0
    cur = start
    while cur <= end:
        db.add(LeaveRequest(
            warehouse_id=wh_id, employee_id=req.employee_id,
            leave_date=cur, leave_type=req.leave_type,
            reason=req.reason, status="approved",
            duration_type=req.duration_type, hours=hours_val,
            notified_at=notified_at,
            reviewed_by=current_user.id, reviewed_at=thai_now(),
        ))
        created += 1
        cur += timedelta(days=1)
    await db.flush()
    warning = await full_day_clock_warning(db, emp, start, end) if req.duration_type == "full" else {}
    return {"message": f"已代录 {created} 条请假，跳过 {skipped} 天", "created": created, "skipped": skipped, **warning}

@router.get("/leaves")
async def list_leaves(
    start_date: str = None,
    end_date: str = None,
    status: str = None,
    current_user: User = Depends(employee_access(_ATTENDANCE_PERMISSION, _LEAVE_PERMISSION)),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    query = select(LeaveRequest, Employee.name).join(Employee, LeaveRequest.employee_id == Employee.id)
    query = query.where(Employee.is_deleted == False, Employee.status != "resigned")
    if employee_view(current_user):
        wh_id = get_wh_id(current_user)
        # Use user_id link first, fallback to name matching
        emp = (await db.execute(
            select(Employee).where(
                Employee.warehouse_id == wh_id,
                Employee.user_id == current_user.id,
                Employee.is_deleted == False,
            )
        )).scalar_one_or_none()
        if employee_view(current_user):
            emp = current_user._attendance_employee
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
    from app.models.data_change_history import DataChangeHistory
    cancellations = (await db.execute(select(DataChangeHistory).where(
        DataChangeHistory.module == "leave", DataChangeHistory.operation_type == "cancel",
        DataChangeHistory.record_id.in_([r.id for r, _ in rows]),
    ).order_by(DataChangeHistory.id))).scalars().all() if rows else []
    cancel_by_id = {h.record_id: {"cancelled_by": h.operator_name,
        "cancelled_at": h.after_data.get("cancelled_at"),
        "cancel_reason": h.after_data.get("reason")} for h in cancellations}
    return {"data": [{
        "id": r.id, "employee_id": r.employee_id, "employee_name": name,
        "leave_date": r.leave_date.isoformat(), "leave_type": r.leave_type,
        "duration_type": r.duration_type or "full", "hours": r.hours,
        "photo_path": r.photo_path, "status": r.status, "reason": r.reason,
        **cancel_by_id.get(r.id, {}),
        "notified_at": r.notified_at.isoformat() if r.notified_at else None,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    } for r, name in rows]}

class LeaveCancel(BaseModel):
    model_config = {"extra": "forbid"}
    reason: str


@router.put("/leaves/{leave_id}/cancel")
async def cancel_leave(leave_id: int, req: LeaveCancel,
    current_user: User = Depends(check_staff_permission(_LEAVE_PERMISSION)),
    db: AsyncSession = Depends(get_db)):
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
        raise HTTPException(403, "只有仓库管理员和主管可以撤销请假")
    reason = req.reason.strip()
    if not reason or len(reason) > 500:
        raise HTTPException(400, "请填写撤销原因（最多500字）")
    lr = (await db.execute(select(LeaveRequest).where(
        LeaveRequest.id == leave_id, LeaveRequest.warehouse_id.in_(get_wh_ids(current_user)),
    ).with_for_update())).scalar_one_or_none()
    if lr is None:
        raise HTTPException(404, "请假申请不存在或无权操作")
    await independent_employee(db, current_user, lr.employee_id)
    if lr.status not in ("pending", "approved"):
        raise HTTPException(409, "只能撤销待处理或已批准的请假，不能重复撤销")
    from app.services.data_history import record_history
    cancelled_at = thai_now().isoformat()
    await record_history(db, module="leave", record_id=lr.id, operator=current_user,
        operation_type="cancel", warehouse_id=lr.warehouse_id,
        before={"status": lr.status}, after={"status": "cancelled", "reason": reason,
            "cancelled_at": cancelled_at, "employee_id": lr.employee_id,
            "leave_date": lr.leave_date.isoformat()})
    lr.status = "cancelled"
    await db.flush()
    return {"id": lr.id, "status": "cancelled", "message": "已撤销请假",
        "cancelled_by": current_user.display_name or current_user.username,
        "cancelled_at": cancelled_at, "cancel_reason": reason}


@router.put("/leaves/{leave_id}/approve")
async def approve_leave(leave_id: int, current_user: User = Depends(check_staff_permission(_LEAVE_PERMISSION)), db: AsyncSession = Depends(get_db)):
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
        raise HTTPException(403, "只有管理员可以审批")
    lr = (await db.execute(select(LeaveRequest).where(LeaveRequest.id == leave_id).with_for_update())).scalar_one_or_none()
    if not lr: raise HTTPException(404, "请假申请不存在")
    wh_ids = get_wh_ids(current_user)
    if lr.warehouse_id not in wh_ids: raise HTTPException(403, "无权审批其他仓库的申请")
    await independent_employee(db, current_user, lr.employee_id)
    if lr.status != 'pending':
        raise HTTPException(409, '只能审批待处理的请假申请')
    await _ensure_no_absence(db, lr.employee_id, lr.warehouse_id, lr.leave_date, lr.leave_date)
    lr.status = "approved"
    lr.reviewed_by = current_user.id
    lr.reviewed_at = thai_now()
    await db.flush()
    warning = {}
    if (lr.duration_type or "full") == "full":
        employee = await db.get(Employee, lr.employee_id)
        if employee is not None and employee.warehouse_id == lr.warehouse_id:
            warning = await full_day_clock_warning(db, employee, lr.leave_date, lr.leave_date)
    return {"message": "已批准", **warning}

@router.put("/leaves/{leave_id}/reject")
async def reject_leave(leave_id: int, reason: str = Form(None), current_user: User = Depends(check_staff_permission(_LEAVE_PERMISSION)), db: AsyncSession = Depends(get_db)):
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
        raise HTTPException(403, "只有管理员可以审批")
    lr = (await db.execute(select(LeaveRequest).where(LeaveRequest.id == leave_id).with_for_update())).scalar_one_or_none()
    if not lr: raise HTTPException(404, "请假申请不存在")
    wh_ids = get_wh_ids(current_user)
    if lr.warehouse_id not in wh_ids: raise HTTPException(403, "无权审批其他仓库的申请")
    await independent_employee(db, current_user, lr.employee_id)
    if lr.status not in ('pending', 'approved'):
        raise HTTPException(409, '只能驳回待处理或已批准的请假申请')
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
    kind: Literal["rest", "work", "clear_work"] = "rest"

@router.post("/rest-days")
async def set_rest_days(
    req: RestDayCreate,
    current_user: User = Depends(check_staff_permission(_ATTENDANCE_PERMISSION)),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
        raise HTTPException(403, "只有管理员可以设置休息日")
    wh_id = get_wh_id(current_user)
    if not wh_id: raise HTTPException(400, "请先选择仓库")

    # Validate employee（排除已删除、离职）
    emp = (await db.execute(select(Employee).where(Employee.id == req.employee_id, Employee.warehouse_id == wh_id, Employee.is_deleted == False))).scalar_one_or_none()
    if not emp: raise HTTPException(404, "员工不存在")
    if emp.status == "resigned":
        raise HTTPException(400, "该员工已离职，不能设置休息日")

    if not req.rest_dates or len(req.rest_dates) > 31:
        raise HTTPException(400, "请选择1到31个日期")
    try:
        days = {date.fromisoformat(value) for value in req.rest_dates}
    except ValueError:
        raise HTTPException(400, "日期格式错误")
    await db.refresh(emp, with_for_update=True)
    from app.api.v1.employees import rest_dates_for, log_rest_change
    before = await rest_dates_for(db, emp)
    for day in days:
        row = (await db.execute(select(EmployeeRestDate).where(EmployeeRestDate.employee_id==emp.id, EmployeeRestDate.rest_date==day))).scalar_one_or_none()
        if row is None:
            row = EmployeeRestDate(employee_id=emp.id,warehouse_id=emp.warehouse_id,rest_date=day)
            db.add(row)
        if req.kind == "work":
            if row.prior_is_rest is None:
                row.prior_is_rest = bool(row.is_rest)
            row.is_rest = False
            row.source = "manual"
        elif req.kind == "clear_work":
            if row.prior_is_rest is not None:
                row.is_rest = row.prior_is_rest
                row.prior_is_rest = None
                row.source = "profile"
            elif row.is_rest is None:
                row.is_rest = False
        else:
            row.is_rest = True
            row.source = "manual"
            row.prior_is_rest = None
        row.updated_by = current_user.id
    await db.flush()
    await log_rest_change(db, emp, before, await rest_dates_for(db, emp), current_user)
    return {"message":"休息安排已更新", "added":len(days)}

@router.get("/rest-days")
async def list_rest_days(
    start_date: str = None,
    end_date: str = None,
    current_user: User = Depends(employee_access(_ATTENDANCE_PERMISSION, _LEAVE_PERMISSION)),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF, Role.WAREHOUSE_LABOR):
        raise HTTPException(403, "无权限")

    query = select(EmployeeRestDate, Employee.name).join(Employee, EmployeeRestDate.employee_id == Employee.id)
    query = query.where(EmployeeRestDate.is_rest == True)
    query = query.where(Employee.is_deleted == False, Employee.status != "resigned")
    if employee_view(current_user):
        query = query.where(EmployeeRestDate.employee_id == current_user._attendance_employee.id, EmployeeRestDate.warehouse_id == current_user.warehouse_id)
    elif current_user.role in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF):
        active_wh = get_wh_id(current_user)
        if active_wh:
            query = query.where(EmployeeRestDate.warehouse_id == active_wh)
    else:
        wh_id = get_wh_id(current_user)
        emp = (await db.execute(
            select(Employee.id).where(Employee.warehouse_id == wh_id, Employee.name == current_user.display_name, Employee.is_deleted == False)
        )).scalar_one_or_none()
        if emp:
            query = query.where(EmployeeRestDate.employee_id == emp)
        else:
            return {"data": []}

    if start_date:
        query = query.where(EmployeeRestDate.rest_date >= datetime.strptime(start_date, "%Y-%m-%d").date())
    if end_date:
        query = query.where(EmployeeRestDate.rest_date <= datetime.strptime(end_date, "%Y-%m-%d").date())

    result = await db.execute(query.order_by(EmployeeRestDate.rest_date))
    rows = result.all()
    return {"data": [{
        "id": r.id, "employee_id": r.employee_id, "employee_name": name,
        "rest_date": r.rest_date.isoformat(),
    } for r, name in rows]}

@router.delete("/rest-days/{rest_day_id}")
async def delete_rest_day(rest_day_id: int, current_user: User = Depends(check_staff_permission(_ATTENDANCE_PERMISSION)), db: AsyncSession = Depends(get_db)):
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
        raise HTTPException(403, "只有管理员可以操作")
    rd = (await db.execute(select(EmployeeRestDate).where(EmployeeRestDate.id == rest_day_id))).scalar_one_or_none()
    if not rd: raise HTTPException(404, "休息日不存在")
    wh_ids = get_wh_ids(current_user)
    if rd.warehouse_id not in wh_ids: raise HTTPException(403, "无权操作")
    emp = await db.get(Employee, rd.employee_id, with_for_update=True)
    from app.api.v1.employees import rest_dates_for, log_rest_change
    before = await rest_dates_for(db, emp)
    rd.is_rest = False
    rd.source = "manual"
    rd.updated_by = current_user.id
    await db.flush()
    await log_rest_change(db, emp, before, await rest_dates_for(db, emp), current_user)
    return {"message": "已取消休息，原记录保留"}

# ═══ Absence ════════════════════════════════
class AbsenceCreate(BaseModel):
    employee_id: int
    absence_date: str
    reason: Optional[str] = None

@router.post("/absences")
async def mark_absence(
    req: AbsenceCreate,
    current_user: User = Depends(check_staff_permission(_ATTENDANCE_PERMISSION)),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
        raise HTTPException(403, "只有管理员可以标记")
    wh_id = get_wh_id(current_user)
    if not wh_id: raise HTTPException(400, "请先选择仓库")

    emp = (await db.execute(select(Employee).where(Employee.id == req.employee_id, Employee.warehouse_id == wh_id, Employee.is_deleted == False))).scalar_one_or_none()
    if not emp: raise HTTPException(404, "员工不存在")
    if emp.status == "resigned":
        raise HTTPException(400, "该员工已离职，不能标记缺勤")

    try:
        dt = datetime.strptime(req.absence_date, "%Y-%m-%d").date()
    except:
        raise HTTPException(400, "日期格式错误")

    await db.execute(select(Employee.id).where(Employee.id == emp.id).with_for_update())
    leave = (await db.execute(select(LeaveRequest.id).where(
        LeaveRequest.employee_id == emp.id, LeaveRequest.warehouse_id == wh_id,
        LeaveRequest.leave_date == dt, LeaveRequest.status.in_(("pending", "approved")),
    ).limit(1))).scalar_one_or_none()
    if leave is not None:
        raise HTTPException(400, "此人当天有请假 不能同时标缺勤")
    dup = (await db.execute(
        select(Absence).where(Absence.employee_id == req.employee_id, Absence.absence_date == dt)
    )).scalar_one_or_none()
    if dup: raise HTTPException(400, "该日期已标记为未到")

    a = Absence(warehouse_id=wh_id, employee_id=req.employee_id, absence_date=dt, reason=req.reason, marked_by=current_user.id)
    db.add(a)
    await db.flush()
    return {"message": "已标记未到", "id": a.id}

@router.delete("/absences/{absence_id}")
async def remove_absence(absence_id: int, current_user: User = Depends(check_staff_permission(_ATTENDANCE_PERMISSION)), db: AsyncSession = Depends(get_db)):
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
        raise HTTPException(403, "无权限")
    a = (await db.execute(select(Absence).where(Absence.id == absence_id))).scalar_one_or_none()
    if not a: raise HTTPException(404, "记录不存在")
    wh_ids = get_wh_ids(current_user)
    if a.warehouse_id not in wh_ids: raise HTTPException(403, "无权操作")
    await db.delete(a)
    await db.flush()
    return {"message": "已删除"}

async def effective_rest_calendar(db, emps, range_start, range_end):
    owners = {e.id:e.warehouse_id for e in emps}
    rows = (await db.execute(select(EmployeeRestDate).where(
        EmployeeRestDate.employee_id.in_(owners), EmployeeRestDate.rest_date >= range_start,
        EmployeeRestDate.rest_date <= range_end,
    ))).scalars().all()
    rows = [row for row in rows if owners.get(row.employee_id) == row.warehouse_id]
    rests = {(row.employee_id,row.rest_date) for row in rows if row.is_rest}
    sources = {(row.employee_id,row.rest_date): ("manual_work" if not row.is_rest else "manual_rest" if row.source == "manual" else "profile") for row in rows}
    return rests, sources, []


async def rest_schedule_reminder(db, user):
    if user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
        return None
    warehouse_id = get_wh_id(user)
    if not warehouse_id:
        return None
    today = thai_today()
    start = today.replace(day=1)
    following = today.day >= 20
    if following:
        start = (start.replace(day=28)+timedelta(days=4)).replace(day=1)
    end = (start.replace(day=28)+timedelta(days=4)).replace(day=1)
    scheduled = select(EmployeeRestDate.employee_id).where(EmployeeRestDate.warehouse_id==warehouse_id,
        EmployeeRestDate.is_rest==True, EmployeeRestDate.rest_date>=start, EmployeeRestDate.rest_date<end)
    rows = (await db.execute(select(Employee, Warehouse.name).join(SalaryTemplate, Employee.salary_template_id==SalaryTemplate.id)
        .join(Warehouse, Employee.warehouse_id==Warehouse.id).where(Employee.warehouse_id==warehouse_id,
        SalaryTemplate.warehouse_id==warehouse_id, SalaryTemplate.type=="monthly", Employee.is_deleted==False,
        Employee.status!="resigned", Employee.id.not_in(scheduled)).order_by(Employee.id))).all()
    return {"month":start.strftime("%Y-%m"),"label":"下月" if following else "当月",
        "employees":[{"id":e.id,"name":e.name,"warehouse":name,"position":e.position} for e,name in rows]}


# ═══ Calendar View ════════════════════════════
@router.get("/calendar")
async def get_calendar(
    start_date: str = None,
    end_date: str = None,
    current_user: User = Depends(employee_access(_ATTENDANCE_PERMISSION, _LEAVE_PERMISSION)),
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

    # Get employees scoped to the active warehouse（只在职：is_deleted=False 且 status != resigned）
    emp_query = select(Employee).where(Employee.status != "resigned", Employee.is_deleted == False)
    if employee_view(current_user):
        emp_query = emp_query.where(Employee.id == current_user._attendance_employee.id, Employee.warehouse_id == wh_id)
    elif current_user.role in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF):
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
            select(ClockInRecord).where(valid_clock(),
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
    # 汇总同一天所有已通过请假：full/morning/afternoon 取标记，hours 累加小时数（一天多条要相加）
    leave_map = {}
    for l in leaves:
        key = (l.employee_id, l.leave_date)
        info = leave_map.setdefault(key, {"full": False, "morning": False, "afternoon": False, "hours": 0.0, "hours_has": False})
        dt = l.duration_type or "full"
        if dt == "full":
            info["full"] = True
        elif dt == "morning":
            info["morning"] = True
        elif dt == "afternoon":
            info["afternoon"] = True
        elif dt == "hours":
            if l.hours is None:
                # 小时数为空 → 按原来的全天假处理，不报错
                info["full"] = True
                info["hourly_missing"] = True
            else:
                info["hours"] += float(l.hours)
                info["hours_has"] = True

    rest_set, rest_sources, rest_warnings = await effective_rest_calendar(db, emps, range_start, range_end)

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

    # 当天应有工时（用于判断按小时请假是否够整天）
    work_sched = await get_work_schedule(db, wh_id)
    standard_hours = _standard_daily_hours(work_sched)
    from app.services.attendance_exemptions import active_days, exemption_hours
    exempt_dates = await active_days(db, wh_id, range_start, range_end)

    # 已删除员工已在上面查询中排除，这里不再回填

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

            if dt in exempt_dates:
                hours, leave_hours = exemption_hours(leave_map.get((e.id, dt)), dt, work_sched)
                events[f"{dt.isoformat()}_{e.id}"] = {
                    "date": dt.isoformat(), "employee_id": e.id, "employee_name": e.name,
                    "status": "exempt", "status_label": "已豁免", "is_exempt": True,
                    "rest_source": rest_sources.get((e.id, dt)),
                    "session_count": len({r.session for r in clock_map.get((e.id, dt), [])}),
                    "has_late": False, "leave_hours": leave_hours, "clock_hours": 0.0,
                    "work_hours": hours, "detail": f"豁免按8小时计，请假扣{leave_hours:g}小时；打卡保留但不参与计算",
                }
                continue

            # Check rest / absence first（全天性质）
            session_count = 0
            has_late = False
            clock_hours = 0.0
            leave_hours_val = 0.0
            net_hourly_hours = None
            if (e.id, dt) in rest_set:
                status_name_db = "rest"
            elif (e.id, dt) in absence_map:
                status_name_db = "absent"
            else:
                sessions = clock_map.get((e.id, dt), [])
                session_set = {c.session for c in sessions}
                session_count = len(session_set)
                has_late = any(cr.status in ("late_half", "late_one") for cr in sessions)
                leave_info = leave_map.get((e.id, dt))
                morning = {1, 2}
                afternoon = {3, 4}
                has_morning = morning <= session_set
                has_afternoon = afternoon <= session_set

                # 当天打卡工时（与工资端口径一致），按小时请假时用于扣减
                sessions_by_time = sorted(sessions, key=lambda c: c.clocked_in_at or datetime.min)
                clock_hours = _clock_hours_of_day(sessions_by_time)

                status_name_db = None
                if leave_info is None:
                    pass
                elif leave_info["full"]:
                    status_name_db = "leave"
                elif leave_info["morning"]:
                    # 上午请假 + 下午打满2次卡 → 半天；否则按请假
                    status_name_db = "half" if has_afternoon else "leave"
                elif leave_info["afternoon"]:
                    # 下午请假 + 上午打满2次卡 → 半天；否则按请假
                    status_name_db = "half" if has_morning else "leave"
                elif leave_info["hours_has"]:
                    # 按小时请假：落到当天，显示「请假X小时」，工时扣减
                    leave_hours_val = round(leave_info["hours"], 2)
                    if leave_info["hours"] >= standard_hours:
                        status_name_db = "leave"  # 够整天按请假算
                    else:
                        status_name_db = "hours_leave"

                if is_hourly_leave(leave_info):
                    net_hourly_hours = hourly_leave_net_hours(
                        hourly_clock_hours(sessions_by_time), None if leave_info.get("hourly_missing") else leave_info["hours"],
                        sessions_by_time[-1].clocked_in_at if sessions_by_time else None,
                        dt, work_sched, standard_hours,
                    )

                if is_half_day_leave(leave_info):
                    leave_hours_val, net_hourly_hours = half_day_leave_hours(sessions_by_time, leave_info, dt, work_sched)

                if status_name_db is None:
                    if has_morning and has_afternoon:
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
                "rest": "休息", "absent": "未到", "missing": "未打卡",
                "partial": "部分打卡", "half": "半天", "half_absence": "半天旷工",
                "hours_leave": "按小时请假",
                "future": "未到"
            }
            if status_name_db == "hours_leave":
                status_label = f"请假{_fmt_hours(leave_hours_val)}小时"
            else:
                status_label = status_cn.get(status_name_db, status_name_db)
            key_str = f"{dt.isoformat()}_{e.id}"
            events[key_str] = {
                "date": dt.isoformat(),
                "employee_id": e.id,
                "employee_name": e.name,
                "status": status_name_db,
                "rest_source": rest_sources.get((e.id, dt)),
                "schedule_label": {"manual_work": "上班 调班", "manual_rest": "休息 调休", "automatic": "休息", "profile": "休息"}.get(rest_sources.get((e.id, dt))),
                "status_label": status_label,
                "session_count": session_count,
                "has_late": has_late,
                "leave_hours": leave_hours_val if (status_name_db == "hours_leave" or (net_hourly_hours is not None and is_half_day_leave(leave_map.get((e.id, dt))))) else None,
                "clock_hours": round(clock_hours, 2),
                "work_hours": full_day_net_hours(leave_map.get((e.id, dt)), net_hourly_hours if net_hourly_hours is not None else round(max(clock_hours - leave_hours_val, 0.0), 2)),
                "detail": "",
            }
            if status_name_db == "absent" and (e.id, dt) in absence_map:
                events[key_str]["detail"] = absence_map[(e.id, dt)].reason or ""

    return {
        "start_date": range_start.isoformat(),
        "end_date": range_end.isoformat(),
        "employees": [{"id": e.id, "name": e.name, "position": e.position} for e in emps],
        "events": list(events.values()),
        "rest_warnings": rest_warnings,
        "rest_reminder": await rest_schedule_reminder(db, current_user),
        "summary": {
            "leave_count": len(leave_set),
            "rest_count": len(rest_set),
            "absence_count": sum(1 for a in absences if (a.employee_id, a.absence_date) not in rest_set and a.absence_date not in exempt_dates),
        }
    }


# Warehouse-wide exemptions are an administrator decision, not individual makeup.
async def exemption_admin(user: User = Depends(get_current_user)):
    if user.role != Role.WAREHOUSE_ADMIN:
        raise HTTPException(403, '仓库豁免日只能由仓库管理员操作')
    if not get_wh_id(user) or get_wh_id(user) not in get_wh_ids(user):
        raise HTTPException(403, '无权操作该仓库')
    return user


class ExemptionCreate(BaseModel):
    model_config = {'extra': 'forbid'}
    date: date
    reason: str


class ExemptionRevoke(BaseModel):
    model_config = {'extra': 'forbid'}
    reason: str


def exemption_reason(value):
    value = value.strip()
    if not value or len(value) > 500:
        raise HTTPException(400, '请填写原因，最多500字')
    return value


@router.get('/exemptions')
async def list_exemptions(start_date: Optional[date] = None, end_date: Optional[date] = None,
                          current_user: User = Depends(exemption_admin), db: AsyncSession = Depends(get_db)):
    from app.models.attendance_exemption import AttendanceExemption
    from app.services.attendance_exemptions import data
    if start_date and end_date and start_date > end_date:
        raise HTTPException(400, '开始日期不能晚于结束日期')
    query = select(AttendanceExemption).where(AttendanceExemption.warehouse_id == get_wh_id(current_user))
    if start_date: query = query.where(AttendanceExemption.date >= start_date)
    if end_date: query = query.where(AttendanceExemption.date <= end_date)
    rows = (await db.execute(query.order_by(AttendanceExemption.date.desc(), AttendanceExemption.id.desc()))).scalars()
    return {'data': [data(row) for row in rows]}


@router.post('/exemptions')
async def create_exemption(req: ExemptionCreate, current_user: User = Depends(exemption_admin), db: AsyncSession = Depends(get_db)):
    from app.models.attendance_exemption import AttendanceExemption
    from app.services import attendance_exemptions as exemptions
    from app.services.data_history import record_history
    reason = exemption_reason(req.reason)
    wid = get_wh_id(current_user)
    await exemptions.lock_day(db, wid, req.date)
    if await exemptions.active_days(db, wid, req.date, req.date):
        raise HTTPException(400, '该仓库当天已有有效豁免')
    row = AttendanceExemption(warehouse_id=wid, date=req.date, reason=reason, created_by=current_user.id,
                              created_by_name=current_user.display_name or current_user.username, created_at=thai_now(), status='active')
    db.add(row)
    await db.flush()
    records = (await db.execute(select(ClockInRecord).where(valid_clock(),
        ClockInRecord.warehouse_id == wid, ClockInRecord.clock_date == req.date,
        ClockInRecord.is_makeup == True, exemptions.valid_clock()).with_for_update())).scalars().all()
    previous = [{'id': r.id, 'status': r.status, 'makeup_counts_toward_limit': r.makeup_counts_toward_limit,
                 'makeup_batch_id': r.makeup_batch_id} for r in records]
    batch_ids = sorted({r.makeup_batch_id for r in records if r.makeup_batch_id is not None})
    for record in records:
        record.status = 'voided'
        record.makeup_counts_toward_limit = False
        record.makeup_batch_id = None
    await record_history(db, module='attendance_exemptions', record_id=row.id, operator=current_user,
                         operation_type='create', before={'makeup_records': previous},
                         after={**exemptions.data(row), 'voided_makeup_ids': [r.id for r in records]}, warehouse_id=wid)
    await db.flush()
    return {'message': '豁免日已设置', 'data': exemptions.data(row), 'voided_makeup_count': len(records),
            'detached_batch_ids': batch_ids, 'warning': await exemptions.payroll_warning(db, wid, req.date)}


@router.post('/exemptions/{exemption_id}/revoke')
async def revoke_exemption(exemption_id: int, req: ExemptionRevoke,
                           current_user: User = Depends(exemption_admin), db: AsyncSession = Depends(get_db)):
    from app.models.attendance_exemption import AttendanceExemption
    from app.services import attendance_exemptions as exemptions
    from app.services.data_history import record_history
    wid = get_wh_id(current_user)
    reason = exemption_reason(req.reason)
    row = (await db.execute(select(AttendanceExemption).where(
        AttendanceExemption.id == exemption_id, AttendanceExemption.warehouse_id == wid))).scalar_one_or_none()
    if not row: raise HTTPException(404, '豁免记录不存在')
    await exemptions.lock_day(db, wid, row.date)
    await db.refresh(row)
    if row.status != 'active': raise HTTPException(400, '该豁免已撤销')
    before = exemptions.data(row)
    row.status = 'revoked'
    row.revoked_by = current_user.id
    row.revoked_by_name = current_user.display_name or current_user.username
    row.revoked_at = thai_now()
    row.revoke_reason = reason
    await record_history(db, module='attendance_exemptions', record_id=row.id, operator=current_user,
                         operation_type='edit', before=before, after=exemptions.data(row), warehouse_id=wid)
    await db.flush()
    return {'message': '豁免已撤销，已作废补卡不会恢复', 'data': exemptions.data(row),
            'warning': await exemptions.payroll_warning(db, wid, row.date)}

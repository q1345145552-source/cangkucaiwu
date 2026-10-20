from app.core.employee_access import employee_access, employee_view, attendance_supervisor
from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from app.database import get_db
from app.models.overtime import OvertimeTask, OvertimeAssignment
from app.models.employee import Employee
from app.models.salary_template import SalaryTemplate
from app.models.user import User
from app.core.permissions import check_staff_permission, get_wh_id, get_wh_ids, Role
from app.core.messages import t, get_request_lang
from app.services.data_history import record_history
from app.services.boss_todos import pending_overtime_task, pending_overtime_assignment
from pydantic import BaseModel, field_validator
from app.core.timezone import thai_now, thai_today
from datetime import datetime, date
from typing import Optional, List
import math

from app.core.menu_registry import MENU_PERMISSIONS_BY_KEY

_PERMISSION = MENU_PERMISSIONS_BY_KEY["overtime"].label

router = APIRouter()


# ═══ Schemas ════════════════════════════

class OvertimeCreate(BaseModel):
    employee_ids: List[int]
    date: str  # YYYY-MM-DD
    start_time: str  # HH:MM
    end_time: str  # HH:MM

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


class OvertimeVerifyItem(BaseModel):
    assignment_id: int
    actual_hours: Optional[float] = None


class OvertimeVerify(BaseModel):
    assignments: List[OvertimeVerifyItem]


# 加班费算法：加班分钟数换算成半小时数（不足半小时算半小时，向上取整），
# 再乘以员工薪资模板里的「加班半小时费」。
def _half_hour_count(total_minutes: int) -> int:
    return math.ceil(total_minutes / 30)


def _half_hours_from_times(start_time: str, end_time: str) -> int:
    try:
        start_h, start_m = map(int, start_time.split(":"))
        end_h, end_m = map(int, end_time.split(":"))
        minutes = (end_h * 60 + end_m) - (start_h * 60 + start_m)
        return _half_hour_count(minutes) if minutes > 0 else 0
    except (ValueError, TypeError):
        return 0


# ═══ Admin: Create Overtime ═══════════

@router.post("")
async def create_overtime(
    req: OvertimeCreate,
    current_user: User = Depends(check_staff_permission(_PERMISSION)),
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

    # 薪资模板检查：没有模板的员工先拦住
    no_template = [e for e in employees if not e.salary_template_id]
    if no_template:
        names = "、".join(e.name for e in no_template)
        raise HTTPException(400, f"以下员工还没有设置薪资模板，请先设置薪资模板：\n{names}")

    template_ids = {e.salary_template_id for e in employees if e.salary_template_id}
    template_map = {}
    if template_ids:
        ts = (await db.execute(select(SalaryTemplate).where(SalaryTemplate.id.in_(template_ids)))).scalars().all()
        template_map = {t.id: t for t in ts}
    # 模板存在但被删除等异常情况
    missing_tpl = [e for e in employees if e.salary_template_id not in template_map]
    if missing_tpl:
        names = "、".join(e.name for e in missing_tpl)
        raise HTTPException(400, f"以下员工的薪资模板无效，请重新设置：\n{names}")

    half_hours = _half_hour_count(total_minutes)

    # 每个员工按自己的薪资模板算加班费
    per_emp = []
    for emp in employees:
        tpl = template_map[emp.salary_template_id]
        fee = tpl.overtime_half_hour_fee or 0
        earned = round(half_hours * fee, 2)
        per_emp.append({
            "employee_id": emp.id,
            "employee_name": emp.name,
            "half_hours": half_hours,
            "overtime_half_hour_fee": fee,
            "earned_amount": earned,
        })

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
        hourly_rate=0,
        status="pending",
        needs_verification=True,
        created_by=current_user.id,
    )
    db.add(task)
    await db.flush()

    # Create assignments（每人金额不同，按各自模板）
    for item in per_emp:
        emp = next(e for e in employees if e.id == item["employee_id"])
        linked_user = await _find_linked_user(db, emp)
        assignment = OvertimeAssignment(
            overtime_id=task.id,
            employee_id=emp.id,
            user_id=linked_user.id if linked_user else None,
            earned_amount=item["earned_amount"],
        )
        db.add(assignment)

    await db.flush()
    return {
        "message": "加班任务创建成功",
        "id": task.id,
        "hours": hours,
        "half_hours": half_hours,
        "employee_count": len(employees),
        "total_amount": round(sum(p["earned_amount"] for p in per_emp), 2),
        "assignments": per_emp,
    }


# ═══ Admin: Verify Actual Overtime Hours ═══════════

@router.post("/{task_id}/verify")
async def verify_overtime(
    task_id: int,
    req: OvertimeVerify,
    request: Request,
    current_user: User = Depends(check_staff_permission(_PERMISSION)),
    db: AsyncSession = Depends(get_db),
):
    lang = get_request_lang(request)
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPER_ADMIN, Role.SUPERVISOR):
        raise HTTPException(403, t("overtime_verify_only_admin", lang))

    wh_ids = get_wh_ids(current_user)
    task = (await db.execute(
        select(OvertimeTask).where(
            OvertimeTask.id == task_id,
            OvertimeTask.warehouse_id.in_(wh_ids),
        )
    )).scalar_one_or_none()
    if not task:
        raise HTTPException(404, t("overtime_task_not_found", lang))

    if task.status == "completed":
        raise HTTPException(400, t("overtime_verify_completed", lang))

    if not task.needs_verification:
        raise HTTPException(400, t("overtime_verify_not_needed", lang))

    # 校验实际小时数：必须填写且不能为负
    for item in req.assignments:
        if item.actual_hours is None or item.actual_hours < 0:
            raise HTTPException(400, t("overtime_verify_hours_required", lang))

    # 加载该任务的全部分配记录
    assignments = (await db.execute(
        select(OvertimeAssignment).where(OvertimeAssignment.overtime_id == task_id)
    )).scalars().all()
    assign_map = {a.id: a for a in assignments}

    # 加载员工薪资模板（加班半小时费）
    emp_ids = {a.employee_id for a in assignments}
    emp_map = {}
    if emp_ids:
        es = (await db.execute(select(Employee).where(Employee.id.in_(emp_ids)))).scalars().all()
        emp_map = {e.id: e for e in es}
    tpl_ids = {e.salary_template_id for e in emp_map.values() if e.salary_template_id}
    tpl_map = {}
    if tpl_ids:
        ts = (await db.execute(select(SalaryTemplate).where(SalaryTemplate.id.in_(tpl_ids)))).scalars().all()
        tpl_map = {t.id: t for t in ts}

    # 找出要核实的记录：已确认过的跳过，不碰他的数据
    to_verify = []
    skipped = []
    for item in req.assignments:
        a = assign_map.get(item.assignment_id)
        if not a:
            raise HTTPException(400, t("overtime_verify_assignment_not_found", lang, id=item.assignment_id))
        if a.confirmed:
            skipped.append(a)
        else:
            to_verify.append((item, a))

    # 按本次实际要写入的逐人分配记录判断本人，不使用姓名或整单发起人。
    if current_user.role == Role.SUPERVISOR:
        for _, a in to_verify:
            emp = emp_map.get(a.employee_id)
            if (a.user_id == current_user.id
                    or (emp is not None and emp.user_id == current_user.id)
                    or a.employee_id == current_user.attendance_employee_id):
                raise HTTPException(403, "本人不能核实自己的加班")

    # 月度上限校验（整批，保存前）：本月已核实用实际、未核实用计划、本次用新填的实际
    limit_hours = await _get_monthly_limit(db, task.warehouse_id)
    for item, a in to_verify:
        monthly = await _get_monthly_overtime_for_verify(db, a.employee_id, task.date, task.id)
        after = monthly + item.actual_hours
        if after > limit_hours:
            name = emp_map.get(a.employee_id).name if emp_map.get(a.employee_id) else f"员工{a.employee_id}"
            raise HTTPException(
                400,
                t("overtime_verify_limit_exceeded", lang, name=name, monthly=f"{monthly:.1f}", after=f"{after:.1f}", limit=f"{limit_hours:.0f}"),
            )

    verified_at = thai_now().isoformat()
    verified_count = 0
    for item, a in to_verify:
        audit_before = {"task_id": task.id, "employee_id": a.employee_id, "user_id": a.user_id,
                        "actual_hours": a.actual_hours, "earned_amount": a.earned_amount}
        a.actual_hours = item.actual_hours
        # 按实际小时数重算加班费：半小时向上取整 × 员工薪资模板加班半小时费
        emp = emp_map.get(a.employee_id)
        fee = 0
        if emp and emp.salary_template_id:
            tpl = tpl_map.get(emp.salary_template_id)
            fee = (tpl.overtime_half_hour_fee or 0) if tpl else 0
        half_hours = math.ceil(item.actual_hours * 2)
        a.earned_amount = round(half_hours * fee, 2)
        # 有争议的，核实后清掉争议标记
        if a.has_dispute:
            a.has_dispute = False
            a.dispute_reason = None
            a.dispute_photo = None
            a.dispute_time = None
        await record_history(db, module="overtime", record_id=a.id, operator=current_user,
            operation_type="verify", before=audit_before,
            after={"task_id": task.id, "employee_id": a.employee_id, "user_id": a.user_id,
                   "actual_hours": a.actual_hours, "earned_amount": a.earned_amount,
                   "verified_by": current_user.id, "verified_at": verified_at},
            warehouse_id=task.warehouse_id)
        verified_count += 1

    # 还有分配记录未填实际小时数 → 待核实，否则已核实
    remaining = (await db.execute(
        select(func.count(OvertimeAssignment.id)).where(
            OvertimeAssignment.overtime_id == task_id,
            OvertimeAssignment.actual_hours.is_(None),
        )
    )).scalar()
    task.status = "待核实" if (remaining and remaining > 0) else "已核实"

    await db.flush()

    total_amount = round(sum(a.earned_amount or 0 for a in assignments), 2)

    return {
        "message": t("overtime_verify_success", lang),
        "verified_count": verified_count,
        "skipped_count": len(skipped),
        "skipped_names": [emp_map.get(a.employee_id).name if emp_map.get(a.employee_id) else "" for a in skipped],
        "total_amount": total_amount,
        "status": task.status,
    }


# ═══ Employee: Confirm Attendance ═══════════

@router.post("/{overtime_id}/confirm")
async def confirm_overtime(
    overtime_id: int,
    request: Request,
    current_user: User = Depends(employee_access(_PERMISSION, self_only=True)),
    db: AsyncSession = Depends(get_db),
):
    lang = get_request_lang(request)
    if not employee_view(current_user):
        raise HTTPException(403, t("overtime_only_labor", lang))

    wh_id = get_wh_id(current_user)
    if not wh_id:
        raise HTTPException(400, t("please_select_warehouse", lang))

    task = (await db.execute(
        select(OvertimeTask).where(
            OvertimeTask.id == overtime_id,
            OvertimeTask.warehouse_id == wh_id,
        )
    )).scalar_one_or_none()
    if not task:
        raise HTTPException(404, t("overtime_task_not_found", lang))

    # 先找到登录用户对应的员工档案（绑定账号优先，姓名兜底），再按员工档案找分配记录
    emp = await _find_employee_for_user(db, wh_id, current_user)
    if not emp:
        raise HTTPException(400, t("employee_not_found_contact_admin", lang))

    assignment = (await db.execute(
        select(OvertimeAssignment).where(
            OvertimeAssignment.overtime_id == overtime_id,
            OvertimeAssignment.employee_id == emp.id,
        )
    )).scalar_one_or_none()
    if not assignment:
        raise HTTPException(400, t("overtime_not_assigned", lang))

    # 需要核实的任务，实际小时数还没填 → 拦住
    if task.needs_verification and assignment.actual_hours is None:
        raise HTTPException(400, t("overtime_not_verified_confirm", lang))

    # 已提过异议 → 拦住，等管理员改完再确认
    if assignment.has_dispute:
        raise HTTPException(400, t("overtime_has_dispute_confirm", lang))

    if assignment.confirmed:
        raise HTTPException(400, t("overtime_already_confirmed", lang))

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


# ═══ Employee: Dispute Actual Overtime Hours ═══════════

@router.post("/{task_id}/dispute")
async def dispute_overtime(
    task_id: int,
    request: Request,
    reason: str = Form(None),
    file: UploadFile = File(None),
    current_user: User = Depends(employee_access(_PERMISSION, self_only=True)),
    db: AsyncSession = Depends(get_db),
):
    lang = get_request_lang(request)
    if not employee_view(current_user):
        raise HTTPException(403, t("overtime_dispute_only_labor", lang))

    wh_id = get_wh_id(current_user)

    # 一：任务不存在
    task = (await db.execute(
        select(OvertimeTask).where(
            OvertimeTask.id == task_id,
            OvertimeTask.warehouse_id == wh_id,
        )
    )).scalar_one_or_none()
    if not task:
        raise HTTPException(404, t("overtime_task_not_found", lang))

    # 二：找不到登录用户的员工档案
    emp = await _find_employee_for_user(db, wh_id, current_user)
    if not emp:
        raise HTTPException(400, t("employee_not_found_contact_admin", lang))

    # 三：找不到他在这个任务里的分配记录
    assignment = (await db.execute(
        select(OvertimeAssignment).where(
            OvertimeAssignment.overtime_id == task_id,
            OvertimeAssignment.employee_id == emp.id,
        )
    )).scalar_one_or_none()
    if not assignment:
        raise HTTPException(400, t("overtime_dispute_not_yours", lang))

    # 四：需要核实但实际小时数还是空的
    if task.needs_verification and assignment.actual_hours is None:
        raise HTTPException(400, t("overtime_not_verified_dispute", lang))

    # 五：已经确认过，不能提异议
    if assignment.confirmed:
        raise HTTPException(400, t("overtime_confirmed_cant_dispute", lang))

    # 六：原因不能为空
    if not reason or not reason.strip():
        raise HTTPException(400, t("overtime_dispute_reason_required", lang))

    # 七：照片不能为空
    if file is None or not file.filename:
        raise HTTPException(400, t("overtime_dispute_photo_required", lang))
    content = await file.read()
    if not content:
        raise HTTPException(400, t("overtime_dispute_photo_required", lang))

    # 保存照片（走系统统一压缩 + 缩略图那套）
    import os, uuid
    from app.services.image_utils import save_image
    ext = file.filename.split(".")[-1].lower() if file.filename else "jpg"
    today_str = thai_today().strftime("%Y-%m-%d")
    abs_subdir = os.path.join(os.environ.get("UPLOAD_DIR", "/app/uploads"), str(wh_id), today_str, "overtime_disputes")
    rel_subdir = f"uploads/{wh_id}/{today_str}/overtime_disputes"
    fname = f"{uuid.uuid4().hex}.{ext}"
    result = save_image(content, abs_subdir, rel_subdir, fname)

    # 标成有异议，存原因/照片/时间（重复提异议覆盖旧的）
    assignment.has_dispute = True
    assignment.dispute_reason = reason.strip()[:500]
    assignment.dispute_photo = result["path"]
    assignment.dispute_time = thai_now()
    await db.flush()

    return {"message": t("overtime_dispute_success", lang), "dispute_time": assignment.dispute_time.isoformat()}


# ═══ List Overtime Tasks ═══════════

@router.get("")
async def list_overtimes(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    pending_verification: bool = False,
    status: str = None,
    month: str = None,  # YYYY-MM
    current_user: User = Depends(employee_access(_PERMISSION)),
    db: AsyncSession = Depends(get_db),
):
    labor_emp_id = None
    if employee_view(current_user):
        # Employees see their assigned tasks（按员工档案匹配，账号换绑也能看到）
        emp = await _find_employee_for_user(db, get_wh_id(current_user), current_user)
        if not emp:
            return {"data": [], "total": 0, "page": page, "page_size": page_size}
        labor_emp_id = emp.id
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

    if employee_view(current_user):
        query = query.where(OvertimeTask.warehouse_id == get_wh_id(current_user))
        count_q = count_q.where(OvertimeTask.warehouse_id == get_wh_id(current_user))
    if pending_verification:
        pending = select(OvertimeAssignment.id).where(
            OvertimeAssignment.overtime_id == OvertimeTask.id, pending_overtime_assignment(),
        ).correlate(OvertimeTask).exists()
        query = query.where(pending_overtime_task(), pending)
        count_q = count_q.where(pending_overtime_task(), pending)
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
        assign_q = select(OvertimeAssignment).where(OvertimeAssignment.overtime_id.in_(task_ids))
        if pending_verification:
            assign_q = assign_q.where(pending_overtime_assignment())
        # 劳工只看得到自己那一条分配记录，管理员/主管看全部
        if labor_emp_id is not None:
            assign_q = assign_q.where(OvertimeAssignment.employee_id == labor_emp_id)
        assigns = (await db.execute(assign_q)).scalars().all()
        emp_ids = {a.employee_id for a in assigns}
        emps = {}
        emp_tpl = {}
        tpl_fee_map = {}
        if emp_ids:
            es = (await db.execute(select(Employee).where(Employee.id.in_(emp_ids)))).scalars().all()
            emps = {e.id: e.name for e in es}
            emp_tpl = {e.id: e.salary_template_id for e in es}
            tpl_ids = {e.salary_template_id for e in es if e.salary_template_id}
            if tpl_ids:
                ts = (await db.execute(select(SalaryTemplate).where(SalaryTemplate.id.in_(tpl_ids)))).scalars().all()
                tpl_fee_map = {t.id: (t.overtime_half_hour_fee or 0) for t in ts}
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
                "actual_hours": a.actual_hours,
                "has_dispute": a.has_dispute,
                "dispute_reason": a.dispute_reason,
                "dispute_photo": a.dispute_photo,
                "overtime_half_hour_fee": tpl_fee_map.get(emp_tpl.get(a.employee_id), 0) or 0,
            })

    return {
        "data": [{
            "id": t.id,
            "warehouse_id": t.warehouse_id,
            "date": t.date.isoformat(),
            "start_time": t.start_time,
            "end_time": t.end_time,
            "hours": t.hours,
            "half_hours": _half_hours_from_times(t.start_time, t.end_time),
            "hourly_rate": t.hourly_rate,
            "status": t.status,
            "needs_verification": t.needs_verification,
            "created_by": t.created_by,
            "creator_name": creators.get(t.created_by, ""),
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "assignments": assign_map.get(t.id, []),
            "total_amount": round(sum(a["earned_amount"] for a in assign_map.get(t.id, [])), 2),
            "confirmed_count": sum(1 for a in assign_map.get(t.id, []) if a["confirmed"]),
            "total_assignments": len(assign_map.get(t.id, [])),
        } for t in tasks],
        "total": total or 0,
        "page": page,
    }


# ═══ Pending Tasks for Current User ═══════════

@router.get("/pending")
async def pending_overtimes(
    current_user: User = Depends(employee_access(_PERMISSION, self_only=True)),
    db: AsyncSession = Depends(get_db),
):
    if not employee_view(current_user):
        raise HTTPException(403, "无权限")

    wh_id = get_wh_id(current_user)
    if not wh_id:
        return {"data": [], "pending_count": 0}

    # 先找到员工档案，再按员工档案找未确认的分配（账号换绑也能找到）
    emp = await _find_employee_for_user(db, wh_id, current_user)
    if not emp:
        return {"data": [], "pending_count": 0}

    # Find tasks where this employee has unconfirmed OR disputed assignments
    sub = (
        select(OvertimeAssignment.overtime_id)
        .where(
            OvertimeAssignment.employee_id == emp.id,
            or_(
                OvertimeAssignment.confirmed == False,
                OvertimeAssignment.has_dispute == True,
            ),
        )
        .subquery()
    )
    tasks = (await db.execute(
        select(OvertimeTask).where(
            OvertimeTask.id.in_(select(sub.c.overtime_id)),
            OvertimeTask.warehouse_id == wh_id,
        ).order_by(OvertimeTask.date.desc())
    )).scalars().all()

    # 取该员工在每个任务里的分配记录（金额 / 实际小时数 / 异议标记）
    task_ids = [t.id for t in tasks]
    assign_map = {}
    if task_ids:
        asns = (await db.execute(
            select(OvertimeAssignment).where(
                OvertimeAssignment.overtime_id.in_(task_ids),
                OvertimeAssignment.employee_id == emp.id,
            )
        )).scalars().all()
        assign_map = {a.overtime_id: a for a in asns}

    return {
        "data": [{
            "id": t.id,
            "date": t.date.isoformat(),
            "start_time": t.start_time,
            "end_time": t.end_time,
            "hours": t.hours,
            "half_hours": _half_hours_from_times(t.start_time, t.end_time),
            "needs_verification": t.needs_verification,
            "earned_amount": assign_map[t.id].earned_amount if t.id in assign_map else 0,
            "actual_hours": assign_map[t.id].actual_hours if t.id in assign_map else None,
            "has_dispute": assign_map[t.id].has_dispute if t.id in assign_map else False,
            "dispute_reason": assign_map[t.id].dispute_reason if t.id in assign_map else None,
            "hourly_rate": t.hourly_rate,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        } for t in tasks],
        "pending_count": len(tasks),
    }


# ═══ Monthly Overtime Hours for Employee ═══════════

@router.get("/monthly-hours")
async def monthly_hours(
    month: str = None,
    current_user: User = Depends(employee_access(_PERMISSION)),
    db: AsyncSession = Depends(get_db),
):
    if month is None:
        month = thai_today().strftime("%Y-%m")

    if employee_view(current_user):
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
    current_user: User = Depends(employee_access(_PERMISSION)),
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
    current_user: User = Depends(check_staff_permission(_PERMISSION)),
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
    current_user: User = Depends(check_staff_permission(_PERMISSION)),
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
                or_(User.role == "warehouse_labor", and_(User.role == "supervisor", User.attendance_enabled == True, User.attendance_employee_id == emp.id, User.warehouse_id == emp.warehouse_id)),
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
    if employee_view(user):
        return getattr(user, "_attendance_employee", None)
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


async def _get_monthly_overtime_for_verify(db: AsyncSession, employee_id: int, month_date, exclude_task_id: int) -> float:
    """核实时的月度累计：已核实的任务用实际小时数，没核实的用计划小时数，排除指定任务。"""
    d = month_date if not isinstance(month_date, str) else datetime.strptime(month_date, "%Y-%m-%d").date()
    month_start = d.replace(day=1)
    if month_start.month == 12:
        month_end = month_start.replace(year=month_start.year + 1, month=1, day=1)
    else:
        month_end = month_start.replace(month=month_start.month + 1, day=1)

    rows = (await db.execute(
        select(OvertimeTask.id, OvertimeTask.hours, OvertimeAssignment.actual_hours)
        .join(OvertimeAssignment, OvertimeAssignment.overtime_id == OvertimeTask.id)
        .where(
            OvertimeAssignment.employee_id == employee_id,
            OvertimeTask.date >= month_start,
            OvertimeTask.date < month_end,
            OvertimeTask.id != exclude_task_id,
        )
    )).all()
    total = 0.0
    for _tid, planned, actual in rows:
        total += (actual if actual is not None else planned)
    return total


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

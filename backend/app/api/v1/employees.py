from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.models.employee import Employee
from app.models.warehouse import Warehouse
from app.models.user import User
from app.models.user_warehouse import UserWarehouse
from app.models.salary_template import SalaryTemplate
from app.models.deduction_template import DeductionTemplate
from app.core.permissions import get_current_user, get_wh_id, get_wh_ids, Role
from app.core.security import hash_password
from app.services.image_utils import thumb_path_of
from app.core.timezone import thai_now
from pydantic import BaseModel
from datetime import datetime, date, timedelta
from typing import Optional, List

router = APIRouter()

class EmployeeCreate(BaseModel):
    name: str
    employee_no: str  # 工号 = 登录用户名，必填
    password: str     # 登录密码，必填（至少6位）
    position: str = "仓库劳工"
    user_id: Optional[int] = None  # 关联登录账号
    myanmar_id: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    emergency_contact: Optional[str] = None
    hire_date: Optional[str] = None
    status: str = "trial"
    daily_wage: float = 400
    base_salary: float = 12000
    salary_template_id: Optional[int] = None
    deduction_template_id: Optional[int] = None
    remark: Optional[str] = None
    passport_number: Optional[str] = None
    work_permit_number: Optional[str] = None
    passport_expiry: Optional[str] = None
    work_permit_expiry: Optional[str] = None
    promotion_date: Optional[str] = None
    tags: Optional[str] = None

class EmployeeUpdate(BaseModel):
    name: Optional[str] = None
    employee_no: Optional[str] = None  # 工号 = 登录用户名
    password: Optional[str] = None     # 留空表示不修改
    position: Optional[str] = None
    myanmar_id: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    emergency_contact: Optional[str] = None
    hire_date: Optional[str] = None
    status: Optional[str] = None
    daily_wage: Optional[float] = None
    base_salary: Optional[float] = None
    salary_template_id: Optional[int] = None
    deduction_template_id: Optional[int] = None
    remark: Optional[str] = None
    user_id: Optional[int] = None
    passport_number: Optional[str] = None
    work_permit_number: Optional[str] = None
    passport_expiry: Optional[str] = None
    work_permit_expiry: Optional[str] = None
    promotion_date: Optional[str] = None
    tags: Optional[str] = None

class ResignRequest(BaseModel):
    reason: str  # voluntary / absconded / fired / contract_end / other
    resignation_date: str  # YYYY-MM-DD
    blacklisted: bool = False
    blacklist_reason: Optional[str] = None
    note: Optional[str] = None
    name: Optional[str] = None
    position: Optional[str] = None
    myanmar_id: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    emergency_contact: Optional[str] = None
    hire_date: Optional[str] = None
    status: Optional[str] = None
    daily_wage: Optional[float] = None
    base_salary: Optional[float] = None
    remark: Optional[str] = None

@router.get("")
async def list_employees(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    status: str | None = None,
    include_deleted: bool = False,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
        raise HTTPException(403, "无权限")
    
    wh_ids = get_wh_ids(current_user)
    query = select(Employee)
    count_q = select(func.count(Employee.id))
    query = query.where(Employee.warehouse_id.in_(wh_ids))
    count_q = count_q.where(Employee.warehouse_id.in_(wh_ids))
    if not include_deleted:
        query = query.where(Employee.is_deleted == False)
        count_q = count_q.where(Employee.is_deleted == False)
    if status:
        query = query.where(Employee.status == status)
        count_q = count_q.where(Employee.status == status)
    
    total = (await db.execute(count_q)).scalar()
    result = await db.execute(
        query.order_by(Employee.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    emps = result.scalars().all()
    wh_ids_set = {e.warehouse_id for e in emps}
    wh_map = {}
    if wh_ids_set:
        whs = (await db.execute(select(Warehouse).where(Warehouse.id.in_(wh_ids_set)))).scalars().all()
        wh_map = {w.id: w.name for w in whs}
    uid_set = {e.user_id for e in emps if e.user_id}
    username_map = {}
    if uid_set:
        us = (await db.execute(select(User).where(User.id.in_(uid_set)))).scalars().all()
        username_map = {u.id: u.username for u in us}
    st_ids = {e.salary_template_id for e in emps if e.salary_template_id}
    st_map = {}
    if st_ids:
        sts = (await db.execute(select(SalaryTemplate).where(SalaryTemplate.id.in_(st_ids)))).scalars().all()
        st_map = {s.id: s for s in sts}
    dt_ids = {e.deduction_template_id for e in emps if e.deduction_template_id}
    dt_map = {}
    if dt_ids:
        dts = (await db.execute(select(DeductionTemplate).where(DeductionTemplate.id.in_(dt_ids)))).scalars().all()
        dt_map = {d.id: d for d in dts}
    
    return {
        "data": [{
            "id": e.id, "warehouse_id": e.warehouse_id, "warehouse_name": wh_map.get(e.warehouse_id, ""),
            "name": e.name, "position": e.position,
            "employee_no": username_map.get(e.user_id, "") if e.user_id else "",
            "user_id": e.user_id, "myanmar_id": e.myanmar_id,
            "address": e.address, "phone": e.phone, "emergency_contact": e.emergency_contact,
            "hire_date": e.hire_date.isoformat()[:10] if e.hire_date else None,
            "status": e.status, "daily_wage": e.daily_wage, "base_salary": e.base_salary,
            "salary_template_id": e.salary_template_id,
            "salary_template_name": st_map.get(e.salary_template_id).name if st_map.get(e.salary_template_id) else "",
            "salary_template_type": st_map.get(e.salary_template_id).type if st_map.get(e.salary_template_id) else "",
            "salary_template_amount": st_map.get(e.salary_template_id).amount if st_map.get(e.salary_template_id) else None,
            "salary_template_overtime_fee": st_map.get(e.salary_template_id).overtime_half_hour_fee if st_map.get(e.salary_template_id) else None,
            "deduction_template_id": e.deduction_template_id,
            "deduction_template_name": dt_map.get(e.deduction_template_id).name if dt_map.get(e.deduction_template_id) else "",
            "remark": e.remark,
            "photo_path": e.photo_path,
            "photo_thumb_path": thumb_path_of(e.photo_path),
            "passport_photo_path": e.passport_photo_path,
            "passport_photo_thumb_path": thumb_path_of(e.passport_photo_path),
            "work_permit_photo_path": e.work_permit_photo_path,
            "work_permit_photo_thumb_path": thumb_path_of(e.work_permit_photo_path),
            "passport_number": e.passport_number,
            "work_permit_number": e.work_permit_number,
            "passport_expiry": e.passport_expiry.isoformat() if e.passport_expiry else None,
            "work_permit_expiry": e.work_permit_expiry.isoformat() if e.work_permit_expiry else None,
            "promotion_date": e.promotion_date.isoformat() if e.promotion_date else None,
            "tags": e.tags.split(",") if e.tags else [],
            "resignation_date": e.resignation_date.isoformat() if e.resignation_date else None,
            "resignation_reason": e.resignation_reason,
            "resignation_note": e.resignation_note,
            "is_deleted": bool(e.is_deleted),
            "deleted_by": e.deleted_by,
            "deleted_at": e.deleted_at.isoformat() if e.deleted_at else None,
            "blacklisted": e.blacklisted,
            "blacklist_reason": e.blacklist_reason,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        } for e in emps],
        "total": total, "page": page, "page_size": page_size,
    }

@router.post("")
async def create_employee(
    req: EmployeeCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
        raise HTTPException(403, "只有仓库管理员可以创建员工")
    
    wh_id = get_wh_id(current_user)
    if not wh_id:
        raise HTTPException(400, "请先选择仓库")

    # === 工号与登录账号校验 ===
    employee_no = (req.employee_no or "").strip()
    password = req.password or ""
    if not employee_no:
        raise HTTPException(400, "工号必填")
    if not password:
        raise HTTPException(400, "密码必填")
    if len(password) < 6:
        raise HTTPException(400, "密码至少6位")
    # 工号(用户名)唯一性：包括已禁用账号也占用工号
    existing_user = (await db.execute(
        select(User).where(User.username == employee_no)
    )).scalar_one_or_none()
    if existing_user:
        raise HTTPException(400, "该工号已被使用")

    # 薪资模板必选（先校验，避免创建账号后又失败）
    if not req.salary_template_id:
        raise HTTPException(400, "请选择薪资模板")
    template = (await db.execute(
        select(SalaryTemplate).where(SalaryTemplate.id == req.salary_template_id, SalaryTemplate.warehouse_id == wh_id)
    )).scalar_one_or_none()
    if not template:
        raise HTTPException(400, "薪资模板不存在")
    daily_wage = req.daily_wage or 400
    base_salary = req.base_salary or 12000
    if template.type in ("hourly", "daily"):
        daily_wage = template.amount
    else:
        base_salary = template.amount

    # 扣款模板（可留空 = 不扣考勤类款）
    deduction_template_id = req.deduction_template_id or None
    if deduction_template_id:
        dt = (await db.execute(
            select(DeductionTemplate).where(DeductionTemplate.id == deduction_template_id, DeductionTemplate.warehouse_id == wh_id)
        )).scalar_one_or_none()
        if not dt:
            raise HTTPException(400, "扣款模板不存在")

    # 先创建登录账号（仓库劳工）
    new_user = User(
        username=employee_no,
        password_hash=hash_password(password),
        display_name=req.name,
        role=Role.WAREHOUSE_LABOR.value,
        warehouse_id=wh_id,
        is_active=True,
        created_by=current_user.id,
    )
    db.add(new_user)
    await db.flush()
    db.add(UserWarehouse(user_id=new_user.id, warehouse_id=wh_id))

    # Check max_employees limit
    wh = (await db.execute(select(Warehouse).where(Warehouse.id == wh_id))).scalar_one_or_none()
    if wh and wh.max_employees:
        # Count active (non-resigned) employees
        active_count = (await db.execute(
            select(func.count(Employee.id)).where(
                Employee.warehouse_id == wh_id,
                Employee.status != "resigned",
                Employee.is_deleted == False,
            )
        )).scalar()
        if active_count and active_count >= wh.max_employees:
            raise HTTPException(400, f"员工人数已达上限 ({wh.max_employees}人)，无法新增")
    
    hire_date = None
    if req.hire_date:
        try:
            hire_date = datetime.fromisoformat(req.hire_date)
        except:
            pass
    
    e = Employee(
        warehouse_id=wh_id, name=req.name, position=req.position,
        user_id=new_user.id,
        myanmar_id=req.myanmar_id, address=req.address, phone=req.phone,
        emergency_contact=req.emergency_contact, hire_date=hire_date,
        status=req.status, daily_wage=daily_wage, base_salary=base_salary,
        salary_template_id=template.id,
        deduction_template_id=deduction_template_id,
        remark=req.remark, created_by=current_user.id,
    )
    db.add(e)
    await db.flush()
    return {"id": e.id, "employee_no": employee_no, "message": "员工创建成功"}

@router.put("/{employee_id}")
async def update_employee(
    employee_id: int,
    req: EmployeeUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
        raise HTTPException(403, "只有仓库管理员可以编辑员工")
    
    e = (await db.execute(select(Employee).where(Employee.id == employee_id))).scalar_one_or_none()
    if not e:
        raise HTTPException(404, "员工不存在")
    
    wh_ids = get_wh_ids(current_user)
    if e.warehouse_id not in wh_ids:
        raise HTTPException(403, "只能编辑自己仓库的员工")
    
    updates = req.model_dump(exclude_unset=True)

    # === 工号 / 密码：同步登录账号（与员工档案字段分离处理）===
    employee_no = updates.pop("employee_no", None)
    password = updates.pop("password", None)
    if employee_no is not None:
        employee_no = str(employee_no).strip()
    if password is not None:
        password = str(password)

    # 编辑时工号必填
    if employee_no is not None and employee_no == "":
        raise HTTPException(400, "工号必填")

    linked_user = None
    if e.user_id:
        linked_user = (await db.execute(select(User).where(User.id == e.user_id))).scalar_one_or_none()

    if employee_no:
        # 工号唯一性（含禁用账号；排除当前已绑定账号）
        q = select(User).where(User.username == employee_no)
        if linked_user:
            q = q.where(User.id != linked_user.id)
        dup = (await db.execute(q)).scalar_one_or_none()
        if dup:
            raise HTTPException(400, "该工号已被使用")

        if linked_user:
            # 改了工号 → 同步修改关联账号用户名
            linked_user.username = employee_no
        else:
            # 原无账号：填了工号+密码 → 创建账号并绑定
            if not password or len(password) < 6:
                raise HTTPException(400, "该员工暂无登录账号，请填写密码（至少6位）以创建账号")
            linked_user = User(
                username=employee_no,
                password_hash=hash_password(password),
                display_name=req.name or e.name,
                role=Role.WAREHOUSE_LABOR.value,
                warehouse_id=e.warehouse_id,
                is_active=True,
                created_by=current_user.id,
            )
            db.add(linked_user)
            await db.flush()
            db.add(UserWarehouse(user_id=linked_user.id, warehouse_id=e.warehouse_id))
            e.user_id = linked_user.id
            password = None  # 已用于创建账号

    if password:
        if len(password) < 6:
            raise HTTPException(400, "密码至少6位")
        if linked_user:
            linked_user.password_hash = hash_password(password)

    if "hire_date" in updates and updates["hire_date"] is not None:
        try:
            updates["hire_date"] = datetime.fromisoformat(updates["hire_date"])
        except:
            del updates["hire_date"]
    
    # Handle date fields
    date_fields = ["passport_expiry", "work_permit_expiry", "promotion_date"]
    for df in date_fields:
        if df in updates and updates[df] is not None:
            try:
                updates[df] = datetime.strptime(updates[df], "%Y-%m-%d").date()
            except:
                del updates[df]
        elif df in updates and updates[df] in ("", None):
            updates[df] = None
    
    # 薪资模板变更
    if "salary_template_id" in updates:
        st_id = updates.pop("salary_template_id")
        if st_id:
            template = (await db.execute(
                select(SalaryTemplate).where(SalaryTemplate.id == st_id, SalaryTemplate.warehouse_id == e.warehouse_id)
            )).scalar_one_or_none()
            if not template:
                raise HTTPException(400, "薪资模板不存在")
            e.salary_template_id = template.id
            if template.type in ("hourly", "daily"):
                e.daily_wage = template.amount
            else:
                e.base_salary = template.amount

    # 扣款模板变更（可清空 = 不扣考勤类款）
    if "deduction_template_id" in updates:
        dt_id = updates.pop("deduction_template_id")
        if dt_id:
            dt = (await db.execute(
                select(DeductionTemplate).where(DeductionTemplate.id == dt_id, DeductionTemplate.warehouse_id == e.warehouse_id)
            )).scalar_one_or_none()
            if not dt:
                raise HTTPException(400, "扣款模板不存在")
            e.deduction_template_id = dt.id
        else:
            e.deduction_template_id = None

    for k, v in updates.items():
        setattr(e, k, v)
    await db.flush()
    return {"message": "更新成功"}

@router.post("/{employee_id}/resign")
async def resign_employee(
    employee_id: int,
    req: ResignRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
        raise HTTPException(403, "只有仓库管理员可以操作")
    
    e = (await db.execute(select(Employee).where(Employee.id == employee_id))).scalar_one_or_none()
    if not e:
        raise HTTPException(404, "员工不存在")
    
    wh_ids = get_wh_ids(current_user)
    if e.warehouse_id not in wh_ids:
        raise HTTPException(403, "只能操作自己仓库的员工")
    
    # Parse resignation date
    try:
        resign_dt = datetime.strptime(req.resignation_date, "%Y-%m-%d").date()
    except:
        raise HTTPException(400, "日期格式错误，应为 YYYY-MM-DD")

    # Capture original status for payroll calculation & 人效时薪估算
    emp_original_status = e.status
    if emp_original_status != "resigned":
        e.pre_resign_status = emp_original_status

    # 自动结算：调用工资页面同一套计算逻辑（员工ID + 结算截止日=离职日）
    payroll_msg = ""
    try:
        from app.api.v1.payroll import _calc_payroll, CalculateRequest
        period = resign_dt.strftime("%Y-%m")
        half = "first_half" if resign_dt.day <= 15 else "second_half"
        r = await _calc_payroll(
            db, current_user, e.warehouse_id,
            CalculateRequest(period=period, half=half, employee_ids=[employee_id], end_date=req.resignation_date, is_resignation=True),
        )
        if r.get("record_count", 0) > 0:
            payroll_msg = f"，已生成离职结算工资单（结算到 {resign_dt.isoformat()}）"
        else:
            payroll_msg = f"，本期工资已结算过，跳过"
    except Exception as ex:
        payroll_msg = f"，工资结算失败: {str(ex)}"

    # Update employee
    e.status = "resigned"
    e.resignation_date = resign_dt
    e.resignation_reason = req.reason
    e.resignation_note = req.note
    if req.blacklisted:
        e.blacklisted = True
        e.blacklist_reason = req.blacklist_reason or "被辞退"

    # Disable linked user account
    linked_user = await _find_linked_user(db, e)
    if linked_user:
        linked_user.is_active = False

    await db.flush()


    reason_cn = {
        "voluntary": "正常离职", "absconded": "自离",
        "fired": "被辞退", "contract_end": "合同到期", "other": "其他"
    }

    return {
        "message": f"已将{e.name}标记为离职（{reason_cn.get(req.reason, req.reason)}）{payroll_msg}",
        "employee_id": e.id,
        "blacklisted": e.blacklisted,
    }


@router.delete("/{employee_id}")
async def delete_employee(
    employee_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """软删除员工档案：打删除标记，保留打卡/工资/加班等关联数据，并禁用关联登录账号。"""
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
        raise HTTPException(403, "只有仓库管理员/主管可以删除员工")
    e = (await db.execute(select(Employee).where(Employee.id == employee_id))).scalar_one_or_none()
    if not e:
        raise HTTPException(404, "员工不存在")
    wh_ids = get_wh_ids(current_user)
    if e.warehouse_id not in wh_ids:
        raise HTTPException(403, "只能删除自己管理仓库的员工")
    if e.is_deleted:
        raise HTTPException(400, "该员工已删除")

    e.is_deleted = True
    e.deleted_by = current_user.id
    e.deleted_at = thai_now()

    # 禁用关联登录账号，防止已删除员工继续登录/打卡
    if e.user_id:
        linked = (await db.execute(select(User).where(User.id == e.user_id))).scalar_one_or_none()
        if linked:
            linked.is_active = False
    await db.flush()
    return {"message": f"已删除员工 {e.name}（软删除，数据保留）", "employee_id": e.id}


@router.post("/bind-existing-accounts")
async def bind_existing_accounts(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """批量绑定已有账号：扫描当前仓库未绑定账号的在职员工，按 手机号=用户名 / 姓名=显示名 自动绑定仓库劳工账号。"""
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
        raise HTTPException(403, "只有仓库管理员/主管可以操作")

    wh_id = get_wh_id(current_user)
    if not wh_id:
        raise HTTPException(400, "请先选择仓库")

    # 未绑定账号的在职员工（排除已删除/离职）
    unbound_emps = (await db.execute(
        select(Employee).where(
            Employee.warehouse_id == wh_id,
            Employee.is_deleted == False,
            Employee.status != "resigned",
            Employee.user_id.is_(None),
        ).order_by(Employee.name)
    )).scalars().all()

    if not unbound_emps:
        return {"message": "没有需要绑定的员工", "bound": 0, "not_found": 0, "details": []}

    # 该仓库已被其他员工占用的账号，避免重复绑定
    used_uids = (await db.execute(
        select(Employee.user_id).where(
            Employee.warehouse_id == wh_id,
            Employee.user_id.isnot(None),
        )
    )).scalars().all()
    used_uids = {u for u in used_uids if u is not None}

    # 该仓库的仓库劳工账号（排除已被占用的）
    q = select(User).where(
        User.role == "warehouse_labor",
        User.warehouse_id == wh_id,
    )
    if used_uids:
        q = q.where(User.id.notin_(used_uids))
    labor_users = (await db.execute(q)).scalars().all()

    by_username = {}
    by_display = {}
    for u in labor_users:
        by_username.setdefault((u.warehouse_id, u.username), u)
        by_display.setdefault((u.warehouse_id, u.display_name), u)

    bound = 0
    not_found = 0
    details = []
    for e in unbound_emps:
        u = None
        if e.phone:
            u = by_username.get((wh_id, e.phone))
        if not u and e.name:
            u = by_display.get((wh_id, e.name))
        if u:
            e.user_id = u.id
            bound += 1
            details.append({"employee_id": e.id, "name": e.name, "username": u.username})
            # 一个账号只绑定一个员工
            by_username.pop((wh_id, u.username), None)
            by_display.pop((wh_id, u.display_name), None)
        else:
            not_found += 1

    await db.flush()
    return {
        "message": f"绑定完成：成功 {bound} 个，未找到 {not_found} 个",
        "bound": bound,
        "not_found": not_found,
        "details": details,
    }


async def _find_linked_user(db: AsyncSession, emp: Employee):
    """Find linked user account for an employee (by user_id, then by name)"""
    if emp.user_id:
        user = (await db.execute(
            select(User).where(User.id == emp.user_id, User.is_active == True)
        )).scalar_one_or_none()
        if user:
            return user
    # Fallback to name matching for legacy data
    user = (await db.execute(
        select(User).where(
            User.display_name == emp.name,
            User.role == "warehouse_labor",
            User.is_active == True,
        )
    )).scalar_one_or_none()
    return user


class BatchTemplateSet(BaseModel):
    employee_ids: List[int]
    salary_template_id: int
    deduction_template_id: int


@router.post("/batch-set-templates")
async def batch_set_templates(
    req: BatchTemplateSet,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """批量给员工设置薪资模板和扣款模板。仅仓库管理员/主管。"""
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
        raise HTTPException(403, "只有仓库管理员/主管可以批量设置模板")

    wh_id = get_wh_id(current_user)
    if not wh_id:
        raise HTTPException(400, "请先选择仓库")

    ids = list(dict.fromkeys(req.employee_ids or []))
    if not ids:
        raise HTTPException(400, "请选择员工")

    salary_tpl = (await db.execute(
        select(SalaryTemplate).where(SalaryTemplate.id == req.salary_template_id, SalaryTemplate.warehouse_id == wh_id)
    )).scalar_one_or_none()
    if not salary_tpl:
        raise HTTPException(400, "薪资模板不存在")

    deduction_tpl = (await db.execute(
        select(DeductionTemplate).where(DeductionTemplate.id == req.deduction_template_id, DeductionTemplate.warehouse_id == wh_id)
    )).scalar_one_or_none()
    if not deduction_tpl:
        raise HTTPException(400, "扣款模板不存在")

    emps = (await db.execute(
        select(Employee).where(Employee.id.in_(ids), Employee.warehouse_id == wh_id)
    )).scalars().all()
    if len(emps) != len(ids):
        raise HTTPException(403, "包含无权操作的员工")

    for e in emps:
        e.salary_template_id = salary_tpl.id
        e.deduction_template_id = deduction_tpl.id
        # 按薪资模板同步日薪/底薪字段（跟单个设置一致）
        if salary_tpl.type in ("hourly", "daily"):
            e.daily_wage = salary_tpl.amount
        else:
            e.base_salary = salary_tpl.amount

    await db.flush()
    return {"message": f"已为 {len(emps)} 名员工设置模板", "count": len(emps)}



# ═══ Photo Upload ════════════════════════════

@router.post("/{employee_id}/photo")
async def upload_employee_photo(
    employee_id: int,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
        raise HTTPException(403, "只有仓库管理员可以上传照片")

    wh_id = get_wh_id(current_user)
    if not wh_id:
        raise HTTPException(400, "请先选择仓库")

    emp = (await db.execute(
        select(Employee).where(Employee.id == employee_id, Employee.warehouse_id == wh_id, Employee.is_deleted == False)
    )).scalar_one_or_none()
    if not emp:
        raise HTTPException(404, "员工不存在")

    # Save photo（压缩 + 缩略图）
    import os, uuid
    from app.services.image_utils import save_image
    ext = file.filename.split(".")[-1].lower() if file.filename else "jpg"
    content_bytes = await file.read()
    today_str = datetime.now().strftime("%Y-%m-%d")
    abs_subdir = os.path.join("/app/uploads", str(wh_id), today_str, "employee_photos")
    rel_subdir = f"uploads/{wh_id}/{today_str}/employee_photos"
    fname = f"{uuid.uuid4().hex}.{ext}"
    result = save_image(content_bytes, abs_subdir, rel_subdir, fname)

    emp.photo_path = result["path"]
    await db.flush()
    return {"message": "照片上传成功", "photo_path": result["path"], "photo_thumb_path": result["thumb_path"]}


# ═══ Passport & Work Permit Photo Upload ═══════

@router.post("/{employee_id}/passport-photo")
async def upload_passport_photo(
    employee_id: int,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
        raise HTTPException(403, "只有仓库管理员可以上传照片")

    wh_id = get_wh_id(current_user)
    if not wh_id:
        raise HTTPException(400, "请先选择仓库")

    emp = (await db.execute(
        select(Employee).where(Employee.id == employee_id, Employee.warehouse_id == wh_id, Employee.is_deleted == False)
    )).scalar_one_or_none()
    if not emp:
        raise HTTPException(404, "员工不存在")

    import os, uuid
    from app.services.image_utils import save_image
    ext = file.filename.split(".")[-1].lower() if file.filename else "jpg"
    content_bytes = await file.read()
    today_str = datetime.now().strftime("%Y-%m-%d")
    abs_subdir = os.path.join("/app/uploads", str(wh_id), today_str, "employee_photos")
    rel_subdir = f"uploads/{wh_id}/{today_str}/employee_photos"
    fname = f"{uuid.uuid4().hex}.{ext}"
    result = save_image(content_bytes, abs_subdir, rel_subdir, fname)

    emp.passport_photo_path = result["path"]
    await db.flush()
    return {"message": "护照照片上传成功", "passport_photo_path": result["path"], "passport_photo_thumb_path": result["thumb_path"]}


@router.post("/{employee_id}/work-permit-photo")
async def upload_work_permit_photo(
    employee_id: int,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
        raise HTTPException(403, "只有仓库管理员可以上传照片")

    wh_id = get_wh_id(current_user)
    if not wh_id:
        raise HTTPException(400, "请先选择仓库")

    emp = (await db.execute(
        select(Employee).where(Employee.id == employee_id, Employee.warehouse_id == wh_id, Employee.is_deleted == False)
    )).scalar_one_or_none()
    if not emp:
        raise HTTPException(404, "员工不存在")

    import os, uuid
    from app.services.image_utils import save_image
    ext = file.filename.split(".")[-1].lower() if file.filename else "jpg"
    content_bytes = await file.read()
    today_str = datetime.now().strftime("%Y-%m-%d")
    abs_subdir = os.path.join("/app/uploads", str(wh_id), today_str, "employee_photos")
    rel_subdir = f"uploads/{wh_id}/{today_str}/employee_photos"
    fname = f"{uuid.uuid4().hex}.{ext}"
    result = save_image(content_bytes, abs_subdir, rel_subdir, fname)

    emp.work_permit_photo_path = result["path"]
    await db.flush()
    return {"message": "工作证照片上传成功", "work_permit_photo_path": result["path"], "work_permit_photo_thumb_path": result["thumb_path"]}




# ═══ Monthly Summary ════════════════════════════

@router.get("/{employee_id}/summary")
async def employee_summary(
    employee_id: int,
    month: str = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return attendance & salary summary for an employee"""
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
        raise HTTPException(403, "无权限")

    wh_ids = get_wh_ids(current_user)
    emp = (await db.execute(
        select(Employee).where(Employee.id == employee_id, Employee.warehouse_id.in_(wh_ids))
    )).scalar_one_or_none()
    if not emp:
        raise HTTPException(404, "员工不存在")

    today = datetime.now()
    if not month:
        month = today.strftime("%Y-%m")

    from app.models.clock_in_records import ClockInRecord
    from app.models.overtime import OvertimeAssignment, OvertimeTask
    from app.models.payroll import PayrollRecord

    # Find linked user
    uid = emp.user_id
    if not uid:
        u = await _find_linked_user(db, emp)
        uid = u.id if u else None

    # Attendance summary
    late_count = 0
    attendance_days = 0
    if uid:
        ym_start = datetime.strptime(f"{month}-01", "%Y-%m-%d").date()
        if ym_start.month == 12:
            ym_end = ym_start.replace(year=ym_start.year+1, month=1, day=1)
        else:
            ym_end = ym_start.replace(month=ym_start.month+1, day=1)
        records = (await db.execute(
            select(ClockInRecord).where(
                ClockInRecord.user_id == uid,
                ClockInRecord.clock_date >= ym_start,
                ClockInRecord.clock_date < ym_end,
            )
        )).scalars().all()
        dates_with_records = set()
        for r in records:
            dates_with_records.add(r.clock_date)
            if r.status in ("late_half", "late_one"):
                late_count += 1
        attendance_days = len(dates_with_records)

    # Overtime hours this month
    ot_hours = 0.0
    if uid:
        ym_start = datetime.strptime(f"{month}-01", "%Y-%m-%d").date()
        if ym_start.month == 12:
            ym_end = ym_start.replace(year=ym_start.year+1, month=1, day=1)
        else:
            ym_end = ym_start.replace(month=ym_start.month+1, day=1)
        ot_result = (await db.execute(
            select(func.sum(OvertimeTask.hours))
            .join(OvertimeAssignment, OvertimeAssignment.overtime_id == OvertimeTask.id)
            .where(
                OvertimeAssignment.user_id == uid,
                OvertimeAssignment.confirmed == True,
                OvertimeTask.date >= ym_start,
                OvertimeTask.date < ym_end,
            )
        )).scalar()
        ot_hours = round(ot_result or 0, 1)

    # Payroll record
    payroll = (await db.execute(
        select(PayrollRecord).where(
            PayrollRecord.employee_id == employee_id,
            PayrollRecord.period == month,
        )
    )).scalar_one_or_none()

    payroll_data = None
    if payroll:
        payroll_data = {
            "id": payroll.id,
            "status": payroll.status,
            "disbursed": payroll.disbursed,
            "net_pay": payroll.net_pay,
            "base_pay": payroll.base_pay,
            "overtime_pay": payroll.overtime_pay,
            "late_penalty": payroll.late_penalty,
        }

    return {
        "employee_id": employee_id,
        "employee_name": emp.name,
        "month": month,
        "attendance_days": attendance_days,
        "late_count": late_count,
        "overtime_hours": ot_hours,
        "payroll": payroll_data,
    }

@router.get("/max-limit")
async def get_max_limit(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
        raise HTTPException(403, "无权限")
    wh_id = get_wh_id(current_user)
    if not wh_id:
        return {"max_employees": 50, "current_count": 0}
    wh = (await db.execute(select(Warehouse).where(Warehouse.id == wh_id))).scalar_one_or_none()
    max_val = wh.max_employees if wh and wh.max_employees else 50
    active_count = (await db.execute(
        select(func.count(Employee.id)).where(
            Employee.warehouse_id == wh_id, Employee.status != "resigned", Employee.is_deleted == False
        )
    )).scalar()
    return {"max_employees": max_val, "current_count": active_count or 0}

@router.put("/max-limit")
async def set_max_limit(
    max_employees: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
        raise HTTPException(403, "无权限")
    wh_id = get_wh_id(current_user)
    if not wh_id:
        raise HTTPException(400, "请先选择仓库")
    wh = (await db.execute(select(Warehouse).where(Warehouse.id == wh_id))).scalar_one_or_none()
    if not wh:
        raise HTTPException(404, "仓库不存在")
    wh.max_employees = max_employees
    await db.flush()
    return {"message": f"人数上限已设为 {max_employees}", "max_employees": max_employees}

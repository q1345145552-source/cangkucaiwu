from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.models.employee import Employee
from app.models.warehouse import Warehouse
from app.models.user import User
from app.core.permissions import get_current_user, get_wh_id, get_wh_ids, Role
from pydantic import BaseModel
from datetime import datetime
from typing import Optional

router = APIRouter()

class EmployeeCreate(BaseModel):
    name: str
    position: str = "仓库劳工"
    myanmar_id: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    emergency_contact: Optional[str] = None
    hire_date: Optional[str] = None
    status: str = "trial"
    daily_wage: float = 400
    base_salary: float = 12000
    remark: Optional[str] = None

class EmployeeUpdate(BaseModel):
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
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPER_ADMIN):
        raise HTTPException(403, "无权限")
    
    wh_ids = get_wh_ids(current_user)
    query = select(Employee)
    count_q = select(func.count(Employee.id))
    if current_user.role != Role.SUPER_ADMIN:
        query = query.where(Employee.warehouse_id.in_(wh_ids))
        count_q = count_q.where(Employee.warehouse_id.in_(wh_ids))
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
    
    return {
        "data": [{
            "id": e.id, "warehouse_id": e.warehouse_id, "warehouse_name": wh_map.get(e.warehouse_id, ""),
            "name": e.name, "position": e.position, "myanmar_id": e.myanmar_id,
            "address": e.address, "phone": e.phone, "emergency_contact": e.emergency_contact,
            "hire_date": e.hire_date.isoformat()[:10] if e.hire_date else None,
            "status": e.status, "daily_wage": e.daily_wage, "base_salary": e.base_salary,
            "remark": e.remark, "created_at": e.created_at.isoformat() if e.created_at else None,
        } for e in emps],
        "total": total, "page": page, "page_size": page_size,
    }

@router.post("")
async def create_employee(
    req: EmployeeCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in (Role.WAREHOUSE_ADMIN,):
        raise HTTPException(403, "只有仓库管理员可以创建员工")
    
    wh_id = get_wh_id(current_user)
    if not wh_id:
        raise HTTPException(400, "请先选择仓库")
    
    # Check max_employees limit
    wh = (await db.execute(select(Warehouse).where(Warehouse.id == wh_id))).scalar_one_or_none()
    if wh and wh.max_employees:
        # Count active (non-resigned) employees
        active_count = (await db.execute(
            select(func.count(Employee.id)).where(
                Employee.warehouse_id == wh_id,
                Employee.status != "resigned",
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
        myanmar_id=req.myanmar_id, address=req.address, phone=req.phone,
        emergency_contact=req.emergency_contact, hire_date=hire_date,
        status=req.status, daily_wage=req.daily_wage, base_salary=req.base_salary,
        remark=req.remark, created_by=current_user.id,
    )
    db.add(e)
    await db.flush()
    return {"id": e.id, "message": "员工创建成功"}

@router.put("/{employee_id}")
async def update_employee(
    employee_id: int,
    req: EmployeeUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in (Role.WAREHOUSE_ADMIN,):
        raise HTTPException(403, "只有仓库管理员可以编辑员工")
    
    e = (await db.execute(select(Employee).where(Employee.id == employee_id))).scalar_one_or_none()
    if not e:
        raise HTTPException(404, "员工不存在")
    
    wh_ids = get_wh_ids(current_user)
    if e.warehouse_id not in wh_ids:
        raise HTTPException(403, "只能编辑自己仓库的员工")
    
    updates = req.model_dump(exclude_unset=True)
    if "hire_date" in updates and updates["hire_date"] is not None:
        try:
            updates["hire_date"] = datetime.fromisoformat(updates["hire_date"])
        except:
            del updates["hire_date"]
    
    for k, v in updates.items():
        setattr(e, k, v)
    await db.flush()
    return {"message": "更新成功"}

@router.post("/{employee_id}/resign")
async def resign_employee(
    employee_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in (Role.WAREHOUSE_ADMIN,):
        raise HTTPException(403, "只有仓库管理员可以操作")
    
    e = (await db.execute(select(Employee).where(Employee.id == employee_id))).scalar_one_or_none()
    if not e:
        raise HTTPException(404, "员工不存在")
    
    wh_ids = get_wh_ids(current_user)
    if e.warehouse_id not in wh_ids:
        raise HTTPException(403, "只能操作自己仓库的员工")
    
    e.status = "resigned"
    await db.flush()
    return {"message": "已标记为离职"}

@router.get("/max-limit")
async def get_max_limit(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in (Role.WAREHOUSE_ADMIN,):
        raise HTTPException(403, "无权限")
    wh_id = get_wh_id(current_user)
    if not wh_id:
        return {"max_employees": 50, "current_count": 0}
    wh = (await db.execute(select(Warehouse).where(Warehouse.id == wh_id))).scalar_one_or_none()
    max_val = wh.max_employees if wh and wh.max_employees else 50
    active_count = (await db.execute(
        select(func.count(Employee.id)).where(
            Employee.warehouse_id == wh_id, Employee.status != "resigned"
        )
    )).scalar()
    return {"max_employees": max_val, "current_count": active_count or 0}

@router.put("/max-limit")
async def set_max_limit(
    max_employees: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in (Role.WAREHOUSE_ADMIN,):
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

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.employee_deduction import EmployeeDeduction, EmployeeFixedDeduction
from app.models.employee import Employee
from app.models.user import User
from app.core.permissions import get_current_user, get_wh_id, get_wh_ids, Role
from pydantic import BaseModel
from datetime import datetime
from typing import Optional

router = APIRouter()


def _check_role(current_user: User):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
        raise HTTPException(403, "无权限")


# ═══ 临时扣款记录 ════════════════════════════

class DeductionCreate(BaseModel):
    employee_id: int
    amount: float
    deduction_date: str  # YYYY-MM-DD
    reason: str


@router.post("")
async def create_deduction(
    req: DeductionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _check_role(current_user)
    wh_id = get_wh_id(current_user)
    if not wh_id:
        raise HTTPException(400, "请先选择仓库")

    if req.amount is None or req.amount <= 0:
        raise HTTPException(400, "扣款金额必须大于0")
    reason = (req.reason or "").strip()
    if not reason:
        raise HTTPException(400, "请填写扣款原因")

    try:
        d_dt = datetime.strptime(req.deduction_date, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        raise HTTPException(400, "扣款日期格式错误 YYYY-MM-DD")

    emp = (await db.execute(
        select(Employee).where(Employee.id == req.employee_id, Employee.warehouse_id == wh_id, Employee.is_deleted == False)
    )).scalar_one_or_none()
    if not emp:
        raise HTTPException(404, "员工不存在")

    # 所属周期自动按日期算：1-15 上半月，16-月末 下半月
    period = d_dt.strftime("%Y-%m")
    half = "first_half" if d_dt.day <= 15 else "second_half"

    d = EmployeeDeduction(
        warehouse_id=wh_id,
        employee_id=req.employee_id,
        amount=req.amount,
        deduction_date=d_dt,
        period=period,
        half=half,
        reason=reason,
        operator_id=current_user.id,
    )
    db.add(d)
    await db.flush()
    return {"message": "扣款记录已创建", "id": d.id}


@router.get("")
async def list_deductions(
    employee_id: Optional[int] = None,
    period: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _check_role(current_user)
    wh_ids = get_wh_ids(current_user)
    if not wh_ids:
        return {"data": [], "total": 0}

    q = select(EmployeeDeduction).where(EmployeeDeduction.warehouse_id.in_(wh_ids))
    if employee_id:
        q = q.where(EmployeeDeduction.employee_id == employee_id)
    if period:
        q = q.where(EmployeeDeduction.period == period)

    rows = (await db.execute(q.order_by(EmployeeDeduction.deduction_date.desc(), EmployeeDeduction.id.desc()))).scalars().all()

    emp_ids = {r.employee_id for r in rows}
    op_ids = {r.operator_id for r in rows if r.operator_id}
    emp_map = {}
    op_map = {}
    if emp_ids:
        es = (await db.execute(select(Employee).where(Employee.id.in_(emp_ids)))).scalars().all()
        emp_map = {e.id: e.name for e in es}
    if op_ids:
        us = (await db.execute(select(User).where(User.id.in_(op_ids)))).scalars().all()
        op_map = {u.id: u.display_name for u in us}

    return {
        "data": [{
            "id": r.id,
            "employee_id": r.employee_id,
            "employee_name": emp_map.get(r.employee_id, ""),
            "amount": r.amount,
            "deduction_date": r.deduction_date.isoformat(),
            "period": r.period,
            "half": r.half,
            "reason": r.reason,
            "operator_name": op_map.get(r.operator_id, ""),
            "created_at": r.created_at.isoformat() if r.created_at else None,
        } for r in rows],
        "total": len(rows),
    }


@router.delete("/{deduction_id}")
async def delete_deduction(
    deduction_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _check_role(current_user)
    wh_id = get_wh_id(current_user)
    if not wh_id:
        raise HTTPException(400, "请先选择仓库")

    r = (await db.execute(
        select(EmployeeDeduction).where(EmployeeDeduction.id == deduction_id, EmployeeDeduction.warehouse_id == wh_id)
    )).scalar_one_or_none()
    if not r:
        raise HTTPException(404, "扣款记录不存在")

    await db.delete(r)
    await db.flush()
    return {"message": "扣款记录已删除"}


# ═══ 固定扣款（员工档案）═══════════════════════════

class FixedDeductionCreate(BaseModel):
    employee_id: int
    name: str
    amount: float


class FixedDeductionUpdate(BaseModel):
    name: Optional[str] = None
    amount: Optional[float] = None


@router.get("/fixed")
async def list_fixed_deductions(
    employee_id: int = Query(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _check_role(current_user)
    wh_ids = get_wh_ids(current_user)
    if not wh_ids:
        return {"data": []}

    emp = (await db.execute(
        select(Employee).where(Employee.id == employee_id, Employee.warehouse_id.in_(wh_ids))
    )).scalar_one_or_none()
    if not emp:
        raise HTTPException(404, "员工不存在")

    rows = (await db.execute(
        select(EmployeeFixedDeduction).where(EmployeeFixedDeduction.employee_id == employee_id)
        .order_by(EmployeeFixedDeduction.id.asc())
    )).scalars().all()
    return {"data": [{
        "id": r.id, "employee_id": r.employee_id, "name": r.name, "amount": r.amount,
    } for r in rows]}


@router.post("/fixed")
async def create_fixed_deduction(
    req: FixedDeductionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _check_role(current_user)
    wh_id = get_wh_id(current_user)
    if not wh_id:
        raise HTTPException(400, "请先选择仓库")

    name = (req.name or "").strip()
    if not name:
        raise HTTPException(400, "请填写扣款项目名称")
    if req.amount is None or req.amount < 0:
        raise HTTPException(400, "金额必须大于等于0")

    emp = (await db.execute(
        select(Employee).where(Employee.id == req.employee_id, Employee.warehouse_id == wh_id, Employee.is_deleted == False)
    )).scalar_one_or_none()
    if not emp:
        raise HTTPException(404, "员工不存在")

    r = EmployeeFixedDeduction(warehouse_id=wh_id, employee_id=req.employee_id, name=name, amount=req.amount)
    db.add(r)
    await db.flush()
    return {"id": r.id, "message": "固定扣款已添加"}


@router.put("/fixed/{deduction_id}")
async def update_fixed_deduction(
    deduction_id: int,
    req: FixedDeductionUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _check_role(current_user)
    wh_id = get_wh_id(current_user)
    if not wh_id:
        raise HTTPException(400, "请先选择仓库")

    r = (await db.execute(
        select(EmployeeFixedDeduction).where(EmployeeFixedDeduction.id == deduction_id, EmployeeFixedDeduction.warehouse_id == wh_id)
    )).scalar_one_or_none()
    if not r:
        raise HTTPException(404, "固定扣款不存在")

    if req.name is not None:
        name = (req.name or "").strip()
        if not name:
            raise HTTPException(400, "请填写扣款项目名称")
        r.name = name
    if req.amount is not None:
        if req.amount < 0:
            raise HTTPException(400, "金额必须大于等于0")
        r.amount = req.amount

    await db.flush()
    return {"message": "固定扣款已更新"}


@router.delete("/fixed/{deduction_id}")
async def delete_fixed_deduction(
    deduction_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _check_role(current_user)
    wh_id = get_wh_id(current_user)
    if not wh_id:
        raise HTTPException(400, "请先选择仓库")

    r = (await db.execute(
        select(EmployeeFixedDeduction).where(EmployeeFixedDeduction.id == deduction_id, EmployeeFixedDeduction.warehouse_id == wh_id)
    )).scalar_one_or_none()
    if not r:
        raise HTTPException(404, "固定扣款不存在")

    await db.delete(r)
    await db.flush()
    return {"message": "固定扣款已删除"}

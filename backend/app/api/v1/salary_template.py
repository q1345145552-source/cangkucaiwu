from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.models.salary_template import SalaryTemplate
from app.models.employee import Employee
from app.models.user import User
from app.core.permissions import get_current_user, get_wh_id, get_wh_ids, Role
from pydantic import BaseModel
from typing import Optional

router = APIRouter()

VALID_TYPES = ("hourly", "daily", "monthly")
TYPE_LABELS = {"hourly": "按小时", "daily": "按天", "monthly": "按月"}


class SalaryTemplateCreate(BaseModel):
    name: str
    type: str  # hourly / daily / monthly
    amount: float
    overtime_half_hour_fee: float = 0
    is_active: bool = True


class SalaryTemplateUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    amount: Optional[float] = None
    overtime_half_hour_fee: Optional[float] = None
    is_active: Optional[bool] = None


def _check_role(current_user: User):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
        raise HTTPException(403, "无权限")


async def _get_usage_count(db: AsyncSession, template_id: int) -> int:
    return int((await db.execute(
        select(func.count(Employee.id)).where(
            Employee.salary_template_id == template_id,
            Employee.is_deleted == False,
        )
    )).scalar() or 0)


@router.get("")
async def list_salary_templates(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _check_role(current_user)
    wh_id = get_wh_id(current_user)
    if not wh_id:
        return {"data": []}

    rows = (await db.execute(
        select(SalaryTemplate).where(SalaryTemplate.warehouse_id == wh_id).order_by(SalaryTemplate.created_at.asc(), SalaryTemplate.id.asc())
    )).scalars().all()

    data = []
    for t in rows:
        data.append({
            "id": t.id,
            "name": t.name,
            "type": t.type,
            "type_label": TYPE_LABELS.get(t.type, t.type),
            "amount": t.amount,
            "overtime_half_hour_fee": t.overtime_half_hour_fee or 0,
            "is_active": t.is_active,
            "usage_count": await _get_usage_count(db, t.id),
        })
    return {"data": data}


@router.post("")
async def create_salary_template(
    req: SalaryTemplateCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _check_role(current_user)
    wh_id = get_wh_id(current_user)
    if not wh_id:
        raise HTTPException(400, "请先选择仓库")
    name = (req.name or "").strip()
    if not name:
        raise HTTPException(400, "请填写模板名称")
    if req.type not in VALID_TYPES:
        raise HTTPException(400, "模板类型无效")
    if req.amount is None or req.amount <= 0:
        raise HTTPException(400, "金额必须大于0")

    t = SalaryTemplate(
        warehouse_id=wh_id,
        name=name,
        type=req.type,
        amount=req.amount,
        overtime_half_hour_fee=req.overtime_half_hour_fee or 0,
        is_active=req.is_active if req.is_active is not None else True,
        created_by=current_user.id,
    )
    db.add(t)
    await db.flush()
    return {"id": t.id, "message": "薪资模板创建成功"}


@router.put("/{template_id}")
async def update_salary_template(
    template_id: int,
    req: SalaryTemplateUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _check_role(current_user)
    wh_id = get_wh_id(current_user)
    if not wh_id:
        raise HTTPException(400, "请先选择仓库")
    t = (await db.execute(
        select(SalaryTemplate).where(SalaryTemplate.id == template_id, SalaryTemplate.warehouse_id == wh_id)
    )).scalar_one_or_none()
    if not t:
        raise HTTPException(404, "薪资模板不存在")

    if req.name is not None:
        name = (req.name or "").strip()
        if not name:
            raise HTTPException(400, "请填写模板名称")
        t.name = name
    if req.type is not None:
        if req.type not in VALID_TYPES:
            raise HTTPException(400, "模板类型无效")
        t.type = req.type
    if req.amount is not None:
        if req.amount <= 0:
            raise HTTPException(400, "金额必须大于0")
        t.amount = req.amount
    if req.overtime_half_hour_fee is not None:
        t.overtime_half_hour_fee = req.overtime_half_hour_fee
    if req.is_active is not None:
        t.is_active = req.is_active

    await db.flush()
    return {"message": "薪资模板已更新"}


@router.delete("/{template_id}")
async def delete_salary_template(
    template_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _check_role(current_user)
    wh_id = get_wh_id(current_user)
    if not wh_id:
        raise HTTPException(400, "请先选择仓库")
    t = (await db.execute(
        select(SalaryTemplate).where(SalaryTemplate.id == template_id, SalaryTemplate.warehouse_id == wh_id)
    )).scalar_one_or_none()
    if not t:
        raise HTTPException(404, "薪资模板不存在")

    usage = await _get_usage_count(db, template_id)
    if usage > 0:
        raise HTTPException(400, f"有 {usage} 个员工在使用该模板，不能删除")

    await db.delete(t)
    await db.flush()
    return {"message": "薪资模板已删除"}

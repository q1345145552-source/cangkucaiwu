from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.models.salary_template import SalaryTemplate
from app.models.employee import Employee
from app.models.user import User
from app.core.permissions import check_staff_permission, check_staff_permission_any, get_wh_id, get_wh_ids, Role
from pydantic import BaseModel, StrictInt
from math import isfinite
from typing import Optional

from app.core.menu_registry import MENU_PERMISSIONS_BY_KEY

_PERMISSION = MENU_PERMISSIONS_BY_KEY["salary_templates"].label

router = APIRouter()

VALID_TYPES = ("hourly", "daily", "monthly")
TYPE_LABELS = {"hourly": "按小时", "daily": "按天", "monthly": "按月"}


class MonthlyTemplateFields(BaseModel):
    monthly_deduction_mode: Optional[str] = None
    monthly_fixed_days: Optional[StrictInt] = None
    monthly_rest_days: Optional[StrictInt] = None
    monthly_rest_pattern: Optional[str] = None
    monthly_rest_weekdays: Optional[list[StrictInt]] = None
    monthly_rest_monthdays: Optional[list[StrictInt]] = None
    monthly_overtime_hour_fee: Optional[float] = None


MONTHLY_FIELDS = tuple(MonthlyTemplateFields.model_fields)
REST_FIELDS = tuple(field for field in MONTHLY_FIELDS if field.startswith("monthly_rest_"))


def _monthly_values(template):
    return {field: getattr(template, field) for field in MONTHLY_FIELDS}


def _validate_monthly(values):
    mode = values["monthly_deduction_mode"]
    if mode not in (None, "fixed", "actual"):
        raise HTTPException(400, "扣款天数模式只能选择固定天数或实际天数")
    fixed = values["monthly_fixed_days"]
    if mode == "fixed" and (fixed is None or fixed <= 0):
        raise HTTPException(400, "固定天数模式请填写大于0的整数天数")
    rest = values["monthly_rest_days"]
    if rest is not None and not 0 <= rest <= 4:
        raise HTTPException(400, "每月固定休息天数必须为0到4的整数")
    pattern = values["monthly_rest_pattern"]
    if pattern not in (None, "weekly", "monthly"):
        raise HTTPException(400, "请选择每周几休或每月几号休")
    for field, low, high, label in (("monthly_rest_weekdays", 0, 6, "每周休息日"),
                                    ("monthly_rest_monthdays", 1, 31, "每月休息日期")):
        days = values[field]
        if days is not None and (len(days) != len(set(days)) or any(day < low or day > high for day in days)):
            raise HTTPException(400, f"{label}选择无效或重复")
    selected = values["monthly_rest_weekdays"] if pattern == "weekly" else values["monthly_rest_monthdays"] if pattern == "monthly" else None
    if rest is not None and rest > 0 and not selected:
        raise HTTPException(400, "填写每月休息天数后，请选择休息规律及具体休息日期")
    overtime = values["monthly_overtime_hour_fee"]
    if overtime is not None and (not isfinite(overtime) or overtime < 0):
        raise HTTPException(400, "每小时加班费不能为负数，请填写有效金额")


class SalaryTemplateCreate(MonthlyTemplateFields):
    model_config = {"extra": "forbid"}
    name: str
    type: str  # hourly / daily / monthly
    amount: float
    overtime_half_hour_fee: float = 0
    is_active: bool = True


class SalaryTemplateUpdate(MonthlyTemplateFields):
    model_config = {"extra": "forbid"}
    name: Optional[str] = None
    type: Optional[str] = None
    amount: Optional[float] = None
    overtime_half_hour_fee: Optional[float] = None
    is_active: Optional[bool] = None


def _check_role(current_user: User):
    if current_user.role not in (Role.SUPER_ADMIN, Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF):
        raise HTTPException(403, "无权限")


async def _get_usage_count(db: AsyncSession, template_id: int) -> int:
    return int((await db.execute(
        select(func.count(Employee.id)).where(
            Employee.salary_template_id == template_id,
            Employee.is_deleted == False,
            Employee.status != "resigned",
        )
    )).scalar() or 0)


@router.get("")
async def list_salary_templates(
    current_user: User = Depends(check_staff_permission_any(
        MENU_PERMISSIONS_BY_KEY["salary_templates"].label,
        MENU_PERMISSIONS_BY_KEY["employees"].label,
    )),
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
            **_monthly_values(t),
        })
    return {"data": data}


@router.post("")
async def create_salary_template(
    req: SalaryTemplateCreate,
    current_user: User = Depends(check_staff_permission(_PERMISSION)),
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

    fields = MONTHLY_FIELDS if req.type == "monthly" else REST_FIELDS
    monthly_values = {field: getattr(req, field) for field in fields}
    if monthly_values:
        _validate_monthly({**dict.fromkeys(MONTHLY_FIELDS), **monthly_values})
    t = SalaryTemplate(
        warehouse_id=wh_id,
        name=name,
        type=req.type,
        amount=req.amount,
        overtime_half_hour_fee=req.overtime_half_hour_fee or 0,
        is_active=req.is_active if req.is_active is not None else True,
        created_by=current_user.id,
        **monthly_values,
    )
    db.add(t)
    await db.flush()
    result = {"id": t.id, "message": "薪资模板创建成功"}
    if t.type == "monthly":
        result["data"] = {"id": t.id, "name": t.name, "type": t.type, "amount": t.amount, **_monthly_values(t)}
    return result


@router.put("/{template_id}")
async def update_salary_template(
    template_id: int,
    req: SalaryTemplateUpdate,
    current_user: User = Depends(check_staff_permission(_PERMISSION)),
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

    monthly_values = _monthly_values(t)
    fields = MONTHLY_FIELDS if (req.type or t.type) == "monthly" else REST_FIELDS
    monthly_values.update({field: getattr(req, field) for field in fields if field in req.model_fields_set})
    _validate_monthly({**dict.fromkeys(MONTHLY_FIELDS), **{field: monthly_values[field] for field in fields}})

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

    for field in fields:
        setattr(t, field, monthly_values[field])

    await db.flush()
    result = {"message": "薪资模板已更新"}
    if t.type == "monthly":
        result["data"] = {"id": t.id, "name": t.name, "type": t.type, "amount": t.amount, **_monthly_values(t)}
    return result


@router.delete("/{template_id}")
async def delete_salary_template(
    template_id: int,
    current_user: User = Depends(check_staff_permission(_PERMISSION)),
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

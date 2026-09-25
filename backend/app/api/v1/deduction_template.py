from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.models.deduction_template import DeductionTemplate
from app.models.employee import Employee
from app.models.user import User
from app.core.permissions import get_current_user, get_wh_id, Role
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

router = APIRouter()


class DeductionTemplateCreate(BaseModel):
    name: str
    late_half_multiplier: float = 0.5
    late_one_multiplier: float = 1.0
    late_half_threshold: str = "09:05"  # 迟到半小时红线
    late_one_threshold: str = "09:31"   # 迟到1小时红线
    early_half_multiplier: float = 0.5
    early_one_multiplier: float = 1.0
    early_half_threshold: str = "17:30"  # 早退半小时红线
    early_one_threshold: str = "17:00"   # 早退1小时红线
    absence_extra_multiplier: float = 0.5
    is_active: bool = True


class DeductionTemplateUpdate(BaseModel):
    name: Optional[str] = None
    late_half_multiplier: Optional[float] = None
    late_one_multiplier: Optional[float] = None
    late_half_threshold: Optional[str] = None
    late_one_threshold: Optional[str] = None
    early_half_multiplier: Optional[float] = None
    early_one_multiplier: Optional[float] = None
    early_half_threshold: Optional[str] = None
    early_one_threshold: Optional[str] = None
    absence_extra_multiplier: Optional[float] = None
    is_active: Optional[bool] = None


def _parse_hhmm(s: str):
    try:
        return datetime.strptime(s, "%H:%M").time()
    except (ValueError, TypeError):
        return None


def _validate_thresholds(early_half: str, early_one: str):
    ht = _parse_hhmm(early_half)
    ot = _parse_hhmm(early_one)
    if ht is None or ot is None:
        raise HTTPException(400, "早退红线时间格式错误，应为 HH:MM")
    if ot >= ht:
        raise HTTPException(400, "早退1小时红线要早于早退半小时红线")


def _validate_late_thresholds(late_half: str, late_one: str):
    ht = _parse_hhmm(late_half)
    ot = _parse_hhmm(late_one)
    if ht is None or ot is None:
        raise HTTPException(400, "迟到红线时间格式错误，应为 HH:MM")
    if ht >= ot:
        raise HTTPException(400, "迟到半小时红线要早于迟到1小时红线")


def _check_role(current_user: User):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
        raise HTTPException(403, "无权限")


async def _get_usage_count(db: AsyncSession, template_id: int) -> int:
    return int((await db.execute(
        select(func.count(Employee.id)).where(
            Employee.deduction_template_id == template_id,
            Employee.is_deleted == False,
        )
    )).scalar() or 0)


@router.get("")
async def list_deduction_templates(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _check_role(current_user)
    wh_id = get_wh_id(current_user)
    if not wh_id:
        return {"data": []}

    rows = (await db.execute(
        select(DeductionTemplate).where(DeductionTemplate.warehouse_id == wh_id)
        .order_by(DeductionTemplate.created_at.asc(), DeductionTemplate.id.asc())
    )).scalars().all()

    data = []
    for t in rows:
        data.append({
            "id": t.id,
            "name": t.name,
            "late_half_multiplier": t.late_half_multiplier if t.late_half_multiplier is not None else 0.5,
            "late_one_multiplier": t.late_one_multiplier if t.late_one_multiplier is not None else 1.0,
            "late_half_threshold": t.late_half_threshold or "09:05",
            "late_one_threshold": t.late_one_threshold or "09:31",
            "early_half_multiplier": t.early_half_multiplier if t.early_half_multiplier is not None else 0.5,
            "early_one_multiplier": t.early_one_multiplier if t.early_one_multiplier is not None else 1.0,
            "early_half_threshold": t.early_half_threshold or "17:30",
            "early_one_threshold": t.early_one_threshold or "17:00",
            "absence_extra_multiplier": t.absence_extra_multiplier if t.absence_extra_multiplier is not None else 0.5,
            "is_active": t.is_active,
            "usage_count": await _get_usage_count(db, t.id),
        })
    return {"data": data}


@router.post("")
async def create_deduction_template(
    req: DeductionTemplateCreate,
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
    _validate_thresholds(req.early_half_threshold, req.early_one_threshold)
    _validate_late_thresholds(req.late_half_threshold, req.late_one_threshold)

    t = DeductionTemplate(
        warehouse_id=wh_id,
        name=name,
        late_half_multiplier=req.late_half_multiplier,
        late_one_multiplier=req.late_one_multiplier,
        late_half_threshold=req.late_half_threshold,
        late_one_threshold=req.late_one_threshold,
        early_half_multiplier=req.early_half_multiplier,
        early_one_multiplier=req.early_one_multiplier,
        early_half_threshold=req.early_half_threshold,
        early_one_threshold=req.early_one_threshold,
        absence_extra_multiplier=req.absence_extra_multiplier,
        is_active=req.is_active if req.is_active is not None else True,
        created_by=current_user.id,
    )
    db.add(t)
    await db.flush()
    return {"id": t.id, "message": "扣款模板创建成功"}


@router.put("/{template_id}")
async def update_deduction_template(
    template_id: int,
    req: DeductionTemplateUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _check_role(current_user)
    wh_id = get_wh_id(current_user)
    if not wh_id:
        raise HTTPException(400, "请先选择仓库")
    t = (await db.execute(
        select(DeductionTemplate).where(DeductionTemplate.id == template_id, DeductionTemplate.warehouse_id == wh_id)
    )).scalar_one_or_none()
    if not t:
        raise HTTPException(404, "扣款模板不存在")

    if req.name is not None:
        name = (req.name or "").strip()
        if not name:
            raise HTTPException(400, "请填写模板名称")
        t.name = name
    for f in ("late_half_multiplier", "late_one_multiplier", "early_half_multiplier", "early_one_multiplier", "absence_extra_multiplier"):
        v = getattr(req, f)
        if v is not None:
            setattr(t, f, v)
    if req.early_half_threshold is not None:
        t.early_half_threshold = req.early_half_threshold
    if req.early_one_threshold is not None:
        t.early_one_threshold = req.early_one_threshold
    if req.late_half_threshold is not None:
        t.late_half_threshold = req.late_half_threshold
    if req.late_one_threshold is not None:
        t.late_one_threshold = req.late_one_threshold
    _validate_thresholds(t.early_half_threshold or "17:30", t.early_one_threshold or "17:00")
    _validate_late_thresholds(t.late_half_threshold or "09:05", t.late_one_threshold or "09:31")
    if req.is_active is not None:
        t.is_active = req.is_active

    await db.flush()
    return {"message": "扣款模板已更新"}


@router.delete("/{template_id}")
async def delete_deduction_template(
    template_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _check_role(current_user)
    wh_id = get_wh_id(current_user)
    if not wh_id:
        raise HTTPException(400, "请先选择仓库")
    t = (await db.execute(
        select(DeductionTemplate).where(DeductionTemplate.id == template_id, DeductionTemplate.warehouse_id == wh_id)
    )).scalar_one_or_none()
    if not t:
        raise HTTPException(404, "扣款模板不存在")

    usage = await _get_usage_count(db, template_id)
    if usage > 0:
        raise HTTPException(400, f"有 {usage} 个员工在使用该模板，不能删除")

    await db.delete(t)
    await db.flush()
    return {"message": "扣款模板已删除"}

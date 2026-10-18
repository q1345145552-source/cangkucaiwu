"""垫款登记和确认；本轮不提供归还，不写成本、支出或工资。"""
import os
import uuid
from datetime import date
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.menu_registry import MENU_PERMISSIONS_BY_KEY
from app.core.permissions import Role, check_staff_permission, get_current_user, get_wh_id
from app.core.timezone import thai_now
from app.database import get_db
from app.models.cash_advance import CashAdvance, PURPOSE_LABELS, STATUS_LABELS
from app.models.user import User
from app.models.user_warehouse import UserWarehouse
from app.services.data_history import record_history

router = APIRouter()
UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "/app/uploads")
PERMISSION = MENU_PERMISSIONS_BY_KEY["cash_advances"].label


async def _reader(user=Depends(check_staff_permission(PERMISSION))):
    if user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF):
        raise HTTPException(403, "无此操作权限")
    return user


async def _creator(user=Depends(get_current_user)):
    if user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
        raise HTTPException(403, "只有仓库管理员和主管可以新建垫款单")
    await check_staff_permission(PERMISSION)(user)
    return user


async def _reviewer(user=Depends(get_current_user)):
    if user.role != Role.WAREHOUSE_ADMIN:
        raise HTTPException(403, "只有仓库管理员可以确认或驳回垫款单")
    return user


def _warehouse(user):
    if getattr(user, "_all_warehouses", False):
        raise HTTPException(400, "请先选择一个仓库")
    wid = get_wh_id(user)
    if wid is None:
        raise HTTPException(400, "请先选择一个仓库")
    return wid


def _user_in_warehouse(wid):
    return or_(User.warehouse_id == wid, exists(select(UserWarehouse.user_id).where(
        UserWarehouse.user_id == User.id, UserWarehouse.warehouse_id == wid,
    )))


class CashAdvanceCreate(BaseModel):
    payer_id: int | None = Field(default=None, gt=0)
    payer_name: str | None = Field(default=None, max_length=100)
    advance_date: date
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2, allow_inf_nan=False)
    purpose: Literal["salary", "purchase", "expense", "other"]
    description: str | None = Field(default=None, max_length=2000)
    voucher_path: str | None = Field(default=None, max_length=500)

    @field_validator("payer_name", "description", "voucher_path")
    @classmethod
    def trim(cls, value):
        return value.strip() or None if value is not None else None


class RejectRequest(BaseModel):
    reject_reason: str | None = Field(default=None, max_length=500)


def _serialize(row):
    outstanding = max(Decimal("0"), row.amount - row.repaid_amount) if row.status == "confirmed" else Decimal("0")
    return {
        "id": row.id, "warehouse_id": row.warehouse_id,
        "payer_id": row.payer_id, "payer_name": row.payer_name,
        "advance_date": row.advance_date.isoformat(), "amount": float(row.amount),
        "purpose": row.purpose, "purpose_label": PURPOSE_LABELS[row.purpose],
        "description": row.description, "voucher_path": row.voucher_path,
        "status": row.status, "status_label": STATUS_LABELS[row.status],
        "repaid_amount": float(row.repaid_amount), "outstanding_amount": float(outstanding),
        "created_by_id": row.created_by_id, "created_by_name": row.created_by_name,
        "created_at": row.created_at.isoformat(),
        "reviewed_by_id": row.reviewed_by_id, "reviewed_by_name": row.reviewed_by_name,
        "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
        "reject_reason": row.reject_reason,
    }


@router.get("/payers")
async def list_payers(user=Depends(_reader), db: AsyncSession = Depends(get_db)):
    accounts = (await db.execute(select(User).where(
        _user_in_warehouse(_warehouse(user)), User.is_active.is_(True), User.role != Role.SUPER_ADMIN,
    ).order_by(User.display_name, User.id))).scalars().all()
    return {"data": [{"id": u.id, "name": u.display_name, "username": u.username, "role": u.role} for u in accounts]}


@router.get("/summary")
async def summary(user=Depends(_reader), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(CashAdvance).where(
        CashAdvance.warehouse_id == _warehouse(user), CashAdvance.status == "confirmed",
        CashAdvance.amount > CashAdvance.repaid_amount,
    ).order_by(CashAdvance.id))).scalars().all()
    groups = {}
    for row in rows:
        key = ("user", row.payer_id) if row.payer_id is not None else ("name", row.payer_name)
        group = groups.setdefault(key, {"payer_id": row.payer_id, "payer_name": row.payer_name, "total": Decimal("0")})
        group["total"] += row.amount - row.repaid_amount
    return {"payer_count": len(groups), "total_outstanding": float(sum((g["total"] for g in groups.values()), Decimal("0"))),
            "data": [{"payer_id": g["payer_id"], "payer_name": g["payer_name"], "outstanding_amount": float(g["total"])} for g in groups.values()]}


@router.get("")
async def list_advances(
    start_date: date | None = None, end_date: date | None = None,
    status: Literal["pending", "confirmed", "rejected", "repaid"] | None = None,
    payer_id: int | None = None, payer_name: str | None = Query(default=None, max_length=100),
    page: int = Query(default=1, ge=1), page_size: int = Query(default=20, ge=1, le=200),
    user=Depends(_reader), db: AsyncSession = Depends(get_db),
):
    if start_date and end_date and start_date > end_date:
        raise HTTPException(400, "开始日期不能晚于结束日期")
    filters = [CashAdvance.warehouse_id == _warehouse(user)]
    if start_date: filters.append(CashAdvance.advance_date >= start_date)
    if end_date: filters.append(CashAdvance.advance_date <= end_date)
    if status: filters.append(CashAdvance.status == status)
    if payer_id is not None: filters.append(CashAdvance.payer_id == payer_id)
    if payer_name and payer_name.strip(): filters.append(CashAdvance.payer_name.contains(payer_name.strip(), autoescape=True))
    total = (await db.execute(select(func.count()).select_from(CashAdvance).where(*filters))).scalar_one()
    rows = (await db.execute(select(CashAdvance).where(*filters).order_by(
        CashAdvance.advance_date.desc(), CashAdvance.id.desc(),
    ).offset((page - 1) * page_size).limit(page_size))).scalars().all()
    return {"data": [_serialize(r) for r in rows], "total": total, "page": page, "page_size": page_size}


@router.post("/voucher")
async def upload_voucher(file: UploadFile = File(...), user=Depends(_creator)):
    from app.services.image_utils import is_image, save_image
    wid = _warehouse(user)
    content = await file.read(10 * 1024 * 1024 + 1)
    if not content or len(content) > 10 * 1024 * 1024:
        raise HTTPException(400, "凭证照片大小须在10MB以内")
    ext = (file.filename or "").rsplit(".", 1)[-1].lower()
    if ext not in ("png", "jpg", "jpeg", "webp") or not is_image(content):
        raise HTTPException(400, "请上传 png/jpg/jpeg/webp 凭证照片")
    subdir = f"{wid}/{thai_now():%Y-%m-%d}/cash-advances"
    result = save_image(content, os.path.join(UPLOAD_DIR, subdir), f"uploads/{subdir}", f"{uuid.uuid4().hex}.{ext}")
    return {"path": result["path"], "thumb_path": result["thumb_path"]}


@router.post("")
async def create_advance(req: CashAdvanceCreate, user=Depends(_creator), db: AsyncSession = Depends(get_db)):
    wid = _warehouse(user)
    payer_id, payer_name = req.payer_id, req.payer_name
    if payer_id is not None:
        payer = (await db.execute(select(User).where(User.id == payer_id, _user_in_warehouse(wid),
            User.is_active.is_(True), User.role != Role.SUPER_ADMIN))).scalar_one_or_none()
        if payer is None: raise HTTPException(400, "垫款账号不存在、已停用或不属于当前仓库")
        payer_name = payer.display_name
    elif not payer_name:
        payer_id, payer_name = user.id, user.display_name
    if req.voucher_path:
        parts = req.voucher_path.split("/")
        if len(parts) != 5 or parts[:2] != ["uploads", str(wid)] or parts[3] != "cash-advances" or any(p in ("", ".", "..") or "\\" in p for p in parts):
            raise HTTPException(400, "凭证照片不属于当前仓库的垫款单")
    row = CashAdvance(warehouse_id=wid, payer_id=payer_id, payer_name=payer_name,
        advance_date=req.advance_date, amount=req.amount, purpose=req.purpose,
        description=req.description, voucher_path=req.voucher_path, status="pending", repaid_amount=0,
        created_by_id=user.id, created_by_name=user.display_name, created_at=thai_now())
    db.add(row)
    await db.flush()
    result = _serialize(row)
    await record_history(db, module="cash_advances", record_id=row.id, operator=user,
        operation_type="create", after=result, warehouse_id=wid)
    return result


async def _review(advance_id, reason, user, db):
    row = (await db.execute(select(CashAdvance).where(
        CashAdvance.id == advance_id, CashAdvance.warehouse_id == _warehouse(user),
    ).with_for_update())).scalar_one_or_none()
    if row is None: raise HTTPException(404, "垫款单不存在或不属于当前仓库")
    if row.status != "pending":
        raise HTTPException(400, f"该垫款单{STATUS_LABELS[row.status]}，不能重复确认或驳回")
    before = _serialize(row)
    row.status = "rejected" if reason is not None else "confirmed"
    row.reject_reason = reason
    row.reviewed_by_id, row.reviewed_by_name, row.reviewed_at = user.id, user.display_name, thai_now()
    await db.flush()
    result = _serialize(row)
    await record_history(db, module="cash_advances", record_id=row.id, operator=user,
        operation_type="reject" if reason is not None else "confirm", before=before, after=result, warehouse_id=row.warehouse_id)
    return result


@router.post("/{advance_id}/confirm")
async def confirm_advance(advance_id: int, user=Depends(_reviewer), db: AsyncSession = Depends(get_db)):
    return await _review(advance_id, None, user, db)


@router.post("/{advance_id}/reject")
async def reject_advance(advance_id: int, req: RejectRequest | None = None, user=Depends(_reviewer), db: AsyncSession = Depends(get_db)):
    reason = ((req.reject_reason if req else None) or "").strip()
    if not reason: raise HTTPException(400, "请填写驳回原因")
    return await _review(advance_id, reason, user, db)

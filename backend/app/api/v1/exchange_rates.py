from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func
from datetime import datetime
from app.database import get_db
from app.models.recharge import ExchangeRate
from app.models.user import User
from app.core.permissions import get_current_user, Role
from app.schemas.business import ExchangeRateCreate

router = APIRouter()

def get_wh_id(user: User) -> int:
    return user.warehouse_id if user.warehouse_id else 1


@router.get("/rates")
async def list_rates(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """列出当前仓库的汇率变更记录（最新在前）"""
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    wh_id = current_user.warehouse_id

    query = select(ExchangeRate).where(ExchangeRate.warehouse_id == wh_id).order_by(desc(ExchangeRate.effective_from)).limit(50)
    result = await db.execute(query)
    records = result.scalars().all()

    # Get setter names
    setter_ids = {r.set_by for r in records if r.set_by}
    setter_map = {}
    if setter_ids:
        setter_rows = (await db.execute(select(User).where(User.id.in_(setter_ids)))).scalars().all()
        setter_map = {u.id: u.display_name for u in setter_rows}

    return {"data": [{
        "id": r.id,
        "warehouse_id": r.warehouse_id,
        "effective_from": r.effective_from.isoformat() if r.effective_from else None,
        "from_currency": r.from_currency,
        "to_currency": r.to_currency,
        "rate": r.rate,
        "set_by_name": setter_map.get(r.set_by, ""),
        "created_at": r.created_at.isoformat() if r.created_at else None,
    } for r in records]}


@router.post("/rates")
async def create_rate(
    req: ExchangeRateCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """新增一条汇率记录。每次都新增，不覆盖旧记录。"""
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if current_user.role not in (Role.SUPER_ADMIN, Role.WAREHOUSE_ADMIN):
        raise HTTPException(403, "无权限")

    effective_from = datetime.fromisoformat(req.effective_from) if req.effective_from else datetime.utcnow()

    r = ExchangeRate(
        warehouse_id=current_user.warehouse_id,
        effective_from=effective_from,
        from_currency=req.from_currency,
        to_currency=req.to_currency,
        rate=req.rate,
        set_by=current_user.id,
    )
    db.add(r)
    await db.flush()
    return {"id": r.id, "message": "汇率设定成功"}


@router.get("/rates/query")
async def query_rate(
    at_time: str = None,
    from_currency: str = "CNY",
    to_currency: str = "THB",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """查询某个时间点的有效汇率。不传 at_time 则返回最新汇率。"""
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    wh_id = current_user.warehouse_id

    target_time = datetime.fromisoformat(at_time) if at_time else datetime.utcnow()

    # 找到 <= target_time 且币种匹配的最新一条记录
    query = (
        select(ExchangeRate)
        .where(
            ExchangeRate.warehouse_id == wh_id,
            ExchangeRate.from_currency == from_currency,
            ExchangeRate.to_currency == to_currency,
            ExchangeRate.effective_from <= target_time,
        )
        .order_by(desc(ExchangeRate.effective_from))
        .limit(1)
    )
    result = await db.execute(query)
    rate = result.scalar_one_or_none()

    if not rate:
        # Fallback: return the closest rate without time constraint
        fallback = await db.execute(
            select(ExchangeRate)
            .where(
                ExchangeRate.warehouse_id == wh_id,
                ExchangeRate.from_currency == from_currency,
                ExchangeRate.to_currency == to_currency,
            )
            .order_by(desc(ExchangeRate.effective_from))
            .limit(1)
        )
        rate = fallback.scalar_one_or_none()

    if not rate:
        raise HTTPException(404, f"未找到 {from_currency} → {to_currency} 的汇率记录")

    return {
        "rate": rate.rate,
        "from_currency": rate.from_currency,
        "to_currency": rate.to_currency,
        "effective_from": rate.effective_from.isoformat() if rate.effective_from else None,
    }

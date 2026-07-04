from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.models.recharge import RechargeDeclaration, MatchStatus
from app.models.recharge import IncomingFlow
from app.models.market import MarketItem
from app.models.group_order import GroupOrder, GroupOrderStatus
from app.models.warehouse import Warehouse
from app.models.user import User
from app.core.permissions import get_current_user, Role

router = APIRouter()

@router.get("/stats")
async def dashboard_stats(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    wh_filter = lambda q: q
    if current_user.role != Role.SUPER_ADMIN:
        wh_filter = lambda q: q.where(q.column_val == current_user.warehouse_id)

    # Total recharge this month
    rq = select(func.coalesce(func.sum(RechargeDeclaration.amount), 0)).where(
        func.to_char(RechargeDeclaration.declare_date, 'YYYY-MM') == func.to_char(func.now(), 'YYYY-MM')
    )
    if current_user.role != Role.SUPER_ADMIN:
        rq = rq.where(RechargeDeclaration.warehouse_id == current_user.warehouse_id)
    total_recharge = (await db.execute(rq)).scalar() or 0

    # Total incoming this month
    iq = select(func.coalesce(func.sum(IncomingFlow.amount), 0)).where(
        func.to_char(IncomingFlow.received_date, 'YYYY-MM') == func.to_char(func.now(), 'YYYY-MM')
    )
    if current_user.role != Role.SUPER_ADMIN:
        iq = iq.where(IncomingFlow.warehouse_id == current_user.warehouse_id)
    total_incoming = (await db.execute(iq)).scalar() or 0

    # Unmatched recharges
    uq = select(func.count(RechargeDeclaration.id)).where(RechargeDeclaration.match_status == 'unmatched')
    if current_user.role != Role.SUPER_ADMIN:
        uq = uq.where(RechargeDeclaration.warehouse_id == current_user.warehouse_id)
    unmatched = (await db.execute(uq)).scalar() or 0

    # Pending market items
    mq = select(func.count(MarketItem.id)).where(MarketItem.status == 'pending')
    if current_user.role != Role.SUPER_ADMIN:
        mq = mq.where(MarketItem.warehouse_id == current_user.warehouse_id)
    pending_market = (await db.execute(mq)).scalar() or 0

    # Pending group orders
    gq = select(func.count(GroupOrder.id)).where(GroupOrder.status == 'open')
    pending_group = (await db.execute(gq)).scalar() or 0

    return {
        "total_recharge_month": float(total_recharge),
        "total_incoming_month": float(total_incoming),
        "unmatched_count": unmatched,
        "pending_market_review": pending_market,
        "pending_group_orders": pending_group,
    }

@router.get("/warehouse-summary")
async def warehouse_summary(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if current_user.role != Role.SUPER_ADMIN:
        wh = current_user.warehouse
        if not wh:
            return {"data": []}
        rq = (await db.execute(select(func.sum(RechargeDeclaration.amount)).where(RechargeDeclaration.warehouse_id == wh.id))).scalar() or 0
        iq = (await db.execute(select(func.sum(IncomingFlow.amount)).where(IncomingFlow.warehouse_id == wh.id))).scalar() or 0
        uq = (await db.execute(select(func.count(RechargeDeclaration.id)).where(
            RechargeDeclaration.warehouse_id == wh.id, RechargeDeclaration.match_status == 'unmatched'))).scalar() or 0
        return {"data": [{"warehouse_id": wh.id, "warehouse_name": wh.name, "recharge_total": float(rq), "incoming_total": float(iq), "unmatched_count": uq}]}

    warehouses = (await db.execute(select(Warehouse).where(Warehouse.is_active == True))).scalars().all()
    result = []
    for wh in warehouses:
        rq = (await db.execute(select(func.sum(RechargeDeclaration.amount)).where(RechargeDeclaration.warehouse_id == wh.id))).scalar() or 0
        iq = (await db.execute(select(func.sum(IncomingFlow.amount)).where(IncomingFlow.warehouse_id == wh.id))).scalar() or 0
        uq = (await db.execute(select(func.count(RechargeDeclaration.id)).where(
            RechargeDeclaration.warehouse_id == wh.id, RechargeDeclaration.match_status == 'unmatched'))).scalar() or 0
        result.append({"warehouse_id": wh.id, "warehouse_name": wh.name, "recharge_total": float(rq), "incoming_total": float(iq), "unmatched_count": uq})
    return {"data": result}

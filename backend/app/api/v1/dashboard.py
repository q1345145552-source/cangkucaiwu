from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.models.recharge import RechargeDeclaration, MatchStatus
from app.models.recharge import IncomingFlow
from app.models.market import MarketItem
from app.models.group_order import GroupOrder, GroupOrderStatus
from app.models.expense_fund import ExpenseFundItem, ExpenseFund, ReviewStatus
from app.models.reimbursement import Reimbursement, ReimbStatus
from app.models.warehouse import Warehouse
from app.models.user import User
from app.core.permissions import get_current_user, Role

router = APIRouter()

def _wh_filter(query, model, current_user):
    if current_user.role != Role.SUPER_ADMIN:
        return query.where(model.warehouse_id == current_user.warehouse_id)
    return query

@router.get("/stats")
async def dashboard_stats(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    # Total recharge this month
    rq = select(func.coalesce(func.sum(RechargeDeclaration.amount), 0)).where(
        func.to_char(RechargeDeclaration.declare_date, 'YYYY-MM') == func.to_char(func.now(), 'YYYY-MM')
    )
    rq = _wh_filter(rq, RechargeDeclaration, current_user)
    total_recharge = (await db.execute(rq)).scalar() or 0

    # Total incoming this month
    iq = select(func.coalesce(func.sum(IncomingFlow.amount), 0)).where(
        func.to_char(IncomingFlow.received_date, 'YYYY-MM') == func.to_char(func.now(), 'YYYY-MM')
    )
    iq = _wh_filter(iq, IncomingFlow, current_user)
    total_incoming = (await db.execute(iq)).scalar() or 0

    # Unmatched recharges
    uq = select(func.count(RechargeDeclaration.id)).where(RechargeDeclaration.match_status == 'unmatched')
    uq = _wh_filter(uq, RechargeDeclaration, current_user)
    unmatched = (await db.execute(uq)).scalar() or 0

    # Pending market items
    mq = select(func.count(MarketItem.id)).where(MarketItem.status == 'pending')
    mq = _wh_filter(mq, MarketItem, current_user)
    pending_market = (await db.execute(mq)).scalar() or 0

    # Pending group orders
    gq = select(func.count(GroupOrder.id)).where(GroupOrder.status == 'open')
    pending_group = (await db.execute(gq)).scalar() or 0

    # Pending expense fund item reviews (join through ExpenseFund for warehouse filter)
    efq = select(func.count(ExpenseFundItem.id)).join(
        ExpenseFund, ExpenseFundItem.fund_id == ExpenseFund.id
    ).where(ExpenseFundItem.review_status == ReviewStatus.PENDING.value)
    if current_user.role != Role.SUPER_ADMIN:
        efq = efq.where(ExpenseFund.warehouse_id == current_user.warehouse_id)
    pending_expense_fund = (await db.execute(efq)).scalar() or 0

    # Pending reimbursement approvals
    rbq = select(func.count(Reimbursement.id)).where(Reimbursement.status == ReimbStatus.PENDING.value)
    rbq = _wh_filter(rbq, Reimbursement, current_user)
    pending_reimbursement = (await db.execute(rbq)).scalar() or 0

    return {
        "total_recharge_month": float(total_recharge),
        "total_incoming_month": float(total_incoming),
        "unmatched_count": unmatched,
        "pending_market_review": pending_market,
        "pending_group_orders": pending_group,
        "pending_expense_fund_reviews": pending_expense_fund,
        "pending_reimbursements": pending_reimbursement,
    }

@router.get("/pending-tasks")
async def pending_tasks(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    tasks = []

    # 1. Pending expense fund item reviews
    efq = select(ExpenseFundItem, ExpenseFund, User).join(
        ExpenseFund, ExpenseFundItem.fund_id == ExpenseFund.id
    ).join(
        User, ExpenseFund.employee_id == User.id
    ).where(ExpenseFundItem.review_status == ReviewStatus.PENDING.value)
    if current_user.role != Role.SUPER_ADMIN:
        efq = efq.where(ExpenseFund.warehouse_id == current_user.warehouse_id)
    efq = efq.order_by(ExpenseFundItem.created_at.desc()).limit(20)
    ef_result = (await db.execute(efq)).all()
    for item, fund, emp in ef_result:
        tasks.append({
            "type": "expense_fund",
            "description": f"{emp.display_name} 的备用金开销待审核",
            "link": "/expense-fund",
            "id": item.id,
            "created_at": item.created_at.isoformat() if item.created_at else None,
        })

    # 2. Pending reimbursements
    rbq = select(Reimbursement, User).join(
        User, Reimbursement.employee_id == User.id
    ).where(Reimbursement.status == ReimbStatus.PENDING.value)
    rbq = _wh_filter(rbq, Reimbursement, current_user)
    rbq = rbq.order_by(Reimbursement.created_at.desc()).limit(20)
    rb_result = (await db.execute(rbq)).all()
    for reim, emp in rb_result:
        tasks.append({
            "type": "reimbursement",
            "description": f"{emp.display_name} 的报销单待审批",
            "link": "/reimbursement",
            "id": reim.id,
            "created_at": reim.created_at.isoformat() if reim.created_at else None,
        })

    # 3. Pending market items
    mq = select(MarketItem, User).join(
        User, MarketItem.uploader_id == User.id
    ).where(MarketItem.status == 'pending')
    mq = _wh_filter(mq, MarketItem, current_user)
    mq = mq.order_by(MarketItem.created_at.desc()).limit(20)
    m_result = (await db.execute(mq)).all()
    for item, uploader in m_result:
        tasks.append({
            "type": "market",
            "description": f"{uploader.display_name} 上架的 {item.name} 待审核",
            "link": "/market",
            "id": item.id,
            "created_at": item.created_at.isoformat() if item.created_at else None,
        })

    # Sort all tasks by created_at desc, cap at 20
    tasks.sort(key=lambda t: t["created_at"] or "", reverse=True)
    for t in tasks: del t["created_at"]
    tasks = tasks[:20]

    return {"data": tasks}

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

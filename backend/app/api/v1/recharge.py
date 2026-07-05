from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime
from app.database import get_db
from app.models.recharge import RechargeDeclaration, CurrencyEnum, MatchStatus
from app.models.customer import Customer
from app.models.warehouse import Warehouse
from app.models.user import User
from app.core.permissions import get_current_user, Role
from app.schemas.business import RechargeCreate

router = APIRouter()

@router.get("")
async def list_recharges(
    page: int = 1, page_size: int = 20, month: str = None,
    customer_id: int = None, status: str = None, search: str = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    query = select(RechargeDeclaration); count_q = select(func.count(RechargeDeclaration.id))
    if current_user.role != Role.SUPER_ADMIN:
        query = query.where(RechargeDeclaration.warehouse_id == current_user.warehouse_id)
        count_q = count_q.where(RechargeDeclaration.warehouse_id == current_user.warehouse_id)
    if month:
        query = query.where(func.to_char(RechargeDeclaration.declare_date, 'YYYY-MM') == month)
        count_q = count_q.where(func.to_char(RechargeDeclaration.declare_date, 'YYYY-MM') == month)
    if customer_id:
        query = query.where(RechargeDeclaration.customer_id == customer_id)
        count_q = count_q.where(RechargeDeclaration.customer_id == customer_id)
    if status:
        query = query.where(RechargeDeclaration.match_status == status)
        count_q = count_q.where(RechargeDeclaration.match_status == status)
    total = (await db.execute(count_q)).scalar()
    result = await db.execute(query.order_by(RechargeDeclaration.created_at.desc()).offset((page-1)*page_size).limit(page_size))
    records = result.scalars().all()

    customer_ids = list(set(r.customer_id for r in records if r.customer_id))
    cust_map = {}
    if customer_ids:
        custs = (await db.execute(select(Customer).where(Customer.id.in_(customer_ids)))).scalars().all()
        cust_map = {c.id: c.company_name for c in custs}

    user_ids = list(set(r.declarer_id for r in records if r.declarer_id))
    user_map = {}
    if user_ids:
        users = (await db.execute(select(User).where(User.id.in_(user_ids)))).scalars().all()
        user_map = {u.id: u.display_name for u in users}

    return {"data": [{
        "id": r.id, "warehouse_id": r.warehouse_id, "customer_id": r.customer_id,
        "customer_name": cust_map.get(r.customer_id, ""),
        "declare_date": r.declare_date.isoformat() if r.declare_date else None,
        "amount": r.amount, "currency": r.currency or "THB",
        "payment_method": r.payment_method, "payment_time": r.payment_time.isoformat() if r.payment_time else None,
        "transaction_no": r.transaction_no, "account_tail": r.account_tail,
        "screenshot": r.screenshot, "remark": r.remark,
        "match_status": r.match_status or "unmatched",
        "declarer_name": user_map.get(r.declarer_id, ""),
        "created_at": r.created_at.isoformat() if r.created_at else None,
    } for r in records], "total": total, "page": page, "page_size": page_size}

@router.post("")
async def create_recharge(req: RechargeCreate, current_user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    wh_id = current_user.warehouse_id
    if current_user.role == Role.SUPER_ADMIN:
        cust = (await db.execute(select(Customer).where(Customer.id == req.customer_id))).scalar_one_or_none()
        if not cust: raise HTTPException(400, "客户不存在")
        wh_id = cust.warehouse_id
    if not wh_id: raise HTTPException(400, "无法确定仓库")

    r = RechargeDeclaration(
        warehouse_id=wh_id, customer_id=req.customer_id,
        declare_date=datetime.fromisoformat(req.declare_date),
        amount=req.amount, currency=req.currency,
        payment_method=req.payment_method,
        payment_time=datetime.fromisoformat(req.payment_time) if req.payment_time else None,
        transaction_no=req.transaction_no, account_tail=req.account_tail,
        screenshot=req.screenshot, remark=req.remark,
        declarer_id=current_user.id,
    )
    db.add(r); await db.flush(); return {"id": r.id, "message": "申报成功"}


@router.get("/{recharge_id}")
async def get_recharge(recharge_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(RechargeDeclaration).where(RechargeDeclaration.id == recharge_id))
    r = result.scalar_one_or_none()
    if not r: raise HTTPException(404, "不存在")
    return {"id": r.id, "amount": r.amount, "currency": r.currency, "declare_date": str(r.declare_date), "match_status": r.match_status, "remark": r.remark}

@router.put("/{recharge_id}")
async def edit_recharge(recharge_id: int, req: RechargeCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(RechargeDeclaration).where(RechargeDeclaration.id == recharge_id))
    r = result.scalar_one_or_none()
    if not r: raise HTTPException(404, "不存在")
    r.amount = req.amount; r.currency = req.currency
    r.declare_date = datetime.fromisoformat(req.declare_date)
    r.remark = req.remark; r.payment_method = req.payment_method
    await db.flush(); return {"message": "更新成功"}

@router.delete("/{recharge_id}")
async def delete_recharge(recharge_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(RechargeDeclaration).where(RechargeDeclaration.id == recharge_id))
    r = result.scalar_one_or_none()
    if not r: raise HTTPException(404, "不存在")
    await db.delete(r); await db.flush(); return {"message": "删除成功"}

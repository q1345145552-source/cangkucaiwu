from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime
from app.database import get_db
from app.models.credit import CreditCustomer, CreditRepayment, CreditStatus
from app.models.customer import Customer
from app.models.user import User
from app.core.permissions import get_current_user, Role
from pydantic import BaseModel
from typing import Optional

router = APIRouter()

class CreditCreate(BaseModel):
    customer_id: int; credit_limit: float; repayment_day: int = 15
    remark: Optional[str] = None

class CreditUpdate(BaseModel):
    credit_limit: Optional[float] = None; repayment_day: Optional[int] = None
    status: Optional[str] = None; current_debt: Optional[float] = None
    overdue_days: Optional[int] = None

class RepaymentCreate(BaseModel):
    repayment_date: str; amount: float; remark: Optional[str] = None

def get_wh(user: User) -> int:
    return user.warehouse_id or 1

@router.get("")
async def list_credit_customers(
    page: int = 1, page_size: int = 20,
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    query = select(CreditCustomer); count_q = select(func.count(CreditCustomer.id))
    if current_user.role != Role.SUPER_ADMIN:
        query = query.where(CreditCustomer.warehouse_id == current_user.warehouse_id)
        count_q = count_q.where(CreditCustomer.warehouse_id == current_user.warehouse_id)
    total = (await db.execute(count_q)).scalar()
    result = await db.execute(query.order_by(CreditCustomer.created_at.desc()).offset((page-1)*page_size).limit(page_size))
    records = result.scalars().all()
    cids = {r.customer_id for r in records}
    cmap = {}
    if cids:
        custs = (await db.execute(select(Customer).where(Customer.id.in_(cids)))).scalars().all()
        cmap = {c.id: c.company_name for c in custs}
    return {"data": [{
        "id": r.id, "warehouse_id": r.warehouse_id, "customer_id": r.customer_id,
        "customer_name": cmap.get(r.customer_id, ""),
        "credit_limit": r.credit_limit, "current_debt": r.current_debt,
        "overdue_days": r.overdue_days, "repayment_day": r.repayment_day,
        "status": r.status, "remark": r.remark,
    } for r in records], "total": total, "page": page, "page_size": page_size}

@router.post("")
async def create_credit(req: CreditCreate, current_user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    if current_user.role not in (Role.SUPER_ADMIN, Role.WAREHOUSE_ADMIN):
        raise HTTPException(403, "无权限")
    c = CreditCustomer(
        warehouse_id=get_wh(current_user), customer_id=req.customer_id,
        credit_limit=req.credit_limit, repayment_day=req.repayment_day,
        remark=req.remark, created_by=current_user.id,
    )
    db.add(c); await db.flush(); return {"id": c.id, "message": "账期客户创建成功"}

@router.put("/{credit_id}")
async def update_credit(credit_id: int, req: CreditUpdate,
                        current_user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    if current_user.role != Role.SUPER_ADMIN:
        raise HTTPException(403, "仅超级管理员可设置额度")
    result = await db.execute(select(CreditCustomer).where(CreditCustomer.id == credit_id))
    c = result.scalar_one_or_none()
    if not c: raise HTTPException(404, "记录不存在")
    if req.credit_limit is not None: c.credit_limit = req.credit_limit
    if req.repayment_day is not None: c.repayment_day = req.repayment_day
    if req.status is not None: c.status = req.status
    if req.current_debt is not None: c.current_debt = req.current_debt
    if req.overdue_days is not None: c.overdue_days = req.overdue_days
    await db.flush(); return {"message": "更新成功"}

@router.get("/{credit_id}/detail")
async def credit_detail(credit_id: int, current_user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(CreditCustomer).where(CreditCustomer.id == credit_id))
    c = result.scalar_one_or_none()
    if not c: raise HTTPException(404, "记录不存在")
    cust = (await db.execute(select(Customer).where(Customer.id == c.customer_id))).scalar_one_or_none()
    reps = (await db.execute(select(CreditRepayment).where(CreditRepayment.credit_customer_id == credit_id).order_by(CreditRepayment.created_at.desc()))).scalars().all()
    return {
        "id": c.id, "warehouse_id": c.warehouse_id, "customer_id": c.customer_id,
        "customer_name": cust.company_name if cust else "",
        "credit_limit": c.credit_limit, "current_debt": c.current_debt,
        "overdue_days": c.overdue_days, "repayment_day": c.repayment_day,
        "status": c.status, "remark": c.remark,
        "repayments": [{"id": r.id, "repayment_date": r.repayment_date.isoformat() if r.repayment_date else None,
                        "amount": r.amount, "remark": r.remark,
                        "created_at": r.created_at.isoformat() if r.created_at else None} for r in reps],
    }

@router.post("/{credit_id}/payment")
async def record_repayment(credit_id: int, req: RepaymentCreate,
                           current_user: User = Depends(get_current_user),
                           db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(CreditCustomer).where(CreditCustomer.id == credit_id))
    c = result.scalar_one_or_none()
    if not c: raise HTTPException(404, "记录不存在")
    r = CreditRepayment(
        credit_customer_id=credit_id, repayment_date=datetime.fromisoformat(req.repayment_date),
        amount=req.amount, remark=req.remark, recorded_by=current_user.id,
    )
    db.add(r); await db.flush(); return {"id": r.id, "message": "还款记录创建成功"}

@router.get("/dashboard")
async def credit_dashboard(current_user: User = Depends(get_current_user),
                           db: AsyncSession = Depends(get_db)):
    # 全局统计
    dq = select(func.coalesce(func.sum(CreditCustomer.current_debt), 0), 
                func.coalesce(func.sum(CreditCustomer.credit_limit), 0),
                func.count(CreditCustomer.id))
    if current_user.role != Role.SUPER_ADMIN:
        dq = dq.where(CreditCustomer.warehouse_id == current_user.warehouse_id)
    total_debt, total_limit, total_cust = (await db.execute(dq)).first()
    overdue_q = select(func.count(CreditCustomer.id)).where(
        CreditCustomer.status == CreditStatus.ACTIVE.value,
        CreditCustomer.overdue_days > 0,
    )
    if current_user.role != Role.SUPER_ADMIN:
        overdue_q = overdue_q.where(CreditCustomer.warehouse_id == current_user.warehouse_id)
    overdue_count = (await db.execute(overdue_q)).scalar() or 0
    return {
        "total_debt": float(total_debt or 0), "total_credit_limit": float(total_limit or 0),
        "total_customers": total_cust or 0, "overdue_count": overdue_count,
        "utilization_rate": round(float(total_debt or 0) / float(total_limit or 1) * 100, 1) if total_limit else 0,
    }

@router.get("/alerts")
async def credit_alerts(level: str = None, current_user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    query = select(CreditCustomer).where(
        CreditCustomer.status == CreditStatus.ACTIVE.value,
        CreditCustomer.overdue_days > 0,
    ).order_by(CreditCustomer.overdue_days.desc())
    if current_user.role != Role.SUPER_ADMIN:
        query = query.where(CreditCustomer.warehouse_id == current_user.warehouse_id)
    records = (await db.execute(query)).scalars().all()
    cids = {r.customer_id for r in records}
    cmap = {}
    if cids:
        custs = (await db.execute(select(Customer).where(Customer.id.in_(cids)))).scalars().all()
        cmap = {c.id: c.company_name for c in custs}
    return {"data": [{
        "id": r.id, "customer_name": cmap.get(r.customer_id, ""),
        "current_debt": r.current_debt, "overdue_days": r.overdue_days,
        "credit_limit": r.credit_limit, "status": r.status,
    } for r in records]}

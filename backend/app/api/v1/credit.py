from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime, date
from app.database import get_db
from app.models.credit import CreditCustomer, CreditRepayment, CreditShipment, CreditStatus
from app.models.customer import Customer
from app.models.user import User
from app.core.permissions import get_current_user, Role, check_staff_permission
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

class ShipmentCreate(BaseModel):
    ship_date: str; amount: float; order_no: Optional[str] = None; remark: Optional[str] = None

def get_wh(user: User) -> int:
    return user.warehouse_id or 1

async def _compute_debt_and_overdue(db: AsyncSession, credit_id: int):
    """Calculate current_debt and overdue_days from shipments and repayments."""
    ship_total = (await db.execute(
        select(func.coalesce(func.sum(CreditShipment.amount), 0))
        .where(CreditShipment.credit_customer_id == credit_id)
    )).scalar() or 0

    repay_total = (await db.execute(
        select(func.coalesce(func.sum(CreditRepayment.amount), 0))
        .where(CreditRepayment.credit_customer_id == credit_id)
    )).scalar() or 0

    current_debt = float(ship_total) - float(repay_total)

    # overdue_days: days since last repayment, or since last shipment if no repayment
    last_repay = (await db.execute(
        select(CreditRepayment.repayment_date)
        .where(CreditRepayment.credit_customer_id == credit_id)
        .order_by(CreditRepayment.repayment_date.desc())
    )).scalar()
    last_ship = (await db.execute(
        select(CreditShipment.ship_date)
        .where(CreditShipment.credit_customer_id == credit_id)
        .order_by(CreditShipment.ship_date.desc())
    )).scalar()

    ref_date = last_repay or last_ship
    today = date.today()
    if ref_date:
        if isinstance(ref_date, datetime):
            ref_date = ref_date.date()
        overdue_days = (today - ref_date).days
    else:
        overdue_days = 0

    return current_debt, max(overdue_days, 0)

@router.get("")
async def list_credit_customers(
    page: int = 1, page_size: int = 20,
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
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

    # Compute debt/overdue for each record
    data = []
    for r in records:
        debt, overdue = await _compute_debt_and_overdue(db, r.id)
        data.append({
            "id": r.id, "warehouse_id": r.warehouse_id, "customer_id": r.customer_id,
            "customer_name": cmap.get(r.customer_id, ""),
            "credit_limit": r.credit_limit, "current_debt": debt,
            "overdue_days": overdue, "repayment_day": r.repayment_day,
            "status": r.status, "remark": r.remark,
        })

    return {"data": data, "total": total, "page": page, "page_size": page_size}

@router.post("")
async def create_credit(req: CreditCreate, current_user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
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
    result = await db.execute(select(CreditCustomer).where(CreditCustomer.id == credit_id))
    c = result.scalar_one_or_none()
    if not c: raise HTTPException(404, "记录不存在")
    if current_user.role == Role.SUPER_ADMIN:
        pass
    elif current_user.role == Role.WAREHOUSE_ADMIN:
        if c.warehouse_id != current_user.warehouse_id:
            raise HTTPException(403, "只能修改自己仓库的账期客户")
    else:
        raise HTTPException(403, "无权限")
    if req.credit_limit is not None: c.credit_limit = req.credit_limit
    if req.repayment_day is not None: c.repayment_day = req.repayment_day
    if req.status is not None: c.status = req.status
    if req.current_debt is not None: c.current_debt = req.current_debt
    if req.overdue_days is not None: c.overdue_days = req.overdue_days
    await db.flush(); return {"message": "更新成功"}

@router.get("/{credit_id}/detail")
async def credit_detail(credit_id: int, current_user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    result = await db.execute(select(CreditCustomer).where(CreditCustomer.id == credit_id))
    c = result.scalar_one_or_none()
    if not c: raise HTTPException(404, "记录不存在")
    cust = (await db.execute(select(Customer).where(Customer.id == c.customer_id))).scalar_one_or_none()

    # Get repayments
    reps = (await db.execute(
        select(CreditRepayment).where(CreditRepayment.credit_customer_id == credit_id)
        .order_by(CreditRepayment.created_at.desc())
    )).scalars().all()

    # Get shipments
    ships = (await db.execute(
        select(CreditShipment).where(CreditShipment.credit_customer_id == credit_id)
        .order_by(CreditShipment.ship_date.desc())
    )).scalars().all()

    # Compute debt/overdue
    debt, overdue = await _compute_debt_and_overdue(db, credit_id)

    return {
        "id": c.id, "warehouse_id": c.warehouse_id, "customer_id": c.customer_id,
        "customer_name": cust.company_name if cust else "",
        "credit_limit": c.credit_limit, "current_debt": debt,
        "overdue_days": overdue, "repayment_day": c.repayment_day,
        "status": c.status, "remark": c.remark,
        "repayments": [{"id": r.id, "repayment_date": r.repayment_date.isoformat() if r.repayment_date else None,
                        "amount": r.amount, "remark": r.remark,
                        "created_at": r.created_at.isoformat() if r.created_at else None} for r in reps],
        "shipments": [{"id": s.id, "ship_date": s.ship_date.isoformat() if s.ship_date else None,
                       "order_no": s.order_no, "amount": s.amount, "remark": s.remark,
                       "created_at": s.created_at.isoformat() if s.created_at else None} for s in ships],
    }

@router.post("/{credit_id}/shipment")
async def create_shipment(credit_id: int, req: ShipmentCreate,
                          current_user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if current_user.role not in (Role.WAREHOUSE_ADMIN,) and current_user.role != Role.STAFF:
        raise HTTPException(403, "无权限")
    if current_user.role == Role.STAFF and "账期管理" not in (current_user.extra_permissions or []):
        raise HTTPException(403, "无管理账期权限")
    result = await db.execute(select(CreditCustomer).where(CreditCustomer.id == credit_id))
    c = result.scalar_one_or_none()
    if not c: raise HTTPException(404, "账期客户不存在")

    s = CreditShipment(
        credit_customer_id=credit_id,
        ship_date=datetime.fromisoformat(req.ship_date),
        order_no=req.order_no,
        amount=req.amount,
        remark=req.remark,
        entrant_id=current_user.id,
    )
    db.add(s)
    await db.flush()

    # Recompute and update current_debt / overdue_days
    debt, overdue = await _compute_debt_and_overdue(db, credit_id)
    c.current_debt = debt
    c.overdue_days = overdue
    await db.flush()

    return {"id": s.id, "current_debt": debt, "overdue_days": overdue, "message": "发货记录创建成功"}

@router.post("/{credit_id}/payment")
async def record_repayment(credit_id: int, req: RepaymentCreate,
                           current_user: User = Depends(get_current_user),
                           db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if current_user.role == Role.STAFF and "账期管理" not in (current_user.extra_permissions or []):
        raise HTTPException(403, "无管理账期权限")
    result = await db.execute(select(CreditCustomer).where(CreditCustomer.id == credit_id))
    c = result.scalar_one_or_none()
    if not c: raise HTTPException(404, "记录不存在")
    r = CreditRepayment(
        credit_customer_id=credit_id, repayment_date=datetime.fromisoformat(req.repayment_date),
        amount=req.amount, remark=req.remark, recorded_by=current_user.id,
    )
    db.add(r)

    # Recompute and update current_debt / overdue_days
    debt, overdue = await _compute_debt_and_overdue(db, credit_id)
    c.current_debt = debt
    c.overdue_days = overdue
    await db.flush()

    return {"id": r.id, "current_debt": debt, "overdue_days": overdue, "message": "还款记录创建成功"}

@router.get("/dashboard")
async def credit_dashboard(current_user: User = Depends(get_current_user),
                           db: AsyncSession = Depends(get_db)):
    # 全局统计
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
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
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
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

    data = []
    for r in records:
        debt, overdue = await _compute_debt_and_overdue(db, r.id)
        data.append({
            "id": r.id, "customer_name": cmap.get(r.customer_id, ""),
            "current_debt": debt, "overdue_days": overdue,
            "credit_limit": r.credit_limit, "status": r.status,
        })

    return {"data": data}

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.core.timezone import thai_now, thai_today
from datetime import datetime, date
from app.database import get_db
from app.models.credit import CreditCustomer, CreditRepayment, CreditShipment, CreditStatus
from app.models.customer import Customer
from app.models.user import User
from app.core.permissions import get_current_user, get_wh_id, get_wh_ids, Role, check_staff_permission
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

    # If fully paid (debt <= 0), overdue_days is always 0
    if current_debt <= 0:
        return max(current_debt, 0), 0

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
    today = thai_today()
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
        query = query.where(CreditCustomer.warehouse_id.in_(get_wh_ids(current_user)))
        count_q = count_q.where(CreditCustomer.warehouse_id.in_(get_wh_ids(current_user)))
    total = (await db.execute(count_q)).scalar()
    result = await db.execute(query.order_by(CreditCustomer.created_at.desc()).offset((page-1)*page_size).limit(page_size))
    records = result.scalars().all()
    cids = {r.customer_id for r in records}
    cmap = {}
    if cids:
        custs = (await db.execute(select(Customer).where(Customer.id.in_(cids)))).scalars().all()
        cmap = {c.id: c.company_name for c in custs}

    # Batch compute debt/overdue for all records (avoid N+1)
    all_cids = [r.id for r in records]
    debt_map = {}
    if all_cids:
        # Batch shipments sum
        ship_rows = (await db.execute(
            select(CreditShipment.credit_customer_id, func.coalesce(func.sum(CreditShipment.amount), 0))
            .where(CreditShipment.credit_customer_id.in_(all_cids))
            .group_by(CreditShipment.credit_customer_id)
        )).all()
        ship_totals = {row[0]: float(row[1]) for row in ship_rows}
        # Batch repayments sum
        repay_rows = (await db.execute(
            select(CreditRepayment.credit_customer_id, func.coalesce(func.sum(CreditRepayment.amount), 0))
            .where(CreditRepayment.credit_customer_id.in_(all_cids))
            .group_by(CreditRepayment.credit_customer_id)
        )).all()
        repay_totals = {row[0]: float(row[1]) for row in repay_rows}
        # Batch last repayment date
        last_repay_sub = (
            select(CreditRepayment.credit_customer_id, func.max(CreditRepayment.repayment_date).label("max_date"))
            .where(CreditRepayment.credit_customer_id.in_(all_cids))
            .group_by(CreditRepayment.credit_customer_id)
        ).subquery()
        last_ship_sub = (
            select(CreditShipment.credit_customer_id, func.max(CreditShipment.ship_date).label("max_date"))
            .where(CreditShipment.credit_customer_id.in_(all_cids))
            .group_by(CreditShipment.credit_customer_id)
        ).subquery()
        last_repay_rows = (await db.execute(select(last_repay_sub))).all()
        last_ship_rows = (await db.execute(select(last_ship_sub))).all()
        repay_date_map = {row[0]: row[1] for row in last_repay_rows}
        ship_date_map = {row[0]: row[1] for row in last_ship_rows}
        today = thai_today()
        for cid in all_cids:
            s_total = ship_totals.get(cid, 0)
            r_total = repay_totals.get(cid, 0)
            debt = s_total - r_total
            if debt <= 0:
                debt_map[cid] = (max(debt, 0), 0)
            else:
                ref_date = repay_date_map.get(cid) or ship_date_map.get(cid)
                overdue = 0
                if ref_date:
                    if isinstance(ref_date, datetime):
                        ref_date = ref_date.date()
                    overdue = max((today - ref_date).days, 0)
                debt_map[cid] = (debt, overdue)

    data = []
    for r in records:
        debt, overdue = debt_map.get(r.id, (0, 0))
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
        warehouse_id=get_wh_id(current_user), customer_id=req.customer_id,
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
        if c.warehouse_id not in get_wh_ids(current_user):
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

    # Get assessment for this single customer
    ass_data = await _compute_assessment(current_user, db)
    assessment = next((a for a in ass_data["data"] if a["customer_id"] == c.customer_id), None)

    return {
        "id": c.id, "warehouse_id": c.warehouse_id, "customer_id": c.customer_id,
        "customer_name": cust.company_name if cust else "",
        "credit_limit": c.credit_limit, "current_debt": debt,
        "overdue_days": overdue, "repayment_day": c.repayment_day,
        "status": c.status, "remark": c.remark,
        "rating": assessment["rating"] if assessment else "B",
        "coop_months": assessment["coop_months"] if assessment else 0,
        "on_time_rate": assessment["on_time_rate"] if assessment else 100,
        "overdue_count": assessment["overdue_count"] if assessment else 0,
        "max_overdue_days": assessment["max_overdue_days"] if assessment else 0,
        "avg_monthly_repay": assessment["avg_monthly_repay"] if assessment else 0,
        "utilization_rate": assessment["utilization_rate"] if assessment else 0,
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
    # Get all active credit customers for this warehouse and compute debt in realtime (batch)
    cust_query = select(CreditCustomer)
    if current_user.role != Role.SUPER_ADMIN:
        cust_query = cust_query.where(CreditCustomer.warehouse_id.in_(get_wh_ids(current_user)))
    all_credits = (await db.execute(cust_query)).scalars().all()
    all_cids = [c.id for c in all_credits]
    total_limit = sum(c.credit_limit or 0 for c in all_credits)
    total_cust = len(all_credits)
    # Batch compute debt for all
    total_debt = 0.0
    if all_cids:
        ship_rows = (await db.execute(
            select(CreditShipment.credit_customer_id, func.coalesce(func.sum(CreditShipment.amount), 0))
            .where(CreditShipment.credit_customer_id.in_(all_cids))
            .group_by(CreditShipment.credit_customer_id)
        )).all()
        repay_rows = (await db.execute(
            select(CreditRepayment.credit_customer_id, func.coalesce(func.sum(CreditRepayment.amount), 0))
            .where(CreditRepayment.credit_customer_id.in_(all_cids))
            .group_by(CreditRepayment.credit_customer_id)
        )).all()
        ship_map = {row[0]: float(row[1]) for row in ship_rows}
        repay_map = {row[0]: float(row[1]) for row in repay_rows}
        for c in all_credits:
            debt = ship_map.get(c.id, 0) - repay_map.get(c.id, 0)
            total_debt += max(debt, 0)
    total_debt = float(total_debt)
    overdue_q = select(func.count(CreditCustomer.id)).where(
        CreditCustomer.status == CreditStatus.ACTIVE.value,
        CreditCustomer.overdue_days > 0,
    )
    if current_user.role != Role.SUPER_ADMIN:
        overdue_q = overdue_q.where(CreditCustomer.warehouse_id.in_(get_wh_ids(current_user)))
    overdue_count = (await db.execute(overdue_q)).scalar() or 0

    # Rating distribution
    try:
        assessment_result = await _compute_assessment(current_user, db)
        rating_dist = {"A": 0, "B": 0, "C": 0}
        for item in assessment_result["data"]:
            r = item.get("rating", "B")
            rating_dist[r] = rating_dist.get(r, 0) + 1
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"评级计算失败: {e}")
        rating_dist = {"A": 0, "B": 0, "C": 0}

    return {
        "total_debt": float(total_debt or 0), "total_credit_limit": float(total_limit or 0),
        "total_customers": total_cust or 0, "overdue_count": overdue_count,
        "utilization_rate": round(float(total_debt or 0) / float(total_limit or 1) * 100, 1) if total_limit else 0,
        "rating_dist": rating_dist,
    }


# ==== Assessment & Rating ====
async def _compute_assessment(
    current_user: User, db: AsyncSession,
) -> dict:
    """核心评级计算逻辑，供端点和看板复用"""
    wh_id = get_wh_id(current_user)
    query = select(CreditCustomer).where(CreditCustomer.status == CreditStatus.ACTIVE.value)
    if current_user.role != Role.SUPER_ADMIN:
        query = query.where(CreditCustomer.warehouse_id.in_(get_wh_ids(current_user)))
    records = (await db.execute(query)).scalars().all()

    cids = {r.customer_id for r in records}
    cmap = {}
    if cids:
        custs = (await db.execute(select(Customer).where(Customer.id.in_(cids)))).scalars().all()
        cmap = {c.id: {"name": c.company_name, "created_at": c.created_at} for c in custs}

    today = thai_today()
    data = []
    for r in records:
        cust_info = cmap.get(r.customer_id, {"name": "", "created_at": None})

        coop_months = 0
        if cust_info["created_at"] and hasattr(cust_info["created_at"], 'date'):
            coop_months = max(0, (today - cust_info["created_at"].date()).days // 30)

        reps = (await db.execute(
            select(CreditRepayment).where(CreditRepayment.credit_customer_id == r.id)
            .order_by(CreditRepayment.repayment_date.asc())
        )).scalars().all()

        ships = (await db.execute(
            select(CreditShipment).where(CreditShipment.credit_customer_id == r.id)
            .order_by(CreditShipment.ship_date.asc())
        )).scalars().all()

        total_repayments = len(reps)
        on_time_count = 0
        overdue_count = 0
        max_overdue_days = 0

        for rep in reps:
            rep_date = rep.repayment_date.date() if hasattr(rep.repayment_date, 'date') else rep.repayment_date
            relevant_ship_date = None
            for s in ships:
                sd = s.ship_date.date() if hasattr(s.ship_date, 'date') else s.ship_date
                if sd <= rep_date:
                    relevant_ship_date = sd
            if relevant_ship_date:
                days_since = (rep_date - relevant_ship_date).days
                if days_since <= (r.repayment_day or 15):
                    on_time_count += 1
                else:
                    overdue_count += 1
                    max_overdue_days = max(max_overdue_days, days_since - (r.repayment_day or 15))
            else:
                on_time_count += 1

        on_time_rate = round(on_time_count / total_repayments * 100, 1) if total_repayments > 0 else 100

        three_months_ago = today.replace(day=1)
        if three_months_ago.month > 2:
            three_months_ago = three_months_ago.replace(month=three_months_ago.month - 2)
        else:
            three_months_ago = three_months_ago.replace(year=three_months_ago.year - 1, month=three_months_ago.month + 10)

        recent_reps = [rep for rep in reps if rep.repayment_date and
                       (rep.repayment_date.date() if hasattr(rep.repayment_date, 'date') else rep.repayment_date) >= three_months_ago]
        avg_monthly_repay = round(sum(rp.amount for rp in recent_reps) / 3, 1) if recent_reps else 0

        utilization_rate = round((r.current_debt or 0) / (r.credit_limit or 1) * 100, 1)

        if coop_months >= 6 and overdue_count == 0 and on_time_rate >= 95:
            rating = "A"
        elif coop_months < 3 or overdue_count >= 3 or max_overdue_days > 30:
            rating = "C"
        else:
            rating = "B"

        data.append({
            "id": r.id, "customer_id": r.customer_id,
            "customer_name": cust_info.get("name", ""),
            "rating": rating,
            "credit_limit": r.credit_limit or 0,
            "current_debt": r.current_debt or 0,
            "overdue_days": r.overdue_days or 0,
            "coop_months": coop_months,
            "on_time_rate": on_time_rate,
            "total_repayments": total_repayments,
            "overdue_count": overdue_count,
            "max_overdue_days": max_overdue_days,
            "avg_monthly_repay": avg_monthly_repay,
            "utilization_rate": utilization_rate,
        })

    return {"data": data}


@router.get("/assessment")
async def credit_assessment(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    """返回所有账期客户的评级和评估数据"""
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.STAFF):
        raise HTTPException(403, "无权限")
    return await _compute_assessment(current_user, db)


@router.get("/assessment/export")
async def export_assessment(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    """导出账期客户评估报告"""
    from fastapi.responses import StreamingResponse
    import io, openpyxl

    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.STAFF):
        raise HTTPException(403, "无权限")

    # Reuse assessment logic
    result = await _compute_assessment(current_user, db)
    data = result["data"]

    rating_labels = {"A": "A级-优质客户", "B": "B级-正常客户", "C": "C级-风险客户"}
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "账期客户评估"
    ws.append(["客户名称", "评级", "信用额度", "当前欠款", "逾期天数", "还款准时率(%)",
                "逾期次数", "最长逾期(天)", "合作时长(月)", "月均还款", "额度使用率(%)"])

    for d in data:
        ws.append([
            d["customer_name"], rating_labels.get(d["rating"], d["rating"]),
            d["credit_limit"], d["current_debt"], d["overdue_days"],
            d["on_time_rate"], d["overdue_count"], d["max_overdue_days"],
            d["coop_months"], d["avg_monthly_repay"], d["utilization_rate"],
        ])

    output = io.BytesIO()
    wb.save(output); output.seek(0)
    return StreamingResponse(output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=credit_assessment.xlsx"})


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
        query = query.where(CreditCustomer.warehouse_id.in_(get_wh_ids(current_user)))
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

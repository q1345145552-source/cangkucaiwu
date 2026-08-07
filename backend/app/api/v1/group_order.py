from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.models.group_order import GroupOrder, GroupOrderParticipant, GroupOrderStatus
from app.models.warehouse import Warehouse
from app.models.user import User
from app.core.permissions import get_current_user, get_wh_id, get_wh_ids, Role, require_role
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

router = APIRouter()

class GOCreate(BaseModel):
    item_name: str; specification: Optional[str] = None
    target_quantity: int; target_price: float; deadline: str
    reason: Optional[str] = None

class JoinRequest(BaseModel):
    quantity: int; delivery_address: Optional[str] = None
    agreed_rules: bool = True

class CompleteRequest(BaseModel):
    final_price: float; final_supplier: Optional[str] = None
    logistics_fee: Optional[float] = None

class CancelRequest(BaseModel):
    reason: str

STATUS_CN = {"open": "开放中", "closed": "已截止", "completed": "已完成", "cancelled": "已取消"}

async def _get_participant_details(db: AsyncSession, go_id: int):
    """获取拼单的参与仓库明细"""
    ps = (await db.execute(
        select(GroupOrderParticipant).where(GroupOrderParticipant.group_order_id == go_id)
    )).scalars().all()
    wh_map = {}
    wids = {p.warehouse_id for p in ps}
    if wids:
        whs = (await db.execute(select(Warehouse).where(Warehouse.id.in_(wids)))).scalars().all()
        wh_map = {w.id: w.name for w in whs}
    total_qty = sum(p.quantity for p in ps)
    items = [{
        "id": p.id, "warehouse_id": p.warehouse_id,
        "warehouse_name": wh_map.get(p.warehouse_id, ""),
        "quantity": p.quantity, "delivery_address": p.delivery_address or "",
        "created_at": p.created_at.isoformat() if p.created_at else None,
    } for p in ps]
    return items, total_qty, len({p.warehouse_id for p in ps})


@router.get("")
async def list_group_orders(
    page: int = 1, page_size: int = 20, status: str = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """所有开放的拼单对所有仓库可见，浏览阶段不限制"""
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    query = select(GroupOrder); count_q = select(func.count(GroupOrder.id))
    if status:
        query = query.where(GroupOrder.status == status)
        count_q = count_q.where(GroupOrder.status == status)
    else:
        # Default: show open + closed orders
        query = query.where(GroupOrder.status.in_([GroupOrderStatus.OPEN.value, GroupOrderStatus.CLOSED.value]))
        count_q = count_q.where(GroupOrder.status.in_([GroupOrderStatus.OPEN.value, GroupOrderStatus.CLOSED.value]))
    total = (await db.execute(count_q)).scalar()
    result = await db.execute(query.order_by(GroupOrder.created_at.desc()).offset((page-1)*page_size).limit(page_size))
    orders = result.scalars().all()

    go_ids = [o.id for o in orders]
    part_summary: dict = {}
    part_wh_count: dict = {}
    if go_ids:
        # 一次性聚合所有拼单的参与数量与参与仓库数（避免逐单 N+1 查询）
        rows = (await db.execute(
            select(
                GroupOrderParticipant.group_order_id,
                func.coalesce(func.sum(GroupOrderParticipant.quantity), 0),
                func.count(func.distinct(GroupOrderParticipant.warehouse_id)),
            )
            .where(GroupOrderParticipant.group_order_id.in_(go_ids))
            .group_by(GroupOrderParticipant.group_order_id)
        )).all()
        for gid, qty, wh_cnt in rows:
            part_summary[gid] = qty or 0
            part_wh_count[gid] = wh_cnt or 0

    wh_map = {}
    wids = {o.warehouse_id for o in orders}
    if wids:
        whs = (await db.execute(select(Warehouse).where(Warehouse.id.in_(wids)))).scalars().all()
        wh_map = {w.id: w.name for w in whs}

    return {"data": [{
        "id": o.id, "warehouse_id": o.warehouse_id,
        "warehouse_name": wh_map.get(o.warehouse_id, ""),
        "item_name": o.item_name, "specification": o.specification,
        "target_quantity": o.target_quantity, "target_price": o.target_price,
        "deadline": o.deadline.isoformat() if o.deadline else None,
        "reason": o.reason, "status": o.status, "status_cn": STATUS_CN.get(o.status, o.status),
        "final_price": o.final_price, "final_supplier": o.final_supplier,
        "logistics_fee": o.logistics_fee,
        "current_quantity": part_summary.get(o.id, 0),
        "participant_warehouse_count": part_wh_count.get(o.id, 0),
        "created_at": o.created_at.isoformat() if o.created_at else None,
    } for o in orders], "total": total, "page": page, "page_size": page_size}


@router.post("")
async def create_group_order(req: GOCreate, current_user: User = Depends(get_current_user),
                              db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if current_user.role not in (Role.SUPER_ADMIN, Role.WAREHOUSE_ADMIN):
        raise HTTPException(403, "仅仓库管理员可发起")
    o = GroupOrder(
        warehouse_id=get_wh_id(current_user), item_name=req.item_name,
        specification=req.specification, target_quantity=req.target_quantity,
        target_price=req.target_price, deadline=datetime.fromisoformat(req.deadline),
        reason=req.reason, initiator_id=current_user.id,
    )
    db.add(o); await db.flush(); return {"id": o.id, "message": "拼单发起成功"}


@router.post("/{go_id}/join")
async def join_group_order(go_id: int, req: JoinRequest, current_user: User = Depends(get_current_user),
                            db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    result = await db.execute(select(GroupOrder).where(GroupOrder.id == go_id))
    o = result.scalar_one_or_none()
    if not o: raise HTTPException(404, "拼单不存在")
    if o.status != GroupOrderStatus.OPEN.value:
        raise HTTPException(400, "拼单已截止")
    if not req.agreed_rules:
        raise HTTPException(400, "需同意拼单规则")
    if req.quantity <= 0:
        raise HTTPException(400, "参与数量必须大于0")
    # Check not banned
    banned = (await db.execute(select(GroupOrderParticipant).where(
        GroupOrderParticipant.group_order_id == go_id,
        GroupOrderParticipant.warehouse_id.in_(get_wh_ids(current_user)),
        GroupOrderParticipant.is_banned == True,
    ))).scalars().all()
    if banned:
        raise HTTPException(403, "该仓库已被禁止参与拼单")
    # Check not already joined
    already = (await db.execute(select(GroupOrderParticipant).where(
        GroupOrderParticipant.group_order_id == go_id,
        GroupOrderParticipant.warehouse_id.in_(get_wh_ids(current_user)),
        GroupOrderParticipant.is_banned == False,
    ))).scalar_one_or_none()
    if already:
        raise HTTPException(400, "该仓库已参与此拼单")
    p = GroupOrderParticipant(
        group_order_id=go_id, warehouse_id=get_wh_id(current_user),
        quantity=req.quantity, delivery_address=req.delivery_address,
        agreed_rules=True,
    )
    db.add(p); await db.flush(); return {"id": p.id, "message": "参与成功"}


@router.get("/{go_id}/participants")
async def list_participants(go_id: int, current_user: User = Depends(get_current_user),
                            db: AsyncSession = Depends(get_db)):
    items, total_qty, wh_count = await _get_participant_details(db, go_id)
    return {"data": items, "total_quantity": total_qty, "warehouse_count": wh_count}



@router.get("/history")
async def history(
    page: int = 1, page_size: int = 50,
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    query = select(GroupOrder).where(
        GroupOrder.status.in_([GroupOrderStatus.COMPLETED.value, GroupOrderStatus.CANCELLED.value])
    ).order_by(GroupOrder.created_at.desc())
    total = (await db.execute(select(func.count(GroupOrder.id)).where(
        GroupOrder.status.in_([GroupOrderStatus.COMPLETED.value, GroupOrderStatus.CANCELLED.value])
    ))).scalar()
    result = await db.execute(query.offset((page-1)*page_size).limit(page_size))
    orders = result.scalars().all()

    wh_map = {}
    wids = {o.warehouse_id for o in orders}
    if wids:
        whs = (await db.execute(select(Warehouse).where(Warehouse.id.in_(wids)))).scalars().all()
        wh_map = {w.id: w.name for w in whs}

    data = []
    for o in orders:
        participants, total_qty, wh_count = await _get_participant_details(db, o.id)
        savings = 0
        if o.final_price and o.target_price and o.final_price < o.target_price:
            savings = (o.target_price - o.final_price) * total_qty
        logistics_per_wh = (o.logistics_fee or 0) / max(wh_count, 1)
        data.append({
            "id": o.id, "warehouse_id": o.warehouse_id,
            "warehouse_name": wh_map.get(o.warehouse_id, ""),
            "item_name": o.item_name, "specification": o.specification,
            "target_quantity": o.target_quantity, "target_price": o.target_price,
            "deadline": o.deadline.isoformat() if o.deadline else None,
            "reason": o.reason, "status": o.status, "status_cn": STATUS_CN.get(o.status, o.status),
            "final_price": o.final_price, "final_supplier": o.final_supplier,
            "logistics_fee": o.logistics_fee,
            "total_quantity": total_qty,
            "total_amount": total_qty * (o.final_price or o.target_price or 0),
            "participant_warehouse_count": wh_count,
            "participants": participants,
            "savings": savings,
            "logistics_per_warehouse": round(logistics_per_wh, 2),
            "created_at": o.created_at.isoformat() if o.created_at else None,
        })
    return {"data": data, "total": total, "page": page, "page_size": page_size}



@router.get("/{go_id}")
async def get_order_detail(go_id: int, current_user: User = Depends(get_current_user),
                            db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(GroupOrder).where(GroupOrder.id == go_id))
    o = result.scalar_one_or_none()
    if not o: raise HTTPException(404, "拼单不存在")
    items, total_qty, wh_count = await _get_participant_details(db, go_id)
    wh = (await db.execute(select(Warehouse).where(Warehouse.id == o.warehouse_id))).scalar_one_or_none()
    return {
        "id": o.id, "warehouse_id": o.warehouse_id,
        "warehouse_name": wh.name if wh else "",
        "item_name": o.item_name, "specification": o.specification,
        "target_quantity": o.target_quantity, "target_price": o.target_price,
        "deadline": o.deadline.isoformat() if o.deadline else None,
        "reason": o.reason, "status": o.status, "status_cn": STATUS_CN.get(o.status, o.status),
        "final_price": o.final_price, "final_supplier": o.final_supplier,
        "logistics_fee": o.logistics_fee,
        "current_quantity": total_qty,
        "participant_warehouse_count": wh_count,
        "participants": items,
        "created_at": o.created_at.isoformat() if o.created_at else None,
    }


@router.put("/{go_id}/close")
async def close_order(go_id: int, current_user: User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(GroupOrder).where(GroupOrder.id == go_id))
    o = result.scalar_one_or_none()
    if not o: raise HTTPException(404, "拼单不存在")
    if current_user.role not in (Role.SUPER_ADMIN, Role.WAREHOUSE_ADMIN):
        raise HTTPException(403, "无权限")
    if current_user.role != Role.SUPER_ADMIN and o.warehouse_id not in get_wh_ids(current_user):
        raise HTTPException(403, "只能操作本仓库发起的拼单")
    if o.status != GroupOrderStatus.OPEN.value:
        raise HTTPException(400, "只能截止开放中的拼单")
    o.status = GroupOrderStatus.CLOSED.value
    await db.flush()
    # Return summary
    items, total_qty, wh_count = await _get_participant_details(db, go_id)
    total_amount = total_qty * (o.target_price or 0)
    return {
        "message": "拼单已截止",
        "summary": {
            "item_name": o.item_name,
            "total_quantity": total_qty,
            "total_amount": total_amount,
            "warehouse_count": wh_count,
            "met_target": total_qty >= o.target_quantity,
            "target_quantity": o.target_quantity,
        }
    }


@router.put("/{go_id}/complete")
async def complete_order(go_id: int, req: CompleteRequest,
                         current_user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(GroupOrder).where(GroupOrder.id == go_id))
    o = result.scalar_one_or_none()
    if not o: raise HTTPException(404, "拼单不存在")
    if current_user.role not in (Role.SUPER_ADMIN, Role.WAREHOUSE_ADMIN):
        raise HTTPException(403, "无权限")
    if current_user.role != Role.SUPER_ADMIN and o.warehouse_id not in get_wh_ids(current_user):
        raise HTTPException(403, "只能操作本仓库发起的拼单")
    if o.status != GroupOrderStatus.CLOSED.value:
        raise HTTPException(400, "只能完成已截止的拼单")
    o.status = GroupOrderStatus.COMPLETED.value
    o.final_price = req.final_price; o.final_supplier = req.final_supplier
    o.logistics_fee = req.logistics_fee; o.completed_by = current_user.id
    await db.flush(); return {"message": "采购完成"}


@router.put("/{go_id}/cancel")
async def cancel_order(go_id: int, req: CancelRequest,
                        current_user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(GroupOrder).where(GroupOrder.id == go_id))
    o = result.scalar_one_or_none()
    if not o: raise HTTPException(404, "拼单不存在")
    if current_user.role not in (Role.SUPER_ADMIN, Role.WAREHOUSE_ADMIN):
        raise HTTPException(403, "无权限")
    if current_user.role != Role.SUPER_ADMIN and o.warehouse_id not in get_wh_ids(current_user):
        raise HTTPException(403, "只能操作本仓库发起的拼单")
    if o.status not in (GroupOrderStatus.OPEN.value, GroupOrderStatus.CLOSED.value):
        raise HTTPException(400, "只能取消开放中或已截止的拼单")
    o.status = GroupOrderStatus.CANCELLED.value
    o.reason = (o.reason or "") + f" [取消原因: {req.reason}]"
    await db.flush(); return {"message": "拼单已取消"}



@router.put("/participant/{participant_id}/ban")
async def ban_participant(participant_id: int, current_user: User = Depends(require_role(Role.SUPER_ADMIN)),
                          db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(GroupOrderParticipant).where(GroupOrderParticipant.id == participant_id))
    p = result.scalar_one_or_none()
    if not p: raise HTTPException(404, "参与记录不存在")
    p.is_banned = True; await db.flush()
    return {"message": "已禁止该仓库参与拼单"}

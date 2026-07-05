from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.models.group_order import GroupOrder, GroupOrderParticipant, GroupOrderStatus
from app.models.warehouse import Warehouse
from app.models.user import User
from app.core.permissions import get_current_user, Role, require_role
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

class BanRequest(BaseModel):
    warehouse_id: int; reason: Optional[str] = None

def get_wh(user: User) -> int:
    return user.warehouse_id or 1

@router.get("")
async def list_group_orders(
    page: int = 1, page_size: int = 20, status: str = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(GroupOrder); count_q = select(func.count(GroupOrder.id))
    if current_user.role != Role.SUPER_ADMIN:
        query = query.where(GroupOrder.warehouse_id == get_wh(current_user))
        count_q = count_q.where(GroupOrder.warehouse_id == get_wh(current_user))
    if status:
        query = query.where(GroupOrder.status == status)
        count_q = count_q.where(GroupOrder.status == status)
    total = (await db.execute(count_q)).scalar()
    result = await db.execute(query.order_by(GroupOrder.created_at.desc()).offset((page-1)*page_size).limit(page_size))
    orders = result.scalars().all()
    # Get participant counts
    go_ids = [o.id for o in orders]
    part_counts = {}
    if go_ids:
        for gid in go_ids:
            cnt = (await db.execute(select(func.sum(GroupOrderParticipant.quantity)).where(GroupOrderParticipant.group_order_id == gid))).scalar() or 0
            part_counts[gid] = cnt
    wh_map = {}
    wids = {o.warehouse_id for o in orders}
    if wids:
        whs = (await db.execute(select(Warehouse).where(Warehouse.id.in_(wids)))).scalars().all()
        wh_map = {w.id: w.name for w in whs}
    return {"data": [{
        "id": o.id, "warehouse_id": o.warehouse_id, "warehouse_name": wh_map.get(o.warehouse_id, ""),
        "item_name": o.item_name, "specification": o.specification,
        "target_quantity": o.target_quantity, "target_price": o.target_price,
        "deadline": o.deadline.isoformat() if o.deadline else None,
        "reason": o.reason, "status": o.status,
        "final_price": o.final_price, "final_supplier": o.final_supplier,
        "logistics_fee": o.logistics_fee,
        "current_quantity": part_counts.get(o.id, 0),
        "created_at": o.created_at.isoformat() if o.created_at else None,
    } for o in orders], "total": total, "page": page, "page_size": page_size}

@router.post("")
async def create_group_order(req: GOCreate, current_user: User = Depends(get_current_user),
                              db: AsyncSession = Depends(get_db)):
    if current_user.role not in (Role.SUPER_ADMIN, Role.WAREHOUSE_ADMIN):
        raise HTTPException(403, "仅仓库管理员可发起")
    o = GroupOrder(
        warehouse_id=get_wh(current_user), item_name=req.item_name,
        specification=req.specification, target_quantity=req.target_quantity,
        target_price=req.target_price, deadline=datetime.fromisoformat(req.deadline),
        reason=req.reason, initiator_id=current_user.id,
    )
    db.add(o); await db.flush(); return {"id": o.id, "message": "拼单发起成功"}

@router.post("/{go_id}/join")
async def join_group_order(go_id: int, req: JoinRequest, current_user: User = Depends(get_current_user),
                            db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(GroupOrder).where(GroupOrder.id == go_id))
    o = result.scalar_one_or_none()
    if not o: raise HTTPException(404, "拼单不存在")
    if o.status != GroupOrderStatus.OPEN.value:
        raise HTTPException(400, "拼单已截止")
    if not req.agreed_rules:
        raise HTTPException(400, "需同意拼单规则")
    # Check not banned
    banned = (await db.execute(select(GroupOrderParticipant).where(
        GroupOrderParticipant.warehouse_id == get_wh(current_user),
        GroupOrderParticipant.is_banned == True,
    ))).scalars().all()
    if banned:
        raise HTTPException(403, "该仓库已被禁止参与拼单")
    p = GroupOrderParticipant(
        group_order_id=go_id, warehouse_id=get_wh(current_user),
        quantity=req.quantity, delivery_address=req.delivery_address,
        agreed_rules=True,
    )
    db.add(p); await db.flush(); return {"id": p.id, "message": "参与成功"}

@router.get("/{go_id}/participants")
async def list_participants(go_id: int, current_user: User = Depends(get_current_user),
                            db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(GroupOrderParticipant).where(GroupOrderParticipant.group_order_id == go_id))
    ps = result.scalars().all()
    wh_map = {}
    wids = {p.warehouse_id for p in ps}
    if wids:
        whs = (await db.execute(select(Warehouse).where(Warehouse.id.in_(wids)))).scalars().all()
        wh_map = {w.id: w.name for w in whs}
    total_qty = sum(p.quantity for p in ps)
    return {"data": [{"id": p.id, "warehouse_name": wh_map.get(p.warehouse_id, ""),
                      "quantity": p.quantity, "delivery_address": p.delivery_address,
                      "created_at": p.created_at.isoformat() if p.created_at else None} for p in ps],
            "total_quantity": total_qty}

@router.put("/{go_id}/close")
async def close_order(go_id: int, current_user: User = Depends(require_role(Role.SUPER_ADMIN)),
                      db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(GroupOrder).where(GroupOrder.id == go_id))
    o = result.scalar_one_or_none()
    if not o: raise HTTPException(404, "拼单不存在")
    o.status = GroupOrderStatus.CLOSED.value
    await db.flush(); return {"message": "拼单已截止"}

@router.put("/{go_id}/complete")
async def complete_order(go_id: int, req: CompleteRequest,
                         current_user: User = Depends(require_role(Role.SUPER_ADMIN)),
                         db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(GroupOrder).where(GroupOrder.id == go_id))
    o = result.scalar_one_or_none()
    if not o: raise HTTPException(404, "拼单不存在")
    o.status = GroupOrderStatus.COMPLETED.value
    o.final_price = req.final_price; o.final_supplier = req.final_supplier
    o.logistics_fee = req.logistics_fee; o.completed_by = current_user.id
    await db.flush(); return {"message": "采购完成"}

@router.get("/history")
async def history(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    # Show only completed orders where this warehouse participated
    sub = select(GroupOrderParticipant.group_order_id).where(
        GroupOrderParticipant.warehouse_id == get_wh(current_user)
    )
    if current_user.role == Role.SUPER_ADMIN:
        query = select(GroupOrder).where(GroupOrder.status == GroupOrderStatus.COMPLETED.value)
    else:
        query = select(GroupOrder).where(
            GroupOrder.id.in_(sub),
            GroupOrder.status == GroupOrderStatus.COMPLETED.value,
        )
    result = await db.execute(query.order_by(GroupOrder.created_at.desc()))
    orders = result.scalars().all()
    return {"data": [{"id": o.id, "item_name": o.item_name, "final_price": o.final_price,
                      "final_supplier": o.final_supplier, "logistics_fee": o.logistics_fee} for o in orders]}

@router.put("/participant/{participant_id}/ban")
async def ban_participant(participant_id: int, current_user: User = Depends(require_role(Role.SUPER_ADMIN)),
                          db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(GroupOrderParticipant).where(GroupOrderParticipant.id == participant_id))
    p = result.scalar_one_or_none()
    if not p: raise HTTPException(404, "参与记录不存在")
    p.is_banned = True; await db.flush()
    return {"message": "已禁止该仓库参与拼单"}

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.models.market import MarketItem, MarketStatus
from app.models.user import User
from app.models.warehouse import Warehouse
from app.core.permissions import get_current_user, get_wh_id, get_wh_ids, Role, require_role
from pydantic import BaseModel
from typing import Optional
from app.core.timezone import thai_now, thai_today
from datetime import datetime

router = APIRouter()

class MarketCreate(BaseModel):
    name: str; quantity: int; price: float = 0
    image: Optional[str] = None; description: Optional[str] = None

class MarketReview(BaseModel):
    status: str  # approved / rejected
    review_remark: Optional[str] = None

class PurchaseRequest(BaseModel):
    contact_info: str

@router.get("")
async def list_items(
    page: int = 1, page_size: int = 20, search: str = None,
    status: str = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    query = select(MarketItem); count_q = select(func.count(MarketItem.id))
    # All warehouse visible for approved items; pending only for uploader
    if current_user.role != Role.SUPER_ADMIN:
        query = query.where(
            (MarketItem.status == MarketStatus.APPROVED.value) |
            (MarketItem.uploader_id == current_user.id)
        )
        count_q = count_q.where(
            (MarketItem.status == MarketStatus.APPROVED.value) |
            (MarketItem.uploader_id == current_user.id)
        )
    if search:
        query = query.where(MarketItem.name.ilike(f"%{search}%"))
        count_q = count_q.where(MarketItem.name.ilike(f"%{search}%"))
    if status:
        query = query.where(MarketItem.status == status)
        count_q = count_q.where(MarketItem.status == status)
    total = (await db.execute(count_q)).scalar()
    result = await db.execute(query.order_by(MarketItem.created_at.desc()).offset((page-1)*page_size).limit(page_size))
    items = result.scalars().all()
    uid_map = {}
    uids = {i.uploader_id for i in items}
    if uids:
        users = (await db.execute(select(User).where(User.id.in_(uids)))).scalars().all()
        uid_map = {u.id: u.display_name for u in users}
    wh_map = {}
    wids = {i.warehouse_id for i in items}
    if wids:
        whs = (await db.execute(select(Warehouse).where(Warehouse.id.in_(wids)))).scalars().all()
        wh_map = {w.id: w.name for w in whs}
    return {"data": [{
        "id": i.id, "warehouse_id": i.warehouse_id, "warehouse_name": wh_map.get(i.warehouse_id, ""),
        "name": i.name, "quantity": i.quantity, "price": i.price,
        "image": i.image, "description": i.description, "status": i.status,
        "uploader_name": uid_map.get(i.uploader_id, ""), "contact_info": i.contact_info,
        "created_at": i.created_at.isoformat() if i.created_at else None,
    } for i in items], "total": total, "page": page, "page_size": page_size}

@router.post("")
async def create_item(req: MarketCreate, current_user: User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if current_user.role not in (Role.SUPER_ADMIN, Role.WAREHOUSE_ADMIN):
        raise HTTPException(403, "仅仓库管理员可上架")
    i = MarketItem(
        warehouse_id=get_wh_id(current_user), name=req.name, quantity=req.quantity,
        price=req.price, image=req.image, description=req.description,
        uploader_id=current_user.id,
    )
    db.add(i); await db.flush(); return {"id": i.id, "message": "上架成功，等待审核"}

@router.get("/review-list")
async def review_list(current_user: User = Depends(require_role(Role.SUPER_ADMIN)),
                      db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(MarketItem).where(MarketItem.status == MarketStatus.PENDING.value).order_by(MarketItem.created_at.asc()))
    items = result.scalars().all()
    wh_map = {}
    wids = {i.warehouse_id for i in items}
    if wids:
        whs = (await db.execute(select(Warehouse).where(Warehouse.id.in_(wids)))).scalars().all()
        wh_map = {w.id: w.name for w in whs}
    return {"data": [{"id": i.id, "name": i.name, "warehouse_name": wh_map.get(i.warehouse_id, ""),
                      "quantity": i.quantity, "price": i.price, "description": i.description,
                      "image": i.image, "created_at": i.created_at.isoformat() if i.created_at else None} for i in items]}

@router.put("/{item_id}/review")
async def review_item(item_id: int, req: MarketReview, current_user: User = Depends(require_role(Role.SUPER_ADMIN)),
                      db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(MarketItem).where(MarketItem.id == item_id))
    i = result.scalar_one_or_none()
    if not i: raise HTTPException(404, "商品不存在")
    i.status = req.status; i.review_remark = req.review_remark
    i.reviewer_id = current_user.id; i.reviewed_at = thai_now()
    await db.flush(); return {"message": f"审核{'通过' if req.status == 'approved' else '驳回'}"}

@router.post("/{item_id}/purchase")
async def purchase(item_id: int, req: PurchaseRequest, current_user: User = Depends(get_current_user),
                   db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(MarketItem).where(MarketItem.id == item_id))
    i = result.scalar_one_or_none()
    if not i: raise HTTPException(404, "商品不存在")
    if i.status != MarketStatus.APPROVED.value:
        raise HTTPException(400, "商品未审核通过")
    # 防覆盖：已有买家申请时不允许被后来者冲掉
    if i.contact_info:
        raise HTTPException(400, "该商品已有买家申请，请等待卖家确认或联系卖家")
    i.contact_info = req.contact_info  # Store buyer contact
    await db.flush()
    return {"message": "购买申请已提交", "seller_warehouse": i.warehouse_id}

@router.put("/{item_id}/confirm")
async def confirm_trade(item_id: int, current_user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(MarketItem).where(MarketItem.id == item_id))
    i = result.scalar_one_or_none()
    if not i: raise HTTPException(404, "商品不存在")
    if current_user.role == Role.SUPER_ADMIN or get_wh_id(current_user) == i.warehouse_id:
        i.status = MarketStatus.SOLD.value
        await db.flush(); return {"message": "交易确认完成"}
    raise HTTPException(403, "无权限确认")

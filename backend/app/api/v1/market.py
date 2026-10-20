from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.models.market import MarketItem, MarketStatus
from app.models.user import User
from app.models.warehouse import Warehouse
from app.core.permissions import get_current_user, get_wh_id, get_wh_ids, Role, require_role, require_non_labor
from pydantic import BaseModel
from typing import Optional
from app.core.timezone import thai_now, thai_today
from datetime import datetime
from app.core.shared_platform import publication_warehouse

router = APIRouter()

class MarketCreate(BaseModel):
    name: str; quantity: int; price: float = 0
    image: Optional[str] = None; description: Optional[str] = None
    warehouse_id: Optional[int] = None

class MarketReview(BaseModel):
    status: str  # approved / rejected
    review_remark: Optional[str] = None

class PurchaseRequest(BaseModel):
    contact_info: str


async def validate_market_image(db, user, image):
    if not image:
        return
    from pathlib import Path
    from app.api.secure_uploads import upload_root, may_read, has_private_reference
    target = image.lstrip("/")
    parts = Path(target).parts
    path = upload_root().joinpath(*parts[1:]).resolve()
    if (len(parts) < 3 or parts[0] != "uploads" or not parts[1].isdigit() or ".." in parts
        or not path.is_relative_to(upload_root()) or not path.is_file()
        or path.suffix.lower() not in (".jpg", ".jpeg", ".png", ".webp")):
        raise HTTPException(400, "请上传有效的市场商品图片")
    if await has_private_reference(db, target) or not await may_read(db, user, target):
        raise HTTPException(403, "市场图片不能引用业务附件或他人未发布的图片")


@router.post("/image")
async def upload_market_image(file: UploadFile = File(...), warehouse_id: int = Form(...),
    current_user: User = Depends(require_role(Role.SUPER_ADMIN)), db: AsyncSession = Depends(get_db)):
    import uuid
    from app.api.secure_uploads import upload_root, mark_temporary_upload
    from app.services.image_utils import save_image, is_image
    wid = await publication_warehouse(db, current_user, warehouse_id)
    content = await file.read()
    ext = (file.filename or "").rsplit(".", 1)[-1].lower()
    if ext not in ("jpg", "jpeg", "png", "webp") or not is_image(content):
        raise HTTPException(400, "请上传有效的市场商品图片")
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(400, "文件大小不能超过10MB")
    rel = f"uploads/{wid}/{thai_today().isoformat()}/market"
    result = save_image(content, str(upload_root().joinpath(*rel.split('/')[1:])), rel, f"{uuid.uuid4().hex}.{ext}")
    for key in ("path", "thumb_path"):
        if result.get(key): mark_temporary_upload(result[key], current_user)
    return {"path": result["path"], "thumb_path": result.get("thumb_path")}

@router.get("")
async def list_items(
    page: int = 1, page_size: int = 20, search: str = None,
    status: str = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
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
        "uploader_name": uid_map.get(i.uploader_id, ""), "contact_info": i.contact_info if current_user.role == Role.SUPER_ADMIN else None,
        "created_at": i.created_at.isoformat() if i.created_at else None,
    } for i in items], "total": total, "page": page, "page_size": page_size}

@router.post("")
async def create_item(req: MarketCreate, current_user: User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    wh_id = await publication_warehouse(db, current_user, req.warehouse_id)
    await validate_market_image(db, current_user, req.image)
    i = MarketItem(
        warehouse_id=wh_id, name=req.name, quantity=req.quantity,
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
    if req.status == MarketStatus.APPROVED.value:
        await validate_market_image(db, current_user, i.image)
    i.status = req.status; i.review_remark = req.review_remark
    i.reviewer_id = current_user.id; i.reviewed_at = thai_now()
    await db.flush(); return {"message": f"审核{'通过' if req.status == 'approved' else '驳回'}"}

@router.post("/{item_id}/purchase", dependencies=[Depends(require_non_labor)])
async def purchase(item_id: int, req: PurchaseRequest, current_user: User = Depends(get_current_user),
                   db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "请使用仓库管理账号参与跨仓业务")
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

@router.put("/{item_id}/confirm", dependencies=[Depends(require_non_labor)])
async def confirm_trade(item_id: int, current_user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    if current_user.role != Role.SUPER_ADMIN:
        raise HTTPException(403, "只有超级管理员可以确认跨仓交易")
    result = await db.execute(select(MarketItem).where(MarketItem.id == item_id))
    i = result.scalar_one_or_none()
    if not i: raise HTTPException(404, "商品不存在")
    if current_user.role == Role.SUPER_ADMIN or get_wh_id(current_user) == i.warehouse_id:
        i.status = MarketStatus.SOLD.value
        await db.flush(); return {"message": "交易确认完成"}
    raise HTTPException(403, "无权限确认")

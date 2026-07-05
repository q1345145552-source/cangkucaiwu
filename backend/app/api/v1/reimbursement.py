from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime
from app.database import get_db
from app.models.reimbursement import Reimbursement, ReimbursementItem, ReimbStatus
from app.models.user import User
from app.core.permissions import get_current_user, Role, check_staff_permission
from pydantic import BaseModel
from typing import Optional, List

router = APIRouter()

class ReimbItemCreate(BaseModel):
    category: str; amount: float; description: Optional[str] = None
    receipt: Optional[str] = None

class ReimbCreate(BaseModel):
    items: List[ReimbItemCreate]; submit_date: str; currency: str = "THB"

class ReimbReview(BaseModel):
    items: List[dict]  # [{"item_id": 1, "status": "approved"/"rejected", "remark": ""}]
    overall_remark: Optional[str] = None

class CategoryReq(BaseModel):
    name: str; description: Optional[str] = None

def get_wh(user: User) -> int:
    return user.warehouse_id or 1

@router.get("")
async def list_reimbursements(
    page: int = 1, page_size: int = 20, month: str = None, status: str = None,
    employee_id: int = None,
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    query = select(Reimbursement); count_q = select(func.count(Reimbursement.id))
    if current_user.role != Role.SUPER_ADMIN:
        query = query.where(Reimbursement.warehouse_id == current_user.warehouse_id)
        count_q = count_q.where(Reimbursement.warehouse_id == current_user.warehouse_id)
    if month:
        query = query.where(func.to_char(Reimbursement.submit_date, 'YYYY-MM') == month)
        count_q = count_q.where(func.to_char(Reimbursement.submit_date, 'YYYY-MM') == month)
    if status:
        query = query.where(Reimbursement.status == status)
        count_q = count_q.where(Reimbursement.status == status)
    if employee_id:
        query = query.where(Reimbursement.employee_id == employee_id)
        count_q = count_q.where(Reimbursement.employee_id == employee_id)
    total = (await db.execute(count_q)).scalar()
    result = await db.execute(query.order_by(Reimbursement.created_at.desc()).offset((page-1)*page_size).limit(page_size))
    reimbs = result.scalars().all()
    uids = {r.employee_id for r in reimbs}
    umap = {}
    if uids:
        users = (await db.execute(select(User).where(User.id.in_(uids)))).scalars().all()
        umap = {u.id: u.display_name for u in users}
    return {"data": [{
        "id": r.id, "warehouse_id": r.warehouse_id, "employee_id": r.employee_id,
        "employee_name": umap.get(r.employee_id, ""),
        "submit_date": r.submit_date.isoformat() if r.submit_date else None,
        "total_amount": r.total_amount, "currency": r.currency, "status": r.status,
        "review_remark": r.review_remark, "paid_at": r.paid_at.isoformat() if r.paid_at else None,
    } for r in reimbs], "total": total, "page": page, "page_size": page_size}

@router.post("")
async def create_reimbursement(req: ReimbCreate, current_user: User = Depends(get_current_user),
                                db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    total = sum(i.amount for i in req.items)
    r = Reimbursement(
        warehouse_id=get_wh(current_user), employee_id=current_user.id,
        submit_date=datetime.fromisoformat(req.submit_date),
        total_amount=total, currency=req.currency,
    )
    db.add(r); await db.flush()
    for item in req.items:
        db.add(ReimbursementItem(reimbursement_id=r.id, category=item.category,
                                 amount=item.amount, description=item.description, receipt=item.receipt))
    await db.flush(); return {"id": r.id, "message": "报销单创建成功"}

@router.get("/{reimb_id}")
async def get_reimb_detail(reimb_id: int, current_user: User = Depends(get_current_user),
                           db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    result = await db.execute(select(Reimbursement).where(Reimbursement.id == reimb_id))
    r = result.scalar_one_or_none()
    if not r: raise HTTPException(404, "报销单不存在")
    items = (await db.execute(select(ReimbursementItem).where(ReimbursementItem.reimbursement_id == reimb_id))).scalars().all()
    return {
        "id": r.id, "warehouse_id": r.warehouse_id, "employee_id": r.employee_id,
        "submit_date": r.submit_date.isoformat() if r.submit_date else None,
        "total_amount": r.total_amount, "currency": r.currency, "status": r.status,
        "review_remark": r.review_remark, "paid_at": r.paid_at.isoformat() if r.paid_at else None,
        "items": [{"id": i.id, "category": i.category, "amount": i.amount,
                   "description": i.description, "receipt": i.receipt,
                   "review_status": i.review_status} for i in items],
    }

@router.put("/{reimb_id}")
async def edit_reimb(reimb_id: int, req: ReimbCreate, current_user: User = Depends(get_current_user),
                     db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    result = await db.execute(select(Reimbursement).where(Reimbursement.id == reimb_id))
    r = result.scalar_one_or_none()
    if not r: raise HTTPException(404, "报销单不存在")
    if r.status != ReimbStatus.PENDING.value:
        raise HTTPException(400, "仅待审批状态可编辑")
    r.total_amount = sum(i.amount for i in req.items)
    # Delete old items and recreate
    old = (await db.execute(select(ReimbursementItem).where(ReimbursementItem.reimbursement_id == reimb_id))).scalars().all()
    for o in old: await db.delete(o)
    for item in req.items:
        db.add(ReimbursementItem(reimbursement_id=reimb_id, category=item.category,
                                 amount=item.amount, description=item.description, receipt=item.receipt))
    await db.flush(); return {"message": "更新成功"}

@router.post("/{reimb_id}/submit")
async def submit_reimb(reimb_id: int, current_user: User = Depends(get_current_user),
                       db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    result = await db.execute(select(Reimbursement).where(Reimbursement.id == reimb_id))
    r = result.scalar_one_or_none()
    if not r: raise HTTPException(404, "报销单不存在")
    r.status = ReimbStatus.PENDING.value
    await db.flush(); return {"message": "已提交审批"}

@router.post("/{reimb_id}/review")
async def review_reimb(reimb_id: int, req: ReimbReview, current_user: User = Depends(get_current_user),
                       db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if current_user.role == Role.STAFF and "approve_reimbursement" not in (current_user.extra_permissions or []):
        raise HTTPException(403, "无审批报销权限")
    if current_user.role not in (Role.SUPER_ADMIN, Role.WAREHOUSE_ADMIN, Role.STAFF):
        raise HTTPException(403, "无审批权限")
    result = await db.execute(select(Reimbursement).where(Reimbursement.id == reimb_id))
    r = result.scalar_one_or_none()
    if not r: raise HTTPException(404, "报销单不存在")
    r.reviewer_id = current_user.id; r.review_remark = req.overall_remark

    approved = sum(item.get("amount", 0) for item in req.items if item.get("status") == "approved")
    rejected = sum(item.get("amount", 0) for item in req.items if item.get("status") != "approved")

    if rejected == 0:
        r.status = ReimbStatus.APPROVED.value
    elif approved > 0:
        r.status = ReimbStatus.PARTIALLY_APPROVED.value
    else:
        r.status = ReimbStatus.REJECTED.value
    r.total_amount = approved

    for item_data in req.items:
        item = (await db.execute(select(ReimbursementItem).where(ReimbursementItem.id == item_data["item_id"]))).scalar_one_or_none()
        if item:
            item.review_status = item_data.get("status", "rejected")
    await db.flush(); return {"message": "审批完成", "status": r.status, "approved_amount": approved}

@router.post("/{reimb_id}/pay")
async def pay_reimb(reimb_id: int, current_user: User = Depends(get_current_user),
                    db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if current_user.role not in (Role.SUPER_ADMIN, Role.WAREHOUSE_ADMIN):
        raise HTTPException(403, "无权限")
    result = await db.execute(select(Reimbursement).where(Reimbursement.id == reimb_id))
    r = result.scalar_one_or_none()
    if not r: raise HTTPException(404, "报销单不存在")
    if r.status not in (ReimbStatus.APPROVED.value, ReimbStatus.PARTIALLY_APPROVED.value):
        raise HTTPException(400, "仅已审批状态可付款")
    r.status = ReimbStatus.PAID.value; r.paid_at = datetime.now()
    await db.flush(); return {"message": "已标记付款"}


# === Reimbursement Categories ===
_reimb_categories = ["交通费", "餐饮费", "办公用品", "通讯费", "差旅费", "水电费", "维修费", "其他"]

@router.get("/categories")
async def list_reimb_categories():
    return {"data": [{"id": i+1, "name": n} for i, n in enumerate(_reimb_categories)]}

@router.post("/categories")
async def create_reimb_category(req: CategoryReq):
    _reimb_categories.append(req.name)
    return {"id": len(_reimb_categories), "name": req.name, "message": "类别添加成功"}

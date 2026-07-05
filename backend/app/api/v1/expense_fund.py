from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime
from app.database import get_db
from app.models.expense_fund import ExpenseFund, ExpenseFundItem, FundStatus, ReviewStatus, ReviewAction
from app.models.user import User
from app.core.permissions import get_current_user, Role, check_staff_permission
from pydantic import BaseModel
from typing import Optional, List

router = APIRouter()

class FundCreate(BaseModel):
    receive_date: str; amount: float; purpose: str
    expected_return_date: Optional[str] = None

class FundItemCreate(BaseModel):
    expense_date: str; category: str; amount: float; description: str
    receipt: Optional[str] = None

class ReviewRequest(BaseModel):
    action: str  # approve / reject
    items: List[dict]  # [{"item_id": 1, "status": "approved", "remark": "", "action": "employee_pay"}]
    remark: Optional[str] = None

def get_wh(user: User) -> int:
    return user.warehouse_id or 1

@router.get("")
async def list_funds(
    employee_id: int = None, status: str = None,
    page: int = 1, page_size: int = 20,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    query = select(ExpenseFund); count_q = select(func.count(ExpenseFund.id))
    if current_user.role != Role.SUPER_ADMIN:
        query = query.where(ExpenseFund.warehouse_id == current_user.warehouse_id)
        count_q = count_q.where(ExpenseFund.warehouse_id == current_user.warehouse_id)
    if employee_id:
        query = query.where(ExpenseFund.employee_id == employee_id)
        count_q = count_q.where(ExpenseFund.employee_id == employee_id)
    if status:
        query = query.where(ExpenseFund.status == status)
        count_q = count_q.where(ExpenseFund.status == status)
    total = (await db.execute(count_q)).scalar()
    result = await db.execute(query.order_by(ExpenseFund.created_at.desc()).offset((page-1)*page_size).limit(page_size))
    funds = result.scalars().all()
    uid_map = {}
    uids = {f.employee_id for f in funds}
    if uids:
        users = (await db.execute(select(User).where(User.id.in_(uids)))).scalars().all()
        uid_map = {u.id: u.display_name for u in users}
    return {"data": [{
        "id": f.id, "warehouse_id": f.warehouse_id, "employee_id": f.employee_id,
        "employee_name": uid_map.get(f.employee_id, ""),
        "receive_date": f.receive_date.isoformat() if f.receive_date else None,
        "amount": f.amount, "purpose": f.purpose,
        "expected_return_date": f.expected_return_date.isoformat() if f.expected_return_date else None,
        "status": f.status, "remaining_balance": f.remaining_balance,
        "alert_threshold": f.alert_threshold,
    } for f in funds], "total": total, "page": page, "page_size": page_size}

@router.post("")
async def create_fund(req: FundCreate, current_user: User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if current_user.role == Role.STAFF:
        raise HTTPException(403, "仓库财务无权领用")
    f = ExpenseFund(
        warehouse_id=get_wh(current_user), employee_id=current_user.id,
        receive_date=datetime.fromisoformat(req.receive_date),
        amount=req.amount, purpose=req.purpose,
        expected_return_date=datetime.fromisoformat(req.expected_return_date) if req.expected_return_date else None,
        remaining_balance=req.amount,
    )
    db.add(f); await db.flush(); return {"id": f.id, "message": "领用成功"}

@router.get("/{fund_id}/items")
async def list_items(fund_id: int, current_user: User = Depends(get_current_user),
                     db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    result = await db.execute(select(ExpenseFundItem).where(ExpenseFundItem.fund_id == fund_id).order_by(ExpenseFundItem.expense_date.desc()))
    items = result.scalars().all()
    return {"data": [{
        "id": i.id, "fund_id": i.fund_id, "expense_date": i.expense_date.isoformat() if i.expense_date else None,
        "category": i.category, "amount": i.amount, "description": i.description,
        "receipt": i.receipt, "review_status": i.review_status,
        "review_remark": i.review_remark, "review_action": i.review_action,
    } for i in items]}

@router.post("/{fund_id}/items")
async def add_item(fund_id: int, req: FundItemCreate, current_user: User = Depends(get_current_user),
                   db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    result = await db.execute(select(ExpenseFund).where(ExpenseFund.id == fund_id))
    fund = result.scalar_one_or_none()
    if not fund: raise HTTPException(404, "备用金记录不存在")
    if current_user.role == Role.STAFF and fund.employee_id != current_user.id:
        raise HTTPException(403, "只能操作本人领用")
    i = ExpenseFundItem(
        fund_id=fund_id, expense_date=datetime.fromisoformat(req.expense_date),
        category=req.category, amount=req.amount, description=req.description, receipt=req.receipt,
    )
    db.add(i); await db.flush(); return {"id": i.id, "message": "开销记录成功"}

@router.post("/{fund_id}/submit-review")
async def submit_review(fund_id: int, current_user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    result = await db.execute(select(ExpenseFund).where(ExpenseFund.id == fund_id))
    fund = result.scalar_one_or_none()
    if not fund: raise HTTPException(404, "备用金记录不存在")
    if current_user.role == Role.STAFF and fund.employee_id != current_user.id:
        raise HTTPException(403, "只能提交本人")
    # Submit all pending items
    items = (await db.execute(select(ExpenseFundItem).where(
        ExpenseFundItem.fund_id == fund_id, ExpenseFundItem.review_status == ReviewStatus.PENDING.value
    ))).scalars().all()
    for i in items:
        i.review_status = ReviewStatus.PENDING.value
    await db.flush(); return {"message": f"已提交{len(items)}条待审核记录"}

@router.get("/{fund_id}/review")
async def review_board(fund_id: int, current_user: User = Depends(get_current_user),
                       db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if current_user.role not in (Role.SUPER_ADMIN, Role.WAREHOUSE_ADMIN):
        raise HTTPException(403, "无审核权限")
    items = (await db.execute(select(ExpenseFundItem).where(ExpenseFundItem.fund_id == fund_id).order_by(ExpenseFundItem.id))).scalars().all()
    total = sum(i.amount for i in items)
    cats = {}
    for i in items:
        cats[i.category] = cats.get(i.category, 0) + i.amount
    return {"items": [{"id": i.id, "category": i.category, "amount": i.amount, "description": i.description,
                        "review_status": i.review_status} for i in items],
            "total_amount": total, "category_breakdown": cats}

@router.post("/{fund_id}/review")
async def do_review(fund_id: int, req: ReviewRequest, current_user: User = Depends(get_current_user),
                    db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if current_user.role == Role.STAFF and "approve_expense_fund" not in (current_user.extra_permissions or []):
        raise HTTPException(403, "无审批备用金权限")
    if current_user.role not in (Role.SUPER_ADMIN, Role.WAREHOUSE_ADMIN, Role.STAFF):
        raise HTTPException(403, "无审核权限")
    for item_data in req.items:
        item = (await db.execute(select(ExpenseFundItem).where(ExpenseFundItem.id == item_data["item_id"]))).scalar_one_or_none()
        if item:
            item.review_status = "approved" if item_data.get("status") == "approved" else "rejected"
            item.review_remark = item_data.get("remark") or req.remark
            if item_data.get("action"):
                item.review_action = item_data.get("action")
    await db.flush(); return {"message": "审核完成"}

@router.get("/balance")
async def balance_summary(current_user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    query = select(ExpenseFund).where(ExpenseFund.status == FundStatus.ACTIVE.value)
    if current_user.role != Role.SUPER_ADMIN:
        query = query.where(ExpenseFund.warehouse_id == current_user.warehouse_id)
    funds = (await db.execute(query)).scalars().all()
    uids = {f.employee_id for f in funds}
    umap = {}
    if uids:
        users = (await db.execute(select(User).where(User.id.in_(uids)))).scalars().all()
        umap = {u.id: u.display_name for u in users}
    return {"data": [{
        "employee_id": f.employee_id, "employee_name": umap.get(f.employee_id, ""),
        "remaining_balance": f.remaining_balance, "total_amount": f.amount,
        "fund_id": f.id,
    } for f in funds]}

@router.get("/alert")
async def alert_list(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    query = select(ExpenseFund).where(
        ExpenseFund.status == FundStatus.ACTIVE.value,
        ExpenseFund.remaining_balance <= ExpenseFund.alert_threshold,
    )
    if current_user.role != Role.SUPER_ADMIN:
        query = query.where(ExpenseFund.warehouse_id == current_user.warehouse_id)
    funds = (await db.execute(query)).scalars().all()
    uids = {f.employee_id for f in funds}
    umap = {}
    if uids:
        users = (await db.execute(select(User).where(User.id.in_(uids)))).scalars().all()
        umap = {u.id: u.display_name for u in users}
    return {"data": [{"employee_name": umap.get(f.employee_id, ""),
                      "remaining_balance": f.remaining_balance, "threshold": f.alert_threshold,
                      "fund_id": f.id} for f in funds]}

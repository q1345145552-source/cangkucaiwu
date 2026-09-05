from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.core.timezone import thai_now, thai_today
from datetime import datetime, timedelta
from app.database import get_db
from app.models.reimbursement import Reimbursement, ReimbursementItem, ReimbCategory, ReimbStatus
from app.models.expense_fund import ExpenseFund, ExpenseFundItem, FundStatus, ReviewStatus
from app.models.user import User
from app.core.permissions import get_current_user, get_wh_id, get_wh_ids, Role, check_staff_permission
from pydantic import BaseModel
from typing import Optional, List

router = APIRouter()

class ReimbItemCreate(BaseModel):
    category: str; amount: float; description: Optional[str] = None
    receipt: Optional[str] = None

class ReimbCreate(BaseModel):
    items: List[ReimbItemCreate]; submit_date: str; currency: str = "THB"
    is_fund_linked: Optional[str] = "0"

class ReimbReview(BaseModel):
    items: List[dict]  # [{"item_id": 1, "status": "approved"/"rejected", "remark": ""}]
    overall_remark: Optional[str] = None

class CategoryReq(BaseModel):
    name: str; description: Optional[str] = None

@router.get("")
async def list_reimbursements(
    page: int = 1, page_size: int = 20, month: str = None, status: str = None,
    start_date: str = None, end_date: str = None,
    employee_id: int = None,
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    query = select(Reimbursement); count_q = select(func.count(Reimbursement.id))
    if current_user.role != Role.SUPER_ADMIN:
        query = query.where(Reimbursement.warehouse_id.in_(get_wh_ids(current_user)))
        count_q = count_q.where(Reimbursement.warehouse_id.in_(get_wh_ids(current_user)))
    if month:
        query = query.where(func.to_char(Reimbursement.submit_date, 'YYYY-MM') == month)
        count_q = count_q.where(func.to_char(Reimbursement.submit_date, 'YYYY-MM') == month)
    if start_date:
        query = query.where(Reimbursement.submit_date >= datetime.strptime(start_date, "%Y-%m-%d"))
        count_q = count_q.where(Reimbursement.submit_date >= datetime.strptime(start_date, "%Y-%m-%d"))
    if end_date:
        end_next = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
        query = query.where(Reimbursement.submit_date < end_next)
        count_q = count_q.where(Reimbursement.submit_date < end_next)
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
        "is_fund_linked": r.is_fund_linked or "0", "fund_item_id": r.fund_item_id,
        "review_remark": r.review_remark, "paid_at": r.paid_at.isoformat() if r.paid_at else None,
    } for r in reimbs], "total": total, "page": page, "page_size": page_size}

@router.post("")
async def create_reimbursement(req: ReimbCreate, current_user: User = Depends(get_current_user),
                                db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    wh_id = get_wh_id(current_user)
    total = sum(i.amount for i in req.items)

    fund_item_id = None
    if req.is_fund_linked == "1":
        # 查找员工备用金账户
        fund = (await db.execute(select(ExpenseFund).where(
            ExpenseFund.warehouse_id.in_(get_wh_ids(current_user)),
            ExpenseFund.employee_id == current_user.id,
            ExpenseFund.status == FundStatus.ACTIVE.value,
        ))).scalar_one_or_none()
        if not fund:
            raise HTTPException(400, "该员工没有备用金账户，无法关联扣款")
        if (fund.remaining_balance or 0) < total:
            raise HTTPException(400, f"备用金余额不足（当前余额: {fund.remaining_balance:,.0f}，报销金额: {total:,.0f}）")

        # 扣减备用金
        fund.remaining_balance = (fund.remaining_balance or 0) - total

        # 生成备用金开销记录
        descriptions = "; ".join([f"{i.category}: {i.description or ''}" for i in req.items])
        fund_item = ExpenseFundItem(
            fund_id=fund.id,
            expense_date=datetime.fromisoformat(req.submit_date) if req.submit_date else datetime.utcnow(),
            category="报销",
            amount=total,
            currency=req.currency,
            description=f"来自报销管理: {descriptions}",
            review_status=ReviewStatus.PENDING.value,
        )
        db.add(fund_item)
        await db.flush()
        fund_item_id = fund_item.id

    r = Reimbursement(
        warehouse_id=wh_id, employee_id=current_user.id,
        submit_date=datetime.fromisoformat(req.submit_date),
        total_amount=total, currency=req.currency,
        is_fund_linked=req.is_fund_linked or "0",
        fund_item_id=fund_item_id,
        status=ReimbStatus.FUND_LINKED.value if req.is_fund_linked == "1" else ReimbStatus.PENDING.value,
    )
    db.add(r); await db.flush()
    for item in req.items:
        db.add(ReimbursementItem(reimbursement_id=r.id, category=item.category,
                                 amount=item.amount, description=item.description, receipt=item.receipt))
    await db.flush()

    msg = "报销单创建成功，已转入备用金审核" if req.is_fund_linked == "1" else "报销单创建成功"
    return {"id": r.id, "message": msg}

@router.get("/export")
async def export_reimbursements(
    month: str = Query(None), status: str = Query(None),
    start_date: str = Query(None), end_date: str = Query(None),
    employee_id: int = Query(None),
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    """导出报销单为 Excel"""
    from fastapi.responses import StreamingResponse
    import io, openpyxl

    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    wh_id = get_wh_id(current_user)

    query = select(Reimbursement).where(Reimbursement.warehouse_id.in_(get_wh_ids(current_user)))
    if month:
        query = query.where(func.to_char(Reimbursement.submit_date, 'YYYY-MM') == month)
    if start_date:
        query = query.where(Reimbursement.submit_date >= datetime.strptime(start_date, "%Y-%m-%d"))
    if end_date:
        query = query.where(Reimbursement.submit_date < datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1))
    if status:
        query = query.where(Reimbursement.status == status)
    if employee_id:
        query = query.where(Reimbursement.employee_id == employee_id)

    result = await db.execute(query.order_by(Reimbursement.submit_date.desc()))
    reimbs = result.scalars().all()

    uids = {r.employee_id for r in reimbs}
    umap = {}
    if uids:
        users = (await db.execute(select(User).where(User.id.in_(uids)))).scalars().all()
        umap = {u.id: u.display_name for u in users}

    status_labels = {"pending": "待审批", "approved": "已通过", "partially_approved": "部分通过",
                     "rejected": "已驳回", "paid": "已付款", "fund_linked": "转入备用金审核"}

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "报销清单"
    ws.append(["报销人", "提交日期", "金额", "币种", "状态", "审批备注", "付款时间", "关联备用金"])

    for r in reimbs:
        ws.append([
            umap.get(r.employee_id, ""),
            r.submit_date.strftime("%Y-%m-%d") if r.submit_date else "",
            r.total_amount, r.currency,
            status_labels.get(r.status, r.status),
            r.review_remark or "",
            r.paid_at.strftime("%Y-%m-%d %H:%M") if r.paid_at else "",
            "是" if r.is_fund_linked == "1" else "否",
        ])

    output = io.BytesIO()
    wb.save(output); output.seek(0)
    return StreamingResponse(output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=reimbursements.xlsx"})


DEFAULT_REIMB_CATEGORIES = ["交通费", "餐饮费", "办公用品", "通讯费", "差旅费", "水电费", "维修费", "其他"]

@router.get("/categories")
async def list_reimb_categories(current_user: User = Depends(get_current_user),
                                db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    wh_id = get_wh_id(current_user)
    if not wh_id:
        raise HTTPException(400, "当前用户未关联仓库")
    cats = (await db.execute(
        select(ReimbCategory).where(ReimbCategory.warehouse_id.in_(get_wh_ids(current_user)))
        .order_by(ReimbCategory.sort_order, ReimbCategory.id)
    )).scalars().all()
    # 首次访问：该仓库无分类则自动播种默认分类
    if not cats:
        for i, name in enumerate(DEFAULT_REIMB_CATEGORIES):
            db.add(ReimbCategory(warehouse_id=wh_id, name=name, sort_order=i))
        await db.flush()
        cats = (await db.execute(
            select(ReimbCategory).where(ReimbCategory.warehouse_id.in_(get_wh_ids(current_user)))
            .order_by(ReimbCategory.sort_order, ReimbCategory.id)
        )).scalars().all()
    return {"data": [{"id": c.id, "name": c.name} for c in cats]}


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
        "is_fund_linked": r.is_fund_linked or "0", "fund_item_id": r.fund_item_id,
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
    if current_user.role == Role.STAFF and "报销管理" not in (current_user.extra_permissions or []):
        raise HTTPException(403, "无审批报销权限")
    if current_user.role not in (Role.SUPER_ADMIN, Role.WAREHOUSE_ADMIN, Role.STAFF):
        raise HTTPException(403, "无审批权限")
    result = await db.execute(select(Reimbursement).where(Reimbursement.id == reimb_id))
    r = result.scalar_one_or_none()
    if not r: raise HTTPException(404, "报销单不存在")
    if r.warehouse_id not in get_wh_ids(current_user):
        raise HTTPException(403, "只能审批本仓库的报销单")
    # 状态前置：仅待审批/转入备用金审核/部分通过 可再审批，已付款或已驳回不可重复审批（防重复退款）
    from app.services.flow_rules import is_reviewable_reimb, can_refund_fund_item
    if not is_reviewable_reimb(r.status):
        raise HTTPException(400, f"当前状态（{r.status}）不可审批")
    r.reviewer_id = current_user.id; r.review_remark = req.overall_remark

    approved_count = 0; rejected_count = 0; approved_amount = 0
    for item_data in req.items:
        item = (await db.execute(select(ReimbursementItem).where(ReimbursementItem.id == item_data["item_id"]))).scalar_one_or_none()
        if not item: continue
        status = item_data.get("status", "rejected")
        item.review_status = status
        if status == "approved":
            approved_count += 1
            approved_amount += item.amount
        else:
            rejected_count += 1

    if rejected_count == 0:
        r.status = ReimbStatus.APPROVED.value
        if r.is_fund_linked == "1" and r.fund_item_id:
            fund_item = (await db.execute(select(ExpenseFundItem).where(ExpenseFundItem.id == r.fund_item_id))).scalar_one_or_none()
            if fund_item:
                fund_item.review_status = ReviewStatus.APPROVED.value
    elif approved_count > 0:
        r.status = ReimbStatus.PARTIALLY_APPROVED.value
    else:
        r.status = ReimbStatus.REJECTED.value
        if r.is_fund_linked == "1" and r.fund_item_id:
            fund_item = (await db.execute(select(ExpenseFundItem).where(ExpenseFundItem.id == r.fund_item_id))).scalar_one_or_none()
            # 幂等守卫：仅当该备用金开销尚未驳回时才退回余额，避免重复退款
            if fund_item and can_refund_fund_item(fund_item.review_status):
                fund = (await db.execute(select(ExpenseFund).where(ExpenseFund.id == fund_item.fund_id))).scalar_one_or_none()
                if fund:
                    fund.remaining_balance = (fund.remaining_balance or 0) + fund_item.amount
                fund_item.review_status = ReviewStatus.REJECTED.value
    r.total_amount = approved_amount
    await db.flush(); return {"message": "审批完成", "status": r.status, "approved_amount": approved_amount}

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
    r.status = ReimbStatus.PAID.value; r.paid_at = thai_now()
    await db.flush(); return {"message": "已标记付款"}


# === Reimbursement Categories ===
@router.post("/categories")
async def create_reimb_category(req: CategoryReq, current_user: User = Depends(get_current_user),
                                db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if current_user.role not in (Role.SUPER_ADMIN, Role.WAREHOUSE_ADMIN):
        raise HTTPException(403, "无权限")
    wh_id = get_wh_id(current_user)
    if not wh_id:
        raise HTTPException(400, "当前用户未关联仓库")
    name = (req.name or "").strip()
    if not name:
        raise HTTPException(400, "分类名称不能为空")
    # 同仓库去重
    existing = (await db.execute(
        select(ReimbCategory).where(ReimbCategory.warehouse_id.in_(get_wh_ids(current_user)), ReimbCategory.name == name)
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(400, "该分类已存在")
    max_sort = (await db.execute(
        select(func.coalesce(func.max(ReimbCategory.sort_order), 0)).where(ReimbCategory.warehouse_id.in_(get_wh_ids(current_user)))
    )).scalar() or 0
    c = ReimbCategory(warehouse_id=wh_id, name=name, sort_order=max_sort + 1)
    db.add(c); await db.flush()
    return {"id": c.id, "name": c.name, "message": "类别添加成功"}

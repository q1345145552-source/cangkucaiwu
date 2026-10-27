from app.core.personal_finance import personal_finance_access
from app.services import financial_authorization as finance
from app.services.fund_authorization import identities
from app.services.fund_authorization import reimbursement_payment_capability
from app.core.round2_access import mutation_scope, own_scope
from fastapi import APIRouter, Depends, HTTPException, Query, File, UploadFile, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.core.timezone import thai_now, thai_today
from datetime import datetime, timedelta
from app.database import get_db
from app.models.reimbursement import Reimbursement, ReimbursementItem, ReimbCategory, ReimbStatus
from app.models.expense_fund import ExpenseFund, ExpenseFundItem, FundStatus, ReviewStatus
from app.models.user import User
from app.core.permissions import get_current_user, get_wh_id, get_wh_ids, Role, check_staff_permission, require_non_labor
from app.core.financial_reversals import reject_disabled_financial_reversal
from app.services.data_history import record_history
from pydantic import BaseModel, Field
from typing import Optional, List, Literal
from app.services import reimbursement_payment as payments
from app.models.reimbursement_payment import ReimbursementPayment
from app.services.cash_advance_reference import cash_advance_numbers, cash_advance_reference

router = APIRouter(dependencies=[Depends(mutation_scope)])

class ReimbItemCreate(BaseModel):
    model_config = {"extra": "forbid"}
    category: str; amount: float; description: Optional[str] = None
    receipt: Optional[str] = None

class ReimbCreate(BaseModel):
    model_config = {"extra": "forbid"}
    items: List[ReimbItemCreate]; submit_date: str; currency: str = "THB"
    is_fund_linked: Optional[str] = "0"

class ReimbReview(BaseModel):
    items: List[dict]  # [{"item_id": 1, "status": "approved"/"rejected", "remark": ""}]
    overall_remark: Optional[str] = None

class CategoryReq(BaseModel):
    name: str; description: Optional[str] = None

class ReimbPay(BaseModel):
    funding_source: Literal["company_account", "cash_advance", "expense_fund"] | None = None
    payment_account_id: int | None = Field(default=None, gt=0)
    cash_advance_id: int | None = Field(default=None, gt=0)
    payment_method: Literal["cash", "transfer"] = "cash"
    payment_voucher_path: str | None = Field(default=None, max_length=500)

class RevokePayment(BaseModel):
    reason: str | None = Field(default=None, max_length=500)

async def _payment_reimb(db, reimb_id, user, *, lock=False):
    if user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF):
        raise HTTPException(403, "无权限")
    query = select(Reimbursement).where(Reimbursement.id == reimb_id)
    if lock: query = query.with_for_update()
    r = (await db.execute(query)).scalar_one_or_none()
    if r is None: raise HTTPException(404, "报销单不存在")
    if r.warehouse_id not in get_wh_ids(user): raise HTTPException(403, "无权操作其他仓库的报销单")
    return r

@router.get("/payment-sources")
async def payment_sources(reimbursement_id: int, current_user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db), _perm=Depends(personal_finance_access("报销管理"))):
    from app.models.customer import PaymentAccount
    from app.models.cash_advance import CashAdvance
    from app.services.account_balances import current_account_balances
    from app.services.cash_advance_payroll import payroll_usage_totals, usage_amounts
    from app.services.cash_advance_usage import reimbursement_usage_totals
    r = await _payment_reimb(db, reimbursement_id, current_user)
    accounts = (await db.execute(select(PaymentAccount).where(
        PaymentAccount.warehouse_id == r.warehouse_id,
        (PaymentAccount.status == "active") | PaymentAccount.status.is_(None),
    ).order_by(PaymentAccount.id))).scalars().all()
    balances = await current_account_balances(db, accounts)
    advances = (await db.execute(select(CashAdvance).where(
        CashAdvance.warehouse_id == r.warehouse_id, CashAdvance.status == "confirmed",
        CashAdvance.currency == (r.currency or "THB").upper(), CashAdvance.amount > CashAdvance.repaid_amount,
    ).order_by(CashAdvance.id.desc()))).scalars().all()
    wages, expenses = await payroll_usage_totals(db, advances), await reimbursement_usage_totals(db, advances)
    return {"currency": r.currency or "THB", "is_fund_linked": r.is_fund_linked or "0",
        "accounts": [{"id": a.id, "account_name": a.account_name, "account_type": a.account_type,
            "currency": a.currency or "THB", "current_balance": float(balances[a.id])} for a in accounts
            if (a.currency or "THB").upper() == (r.currency or "THB").upper()],
        "cash_advances": [{"id": a.id, "payer_name": a.payer_name, "currency": a.currency,
            "outstanding_amount": float(a.amount - a.repaid_amount), **usage_amounts(a, wages[a.id], expenses[a.id])} for a in advances]}

@router.post("/payment-voucher")
async def payment_voucher(reimbursement_id: int = Form(...), file: UploadFile = File(...),
                          current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
                          _perm=Depends(personal_finance_access("报销管理"))):
    import os, uuid
    from app.services.image_utils import is_image, save_image
    r = await _payment_reimb(db, reimbursement_id, current_user)
    content = await file.read(10 * 1024 * 1024 + 1)
    ext = (file.filename or "").rsplit(".", 1)[-1].lower()
    if not content or len(content) > 10 * 1024 * 1024: raise HTTPException(400, "付款凭证须在10MB以内")
    if ext not in ("png", "jpg", "jpeg", "webp") or not is_image(content): raise HTTPException(400, "请上传有效付款凭证图片")
    subdir = f"{r.warehouse_id}/{thai_now():%Y-%m-%d}/reimbursement-payments"
    output = save_image(content, os.path.join(payments.UPLOAD_DIR, subdir), f"uploads/{subdir}", f"{uuid.uuid4().hex}.{ext}")
    return {"path": output["path"], "thumb_path": output["thumb_path"]}

@router.get("")
async def list_reimbursements(
    page: int = 1, page_size: int = 20, month: str = None, status: str = None,
    start_date: str = None, end_date: str = None,
    employee_id: int = None,
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
    _perm=Depends(personal_finance_access("报销管理")),
):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    query = select(Reimbursement); count_q = select(func.count(Reimbursement.id))
    if current_user.role != Role.SUPER_ADMIN:
        query = query.where(Reimbursement.warehouse_id.in_(get_wh_ids(current_user)))
        count_q = count_q.where(Reimbursement.warehouse_id.in_(get_wh_ids(current_user)))
    if getattr(current_user, '_personal_finance', False):
        query = query.where(Reimbursement.employee_id.in_(current_user._personal_user_ids))
        count_q = count_q.where(Reimbursement.employee_id.in_(current_user._personal_user_ids))
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
    paid = await payments.active_payment_map(db, reimbs)
    advance_numbers = await cash_advance_numbers(db, reimbs)
    return {"data": [{
        "id": r.id, "warehouse_id": r.warehouse_id, "employee_id": r.employee_id,
        "employee_name": umap.get(r.employee_id, ""),
        "submit_date": r.submit_date.isoformat() if r.submit_date else None,
        "total_amount": r.total_amount, "currency": r.currency, "status": r.status,
        "is_fund_linked": r.is_fund_linked or "0", "fund_item_id": r.fund_item_id,
        "can_fund_pay": await reimbursement_payment_capability(db, current_user, r),
        "capabilities": await finance.reimbursement_capabilities(db,current_user,r),
        "review_remark": r.review_remark, "paid_at": r.paid_at.isoformat() if r.paid_at else None,
        **payments.payment_fields(r, paid.get(r.id), can_revoke=current_user.role == Role.WAREHOUSE_ADMIN),
        **cash_advance_reference(r, advance_numbers),
    } for r in reimbs], "total": total, "page": page, "page_size": page_size}

@router.post("", dependencies=[Depends(require_non_labor)])
async def create_reimbursement(req: ReimbCreate, current_user: User = Depends(get_current_user),
                                db: AsyncSession = Depends(get_db),
                                _perm=Depends(personal_finance_access("报销管理"))):
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
        funding_source="expense_fund" if req.is_fund_linked == "1" else None,
        status=ReimbStatus.FUND_LINKED.value if req.is_fund_linked == "1" else ReimbStatus.PENDING.value,
    )
    db.add(r); await db.flush()
    for item in req.items:
        db.add(ReimbursementItem(reimbursement_id=r.id, category=item.category,
                                 amount=item.amount, description=item.description, receipt=item.receipt))
    await db.flush()

    msg = "报销单创建成功，已转入备用金审核" if req.is_fund_linked == "1" else "报销单创建成功"
    await record_history(db, module="reimbursement", record_id=r.id, operator=current_user,
                          operation_type="create", after={
                              "total_amount": total, "currency": req.currency,
                              "submit_date": req.submit_date,
                              "items": [{"category": i.category, "amount": i.amount, "description": i.description} for i in req.items],
                          }, warehouse_id=wh_id)
    return {"id": r.id, "message": msg}

@router.get("/export")
async def export_reimbursements(
    month: str = Query(None), status: str = Query(None),
    start_date: str = Query(None), end_date: str = Query(None),
    employee_id: int = Query(None),
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
    _perm=Depends(personal_finance_access("报销管理")),
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

@router.get("/categories", dependencies=[Depends(require_non_labor)])
async def list_reimb_categories(current_user: User = Depends(get_current_user),
                                db: AsyncSession = Depends(get_db),
                                _perm=Depends(personal_finance_access("报销管理"))):
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
                           db: AsyncSession = Depends(get_db),
                           _perm=Depends(personal_finance_access("报销管理"))):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    result = await db.execute(select(Reimbursement).where(Reimbursement.id == reimb_id))
    r = result.scalar_one_or_none()
    if not r: raise HTTPException(404, "报销单不存在")
    if current_user.role != Role.SUPER_ADMIN and r.warehouse_id not in get_wh_ids(current_user):
        raise HTTPException(403, "无权查看其他仓库的报销单")
    items = (await db.execute(select(ReimbursementItem).where(ReimbursementItem.reimbursement_id == reimb_id))).scalars().all()
    paid = (await payments.active_payment_map(db, [r])).get(r.id)
    advance_numbers = await cash_advance_numbers(db, [r])
    employee = await db.get(User, r.employee_id)
    return {
        "id": r.id, "warehouse_id": r.warehouse_id, "employee_id": r.employee_id,
        "employee_name": employee.display_name if employee else "",
        "is_fund_linked": r.is_fund_linked or "0", "fund_item_id": r.fund_item_id,
        "can_fund_pay": await reimbursement_payment_capability(db, current_user, r),
        "capabilities": await finance.reimbursement_capabilities(db,current_user,r),
        "submit_date": r.submit_date.isoformat() if r.submit_date else None,
        "total_amount": r.total_amount, "currency": r.currency, "status": r.status,
        "review_remark": r.review_remark, "paid_at": r.paid_at.isoformat() if r.paid_at else None,
        **payments.payment_fields(r, paid, can_revoke=current_user.role == Role.WAREHOUSE_ADMIN),
        **cash_advance_reference(r, advance_numbers),
        "items": [{"id": i.id, "category": i.category, "amount": i.amount,
                   "description": i.description, "receipt": i.receipt,
                   "review_status": i.review_status} for i in items],
    }

@router.put("/{reimb_id}", dependencies=[Depends(require_non_labor)])
async def edit_reimb(reimb_id: int, req: ReimbCreate, current_user: User = Depends(get_current_user),
                     db: AsyncSession = Depends(get_db),
                     _perm=Depends(personal_finance_access("报销管理"))):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    result = await db.execute(select(Reimbursement).where(Reimbursement.id == reimb_id).with_for_update())
    r = result.scalar_one_or_none()
    if not r: raise HTTPException(404, "报销单不存在")
    own_scope(current_user, r.warehouse_id)
    if current_user.role != Role.WAREHOUSE_ADMIN and r.employee_id not in await identities(db, current_user):
        raise HTTPException(403, '只能修改、删除或提交本人的报销申请')
    if current_user.role != Role.SUPER_ADMIN and r.warehouse_id not in get_wh_ids(current_user):
        raise HTTPException(403, "无权编辑其他仓库的报销单")
    if r.status != ReimbStatus.PENDING.value:
        raise HTTPException(400, "仅待审批状态可编辑")
    if r.is_fund_linked == '1':
        raise HTTPException(409, '关联备用金申请不能从普通编辑入口改变预留金额')
    await finance.evidence(db, current_user, r, 'reimb_verify', {'invalidated': True})
    old_items = (await db.execute(select(ReimbursementItem).where(ReimbursementItem.reimbursement_id == reimb_id))).scalars().all()
    before = {
        "total_amount": r.total_amount, "currency": r.currency,
        "submit_date": r.submit_date.isoformat() if r.submit_date else None,
        "items": [{"category": o.category, "amount": o.amount, "description": o.description} for o in old_items],
    }
    r.total_amount = sum(i.amount for i in req.items)
    # Delete old items and recreate
    for o in old_items: await db.delete(o)
    for item in req.items:
        db.add(ReimbursementItem(reimbursement_id=reimb_id, category=item.category,
                                 amount=item.amount, description=item.description, receipt=item.receipt))
    await db.flush()
    await record_history(db, module="reimbursement", record_id=r.id, operator=current_user,
                          operation_type="edit", before=before, after={
                              "total_amount": r.total_amount, "currency": req.currency,
                              "items": [{"category": i.category, "amount": i.amount, "description": i.description} for i in req.items],
                          }, warehouse_id=r.warehouse_id)
    return {"message": "更新成功"}

@router.delete("/{reimb_id}")
async def delete_reimb(reimb_id: int, current_user: User = Depends(get_current_user),
                       db: AsyncSession = Depends(get_db),
                       _perm=Depends(personal_finance_access("报销管理"))):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF):
        raise HTTPException(403, "无权限")
    result = await db.execute(select(Reimbursement).where(Reimbursement.id == reimb_id).with_for_update())
    r = result.scalar_one_or_none()
    if not r: raise HTTPException(404, "报销单不存在")
    own_scope(current_user, r.warehouse_id)
    if current_user.role != Role.WAREHOUSE_ADMIN and r.employee_id not in await identities(db, current_user):
        raise HTTPException(403, '只能修改、删除或提交本人的报销申请')
    if current_user.role != Role.SUPER_ADMIN and r.warehouse_id not in get_wh_ids(current_user):
        raise HTTPException(403, "无权限")
    if r.status not in ('pending', 'rejected', 'fund_linked'):
        raise HTTPException(409, '已批准申请不能直接删除，请先由管理员退回')
    if r.status == "paid": raise HTTPException(400, "已付款报销请先撤销付款")
    if (await db.execute(select(ReimbursementPayment.id).where(ReimbursementPayment.reimbursement_id == r.id).limit(1))).first():
        raise HTTPException(400, "有付款记录的报销单不能删除，请保留付款历史")

    wh_id = r.warehouse_id
    before = {
        "total_amount": r.total_amount, "currency": r.currency,
        "submit_date": r.submit_date.isoformat() if r.submit_date else None,
        "status": r.status, "is_fund_linked": r.is_fund_linked,
    }

    # 处理备用金关联：恢复余额 + 删除关联的备用金开销记录
    if r.is_fund_linked == "1" and r.fund_item_id:
        fund_item = (await db.execute(
            select(ExpenseFundItem).where(ExpenseFundItem.id == r.fund_item_id)
        )).scalar_one_or_none()
        if fund_item:
            fund = (await db.execute(
                select(ExpenseFund).where(ExpenseFund.id == fund_item.fund_id)
            )).scalar_one_or_none()
            if fund:
                fund.remaining_balance = (fund.remaining_balance or 0) + (r.total_amount or 0)
            await db.delete(fund_item)

    # 删除报销明细 + 报销单
    items = (await db.execute(
        select(ReimbursementItem).where(ReimbursementItem.reimbursement_id == reimb_id)
    )).scalars().all()
    for it in items:
        await db.delete(it)
    await db.delete(r)
    await db.flush()

    await record_history(db, module="reimbursement", record_id=reimb_id, operator=current_user,
                          operation_type="delete", before=before, warehouse_id=wh_id)
    return {"message": "删除成功"}

@router.post("/{reimb_id}/submit", dependencies=[Depends(require_non_labor)])
async def submit_reimb(reimb_id: int, current_user: User = Depends(get_current_user),
                       db: AsyncSession = Depends(get_db),
                       _perm=Depends(personal_finance_access("报销管理"))):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    result = await db.execute(select(Reimbursement).where(Reimbursement.id == reimb_id).with_for_update())
    r = result.scalar_one_or_none()
    if not r: raise HTTPException(404, "报销单不存在")
    own_scope(current_user, r.warehouse_id)
    if current_user.role != Role.WAREHOUSE_ADMIN and r.employee_id not in await identities(db, current_user):
        raise HTTPException(403, '只能修改、删除或提交本人的报销申请')
    if current_user.role != Role.SUPER_ADMIN and r.warehouse_id not in get_wh_ids(current_user):
        raise HTTPException(403, "无权操作其他仓库的报销单")
    if r.status == "paid" or await payments.active_payment_map(db, [r]):
        raise HTTPException(400, "已付款报销请先撤销付款")
    if r.status not in ('pending', 'rejected') or r.is_fund_linked == '1':
        raise HTTPException(409, '已批准或关联备用金的申请须由管理员明确退回重审')
    await finance.evidence(db, current_user, r, 'reimb_verify', {'invalidated': True})
    r.status = ReimbStatus.PENDING.value
    await db.flush(); return {"message": "已提交审批"}

@router.post("/{reimb_id}/verify")
async def verify_reimb(reimb_id: int, current_user: User = Depends(personal_finance_access("报销管理")), db: AsyncSession = Depends(get_db)):
    finance.accountant(current_user)
    r = await _payment_reimb(db, reimb_id, current_user, lock=True)
    own_scope(current_user, r.warehouse_id)
    await finance.independent(db, current_user, r.employee_id)
    if r.is_fund_linked == '1':
        raise HTTPException(409, '关联备用金请从备用金凭证核验入口办理')
    if r.status != 'pending':raise HTTPException(409, '只能核验待处理的报销')
    await finance.evidence(db, current_user, r, 'reimb_verify', await finance.reimb_payload(db, r))
    return {'message': '凭证已核验，等待管理员批准，尚未付款'}

@router.post("/{reimb_id}/return-to-draft")
async def return_reimb(reimb_id: int, current_user: User = Depends(personal_finance_access("报销管理")), db: AsyncSession = Depends(get_db)):
    finance.approver(current_user)
    r = await _payment_reimb(db, reimb_id, current_user, lock=True)
    own_scope(current_user, r.warehouse_id)
    if r.is_fund_linked == '1':raise HTTPException(409, '备用金预留不能从此入口退回')
    if r.status not in ('approved', 'partially_approved', 'rejected') or await payments.active_payment_map(db,[r]):
        raise HTTPException(409, '只有未付款的已审核报销可以退回')
    items=(await db.execute(select(ReimbursementItem).where(ReimbursementItem.reimbursement_id==r.id).with_for_update())).scalars().all()
    for item in items:item.review_status='pending'
    r.total_amount=sum(item.amount for item in items)
    r.status='pending';r.reviewer_id=None
    await finance.evidence(db,current_user,r,'reimb_verify',{'invalidated':True})
    await finance.evidence(db,current_user,r,'reimb_approve',{'invalidated':True})
    return {'message':'已退回，必须重新核验和批准'}

@router.post("/{reimb_id}/review", dependencies=[Depends(mutation_scope)])
async def review_reimb(reimb_id: int, req: ReimbReview, current_user: User = Depends(get_current_user),
                       db: AsyncSession = Depends(get_db),
                       _perm=Depends(personal_finance_access("报销管理"))):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if current_user.role not in (Role.SUPER_ADMIN, Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF):
        raise HTTPException(403, "无审批权限")
    finance.approver(current_user)
    result = await db.execute(select(Reimbursement).where(Reimbursement.id == reimb_id).with_for_update())
    r = result.scalar_one_or_none()
    if not r: raise HTTPException(404, "报销单不存在")
    if r.warehouse_id not in get_wh_ids(current_user):
        raise HTTPException(403, "只能审批本仓库的报销单")
    # 普通报销保留原再审规则；关联备用金还必须满足下方核验守卫，已批准快照不可改审。
    from app.services.flow_rules import is_reviewable_reimb, can_refund_fund_item
    if not is_reviewable_reimb(r.status):
        raise HTTPException(400, f"当前状态（{r.status}）不可审批")
    own_scope(current_user, r.warehouse_id)
    if not req.items:
        raise HTTPException(400, "请选择待审核明细")
    decisions = {}
    for entry in req.items:
        item_id = entry.get("item_id")
        status = entry.get("status")
        if type(item_id) is not int or item_id in decisions or status not in ("approved", "rejected"):
            raise HTTPException(400, "审核明细编号重复或审核状态无效")
        decisions[item_id] = status
    items = (await db.execute(select(ReimbursementItem).where(
        ReimbursementItem.reimbursement_id == r.id).order_by(ReimbursementItem.id).with_for_update())).scalars().all()
    by_id = {item.id: item for item in items}
    if any(item_id not in by_id or by_id[item_id].review_status not in ("pending", "approved", "rejected") for item_id in decisions):
        raise HTTPException(400, "审核明细不存在、不属于当前报销单或状态不合法")
    if r.is_fund_linked == "1" and r.fund_item_id:
        linked = (await db.execute(select(ExpenseFundItem, ExpenseFund).join(
            ExpenseFund, ExpenseFundItem.fund_id == ExpenseFund.id).where(
            ExpenseFundItem.id == r.fund_item_id).with_for_update())).first()
        if not linked or linked[1].warehouse_id != r.warehouse_id or linked[1].employee_id != r.employee_id:
            raise HTTPException(400, "关联备用金归属不合法")
        from app.core.round2_access import require_account_manager
        from app.services import fund_authorization as duties
        require_account_manager(current_user)
        await duties.independent(db, current_user, r.employee_id, linked[1].employee_id)
        if linked[0].review_status != 'verified':
            raise HTTPException(409, '请先完成关联备用金凭证核验')
        await duties.proof(db, linked[0], 'item_verify', await duties.item_review_payload(db, *linked), r.warehouse_id)
        if any(decisions.get(item.id, item.review_status) not in ('approved', 'rejected') for item in items):
            raise HTTPException(400, '关联备用金报销必须明确决定全部明细后才能批准')
        from decimal import Decimal
        if (not duties.same_payment_amount(sum(Decimal(str(item.amount)) for item in items), linked[0].amount)
                or r.currency != linked[0].currency):
            raise HTTPException(409, '报销明细金额或币种与备用金记录不一致')

    if r.is_fund_linked != '1':
        if r.status != 'pending':
            raise HTTPException(409, '请先由管理员退回重审')
        await finance.independent(db, current_user, r.employee_id)
        await finance.proof(db, r, 'reimb_verify', await finance.reimb_payload(db, r))
        if any(decisions.get(item.id, item.review_status) not in ('approved', 'rejected') for item in items):
            raise HTTPException(400, '请明确决定全部报销明细')

    r.reviewer_id = current_user.id
    r.review_remark = req.overall_remark
    for item_id, status in decisions.items():
        by_id[item_id].review_status = status
    approved_count = sum(item.review_status == "approved" for item in items)
    rejected_count = sum(item.review_status != "approved" for item in items)
    approved_amount = sum(item.amount for item in items if item.review_status == "approved")

    if rejected_count == 0:
        r.status = ReimbStatus.APPROVED.value
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
    if r.is_fund_linked == '1' and r.fund_item_id and approved_count > 0:
        linked[0].review_status = ReviewStatus.APPROVED.value
        await db.flush()
        await duties.evidence(db, current_user, linked[0], 'item_approve',
            await duties.item_review_payload(db, *linked), r.warehouse_id)
    if r.is_fund_linked != '1' and approved_count > 0:
        await db.flush()
        await finance.evidence(db, current_user, r, 'reimb_approve', await finance.reimb_payload(db, r))
    await db.flush(); return {"message": "审批完成", "status": r.status, "approved_amount": approved_amount}

@router.post("/{reimb_id}/pay", dependencies=[Depends(mutation_scope)])
async def pay_reimb(reimb_id: int, req: ReimbPay | None = None, current_user: User = Depends(get_current_user),
                    db: AsyncSession = Depends(get_db),
                    _perm=Depends(personal_finance_access("报销管理"))):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF):
        raise HTTPException(403, "无权限")
    r = await _payment_reimb(db, reimb_id, current_user, lock=True)
    own_scope(current_user, r.warehouse_id)
    return await payments.pay(db, r, req or ReimbPay(), current_user)

@router.get("/{reimb_id}/payments")
async def payment_history(reimb_id: int, current_user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db), _perm=Depends(personal_finance_access("报销管理"))):
    r = await _payment_reimb(db, reimb_id, current_user)
    rows = (await db.execute(select(ReimbursementPayment).where(
        ReimbursementPayment.reimbursement_id == r.id, ReimbursementPayment.warehouse_id == r.warehouse_id,
    ).order_by(ReimbursementPayment.id.desc()))).scalars().all()
    advance_numbers = await cash_advance_numbers(db, rows)
    return {"data": [{**payments.payment_dict(p), **cash_advance_reference(p, advance_numbers), "can_revoke": p.status == "active" and current_user.role == Role.WAREHOUSE_ADMIN} for p in rows],
        "total": len(rows), "status": r.status, "is_legacy_payment": r.status == "paid" and not rows}

@router.post("/{reimb_id}/revoke-payment", dependencies=[Depends(reject_disabled_financial_reversal)])
async def revoke_payment(reimb_id: int, req: RevokePayment | None = None, current_user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db), _perm=Depends(personal_finance_access("报销管理"))):
    if current_user.role != Role.WAREHOUSE_ADMIN: raise HTTPException(403, "只有仓库管理员可以撤销报销付款")
    reason = ((req.reason if req else None) or "").strip()
    if not reason: raise HTTPException(400, "请填写撤销原因")
    r = await _payment_reimb(db, reimb_id, current_user, lock=True)
    return await payments.revoke(db, r, current_user, reason)


# === Reimbursement Categories ===
@router.post("/categories")
async def create_reimb_category(req: CategoryReq, current_user: User = Depends(get_current_user),
                                db: AsyncSession = Depends(get_db),
                                _perm=Depends(personal_finance_access("报销管理"))):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF):
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

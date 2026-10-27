from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.models.expense_approval import ExpenseApproval
from app.models.income_expense import ExpenseRecord, IncomeExpenseCategory
from app.models.customer import PaymentAccount
from app.models.expense_fund import SystemSetting, ExpenseFund, ExpenseFundItem, ReviewStatus
from app.models.user import User
from app.core.permissions import get_wh_id, get_wh_ids, Role, check_staff_permission_any, check_staff_permission
from app.core.menu_registry import MENU_PERMISSIONS_BY_KEY
from app.core.config_access import ensure_config_editor
from app.core.timezone import thai_now, thai_today, THAI_TZ
from pydantic import BaseModel, Field
from datetime import datetime, date
from decimal import Decimal
from typing import Optional
import base64, os, uuid
from app.schemas.cost_identity import CostFields
from app.services import cost_identity as costs

router = APIRouter()

PAYMENT_METHODS = ("alipay", "wechat", "bank_transfer", "company_account", "cash")
FUND_SOURCES = ("fund", "company")
THRESHOLD_KEY = "expense_approval_threshold"
EXEMPT_NOTE = "金额未超过审批门槛，免审批，待付款"
expense_user = check_staff_permission(MENU_PERMISSIONS_BY_KEY["expense_approval"].label)


def _check_submit_role(current_user: User):
    """提申请：管理员/主管/财务；超级管理员拒绝。"""
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF):
        raise HTTPException(403, "无权限")


def _check_manage_role(current_user: User):
    """审批操作（审批/驳回/付款）：仅仓库管理员。"""
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if current_user.role != Role.WAREHOUSE_ADMIN:
        raise HTTPException(403, "只有仓库管理员可以审批")


async def _get_threshold(db: AsyncSession, wh_id: int) -> float:
    row = (await db.execute(
        select(SystemSetting).where(SystemSetting.warehouse_id == wh_id, SystemSetting.key == THRESHOLD_KEY)
    )).scalar_one_or_none()
    try:
        return float(row.value) if row else 0.0
    except (ValueError, TypeError):
        return 0.0


class ApprovalCreate(CostFields):
    payment_account_id: Optional[int] = None
    amount: float = Field(gt=0)
    currency: str = "THB"
    purpose: str
    expense_date: str  # YYYY-MM-DD
    payment_method: str = "cash"
    fund_source: str = "company"
    voucher_base64: Optional[str] = None  # 凭证照片 base64（可选）


class ApprovalUpdate(CostFields):
    payment_account_id: Optional[int] = None
    amount: Optional[float] = None
    currency: Optional[str] = None
    purpose: Optional[str] = None
    expense_date: Optional[str] = None
    payment_method: Optional[str] = None
    fund_source: Optional[str] = None
    voucher_base64: Optional[str] = None


class ThresholdSet(BaseModel):
    threshold: float


class RejectRequest(BaseModel):
    note: Optional[str] = None


class PayRequest(BaseModel):
    cost_confirmation: Optional[dict] = None
    payment_account_id: Optional[int] = None
    voucher_base64: Optional[str] = None  # 付款凭证照片 base64（可选）


def _save_voucher(wh_id, data_url: str) -> Optional[str]:
    try:
        header, b64 = (data_url.split(",", 1) if "," in data_url else ("", data_url))
        img = base64.b64decode(b64)
        from app.services.image_utils import save_image
        upload_dir = os.environ.get("UPLOAD_DIR", "/app/uploads")
        today = thai_today().isoformat()
        abs_subdir = os.path.join(upload_dir, str(wh_id), today, "approvals")
        rel_subdir = f"uploads/{wh_id}/{today}/approvals"
        fname = f"{uuid.uuid4().hex}.jpg"
        result = save_image(img, abs_subdir, rel_subdir, fname)
        return result["path"]
    except Exception:
        return None


async def _generate_operating_expense(db: AsyncSession, appr: ExpenseApproval):
    """实际公司付款才生成支出；余额和流水统一由这条付款事实投影。"""
    if appr.fund_source == "fund":
        return  # 已在备用金拨付时计过公司支出
    from app.services.wallet import lock_account, positive_money
    from app.services.account_balances import current_account_balances
    account = await lock_account(db, appr.warehouse_id, appr.payment_account_id, appr.currency or "THB")
    value = positive_money(appr.amount)
    from app.services.balance_warning import balance_warning
    warning=balance_warning((await current_account_balances(db,[account]))[account.id],value,appr.currency or 'THB',source='company_account',source_id=account.id)
    # 找运营支出类别，没有则建一个
    cat = (await db.execute(
        select(IncomeExpenseCategory).where(
            IncomeExpenseCategory.warehouse_id == appr.warehouse_id,
            IncomeExpenseCategory.type == "expense",
            IncomeExpenseCategory.category_group == "operating",
            IncomeExpenseCategory.name == "运营支出",
        ).order_by(IncomeExpenseCategory.id.asc())
    )).scalars().first()
    if not cat:
        cat = IncomeExpenseCategory(warehouse_id=appr.warehouse_id, type="expense", name="运营支出", category_group="operating", sort_order=0)
        db.add(cat)
        await db.flush()

    expense = ExpenseRecord(
        warehouse_id=appr.warehouse_id,
        category_id=cat.id,
        account_id=account.id,
        amount=appr.amount,
        currency=appr.currency or "THB",
        expense_date=appr.paid_at.replace(tzinfo=None),
        voucher=appr.payment_voucher,
        remark=f"[费用审批#{appr.id}] {appr.purpose}",
    )
    db.add(expense)
    await db.flush()
    await costs.link_child(db,appr,expense)
    appr.expense_record_id = expense.id
    return warning


async def _link_fund(db: AsyncSession, appr: ExpenseApproval):
    """资金来源选备用金：付款后在备用金账户记一笔开销（无需二次审核）。"""
    if appr.fund_source != "fund":
        return
    fund = (await db.execute(
        select(ExpenseFund).where(
            ExpenseFund.warehouse_id == appr.warehouse_id,
            ExpenseFund.status == "active",
            func.coalesce(ExpenseFund.currency, "THB") == (appr.currency or "THB"),
        ).order_by(ExpenseFund.id.asc()).with_for_update().execution_options(populate_existing=True)
    )).scalars().first()
    if not fund:
        raise HTTPException(400, "没有可用的同币种备用金")
    from app.services.employee_advance_funding import fund_available_amount
    from app.services.balance_warning import balance_warning
    warning=balance_warning(await fund_available_amount(db,fund),appr.amount,appr.currency or 'THB',source='expense_fund',source_id=fund.id)
    item = ExpenseFundItem(
        fund_id=fund.id,
        expense_date=thai_now().replace(tzinfo=None),
        category="费用支出",
        amount=appr.amount,
        currency=appr.currency or "THB",
        description=appr.purpose,
        receipt=appr.payment_voucher,
        review_status=ReviewStatus.APPROVED.value, cost_record_only=True,
    )
    db.add(item)
    await db.flush()
    await costs.link_child(db,appr,item)
    appr.fund_item_id = item.id
    return warning


def _payment_result(a: ExpenseApproval, *, already_paid=False):
    paid_at = (a.paid_at.replace(tzinfo=THAI_TZ) if a.paid_at and a.paid_at.tzinfo is None else a.paid_at)
    return {"id": a.id, "status": a.status, "message": "该申请已付款，请勿重复付款" if already_paid else "已付款",
        "already_paid": already_paid, "payer_id": a.payer_id,
        "paid_at": paid_at.astimezone(THAI_TZ).isoformat() if paid_at else None,
        "payment_account_id": a.payment_account_id, "expense_record_id": a.expense_record_id,
        "fund_item_id": a.fund_item_id, "payment_voucher": a.payment_voucher,
        "ledger_ref_no": f"EX-{a.expense_record_id}" if a.expense_record_id else None}


@router.post("")
async def create_approval(
    req: ApprovalCreate,
    current_user: User = Depends(expense_user),
    db: AsyncSession = Depends(get_db),
):
    _check_submit_role(current_user)
    wh_id = get_wh_id(current_user)
    if not wh_id:
        raise HTTPException(400, "请先选择仓库")

    from app.services.wallet import positive_money
    positive_money(req.amount)
    purpose = (req.purpose or "").strip()
    if not purpose:
        raise HTTPException(400, "请填写用途说明")
    if req.payment_method not in PAYMENT_METHODS:
        raise HTTPException(400, "付款方式无效")
    if req.fund_source not in FUND_SOURCES:
        raise HTTPException(400, "资金来源无效")
    try:
        exp_dt = datetime.strptime(req.expense_date, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        raise HTTPException(400, "费用日期格式错误 YYYY-MM-DD")

    costs.number(req.request_key,'登记请求编号',100)
    await costs.lock(db,wh_id)
    signature=costs.fingerprint(req.model_dump(exclude={'cost_confirmation'}))
    previous=await costs.replay(db,'approval',wh_id,req.request_key,signature)
    if previous:return {'id':previous.id,'status':previous.status,'replayed':True,'message':'原费用申请已保存，未重复新增',**await costs.metadata_for(db,previous)}
    identity=costs.parse_identity(req.invoice_identity,current_user)
    if req.fund_source == "company" and req.payment_account_id is not None:
        from app.services.wallet import lock_account
        await lock_account(db, wh_id, req.payment_account_id, req.currency or "THB")
    voucher_path = _save_voucher(wh_id, req.voucher_base64) if req.voucher_base64 else None

    threshold = await _get_threshold(db, wh_id)
    # 免审批只进入待付款，不代表钱已经付出。
    status = "pending" if req.amount > threshold else "approved"

    a = ExpenseApproval(
        warehouse_id=wh_id,
        applicant_id=current_user.id,
        amount=req.amount,
        currency=req.currency or "THB",
        purpose=purpose,
        expense_date=exp_dt,
        voucher_path=voucher_path,
        payment_method=req.payment_method,
        fund_source=req.fund_source, payment_account_id=req.payment_account_id if req.fund_source == "company" else None,
        status=status,
        approval_note=EXEMPT_NOTE if status == "approved" else None,
    )
    db.add(a)
    await db.flush()
    root=await costs.sync(db,'approval',a,current_user,supplier=req.supplier_id,identity=identity,
        confirmation=req.cost_confirmation,key=req.request_key,signature=signature)

    return {"id": a.id, "status": status, "message": "费用已提交，等待审批" if status == "pending" else "免审批，等待确认付款",**costs.metadata(root)}


@router.get("")
async def list_approvals(
    status: Optional[str] = None,
    current_user: User = Depends(expense_user),
    db: AsyncSession = Depends(get_db),
):
    _check_submit_role(current_user)
    wh_ids = get_wh_ids(current_user)
    if not wh_ids:
        return {"data": [], "total": 0}

    q = select(ExpenseApproval).where(ExpenseApproval.warehouse_id.in_(wh_ids))
    if status and status != "all":
        q = q.where(ExpenseApproval.status == status)

    rows = (await db.execute(q.order_by(ExpenseApproval.created_at.desc(), ExpenseApproval.id.desc()))).scalars().all()

    applicant_ids = {r.applicant_id for r in rows}
    approver_ids = {r.approver_id for r in rows if r.approver_id}
    payer_ids = {r.payer_id for r in rows if r.payer_id}
    user_map = {}
    uids = applicant_ids | approver_ids | payer_ids
    if uids:
        us = (await db.execute(select(User).where(User.id.in_(uids)))).scalars().all()
        user_map = {u.id: u.display_name for u in us}

    return {
        "data": [{
            **await costs.metadata_for(db,r),
            "id": r.id,
            "warehouse_id": r.warehouse_id,
            "applicant_id": r.applicant_id,
            "applicant_name": user_map.get(r.applicant_id, ""),
            "amount": r.amount,
            "currency": r.currency or "THB",
            "purpose": r.purpose,
            "expense_date": r.expense_date.isoformat(),
            "voucher_path": r.voucher_path,
            "payment_method": r.payment_method,
            "fund_source": r.fund_source, "payment_account_id": r.payment_account_id, "expense_record_id": r.expense_record_id,
            "fund_item_id": r.fund_item_id,
            "status": r.status,
            "approver_id": r.approver_id,
            "approver_name": user_map.get(r.approver_id, ""),
            "approved_at": r.approved_at.isoformat() if r.approved_at else None,
            "approval_note": r.approval_note,
            "payer_id": r.payer_id, "payer_name": user_map.get(r.payer_id, ""),
            "paid_at": r.paid_at.isoformat() if r.paid_at else None,
            "payment_voucher": r.payment_voucher,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        } for r in rows],
        "total": len(rows),
    }


@router.get("/summary")
async def approval_summary(
    current_user: User = Depends(expense_user),
    db: AsyncSession = Depends(get_db),
):
    """页面看板：待审批笔数 / 已批准待付款笔数 / 本月已付款金额按币种。"""
    _check_submit_role(current_user)
    wh_id = get_wh_id(current_user)
    if not wh_id:
        return {"pending_count": 0, "approved_count": 0, "paid_by_currency": []}

    pending_count = int((await db.execute(
        select(func.count(ExpenseApproval.id)).where(ExpenseApproval.warehouse_id == wh_id, ExpenseApproval.status == "pending")
    )).scalar() or 0)
    approved_count = int((await db.execute(
        select(func.count(ExpenseApproval.id)).where(ExpenseApproval.warehouse_id == wh_id, ExpenseApproval.status == "approved")
    )).scalar() or 0)

    month_start = datetime.combine(thai_today().replace(day=1), datetime.min.time())
    paid_rows = (await db.execute(
        select(ExpenseApproval.currency, func.sum(ExpenseApproval.amount))
        .where(ExpenseApproval.warehouse_id == wh_id, ExpenseApproval.status == "paid", ExpenseApproval.paid_at >= month_start)
        .group_by(ExpenseApproval.currency)
    )).all()

    return {
        "pending_count": pending_count,
        "approved_count": approved_count,
        "paid_by_currency": [{"currency": c or "THB", "amount": round(a or 0, 2)} for c, a in paid_rows],
    }


@router.get("/threshold")
async def get_threshold(
    current_user: User = Depends(check_staff_permission_any(MENU_PERMISSIONS_BY_KEY["config_center"].label, MENU_PERMISSIONS_BY_KEY["expense_approval"].label)),
    db: AsyncSession = Depends(get_db),
):
    _check_submit_role(current_user)
    wh_id = get_wh_id(current_user)
    if not wh_id:
        return {"threshold": 0}
    return {"threshold": await _get_threshold(db, wh_id), "warehouse_id": wh_id}


@router.put("/threshold")
async def set_threshold(
    req: ThresholdSet,
    current_user: User = Depends(check_staff_permission(MENU_PERMISSIONS_BY_KEY["config_center"].label)),
    db: AsyncSession = Depends(get_db),
):
    ensure_config_editor(current_user)
    wh_id = get_wh_id(current_user)
    if not wh_id:
        raise HTTPException(400, "请先选择仓库")
    if req.threshold < 0:
        raise HTTPException(400, "门槛不能为负数")

    row = (await db.execute(
        select(SystemSetting).where(SystemSetting.warehouse_id == wh_id, SystemSetting.key == THRESHOLD_KEY)
    )).scalar_one_or_none()
    if row:
        row.value = str(req.threshold)
        row.updated_by = current_user.id
        row.updated_at = thai_now()
    else:
        db.add(SystemSetting(warehouse_id=wh_id, key=THRESHOLD_KEY, value=str(req.threshold), updated_by=current_user.id))
    await db.flush()
    return {"message": f"审批门槛已设为 {req.threshold}", "threshold": req.threshold}


@router.put("/{approval_id}")
async def update_approval(
    approval_id: int,
    req: ApprovalUpdate,
    current_user: User = Depends(expense_user),
    db: AsyncSession = Depends(get_db),
):
    """申请人修改（待审批/已驳回），改完重新提交 → 状态回到待审批。"""
    _check_submit_role(current_user)
    wh_id = get_wh_id(current_user)
    if not wh_id:
        raise HTTPException(400, "请先选择仓库")

    await costs.lock(db,wh_id)
    a = (await db.execute(
        select(ExpenseApproval).where(ExpenseApproval.id == approval_id, ExpenseApproval.warehouse_id == wh_id)
        .with_for_update().execution_options(populate_existing=True)
    )).scalar_one_or_none()
    if not a:
        raise HTTPException(404, "费用申请不存在")
    if a.applicant_id != current_user.id and current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
        raise HTTPException(403, "只能修改自己的申请")
    if a.status not in ("pending", "rejected"):
        raise HTTPException(400, "当前状态不能修改")

    if req.amount is not None:
        if req.amount <= 0:
            raise HTTPException(400, "金额必须大于0")
        a.amount = req.amount
    if req.currency is not None:
        a.currency = req.currency
    if req.purpose is not None:
        p = (req.purpose or "").strip()
        if not p:
            raise HTTPException(400, "请填写用途说明")
        a.purpose = p
    if req.expense_date is not None:
        try:
            a.expense_date = datetime.strptime(req.expense_date, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            raise HTTPException(400, "费用日期格式错误 YYYY-MM-DD")
    if req.payment_method is not None:
        if req.payment_method not in PAYMENT_METHODS:
            raise HTTPException(400, "付款方式无效")
        a.payment_method = req.payment_method
    if req.fund_source is not None:
        if req.fund_source not in FUND_SOURCES:
            raise HTTPException(400, "资金来源无效")
        a.fund_source = req.fund_source
    if req.payment_account_id is not None:
        from app.services.wallet import lock_account
        await lock_account(db, wh_id, req.payment_account_id, a.currency or "THB")
        a.payment_account_id = req.payment_account_id
    if a.fund_source == "fund": a.payment_account_id = None
    if req.voucher_base64 is not None:
        p = _save_voucher(wh_id, req.voucher_base64)
        if p:
            a.voucher_path = p

    # 重新提交 → 待审批
    a.status = "pending"
    a.approver_id = None
    a.approved_at = None
    a.approval_note = None
    await costs.sync(db,'approval',a,current_user,
        supplier=req.supplier_id if 'supplier_id' in req.model_fields_set else costs.UNSET,
        identity=costs.parse_identity(req.invoice_identity,current_user) if 'invoice_identity' in req.model_fields_set else costs.UNSET,
        confirmation=req.cost_confirmation)
    await db.flush()
    return {"id": a.id, "message": "已重新提交，等待审批"}


@router.post("/{approval_id}/approve")
async def approve_approval(
    approval_id: int,
    current_user: User = Depends(expense_user),
    db: AsyncSession = Depends(get_db),
):
    _check_manage_role(current_user)
    wh_id = get_wh_id(current_user)
    if not wh_id:
        raise HTTPException(400, "请先选择仓库")
    await costs.lock(db,wh_id)
    a = (await db.execute(
        select(ExpenseApproval).where(ExpenseApproval.id == approval_id, ExpenseApproval.warehouse_id == wh_id)
        .with_for_update().execution_options(populate_existing=True)
    )).scalar_one_or_none()
    if not a:
        raise HTTPException(404, "费用申请不存在")
    if a.status != "pending":
        raise HTTPException(400, "只有待审批的申请可以批准")
    a.status = "approved"
    a.approver_id = current_user.id
    a.approved_at = thai_now()
    await costs.sync(db,'approval',a,current_user)
    await db.flush()
    return {"id": a.id, "message": "已批准"}


@router.post("/{approval_id}/reject")
async def reject_approval(
    approval_id: int,
    req: RejectRequest,
    current_user: User = Depends(expense_user),
    db: AsyncSession = Depends(get_db),
):
    _check_manage_role(current_user)
    wh_id = get_wh_id(current_user)
    if not wh_id:
        raise HTTPException(400, "请先选择仓库")
    await costs.lock(db,wh_id)
    a = (await db.execute(
        select(ExpenseApproval).where(ExpenseApproval.id == approval_id, ExpenseApproval.warehouse_id == wh_id)
        .with_for_update().execution_options(populate_existing=True)
    )).scalar_one_or_none()
    if not a:
        raise HTTPException(404, "费用申请不存在")
    if a.status != "pending":
        raise HTTPException(400, "只有待审批的申请可以驳回")
    a.status = "rejected"
    a.approver_id = current_user.id
    a.approved_at = thai_now()
    a.approval_note = req.note
    await costs.sync(db,'approval',a,current_user)
    await db.flush()
    return {"id": a.id, "message": "已驳回"}


@router.get("/{approval_id}/payment-preview")
async def payment_preview(approval_id:int,payment_account_id:int=None,current_user:User=Depends(expense_user),db:AsyncSession=Depends(get_db)):
    _check_manage_role(current_user)
    wid=get_wh_id(current_user)
    a=(await db.execute(select(ExpenseApproval).where(ExpenseApproval.id==approval_id,ExpenseApproval.warehouse_id==wid))).scalar_one_or_none()
    if a is None: raise HTTPException(404,"费用申请不存在")
    from app.services.balance_warning import balance_warning
    if a.fund_source=='company':
        from app.services.wallet import read_account
        from app.services.account_balances import current_account_balances
        source=await read_account(db,wid,payment_account_id,a.currency or 'THB')
        balance=(await current_account_balances(db,[source]))[source.id]
        kind='company_account'
    else:
        source=(await db.execute(select(ExpenseFund).where(ExpenseFund.warehouse_id==wid,ExpenseFund.status=='active',
            func.coalesce(ExpenseFund.currency,'THB')==(a.currency or 'THB')).order_by(ExpenseFund.id).limit(1))).scalar_one_or_none()
        if source is None:raise HTTPException(400,"没有可用的同币种备用金")
        from app.services.employee_advance_funding import fund_available_amount
        balance=await fund_available_amount(db,source);kind='expense_fund'
    return {'balance':float(balance),'amount':a.amount,'currency':a.currency,'warning':balance_warning(balance,a.amount,a.currency or 'THB',source=kind,source_id=source.id)}


@router.post("/{approval_id}/pay")
async def pay_approval(
    approval_id: int,
    req: PayRequest = PayRequest(),
    current_user: User = Depends(expense_user),
    db: AsyncSession = Depends(get_db),
):
    _check_manage_role(current_user)
    wh_id = get_wh_id(current_user)
    if not wh_id:
        raise HTTPException(400, "请先选择仓库")
    await costs.lock(db,wh_id)
    a = (await db.execute(
        select(ExpenseApproval).where(ExpenseApproval.id == approval_id, ExpenseApproval.warehouse_id == wh_id).with_for_update().execution_options(populate_existing=True)
    )).scalar_one_or_none()
    if not a:
        raise HTTPException(404, "费用申请不存在")
    if a.status == "paid":
        if req.payment_account_id is not None and req.payment_account_id != a.payment_account_id:
            raise HTTPException(409, "该申请已付款，不能更换付款账户")
        from app.services.balance_warning import saved_balance_warning
        return {'warning':await saved_balance_warning(db,module='expense_approval',record_id=a.id),**_payment_result(a,already_paid=True)}
    if a.status != "approved":
        raise HTTPException(400, "只有已批准的申请可以付款")
    if a.expense_record_id is not None or a.fund_item_id is not None:
        raise HTTPException(400, "该申请已有记账记录，请先核对")
    if a.fund_source == "company" and not req.payment_account_id:
        raise HTTPException(400, "请选择付款账户")
    if a.fund_source == "fund" and req.payment_account_id is not None:
        raise HTTPException(400, "备用金付款不应选择公司账户")

    # 付款凭证必填
    if not req.voucher_base64:
        raise HTTPException(400, "请上传付款凭证")
    p = _save_voucher(wh_id, req.voucher_base64)
    if not p:
        raise HTTPException(400, "请上传付款凭证")
    a.payment_voucher = p
    a.payment_account_id = req.payment_account_id

    a.status = "paid"
    a.payer_id = current_user.id
    a.paid_at = thai_now()
    await costs.sync(db,'approval',a,current_user,confirmation=req.cost_confirmation)
    await db.flush()

    # 付款后自动生成运营支出 + 备用金联动
    company_warning=await _generate_operating_expense(db, a)
    fund_warning=await _link_fund(db, a)
    warning=company_warning or fund_warning
    await db.flush()
    from app.services.data_history import record_history
    await record_history(db, module="expense_approval", record_id=a.id, operator=current_user,
        operation_type="pay", after={**_payment_result(a), "amount": a.amount,
            "currency": a.currency, "fund_source": a.fund_source}, warehouse_id=wh_id)
    from app.services.balance_warning import record_balance_warning
    await record_balance_warning(db,warning,current_user,module='expense_approval',record_id=a.id,warehouse_id=wh_id)
    return {'warning':warning,**_payment_result(a)}

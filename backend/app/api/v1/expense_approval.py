from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.models.expense_approval import ExpenseApproval
from app.models.income_expense import ExpenseRecord, IncomeExpenseCategory
from app.models.customer import PaymentAccount
from app.models.expense_fund import SystemSetting
from app.models.user import User
from app.core.permissions import get_current_user, get_wh_id, get_wh_ids, Role
from app.core.timezone import thai_now, thai_today
from pydantic import BaseModel, Field
from datetime import datetime, date
from typing import Optional
import base64, os, uuid

router = APIRouter()

PAYMENT_METHODS = ("alipay", "wechat", "bank_transfer", "company_account", "cash")
FUND_SOURCES = ("fund", "company")
THRESHOLD_KEY = "expense_approval_threshold"


def _check_submit_role(current_user: User):
    """提申请：管理员/主管/财务；超级管理员拒绝。"""
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF):
        raise HTTPException(403, "无权限")


def _check_manage_role(current_user: User):
    """审批操作（改门槛/审批/驳回/付款）：仅仓库管理员/主管。"""
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
        raise HTTPException(403, "无权限")


async def _get_threshold(db: AsyncSession, wh_id: int) -> float:
    row = (await db.execute(
        select(SystemSetting).where(SystemSetting.warehouse_id == wh_id, SystemSetting.key == THRESHOLD_KEY)
    )).scalar_one_or_none()
    try:
        return float(row.value) if row else 0.0
    except (ValueError, TypeError):
        return 0.0


class ApprovalCreate(BaseModel):
    amount: float = Field(gt=0)
    currency: str = "THB"
    purpose: str
    expense_date: str  # YYYY-MM-DD
    payment_method: str = "cash"
    fund_source: str = "company"
    voucher_base64: Optional[str] = None  # 凭证照片 base64（可选）


class ApprovalUpdate(BaseModel):
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


def _save_voucher(wh_id, data_url: str) -> Optional[str]:
    try:
        header, b64 = (data_url.split(",", 1) if "," in data_url else ("", data_url))
        img = base64.b64decode(b64)
        from app.services.image_utils import save_image
        today = thai_today().isoformat()
        abs_subdir = os.path.join("/app/uploads", str(wh_id), today, "approvals")
        rel_subdir = f"uploads/{wh_id}/{today}/approvals"
        fname = f"{uuid.uuid4().hex}.jpg"
        result = save_image(img, abs_subdir, rel_subdir, fname)
        return result["path"]
    except Exception:
        return None


async def _generate_operating_expense(db: AsyncSession, appr: ExpenseApproval):
    """不超过门槛：直接完成，并生成一笔运营支出。"""
    # 找运营支出类别，没有则建一个
    cat = (await db.execute(
        select(IncomeExpenseCategory).where(
            IncomeExpenseCategory.warehouse_id == appr.warehouse_id,
            IncomeExpenseCategory.type == "expense",
            IncomeExpenseCategory.category_group == "operating",
        ).order_by(IncomeExpenseCategory.id.asc())
    )).scalars().first()
    if not cat:
        cat = IncomeExpenseCategory(warehouse_id=appr.warehouse_id, type="expense", name="运营支出", category_group="operating", sort_order=0)
        db.add(cat)
        await db.flush()

    # 找一个收款账户，没有则建一个默认
    account = (await db.execute(
        select(PaymentAccount).where(
            PaymentAccount.warehouse_id == appr.warehouse_id,
            PaymentAccount.status != "inactive",
        ).order_by(PaymentAccount.id.asc())
    )).scalars().first()
    if not account:
        account = PaymentAccount(
            warehouse_id=appr.warehouse_id, account_name="公司账户", account_type="bank",
            account_number="-", currency="THB", status="active",
        )
        db.add(account)
        await db.flush()

    db.add(ExpenseRecord(
        warehouse_id=appr.warehouse_id,
        category_id=cat.id,
        account_id=account.id,
        amount=appr.amount,
        currency=appr.currency or "THB",
        expense_date=datetime.combine(appr.expense_date, datetime.min.time()),
        voucher=appr.voucher_path,
        remark=f"[费用审批#{appr.id}] {appr.purpose}",
    ))


@router.post("")
async def create_approval(
    req: ApprovalCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _check_submit_role(current_user)
    wh_id = get_wh_id(current_user)
    if not wh_id:
        raise HTTPException(400, "请先选择仓库")

    if req.amount <= 0:
        raise HTTPException(400, "金额必须大于0")
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

    voucher_path = _save_voucher(wh_id, req.voucher_base64) if req.voucher_base64 else None

    threshold = await _get_threshold(db, wh_id)
    # 门槛判断：超过门槛待审批，不超过直接完成
    status = "pending" if req.amount > threshold else "completed"

    a = ExpenseApproval(
        warehouse_id=wh_id,
        applicant_id=current_user.id,
        amount=req.amount,
        currency=req.currency or "THB",
        purpose=purpose,
        expense_date=exp_dt,
        voucher_path=voucher_path,
        payment_method=req.payment_method,
        fund_source=req.fund_source,
        status=status,
    )
    db.add(a)
    await db.flush()

    if status == "completed":
        await _generate_operating_expense(db, a)

    await db.flush()
    return {"id": a.id, "status": status, "message": "费用已提交" if status == "pending" else "费用已生效"}


@router.get("")
async def list_approvals(
    status: Optional[str] = None,
    current_user: User = Depends(get_current_user),
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
            "fund_source": r.fund_source,
            "status": r.status,
            "approver_id": r.approver_id,
            "approver_name": user_map.get(r.approver_id, ""),
            "approved_at": r.approved_at.isoformat() if r.approved_at else None,
            "approval_note": r.approval_note,
            "payer_name": user_map.get(r.payer_id, ""),
            "paid_at": r.paid_at.isoformat() if r.paid_at else None,
            "payment_voucher": r.payment_voucher,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        } for r in rows],
        "total": len(rows),
    }


@router.get("/threshold")
async def get_threshold(
    current_user: User = Depends(get_current_user),
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
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _check_manage_role(current_user)
    if current_user.role != Role.WAREHOUSE_ADMIN:
        raise HTTPException(403, "只有仓库管理员可以设置门槛")
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
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """申请人修改（待审批/已驳回），改完重新提交 → 状态回到待审批。"""
    _check_submit_role(current_user)
    wh_id = get_wh_id(current_user)
    if not wh_id:
        raise HTTPException(400, "请先选择仓库")

    a = (await db.execute(
        select(ExpenseApproval).where(ExpenseApproval.id == approval_id, ExpenseApproval.warehouse_id == wh_id)
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
    if req.voucher_base64 is not None:
        p = _save_voucher(wh_id, req.voucher_base64)
        if p:
            a.voucher_path = p

    # 重新提交 → 待审批
    a.status = "pending"
    a.approver_id = None
    a.approved_at = None
    a.approval_note = None
    await db.flush()
    return {"id": a.id, "message": "已重新提交，等待审批"}


@router.post("/{approval_id}/approve")
async def approve_approval(
    approval_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _check_manage_role(current_user)
    wh_id = get_wh_id(current_user)
    if not wh_id:
        raise HTTPException(400, "请先选择仓库")
    a = (await db.execute(
        select(ExpenseApproval).where(ExpenseApproval.id == approval_id, ExpenseApproval.warehouse_id == wh_id)
    )).scalar_one_or_none()
    if not a:
        raise HTTPException(404, "费用申请不存在")
    if a.status != "pending":
        raise HTTPException(400, "只有待审批的申请可以批准")
    a.status = "approved"
    a.approver_id = current_user.id
    a.approved_at = thai_now()
    await db.flush()
    return {"id": a.id, "message": "已批准"}


@router.post("/{approval_id}/reject")
async def reject_approval(
    approval_id: int,
    req: RejectRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _check_manage_role(current_user)
    wh_id = get_wh_id(current_user)
    if not wh_id:
        raise HTTPException(400, "请先选择仓库")
    a = (await db.execute(
        select(ExpenseApproval).where(ExpenseApproval.id == approval_id, ExpenseApproval.warehouse_id == wh_id)
    )).scalar_one_or_none()
    if not a:
        raise HTTPException(404, "费用申请不存在")
    if a.status != "pending":
        raise HTTPException(400, "只有待审批的申请可以驳回")
    a.status = "rejected"
    a.approver_id = current_user.id
    a.approved_at = thai_now()
    a.approval_note = req.note
    await db.flush()
    return {"id": a.id, "message": "已驳回"}


@router.post("/{approval_id}/pay")
async def pay_approval(
    approval_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _check_manage_role(current_user)
    wh_id = get_wh_id(current_user)
    if not wh_id:
        raise HTTPException(400, "请先选择仓库")
    a = (await db.execute(
        select(ExpenseApproval).where(ExpenseApproval.id == approval_id, ExpenseApproval.warehouse_id == wh_id)
    )).scalar_one_or_none()
    if not a:
        raise HTTPException(404, "费用申请不存在")
    if a.status != "approved":
        raise HTTPException(400, "只有已批准的申请可以付款")
    a.status = "paid"
    a.payer_id = current_user.id
    a.paid_at = thai_now()
    await db.flush()
    return {"id": a.id, "message": "已付款"}

"""垫款登记、确认和非成本归还；不写运营支出或工资。"""
import os
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.menu_registry import MENU_PERMISSIONS_BY_KEY
from app.core.financial_reversals import reject_disabled_financial_reversal
from app.core.permissions import Role, check_staff_permission, get_current_user, get_wh_id
from app.core.timezone import thai_now, thai_today
from app.database import get_db
from app.models.cash_advance import CashAdvance, PURPOSE_LABELS, STATUS_LABELS
from app.models.cash_advance_repayment import CashAdvanceRepayment
from app.models.customer import PaymentAccount
from app.models.user import User
from app.models.user_warehouse import UserWarehouse
from app.services.data_history import record_history
from app.services.account_balances import current_account_balances
from app.services.cash_advance_payroll import payroll_usage_totals, usage_amounts, payroll_usage
from app.services.cash_advance_usage import reimbursement_usage_totals, reimbursement_usage, employee_advance_usage_totals, employee_advance_usage
from app.services import cash_advance_documents as documents

router = APIRouter()
UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "/app/uploads")
PERMISSION = MENU_PERMISSIONS_BY_KEY["cash_advances"].label


async def _reader(user=Depends(check_staff_permission(PERMISSION))):
    if user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF):
        raise HTTPException(403, "无此操作权限")
    return user


async def _creator(user=Depends(get_current_user)):
    if user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
        raise HTTPException(403, "只有仓库管理员和主管可以新建垫款单")
    await check_staff_permission(PERMISSION)(user)
    return user


async def _reviewer(user=Depends(get_current_user)):
    if user.role != Role.WAREHOUSE_ADMIN:
        raise HTTPException(403, "只有仓库管理员可以确认或驳回垫款单")
    return user


async def _repayer(user=Depends(get_current_user)):
    if user.role != Role.WAREHOUSE_ADMIN:
        raise HTTPException(403, "只有仓库管理员可以归还垫款")
    return user


def _warehouse(user):
    if getattr(user, "_all_warehouses", False):
        raise HTTPException(400, "请先选择一个仓库")
    wid = get_wh_id(user)
    if wid is None:
        raise HTTPException(400, "请先选择一个仓库")
    return wid


def _user_in_warehouse(wid):
    return or_(User.warehouse_id == wid, exists(select(UserWarehouse.user_id).where(
        UserWarehouse.user_id == User.id, UserWarehouse.warehouse_id == wid,
    )))


class DocumentReference(BaseModel):
    document_type: Literal["payroll", "payable", "reimbursement", "employee_advance"]
    document_id: int = Field(gt=0)


class CashAdvanceCreate(BaseModel):
    payer_id: int | None = Field(default=None, gt=0)
    payer_name: str | None = Field(default=None, max_length=100)
    advance_date: date
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2, allow_inf_nan=False)
    currency: Literal["THB", "CNY"] = "THB"
    purpose: Literal["salary", "purchase", "expense", "other"]
    description: str | None = Field(default=None, max_length=2000)
    voucher_path: str | None = Field(default=None, max_length=500)
    linked_documents: list[DocumentReference] = Field(default_factory=list, max_length=200)
    amount_difference_note: str | None = Field(default=None, max_length=2000)

    @field_validator("payer_name", "description", "voucher_path", "amount_difference_note")
    @classmethod
    def trim(cls, value):
        return value.strip() or None if value is not None else None


class RejectRequest(BaseModel):
    reject_reason: str | None = Field(default=None, max_length=500)


def _serialize(row):
    outstanding = max(Decimal("0"), row.amount - row.repaid_amount) if row.status == "confirmed" else Decimal("0")
    return {
        "id": row.id, "warehouse_id": row.warehouse_id,
        "payer_id": row.payer_id, "payer_name": row.payer_name,
        "advance_date": row.advance_date.isoformat(), "amount": float(row.amount), "currency": row.currency,
        "purpose": row.purpose, "purpose_label": PURPOSE_LABELS[row.purpose],
        "description": row.description, "voucher_path": row.voucher_path,
        "status": row.status, "status_label": "部分归还" if row.status == "confirmed" and row.repaid_amount > 0 else STATUS_LABELS[row.status],
        "repaid_amount": float(row.repaid_amount), "outstanding_amount": float(outstanding),
        "created_by_id": row.created_by_id, "created_by_name": row.created_by_name,
        "created_at": row.created_at.isoformat(),
        "reviewed_by_id": row.reviewed_by_id, "reviewed_by_name": row.reviewed_by_name,
        "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
        "reject_reason": row.reject_reason,
        "amount_difference_note": row.amount_difference_note,
    }


async def _used_ids(db, ids):
    """已执行过资金使用/归还的单据不再允许编辑，即使相关记录后来已作废。"""
    from app.models.payroll import PayrollRecord
    from app.models.reimbursement_payment import ReimbursementPayment
    from app.models.employee_advance import EmployeeAdvance
    used = set()
    for model, condition in (
        (CashAdvanceRepayment, True), (ReimbursementPayment, True),
        (PayrollRecord, PayrollRecord.disbursed.is_(True)),
        (EmployeeAdvance, EmployeeAdvance.approval_status == "approved"),
    ):
        used.update((await db.execute(select(model.cash_advance_id).where(
            model.cash_advance_id.in_(ids), condition))).scalars().all())
    return used


def _can_edit(row, user, used):
    return (row.id not in used and row.repaid_amount == 0 and
        (row.status == "pending" and user.role in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR) or
         row.status == "confirmed" and user.role == Role.WAREHOUSE_ADMIN))


async def _with_documents(db, row, user):
    links = (await documents.links_map(db, [row]))[row.id]
    return {**_serialize(row), "linked_documents": links,
        "linked_documents_total": float(sum((documents.money(d["amount"]) for d in links), Decimal(0))),
        "can_edit": _can_edit(row, user, await _used_ids(db, [row.id]))}


@router.get("/document-options")
async def document_options(
    document_type: Literal["payroll", "payable", "reimbursement", "employee_advance"],
    currency: Literal["THB", "CNY"] = "THB", search: str = Query(default="", max_length=100),
    page: int = Query(default=1, ge=1), page_size: int = Query(default=50, ge=1, le=100),
    user=Depends(_creator), db: AsyncSession = Depends(get_db),
):
    return await documents.options(db, _warehouse(user), document_type, currency, search.strip(), page, page_size)


@router.get("/payers")
async def list_payers(user=Depends(_reader), db: AsyncSession = Depends(get_db)):
    accounts = (await db.execute(select(User).where(
        _user_in_warehouse(_warehouse(user)), User.is_active.is_(True), User.role != Role.SUPER_ADMIN,
    ).order_by(User.display_name, User.id))).scalars().all()
    return {"data": [{"id": u.id, "name": u.display_name, "username": u.username, "role": u.role} for u in accounts]}


@router.get("/summary")
async def summary(user=Depends(_reader), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(CashAdvance).where(
        CashAdvance.warehouse_id == _warehouse(user), CashAdvance.status == "confirmed",
        CashAdvance.amount > CashAdvance.repaid_amount,
    ).order_by(CashAdvance.id))).scalars().all()
    groups = {}
    currency_totals = {}
    for row in rows:
        key = ("user", row.payer_id) if row.payer_id is not None else ("name", row.payer_name)
        group = groups.setdefault(key, {"payer_id": row.payer_id, "payer_name": row.payer_name, "totals": {}})
        currency = row.currency
        amount = row.amount - row.repaid_amount
        group["totals"][currency] = group["totals"].get(currency, Decimal("0")) + amount
        currency_totals[currency] = currency_totals.get(currency, Decimal("0")) + amount
    def amounts(totals):
        return [{"currency": currency, "amount": float(amount)} for currency, amount in sorted(totals.items())]
    def single_total(totals):
        return float(next(iter(totals.values()))) if len(totals) == 1 else (0 if not totals else None)
    return {"payer_count": len(groups), "total_outstanding": single_total(currency_totals),
            "totals_by_currency": amounts(currency_totals),
            "data": [{"payer_id": g["payer_id"], "payer_name": g["payer_name"],
                "outstanding_amount": single_total(g["totals"]), "totals_by_currency": amounts(g["totals"])} for g in groups.values()]}


@router.get("")
async def list_advances(
    start_date: date | None = None, end_date: date | None = None,
    status: Literal["pending", "confirmed", "rejected", "repaid", "partially_repaid"] | None = None,
    payer_id: int | None = None, payer_name: str | None = Query(default=None, max_length=100),
    page: int = Query(default=1, ge=1), page_size: int = Query(default=20, ge=1, le=200),
    user=Depends(_reader), db: AsyncSession = Depends(get_db),
):
    if start_date and end_date and start_date > end_date:
        raise HTTPException(400, "开始日期不能晚于结束日期")
    filters = [CashAdvance.warehouse_id == _warehouse(user)]
    if start_date: filters.append(CashAdvance.advance_date >= start_date)
    if end_date: filters.append(CashAdvance.advance_date <= end_date)
    if status == "partially_repaid":
        filters.extend([CashAdvance.status == "confirmed", CashAdvance.repaid_amount > 0])
    elif status: filters.append(CashAdvance.status == status)
    if payer_id is not None: filters.append(CashAdvance.payer_id == payer_id)
    if payer_name and payer_name.strip(): filters.append(CashAdvance.payer_name.contains(payer_name.strip(), autoescape=True))
    total = (await db.execute(select(func.count()).select_from(CashAdvance).where(*filters))).scalar_one()
    rows = (await db.execute(select(CashAdvance).where(*filters).order_by(
        CashAdvance.advance_date.desc(), CashAdvance.id.desc(),
    ).offset((page - 1) * page_size).limit(page_size))).scalars().all()
    used = await payroll_usage_totals(db, rows)
    other = await reimbursement_usage_totals(db, rows)
    advances = await employee_advance_usage_totals(db, rows)
    linked = await documents.links_map(db, rows)
    used_ids = await _used_ids(db, [r.id for r in rows]) if rows else set()
    return {"data": [{**_serialize(r), **usage_amounts(r, used[r.id], other[r.id], advances[r.id]),
        "linked_documents": linked[r.id], "linked_documents_total": float(sum((documents.money(d["amount"]) for d in linked[r.id]), Decimal(0))),
        "can_edit": _can_edit(r, user, used_ids)} for r in rows],
            "total": total, "page": page, "page_size": page_size}


@router.post("/voucher")
async def upload_voucher(file: UploadFile = File(...), user=Depends(_creator)):
    from app.services.image_utils import is_image, save_image
    wid = _warehouse(user)
    content = await file.read(10 * 1024 * 1024 + 1)
    if not content or len(content) > 10 * 1024 * 1024:
        raise HTTPException(400, "凭证照片大小须在10MB以内")
    ext = (file.filename or "").rsplit(".", 1)[-1].lower()
    if ext not in ("png", "jpg", "jpeg", "webp") or not is_image(content):
        raise HTTPException(400, "请上传 png/jpg/jpeg/webp 凭证照片")
    subdir = f"{wid}/{thai_now():%Y-%m-%d}/cash-advances"
    result = save_image(content, os.path.join(UPLOAD_DIR, subdir), f"uploads/{subdir}", f"{uuid.uuid4().hex}.{ext}")
    return {"path": result["path"], "thumb_path": result["thumb_path"]}


async def _validate_payer(req, user, wid, db):
    payer_id, payer_name = req.payer_id, req.payer_name
    if payer_id is not None:
        payer = (await db.execute(select(User).where(User.id == payer_id, _user_in_warehouse(wid),
            User.is_active.is_(True), User.role != Role.SUPER_ADMIN))).scalar_one_or_none()
        if payer is None: raise HTTPException(400, "垫款账号不存在、已停用或不属于当前仓库")
        payer_name = payer.display_name
    elif not payer_name:
        payer_id, payer_name = user.id, user.display_name
    if req.voucher_path:
        parts = req.voucher_path.split("/")
        if len(parts) != 5 or parts[:2] != ["uploads", str(wid)] or parts[3] != "cash-advances" or any(p in ("", ".", "..") or "\\" in p for p in parts):
            raise HTTPException(400, "凭证照片不属于当前仓库的垫款单")
    return payer_id, payer_name


@router.post("")
async def create_advance(req: CashAdvanceCreate, user=Depends(_creator), db: AsyncSession = Depends(get_db)):
    wid = _warehouse(user)
    payer_id, payer_name = await _validate_payer(req, user, wid, db)
    linked = await documents.resolve(db, wid, req.currency, req.linked_documents)
    documents.validate_difference(req.amount, linked, req.amount_difference_note)
    confirmed = user.role == Role.WAREHOUSE_ADMIN
    now = thai_now()
    row = CashAdvance(warehouse_id=wid, payer_id=payer_id, payer_name=payer_name,
        advance_date=req.advance_date, amount=req.amount, currency=req.currency, purpose=req.purpose,
        description=req.description, voucher_path=req.voucher_path, status="confirmed" if confirmed else "pending", repaid_amount=0,
        amount_difference_note=req.amount_difference_note,
        reviewed_by_id=user.id if confirmed else None, reviewed_by_name=user.display_name if confirmed else None,
        reviewed_at=now if confirmed else None, created_by_id=user.id, created_by_name=user.display_name, created_at=now)
    db.add(row)
    await db.flush()
    await documents.save_links(db, row, linked)
    result = await _with_documents(db, row, user)
    await record_history(db, module="cash_advances", record_id=row.id, operator=user,
        operation_type="create", after=result, warehouse_id=wid)
    return result


@router.put("/{advance_id}")
async def edit_advance(advance_id: int, req: CashAdvanceCreate, user=Depends(_creator), db: AsyncSession = Depends(get_db)):
    wid = _warehouse(user)
    row = (await db.execute(select(CashAdvance).where(CashAdvance.id == advance_id,
        CashAdvance.warehouse_id == wid).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
    if row is None: raise HTTPException(404, "垫款单不存在或不属于当前仓库")
    if not _can_edit(row, user, await _used_ids(db, [row.id])):
        raise HTTPException(400, "仅待确认单可由主管或管理员编辑；未使用且未归还的已确认单仅管理员可编辑")
    before = await _with_documents(db, row, user)
    payer_id, payer_name = await _validate_payer(req, user, wid, db)
    linked = await documents.resolve(db, wid, req.currency, req.linked_documents)
    documents.validate_difference(req.amount, linked, req.amount_difference_note)
    for key in ("advance_date", "amount", "currency", "purpose", "description", "voucher_path", "amount_difference_note"):
        setattr(row, key, getattr(req, key))
    row.payer_id, row.payer_name = payer_id, payer_name
    await documents.save_links(db, row, linked)
    result = await _with_documents(db, row, user)
    await record_history(db, module="cash_advances", record_id=row.id, operator=user,
        operation_type="update", before=before, after=result, warehouse_id=wid)
    return result


@router.get("/{advance_id}/documents/{link_id}")
async def linked_document_detail(advance_id: int, link_id: int, user=Depends(_reader), db: AsyncSession = Depends(get_db)):
    return await documents.view_document(db, _warehouse(user), advance_id, link_id)


async def _review(advance_id, reason, user, db):
    row = (await db.execute(select(CashAdvance).where(
        CashAdvance.id == advance_id, CashAdvance.warehouse_id == _warehouse(user),
    ).with_for_update())).scalar_one_or_none()
    if row is None: raise HTTPException(404, "垫款单不存在或不属于当前仓库")
    if row.status != "pending":
        raise HTTPException(400, f"该垫款单{STATUS_LABELS[row.status]}，不能重复确认或驳回")
    before = _serialize(row)
    row.status = "rejected" if reason is not None else "confirmed"
    row.reject_reason = reason
    row.reviewed_by_id, row.reviewed_by_name, row.reviewed_at = user.id, user.display_name, thai_now()
    await db.flush()
    result = _serialize(row)
    await record_history(db, module="cash_advances", record_id=row.id, operator=user,
        operation_type="reject" if reason is not None else "confirm", before=before, after=result, warehouse_id=row.warehouse_id)
    return result


@router.post("/{advance_id}/confirm")
async def confirm_advance(advance_id: int, user=Depends(_reviewer), db: AsyncSession = Depends(get_db)):
    return await _review(advance_id, None, user, db)


@router.post("/{advance_id}/reject")
async def reject_advance(advance_id: int, req: RejectRequest | None = None, user=Depends(_reviewer), db: AsyncSession = Depends(get_db)):
    reason = ((req.reject_reason if req else None) or "").strip()
    if not reason: raise HTTPException(400, "请填写驳回原因")
    return await _review(advance_id, reason, user, db)


class RepaymentRequest(BaseModel):
    repayment_date: date = Field(default_factory=thai_today)
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2, allow_inf_nan=False)
    account_id: int | None = Field(default=None, gt=0)
    payment_method: Literal["cash", "transfer"]
    voucher_path: str | None = Field(default=None, max_length=500)
    description: str | None = Field(default=None, max_length=2000)
    request_key: str | None = Field(default=None, min_length=1, max_length=64)


class RevokeRepaymentRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


def _repayment_dict(row):
    return {
        "id": row.id, "cash_advance_id": row.cash_advance_id, "warehouse_id": row.warehouse_id,
        "repayment_date": row.repayment_date.isoformat(), "amount": float(row.amount),
        "account_id": row.account_id, "account_name": row.account_name, "currency": row.currency,
        "payment_method": row.payment_method, "payment_method_label": "现金" if row.payment_method == "cash" else "转账",
        "voucher_path": row.voucher_path, "description": row.description,
        "created_by_id": row.created_by_id, "created_by_name": row.created_by_name, "created_at": row.created_at.isoformat(),
        "status": row.status, "status_label": "有效" if row.status == "active" else "已撤销",
        "revoked_by_id": row.revoked_by_id, "revoked_by_name": row.revoked_by_name,
        "revoked_at": row.revoked_at.isoformat() if row.revoked_at else None, "revoke_reason": row.revoke_reason,
        "ledger_ref_no": f"CAR-{row.id}", "remark": f"归还垫款 #{row.cash_advance_id}",
    }


async def _loan(db, advance_id, wid, *, lock=False):
    query = select(CashAdvance).where(CashAdvance.id == advance_id, CashAdvance.warehouse_id == wid)
    if lock: query = query.with_for_update()
    row = (await db.execute(query)).scalar_one_or_none()
    if row is None: raise HTTPException(404, "垫款单不存在或不属于当前仓库")
    return row


async def _repayment_result(db, row, loan, account):
    balance = (await current_account_balances(db, [account]))[account.id]
    return {"repayment": _repayment_dict(row), "advance": _serialize(loan),
            "account": {"id": account.id, "name": account.account_name, "current_balance": float(balance), "currency": account.currency or "THB"}}


@router.get("/repayment-accounts")
async def repayment_accounts(user=Depends(_repayer), db: AsyncSession = Depends(get_db)):
    accounts = (await db.execute(select(PaymentAccount).where(
        PaymentAccount.warehouse_id == _warehouse(user),
        or_(PaymentAccount.status == "active", PaymentAccount.status.is_(None)),
    ).order_by(PaymentAccount.id))).scalars().all()
    balances = await current_account_balances(db, accounts)
    return {"data": [{"id": a.id, "account_name": a.account_name, "account_type": a.account_type,
        "currency": a.currency or "THB", "current_balance": float(balances[a.id])} for a in accounts]}


@router.post("/repayment-voucher")
async def repayment_voucher(file: UploadFile = File(...), user=Depends(_repayer)):
    return await upload_voucher(file, user)


@router.get("/{advance_id}/repayments")
async def list_repayments(advance_id: int, user=Depends(_reader), db: AsyncSession = Depends(get_db)):
    wid = _warehouse(user)
    loan = await _loan(db, advance_id, wid)
    rows = (await db.execute(select(CashAdvanceRepayment).where(
        CashAdvanceRepayment.cash_advance_id == loan.id, CashAdvanceRepayment.warehouse_id == wid,
    ).order_by(CashAdvanceRepayment.id.desc()))).scalars().all()
    return {"advance": _serialize(loan), "data": [_repayment_dict(r) for r in rows],
            "total": len(rows), "active_count": sum(r.status == "active" for r in rows),
            "payroll_usage": await payroll_usage(db, loan), "reimbursement_usage": await reimbursement_usage(db, loan),
            "employee_advance_usage": await employee_advance_usage(db, loan)}


@router.post("/{advance_id}/repayments")
async def repay_advance(advance_id: int, req: RepaymentRequest, user=Depends(_repayer), db: AsyncSession = Depends(get_db)):
    wid = _warehouse(user)
    loan = await _loan(db, advance_id, wid, lock=True)
    if not req.account_id: raise HTTPException(400, "请选择归还账户")
    voucher = (req.voucher_path or "").strip()
    parts = voucher.split("/")
    if not voucher: raise HTTPException(400, "请上传归还凭证照片")
    if len(parts) != 5 or parts[:2] != ["uploads", str(wid)] or parts[3] != "cash-advances" or any(p in ("", ".", "..") or "\\" in p for p in parts):
        raise HTTPException(400, "凭证照片不属于当前仓库的垫款单")
    voucher_file = Path(UPLOAD_DIR).joinpath(*parts[1:])
    if not voucher_file.is_file(): raise HTTPException(400, "归还凭证照片不存在，请重新上传")
    if req.request_key:
        previous = (await db.execute(select(CashAdvanceRepayment).where(
            CashAdvanceRepayment.warehouse_id == wid, CashAdvanceRepayment.request_key == req.request_key,
        ))).scalar_one_or_none()
        if previous is not None:
            if (previous.cash_advance_id, previous.amount, previous.account_id, previous.repayment_date, previous.payment_method) != (loan.id, req.amount, req.account_id, req.repayment_date, req.payment_method):
                raise HTTPException(409, "归还请求已使用，请刷新后重试")
            if previous.status != "active": raise HTTPException(400, "该笔归还已撤销，请重新登记")
            account = await db.get(PaymentAccount, previous.account_id)
            return await _repayment_result(db, previous, loan, account)
    if loan.status == "repaid" or loan.repaid_amount >= loan.amount:
        raise HTTPException(400, "该垫款单已还清")
    if loan.status != "confirmed": raise HTTPException(400, "待确认或已驳回的垫款单不能归还")
    if req.amount > loan.amount - loan.repaid_amount: raise HTTPException(400, "不能超过剩余未还")
    account = (await db.execute(select(PaymentAccount).where(
        PaymentAccount.id == req.account_id, PaymentAccount.warehouse_id == wid,
    ).with_for_update())).scalar_one_or_none()
    if account is None: raise HTTPException(400, "归还账户不存在或不属于当前仓库")
    if account.status not in (None, "active"): raise HTTPException(400, "归还账户已停用")
    if (account.currency or "THB").upper() != loan.currency:
        raise HTTPException(400, f"归还账户币种必须与垫款单一致（{loan.currency}）")
    before = _serialize(loan)
    row = CashAdvanceRepayment(cash_advance_id=loan.id, warehouse_id=wid, repayment_date=req.repayment_date,
        amount=req.amount, account_id=account.id, account_name=account.account_name, currency=loan.currency,
        payment_method=req.payment_method, voucher_path=voucher, description=(req.description or "").strip() or None,
        request_key=req.request_key, created_by_id=user.id, created_by_name=user.display_name, created_at=thai_now(), status="active")
    db.add(row)
    loan.repaid_amount += req.amount
    if loan.repaid_amount == loan.amount: loan.status = "repaid"
    await db.flush()
    result = await _repayment_result(db, row, loan, account)
    await record_history(db, module="cash_advances", record_id=loan.id, operator=user, operation_type="repay",
        before=before, after=result, warehouse_id=wid)
    return result


@router.post("/repayments/{repayment_id}/revoke", dependencies=[Depends(reject_disabled_financial_reversal)])
async def revoke_repayment(repayment_id: int, req: RevokeRepaymentRequest | None = None, user=Depends(_repayer), db: AsyncSession = Depends(get_db)):
    wid = _warehouse(user)
    reason = ((req.reason if req else None) or "").strip()
    if not reason: raise HTTPException(400, "请填写撤销原因")
    advance_id = (await db.execute(select(CashAdvanceRepayment.cash_advance_id).where(
        CashAdvanceRepayment.id == repayment_id, CashAdvanceRepayment.warehouse_id == wid,
    ))).scalar_one_or_none()
    if advance_id is None: raise HTTPException(404, "归还记录不存在或不属于当前仓库")
    loan = await _loan(db, advance_id, wid, lock=True)
    row = (await db.execute(select(CashAdvanceRepayment).where(
        CashAdvanceRepayment.id == repayment_id, CashAdvanceRepayment.warehouse_id == wid,
    ).with_for_update())).scalar_one()
    if row.status != "active": raise HTTPException(400, "该笔归还已撤销")
    if loan.status not in ("confirmed", "repaid") or loan.repaid_amount < row.amount:
        raise HTTPException(400, "垫款已还金额异常，请先核对")
    account = (await db.execute(select(PaymentAccount).where(
        PaymentAccount.id == row.account_id, PaymentAccount.warehouse_id == wid,
    ).with_for_update())).scalar_one_or_none()
    if account is None: raise HTTPException(400, "原归还账户不存在或不属于当前仓库")
    if (account.currency or "THB").upper() != row.currency.upper():
        raise HTTPException(400, "原账户币种已变化，请先核对")
    before = {"advance": _serialize(loan), "repayment": _repayment_dict(row)}
    row.status = "revoked"
    row.revoked_by_id, row.revoked_by_name, row.revoked_at, row.revoke_reason = user.id, user.display_name, thai_now(), reason
    loan.repaid_amount -= row.amount
    loan.status = "confirmed"
    await db.flush()
    result = await _repayment_result(db, row, loan, account)
    await record_history(db, module="cash_advances", record_id=loan.id, operator=user, operation_type="revoke_repayment",
        before=before, after=result, warehouse_id=wid)
    return result

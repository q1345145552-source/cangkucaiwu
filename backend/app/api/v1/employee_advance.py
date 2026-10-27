from app.core.personal_finance import personal_finance_access
from app.services import financial_authorization as duties
from app.core.round2_access import mutation_scope, own_scope
from app.core.employee_access import employee_access, employee_view, attendance_supervisor
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.employee_advance import EmployeeAdvance, AdvanceApprovalStatus, ADVANCE_APPROVAL_LABELS
from app.services.attendance_population import employee_account_roles
from app.models.employee import Employee
from app.models.user import User
from app.core.permissions import get_current_user, get_wh_id, get_wh_ids, Role, check_staff_permission
from app.core.menu_registry import MENU_PERMISSIONS_BY_KEY
from app.core.timezone import thai_now
from app.services.data_history import record_history
from app.services.employee_advance_expense import delete_advance_expense
from app.services.employee_advance_limit import check_advance_limit
from app.services.employee_advance_funding import SOURCES, apply_advance_funding, validate_funding, funding_options
from app.services.cash_advance_reference import cash_advance_numbers, cash_advance_reference
from math import isfinite
from pydantic import BaseModel
from datetime import datetime
from typing import Optional, Literal
import json

router = APIRouter(dependencies=[Depends(mutation_scope)])


def _approval_fields(advance):
    return {
        "approval_status": advance.approval_status,
        "approval_status_label": {'pending':'待核验','verified':'待批准','approved_ready':'待出款','approved':'已出款','rejected':'已驳回'}.get(advance.approval_status, advance.approval_status),
        "reviewer_id": advance.reviewer_id,
        "reviewed_at": advance.reviewed_at.isoformat() if advance.reviewed_at else None,
        "reject_reason": advance.reject_reason,
        "expense_record_id": advance.expense_record_id,
        "funding_source": advance.funding_source,
        "funding_source_label": SOURCES.get(advance.funding_source or "company_account", advance.funding_source),
        "cash_advance_id": advance.cash_advance_id,
        "payment_account_id": advance.payment_account_id,
        "fund_account_id": advance.fund_account_id,
    }


def _void_fields(advance):
    return {"is_voided": advance.is_voided, "voided_by": advance.voided_by,
            "voided_at": advance.voided_at.isoformat() if advance.voided_at else None,
            "void_reason": advance.void_reason}


class AdvanceCreate(BaseModel):
    model_config = {"extra": "forbid"}
    employee_id: Optional[int] = None
    user_id: Optional[int] = None
    amount: float
    advance_date: str  # YYYY-MM-DD
    source: Optional[str] = None  # 保留原字段；新单必须另外选择 funding_source
    funding_source: Optional[str] = None
    payment_account_id: Optional[int] = None
    cash_advance_id: Optional[int] = None
    currency: Optional[Literal["THB", "CNY"]] = None
    fund_account_id: Optional[int] = None
    remark: Optional[str] = None


@router.post("")
async def create_advance(
    req: AdvanceCreate,
    current_user: User = Depends(personal_finance_access(MENU_PERMISSIONS_BY_KEY["employee_advances"].label)),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in (Role.SUPER_ADMIN, Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF):
        raise HTTPException(403, "只有仓库管理员/主管可以记预支")

    wh_id = get_wh_id(current_user)
    if not wh_id:
        raise HTTPException(400, "请先选择仓库")

    if req.amount is None or not isfinite(req.amount) or req.amount <= 0:
        raise HTTPException(400, "预支金额必须大于0")

    try:
        adv_dt = datetime.strptime(req.advance_date, "%Y-%m-%d").date()
    except:
        raise HTTPException(400, "预支日期格式错误 YYYY-MM-DD")

    if (req.employee_id is None) == (req.user_id is None):
        raise HTTPException(400, "请选择一个预支对象")
    if req.user_id is not None:
        from app.services.advance_recipients import resolve_advance_account
        emp = await resolve_advance_account(db, req.user_id, wh_id, current_user)
    else:
        emp = (await db.execute(
            select(Employee).where(Employee.id == req.employee_id, Employee.warehouse_id == wh_id, Employee.is_deleted == False)
            .with_for_update()  # 同一员工的登记串行校验，防止并发绕过额度。
        )).scalar_one_or_none()
    if not emp:
        raise HTTPException(404, "员工不存在")
    if emp.status == "resigned":
        raise HTTPException(400, "该员工已离职，不能记预支")

    # 所属周期自动按日期算
    period = adv_dt.strftime("%Y-%m")
    half = "first_half" if adv_dt.day <= 15 else "second_half"

    try:
        currency, _ = await validate_funding(db, req.funding_source, wh_id, req.amount,
            currency=req.currency, payment_account_id=req.payment_account_id,
            cash_advance_id=req.cash_advance_id, fund_account_id=req.fund_account_id)
    except HTTPException as exc:
        if getattr(current_user, '_personal_finance', False):
            raise HTTPException(exc.status_code, '所选资金来源不可用于该申请，请由财务核对') from exc
        raise

    limit_check = await check_advance_limit(db, emp, req.amount, currency, adv_dt)

    approval_status = AdvanceApprovalStatus.PENDING.value

    adv = EmployeeAdvance(
        warehouse_id=wh_id,
        employee_id=emp.id,
        amount=req.amount,
        currency=currency,
        advance_date=adv_dt,
        period=period,
        half=half,
        source="fund" if req.funding_source == "expense_fund" else "supervisor",
        funding_source=req.funding_source,
        payment_account_id=req.payment_account_id if req.funding_source == "company_account" else None,
        cash_advance_id=req.cash_advance_id if req.funding_source == "cash_advance" else None,
        fund_account_id=req.fund_account_id if req.funding_source == "expense_fund" else None,
        remark=req.remark,
        operator_id=current_user.id,
        deducted_amount=0,
        status="unpaid",
        approval_status=approval_status,
        expense_tracking_enabled=True,
    )
    db.add(adv)
    await db.flush()

    # Request registration does not approve or move funds.

    message = "预支记录已创建"
    if limit_check.get("warning"):
        message += "；" + limit_check["warning"]
    return {"message": message, "id": adv.id, **_approval_fields(adv), "limit_check": limit_check}


@router.get("/funding-options")
async def list_funding_options(
    current_user: User = Depends(personal_finance_access(MENU_PERMISSIONS_BY_KEY["employee_advances"].label)),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF):
        raise HTTPException(403, "无此操作权限")
    wh_id = get_wh_id(current_user)
    if not wh_id:
        raise HTTPException(400, "请先选择仓库")
    if getattr(current_user, '_personal_finance', False):
        from app.models.customer import PaymentAccount
        from app.models.cash_advance import CashAdvance
        from app.models.expense_fund import ExpenseFund
        accounts = (await db.execute(select(PaymentAccount).where(PaymentAccount.warehouse_id == wh_id,
            (PaymentAccount.status == 'active') | PaymentAccount.status.is_(None)))).scalars().all()
        funds = (await db.execute(select(ExpenseFund).where(ExpenseFund.warehouse_id == wh_id,
            ExpenseFund.employee_id.in_(current_user._personal_user_ids), ExpenseFund.status == 'active'))).scalars().all()
        loans = (await db.execute(select(CashAdvance).where(CashAdvance.warehouse_id == wh_id,
            CashAdvance.payer_id.in_(current_user._personal_user_ids), CashAdvance.status == 'confirmed'))).scalars().all()
        return {'accounts': [{'id':a.id,'name':a.account_name,'currency':a.currency or 'THB'} for a in accounts],
            'funds':[{'id':a.id,'name':f'本人备用金 #{a.id}','currency':a.currency or 'THB'} for a in funds],
            'cash_advances':[{'id':a.id,'name':f'本人垫款单 #{a.id}','currency':a.currency or 'THB'} for a in loans]}
    return await funding_options(db, wh_id)


@router.get("/recipients")
async def list_advance_recipients(
    current_user: User = Depends(check_staff_permission(MENU_PERMISSIONS_BY_KEY["employee_advances"].label)),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in (Role.SUPER_ADMIN, Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF):
        raise HTTPException(403, "无此操作权限")
    from app.services.advance_recipients import advance_recipient_options
    wh_id = get_wh_id(current_user)
    return {"data": await advance_recipient_options(db, wh_id) if wh_id else []}


@router.get("")
async def list_advances(
    employee_id: Optional[int] = None,
    period: Optional[str] = None,
    advance_id: Optional[int] = None,
    approval_status: Optional[Literal["pending", "verified", "approved_ready", "approved", "rejected", "待审批", "已通过", "已驳回"]] = None,
    current_user: User = Depends(check_staff_permission(MENU_PERMISSIONS_BY_KEY["employee_advances"].label)),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in (Role.SUPER_ADMIN, Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF):
        raise HTTPException(403, "无权限")

    wh_ids = get_wh_ids(current_user)
    if not wh_ids:
        return {"data": [], "total": 0}

    q = select(EmployeeAdvance).where(EmployeeAdvance.warehouse_id.in_(wh_ids))
    if advance_id is not None:
        q = q.where(EmployeeAdvance.id == advance_id)
    if approval_status is not None:
        normalized = {label: value for value, label in ADVANCE_APPROVAL_LABELS.items()}.get(approval_status, approval_status)
        q = q.where(EmployeeAdvance.approval_status == normalized)
    if employee_id:
        q = q.where(EmployeeAdvance.employee_id == employee_id)
    if period:
        q = q.where(EmployeeAdvance.period == period)

    rows = (await db.execute(q.order_by(EmployeeAdvance.advance_date.desc(), EmployeeAdvance.id.desc()))).scalars().all()
    advance_numbers = await cash_advance_numbers(db, rows)

    emp_ids = {r.employee_id for r in rows}
    op_ids = {uid for r in rows for uid in (r.operator_id, r.voided_by) if uid}
    emp_map = {}
    op_map = {}
    if emp_ids:
        es = (await db.execute(select(Employee).where(Employee.id.in_(emp_ids)))).scalars().all()
        emp_map = {e.id: e for e in es}
    if op_ids:
        us = (await db.execute(select(User).where(User.id.in_(op_ids)))).scalars().all()
        op_map = {u.id: u for u in us}

    return {
        "data": [{
            "id": r.id,
            **_approval_fields(r),
            "capabilities": await duties.advance_capabilities(db,current_user,r),
            **cash_advance_reference(r, advance_numbers),
            **_void_fields(r),
            "voided_by_name": op_map.get(r.voided_by).display_name if op_map.get(r.voided_by) else "",
            "can_void": current_user.role == Role.WAREHOUSE_ADMIN and not r.is_voided
                and r.status not in ("deducted", "partial") and (r.deducted_amount or 0) <= 0,
            "employee_id": r.employee_id,
            "employee_name": emp_map.get(r.employee_id).name if emp_map.get(r.employee_id) else "",
            "employee_status": emp_map.get(r.employee_id).status if emp_map.get(r.employee_id) else "",
            "amount": r.amount,
            "currency": r.currency or "THB",
            "advance_date": r.advance_date.isoformat(),
            "period": r.period,
            "half": r.half,
            "source": r.source,
            "deducted_amount": r.deducted_amount or 0,
            "remaining_amount": 0 if r.is_voided else round((r.amount or 0) - (r.deducted_amount or 0), 2),
            "status": r.status,
            "operator_name": op_map.get(r.operator_id).display_name if op_map.get(r.operator_id) else "",
            "remark": r.remark,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        } for r in rows],
        "total": len(rows),
    }


@router.get("/summary")
async def advance_summary(
    current_user: User = Depends(check_staff_permission(MENU_PERMISSIONS_BY_KEY["employee_advances"].label)),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in (Role.SUPER_ADMIN, Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF):
        raise HTTPException(403, "无权限")

    wh_ids = get_wh_ids(current_user)
    if not wh_ids:
        return {"total_by_currency": [], "debtor_count": 0}

    rows = (await db.execute(
        select(EmployeeAdvance).where(EmployeeAdvance.warehouse_id.in_(wh_ids), EmployeeAdvance.not_voided())
    )).scalars().all()

    by_currency = {}
    debtors = set()
    for r in rows:
        remaining = (r.amount or 0) - (r.deducted_amount or 0)
        if remaining > 0:
            cur = r.currency or "THB"
            by_currency[cur] = round(by_currency.get(cur, 0) + remaining, 2)
            debtors.add(r.employee_id)

    return {
        "total_by_currency": [{"currency": k, "total": v} for k, v in sorted(by_currency.items())],
        "debtor_count": len(debtors),
    }


@router.get("/my-debt")
async def my_debt(
    current_user: User = Depends(employee_access(self_only=True)),
    db: AsyncSession = Depends(get_db),
):
    """劳工端：我的欠款（按币种分组）"""
    if not employee_view(current_user):
        raise HTTPException(403, "无权限")

    wh_id = get_wh_id(current_user)
    if not wh_id:
        return {"total_by_currency": [], "data": []}

    emp = current_user._attendance_employee
    if not emp:
        return {"total_by_currency": [], "data": []}

    advances = (await db.execute(
        select(EmployeeAdvance).where(EmployeeAdvance.employee_id == emp.id, EmployeeAdvance.warehouse_id == wh_id,
            EmployeeAdvance.status != "deducted", EmployeeAdvance.not_voided())
    )).scalars().all()

    by_currency = {}
    for a in advances:
        rem = round((a.amount or 0) - (a.deducted_amount or 0), 2)
        if rem > 0:
            cur = a.currency or "THB"
            by_currency[cur] = round(by_currency.get(cur, 0) + rem, 2)

    return {
        "total_by_currency": [{"currency": k, "total": v} for k, v in sorted(by_currency.items())],
        "data": [{"id": a.id, "employee_id": a.employee_id, "amount": a.amount,
                  "currency": a.currency or "THB", "advance_date": a.advance_date.isoformat(),
                  "deducted_amount": a.deducted_amount or 0, "status": a.status,
                  **_approval_fields(a)} for a in advances],
    }


class AdvanceVoidRequest(BaseModel):
    void_reason: Optional[str] = None


async def _advance_voider(current_user: User = Depends(get_current_user)):
    if current_user.role != Role.WAREHOUSE_ADMIN:
        raise HTTPException(403, "只有仓库管理员可以作废预支")
    return current_user


@router.delete("/{advance_id}")
async def delete_advance(
    advance_id: int,
    req: AdvanceVoidRequest = AdvanceVoidRequest(),
    current_user: User = Depends(_advance_voider),
    db: AsyncSession = Depends(get_db),
):
    """保留原DELETE地址，只作废留痕，不硬删预支。"""
    wh_id = get_wh_id(current_user)
    if not wh_id:
        raise HTTPException(400, "请先选择仓库")

    r = (await db.execute(
        select(EmployeeAdvance).where(EmployeeAdvance.id == advance_id, EmployeeAdvance.warehouse_id == wh_id).with_for_update()
    )).scalar_one_or_none()
    if not r:
        raise HTTPException(404, "预支记录不存在")
    if r.is_voided:
        raise HTTPException(400, "该预支已作废")
    if r.status in ("deducted", "partial") or (r.deducted_amount or 0) > 0:
        raise HTTPException(400, "该预支已随工资结清 不能作废" if r.status == "deducted"
                            else "该预支已随工资抵扣 不能作废")
    # 包括保留的作废工资明细；凡查得到扣过这笔预支，就不再允许作废。
    from app.models.payroll import PayrollRecord
    details = (await db.execute(select(PayrollRecord.detail).where(
        PayrollRecord.warehouse_id == wh_id, PayrollRecord.employee_id == r.employee_id,
    ))).scalars().all()
    for raw in details:
        try:
            detail = json.loads(raw or "{}")
            for line in detail.get("advance_deductions", []) or []:
                if str(line.get("advance_id")) == str(r.id) and float(line.get("amount") or 0) > 0:
                    raise HTTPException(400, "该预支已随工资抵扣 不能作废")
        except (ValueError, TypeError, AttributeError):
            continue
    reason = (req.void_reason or "").strip()
    if not reason:
        raise HTTPException(400, "请填写作废原因")
    if len(reason) > 500:
        raise HTTPException(400, "作废原因不能超过500字")
    before = {"employee_id": r.employee_id, "amount": r.amount, "currency": r.currency,
              "status": r.status, "fund_item_id": r.fund_item_id, **_approval_fields(r)}
    await delete_advance_expense(db, r, current_user, reason=f"作废预支：{reason}")
    r.status, r.voided_by, r.voided_at, r.void_reason = "voided", current_user.id, thai_now(), reason
    await record_history(db, module="employee_advances", record_id=r.id, operator=current_user,
        operation_type="void", before=before,
        after={"status": r.status, "amount": r.amount, **_approval_fields(r), **_void_fields(r)}, warehouse_id=wh_id)
    await db.flush()
    return {"message": "预支已作废", "id": r.id, "status": r.status,
            "remaining_amount": 0, **_approval_fields(r), **_void_fields(r)}


class AdvanceRejectRequest(BaseModel):
    reject_reason: Optional[str] = None


async def _advance_approver(current_user: User = Depends(get_current_user)):
    if current_user.role != Role.WAREHOUSE_ADMIN:
        raise HTTPException(403, "只有仓库管理员可以审批预支")
    return current_user


async def _review_advance(db, advance_id, current_user, action, reason=None):
    wh_id = get_wh_id(current_user)
    if not wh_id:
        raise HTTPException(400, "请先选择仓库")
    advance = (await db.execute(select(EmployeeAdvance).where(
        EmployeeAdvance.id == advance_id, EmployeeAdvance.warehouse_id == wh_id,
    ).with_for_update())).scalar_one_or_none()
    if advance is None:
        raise HTTPException(404, "预支记录不存在")
    own_scope(current_user, advance.warehouse_id)
    await duties.independent(db, current_user, *await duties.advance_people(db,advance))
    if advance.is_voided:
        raise HTTPException(400, "该预支已作废，不能审批")
    if action == "reject":
        reason = (reason or "").strip()
        if not reason:
            raise HTTPException(400, "请填写驳回原因")
        if len(reason) > 500:
            raise HTTPException(400, "驳回原因不能超过500字")
    if advance.approval_status == AdvanceApprovalStatus.APPROVED.value:
        raise HTTPException(400, "该预支已通过" if action == "approve" else "该预支已通过，不能驳回")
    if advance.approval_status == AdvanceApprovalStatus.REJECTED.value:
        raise HTTPException(400, "该预支已驳回，不能审批通过" if action == "approve" else "该预支已驳回")
    if advance.approval_status not in ('pending', 'verified'):
        raise HTTPException(400, "只有待审批的预支可以审批")
    before = {"amount": advance.amount, **_approval_fields(advance)}
    if action == "approve":
        await duties.proof(db,advance,'advance_verify',await duties.advance_payload(db,advance))
    advance.approval_status = ("approved_ready" if action == "approve"
                               else AdvanceApprovalStatus.REJECTED.value)
    advance.reviewer_id = current_user.id
    advance.reviewed_at = thai_now()
    advance.reject_reason = reason if action == "reject" else None
    if action == "approve":
        await duties.evidence(db,current_user,advance,'advance_approve',await duties.advance_payload(db,advance))
    await record_history(db, module="employee_advances", record_id=advance.id,
        operator=current_user, operation_type=action, before=before,
        after={"amount": advance.amount, **_approval_fields(advance)}, warehouse_id=wh_id)
    await db.flush()
    return {"message": "预支已通过" if action == "approve" else "预支已驳回",
            "id": advance.id, "amount": advance.amount, **_approval_fields(advance)}


@router.post("/{advance_id}/approve")
async def approve_advance(advance_id: int,
    current_user: User = Depends(_advance_approver), db: AsyncSession = Depends(get_db)):
    return await _review_advance(db, advance_id, current_user, "approve")


@router.post("/{advance_id}/reject")
async def reject_advance(advance_id: int, req: AdvanceRejectRequest = AdvanceRejectRequest(),
    current_user: User = Depends(_advance_approver), db: AsyncSession = Depends(get_db)):
    return await _review_advance(db, advance_id, current_user, "reject", req.reject_reason)


@router.get("/{advance_id}")
async def advance_detail(advance_id: int,
    current_user: User = Depends(check_staff_permission(MENU_PERMISSIONS_BY_KEY["employee_advances"].label)),
    db: AsyncSession = Depends(get_db)):
    result = await list_advances(advance_id=advance_id, current_user=current_user, db=db)
    if not result["data"]:
        raise HTTPException(404, "预支记录不存在")
    return result["data"][0]


@router.post("/{advance_id}/verify")
async def verify_advance(advance_id: int, current_user: User = Depends(check_staff_permission(MENU_PERMISSIONS_BY_KEY["employee_advances"].label)), db: AsyncSession = Depends(get_db)):
    duties.accountant(current_user)
    row=(await db.execute(select(EmployeeAdvance).where(EmployeeAdvance.id==advance_id).with_for_update())).scalar_one_or_none()
    if row is None:raise HTTPException(404,'预支不存在')
    own_scope(current_user,row.warehouse_id)
    await duties.independent(db,current_user,*await duties.advance_people(db,row))
    if row.is_voided or row.approval_status != 'pending':raise HTTPException(409,'只能核验待处理申请')
    row.approval_status='verified'
    await duties.evidence(db,current_user,row,'advance_verify',await duties.advance_payload(db,row))
    return {'message':'凭证已核验，尚未批准或出款','id':row.id,'approval_status':row.approval_status}

@router.post("/{advance_id}/execute")
async def execute_advance(advance_id: int, current_user: User = Depends(check_staff_permission(MENU_PERMISSIONS_BY_KEY["employee_advances"].label)), db: AsyncSession = Depends(get_db)):
    row=(await db.execute(select(EmployeeAdvance).where(EmployeeAdvance.id==advance_id).with_for_update())).scalar_one_or_none()
    if row is None:raise HTTPException(404,'预支不存在')
    own_scope(current_user,row.warehouse_id)
    await duties.executor(db,current_user,*await duties.advance_people(db,row))
    if row.is_voided or row.approval_status != 'approved_ready' or row.expense_record_id or row.fund_item_id:
        raise HTTPException(409,'该预支未经有效批准或已经执行')
    await duties.proof(db,row,'advance_approve',await duties.advance_payload(db,row))
    if not row.funding_source or not row.expense_tracking_enabled:
        raise HTTPException(409,'历史预支缺少可验证资金来源，请先独立核对')
    row.approval_status='approved'
    await apply_advance_funding(db,row,current_user)
    await duties.evidence(db,current_user,row,'advance_execute',await duties.advance_payload(db,row))
    return {'message':'预支已执行','id':row.id,**_approval_fields(row)}

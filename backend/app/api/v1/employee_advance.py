from app.core.employee_access import employee_access, employee_view, attendance_supervisor
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.models.employee_advance import EmployeeAdvance, AdvanceApprovalStatus, ADVANCE_APPROVAL_LABELS
from app.services.attendance_population import employee_account_roles
from app.models.employee import Employee
from app.models.user import User
from app.models.expense_fund import ExpenseFund, ExpenseFundItem, ReviewStatus
from app.core.permissions import get_current_user, get_wh_id, get_wh_ids, Role, check_staff_permission
from app.core.menu_registry import MENU_PERMISSIONS_BY_KEY
from app.core.timezone import thai_now, thai_today
from app.services.flow_rules import fund_available
from app.services.data_history import record_history
from app.services.employee_advance_expense import create_advance_expense, delete_advance_expense
from math import isfinite
from pydantic import BaseModel
from datetime import datetime, date
from typing import Optional, List, Literal

router = APIRouter()


def _approval_fields(advance):
    return {
        "approval_status": advance.approval_status,
        "approval_status_label": ADVANCE_APPROVAL_LABELS.get(advance.approval_status, advance.approval_status),
        "reviewer_id": advance.reviewer_id,
        "reviewed_at": advance.reviewed_at.isoformat() if advance.reviewed_at else None,
        "reject_reason": advance.reject_reason,
        "expense_record_id": advance.expense_record_id,
    }


class AdvanceCreate(BaseModel):
    employee_id: Optional[int] = None
    user_id: Optional[int] = None
    amount: float
    advance_date: str  # YYYY-MM-DD
    source: str  # supervisor / fund
    fund_account_id: Optional[int] = None
    remark: Optional[str] = None


@router.post("")
async def create_advance(
    req: AdvanceCreate,
    current_user: User = Depends(check_staff_permission(MENU_PERMISSIONS_BY_KEY["employee_advances"].label)),
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
        )).scalar_one_or_none()
    if not emp:
        raise HTTPException(404, "员工不存在")
    if emp.status == "resigned":
        raise HTTPException(400, "该员工已离职，不能记预支")

    # 所属周期自动按日期算
    period = adv_dt.strftime("%Y-%m")
    half = "first_half" if adv_dt.day <= 15 else "second_half"

    currency = "THB"
    fund_account = None
    if req.source == "fund":
        if not req.fund_account_id:
            raise HTTPException(400, "请选择备用金账户")
        fund_account = (await db.execute(
            select(ExpenseFund).where(ExpenseFund.id == req.fund_account_id, ExpenseFund.warehouse_id == wh_id)
        )).scalar_one_or_none()
        if not fund_account:
            raise HTTPException(404, "备用金账户不存在")
        currency = fund_account.currency or "THB"
    elif req.source not in ("supervisor", "fund"):
        raise HTTPException(400, "预支来源无效")

    approval_status = AdvanceApprovalStatus.APPROVED.value
    if current_user.role == Role.SUPERVISOR:
        owners, _ = await employee_account_roles(db, [emp])
        owner = owners.get(emp.id)
        if emp.user_id == current_user.id or emp.id == current_user.attendance_employee_id or (owner and owner.id == current_user.id):
            approval_status = AdvanceApprovalStatus.PENDING.value

    adv = EmployeeAdvance(
        warehouse_id=wh_id,
        employee_id=emp.id,
        amount=req.amount,
        currency=currency,
        advance_date=adv_dt,
        period=period,
        half=half,
        source=req.source,
        fund_account_id=req.fund_account_id if req.source == "fund" else None,
        remark=req.remark,
        operator_id=current_user.id,
        deducted_amount=0,
        status="unpaid",
        approval_status=approval_status,
        expense_tracking_enabled=True,
    )
    db.add(adv)
    await db.flush()

    # 备用金联动：来源选备用金账户时，自动记一笔开销
    if req.source == "fund" and fund_account:
        spent_regular = float((await db.execute(
            select(func.coalesce(func.sum(ExpenseFundItem.amount), 0)).where(
                ExpenseFundItem.fund_id == fund_account.id,
                ExpenseFundItem.category != "报销",
                ExpenseFundItem.review_status != ReviewStatus.REJECTED.value,
            )
        )).scalar() or 0)
        available = fund_available(fund_account.remaining_balance, spent_regular)
        if req.amount > available:
            raise HTTPException(400, f"超出备用金可用余额（可用 {available:,.2f}）")
        fund_item = ExpenseFundItem(
            fund_id=fund_account.id,
            expense_date=datetime.combine(adv_dt, datetime.min.time()),
            category="预支工资",
            amount=req.amount,
            currency=currency,
            description=f"预支工资 {emp.name}",
            review_status=ReviewStatus.APPROVED.value,
        )
        db.add(fund_item)
        await db.flush()
        adv.fund_item_id = fund_item.id

    await create_advance_expense(db, adv, current_user)

    return {"message": "预支记录已创建", "id": adv.id, **_approval_fields(adv)}


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
    approval_status: Optional[Literal["pending", "approved", "rejected", "待审批", "已通过", "已驳回"]] = None,
    current_user: User = Depends(check_staff_permission(MENU_PERMISSIONS_BY_KEY["employee_advances"].label)),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in (Role.SUPER_ADMIN, Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF):
        raise HTTPException(403, "无权限")

    wh_ids = get_wh_ids(current_user)
    if not wh_ids:
        return {"data": [], "total": 0}

    q = select(EmployeeAdvance).where(EmployeeAdvance.warehouse_id.in_(wh_ids))
    if approval_status is not None:
        normalized = {label: value for value, label in ADVANCE_APPROVAL_LABELS.items()}.get(approval_status, approval_status)
        q = q.where(EmployeeAdvance.approval_status == normalized)
    if employee_id:
        q = q.where(EmployeeAdvance.employee_id == employee_id)
    if period:
        q = q.where(EmployeeAdvance.period == period)

    rows = (await db.execute(q.order_by(EmployeeAdvance.advance_date.desc(), EmployeeAdvance.id.desc()))).scalars().all()

    emp_ids = {r.employee_id for r in rows}
    op_ids = {r.operator_id for r in rows if r.operator_id}
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
            "remaining_amount": round((r.amount or 0) - (r.deducted_amount or 0), 2),
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
        select(EmployeeAdvance).where(EmployeeAdvance.warehouse_id.in_(wh_ids))
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

    emp = (await db.execute(
        select(Employee).where(Employee.warehouse_id == wh_id, Employee.user_id == current_user.id, Employee.is_deleted == False)
    )).scalar_one_or_none()
    if attendance_supervisor(current_user):
        emp = current_user._attendance_employee
    if not emp:
        emp = (await db.execute(
            select(Employee).where(Employee.warehouse_id == wh_id, Employee.name == current_user.display_name, Employee.is_deleted == False)
        )).scalar_one_or_none()
    if not emp:
        return {"total_by_currency": [], "data": []}

    advances = (await db.execute(
        select(EmployeeAdvance).where(EmployeeAdvance.employee_id == emp.id, EmployeeAdvance.status != "deducted")
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


@router.delete("/{advance_id}")
async def delete_advance(
    advance_id: int,
    current_user: User = Depends(check_staff_permission(MENU_PERMISSIONS_BY_KEY["employee_advances"].label)),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in (Role.SUPER_ADMIN, Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF):
        raise HTTPException(403, "只有仓库管理员/主管可以删除预支记录")

    wh_id = get_wh_id(current_user)
    if not wh_id:
        raise HTTPException(400, "请先选择仓库")

    r = (await db.execute(
        select(EmployeeAdvance).where(EmployeeAdvance.id == advance_id, EmployeeAdvance.warehouse_id == wh_id).with_for_update()
    )).scalar_one_or_none()
    if not r:
        raise HTTPException(404, "预支记录不存在")

    before = {"employee_id": r.employee_id, "amount": r.amount, "currency": r.currency,
              "fund_item_id": r.fund_item_id, **_approval_fields(r)}
    await delete_advance_expense(db, r, current_user)
    await record_history(db, module="employee_advances", record_id=r.id, operator=current_user,
        operation_type="delete", before=before, warehouse_id=wh_id)
    await db.delete(r)
    await db.flush()
    return {"message": "预支记录已删除"}


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
    if advance.approval_status != AdvanceApprovalStatus.PENDING.value:
        raise HTTPException(400, "只有待审批的预支可以审批")
    before = {"amount": advance.amount, **_approval_fields(advance)}
    advance.approval_status = (AdvanceApprovalStatus.APPROVED.value if action == "approve"
                               else AdvanceApprovalStatus.REJECTED.value)
    advance.reviewer_id = current_user.id
    advance.reviewed_at = thai_now()
    advance.reject_reason = reason if action == "reject" else None
    if action == "approve":
        await create_advance_expense(db, advance, current_user)
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

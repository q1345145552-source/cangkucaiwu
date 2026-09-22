from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.models.employee_advance import EmployeeAdvance
from app.models.employee import Employee
from app.models.user import User
from app.models.expense_fund import ExpenseFund, ExpenseFundItem, ReviewStatus
from app.core.permissions import get_current_user, get_wh_id, get_wh_ids, Role
from app.core.timezone import thai_now, thai_today
from app.services.flow_rules import fund_available
from pydantic import BaseModel
from datetime import datetime, date
from typing import Optional, List

router = APIRouter()


class AdvanceCreate(BaseModel):
    employee_id: int
    amount: float
    advance_date: str  # YYYY-MM-DD
    source: str  # supervisor / fund
    fund_account_id: Optional[int] = None
    remark: Optional[str] = None


@router.post("")
async def create_advance(
    req: AdvanceCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
        raise HTTPException(403, "只有仓库管理员/主管可以记预支")

    wh_id = get_wh_id(current_user)
    if not wh_id:
        raise HTTPException(400, "请先选择仓库")

    if req.amount is None or req.amount <= 0:
        raise HTTPException(400, "预支金额必须大于0")

    try:
        adv_dt = datetime.strptime(req.advance_date, "%Y-%m-%d").date()
    except:
        raise HTTPException(400, "预支日期格式错误 YYYY-MM-DD")

    emp = (await db.execute(
        select(Employee).where(Employee.id == req.employee_id, Employee.warehouse_id == wh_id, Employee.is_deleted == False)
    )).scalar_one_or_none()
    if not emp:
        raise HTTPException(404, "员工不存在")

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

    adv = EmployeeAdvance(
        warehouse_id=wh_id,
        employee_id=req.employee_id,
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
        db.add(ExpenseFundItem(
            fund_id=fund_account.id,
            expense_date=datetime.combine(adv_dt, datetime.min.time()),
            category="预支工资",
            amount=req.amount,
            currency=currency,
            description=f"预支工资 {emp.name}",
            review_status=ReviewStatus.APPROVED.value,
        ))
        await db.flush()

    return {"message": "预支记录已创建", "id": adv.id}


@router.get("")
async def list_advances(
    employee_id: Optional[int] = None,
    period: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
        raise HTTPException(403, "无权限")

    wh_ids = get_wh_ids(current_user)
    if not wh_ids:
        return {"data": [], "total": 0}

    q = select(EmployeeAdvance).where(EmployeeAdvance.warehouse_id.in_(wh_ids))
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
            "employee_id": r.employee_id,
            "employee_name": emp_map.get(r.employee_id).name if emp_map.get(r.employee_id) else "",
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
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
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
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """劳工端：我的欠款（按币种分组）"""
    if current_user.role != Role.WAREHOUSE_LABOR:
        raise HTTPException(403, "无权限")

    wh_id = get_wh_id(current_user)
    if not wh_id:
        return {"total_by_currency": []}

    emp = (await db.execute(
        select(Employee).where(Employee.warehouse_id == wh_id, Employee.user_id == current_user.id, Employee.is_deleted == False)
    )).scalar_one_or_none()
    if not emp:
        emp = (await db.execute(
            select(Employee).where(Employee.warehouse_id == wh_id, Employee.name == current_user.display_name, Employee.is_deleted == False)
        )).scalar_one_or_none()
    if not emp:
        return {"total_by_currency": []}

    advances = (await db.execute(
        select(EmployeeAdvance).where(EmployeeAdvance.employee_id == emp.id, EmployeeAdvance.status != "deducted")
    )).scalars().all()

    by_currency = {}
    for a in advances:
        rem = round((a.amount or 0) - (a.deducted_amount or 0), 2)
        if rem > 0:
            cur = a.currency or "THB"
            by_currency[cur] = round(by_currency.get(cur, 0) + rem, 2)

    return {"total_by_currency": [{"currency": k, "total": v} for k, v in sorted(by_currency.items())]}


@router.delete("/{advance_id}")
async def delete_advance(
    advance_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
        raise HTTPException(403, "只有仓库管理员/主管可以删除预支记录")

    wh_id = get_wh_id(current_user)
    if not wh_id:
        raise HTTPException(400, "请先选择仓库")

    r = (await db.execute(
        select(EmployeeAdvance).where(EmployeeAdvance.id == advance_id, EmployeeAdvance.warehouse_id == wh_id)
    )).scalar_one_or_none()
    if not r:
        raise HTTPException(404, "预支记录不存在")

    await db.delete(r)
    await db.flush()
    return {"message": "预支记录已删除"}

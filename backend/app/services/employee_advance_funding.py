"""新预支三种资金来源；待审批只保存选择，通过时在调用方事务内执行。"""
from datetime import datetime, time
from decimal import Decimal, InvalidOperation

from fastapi import HTTPException
from sqlalchemy import func, select

from app.core.timezone import thai_now
from app.models.cash_advance import CashAdvance
from app.models.customer import PaymentAccount
from app.models.employee import Employee
from app.models.employee_advance import EmployeeAdvance, AdvanceApprovalStatus
from app.models.expense_fund import ExpenseFund, ExpenseFundItem, ReviewStatus
from app.models.user import User
from app.services.account_balances import current_account_balances
from app.services.data_history import record_history
from app.services.balance_warning import balance_warning, record_balance_warning
from app.services.employee_advance_expense import create_advance_expense

SOURCES = {"company_account": "公司账户", "cash_advance": "垫款单", "expense_fund": "备用金"}


def money(value):
    return Decimal(str(value or 0)).quantize(Decimal("0.01"))


def validate_money(value):
    try:
        raw = Decimal(str(value))
        if not raw.is_finite() or raw <= 0 or raw != money(raw):
            raise ValueError
        return raw
    except (ValueError, InvalidOperation):
        raise HTTPException(400, "预支金额必须大于0，且最多两位小数")


async def fund_available_amount(db, fund):
    spent = (await db.execute(select(func.coalesce(func.sum(ExpenseFundItem.amount), 0)).where(
        ExpenseFundItem.fund_id == fund.id, ExpenseFundItem.category != "报销",
        ExpenseFundItem.review_status != ReviewStatus.REJECTED.value, ExpenseFundItem.not_voided(),
    ))).scalar_one()
    return max(money(fund.remaining_balance) - money(spent), Decimal(0))


async def validate_funding(db, source, warehouse_id, amount, *, currency=None,
                           payment_account_id=None, cash_advance_id=None, fund_account_id=None, lock=False, exclude_id=None):
    if not source:
        raise HTTPException(400, "请选择资金来源")
    if source not in SOURCES:
        raise HTTPException(400, "资金来源无效")
    amount = validate_money(amount)
    if source == "company_account":
        if not payment_account_id:
            raise HTTPException(400, "请选择公司付款账户")
        query = select(PaymentAccount).where(PaymentAccount.id == payment_account_id,
            PaymentAccount.warehouse_id == warehouse_id)
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        account = (await db.execute(query)).scalar_one_or_none()
        if account is None:
            raise HTTPException(400, "付款账户不存在或不属于当前仓库")
        if account.status not in (None, "active"):
            raise HTTPException(400, "付款账户已停用")
        selected_currency = currency or account.currency or "THB"
        if selected_currency != (account.currency or "THB"):
            raise HTTPException(400, "付款账户币种与预支不一致")
        return selected_currency, account
    if source == "cash_advance":
        if not cash_advance_id:
            raise HTTPException(400, "请选择垫款单")
        query = select(CashAdvance).where(CashAdvance.id == cash_advance_id,
            CashAdvance.warehouse_id == warehouse_id)
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        loan = (await db.execute(query)).scalar_one_or_none()
        if loan is None:
            raise HTTPException(400, "垫款单不存在或不属于当前仓库")
        if loan.status != "confirmed":
            raise HTTPException(400, "只能使用已确认的垫款单")
        selected_currency = currency or "THB"
        if loan.currency != selected_currency:
            raise HTTPException(400, "垫款单币种与预支不一致")
        from app.services.cash_advance_payroll import payroll_usage_totals, usage_amounts
        from app.services.cash_advance_usage import reimbursement_usage_totals, employee_advance_usage_totals
        wages = (await payroll_usage_totals(db, [loan]))[loan.id]
        expenses = (await reimbursement_usage_totals(db, [loan]))[loan.id]
        advances = (await employee_advance_usage_totals(db, [loan], exclude_id=exclude_id))[loan.id]
        return selected_currency, loan
    if not fund_account_id:
        raise HTTPException(400, "请选择备用金账户")
    query = select(ExpenseFund).where(ExpenseFund.id == fund_account_id,
        ExpenseFund.warehouse_id == warehouse_id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    fund = (await db.execute(query)).scalar_one_or_none()
    if fund is None:
        raise HTTPException(400, "备用金账户不存在或不属于当前仓库")
    if fund.status != "active":
        raise HTTPException(400, "备用金账户已停用或结清")
    selected_currency = currency or fund.currency or "THB"
    if selected_currency != (fund.currency or "THB"):
        raise HTTPException(400, "备用金币种与预支不一致")
    available = await fund_available_amount(db, fund)
    return selected_currency, fund


async def apply_advance_funding(db, advance, operator):
    if advance.approval_status != AdvanceApprovalStatus.APPROVED.value:
        return
    if advance.funding_source is None:
        # 老单审批沿用原成本处理，不猜账户、不补扣资金或补占垫款。
        await create_advance_expense(db, advance, operator, paid_at=advance.reviewed_at)
        return
    # 审批时尚未将新状态 flush，避免把本笔算作已占用额度。
    with db.no_autoflush:
        _, source = await validate_funding(db, advance.funding_source, advance.warehouse_id, advance.amount,
            currency=advance.currency, payment_account_id=advance.payment_account_id,
            cash_advance_id=advance.cash_advance_id, fund_account_id=advance.fund_account_id, lock=True, exclude_id=advance.id)
    warning = None
    if advance.funding_source == 'company_account':
        before_balance = (await current_account_balances(db,[source]))[source.id]
        warning = balance_warning(before_balance,advance.amount,advance.currency,source='company_account',source_id=source.id)
    elif advance.funding_source == 'expense_fund':
        warning=balance_warning(await fund_available_amount(db,source),advance.amount,advance.currency,source='expense_fund',source_id=source.id)
    elif advance.funding_source == 'cash_advance':
        from app.services.cash_advance_payroll import payroll_usage_totals,usage_amounts
        from app.services.cash_advance_usage import reimbursement_usage_totals,employee_advance_usage_totals
        used=(await payroll_usage_totals(db,[source]))[source.id]
        other=(await reimbursement_usage_totals(db,[source]))[source.id]
        own=(await employee_advance_usage_totals(db,[source],exclude_id=advance.id))[source.id]
        warning=balance_warning(usage_amounts(source,used,other,own)['available_amount'],advance.amount,advance.currency,source='cash_advance',source_id=source.id)
    employee = await db.get(Employee, advance.employee_id)
    if advance.funding_source == "company_account":
        await create_advance_expense(db, advance, operator, paid_at=advance.reviewed_at)
    elif advance.funding_source == "expense_fund":
        item = ExpenseFundItem(fund_id=source.id, expense_date=datetime.combine(advance.advance_date, time.min),
            category="预支工资", amount=advance.amount, currency=advance.currency,
            description=f"员工预支 #{advance.id} {employee.name}",
            review_status=ReviewStatus.APPROVED.value, cost_record_only=True)
        db.add(item)
        await db.flush()
        advance.fund_item_id = item.id
    await record_history(db, module="employee_advances", record_id=advance.id, operator=operator,
        operation_type="funding", after={"funding_source": advance.funding_source,
            "amount": advance.amount, "currency": advance.currency, "payment_account_id": advance.payment_account_id,
            "cash_advance_id": advance.cash_advance_id, "fund_item_id": advance.fund_item_id,
            "expense_record_id": advance.expense_record_id}, warehouse_id=advance.warehouse_id)

    await record_balance_warning(db,warning,operator,module='employee_advances',record_id=advance.id,warehouse_id=advance.warehouse_id)
    return warning


async def funding_options(db, warehouse_id):
    from app.services.cash_advance_payroll import payroll_usage_totals, usage_amounts
    from app.services.cash_advance_usage import reimbursement_usage_totals, employee_advance_usage_totals
    accounts = (await db.execute(select(PaymentAccount).where(PaymentAccount.warehouse_id == warehouse_id,
        PaymentAccount.status.in_(["active"]) | PaymentAccount.status.is_(None)).order_by(PaymentAccount.id))).scalars().all()
    balances = await current_account_balances(db, accounts)
    loans = (await db.execute(select(CashAdvance).where(CashAdvance.warehouse_id == warehouse_id,
        CashAdvance.status == "confirmed").order_by(CashAdvance.id.desc()))).scalars().all()
    wages, expenses, advances = await payroll_usage_totals(db, loans), await reimbursement_usage_totals(db, loans), await employee_advance_usage_totals(db, loans)
    funds = (await db.execute(select(ExpenseFund, User.display_name).join(User, User.id == ExpenseFund.employee_id).where(
        ExpenseFund.warehouse_id == warehouse_id, ExpenseFund.status == "active"))).all()
    return {"accounts": [{"id": a.id, "account_name": a.account_name, "account_type": a.account_type,
                "currency": a.currency or "THB", "current_balance": float(balances[a.id])} for a in accounts],
        "cash_advances": [{"id": a.id, "payer_name": a.payer_name, "currency": a.currency,
            "outstanding_amount": float(a.amount - a.repaid_amount), **usage_amounts(a, wages[a.id], expenses[a.id], advances[a.id])} for a in loans],
        "funds": [{"id": f.id, "employee_name": name, "currency": f.currency or "THB",
            "available": float(await fund_available_amount(db, f))} for f, name in funds]}

"""保留月初余额；扣除有效垫款归还及公司账户工资，撤销后自动恢复。"""
from decimal import Decimal
from sqlalchemy import select, func
from app.models.cash_advance_repayment import CashAdvanceRepayment
from app.models.income_expense import ExpenseRecord
from app.models.payroll import PayrollRecord


async def current_account_balances(db, accounts):
    if not accounts:
        return {}
    amounts = dict((await db.execute(select(
        CashAdvanceRepayment.account_id, func.sum(CashAdvanceRepayment.amount),
    ).where(
        CashAdvanceRepayment.account_id.in_([a.id for a in accounts]),
        CashAdvanceRepayment.status == "active",
    ).group_by(CashAdvanceRepayment.account_id))).all())
    payroll = (await db.execute(select(ExpenseRecord.account_id, ExpenseRecord.amount).join(
        PayrollRecord, PayrollRecord.expense_record_id == ExpenseRecord.id,
    ).where(
        ExpenseRecord.account_id.in_([a.id for a in accounts]),
        PayrollRecord.cash_advance_id.is_(None), PayrollRecord.disbursed.is_(True),
        PayrollRecord.voided.is_not(True), PayrollRecord.warehouse_id == ExpenseRecord.warehouse_id,
    ))).all()
    for account_id, amount in payroll:
        amounts[account_id] = Decimal(str(amounts.get(account_id) or 0)) + Decimal(str(amount)).quantize(Decimal("0.01"))
    return {a.id: Decimal(str(a.opening_balance or 0)) - Decimal(str(amounts.get(a.id) or 0)) for a in accounts}

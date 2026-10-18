"""保留月初余额；有效垫款归还作为账户资金减项，撤销后自动恢复。"""
from decimal import Decimal
from sqlalchemy import select, func
from app.models.cash_advance_repayment import CashAdvanceRepayment


async def current_account_balances(db, accounts):
    if not accounts:
        return {}
    amounts = dict((await db.execute(select(
        CashAdvanceRepayment.account_id, func.sum(CashAdvanceRepayment.amount),
    ).where(
        CashAdvanceRepayment.account_id.in_([a.id for a in accounts]),
        CashAdvanceRepayment.status == "active",
    ).group_by(CashAdvanceRepayment.account_id))).all())
    return {a.id: Decimal(str(a.opening_balance or 0)) - Decimal(str(amounts.get(a.id) or 0)) for a in accounts}

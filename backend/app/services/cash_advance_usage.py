"""垫款的报销使用金额；与工资共用可用额度，不减少公司剩余欠款。"""
from decimal import Decimal
from sqlalchemy import select, func
from app.models.reimbursement_payment import ReimbursementPayment
from app.models.reimbursement import Reimbursement
from app.models.user import User


async def reimbursement_usage_totals(db, advances):
    if not advances:
        return {}
    rows = (await db.execute(select(
        ReimbursementPayment.cash_advance_id, func.sum(ReimbursementPayment.amount),
    ).where(
        ReimbursementPayment.cash_advance_id.in_([a.id for a in advances]),
        ReimbursementPayment.status == "active", ReimbursementPayment.funding_source == "cash_advance",
    ).group_by(ReimbursementPayment.cash_advance_id))).all()
    amounts = dict(rows)
    return {a.id: Decimal(str(amounts.get(a.id) or 0)) for a in advances}


async def reimbursement_usage(db, advance):
    rows = (await db.execute(select(ReimbursementPayment, User.display_name).join(
        Reimbursement, Reimbursement.id == ReimbursementPayment.reimbursement_id,
    ).outerjoin(User, User.id == Reimbursement.employee_id).where(
        ReimbursementPayment.cash_advance_id == advance.id,
        ReimbursementPayment.warehouse_id == advance.warehouse_id,
        ReimbursementPayment.status == "active", ReimbursementPayment.funding_source == "cash_advance",
    ).order_by(ReimbursementPayment.id.desc()))).all()
    return {"reimbursement_used_amount": float(sum((p.amount for p, _ in rows), Decimal("0"))),
        "data": [{"payment_id": p.id, "reimbursement_id": p.reimbursement_id,
            "employee_name": name or "", "amount": float(p.amount), "currency": p.currency,
            "paid_at": p.paid_at.isoformat(), "paid_by_name": p.paid_by_name} for p, name in rows]}

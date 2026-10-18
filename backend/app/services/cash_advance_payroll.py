"""工资使用垫款的关联和额度；与公司归还垫款的债务金额分开。"""
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select

from app.models.cash_advance import CashAdvance
from app.models.employee import Employee
from app.models.payroll import PayrollRecord

# 现有工资计算、发放统一使用泰铢，本轮不引入另一套工资币种或换汇。
PAYROLL_CURRENCY = "THB"


async def payroll_usage_totals(db, advances):
    if not advances:
        return {}
    warehouses = {a.id: a.warehouse_id for a in advances}
    totals = {a.id: Decimal("0.00") for a in advances}
    rows = (await db.execute(select(
        PayrollRecord.cash_advance_id, PayrollRecord.warehouse_id, PayrollRecord.net_pay,
    ).where(
        PayrollRecord.cash_advance_id.in_(warehouses),
        PayrollRecord.disbursed.is_(True), PayrollRecord.voided.is_not(True),
    ))).all()
    for advance_id, warehouse_id, amount in rows:
        if warehouses[advance_id] == warehouse_id:
            totals[advance_id] += Decimal(str(amount)).quantize(Decimal("0.01"))
    return totals


def usage_amounts(advance, used):
    outstanding = max(advance.amount - advance.repaid_amount, Decimal("0"))
    unused = max(advance.amount - used, Decimal("0"))
    return {
        "payroll_used_amount": float(used),
        "payroll_unused_amount": float(unused),
        "payroll_available_amount": float(min(outstanding, unused)) if advance.status == "confirmed" and advance.currency == PAYROLL_CURRENCY else 0.0,
    }


async def payroll_usage(db, advance):
    rows = (await db.execute(select(PayrollRecord, Employee.name).outerjoin(
        Employee, Employee.id == PayrollRecord.employee_id,
    ).where(
        PayrollRecord.cash_advance_id == advance.id,
        PayrollRecord.warehouse_id == advance.warehouse_id,
        PayrollRecord.disbursed.is_(True), PayrollRecord.voided.is_not(True),
    ).order_by(PayrollRecord.id.desc()))).all()
    used = sum((Decimal(str(r.net_pay)).quantize(Decimal("0.01")) for r, _ in rows), Decimal("0.00"))
    return {**usage_amounts(advance, used), "data": [{
        "payroll_record_id": r.id, "employee_name": name or "", "period": r.period,
        "settle_start_date": r.settle_start_date.isoformat() if r.settle_start_date else None,
        "settle_end_date": r.settle_end_date.isoformat() if r.settle_end_date else None,
        "amount": r.net_pay, "currency": PAYROLL_CURRENCY,
        "disbursed_at": r.disbursed_at.isoformat() if r.disbursed_at else None,
    } for r, name in rows]}


async def lock_payroll_advance(db, warehouse_id, advance_id, records):
    if not advance_id:
        raise HTTPException(400, "请选择工资垫款单")
    advance = (await db.execute(select(CashAdvance).where(
        CashAdvance.id == advance_id, CashAdvance.warehouse_id == warehouse_id,
    ).with_for_update())).scalar_one_or_none()
    if advance is None:
        raise HTTPException(400, "垫款单不存在或不属于当前仓库")
    if advance.status != "confirmed":
        raise HTTPException(400, "只能使用已确认的垫款单发放工资")
    if advance.currency != PAYROLL_CURRENCY:
        raise HTTPException(400, "垫款单币种与工资单不一致，工资以泰铢发放")
    from app.services.payroll_expense import expense_amount
    total = sum((Decimal(str(expense_amount(r))) for r in records), Decimal("0.00"))
    if total > advance.amount - advance.repaid_amount:
        raise HTTPException(400, "垫款单剩余金额不足")
    used = (await payroll_usage_totals(db, [advance]))[advance.id]
    if total > advance.amount - used:
        raise HTTPException(400, "垫款单剩余金额不足")
    return advance

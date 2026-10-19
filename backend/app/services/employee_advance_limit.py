"""登记预支时校验工资额度；不参与工资抵扣或审批。"""
from decimal import Decimal, InvalidOperation, ROUND_DOWN, ROUND_HALF_UP
from datetime import datetime, time, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import and_, or_, select

from app.core.timezone import THAI_TZ
from app.models.employee_advance import EmployeeAdvance, AdvanceApprovalStatus
from app.models.recharge import ExchangeRate
from app.models.salary_template import SalaryTemplate

CENT = Decimal("0.01")


def monthly_salary_standard(template):
    """模板 hourly/daily 的 amount 均存日薪，与现有算薪口径一致。"""
    if template is None:
        return None
    try:
        amount = Decimal(str(template.amount))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not amount.is_finite() or amount < 0:
        return None
    if template.type == "monthly":
        monthly = amount
    elif template.type == "daily":
        monthly = amount * 26
    elif template.type == "hourly":
        hourly_rate = amount / 8
        monthly = hourly_rate * 8 * 26
    else:
        return None
    return monthly.quantize(CENT, rounding=ROUND_HALF_UP)


async def _rate_to_thb(db, warehouse_id, currency, on_date):
    if currency == "THB":
        return Decimal(1)
    # 以预支登记日期在泰国时区的一天为界，不拿之后生效的汇率回填。
    cutoff = datetime.combine(on_date + timedelta(days=1), time.min, THAI_TZ).astimezone(timezone.utc)
    rate = (await db.execute(select(ExchangeRate).where(
        ExchangeRate.warehouse_id == warehouse_id,
        ExchangeRate.effective_from < cutoff,
        or_(
            and_(ExchangeRate.from_currency == currency, ExchangeRate.to_currency == "THB"),
            and_(ExchangeRate.from_currency == "THB", ExchangeRate.to_currency == currency),
        ),
    ).order_by(ExchangeRate.effective_from.desc(), ExchangeRate.id.desc()).limit(1))).scalar_one_or_none()
    if rate is None:
        raise HTTPException(400, f"未找到 {on_date} 已生效的 {currency}→THB 汇率，请先设置汇率后再登记预支")
    value = Decimal(str(rate.rate))
    if not value.is_finite() or value <= 0:
        raise HTTPException(400, f"{currency}→THB 汇率无效，请先设置有效汇率后再登记预支")
    return value if rate.from_currency == currency else Decimal(1) / value


async def check_advance_limit(db, employee, amount, currency, advance_date):
    """调用方须在同一事务持有员工行锁；只查询，不修改已有预支或工资。"""
    template = (await db.execute(select(SalaryTemplate).where(
        SalaryTemplate.id == employee.salary_template_id,
        SalaryTemplate.warehouse_id == employee.warehouse_id,
    ))).scalar_one_or_none() if employee.salary_template_id else None
    monthly = monthly_salary_standard(template)
    if monthly is None:
        warning = ("该员工没有薪资模板 无法校验预支上限" if template is None
                   else "该员工薪资模板金额或类型无效 无法校验预支上限")
        return {"checked": False, "currency": "THB", "warning": warning}

    outstanding = (await db.execute(select(EmployeeAdvance).where(
        EmployeeAdvance.employee_id == employee.id,
        EmployeeAdvance.warehouse_id == employee.warehouse_id,
        EmployeeAdvance.not_voided(),
        or_(EmployeeAdvance.status.is_(None), EmployeeAdvance.status != "deducted"),
        EmployeeAdvance.approval_status.in_((
            AdvanceApprovalStatus.APPROVED.value, AdvanceApprovalStatus.PENDING.value,
        )),
    ))).scalars().all()
    rates = {}

    async def converted(value, source_currency, on_date):
        key = (source_currency, on_date)
        if key not in rates:
            rates[key] = await _rate_to_thb(db, employee.warehouse_id, source_currency, on_date)
        return value * rates[key]

    occupied = Decimal(0)
    for advance in outstanding:
        remaining = Decimal(str(advance.amount))
        if advance.approval_status == AdvanceApprovalStatus.APPROVED.value:
            remaining -= Decimal(str(advance.deducted_amount or 0))
        if remaining <= 0:
            continue
        occupied += await converted(remaining, advance.currency or "THB", advance.advance_date)

    requested = await converted(Decimal(str(amount)), currency, advance_date)
    available = max(monthly - occupied, Decimal(0))
    shown_available = available.quantize(CENT, rounding=ROUND_DOWN)
    if occupied + requested > monthly:
        message = f"预支合计不能超过当月工资，当前可用 {shown_available:.2f} 元"
        if currency != "THB":
            original_available = (available / rates[(currency, advance_date)]).quantize(CENT, rounding=ROUND_DOWN)
            message += f"（THB，折合 {original_available:.2f} {currency}）"
        raise HTTPException(400, message)
    return {
        "checked": True, "currency": "THB", "monthly_salary": float(monthly),
        "occupied_amount": float(occupied.quantize(CENT, rounding=ROUND_HALF_UP)),
        "requested_amount": float(requested.quantize(CENT, rounding=ROUND_HALF_UP)),
        "available_amount": float(shown_available),
        "remaining_amount": float((available - requested).quantize(CENT, rounding=ROUND_DOWN)),
    }

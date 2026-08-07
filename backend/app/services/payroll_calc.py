"""工资计算的纯函数（无 DB 依赖），便于单元测试与复用。

把"钱"相关的核心公式抽出来，保证：
- 迟到扣款：半小时=时薪×0.5，一小时=时薪×1
- 请假/缺勤扣款：按有效日薪×天数
- 净工资 = 底薪 + 加班 - 扣款，且不小于 0
"""
from dataclasses import dataclass


def late_penalty(hourly_rate: float, late_half_count: int, late_one_count: int) -> float:
    return round(late_half_count * hourly_rate * 0.5 + late_one_count * hourly_rate, 2)


def regular_effective_daily(base_salary: float, total_days_in_month: int) -> float:
    """正式员工日薪 = 月基本工资 / (当月天数 - 2 个固定休息日)。"""
    adjusted = total_days_in_month - 2
    if adjusted <= 0:
        adjusted = total_days_in_month
    return base_salary / adjusted


@dataclass
class PayResult:
    base_pay: float
    overtime_pay: float
    late_penalty: float
    leave_deduction: float
    absence_deduction: float
    gross_pay: float
    total_deductions: float
    net_pay: float


def compute_pay(
    *,
    base_pay: float,
    overtime_pay: float,
    effective_daily: float,
    hourly_rate: float,
    late_half_count: int,
    late_one_count: int,
    leave_days: int,
    absence_days: int,
) -> PayResult:
    lp = late_penalty(hourly_rate, late_half_count, late_one_count)
    leave_ded = round(effective_daily * leave_days, 2)
    absence_ded = round(effective_daily * absence_days, 2)
    total_ded = round(lp + leave_ded + absence_ded, 2)
    gross = round(base_pay + overtime_pay, 2)
    net = round(max(gross - total_ded, 0), 2)  # 下限保护：不出现负工资
    return PayResult(
        base_pay=round(base_pay, 2),
        overtime_pay=round(overtime_pay, 2),
        late_penalty=lp,
        leave_deduction=leave_ded,
        absence_deduction=absence_ded,
        gross_pay=gross,
        total_deductions=total_ded,
        net_pay=net,
    )

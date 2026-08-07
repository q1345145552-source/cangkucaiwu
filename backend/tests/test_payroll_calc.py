"""工资计算纯函数单元测试。运行：cd backend && pytest"""
from app.services.payroll_calc import compute_pay, late_penalty, regular_effective_daily


def test_late_penalty_half_and_one_hour():
    # 时薪 50：迟到半小时扣 25，迟到一小时扣 50
    assert late_penalty(50, late_half_count=1, late_one_count=0) == 25.0
    assert late_penalty(50, late_half_count=0, late_one_count=1) == 50.0
    assert late_penalty(50, late_half_count=2, late_one_count=1) == 100.0


def test_regular_effective_daily_subtracts_two_rest_days():
    # 30 天月，月薪 12000 -> 12000 / (30-2) = 428.57...
    assert round(regular_effective_daily(12000, 30), 2) == 428.57
    # 边界：total_days<=2 时退回用总天数，避免除0
    assert regular_effective_daily(1000, 2) == 500.0


def test_net_pay_never_negative():
    # 扣款远超应发，净工资应为 0 而不是负数
    r = compute_pay(
        base_pay=100, overtime_pay=0, effective_daily=400, hourly_rate=50,
        late_half_count=0, late_one_count=0, leave_days=0, absence_days=5,
    )
    assert r.absence_deduction == 2000.0
    assert r.net_pay == 0.0


def test_net_pay_normal_case():
    r = compute_pay(
        base_pay=10000, overtime_pay=500, effective_daily=400, hourly_rate=50,
        late_half_count=1, late_one_count=0, leave_days=1, absence_days=0,
    )
    # 扣款 = 25(迟到) + 400(请假) = 425；净 = 10500 - 425 = 10075
    assert r.late_penalty == 25.0
    assert r.leave_deduction == 400.0
    assert r.gross_pay == 10500.0
    assert r.net_pay == 10075.0

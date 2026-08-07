"""流程规则纯函数单元测试，覆盖本轮修复的核心判定。运行：cd backend && pytest"""
from app.services.flow_rules import (
    exceeds_credit_limit,
    currencies_match,
    can_refund_fund_item,
    is_reviewable_reimb,
    fund_available,
    should_settle_bill,
)


# —— #7 授信额度 ——
def test_credit_limit():
    assert exceeds_credit_limit(current_debt=800, amount=300, credit_limit=1000) is True   # 1100>1000
    assert exceeds_credit_limit(current_debt=800, amount=200, credit_limit=1000) is False  # 1000==1000 不超
    assert exceeds_credit_limit(current_debt=5000, amount=1, credit_limit=0) is False       # 0/None=不限
    assert exceeds_credit_limit(current_debt=5000, amount=1, credit_limit=None) is False


# —— #8 对账币种 ——
def test_currency_match():
    assert currencies_match("THB", "THB") is True
    assert currencies_match("THB", "CNY") is False
    assert currencies_match(None, "THB") is True   # 空按默认 THB
    assert currencies_match("CNY", None) is False


# —— #1 报销/备用金重复退款幂等 ——
def test_refund_idempotency():
    assert can_refund_fund_item("pending") is True
    assert can_refund_fund_item("approved") is True
    assert can_refund_fund_item("rejected") is False   # 已驳回不再退回，防止余额膨胀


# —— #9 报销可审批状态前置 ——
def test_reviewable_reimb():
    assert is_reviewable_reimb("pending") is True
    assert is_reviewable_reimb("fund_linked") is True
    assert is_reviewable_reimb("partially_approved") is True
    assert is_reviewable_reimb("paid") is False        # 已付款不可再审
    assert is_reviewable_reimb("rejected") is False


# —— #5 备用金可用余额 ——
def test_fund_available():
    assert fund_available(5000, 1200) == 3800
    assert fund_available(None, None) == 0
    assert fund_available(1000, 0) == 1000


# —— #3/#4 付款计划账单结算判定 ——
def test_should_settle_bill():
    wh = [1, 2]
    # 本仓、未付清 -> 结算
    assert should_settle_bill(1, "pending", paid_amount=0, amount=100, wh_ids=wh) is True
    # 他仓 -> 不结算（防跨仓库篡改）
    assert should_settle_bill(9, "pending", paid_amount=0, amount=100, wh_ids=wh) is False
    # 已付清 -> 跳过（幂等）
    assert should_settle_bill(1, "paid", paid_amount=100, amount=100, wh_ids=wh) is False
    # 金额已够 -> 跳过
    assert should_settle_bill(1, "partially_paid", paid_amount=100, amount=100, wh_ids=wh) is False
    # 部分付款、未付清 -> 结算
    assert should_settle_bill(2, "partially_paid", paid_amount=40, amount=100, wh_ids=wh) is True

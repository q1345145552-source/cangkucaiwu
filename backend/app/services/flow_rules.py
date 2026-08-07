"""业务流程规则的纯函数（无 DB / 无框架依赖），作为唯一判定来源，方便单测与复用。

把散落在各接口里的"能不能做"判断集中到这里：
- 授信是否超限
- 对账币种是否一致
- 备用金开销退款是否幂等（避免重复退回）
- 报销单当前状态是否可审批
- 备用金可用余额
- 付款计划执行时某张账单是否应结算
"""

# —— 账期 ——
def exceeds_credit_limit(current_debt: float, amount: float, credit_limit) -> bool:
    """当前欠款 + 本次发货是否超过授信额度（额度为空/0 视为不限）。"""
    if not credit_limit:
        return False
    return (current_debt + amount) > credit_limit


# —— 对账 ——
def currencies_match(a, b, default: str = "THB") -> bool:
    return (a or default) == (b or default)


# —— 备用金 / 报销 ——
_REJECTED = "rejected"
_REVIEWABLE_REIMB = {"pending", "fund_linked", "partially_approved"}


def can_refund_fund_item(old_status) -> bool:
    """仅当该备用金开销之前不是"已驳回"时，才允许退回余额（幂等守卫）。"""
    return old_status != _REJECTED


def is_reviewable_reimb(status) -> bool:
    """已付款/已驳回等终态不可再审批，防止重复退款/改额。"""
    return status in _REVIEWABLE_REIMB


def fund_available(remaining_balance, spent_regular) -> float:
    """备用金现金可用余额 = 账户余额 - 已发生的常规（非报销）开销。"""
    return (remaining_balance or 0) - (spent_regular or 0)


# —— 应付账款 ——
def should_settle_bill(bill_warehouse_id, bill_status, paid_amount, amount, wh_ids, paid_value: str = "paid") -> bool:
    """付款计划执行时，判断某张账单是否应被结算：
    必须属于当前用户仓库、且尚未付清。"""
    if bill_warehouse_id not in wh_ids:
        return False
    if bill_status == paid_value:
        return False
    if (paid_amount or 0) >= (amount or 0):
        return False
    return True

"""仅按明确性质归组既有真实余额，不变更收付、流水或余额算法。"""
from decimal import Decimal
from app.core.account_nature import ACCOUNT_NATURE_LABELS
from app.services.wallet import money


def owner_wallet_summary(accounts, balances):
    groups = {}
    for account in accounts:
        currency = account.currency or "THB"
        group = groups.setdefault(currency, {"cash_balance": Decimal(0), "corporate_balance": Decimal(0),
            "unclassified_balance": Decimal(0), "unclassified_account_count": 0, "account_count": 0})
        group["account_count"] += 1
        value = money(balances[account.id])
        if account.account_nature in ACCOUNT_NATURE_LABELS:
            group[account.account_nature + "_balance"] += value
        else:
            group["unclassified_balance"] += value
            group["unclassified_account_count"] += 1
    result = {}
    for currency, group in sorted(groups.items()):
        classified = group["cash_balance"] + group["corporate_balance"]
        complete = group["unclassified_account_count"] == 0
        result[currency] = {**{key: float(value) if isinstance(value, Decimal) else value for key, value in group.items()},
            "classified_wallet_balance": float(classified), "wallet_total_complete": complete,
            "wallet_actual_balance": float(classified) if complete else None,
            "all_account_balance": float(classified + group["unclassified_balance"])}
    return result

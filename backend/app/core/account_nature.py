"""账户性质独立于支付工具类型；未分类账户不推定属于老板钱包。"""
ACCOUNT_NATURES = (
    {"value": "cash", "label": "现金户", "description": "老板手边现金"},
    {"value": "corporate", "label": "企业户", "description": "公司名下账户"},
)
ACCOUNT_NATURE_LABELS = {item["value"]: item["label"] for item in ACCOUNT_NATURES}

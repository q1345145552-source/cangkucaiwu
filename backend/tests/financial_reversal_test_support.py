def without_disabled_gate(source):
    """老轮次的源码保护允许本轮明确新增的外层依赖，仍检查全部原实现。"""
    return source.replace("from app.core.financial_reversals import reject_disabled_financial_reversal\n", "").replace(
        ", dependencies=[Depends(reject_disabled_financial_reversal)]", "")

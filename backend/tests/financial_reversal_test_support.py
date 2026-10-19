def without_disabled_gate(source):
    """老轮次的源码保护允许本轮明确新增的外层依赖，仍检查全部原实现。"""
    return source.replace("from app.core.financial_reversals import reject_disabled_financial_reversal\n", "").replace(
        ", dependencies=[Depends(reject_disabled_financial_reversal)]", "")


def without_advance_void_query(source):
    """只移除后续明确增加的作废排除和同一条预支查询的行锁，再严格比较原算薪代码。"""
    return source.replace("                EmployeeAdvance.not_voided(),\n", "").replace(
        ").order_by(EmployeeAdvance.advance_date.asc(), EmployeeAdvance.id.asc()).with_for_update()",
        ").order_by(EmployeeAdvance.advance_date.asc(), EmployeeAdvance.id.asc())")

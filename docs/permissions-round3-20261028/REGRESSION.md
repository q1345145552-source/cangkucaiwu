> 第三轮fix01补修更正：此前把124项前置失败泛称由277目标组替代覆盖的说明不充分，不能作为有效回归证据。原始失败数据保留。现已追加真实审批前置、逐断言跟踪及独立基线补证，见[本轮补修报告](../permissions-r03-fix01-20261028/REPORT.md)；最终283项275通过8失败，未宣称全绿。

# 相关回归：实际断言对照

完整当前运行284项（139通过、145失败），基线283项（211通过、72失败）；0跳过。数量差异来自新增离职待核算路由被动态劳工守卫测试收集。最终守卫定向结果见下。不能把新增失败全部称历史失败，也不能把旧流程失败称通过。

初次运行从隔离环境目录启动，1项git show提前失败且2项缺PGlite跳过；已完整从各自有Git历史的backend目录重跑并提供本地PGlite，第二次全部到达测试断言。原日志保留，不使用首次环境错误作为基线证据。

|类别|数量|
|---|---|
|第三轮授权变化使旧流程断言不再成立|124|
|基线存在相同首个断言|14|
|源码恒等断言含历史差异及授权变更|5|
|已按新授权更新有效断言并定向通过|2|

最终劳工边界及采购职责定向：{'pass': 30}。原失败逐项保留，增加的新拒绝并非删除有效断言。

|用例|具体归因|替代/复核证据|
|---|---|---|
|tests.test_disabled_financial_reversals::test_three_endpoints_disabled_for_every_authenticated_role_without_any_write[1]|旧主管/管理员直接付款或主管全仓工资行为被职责上限拒绝。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_disabled_financial_reversals::test_three_endpoints_disabled_for_every_authenticated_role_without_any_write[2]|旧主管/管理员直接付款或主管全仓工资行为被职责上限拒绝。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_disabled_financial_reversals::test_three_endpoints_disabled_for_every_authenticated_role_without_any_write[3]|旧主管/管理员直接付款或主管全仓工资行为被职责上限拒绝。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_disabled_financial_reversals::test_three_endpoints_disabled_for_every_authenticated_role_without_any_write[4]|旧主管/管理员直接付款或主管全仓工资行为被职责上限拒绝。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_disabled_financial_reversals::test_three_endpoints_disabled_for_every_authenticated_role_without_any_write[5]|旧主管/管理员直接付款或主管全仓工资行为被职责上限拒绝。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_disabled_financial_reversals::test_no_permission_or_unknown_record_cannot_bypass_gate_and_auth_still_required|对照实际返回/数值及失败断言相同；仅证明首个失败，不能推断之后未执行断言。|baseline/current-02 XML全文|
|tests.test_disabled_financial_reversals::test_revoked_history_amounts_and_ledger_readback_unchanged|旧主管/管理员直接付款或主管全仓工资行为被职责上限拒绝。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_disabled_financial_reversals::test_original_handlers_and_calculations_are_byte_identical_after_removing_only_outer_gate|基线与当前均有各自源码差异，不能说同根因；本轮新增守卫、阶段、能力与批准证据使恒等要求不成立。纯工资计算函数另做AST对照。|formula-preservation.json|
|tests.test_payroll_labor_boundary::test_real_logins_self_only_four_employee_pages_and_management_roles|主管管理工资改为拒绝；新增离职待核算接口仍受劳工守卫；保留原本人查询、其他角色、无副作用断言。|guard-regression-final.xml|
|tests.test_payroll_labor_boundary::test_single_self_exception_and_guard_on_every_management_route|主管管理工资改为拒绝；新增离职待核算接口仍受劳工守卫；保留原本人查询、其他角色、无副作用断言。|guard-regression-final.xml|
|tests.test_payroll_expense::test_disburse_reverse_reissue_and_reports[1]|旧主管/管理员直接付款或主管全仓工资行为被职责上限拒绝。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_payroll_expense::test_disburse_reverse_reissue_and_reports[4]|旧主管/管理员直接付款或主管全仓工资行为被职责上限拒绝。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_payroll_expense::test_account_guards_no_writes[missing]|旧主管/管理员直接付款或主管全仓工资行为被职责上限拒绝。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_payroll_expense::test_account_guards_no_writes[foreign]|旧主管/管理员直接付款或主管全仓工资行为被职责上限拒绝。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_payroll_expense::test_account_guards_no_writes[inactive]|旧主管/管理员直接付款或主管全仓工资行为被职责上限拒绝。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_payroll_expense::test_account_guards_no_writes[foreign_currency]|旧主管/管理员直接付款或主管全仓工资行为被职责上限拒绝。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_payroll_expense::test_batch_one_expense_per_payroll_one_account_and_idempotence|批量重复ID由旧去重改为整批拒绝；新批量有效和混合非法测试分别验证。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_payroll_expense::test_failed_expense_rolls_back_whole_payment[False]|旧主管/管理员直接付款或主管全仓工资行为被职责上限拒绝。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_payroll_expense::test_failed_expense_rolls_back_whole_payment[True]|旧主管/管理员直接付款或主管全仓工资行为被职责上限拒绝。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_payroll_expense::test_failed_revocation_rolls_back_expense_and_payroll|旧主管/管理员直接付款或主管全仓工资行为被职责上限拒绝。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_payroll_expense::test_exact_cent_amount_or_reject[0-200]|旧主管/管理员直接付款或主管全仓工资行为被职责上限拒绝。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_payroll_expense::test_exact_cent_amount_or_reject[-1-400]|旧主管/管理员直接付款或主管全仓工资行为被职责上限拒绝。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_payroll_expense::test_exact_cent_amount_or_reject[1234.567-400]|旧主管/管理员直接付款或主管全仓工资行为被职责上限拒绝。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_payroll_expense::test_missing_category_rejects_without_changing_payroll|新状态/角色/对象范围检查使旧入口更早拒绝，或旧未执行预支没有扣款可阻止作废；详见保留的具体请求和断言。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_payroll_cash_advance::test_cost_7000_company_accounts_and_ledger_unchanged_then_revoke|旧用例期待新建即确认/批准；现在仅申请待核验，不能恢复自动资金授权。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_payroll_cash_advance::test_company_account_deducts_once_and_revoke_restores_with_same_cost_and_flow|旧主管/管理员直接付款或主管全仓工资行为被职责上限拒绝。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_payroll_cash_advance::test_invalid_funding_never_changes_any_money[insufficient]|旧用例期待新建即确认/批准；现在仅申请待核验，不能恢复自动资金授权。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_payroll_cash_advance::test_invalid_funding_never_changes_any_money[pending]|旧用例期待新建即确认/批准；现在仅申请待核验，不能恢复自动资金授权。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_payroll_cash_advance::test_invalid_funding_never_changes_any_money[rejected]|旧用例期待新建即确认/批准；现在仅申请待核验，不能恢复自动资金授权。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_payroll_cash_advance::test_invalid_funding_never_changes_any_money[repaid]|旧用例期待新建即确认/批准；现在仅申请待核验，不能恢复自动资金授权。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_payroll_cash_advance::test_invalid_funding_never_changes_any_money[currency]|旧用例期待新建即确认/批准；现在仅申请待核验，不能恢复自动资金授权。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_payroll_cash_advance::test_invalid_funding_never_changes_any_money[foreign]|旧用例期待新建即确认/批准；现在仅申请待核验，不能恢复自动资金授权。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_payroll_cash_advance::test_invalid_funding_never_changes_any_money[missing]|旧用例期待新建即确认/批准；现在仅申请待核验，不能恢复自动资金授权。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_payroll_cash_advance::test_invalid_funding_never_changes_any_money[mixed]|旧用例期待新建即确认/批准；现在仅申请待核验，不能恢复自动资金授权。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_payroll_cash_advance::test_invalid_funding_never_changes_any_money[company_mixed]|旧用例期待新建即确认/批准；现在仅申请待核验，不能恢复自动资金授权。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_payroll_cash_advance::test_reuse_limit_batch_total_idempotence_and_revoke_releases_capacity|旧用例期待新建即确认/批准；现在仅申请待核验，不能恢复自动资金授权。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_payroll_cash_advance::test_batch_aggregate_budget_and_atomic_rollback[False]|旧用例期待新建即确认/批准；现在仅申请待核验，不能恢复自动资金授权。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_payroll_cash_advance::test_batch_aggregate_budget_and_atomic_rollback[True]|旧用例期待新建即确认/批准；现在仅申请待核验，不能恢复自动资金授权。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_payroll_cash_advance::test_failed_revoke_restores_cost_usage_and_loan_link|旧用例期待新建即确认/批准；现在仅申请待核验，不能恢复自动资金授权。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_payroll_cash_advance::test_supervisor_with_only_payroll_grant_and_cross_warehouse_rejected|旧用例期待新建即确认/批准；现在仅申请待核验，不能恢复自动资金授权。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_payroll_cash_advance::test_old_disbursement_role_restrictions_preserved[2]|旧用例期待新建即确认/批准；现在仅申请待核验，不能恢复自动资金授权。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_payroll_cash_advance::test_old_disbursement_role_restrictions_preserved[3]|旧用例期待新建即确认/批准；现在仅申请待核验，不能恢复自动资金授权。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_payroll_cash_advance::test_old_disbursement_role_restrictions_preserved[5]|旧用例期待新建即确认/批准；现在仅申请待核验，不能恢复自动资金授权。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_payroll_cash_advance::test_repay_after_salary_changes_debt_and_funds_but_never_salary_cost|旧用例期待新建即确认/批准；现在仅申请待核验，不能恢复自动资金授权。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_payroll_cash_advance::test_no_payroll_calculation_or_other_financial_module_changes|基线与当前均有各自源码差异，不能说同根因；本轮新增守卫、阶段、能力与批准证据使恒等要求不成立。纯工资计算函数另做AST对照。|formula-preservation.json|
|tests.test_reimbursement_payments::test_company_payment_2000_exactly_one_cost_and_one_flow_revoke_keeps_voided_flow|旧合成已确认/已批准对象未走独立核验及管理员批准快照，安全拒绝；不能伪造批准以保留旧200。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_reimbursement_payments::test_cash_advance_cost_only_usage_revoke_and_repay_do_not_duplicate_cost|旧用例期待新建即确认/批准；现在仅申请待核验，不能恢复自动资金授权。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_reimbursement_payments::test_validation_no_partial_money_changes[no_voucher]|旧合成已确认/已批准对象未走独立核验及管理员批准快照，安全拒绝；不能伪造批准以保留旧200。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_reimbursement_payments::test_validation_no_partial_money_changes[bad_voucher]|旧合成已确认/已批准对象未走独立核验及管理员批准快照，安全拒绝；不能伪造批准以保留旧200。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_reimbursement_payments::test_validation_no_partial_money_changes[no_account]|旧合成已确认/已批准对象未走独立核验及管理员批准快照，安全拒绝；不能伪造批准以保留旧200。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_reimbursement_payments::test_validation_no_partial_money_changes[foreign_account]|旧合成已确认/已批准对象未走独立核验及管理员批准快照，安全拒绝；不能伪造批准以保留旧200。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_reimbursement_payments::test_validation_no_partial_money_changes[inactive_account]|旧合成已确认/已批准对象未走独立核验及管理员批准快照，安全拒绝；不能伪造批准以保留旧200。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_reimbursement_payments::test_validation_no_partial_money_changes[currency]|旧合成已确认/已批准对象未走独立核验及管理员批准快照，安全拒绝；不能伪造批准以保留旧200。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_reimbursement_payments::test_validation_no_partial_money_changes[no_advance]|旧合成已确认/已批准对象未走独立核验及管理员批准快照，安全拒绝；不能伪造批准以保留旧200。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_reimbursement_payments::test_validation_no_partial_money_changes[small_advance]|旧合成已确认/已批准对象未走独立核验及管理员批准快照，安全拒绝；不能伪造批准以保留旧200。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_reimbursement_payments::test_validation_no_partial_money_changes[foreign_advance]|旧合成已确认/已批准对象未走独立核验及管理员批准快照，安全拒绝；不能伪造批准以保留旧200。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_reimbursement_payments::test_validation_no_partial_money_changes[advance_currency]|旧合成已确认/已批准对象未走独立核验及管理员批准快照，安全拒绝；不能伪造批准以保留旧200。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_reimbursement_payments::test_validation_no_partial_money_changes[pending_advance]|旧合成已确认/已批准对象未走独立核验及管理员批准快照，安全拒绝；不能伪造批准以保留旧200。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_reimbursement_payments::test_validation_no_partial_money_changes[mixed]|旧合成已确认/已批准对象未走独立核验及管理员批准快照，安全拒绝；不能伪造批准以保留旧200。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_reimbursement_payments::test_validation_no_partial_money_changes[not_linked_fund]|旧合成已确认/已批准对象未走独立核验及管理员批准快照，安全拒绝；不能伪造批准以保留旧200。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_reimbursement_payments::test_payment_and_revoke_failures_rollback_everything[company_account]|旧合成已确认/已批准对象未走独立核验及管理员批准快照，安全拒绝；不能伪造批准以保留旧200。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_reimbursement_payments::test_payment_and_revoke_failures_rollback_everything[cash_advance]|旧合成已确认/已批准对象未走独立核验及管理员批准快照，安全拒绝；不能伪造批准以保留旧200。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_reimbursement_payments::test_only_warehouse_admin_can_revoke[3]|旧合成已确认/已批准对象未走独立核验及管理员批准快照，安全拒绝；不能伪造批准以保留旧200。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_reimbursement_payments::test_only_warehouse_admin_can_revoke[4]|旧合成已确认/已批准对象未走独立核验及管理员批准快照，安全拒绝；不能伪造批准以保留旧200。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_reimbursement_payments::test_only_warehouse_admin_can_revoke[5]|旧合成已确认/已批准对象未走独立核验及管理员批准快照，安全拒绝；不能伪造批准以保留旧200。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_reimbursement_payments::test_only_warehouse_admin_can_revoke[2]|旧合成已确认/已批准对象未走独立核验及管理员批准快照，安全拒绝；不能伪造批准以保留旧200。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_reimbursement_payments::test_cny_account_and_advance_are_independent_from_thb|旧合成已确认/已批准对象未走独立核验及管理员批准快照，安全拒绝；不能伪造批准以保留旧200。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_reimbursement_payments::test_loan_quota_already_used_by_payroll_blocks_reimbursement_and_category_backfill_idempotent|旧用例期待新建即确认/批准；现在仅申请待核验，不能恢复自动资金授权。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_reimbursement_payments::test_decimal_item_sums_and_partially_approved_total_used_for_payment|旧合成已确认/已批准对象未走独立核验及管理员批准快照，安全拒绝；不能伪造批准以保留旧200。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_reimbursement_payments::test_legacy_paid_untouched_warehouse_scope_permissions_and_required_revoke_reason|旧合成已确认/已批准对象未走独立核验及管理员批准快照，安全拒绝；不能伪造批准以保留旧200。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_employee_advance_funding::test_source_money_cost_ledger_and_void[company_account]|旧用例金额/关联记录断言依赖创建或批准立即出款；现在资金效果仅发生在独立execute。原断言未删除，不把此运行称通过。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_employee_advance_funding::test_source_money_cost_ledger_and_void[cash_advance]|旧合成已确认/已批准对象未走独立核验及管理员批准快照，安全拒绝；不能伪造批准以保留旧200。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_employee_advance_funding::test_source_money_cost_ledger_and_void[expense_fund]|旧用例金额/关联记录断言依赖创建或批准立即出款；现在资金效果仅发生在独立execute。原断言未删除，不把此运行称通过。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_employee_advance_funding::test_pending_no_money_then_approval_once_and_rejection[company_account]|旧合成已确认/已批准对象未走独立核验及管理员批准快照，安全拒绝；不能伪造批准以保留旧200。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_employee_advance_funding::test_pending_no_money_then_approval_once_and_rejection[cash_advance]|旧合成已确认/已批准对象未走独立核验及管理员批准快照，安全拒绝；不能伪造批准以保留旧200。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_employee_advance_funding::test_pending_no_money_then_approval_once_and_rejection[expense_fund]|旧合成已确认/已批准对象未走独立核验及管理员批准快照，安全拒绝；不能伪造批准以保留旧200。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_employee_advance_funding::test_validation_no_partial_writes[values8-\u53ea\u80fd\u4f7f\u7528\u5df2\u786e\u8ba4\u7684\u57ab\u6b3e\u5355]|旧合成已确认/已批准对象未走独立核验及管理员批准快照，安全拒绝；不能伪造批准以保留旧200。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_employee_advance_funding::test_validation_no_partial_writes[values9-\u57ab\u6b3e\u5355\u5e01\u79cd\u4e0e\u9884\u652f\u4e0d\u4e00\u81f4]|旧合成已确认/已批准对象未走独立核验及管理员批准快照，安全拒绝；不能伪造批准以保留旧200。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_employee_advance_funding::test_validation_no_partial_writes[values10-\u57ab\u6b3e\u5355\u5269\u4f59\u91d1\u989d\u4e0d\u8db3]|旧合成已确认/已批准对象未走独立核验及管理员批准快照，安全拒绝；不能伪造批准以保留旧200。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_employee_advance_funding::test_approval_rechecks_resources_and_keeps_pending_on_failure[company_account]|旧合成已确认/已批准对象未走独立核验及管理员批准快照，安全拒绝；不能伪造批准以保留旧200。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_employee_advance_funding::test_approval_rechecks_resources_and_keeps_pending_on_failure[cash_advance]|旧垫款来源没有有效批准，创建预支已拒绝，旧测试继续取id导致KeyError；后续金额断言未执行。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_employee_advance_funding::test_approval_rechecks_resources_and_keeps_pending_on_failure[expense_fund]|旧合成已确认/已批准对象未走独立核验及管理员批准快照，安全拒绝；不能伪造批准以保留旧200。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_employee_advance_funding::test_history_failure_rolls_back_all_money_and_records[company_account]|原故障注入点位于新建/批准即付款旧路径，新流程不执行该写入；已在真实执行阶段补故障回滚与重试。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_employee_advance_funding::test_history_failure_rolls_back_all_money_and_records[cash_advance]|原故障注入点位于新建/批准即付款旧路径，新流程不执行该写入；已在真实执行阶段补故障回滚与重试。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_employee_advance_funding::test_history_failure_rolls_back_all_money_and_records[expense_fund]|原故障注入点位于新建/批准即付款旧路径，新流程不执行该写入；已在真实执行阶段补故障回滚与重试。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_employee_advance_funding::test_shared_cash_capacity_cannot_be_reused|旧合成已确认/已批准对象未走独立核验及管理员批准快照，安全拒绝；不能伪造批准以保留旧200。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_employee_advance_funding::test_three_sources_share_original_salary_cap[1]|旧合成已确认/已批准对象未走独立核验及管理员批准快照，安全拒绝；不能伪造批准以保留旧200。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_employee_advance_funding::test_three_sources_share_original_salary_cap[4]|旧合成已确认/已批准对象未走独立核验及管理员批准快照，安全拒绝；不能伪造批准以保留旧200。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_employee_advance_funding::test_salary_functions_and_cap_unchanged|基线与当前均有各自源码差异，不能说同根因；本轮新增守卫、阶段、能力与批准证据使恒等要求不成立。纯工资计算函数另做AST对照。|formula-preservation.json|
|tests.test_employee_advance_funding::test_fund_review_cannot_refund_an_approved_advance|新状态/角色/对象范围检查使旧入口更早拒绝，或旧未执行预支没有扣款可阻止作废；详见保留的具体请求和断言。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_employee_advance_funding::test_cny_sources_keep_original_exchange_rate_cap|旧合成已确认/已批准对象未走独立核验及管理员批准快照，安全拒绝；不能伪造批准以保留旧200。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_employee_advance_funding::test_company_balance_keeps_cent_precision_after_fractional_advances|旧用例金额/关联记录断言依赖创建或批准立即出款；现在资金效果仅发生在独立execute。原断言未删除，不把此运行称通过。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_employee_advance_funding::test_locked_validation_refreshes_previously_loaded_resource[cash_advance-\u53ea\u80fd\u4f7f\u7528\u5df2\u786e\u8ba4\u7684\u57ab\u6b3e\u5355]|旧合成已确认/已批准对象未走独立核验及管理员批准快照，安全拒绝；不能伪造批准以保留旧200。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_employee_advance_limit::test_requested_monthly_10000_workflow_and_pending_reservation|旧用例期待新建即确认/批准；现在仅申请待核验，不能恢复自动资金授权。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_employee_advance_limit::test_actual_payroll_settlement_restores_quota_without_formula_changes|旧用例金额/关联记录断言依赖创建或批准立即出款；现在资金效果仅发生在独立execute。原断言未删除，不把此运行称通过。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_employee_advance_void::test_void_keeps_row_deletes_cost_releases_quota_and_never_recalculates|旧用例金额/关联记录断言依赖创建或批准立即出款；现在资金效果仅发生在独立execute。原断言未删除，不把此运行称通过。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_employee_advance_void::test_only_warehouse_admin_can_void_regardless_of_permission[False-2]|对照实际返回/数值及失败断言相同；仅证明首个失败，不能推断之后未执行断言。|baseline/current-02 XML全文|
|tests.test_employee_advance_void::test_only_warehouse_admin_can_void_regardless_of_permission[False-3]|对照实际返回/数值及失败断言相同；仅证明首个失败，不能推断之后未执行断言。|baseline/current-02 XML全文|
|tests.test_employee_advance_void::test_only_warehouse_admin_can_void_regardless_of_permission[False-4]|对照实际返回/数值及失败断言相同；仅证明首个失败，不能推断之后未执行断言。|baseline/current-02 XML全文|
|tests.test_employee_advance_void::test_only_warehouse_admin_can_void_regardless_of_permission[False-5]|对照实际返回/数值及失败断言相同；仅证明首个失败，不能推断之后未执行断言。|baseline/current-02 XML全文|
|tests.test_employee_advance_void::test_only_warehouse_admin_can_void_regardless_of_permission[True-2]|对照实际返回/数值及失败断言相同；仅证明首个失败，不能推断之后未执行断言。|baseline/current-02 XML全文|
|tests.test_employee_advance_void::test_only_warehouse_admin_can_void_regardless_of_permission[True-5]|对照实际返回/数值及失败断言相同；仅证明首个失败，不能推断之后未执行断言。|baseline/current-02 XML全文|
|tests.test_employee_advance_void::test_real_full_and_partial_payroll_deductions_cannot_be_voided[1000-\u8be5\u9884\u652f\u5df2\u968f\u5de5\u8d44\u7ed3\u6e05 \u4e0d\u80fd\u4f5c\u5e9f]|新状态/角色/对象范围检查使旧入口更早拒绝，或旧未执行预支没有扣款可阻止作废；详见保留的具体请求和断言。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_employee_advance_void::test_real_full_and_partial_payroll_deductions_cannot_be_voided[2000-\u8be5\u9884\u652f\u5df2\u968f\u5de5\u8d44\u62b5\u6263 \u4e0d\u80fd\u4f5c\u5e9f]|新状态/角色/对象范围检查使旧入口更早拒绝，或旧未执行预支没有扣款可阻止作废；详见保留的具体请求和断言。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_employee_advance_void::test_void_transaction_rolls_back_cost_and_metadata_on_failure[expense_log]|原故障注入点位于新建/批准即付款旧路径，新流程不执行该写入；已在真实执行阶段补故障回滚与重试。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_cash_advance_repayments::test_full_repayment_money_ledger_and_costs_exactly_unchanged|旧用例期待新建即确认/批准；现在仅申请待核验，不能恢复自动资金授权。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_cash_advance_repayments::test_partial_repayment_reversal_keeps_voided_flow_and_restores_balance|旧用例期待新建即确认/批准；现在仅申请待核验，不能恢复自动资金授权。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_cash_advance_repayments::test_admin_only_repayment_upload_accounts_and_revoke[2]|旧用例期待新建即确认/批准；现在仅申请待核验，不能恢复自动资金授权。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_cash_advance_repayments::test_admin_only_repayment_upload_accounts_and_revoke[3]|旧用例期待新建即确认/批准；现在仅申请待核验，不能恢复自动资金授权。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_cash_advance_repayments::test_admin_only_repayment_upload_accounts_and_revoke[4]|旧用例期待新建即确认/批准；现在仅申请待核验，不能恢复自动资金授权。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_cash_advance_repayments::test_admin_only_repayment_upload_accounts_and_revoke[5]|旧用例期待新建即确认/批准；现在仅申请待核验，不能恢复自动资金授权。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_cash_advance_repayments::test_repayment_validation_no_partial_financial_writes[fields0-\u4e0d\u80fd\u8d85\u8fc7\u5269\u4f59\u672a\u8fd8]|旧用例期待新建即确认/批准；现在仅申请待核验，不能恢复自动资金授权。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_cash_advance_repayments::test_repayment_validation_no_partial_financial_writes[fields1-\u8bf7\u9009\u62e9\u5f52\u8fd8\u8d26\u6237]|旧用例期待新建即确认/批准；现在仅申请待核验，不能恢复自动资金授权。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_cash_advance_repayments::test_repayment_validation_no_partial_financial_writes[fields2-\u8bf7\u4e0a\u4f20\u5f52\u8fd8\u51ed\u8bc1\u7167\u7247]|旧用例期待新建即确认/批准；现在仅申请待核验，不能恢复自动资金授权。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_cash_advance_repayments::test_repayment_validation_no_partial_financial_writes[fields3-\u8bf7\u4e0a\u4f20\u5f52\u8fd8\u51ed\u8bc1\u7167\u7247]|旧用例期待新建即确认/批准；现在仅申请待核验，不能恢复自动资金授权。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_cash_advance_repayments::test_repayment_validation_no_partial_financial_writes[fields4-\u51ed\u8bc1\u7167\u7247\u4e0d\u5c5e\u4e8e\u5f53\u524d\u4ed3\u5e93\u7684\u57ab\u6b3e\u5355]|旧用例期待新建即确认/批准；现在仅申请待核验，不能恢复自动资金授权。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_cash_advance_repayments::test_repayment_validation_no_partial_financial_writes[fields5-\u5f52\u8fd8\u51ed\u8bc1\u7167\u7247\u4e0d\u5b58\u5728\uff0c\u8bf7\u91cd\u65b0\u4e0a\u4f20]|旧用例期待新建即确认/批准；现在仅申请待核验，不能恢复自动资金授权。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_cash_advance_repayments::test_pending_rejected_inactive_cross_warehouse_and_currency_are_blocked|新状态/角色/对象范围检查使旧入口更早拒绝，或旧未执行预支没有扣款可阻止作废；详见保留的具体请求和断言。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_cash_advance_repayments::test_full_reversal_inactive_account_and_multiple_payments|旧用例期待新建即确认/批准；现在仅申请待核验，不能恢复自动资金授权。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_cash_advance_repayments::test_history_failure_rolls_back_repayment_and_revoke|旧用例期待新建即确认/批准；现在仅申请待核验，不能恢复自动资金授权。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_cash_advance_repayments::test_repayment_never_recalculates_and_manual_payroll_amount_stays_same|旧用例期待新建即确认/批准；现在仅申请待核验，不能恢复自动资金授权。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_cash_advance_repayments::test_currency_is_explicit_account_must_match_and_summary_never_adds_currencies|旧用例期待新建即确认/批准；现在仅申请待核验，不能恢复自动资金授权。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_cash_advance_repayments::test_invalid_money_does_not_change_balance_or_create_flows[0]|旧用例期待新建即确认/批准；现在仅申请待核验，不能恢复自动资金授权。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_cash_advance_repayments::test_invalid_money_does_not_change_balance_or_create_flows[-1]|旧用例期待新建即确认/批准；现在仅申请待核验，不能恢复自动资金授权。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_cash_advance_repayments::test_invalid_money_does_not_change_balance_or_create_flows[NaN]|旧用例期待新建即确认/批准；现在仅申请待核验，不能恢复自动资金授权。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_cash_advance_repayments::test_invalid_money_does_not_change_balance_or_create_flows[Infinity]|旧用例期待新建即确认/批准；现在仅申请待核验，不能恢复自动资金授权。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_cash_advance_repayments::test_invalid_money_does_not_change_balance_or_create_flows[1.001]|旧用例期待新建即确认/批准；现在仅申请待核验，不能恢复自动资金授权。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_cash_advance_documents::test_two_wages_difference_manual_status_detail_and_other_books_unchanged|旧用例期待新建即确认/批准；现在仅申请待核验，不能恢复自动资金授权。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_cash_advance_documents::test_edit_pending_confirmed_permissions_and_warehouse|旧用例期待新建即确认/批准；现在仅申请待核验，不能恢复自动资金授权。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_cash_advance_documents::test_payment_and_repayment_business_functions_unchanged|基线与当前均有各自源码差异，不能说同根因；本轮新增守卫、阶段、能力与批准证据使恒等要求不成立。纯工资计算函数另做AST对照。|formula-preservation.json|
|tests.test_advance_payroll_approval_audit::test_pending_1000_approved_only_after_manual_recalc|对照实际返回/数值及失败断言相同；仅证明首个失败，不能推断之后未执行断言。|baseline/current-02 XML全文|
|tests.test_round18_advance_review::test_admin_review_reject_state_guards_and_history|旧合成已确认/已批准对象未走独立核验及管理员批准快照，安全拒绝；不能伪造批准以保留旧200。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_round18_advance_review::test_only_warehouse_admin_can_review[False-2]|对照实际返回/数值及失败断言相同；仅证明首个失败，不能推断之后未执行断言。|baseline/current-02 XML全文|
|tests.test_round18_advance_review::test_only_warehouse_admin_can_review[False-3]|对照实际返回/数值及失败断言相同；仅证明首个失败，不能推断之后未执行断言。|baseline/current-02 XML全文|
|tests.test_round18_advance_review::test_only_warehouse_admin_can_review[False-4]|对照实际返回/数值及失败断言相同；仅证明首个失败，不能推断之后未执行断言。|baseline/current-02 XML全文|
|tests.test_round18_advance_review::test_only_warehouse_admin_can_review[False-5]|对照实际返回/数值及失败断言相同；仅证明首个失败，不能推断之后未执行断言。|baseline/current-02 XML全文|
|tests.test_round18_advance_review::test_only_warehouse_admin_can_review[True-2]|对照实际返回/数值及失败断言相同；仅证明首个失败，不能推断之后未执行断言。|baseline/current-02 XML全文|
|tests.test_round18_advance_review::test_only_warehouse_admin_can_review[True-5]|对照实际返回/数值及失败断言相同；仅证明首个失败，不能推断之后未执行断言。|baseline/current-02 XML全文|
|tests.test_round18_advance_review::test_pending_approved_manual_recalc_exactly_100_and_carry|旧合成已确认/已批准对象未走独立核验及管理员批准快照，安全拒绝；不能伪造批准以保留旧200。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_round18_advance_review::test_review_history_failure_rolls_back|旧合成已确认/已批准对象未走独立核验及管理员批准快照，安全拒绝；不能伪造批准以保留旧200。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_round18_advance_review::test_supervisor_self_advance_end_to_end|旧合成已确认/已批准对象未走独立核验及管理员批准快照，安全拒绝；不能伪造批准以保留旧200。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_advance_manager_recipients::test_options_auto_archive_reuse_and_labor|旧用例期待新建即确认/批准；现在仅申请待核验，不能恢复自动资金授权。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_advance_manager_recipients::test_existing_enabled_archive_and_self_approval_preserved|旧用例期待新建即确认/批准；现在仅申请待核验，不能恢复自动资金授权。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_advance_manager_recipients::test_recipient_role_and_warehouse_scope|新状态/角色/对象范围检查使旧入口更早拒绝，或旧未执行预支没有扣款可阻止作废；详见保留的具体请求和断言。|requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到|
|tests.test_advance_manager_recipients::test_unchanged_review_and_payroll_math|基线与当前均有各自源码差异，不能说同根因；本轮新增守卫、阶段、能力与批准证据使恒等要求不成立。纯工资计算函数另做AST对照。|formula-preservation.json|

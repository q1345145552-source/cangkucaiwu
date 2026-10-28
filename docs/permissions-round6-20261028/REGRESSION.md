# 回归失败逐项对照

保留原始首次、修正夹具前和最终日志。所有套件无 skip；退出码 1 如实保留。测试角色/文案适配不改变业务金额断言。完整原始断言文本在 regression-comparison.json。

## prior
基线 275/283，本轮 275/283；基线和本轮 skips=0/0。

### tests.test_cash_advance_repayments::test_full_repayment_money_ledger_and_costs_exactly_unchanged
基线同名成本/钱包展示断言仍失败；完整原值保留，字典输出顺序会变化，不以相同名字代替数值核对。

```
E   AssertionError: [{'assertion': 'test_full_repayment_money_ledger_and_costs_exactly_unchanged:100', 'actual_failure': 'assert (3000.0 == 3000 and False is True)'}, {'assertion': 'test_full_repayment_money_ledger_and_costs_exactly_unchanged:104', 'actual_failure': "assert ({'/income-exp...', ...}, ...}} == {'/income-exp...', ...}, ...}}\n  \n  Differing items:\n  {'/income-expense/monthly-summary?start_date=2026-10-01&end_date=2026-10-31&category_group=operating': {'basis': '公司钱包...，备用金拨付及垫款归还按原钱包规则统计', 'end_date': '2026-10-31', 'expense_by_currency': {'THB': 3750.0}, 'income_by_currency': {}, ...}} != {'/income-expense/monthly-summary?start_date=2026-10-01&end_date=2026-10-31&category_group=operating': {'basis': '公司钱包...次，备用金拨付及垫款归还按原钱包规则统计', 'end_date': '2026-10-31', 'expense_by_currency': {'THB': 750.0}, 'income_by_currency': {}, ...}}\n  {'/income-expense/expense?category_group=operating': {'cost_basis': '公司钱包实际收...\n  \n  ...Full output truncated (3 lines hidden), use '-vv' to show)"}]
```

### tests.test_cash_advance_repayments::test_currency_is_explicit_account_must_match_and_summary_never_adds_currencies
基线同名成本/钱包展示断言仍失败；完整原值保留，字典输出顺序会变化，不以相同名字代替数值核对。

```
E   AssertionError: [{'assertion': 'test_currency_is_explicit_account_must_match_and_summary_never_adds_currencies:294', 'actual_failure': "assert {'/income-exp...', ...}, ...}} == {'/income-exp...', ...}, ...}}\n  \n  Differing items:\n  {'/income-expense/monthly-summary?start_date=2026-10-01&end_date=2026-10-31&category_group=operating': {'basis': '公司钱包...包规则统计', 'end_date': '2026-10-31', 'expense_by_currency': {'CNY': 3000.0, 'THB': 750.0}, 'income_by_currency': {}, ...}} != {'/income-expense/monthly-summary?start_date=2026-10-01&end_date=2026-10-31&category_group=operating': {'basis': '公司钱包...次，备用金拨付及垫款归还按原钱包规则统计', 'end_date': '2026-10-31', 'expense_by_currency': {'THB': 750.0}, 'income_by_currency': {}, ...}}\n  {'/income-expense/expense?category_group=operating': {'cost_basis': '公司钱包实际收...\n  \n  ...Full output truncated (3 lines hidden), use '-vv' to show"}]
```

### tests.test_employee_advance_funding::test_source_money_cost_ledger_and_void[company_account]
基线同名成本/展示口径差异保留；本轮未改计价和成本公式。

```
E   AssertionError: [{'assertion': 'test_source_money_cost_ledger_and_void:108', 'actual_failure': "assert (2 == 1)\n +  where 2 = len([{'account_id': 1, 'account_name': '账户1', 'amount': 1000.0, 'cash_advance_id': None, ...}, {'account_id': None, 'account_name': '未指定账户', 'amount': 10000.0, 'cash_advance_id': None, ...}])"}]
```

### tests.test_payroll_cash_advance::test_cost_7000_company_accounts_and_ledger_unchanged_then_revoke
基线同名成本/展示口径差异保留；本轮未改计价和成本公式。

```
E   AssertionError: [{'assertion': '7000 salary cost row/count/amount/source', 'actual_failure': 'assert (2, 750.0) == (3, 7750)\n  \n  At index 0 diff: 2 != 3\n  Use -v to get more diff'}, {'assertion': '7000 report cost total', 'actual_failure': "assert (200 == 200 and {'THB': 750.0} == {'THB': 7750}\n +  where 200 = <Response [200 OK]>.status_code\n  \n  Differing items:\n  {'THB': 750.0} != {'THB': 7750}\n  Use -v to get more diff)"}, {'assertion': 'linked cost edit protection requires generated expense', 'actual_failure': "{'account_id': None, 'cash_advance_id': 1, 'disbursed_at': '2026-10-28T07:16:22.389209+07:00', 'expense_record_id': None, ...}\nassert None is not None"}]
```

### tests.test_payroll_expense::test_disburse_reverse_reissue_and_reports[3]
基线同名成本/展示口径差异保留；本轮未改计价和成本公式。

```
E   AssertionError: {'card_expense': 1234.56, 'card_income': 0, 'card_net': -1234.56, 'data': [{'account_id': 3, 'account_name': '现金', 'amount': 1234.56, 'cash_advance_id': None, ...}], ...}
E   assert False
```

### tests.test_reimbursement_payments::test_company_payment_2000_exactly_one_cost_and_one_flow_revoke_keeps_voided_flow
基线同名成本/展示口径差异保留；本轮未改计价和成本公式。

```
E   AssertionError: [{'assertion': 'test_company_payment_2000_exactly_one_cost_and_one_flow_revoke_keeps_voided_flow:124', 'actual_failure': 'assert (4, 7750.0) == (3, 2750)\n  \n  At index 0 diff: 4 != 3\n  Use -v to get more diff'}, {'assertion': 'test_company_payment_2000_exactly_one_cost_and_one_flow_revoke_keeps_voided_flow:133', 'actual_failure': 'assert (400 == 400 and 4 == 3)\n +  where 400 = <Response [400 Bad Request]>.status_code'}, {'assertion': 'test_company_payment_2000_exactly_one_cost_and_one_flow_revoke_keeps_voided_flow:137', 'actual_failure': "assert (200 == 200 and {'THB': 7750.0} == {'THB': 2750}\n +  where 200 = <Response [200 OK]>.status_code\n  \n  Differing items:\n  {'THB': 7750.0} != {'THB': 2750}\n  Use -v to get more diff)"}, {'assertion': 'test_company_payment_2000_exactly_one_cost_and_one_flow_revoke_keeps_voided_flow:142', 'actual_failure': 'assert (5750.0 == 750)'}]
```

### tests.test_reimbursement_payments::test_cash_advance_cost_only_usage_revoke_and_repay_do_not_duplicate_cost
基线同名成本/展示口径差异保留；本轮未改计价和成本公式。

```
E   AssertionError: [{'assertion': 'test_cash_advance_cost_only_usage_revoke_and_repay_do_not_duplicate_cost:171', 'actual_failure': 'assert (5750.0 == 2750)'}, {'assertion': 'test_cash_advance_cost_only_usage_revoke_and_repay_do_not_duplicate_cost:187', 'actual_failure': 'assert (5750.0 == 750)'}, {'assertion': 'test_cash_advance_cost_only_usage_revoke_and_repay_do_not_duplicate_cost:190', 'actual_failure': 'assert (200 == 200 and 5750.0 == 2750)\n +  where 200 = <Response [200 OK]>.status_code'}, {'assertion': 'test_cash_advance_cost_only_usage_revoke_and_repay_do_not_duplicate_cost:193', 'actual_failure': 'assert (200 == 200 and 7750.0 == 2750)\n +  where 200 = <Response [200 OK]>.status_code'}]
```

### tests.test_reimbursement_payments::test_decimal_item_sums_and_partially_approved_total_used_for_payment
基线同名成本/展示口径差异保留；本轮未改计价和成本公式。

```
E   AssertionError: [{'assertion': 'test_decimal_item_sums_and_partially_approved_total_used_for_payment:388', 'actual_failure': 'assert 5750.3 == 750.3'}]
```

## related
基线 234/239，本轮 234/239；基线和本轮 skips=0/0。

### tests.test_batch_makeup::test_single_makeup_function_and_unrelated_business_unchanged
基线已有旧源码快照/菜单数量预期；本轮保留原断言。

```
E   AssertionError: clock_in
E   assert 'AsyncFunctio...pe_params=[])' == 'AsyncFunctio...pe_params=[])'
E     
E     Skipping 1822 identical leading characters in diff, use -v to show
E     - else=[]), Assign(targets=[Name(id='today', ctx=Store())], value=Call(func=Name(id='thai_today', ctx=Load()), args=[], keywords=[])), Assign(targets=[Name(id='now', ctx=Store())], value=Call(func=Name(id='thai_now', ctx=Load()), args=[], keywords=[])), Assign(targets=[Name(id='si', ctx=Store())], value=Subscript(value=Name(id='SESSIONS', ctx=Load()), slice=Name(id='session', ctx=Load()), ctx=Load())), Assign(targets=[Name(id='label', ctx=Store())], value=Call(func=Name(id='session_label', ctx=Load()), ar...
E     
E     ...Full output truncated (4 lines hidden), use '-vv' to show
```

### tests.test_employee_limit_routes::test_limit_routes_and_unrelated_employee_functions_unchanged
基线已有旧源码快照/菜单数量预期；本轮保留原断言。

```
E   assert {'_find_linke...ams=[])', ...} == {'_find_linke...ams=[])', ...}
E     
E     Omitting 2 identical items, use -vv to show
E     Differing items:
E     {'bind_existing_accounts': "AsyncFunctionDef(name='bind_existing_accounts', args=arguments(posonlyargs=[], args=[arg(a...x=Load()), attr='post', ctx=Load()), args=[Constant(value='/bind-existing-accounts')], keywords=[])], type_params=[])"} != {'bind_existing_accounts': "AsyncFunctionDef(name='bind_existing_accounts', args=arguments(posonlyargs=[], args=[arg(a..., Call(func=Name(id='read_projection', ctx=Load()), args=[Constant(value='employee')], keywords=[])], type_params=[])"}
E     {'set_max_limit': "AsyncFunctionD...
E     
E     ...Full output truncated (9 lines hidden), use '-vv' to show
```

### tests.test_full_day_leave::test_half_hourly_early_and_other_writes_unchanged
基线已有旧源码快照/菜单数量预期；本轮保留原断言。

```
E   assert {'_count_make...ams=[])', ...} == {'_count_make...ams=[])', ...}
E     
E     Omitting 10 identical items, use -vv to show
E     Differing items:
E     {'batch_makeup_clock_in': "AsyncFunctionDef(name='batch_makeup_clock_in', args=arguments(posonlyargs=[], args=[arg(arg...outer', ctx=Load()), attr='post', ctx=Load()), args=[Constant(value='/batch-makeup')], keywords=[])], type_params=[])"} != {'batch_makeup_clock_in': "AsyncFunctionDef(name='batch_makeup_clock_in', args=arguments(posonlyargs=[], args=[arg(arg...outer', ctx=Load()), attr='post', ctx=Load()), args=[Constant(value='/batch-makeup')], keywords=[])], type_params=[])"}
E     {'list_records': "AsyncFunctionD...
E     
E     ...Full output truncated (378 lines hidden), use '-vv' to show
```

### tests.test_makeup_batches::test_first_round_logic_and_quota_unchanged_except_batch_link
基线已有旧源码快照/菜单数量预期；本轮保留原断言。

```
E   AssertionError: clock_in
E   assert 'AsyncFunctio...pe_params=[])' == 'AsyncFunctio...pe_params=[])'
E     
E     Skipping 1822 identical leading characters in diff, use -v to show
E     - else=[]), If(test=BinOp(left=Call(func=Name(id='set', ctx=Load()), args=[Await(value=Call(func=Attribute(value=Name(id='request', ctx=Load()), attr='form', ctx=Load()), args=[], keywords=[]))], keywords=[]), op=Sub(), right=Set(elts=[Constant(value='session'), Constant(value='photo_base64')])), body=[Raise(exc=Call(func=Name(id='HTTPException', ctx=Load()), args=[Constant(value=400), Constant(value='打卡包含不允许的字段')], keywords=[]))], orelse=[]), Expr(value=Await(value=Call(func=Attribute(value=Name(id='db',...
E     
E     ...Full output truncated (4 lines hidden), use '-vv' to show
```

### tests.test_round12_attendance_identity::test_link_and_timestamp_are_server_owned
基线已有旧源码快照/菜单数量预期；本轮保留原断言。

```
E   AssertionError: assert 37 == 34
E    +  where 37 = len([MenuPermission(menu_key='recharge', label='充值申报', path='/recharge', roles=('warehouse_admin', 'staff', 'supervisor'),...arehouse_admin', 'supervisor'), selectable=True, legacy_permission=False, permission_menu_key='salary_templates'), ...])
```

## reads
基线 32/39，本轮 32/39；基线和本轮 skips=0/0。

### tests.test_dashboard_procurement_payments::test_money_basis_numbers_on_real_postgres
基线即使用管理员执行普通资金拨付被403拒绝，后续汇总断言未抵达；不恢复旧付款角色。

```
E   AssertionError: {"detail":"仅获授权财务可以执行；财务本人申请可由管理员独立办理"}
E   assert 403 == 200
E    +  where 403 = <Response [403 Forbidden]>.status_code
```

### tests.test_modification_log_permissions::test_same_permission_for_list_operators_export[2-False]
基线旧日志模块、字段/仓库、拒绝文案或数量预期；本轮保持敏感字段与仓库守卫。

```
E   assert (0 == 2)
```

### tests.test_modification_log_permissions::test_same_permission_for_list_operators_export[3-True]
基线旧日志模块、字段/仓库、拒绝文案或数量预期；本轮保持敏感字段与仓库守卫。

```
E   assert (0 == 2)
```

### tests.test_modification_log_permissions::test_same_permission_for_list_operators_export[4-True]
基线旧日志模块、字段/仓库、拒绝文案或数量预期；本轮保持敏感字段与仓库守卫。

```
E   assert (0 == 2)
```

### tests.test_modification_log_permissions::test_same_permission_for_list_operators_export[5-True]
基线旧日志模块、字段/仓库、拒绝文案或数量预期；本轮保持敏感字段与仓库守卫。

```
E   AssertionError: assert False
E    +  where False = <built-in method startswith of str object at 0x123464120>('无此操作权限')
E    +    where <built-in method startswith of str object at 0x123464120> = '无权访问'.startswith
```

### tests.test_modification_log_permissions::test_migration_once_supervisor_only_and_real_read
基线旧日志模块、字段/仓库、拒绝文案或数量预期；本轮保持敏感字段与仓库守卫。

```
E   assert (200 == 200 and 0 == 2)
E    +  where 200 = <Response [200 OK]>.status_code
```

### tests.test_modification_log_permissions::test_warehouse_filter_and_export_exactly_match
基线旧日志模块、字段/仓库、拒绝文案或数量预期；本轮保持敏感字段与仓库守卫。

```
E   assert 403 == 200
E    +  where 403 = <Response [403 Forbidden]>.status_code
```

## 本轮引入后已解决/适配的差异

- 主管代录垫款原先使 283 套件出现 72 失败；独立合成财务 94 录入，申请/受益人仍为 4，核验人 3、批准人 1 不变。两处合法编辑改为录入人 94；原金额、状态、并发与回滚断言保持。最终恢复到基线的 8 项失败。
- 新中央角色上限优先拒绝，预支审批、作废、垫款接口的 403 文案断言按新拒绝原因更新，拒绝状态和数据库不变断言未删除。
- 旧日志补权回滚测试改用已有明确“考勤”旧授权的独立主管 7，仍检查事务回滚、标记不存在和重复执行；空主管 4 继续保持空。不再要求空账号自动补权。
- 用户服务端归属字段从忽略改为422：先断言拒绝，再提交合法字段并保留原绑定/时间断言。历史报告 handler 对比补真实注册 route 上下文，未模拟鉴权放行。
- 采购目录初稿误限管理员已修，原职责、版本核验及例外保护测试实际通过；采购生效不替代资金批准。

旧成本断言包含 7000 工资场景实际费用行 (2,750) 与旧期待 (3,7750)、报表 THB750 与期待7750，以及关联费用记录缺失；这些差异在精确基线存在，不改成本口径。历史三条依赖生成费用记录的断言仍不能冒称通过。请结合完整 trace 和原测试 DeferredChecks 审查，不将基线存在理解为可忽略。

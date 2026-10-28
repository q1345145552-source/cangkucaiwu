# 权限七轮合并 main 验收与证据摘要

本地合成数据库及实际应用路由验证。未部署、未 SSH、未读生产凭据、未连接生产。库存计价、成本计算和真实数据未修改。

## 合并

- 工作树：`/private/tmp/permissions-round7-20261028`。
- 权限基线：`87a461b5f41530efd329202242c5b1297f4ddbf7`。
- main 基线：`6cee8b94514f5612bcf6be48d7131520a6039b53`。
- 双父合并提交：`1427dbbe82380685788902d830c1d82dab92e4a4`。先把 origin/main 合入权限分支，没有 squash、rebase、强推或重写历史。
- 18 个权限提交及 main 的 5 个提交均通过祖先检查。最近二十条和远端核验在推送后保存为本地 `main-last20.txt`、`push-verification.json`。

## 五项 main 功能

|功能|代码对照及实际验证|
|---|---|
|13 处余额不足提示|保留 main 的 warning 服务与金额算法。真实测试覆盖余额提示、并发、防重复及回滚；预支实际出款前补齐确认提示，取消零付款。|
|供应商库存、SKU|三个接口及三个手机尺寸页面均 200，无页面异常或失败 API；库存服务和模型未改。|
|规格、币种单位比价|supplier_comparison.py、specifications.ts 与 main 完全一致；后端供应商独立验收测试通过，实际 React 规格表单 4 项通过。|
|到账建议|incoming_suggestions.py、incoming.py 与 main 完全一致；合成 XT10022 录入返回 suggestions 一条，命中日期、金额、名称三条件。|
|到账客户可空|实际返回 200、customer_id=null、created=true，保持 unmatched，不自动形成客户实收。|

逐文件差异见原始证据 `protected-diff-0.txt` 至 `protected-diff-7.txt`。供应商和对账页面保留新增权限守卫与字段过滤。main 新增的两条读取路由已加入动作目录，实际注册与目录精确匹配 436 条。

## 全量后端与成本失败

实际收集并执行 2,954 项：**2,940 通过、14 失败、0 跳过，退出码 1**。四个隔离数据库按文件分组，每项只执行一次；584 个源文件运行前后哈希一致。原始日志为 `logs/full/full-current-final-merge02.log`、各 shard 日志/XML、command/environment/freeze-check。

14 项失败以相同详细输出格式单独复跑，与此前独立验收的 R6 基线 `0e4d2f9` 同合成夹具证据逐断言比较，**14/14 相同**。只归一化 Python 内存地址、随机 PNG 文件名及 disbursed_at 时间，没有归一化金额、状态、记录数或响应。

基线原始证据在 `/private/tmp/permissions-r7-independent-review-20261028/COST-COMPARISON.json`。本轮比较在 `merged-cost-comparison.json`、`merged-test-summary.json`、`logs/cost-merged-verbose-final.xml`。本轮使用此前实际独立验证的完整基线断言，没有声称重新执行整个 R6 基线。

首轮合并诊断为 2,911 通过、43 失败。修正旧测试的余额硬拦预期、未经批准直接付款夹具、历史时间窗口，以及测试自身权限编辑的时间戳；保留原金额、成本、并发、幂等和回滚断言，不 skip/xfail。最终仅剩下文列出的旧成本问题。

## 其他验证与限制

- 九组真实权限专项退出码均为 0；指定验收 16 条请求全部符合预期，拒绝均核对业务表无变更。
- 最终完整前端类型检查退出 0，Next.js 构建退出 0。原有构建跳过类型配置未改，另行执行完整 tsc。
- 新增预支执行确认测试 8 场景通过：三资金来源取消/确认，以及记录、来源失效；取消和失效零付款，确认一次付款。
- 旧前端脚本 10 组失败，在原第七轮快照也复现相同错误：9 组缺少权限组件/Hook 测试加载器映射，1 组旧工资源码冻结断言。见 `logs/ui-baseline-*`、`logs/ui-*`。不宣称这些脚本通过，与实际页面、类型、构建结果分别报告。
- 最终构建曾因借用的外部依赖目录变空失败，已按锁文件在本轮独立目录重装并成功重跑，未改包版本或放宽配置。
- 后端全量完成后只补了预支前端提示及其测试；后端未再变动，前端重新通过类型、构建与专项验证。

## 大文件与大小

持久原始备份：`/Users/xiongliu/Desktop/权限合并验收原始证据-20261028/archive`。本轮请求、日志和截图在同目录的 `evidence`、`logs` 等位置。运行环境和中间脚本在 `/private/tmp/permissions-main-merge-evidence-20261028`，不提交数据库、依赖或原始大日志。

- 123 个新增证据文件超过 1,000,000 字节，总计 1,226,620,470 字节。
- 共归档移出 2,684 份生成文档、1,308,973,112 字节、27,421,676 行，只新增本摘要。逐文件清单见 `removed-docs.json`、`large-files.json`。
- 权限运行目录保留所有实际运行字段，只移出重复源码审计元数据并紧凑存储，约 3.1 MB 降至 920,082 字节；完整元数据已归档，没有删除权限规则。
- `.gitignore` 排除 docs 的日志、JSON/JSONL、截图、XML、raw-logs；三组新测试的证据默认写仓库外。已验证忽略规则和差异空白检查。
- 版本文件总大小：权限合并前 1,382,950,865 字节；合并后清理前 1,384,641,005 字节；清理后约 75,686,610 字节，最终摘要及小测试另增加少量文本。
- Git 历史目录前后约 237 MB。没有重写历史，旧大文件仍在历史中，不能宣称历史体积已缩小；本轮只新增代码、测试及小摘要对象。精确对象统计见 `git-size-final.txt`。

## 交付边界

仅推送 main，核对远端 HEAD 后删除本轮权限分支；不删除其他任务分支。未部署，等待用户审查。

## Preserved commit ancestry

|Source|Commit|Subject|
|---|---|---|
|permissions18|`87a461b5f415`|docs: record round seven integration evidence and unresolved cost assertions|
|permissions18|`c2a2eab785f6`|fix: close round seven permission bypasses and complete action forms|
|permissions18|`0e4d2f9b45f9`|docs: hand off round six for independent permission review|
|permissions18|`06c2a24a9562`|feat: enforce versioned view operate and approve permissions|
|permissions18|`a28e128614be`|fix: enforce payroll field permissions in history and exports|
|permissions18|`4bfdb4bb4866`|fix: project employee mutation responses by authorized purpose|
|permissions18|`bf1555424cb0`|fix: scope sensitive reads exports and attachments by role|
|permissions18|`a28717065b97`|docs: hand off round four fix01 for independent revalidation|
|permissions18|`43eaec0fa048`|fix: validate personal receipt ownership after JSON model parsing|
|permissions18|`ec2666f915db`|docs: record round four local handoff and validation limitations|
|permissions18|`7134907045aa`|fix: enforce round four bookkeeping rules and independent employee approvals|
|permissions18|`1602e8133ebe`|test: restore round-three approval regression evidence|
|permissions18|`e51b6363ec5d`|docs: close round three handoff for independent review|
|permissions18|`e4d7e05b2192`|fix: separate payroll and payment approval from execution|
|permissions18|`e6cc888187d8`|docs: correct permission regression baseline evidence|
|permissions18|`422ee2b09b38`|fix: preserve approved partial petty cash reimbursements|
|permissions18|`11d032a41d0d`|fix: enforce account and petty cash permission boundaries|
|permissions18|`bc903a55c60c`|新增第一轮权限审计矩阵与本地隔离复现证据|
|main5|`6cee8b94514f`|新增到账只读匹配建议与逐行确认并支持恢复匹配前归属|
|main5|`92160ed8f0a6`|合并供应商可用性修复与独立验收补修|
|main5|`117a138efbfc`|验收补修供应商规格表单与币种单位比价|
|main5|`94c5d574efda`|统一资金余额不足为确认提示并保留执行快照与日志|
|main5|`6ec3d6216203`|将拨付预支报销余额不足改为确认提示并记录执行余额|

## 14 baseline failures: actual assertions

|Test|Actual failure (first assertion)|Baseline comparison|
|---|---|---|
|`tests.test_cost_funds_debt::test_report_costs_accounts_debt_details_and_no_writes`|assert 4234.56 == 7234.56|Same failure on baseline|
|`tests.test_cost_funds_debt::test_original_formula_balances_and_non_cost_repayment_stays_red`|assert [4234.56, 4234.56, 0.0] == [7234.56, 4234.56, 3000]|Same failure on baseline|
|`tests.test_cost_funds_debt::test_fund_withdrawal_unassigned_and_weekly_dates`|assert (250.0 == 1250)|Same failure on baseline|
|`tests.test_cost_funds_debt::test_pagination_category_exact_payer_and_shared_list_projection`|assert 6 == 8|Same failure on baseline|
|`tests.test_payroll_cash_advance::test_cost_7000_company_accounts_and_ledger_unchanged_then_revoke`|assert (2, 750.0) == (3, 7750)|Same failure on baseline|
|`tests.test_reimbursement_payments::test_company_payment_2000_exactly_one_cost_and_one_flow_revoke_keeps_voided_flow`|assert (4, 7750.0) == (3, 2750)|Same failure on baseline|
|`tests.test_reimbursement_payments::test_cash_advance_cost_only_usage_revoke_and_repay_do_not_duplicate_cost`|assert (5750.0 == 2750)|Same failure on baseline|
|`tests.test_reimbursement_payments::test_decimal_item_sums_and_partially_approved_total_used_for_payment`|assert 5750.3 == 750.3|Same failure on baseline|
|`tests.test_fund_disbursement::test_legacy_audit_preserved_and_new_spending_does_not_change_old_totals`|assert 6400.0 == 1400|Same failure on baseline|
|`tests.test_employee_advance_expense::test_fund_advance_no_cost_preserves_currency_and_no_second_company_flow`|assert not [(8, 'expense_fund', 8, 'expense_fund', '历史备用金拨付（未指定账户）', 'EF-8', 'active', '未指定账户', 1, datetime.date(2026, 9, 30), None, '备用金拨付', Decimal('5000.00'), 'CNY', None, '测试', None, 'company_account', None, None, None, True, None, None|Same failure on baseline|
|`tests.test_employee_advance_funding::test_source_money_cost_ledger_and_void[company_account]`|assert (2 == 1)|Same failure on baseline|
|`tests.test_cash_advance_repayments::test_full_repayment_money_ledger_and_costs_exactly_unchanged`|assert (3000.0 == 3000 and False is True)|Same failure on baseline|
|`tests.test_cash_advance_repayments::test_currency_is_explicit_account_must_match_and_summary_never_adds_currencies`|assert {'/income-expense/expense?category_group=operating': {'data': [{'id': 'cash_advance_repayment-1', 'source': 'cash_advance_repayment', 'source_id': 1, 'wallet_source': 'cash_advance_repayment', 'source_label': '垫款归还', 'ref_no': 'CAR-1|Same failure on baseline|
|`tests.test_cost_funds_debt_postgres::test_actual_postgres_union_types_currency_and_business_day`|assert (2000.0 == 2100)|Same failure on baseline|

## Required HTTP evidence

- `POST /payroll/2/disburse`: **403**, `{"detail": "该动作超出当前角色职责上限"}`; no business table changes.
- `PUT /payable/1/pay?paid_amount=100&account_id=1`: **403**, `{"detail": "该动作超出当前角色职责上限"}`; no business table changes.
- `POST /reimbursement/2/pay`: **403**, `{"detail": "不能核验、批准或支付本人的资金申请"}`; no business table changes.
- `POST /expense-fund/accounts/1/topup`: **403**, `{"detail": "该动作超出当前角色职责上限"}`; no business table changes.
- `PUT /suppliers/purchase-approval-threshold`: **403**, `{"detail": "该动作超出当前角色职责上限"}`; no business table changes.
- `PUT /accounts/1/toggle-status`: **403**, `{"detail": "该动作超出当前角色职责上限"}`; no business table changes.

negative-fund-warning: HTTP 200
```json
{
  "message": "拨付已执行",
  "status": "executed",
  "warning": {
    "message": "当前账户余额不足（可用 -1,000.00，本次 5,000.00），确认继续吗",
    "balance_before": -1000.0,
    "amount": 5000.0,
    "balance_after": -6000.0,
    "currency": "THB",
    "source": "company_account",
    "source_id": 1
  },
  "id": 1,
  "disbursement_id": 1,
  "fund_id": 2,
  "warehouse_id": 1,
  "amount": 5000.0,
  "currency": "THB",
  "disbursed_date": "2026-10-28",
  "payment_account_id": 1,
  "account_name": "SYNTHETIC ACCOUNT 1",
  "expense_record_id": 1,
  "recharge_request_id": 1,
  "operator_name": "SYNTHETIC staff 3",
  "created_at": "2026-10-28T09:10:54.267166+00:00",
  "remark": "拨给SYNTHETIC supervisor 2 SYNTHETIC WH1 备用金",
  "account_balance": -6000.0,
  "new_balance": 5000.0,
  "total_topped_up": 5000.0
}
```

negative-fund-repeat: HTTP 409
```json
{
  "detail": "该申请已经执行，未重复产生资金记录"
}
```

incoming-suggestions-empty-customer: HTTP 200
```json
{
  "id": 1,
  "warehouse_id": 1,
  "received_date": "2026-10-20T00:00:00",
  "amount": 3000.0,
  "currency": "THB",
  "account_id": 1,
  "payer_name": "XT10022",
  "payment_method": "银行转账",
  "remark": null,
  "match_status": "unmatched",
  "entrant_name": "",
  "created_at": "2026-10-28T09:10:54.420299+00:00",
  "request_key": "merge-incoming-1",
  "has_screenshot": false,
  "customer_id": null,
  "suggestions": [
    {
      "declaration_id": 1,
      "customer_id": 1,
      "customer_code": "XT10022",
      "customer_name": "SYNTHETIC CUSTOMER",
      "declare_date": "2026-10-20T00:00:00",
      "amount": 3000.0,
      "currency": "THB",
      "matched_count": 3,
      "matched_conditions": [
        "日期相差不超过3天",
        "金额完全相同",
        "付款方与客户名称或编号一致"
      ],
      "date_distance_days": 0
    }
  ],
  "created": true,
  "message": "录入成功"
}
```

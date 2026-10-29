# 日期查询接口扫描

基线：813f867db168cb8b4987f6aed49275e15db71853。真实应用鉴权与本机 PostgreSQL 独立随机 schema，全部合成数据。

注册路由中直接声明 date/start_date/end_date/date_from/date_to 的 GET 接口共46条，全部实际调用：43条200，3条因既有停用保护返回403。无错误被当作空列表通过。

构造10月28、29、30日三组记录（时间字段为15:30），对列表检查正例和相邻日排除，对导出解析工作簿检查。记录类默认日规则仅改打卡接口，不强行改变其他业务默认期间。

| 接口（GET） | 实际传入 | HTTP | 结果及边界 |
|---|---|---:|---|
| `/api/v1/dashboard/warehouse-summary` | end_date=2026-10-29, start_date=2026-10-29 | 200 | 过滤/范围回归正常，未修改 |
| `/api/v1/customers/{customer_id}/receivables` | end_date=2026-10-29, start_date=2026-10-29 | 403 | 既有功能停用，日期过滤未验证；未绕过保护 |
| `/api/v1/reconciliation/unmatched` | end_date=2026-10-29, start_date=2026-10-29 | 200 | 已修复：结束日期包含当天15:30申报和到账 |
| `/api/v1/reconciliation/results` | end_date=2026-10-29, start_date=2026-10-29 | 200 | 过滤/范围回归正常，未修改 |
| `/api/v1/reconciliation/export` | end_date=2026-10-29, start_date=2026-10-29 | 200 | 过滤/范围回归正常，未修改 |
| `/api/v1/income-expense/income` | end_date=2026-10-29, start_date=2026-10-29 | 200 | 过滤/范围回归正常，未修改 |
| `/api/v1/income-expense/expense` | end_date=2026-10-29, start_date=2026-10-29 | 200 | 过滤/范围回归正常，未修改 |
| `/api/v1/income-expense/expense/export` | end_date=2026-10-29, start_date=2026-10-29 | 200 | 过滤/范围回归正常，未修改 |
| `/api/v1/income-expense/ledger` | end_date=2026-10-29, start_date=2026-10-29 | 200 | 过滤/范围回归正常，未修改 |
| `/api/v1/income-expense/ledger/export` | end_date=2026-10-29, start_date=2026-10-29 | 200 | 过滤/范围回归正常，未修改 |
| `/api/v1/income-expense/income/export` | end_date=2026-10-29, start_date=2026-10-29 | 200 | 过滤/范围回归正常，未修改 |
| `/api/v1/income-expense/monthly-summary` | end_date=2026-10-29, start_date=2026-10-29 | 200 | 过滤/范围回归正常，未修改 |
| `/api/v1/income-expense/operating-dashboard` | end_date=2026-10-29, start_date=2026-10-29 | 200 | 过滤/范围回归正常，未修改 |
| `/api/v1/expense-fund/review/pending` | end_date=2026-10-29, start_date=2026-10-29 | 200 | 已修复：结束日期包含当天15:30开销 |
| `/api/v1/reimbursement` | end_date=2026-10-29, start_date=2026-10-29 | 200 | 过滤/范围回归正常，未修改 |
| `/api/v1/reimbursement/export` | end_date=2026-10-29, start_date=2026-10-29 | 200 | 过滤/范围回归正常，未修改 |
| `/api/v1/payable` | end_date=2026-10-29, start_date=2026-10-29 | 200 | 过滤/范围回归正常，未修改 |
| `/api/v1/payable/stats` | end_date=2026-10-29, start_date=2026-10-29 | 200 | 过滤/范围回归正常，未修改 |
| `/api/v1/payable/batch-export` | end_date=2026-10-29, start_date=2026-10-29 | 200 | 已修复：结束日期包含当天15:30到期账单（沿用到期日口径） |
| `/api/v1/credit/shipments` | end_date=2026-10-29, start_date=2026-10-29 | 403 | 既有功能停用，日期过滤未验证；未绕过保护 |
| `/api/v1/credit/{credit_id}/detail` | end_date=2026-10-29, start_date=2026-10-29 | 200 | 发货/还款列表按范围；当前余额及其累计依据不改。 |
| `/api/v1/reports/cost-funds-debt` | end_date=2026-10-29, start_date=2026-10-29 | 200 | 实际调用成功且期间回传正确；成本公式未更改，本轮不重验全套成本口径。 |
| `/api/v1/reports/cost-funds-debt/costs` | end_date=2026-10-29, start_date=2026-10-29 | 200 | 过滤/范围回归正常，未修改 |
| `/api/v1/reports/cost-funds-debt/flows` | end_date=2026-10-29, start_date=2026-10-29 | 200 | 过滤/范围回归正常，未修改 |
| `/api/v1/reports/cost-funds-debt/advances` | end_date=2026-10-29, start_date=2026-10-29 | 200 | 过滤/范围回归正常，未修改 |
| `/api/v1/reports/previews` | end_date=2026-10-29, start_date=2026-10-29 | 200 | 期间数据已校验；备用金/账期余额是当前值，对账差异按月，保留既有口径。 |
| `/api/v1/reports/recharge-summary` | end_date=2026-10-29, start_date=2026-10-29 | 200 | 过滤/范围回归正常，未修改 |
| `/api/v1/reports/incoming-summary` | end_date=2026-10-29, start_date=2026-10-29 | 200 | 过滤/范围回归正常，未修改 |
| `/api/v1/reports/income-expense` | end_date=2026-10-29, start_date=2026-10-29 | 200 | 过滤/范围回归正常，未修改 |
| `/api/v1/reports/payable` | end_date=2026-10-29, start_date=2026-10-29 | 200 | 过滤/范围回归正常，未修改 |
| `/api/v1/reports/reimbursement` | end_date=2026-10-29, start_date=2026-10-29 | 200 | 过滤/范围回归正常，未修改 |
| `/api/v1/reports/reconciliation-diff` | end_date=2026-10-29, start_date=2026-10-29 | 200 | 按月份统计；日期选择对应月份，并非逐日明细，保留既有口径。 |
| `/api/v1/reports/operations` | end_date=2026-10-29, start_date=2026-10-29 | 403 | 既有功能停用，日期过滤未验证；未绕过保护 |
| `/api/v1/settings/logs` | date=2026-10-29 | 200 | 已修复：日期绑定类型，消除 PostgreSQL date=varchar 错误 |
| `/api/v1/clock-in/records` | date=2026-10-29 | 200 | 已修复：date/month/仓库/员工过滤、默认泰国今天、50条分页（最多100） |
| `/api/v1/clock-in/makeup-batches` | end_date=2026-10-29, start_date=2026-10-29 | 200 | 过滤/范围回归正常，未修改 |
| `/api/v1/clock-in/makeup-count` | date=2026-10-29, employee_id=100 | 200 | 指定日期所在月份的补卡额度查询，不是单日记录列表。 |
| `/api/v1/clock-in/records/export` | end_date=2026-10-29, start_date=2026-10-29 | 200 | 过滤/范围回归正常，未修改 |
| `/api/v1/clock-in/photos` | date=2026-10-29, employee_id=100 | 200 | 单日四个打卡时段；正例员工100。 |
| `/api/v1/attendance/leaves` | end_date=2026-10-29, start_date=2026-10-29 | 200 | 过滤/范围回归正常，未修改 |
| `/api/v1/attendance/rest-days` | end_date=2026-10-29, start_date=2026-10-29 | 200 | 过滤/范围回归正常，未修改 |
| `/api/v1/attendance/calendar` | end_date=2026-10-29, start_date=2026-10-29 | 200 | 过滤/范围回归正常，未修改 |
| `/api/v1/attendance/exemptions` | end_date=2026-10-29, start_date=2026-10-29 | 200 | 过滤/范围回归正常，未修改 |
| `/api/v1/history` | end_date=2026-10-29, start_date=2026-10-29 | 200 | 过滤/范围回归正常，未修改 |
| `/api/v1/history/export` | end_date=2026-10-29, start_date=2026-10-29 | 200 | 过滤/范围回归正常，未修改 |
| `/api/v1/cash-advances` | end_date=2026-10-29, start_date=2026-10-29 | 200 | 过滤/范围回归正常，未修改 |

3条停用接口不能宣称日期验证通过；月报/当前余额也不能拿“只返回当天逐笔记录”作为验收口径。静态检查与合成样本不代表线上历史数据已验证。

原始请求、响应、解析后的导出、修复前失败证据：`/Users/xiongliu/Desktop/打卡日期筛选验收-20261029/`。不提交原始 JSON、截图和日志到 Git。

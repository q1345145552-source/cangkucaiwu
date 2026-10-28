# 采购审批门槛与列表筛选验收（2026-10-28）

## 基线、范围

实际工作树 `/private/tmp/supplier-import-main-20261027`，分支 `main`，基线 `6f7ae35552eae3ef73e57a86fb7c0711163571bf`。仅本地合成数据；不连接生产、不部署、不推送。未修改数据库结构、采购金额算法、应付生成实现或历史订单状态，无迁移/补审批。

## 修复清单

| 问题 | 修改 | 验证 |
|---|---|---|
| 采购门槛 0 被当作关闭审批 | `suppliers.create_purchase_order`：0 一律 pending，正数仅超过门槛 pending；沿用负数 400 校验 | 0/5、1000/500、1000/1000、1000/2000；无配置默认 0；负数拒绝且设置保持不变 |
| 采购列表忽略 status | `GET /suppliers/purchase-orders` 接收 status，并同步过滤数据和 total | pending/confirmed/不传、分页、无匹配、切仓隔离 |
| 充值申报接收 search 但未使用 | `GET /recharge` 按客户名称、交易号、备注搜索，数据与 total 共用条件，转义通配字符 | 关键词、无匹配、特殊 %、月份+状态组合、跨仓记录排除 |
| 市场搜索关键词含 & 被截断 | 前端对 search 使用 encodeURIComponent | 真实手机浏览器搜索“甲&乙”只返回该商品，排除“甲其他” |

配置中心显示：**填 0 表示所有采购单都需要审批**。采购单列表增加状态选择，传 pending/confirmed/rejected，全部不传 status；序列号防止快速切换时旧请求覆盖新结果。收货列表原调用不传 status，保持原展示范围。

## 第一步至第五步实际结果

全部为本地合成账号、真实应用路由/JWT/独立 PostgreSQL schema，未模拟放行鉴权。

1. 保存 0：HTTP 200 `{"message":"采购审批门槛已设为 0.0 泰铢","threshold":0.0}`。手机页面小字逐字验证。负数 HTTP 400 `{"detail":"门槛金额不能为负数"}`，没有改动设置。
2. 五元单：HTTP 200，`message=采购单已提交审批, order.id=3, total_amount=5, pending=true, payable_bill_id=null`。数据库状态 pending，尚无应付。
3. 独立管理员 96 在审批列表看到订单 3，通过后 HTTP 200 `{"message":"审批通过，应付账单已生成","payable_bill_id":2,"duty_execution_id":1,"duty_operator_id":96}`。数据库订单 confirmed，应付 2 金额 5，关联订单 3。未修改原审批职责开关或绕过版本/例外保护。
4. 为验证待批筛选另建订单 4。pending 返回 total=1（订单 4）；confirmed 返回 total=3（3、2、1，全部 confirmed）；不传返回 total=4（1 条 pending、3 条 confirmed）。分页 page_size=1 时 total 仍为 3。
5. 门槛 1000：500 元订单 5，HTTP 200，pending=false、应付 3，数据库 confirmed；2000 元订单 7，HTTP 200，pending=true、payable_bill_id=null，数据库 pending。补验边界恰好 1000 元订单 6直接 confirmed、应付 4。

两张合成旧单 1、2 前后均为 confirmed。修改设置不触发旧单更新。

## 其他筛选盘查范围

扫描全项目后端 GET 路由声明的状态、日期、月份、关键词等参数，形成 77 个处理函数清单；检查参数是否被读取、where/filter 是否丢弃返回查询，并核对前端显式查询参数。发现并修复上述充值搜索与市场关键词问题。报表中表面未读取的日期参数由 `selected_report_scope` 依赖读取，经过 `money_period` 和 `scoped_query` 应用于查询，并非失效。本轮包含报表预览范围与资金记录日期范围实际回归。

这是一轮静态扫描加相关接口/页面验证，不代表 77 个接口的每个筛选组合均已逐一动态验证；未对全站所有页面逐页验收，不宣称全系统无其他筛选问题。

| 文件 | 处理函数 | 声明的筛选参数 |
|---|---|---|
| `backend/app/api/v1/efficiency.py` | `get_summary` | week_start, month |
| `backend/app/api/v1/efficiency.py` | `get_compare` | week_start, month |
| `backend/app/api/v1/efficiency.py` | `get_daily_orders` | month |
| `backend/app/api/v1/efficiency.py` | `get_standard` | month |
| `backend/app/api/v1/overtime.py` | `list_overtimes` | pending_verification, status, month |
| `backend/app/api/v1/overtime.py` | `monthly_hours` | month |
| `backend/app/api/v1/cost_funds_debt.py` | `get_report` | start_date, end_date, month, year |
| `backend/app/api/v1/cost_funds_debt.py` | `costs` | start_date, end_date, month, year |
| `backend/app/api/v1/cost_funds_debt.py` | `flows` | start_date, end_date, month, year |
| `backend/app/api/v1/cost_funds_debt.py` | `advances` | start_date, end_date, month, year |
| `backend/app/api/v1/settings_api.py` | `operation_logs` | date |
| `backend/app/api/v1/income_expense.py` | `list_income` | month, year, start_date, end_date, search |
| `backend/app/api/v1/income_expense.py` | `list_expense` | month, year, start_date, end_date, search |
| `backend/app/api/v1/income_expense.py` | `export_expense` | month, year, start_date, end_date, search |
| `backend/app/api/v1/income_expense.py` | `ledger` | start_date, end_date, month, year |
| `backend/app/api/v1/income_expense.py` | `ledger_export` | start_date, end_date, month, year |
| `backend/app/api/v1/income_expense.py` | `export_income` | month, year, search, start_date, end_date |
| `backend/app/api/v1/income_expense.py` | `monthly_summary` | start_date, end_date, month, year, search |
| `backend/app/api/v1/income_expense.py` | `operating_dashboard` | start_date, end_date, month, year |
| `backend/app/api/v1/reconciliation.py` | `get_unmatched` | start_date, end_date |
| `backend/app/api/v1/reconciliation.py` | `list_results` | start_date, end_date, search, search_code |
| `backend/app/api/v1/reconciliation.py` | `export_reconciliation` | start_date, end_date, search, search_code |
| `backend/app/api/v1/market.py` | `list_items` | search, status |
| `backend/app/api/v1/expense_approval.py` | `list_approvals` | status |
| `backend/app/api/v1/attendance.py` | `list_leaves` | start_date, end_date, status |
| `backend/app/api/v1/attendance.py` | `list_rest_days` | start_date, end_date |
| `backend/app/api/v1/attendance.py` | `get_calendar` | start_date, end_date |
| `backend/app/api/v1/employee_advance.py` | `list_advances` | approval_status |
| `backend/app/api/v1/access.py` | `choices` | search |
| `backend/app/api/v1/clock_in.py` | `list_records` | start_date, end_date |
| `backend/app/api/v1/clock_in.py` | `list_makeup_batches` | start_date, end_date |
| `backend/app/api/v1/clock_in.py` | `makeup_count` | date |
| `backend/app/api/v1/clock_in.py` | `export_records` | start_date, end_date |
| `backend/app/api/v1/clock_in.py` | `get_photos` | date |
| `backend/app/api/v1/reimbursement.py` | `list_reimbursements` | month, status, start_date, end_date |
| `backend/app/api/v1/reimbursement.py` | `export_reimbursements` | month, status, start_date, end_date |
| `backend/app/api/v1/payroll.py` | `list_payroll` | settle_month, status, voided_filter |
| `backend/app/api/v1/payroll.py` | `payroll_summary` | settle_month, status, voided_filter |
| `backend/app/api/v1/payroll.py` | `export_payroll` | settle_month, status, voided_filter |
| `backend/app/api/v1/dashboard.py` | `warehouse_summary` | start_date, end_date, month |
| `backend/app/api/v1/dashboard.py` | `dashboard_trends` | month |
| `backend/app/api/v1/dashboard.py` | `dashboard_cockpit` | month |
| `backend/app/api/v1/expense_fund.py` | `list_pending_reviews` | start_date, end_date |
| `backend/app/api/v1/expense_fund.py` | `list_recharge_requests` | status |
| `backend/app/api/v1/reports.py` | `report_previews` | start_date, end_date |
| `backend/app/api/v1/reports.py` | `recharge_summary` | start_date, end_date |
| `backend/app/api/v1/reports.py` | `incoming_summary` | start_date, end_date |
| `backend/app/api/v1/reports.py` | `income_expense_report` | start_date, end_date, month, year |
| `backend/app/api/v1/reports.py` | `payable_report` | start_date, end_date |
| `backend/app/api/v1/reports.py` | `reimbursement_report` | start_date, end_date |
| `backend/app/api/v1/reports.py` | `reconciliation_diff_report` | start_date, end_date |
| `backend/app/api/v1/reports.py` | `operating_report` | month, start_date, end_date |
| `backend/app/api/v1/employees.py` | `list_employees` | status |
| `backend/app/api/v1/employees.py` | `employee_summary` | month |
| `backend/app/api/v1/suppliers.py` | `list_purchase_orders` | status |
| `backend/app/api/v1/suppliers.py` | `concentration_analysis` | month |
| `backend/app/api/v1/suppliers.py` | `concentration_trend` | months |
| `backend/app/api/v1/suppliers.py` | `list_suppliers` | search |
| `backend/app/api/v1/payable.py` | `list_bills` | status, month, start_date, end_date |
| `backend/app/api/v1/payable.py` | `payable_stats` | start_date, end_date, status, all_dates |
| `backend/app/api/v1/payable.py` | `batch_export` | start_date, end_date, status |
| `backend/app/api/v1/payable.py` | `get_monthly_order` | start_month, end_month |
| `backend/app/api/v1/payable.py` | `payable_trend` | months |
| `backend/app/api/v1/recharge.py` | `list_recharges` | month, status, search |
| `backend/app/api/v1/group_order.py` | `list_group_orders` | status |
| `backend/app/api/v1/customers.py` | `customer_receivables` | month, start_date, end_date |
| `backend/app/api/v1/customers.py` | `list_customers` | search, credit_status |
| `backend/app/api/v1/credit.py` | `list_shipments` | month, start_date, end_date, status |
| `backend/app/api/v1/credit.py` | `credit_detail` | start_date, end_date, month |
| `backend/app/api/v1/incoming.py` | `list_incoming` | month, status |
| `backend/app/api/v1/cash_advance.py` | `document_options` | search |
| `backend/app/api/v1/cash_advance.py` | `list_advances` | start_date, end_date, status |
| `backend/app/api/v1/history.py` | `list_history` | start_date, end_date |
| `backend/app/api/v1/history.py` | `export_history` | start_date, end_date |
| `backend/app/api/v1/inventory.py` | `pending_receipts` | status |
| `backend/app/api/v1/inventory.py` | `get_analysis` | month |
| `backend/app/api/v1/inventory.py` | `export_analysis` | month |

## 回归、测试兼容及原始证据

最终 **111 通过、0 失败、0 跳过**；完整前端 TypeScript 检查、构建退出码 0；真实浏览器 390×844 验证配置保存、小字、采购筛选和市场特殊关键词，退出码 0。

回归覆盖供应商删除/启停、SKU、产品报价、采购、审批职责与例外授权、收货、应付/付款、报表日期范围等。原有财务/收货测试过去依赖“未设置门槛即免审批”，现在夹具显式设置合成全局正数门槛 1000000，以继续检查原金额、收货、付款断言；未删除或 skip 这些断言。专门的新测试不设置该夹具默认值，验证未配置时返回 0 且需要审批。既有职责测试创建全局仓库改为不存在才创建，仍完整检查恶意全局职责配置不能绕过专用配置。

原始证据目录：`/Users/xiongliu/Desktop/采购门槛与筛选验收-20261028`。隔离环境：`/private/tmp/purchase-threshold-20261028`，数据库仅 `127.0.0.1:65519/lifecycle`，每个测试使用 UUID schema；使用本地网络限制 guard。日志 `logs/final.xml`、`final.log/exit` 为最终后端结果，`tsc-final.log/exit`、`build-final.log/exit`、`browser-final.log/exit` 为类型、构建和浏览器结果。`actual.json` 保存完整原始返回，`browser-results-final.json` 保存页面实际结果，PNG 保存手机截图。运行说明 `REPRODUCE.md` 在外部证据目录。

保留早期失败日志：数据库初次启动未指定测试端口导致连接拒绝；合成客户漏填 customer_code；正数门槛夹具漏建全局仓库；既有职责夹具重复创建同一仓库。这些均为本次测试准备问题，修正夹具后重跑通过，不归类为业务基线问题。仓库仅保留本摘要和必要测试，原始 JSON/日志/截图不提交。

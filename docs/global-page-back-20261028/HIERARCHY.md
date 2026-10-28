# 页面上级关系实际配置

管理端无历史时使用下表；有可用本站历史时优先返回历史，不弹确认。

## 47 个新增返回入口

| 序号 | 页面 | 地址 | 无历史时的上级 |
|---:|---|---|---|
| 1 | 收款账户 | `/accounts` | 仪表盘 `/dashboard` |
| 2 | 考勤管理 | `/attendance` | 仪表盘 `/dashboard` |
| 3 | 操作日志 | `/audit-logs` | 仪表盘 `/dashboard` |
| 4 | 垫款单列表 | `/cash-advances` | 仪表盘 `/dashboard` |
| 5 | 收支类别管理 | `/categories` | 配置中心 `/config-center` |
| 6 | 打卡 | `/clock-in` | 仪表盘 `/dashboard` |
| 7 | 打卡记录 | `/clock-records` | 工作考勤 `/attendance` |
| 8 | 供应商采购分析 | `/concentration` | 供应商档案 `/suppliers` |
| 9 | 配置中心 | `/config-center` | 仪表盘 `/dashboard` |
| 10 | 账期管理 | `/credit` | 仪表盘 `/dashboard` |
| 11 | 客户档案 | `/customers` | 仪表盘 `/dashboard` |
| 12 | 扣款模板 | `/deduction-templates` | 仪表盘 `/dashboard` |
| 13 | 员工预支 | `/employee-advances` | 仪表盘 `/dashboard` |
| 14 | 员工扣款 | `/employee-deductions` | 仪表盘 `/dashboard` |
| 15 | 员工管理 | `/employees` | 仪表盘 `/dashboard` |
| 16 | 费用审批 | `/expense-approvals` | 仪表盘 `/dashboard` |
| 17 | 备用金管理 | `/expense-fund` | 仪表盘 `/dashboard` |
| 18 | 费用来源核对 | `/expense-identities/[source]/[id]` | 按 source：应付账款 / 费用审批 / 备用金管理 / 运营支出 |
| 19 | 备用金审核 | `/fund-review` | 备用金管理 `/expense-fund` |
| 20 | 拼单功能 | `/group-order` | 仪表盘 `/dashboard` |
| 21 | 收付款管理 | `/income-expense` | 运营收支 `/operating` |
| 22 | 到账流水 | `/incoming` | 仪表盘 `/dashboard` |
| 23 | 耗材库存 | `/inventory` | 供应商档案 `/suppliers` |
| 24 | 人效管理 | `/labor-efficiency` | 仪表盘 `/dashboard` |
| 25 | 资金流水 | `/ledger` | 仪表盘 `/dashboard` |
| 26 | 商品展示区 | `/market` | 仪表盘 `/dashboard` |
| 27 | 修改日志 | `/modification-logs` | 仪表盘 `/dashboard` |
| 28 | 我的考勤 | `/my-attendance` | 仪表盘 `/dashboard` |
| 29 | 我的请假 | `/my-leave` | 仪表盘 `/dashboard` |
| 30 | 我的加班 | `/my-overtime` | 仪表盘 `/dashboard` |
| 31 | 我的工资单 | `/my-payslip` | 仪表盘 `/dashboard` |
| 32 | 我的申请与欠款 | `/my-requests` | 仪表盘 `/dashboard` |
| 33 | 运营支出 | `/operating` | 仪表盘 `/dashboard` |
| 34 | 其他收入 | `/other-income-expense` | 仪表盘 `/dashboard` |
| 35 | 加班管理 | `/overtime` | 仪表盘 `/dashboard` |
| 36 | 应付账款 | `/payable` | 仪表盘 `/dashboard` |
| 37 | 付款计划 | `/payment-plans` | 仪表盘 `/dashboard` |
| 38 | 工资管理 | `/payroll` | 仪表盘 `/dashboard` |
| 39 | 充值申报 | `/recharge` | 仪表盘 `/dashboard` |
| 40 | 对账中心 | `/reconciliation` | 仪表盘 `/dashboard` |
| 41 | 报销管理 | `/reimbursement` | 仪表盘 `/dashboard` |
| 42 | 报表中心 | `/reports` | 仪表盘 `/dashboard` |
| 43 | 工资模板 | `/salary-templates` | 仪表盘 `/dashboard` |
| 44 | 系统设置 | `/settings` | 仪表盘 `/dashboard` |
| 45 | 标准SKU目录 | `/supplier-skus` | 供应商档案 `/suppliers` |
| 46 | 供应商档案 | `/suppliers` | 仪表盘 `/dashboard` |
| 47 | 仓库档案 | `/warehouses` | 仪表盘 `/dashboard` |

## 7 个既有入口统一组件

| 序号 | 页面 | 地址 | 无历史时的上级 |
|---:|---|---|---|
| 1 | 垫款单详情 | `/cash-advances/[id]` | 垫款单 `/cash-advances` |
| 2 | 成本资金欠款 | `/reports/cost-funds-debt` | 报表中心 `/reports` |
| 3 | 采购职责与例外 | `/suppliers/controls` | 采购风险看板 `/suppliers/risk` |
| 4 | 采购价差月报 | `/suppliers/monthly-price-report` | 供应商档案 `/suppliers` |
| 5 | 采购单详情 | `/suppliers/purchase-orders/[id]` | 应付账款 `/payable` |
| 6 | 采购风险看板 | `/suppliers/risk` | 供应商档案 `/suppliers` |
| 7 | 采购复核历史 | `/suppliers/risk/reviews` | 采购风险看板 `/suppliers/risk` |

## 顶层和角色差异

- `/` 只跳转；`/login` 登录、`/dashboard` 仪表盘不加返回。
- 劳工以 `/clock-in` 为员工首页，不加返回；其原有权限允许的考勤、加班、工资单、设置回该首页。没有增加可访问页面。
- 财务/主管的个人页面回 `/dashboard`。
- 系统总管理员默认回 `/warehouses`；该角色的仓库档案作为首页不加返回。
- 费用来源：`payable → /payable`、`approval → /expense-approvals`、`fund_item → /expense-fund`、`expense → /operating`。

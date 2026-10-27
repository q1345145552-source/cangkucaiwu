# 全项目余额不足改提示验收（2026-10-28）

## 范围与隔离

在 `/tmp/all-balance-warning-20261028`、分支 `codex/all-balance-warning-20261028` 接续主支 `6ec3d6216203e35415fb749de8f1f8fe0763fe7f`。原工作树 `/Users/xiongliu/Desktop/海外仓财务系统` 为 `codex/supplier-optimization-20261026`，HEAD `79fae5f59d710e1e4e8176b325f0bfe861b4269a`；其中员工、代办等未提交任务没有混入。

上一轮已提交的公司账户拨备用金、公司账户预支、备用金/公司账户报销警告机制保留。本批新增工资、应付、费用审批和搜索发现的其他资金余额检查，复用同一警告和修改日志服务。只使用虚构数据、临时 SQLite 与 localhost PostgreSQL 随机 schema；不接生产，不修改真实账户、真实付款或已付款记录。没有数据库迁移、库存计价或金额计算改动。未读取 `.deploy`，未 SSH，未部署。

## 实际结果（第一至第四步）

| 验证 | 实际结果 |
|---|---|
| 单笔工资 | HTTP 200；THB 1,234.56；账户 -1,000 → -2,234.56；支出 0 → 1；返回 warning；修改日志 1 条 |
| 批量工资 | HTTP 200；合计 1,334.57；账户 -1,000 → -2,334.57；两张工资各一笔支出；原批次重试 count=0，无再次扣款 |
| 应付付款 | 5 个并发相同原请求全部 200，同一个 payment_id；付 500，账户 -1,000 → -1,500；原请求再试返回原 warning，无再次扣款 |
| 费用审批／公司 | 4 个并发请求仅付款一次；付 200，账户 -1,000 → -1,200；支出/资金记录各一次；重试返回原 warning |
| 费用审批／备用金 | 可用 50，付 200，warning 列出执行后 -150；备用金开销 1 条，公司账户 -1,000 保持不变，没有额外公司支出；重试不重复 |
| 其他位置 | 手工支出、内部转账、备用金开销新增/编辑、预支备用金/垫款、工资垫款、报销垫款、付款计划均已验证余额不足可执行 |

工资接口实际返回中的关键字段：

```json
{"warning":{"balance_before":-1000.0,"amount":1234.56,"balance_after":-2234.56,"currency":"THB","source":"company_account","source_id":1},"id":2,"net_pay":1234.56,"expense_record_id":1,"account_id":1,"funding_source":"company_account"}
```

完整返回、账余额、支出数量、操作人和日志见 `step1-salary.json`、`step1-batch.json`、`step2-payable.json`、`step3-company-fee.json`、`step3-fund-fee.json`。

备用金保持原计算：费用审批登记备用金开销，不额外扣一次原始 remaining_balance；原有“可用金额不小于 0”的展示算法仍保留，所以此例页面计算可用金额显示 0，warning 的执行后快照为 -150。没有为了让显示变负而更改任何财务公式。

## 搜索与修复清单

以余额不足、余额不够、insufficient balance、overdraft、overdraw、剩余金额不足、超出可用余额及金额比较分支检查前后端。基线共 13 个后端资金余额硬拦判断，全部替换：

| 数量 | 位置 | 本批处理 |
|---|---|---|
| 1 | `backend/app/api/v1/payroll.py::_disbursement_funding` | 单笔/批量公司工资返回余额警告，正常支出、扣款与流水 |
| 1 | `backend/app/services/payable_payment.py::record_payment` | 应付单笔及计划共用；原付款编号恢复原警告快照 |
| 1 | `backend/app/api/v1/expense_approval.py::_generate_operating_expense` | 公司支付警告和日志 |
| 1 | 同文件 `::_link_fund` | 备用金支付警告和日志，原选取规则不变 |
| 2 | `backend/app/services/cash_advance_payroll.py::lock_payroll_advance` | 垫款未归还和剩余使用容量均改提示 |
| 2 | `backend/app/services/employee_advance_funding.py::validate_funding` | 垫款/备用金容量改提示；执行时锁定后生成快照，含审批路径 |
| 1 | `backend/app/services/reimbursement_payment.py::lock_advance` | 报销垫款容量改提示 |
| 1 | `backend/app/services/manual_wallet.py::prepare` | 手工支出改警告，原操作编号和指纹保留 |
| 1 | `backend/app/api/v1/payment_accounts.py::create_transfer` | 内部转账改警告，仍不计收入支出 |
| 1 | `backend/app/api/v1/expense_fund.py::add_item` | 新增开销改警告，原请求重试只读原快照 |
| 1 | `backend/app/services/fund_item_controls.py::update_item` | 允许修改的未审核开销改警告；已审核禁止改动规则保留 |

原始搜索见 `search-before.txt`、`search-after.txt`、`search-comparisons.txt`。剩余拦截为库存数量、账户不存在/停用/外仓/币种、权限、付款超过剩余应付、还款超过未还、金额合法性、备用金上限，均不是资金余额不足。没有修改这些规则。

前端工资（单笔/批量）、应付及计划、费用审批两种来源、预支创建及审批、报销垫款、手工支出两入口、内部转账、备用金开销均在写入/凭证上传前刷新余额并使用统一确认：

> 当前账户余额不足（可用 X，本次 Y），确认继续吗

取消不发付款/保存/凭证上传请求；确认继续沿用原入口。服务端不把警告作为新审批门槛。并发下每笔日志以锁定后的余额为准。日志包含操作人、时间、模块、当时余额、本次金额、执行后余额和“余额不足仍然执行”。重试保存快照，不用新余额伪造过去的警告。

## 上限与计算保护

`step5-fund-cap.json`：负公司账户拨 5,001，HTTP 400，“超出账户上限（5,000）”；账户仍 -1,000，没有新增支出或余额警告日志。

新增源码保护测试对照本轮基线：账户余额算法、流水口径、备用金拨付实现、工资支出金额算法文件完全未变；工资计算函数、备用金可用算法、垫款使用算法 AST 一致。

## 验证与限制

- `acceptance-complete.log/.xml`：33 项通过，0 失败、0 skip，退出码 0。含 15 项本批专项，6 项原现金账户/并发/回滚测试，12 项费用审批原测试及更新的余额政策断言。
- `policy-tests.log/.xml`：相关 153 项，124 通过、29 失败、0 skip，退出码 1。
- `baseline-related-final.log/.xml`：同组修改前 153 项，117 通过、36 失败。最终 29 个失败均在基线失败名单中，没有新增失败；详见 `regression-comparison.json`。未改变历史测试以掩盖失败。
- 失败涉及旧成本/余额种子断言、旧撤销路径、旧源码冻结比较等。本批仅更新与“余额不足仍执行”直接冲突的断言，保留权限、币种、限额、原子回滚、原请求重试等有效断言，不 skip、不删除测试。
- 前端实际组件/处理函数：工资 24 场景、预支 12 场景，以及应付、费用审批、报销、备用金、备用金开销控制、手工钱包、运营页共 9 组最终脚本通过，退出码均为 0。包括负余额取消零写入、接受一次写入、费用双击、应付丢响应/凭证重试及切仓/切账号保护。详见 `ui-*.log`。旧的 `ui-supervisor` 脚本需独立历史 fixture，本批未启动该 fixture；该次启动检查退出 1，不宣称通过。
- `types-verified.log`：全前端类型检查通过，退出码 0。
- `build-verified.log`：完整 Next.js 构建通过，退出码 0。
- `compile-final.log`：后端编译检查通过，退出码 0；最终补充检查见 commands。
- `commands.jsonl` 保存各次原始命令、工作目录、耗时及退出码；包含调试期间失败与后续修正重跑，不隐藏失败记录。

没有生产实测，也没有逐个页面真机点击或全项目所有历史测试全绿的结论。手机只覆盖既有滚动弹框断言，未进行本轮手机浏览器视觉验收。未扩展历史类型修复、历史撤销或成本口径任务。

## 提交与推送

本批只提交本隔离工作树的余额提示代码、相关测试和本目录证据；此前未提交任务不在提交内。按会话既有授权推送 GitHub 主支，不部署。实际提交号、远端主支核验结果由最终交付给出。

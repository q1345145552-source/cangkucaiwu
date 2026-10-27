# 第二轮补修：关联备用金报销部分批准

> fix02更正：不能仅按失败名称相同认定同根因。fix01归档基线有4项缺Git历史提前失败，现已用独立工作树定向补证。原52项中47项非源码失败已核对实际断言，5项源码检查须区分历史差异与本轮授权改变；旧的笼统结论撤回。详见[更正报告](../permissions-r02-fix02-20261028/REPORT.md)。原始日志保留。

唯一标记：`permissions7-r02-fix01-20261028`。本次只修第二轮独立验收发现的缺陷及同根因交叉入口问题，不进入第三轮。

## 提交与边界

- 工作树：`/private/tmp/permissions-round2-20261028`，分支：`codex/permissions-round2-20261028`。
- 补修基线：`11d032a41d0d39d770285ce5367ea4d15a2e8e51`，起点工作区干净。追加提交完整HEAD见最终回复及本地Git，不amend原候选。
- 原独立证据：`/private/tmp/permission-r2-review-800p5mtu/partial_probe.py`、`partial-probe.json`、`partial-probe.log`，只读，未覆盖。原第二轮和第一轮证据均未修改。
- 新隔离集群：`/private/tmp/permissions-r02-fix01-env/pgdata`，只监听localhost端口65349，合成round2库。无生产连接，不使用原审查数据库。
- 只有三个业务文件变更：`backend/app/api/v1/reimbursement.py`、`backend/app/api/v1/expense_fund.py`、`backend/app/services/fund_authorization.py`；另加本次真实路由测试与文档/日志。无前端、模型、数据库结构或迁移变更。

## 根因与修复

原候选在报销全部批准分支才设置备用金项为approved并保存批准证据。30/10部分批准只设置报销父单partially_approved和30元总额，付款守卫因此409。原备用金批准快照还没有包含报销明细，且批量批准未同步明细决定。

|入口/修改|目标行为|证据请求ID|
|---|---|---|
|POST `/reimbursement/{id}/review`|全部批准与部分批准均建立批准状态及完整快照；关联单所有明细必须明确决定，不能将未决定当作驳回；缺决定整批400|approve-200-partial、approve-201-full、missing-line-decision、missing-line-only-reject|
|POST `/expense-fund/review/batch` verify|真实核验记录覆盖父单、全部明细及备用金原始预留金额；不批准、不付款|verify-*、stale-verification|
|同接口 approve|仅完整待处理的关联单可走整单批准；同步全部明细为approved并保存相同快照。已有部分审批不能被第二入口升级全额|batch-full-approve、batch-full-pay、cross-entry-*、stale-verification-batch|
|GET报销详情、POST `/reimbursement/{id}/pay`|can_fund_pay与付款使用同一守卫；核对父单、明细、批准合计、仓库/受益人/币种及完整快照；只支付实际批准额|capability-200、pay-200、stale-amount/status/description、legacy-item-only-proof|
|付款事务/并发|保留原父单锁、付款唯一效果及事务；重复请求拒绝；中途异常不留付款或余额变化，随后可独立重试|repeat-pay-*、concurrent-payment、payment-mid-transaction-failure、payment-after-rollback|
|角色/本人/归属|不放宽原守卫；代录本人、关联员工别名、自付、外仓、伪造仓库头、禁用和无附加权限账号均拒绝|on-behalf-*、employee-alias-self-pay、pay-role-*、foreign-*、mixed-parent-review|

逐项实际状态码、请求体、响应、全部数据库表前后差异及断言错误见[原始请求证据](requests.json)。全部拒绝均检查业务表无变化，审计记录单独区分。仅付款中途失败场景替换记审计历史的函数以注入故障，真实路由/JWT/角色鉴权/数据库不替换。

## 金额与余额：40元原始登记，批准30元，驳回10元

|阶段|报销父单|明细|备用金项|余额/付款事实|
|---|---|---|---|---|
|申请登记|40，fund_linked|30/10均pending|40，pending|沿用原登记时预留40|
|财务核验|40，fund_linked|不变|40，verified|无新增扣款、付款或费用|
|管理员部分批准|30，partially_approved|30 approved，10 rejected|保留原预留40，状态approved；批准快照明确父单批准30和每条决定|余额不变；不自动付款|
|独立财务执行|30，paid|决定不变|原预留40及批准证据不变|只生成一笔30元ReimbursementPayment；不再扣40、不释放10、不新增ExpenseRecord|

`ExpenseFundItem.amount`在此保留原申请预留金额，并不作为付款金额；付款金额取已验证的批准明细合计/父单总额30。批准证据同时覆盖两者，不能用40作为获准付款额。报销类原已用统计仍按原预留口径，本次没有擅自决定驳回10元的最终退款或成本归属。该差额后续实际处置需单独核对，不新增隐式释放或扣款。

全部驳回保留原一次性退回40的行为；重复报销驳回、重复备用金批量驳回都拒绝。备用金批量驳回原有解关联行为保留，不恢复停用的付款撤销功能。货币比较复用原付款money函数的精度/容差，未改存储金额和余额公式；通过真实创建0.1+0.2的全批和部分批准付款验证。

## 状态与历史兼容

- 关联单核验后必须提交全部明细的明确决定，才能形成终态批准/部分批准/全部驳回。漏决定400，整批不改变。
- 已形成批准证据的部分批准单不可再审、再核验或从批量入口重新批准/驳回；避免重复退款、扩大支付额。普通非备用金报销的原再审规则未改变。
- 改动任何已核验/批准的明细金额、决定、说明/凭证或父单关键内容，旧证据不再匹配，执行409。
- 旧只有备用金项、不含关联报销明细的核验/批准快照不自动转换为新批准。历史已执行不重付；历史待处理缺证据安全拒绝，需独立核对并安排明确恢复步骤。本次不为历史记录批量补写批准、不擅自设计替代审批人。
- 没有数据库迁移。恢复旧代码会重新暴露部分批准断链及不完整快照问题，不应视为安全回退方案。

## 验证

- 新增`backend/tests/permission_round2/partial_acceptance.py`：84条记录、85次真实HTTP请求，失败0。包括并发2请求，金额/余额/证据快照断言及全表副作用检查。
- 原第二轮目标脚本：176条记录、177次请求，失败0；输出另存[本次复跑目录](original-target/target-status.json)，未覆盖原证据。
- 受影响五文件回归：81项，68通过、13失败、0跳过；原候选11d032a归档统计同样81项/68通过/13失败，但4项是缺Git历史的环境错误，不能作为同根因证明；已由fix02工作树定向复跑补证。逐项对照及原始失败详见[回归对照](REGRESSION.md)、XML和日志，不宣称全套通过。
- 完整TypeScript检查、Next构建、Python编译及源码diff检查：最终退出码见[验证清单](validation.json)。未改宽配置、未忽略tsc错误；项目原build跳过内部类型检查，因此另外运行完整tsc。
- 未新增前端修改；付款按钮能力通过真实GET详情验证。本补修没有重新做浏览器/真机验证，不将前一轮截图当作本补修页面证据。
- 原始日志（含初次locale失败、每次运行和退出码）见[raw-logs](raw-logs/)。基线归档来自本地git archive，无fetch。

## 限制与交付

本次不宣称第二轮全部其他路径已无问题；完整工资、普通报销/预支资金分工、报表导出和员工自助仍不在本补修范围。没有对所有异常历史组合、多浏览器、多进程压力或生产升级做验证。现有历史差额与缺批准快照记录不自动处置。

仅本地代码、合成验证及追加Git提交；未push/fetch、部署、SSH、读取.deploy或生产凭据、连接生产或改真实数据；库存计价/成本计算/期初库存口径未动，未改模型、未创建自动任务、未派其他会话。完成后停止，等待再次独立验收。

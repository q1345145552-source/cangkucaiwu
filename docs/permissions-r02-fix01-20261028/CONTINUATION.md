# permissions7-r02-fix01-20261028 接续

最新授权：协调独立验收发现第二轮关联备用金报销部分批准后付款409，要求只补本轮后追加提交，不amend候选、不第三轮。先重读本轮协调完整提示（partial-probe路径和A–G要求）及本文件。
边界：仅本地、隔离合成数据、本地Git；不push/fetch/部署/SSH/.deploy/生产凭据/生产连接，不真实数据、不库存计价、不模型、不派其他会话。
起点11d032a41d0d39d770285ce5367ea4d15a2e8e51；分支codex/permissions-round2-20261028，工作树/private/tmp/permissions-round2-20261028，起点干净。
独立原证据/private/tmp/permission-r2-review-800p5mtu只读未覆盖。已读partial_probe.py及JSON，原40中批准30驳回10后无法付款。
本次环境/private/tmp/permissions-r02-fix01-env，全新PG集群localhost65349，round2库。首次initdb因locale失败，LC_ALL=C重试成功；原始日志保留。本轮之前测试服务未重启，前端只复用本地依赖与相同源码进行tsc/build。
修改三文件：reimbursement.py部分批准同样保存备用金批准状态和覆盖全部明细的批准证据；fund_authorization.py新增联动父单+明细快照并付款校验；expense_fund.py批量批准明确同步全部待处理明细，拒绝跨入口重审/旧决定/不一致金额。
金额：原预留40不改；部分批准父单30+备用金批准证据记录原40与批准30，支付记录30；不新增释放10或额外扣款。全驳回仍退原40一次，批量驳回仍保留旧解关联口径；需测试跨入口重复不能重复退。
安全策略：关联明细必须全部有明确决定才完成审批，缺决定整批400；部分批准之后锁定不得另一入口重审为全额；陈旧核验或批准快照409；旧缺新快照待处理不自动批准。
新增测试backend/tests/permission_round2/partial_acceptance.py，目前66记录67请求全通过；原176记录177请求另存本补修目录original-target，未覆盖旧证据。真实JWT路由DB；包含失败支付flush后注入异常，鉴权不替换。
正在跑受影响5文件回归（session56468）和build（50236），tsc已0。待：对比候选11d032a基线归档回归；补必要边界测试/证据；完成报告、日志、停止PG、本地追加提交、完整HEAD交付停止。任何历史失败真实列明不能凑绿。

## 最终交接

最新验收84条记录/85HTTP全符合预期，原176记录/177HTTP全通过（original-target目录）。补充全部批准、部分批准、全部驳回、漏明细、两个入口交叉、批量全批明细同步、陈旧核验/批准（含旧无父子快照）、重复/并发付款、故障回滚、代录本人/员工别名、跨仓/权限及真实创建0.1+0.2精度场景。批准断言额外核对父单、备用金原预留40与快照批准30；付款实际仅一次30。
受影响5文件81项68通过13失败，原候选11d032a归档同样结果，逐项REGRESSION.md及XML/logs保留。完整tsc/build/Python编译0。没有修改旧测试，无skip新增。源代码只有3文件，最后差异66增13删。复核金额比较复用现有money精度容差，不改余额/成本口径。
本次新PG65349已停止，shutdown0；无HTTP服务器或外部服务遗留。本轮证据报告REPORT.md、validation.json、COMMANDS.md。当前准备追加本地Git提交；完整HEAD以最终回复或Git为准。提交后停止等独立验收，不第三轮、不发送其他会话、不push/fetch。

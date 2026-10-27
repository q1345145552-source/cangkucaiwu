# permissions7-r02-fix02-20261028

当前任务是第二轮补修证据复核，先重读协调fix02完整提示，不沿用fix01状态。只本地证据/合成验证/提交；不push/fetch/部署/SSH/.deploy/生产/真实数据，不库存计价、不模型、不派会话。起点422ee2b09b38059215737f4f839f2d4ebc670df1，主工作树permissions-round2-20261028/原codex分支干净。没有业务修改。
问题：fix01归档基线4个git show测试128，不等价当前源码断言失败。已建3个独立detached工作树/private/tmp/permissions-fix02-{bc903a5,11d032a,422ee2b}，均可只读访问本地历史，不fetch。全新PG/private/tmp/permissions-fix02-env，localhost65359，合成round2库。
已完成三个版本各6项定向测试：指定4项+config源码恒等+legacy余额。全部6失败，全部真正走到AssertionError，没有git128或收集错误。新日志在env/logs/{sha}.{log,xml,exit,-command.json}。原失败日志保留。
52项原记录：core-baseline.xml43+reimbursement-baseline.xml5，fund-baseline仅log4。48项有XML中46项失败消息完全相同，另routeinventory三条extra仅排序不同、config源码字典显示条目随机；已新跑config。fund4已新跑。5个源码恒等测试应单独审查，不能仅同名结论。特别fundcontrols/receipts原bc是全文比较，第二轮变为排除review的AST，新增get/list报销can_fund_pay与pay作用域是授权变化，属于历史差异叠加本轮变更，非完全相同旧错。
待：完成AST/精确diff审查与52项逐项表；纠正原REPORT/REGRESSION/validation过度结论（原rawlogs不覆盖）；停PG；只证据/必要采集脚本追加本地提交；完整HEAD交付停止。无业务改动不重跑tsc/build。不能把first断言失败等同后面所有源码断言都已验证。

## 最终交接

证据及报告更正完成。三个版本各6项共18项实际失败断言，均exit1，git历史可用；补齐指定4项并扩查config/缺XML余额。原52项47非源码同根因实际断言，5源码检查分段说明历史与授权增量，不能笼统说全部历史错误。SOURCE-REVIEW.md逐项列旧参照函数、本轮变化及保留262真实请求证据；failure-audit.json保留原始消息/堆栈/证据路径。旧原始日志未改，旧报告及JSON明确更正；两个历史报告生成器加过期停止提示，防止再生成错误结论，不涉及pytest断言。
无业务/前端/模型/旧测试修改；不重跑tsc/build。新数据库65359已停止，shutdown0。detached worktrees保留，HEAD分别bc903a5/11d032a/422ee2b，用于只读复核。当前等待本地追加提交；提交后停止等独立验收，不第三轮。

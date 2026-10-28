# 第六轮：三档动作权限本地交付

实施依据为本目录 PROMPT.txt（permissions7-r06-20261028）及接续指令 permissions7-r06-resume01-20261028。本报告不替代独立验收，不表示线上已部署。不返回旧第二轮交付、不开始第七轮。

工作树 `/private/tmp/permissions-round6-20261028`；分支 `codex/permissions-round6-20261028`；父提交/业务基线 `a28e128614beec612cd2e639231044b415f97b97`。本轮提交信息见 HANDOFF.md。桌面原工作树保持原状，没有混入其供应商/员工/交办任务改动。适用祖先和仓库内未发现 AGENTS.md。

实现了真实路由动作目录、独立查看/操作/审批授权、角色上限、版本化兼容转换与审计，以及前端三列编辑和主要页面动作入口。现有仓库、本人、字段和单据状态守卫继续独立执行，动作授权不能覆盖它们。允许路径与拒绝路径均用真实 JWT、应用路由和独立 PostgreSQL 验证。仍有未直接实测路由及既有失败，详见下文，不能宣称全系统权限穷尽验证。

|范围|修改位置与行为|实测证据|
|---|---|---|
|A 动作与后端|core/action_catalog.json 明确434路由，action_access 在真实 get_current_user 校验，main 未登记路由拒绝；POST预览仍是查看；付款是操作；核验/批准按请求 action 拆分；停用入口不授予|registration-check、matrix-final、extended-02、disabled-category|
|B 兼容与迁移|extra_permissions 使用 @wf-actions:1 及 module:tier；新用户最小授权；旧全勾受角色上限；转换全批加锁、验证、审计；版本化撤权不被旧启动补权恢复|extended-02、migration-cli-*；MIGRATION-AND-ROLLBACK.md|
|C 管理界面|ActionPermissionsEditor三列及角色禁用原因；ActionGate/同源能力控制；无查看时使用仅必要选择项的办理页；调用原接口，无通用写入旁路|frontend-gates/manual-gates、browser-final 六场景|
|D 状态与隔离|财务核算/核验，管理员批准，合法独立财务执行；状态、本人/代录、跨仓、父子归属、重复并发沿用前轮守卫。权限授予/撤回保留前后值、原因及来源|final-round3 两组、partial-final、round4-media-final、extended-02|
|E 字段/缓存|第五轮服务端敏感字段投影保留；共享账户选择器无 accounts:view 时只返回标识、名称、币种、状态，不返回余额/银行字段；旧JWT以数据库当前授权校验；账号切换重新取菜单，丢弃跨账号/跨仓迟到响应|第五轮两组、extended-02、browser-final|

详细动作级角色、方法路径、页面入口与证据见 ACTION-MATRIX.md/action-coverage.json；输入字段、前置状态源码、服务位置、审批交接、自批限制、字段和审计要求见 action_catalog.json。这里的角色是上限，具体动作可能继续被原状态或对象守卫拒绝。主管与财务平行，管理员批准资金；采购原有职责配置、例外和版本保护保留，采购订单生效不等于资金批准。

## 实际验证

|验证|结果|原始证据|
|---|---|---|
|八种三档组合与管理写入|66 请求，失败0，exit0|matrix-final / raw-logs/matrix-final.*|
|迁移、撤权、跨仓、非法值、事务/并发等扩展|74 请求，失败0，exit0|extended-02|
|第三轮资金目标，旧格式及v1|每组277实际请求，失败0，exit0|final-round3-legacy/versioned|
|第二轮部分批准金额链|87实际请求，失败0，exit0|partial-final|
|第四轮自助/职责及媒体|275基础+320媒体请求，失败0，exit0|round4-media-final|
|第五轮基础/附件字节/写回包/日志导出|旧格式和v1各311条，共622条，失败0，8组exit0|final-r5-*；真实XLSX/PDF/附件字节证据|
|已关闭供应商全局分类写入|三角色真实me+写入共6请求，写入403且业务无变化|disabled-category|
|实际浏览器|管理员三列保存、主管合法编辑后撤权旧弹窗拒绝、多页刷新、财务只看无核算/付款、仅操作核薪、仅审批他人请假、同页切账号；6场景通过|browser-final，截图及请求|
|完整TypeScript检查|exit0|raw-logs/tsc-delivery.*|
|完整Next构建|exit0|raw-logs/build-delivery.*|
|历史283项回归|275通过、8失败、0skip，与精确基线失败集合一致；exit1|pytest-prior-current-delivery及baseline|
|相关239项回归|234通过、5失败、0skip，与精确基线失败集合一致；exit1|pytest-related-current-final及baseline|
|读取39项回归|32通过、7失败、0skip，与精确基线失败集合一致；exit1|pytest-reads-current-delivery及baseline|

未把第一轮漏洞复现200当作应保留行为。旧主管垫款测试改用独立合成财务录入，受益人、金额、批准人和原资金断言保留；原始72失败阶段也完整保存。旧空权限补权测试调整为有明确旧授权的合成用户，空账号继续为空。其他文案/真实route上下文/服务端字段422适配逐项记于 REGRESSION.md；没有删除有效金额断言、skip、扩大any或放宽配置。Next原配置自带构建时跳类型检查，因此另行运行完整tsc，不以build成功冒充类型检查。

历史成本/报表展示失败、旧源码快照/菜单断言、日志字段/仓库预期均保留，完整基线及最终错误文本见 regression-comparison.json。历史三条依赖费用记录的断言仍不能冒称抵达；不改库存计价、费用口径来换取全绿。第五轮协调独立314请求中另3条不在本地脚本，本轮明确重跑本地311×2，不声称重跑了独立314。

## 迁移、边界与剩余事项

没有SQL结构迁移或ORM模型改动；授权格式转换在独立合成库验证。精确转换表、CLI默认dry-run、显式apply、历史未知值及安全回退见 MIGRATION-AND-ROLLBACK.md。不能直接回滚到不识别v1的旧后端，不能删除审计或恢复全选。

全部434路由已登记不代表全部直接测试。机械覆盖按真实注册顺序匹配路由，防止静态路径误计为另一个/{id}接口；覆盖数量以 coverage-summary.json 为准。所有无请求证据项逐行列出，不将统一守卫静态覆盖写成业务通过。第五轮仓库内清单为215-46=169缺口，与协调独立167口径差2条，来源差异明确保留；逐条接续见 inherited-read-gaps.json。

真实浏览器只完成上述六场景，未穷尽所有模块弹窗/复杂导入/批量表单、全部移动端组合及跨仓迟到请求实景。最小选择器覆盖人员、考勤/请假/加班、工资、备用金、报销、应付、付款计划和账户；其他模块可能需输入已知编号，未声称每个复杂办理表单均可用或已验收。供应商物流价格旧dict接口补充了原有可编辑字段的办理表单合同，未新增业务规则；复杂表单仍需逐场景独立验收。frontend-review-remaining.json 是初始自动映射未识别处理器，含本地输入/关闭/本人操作及后续已受父级能力控制项，不能把它们全部当漏洞或全部当已验证。

F01-F19/T01-T13与修复位置、前置提交、本轮证据及未测项见 FINDINGS-MAP.md。后续优先独立审查角色上限与动作分类、未直接实测读取/附件路由、复杂最小办理表单、历史成本断言和缓存组合。此处只列出建议，不自动实施下一轮。

全程仅本地代码、合成数据及Git提交；未push/fetch、未部署、未SSH、未读取.deploy或生产凭据、未连接生产、未修改真实数据。未改模型、未派发其他会话、未创建自动任务。库存计价、成本计算和真实期初口径未修改；前端库存页仅动作入口控制，cost_identity仅授权桥接。边界核对见 boundary-check.json。独立本地服务完成后停止，证据与工作树保留供用户安排独立验收。

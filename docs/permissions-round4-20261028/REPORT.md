# 独立验收补充状态

原第四轮在独立验收中发现+json附件归属旁路，不能作为最终验收通过。修复与最新验证见 [第四轮fix01报告](../permissions-r04-fix01-20261028/REPORT.md)，等待独立复验。以下为原交付记录，未篡改原始证据。

# 第四轮权限修复交付

标记 permissions7-r04-resume01-20261028。本轮为第四轮：正式记账、规则权限、员工自助与本人审批。第二轮旧交付不代表本轮交付。

工作树 `/private/tmp/permissions-round4-20261028`，分支 `codex/permissions-round4-20261028`，基线 `1602e8133ebea004eb2d17d20e41187bab46ccd0`。第三轮前置业务e4d7e05、交接e51b636、补修1602e81。实际本轮提交清单见COMMIT-HANDOFF.md。桌面原工作树的未提交任务未动，没有清理其他工作树。

## 结果与范围

本轮后端改动通过真实JWT、应用路由和独立PostgreSQL合成数据验证。最终目标275条记录（包含并发复合记录），失败0；完整数据库前后差异见requests.json，拒绝时比较业务表，普通安全日志单列；补卡申请history行按业务数据比较。角色含管理员、主管、财务A/B、员工、全扩展权限、无管理菜单、禁用、外仓和考勤别名。不是全系统全绿，失败和未测项目见下文。

|组|原问题 → 修改位置/接口|目标行为|证据|
|---|---|---|---|
|A|主管正式收支/到账导入/匹配等写旁路 → core/round4_access.py、route_access.py、reconciliation.py|所有注册写方法叠加角色上限，仅获菜单授权财务/仓管，继续约束仓库和状态；主管只保留申请|A-deny、A-supervisor、A-finance、A-repeated、A-concurrent、A-rollback等requests记录|
|A|通用支出改自动来源费用 → 保留原payroll_expense等服务守卫|原关联支出不可直接改删；未放开批准、付款或关闭的撤销入口|A-approved-source-edit/delete返回原400；前轮277/265请求复跑|
|B|主管/财务规则修改 → round4_access动作上限、专用schema；员工敏感字段 → employees.py|规则只授权仓管；薪资/扣款/银行/账号字段非管理员即使null也拒绝；普通现场备注仍可改；混合外仓整批拒绝|B-rule/B-field/B-onsite-edit/B-template-batch-mixed；采购职责前轮回归|
|B|审计对象/仓库与敏感字段 → round4_access的事务before_flush追踪|只追踪本请求实际ORM对象，记录原值摘要/变更字段，规则必要值；银行账号不明文；继承原资金审计|B-admin-sensitive、B-admin-rule及数据库history断言|
|C|本人及别名审批请假、代录、补卡、加班 → independent_employee及对应处理器|主管/管理员均不得批本人；财务不得现场批准；批准加锁、合法状态与原已批准请假纠正驳回保持；本人加班事实确认保留|C-self、C-alias、C-admin-self、C-independent、C-repeat；管理员本人3项403，独立主管审批200|
|D|财务/主管自助被管理菜单误封 → employee_access、personal_finance、payroll_self_identity、auth|有效正式绑定决定本人；管理菜单与本人能力分开；禁用/离职/冲突/伪造头和查询拒绝；不按电话姓名猜身份|D-clock/leave/self/foreign/control/resigned/conflicting；无菜单主管6和财务11成功|
|D|本人资金申请与附件 → reimbursement、expense_fund、employee_advance、secure_uploads|显式self入口固定本人；拒绝系统控制/外人附件；公司资金来源只显示ID名称币种；申请不批准不付款|D-finance-no-menu-advance、D-own-fund、D-other-fund、D-nested-control、D-foreign-receipt|
|D|补卡没有独立本人申请通路 → clock-in/makeup-requests三个接口及MakeupRequests.tsx|pending申请不生成考勤，独立主管/管理员批准后调用原补卡；本人/财务批准403，重复409|D-self-makeup-request、C-independent-makeup、C-repeat-makeup|
|E|页面写按钮/敏感字段与后端不一致 → useBusinessAction、7个管理页、DashboardLayout、my-requests|主管记账/规则不可操作，财务记账保留；员工事实编辑保留，银行/模板仅管理员；身份/仓库切换重建内容，旧管理员缓存重取当前身份|browser-results-final.json、browser-positive.json及手机截图|

具体方法、路径、输入字段schema、源位置、嵌套守卫、状态相关代码、角色、范围、交接、自批与审计逐动作列于ACTION-MATRIX.md/action-matrix.json；实际注册237个方法/路径，其中48个有本轮直接目标请求映射，189个未直接请求，coverage.json完整列出。前轮复跑另列，不能把枚举237条说成全部实测。静态截取条件不等于证明全部服务分支安全。

## 验证及已有失败

|验证|实际结果|日志及退出码|
|---|---|---|
|本轮最终目标|275记录，0失败|target-final-03.log / exit 0|
|第三轮目标复跑|272记录、277 HTTP，0失败|round3-final.log / exit 0；round3-final/status.json|
|第二轮目标复跑|177记录、178 HTTP，0失败|round2-final.log / exit 0|
|第二轮补充复跑|86记录、87 HTTP，0失败|partial-final.log / exit 0；合计265 HTTP|
|前轮相关回归|283项：275通过、8失败、0跳过|regression-prior-01.log/xml / exit 1|
|本轮相关回归（含incoming_operations）|239项：234通过、5失败、0跳过|regression-related-01.log/xml / exit 1|
|1602基线相关回归|233项：216通过、17失败、0跳过|regression-related-baseline.log/xml / exit 1；追加6项incoming未在此基线集|
|浏览器最终角色/页面|39组合通过、0错误（含18本人/旧管理员缓存组合）|browser-final.log / exit 0|
|浏览器正向补充|管理员/财务记账可用、主管不可用；主管/财务本人报销提交200，共5检查|browser-positive.log / exit 0|
|完整独立TypeScript|通过|tsc-final-02.log / exit 0|
|完整Next构建|通过|build-final-04.log / exit 0|

全部本轮原始日志在raw-logs，清单和SHA256见evidence-manifest.json。项目原有Next忽略类型/ESLint构建配置未改；不能用build通过替代独立tsc。没有添加skip/xfail，没有放宽配置或为了通过改计算。初次最终build因共享临时依赖目录缺失失败；从本机npm内容缓存按锁文件恢复107个包到本轮独立目录，非当前平台optional包未提取，无联网安装；后续完整构建与tsc成功。失败尝试日志保留。

八项金额/显示失败与第三轮逐项对照保存在failure-comparison.json，不能仅据同名测试断定等价：

- 工资资金流水备注未含员工工资（金额断言仍执行）。
- 垫款工资7000未生成预期费用：成本750而非7750。
- 公司报销成本7750而非2750，含既有备用金5000。
- 垫款报销成本5750而非2750，归还后7750，仍影响成本。
- 报销小数场景成本5750.3而非750.3。
- 公司来源预支成本集合多出原备用金10000（两项而非一项）。
- 垫款全额归还未保持成本/非成本标记预期。
- CNY垫款归还仍改变成本预期。

第三轮缺少垫款工资费用对象后3条依赖断言仍未验证，原ASSERTION-MAP及原报告保持不动；本轮没有宣称补齐、没有改金额政策。

另外5失败在1602基线也失败，原断言未删除：test_batch_makeup源码恒等、test_employee_limit_routes源码恒等、test_full_day_leave源码恒等、test_makeup_batches源码恒等及test_round12_attendance_identity旧菜单数量34与实际37。前四本轮确有授权范围内代码变化，不能笼统说“与本轮完全无关”；当前/基线失败全文均保留。旧有效金额/范围断言保持，测试前置改为真实新鉴权链：姓名电话不能代替正式绑定、财务自助允许但伪造查询403、工资走核算确认发放、主管不能创建登录账号、选仓头403单独验证后以合法头验证原业务。没有把越权200留作业务要求。

证据缺口：初次related日志被采集器同名覆盖；当时XML保留为regression-related-initial.xml，原日志无法补造。采集器已改递增文件名；最终及基线log/XML/exit完整。target-final-02额外管理员夹具ID与已有请假冲突，失败日志保留；修正合成夹具ID后target-final-03成功。

## 未完成与待独立验收

无独立审批人时仍安全拒绝，未指定替代审批人或新财务门槛。完整报表、全量导出、同仓他人证件附件的管理菜单读取、完整三档权限架构不属本轮；新增本人附件路径已限制并实测，不等于F18整体关闭。原采购职责版本、额外批准保护、资金撤销关闭、二/三轮工资及付款职责保留。

页面验证只涵盖记录的角色/页面/手机视口与旧缓存场景，并非所有浏览器、全部批量表单及完整五至七轮验收。补卡新申请并发批准未单独做双并发测试，代码行锁及重复请求已验证；正式入账并发/异常回滚已有目标证据。完整字段级读取泄露审计留后轮。my-requests列表目前显示既有状态代码，未做完整多语言体验改造。

兼容与回退详见COMPATIBILITY.md；没有模型或结构迁移，历史待处理资金没有自动批准或重新执行。新增makeup_request记录须按业务申请保留，不能当普通日志清理。

只本地修改、合成数据库验证及本地Git提交。未push/fetch、未部署、未SSH、未读取.deploy或生产凭据、未连接生产（包括只读），未修改真实数据。库存计价、成本计算公式、期初库存及模型未改。未派其他会话、未创建自动任务。本轮交付后停止，等待独立验收，不进入第五轮。

补充：源码暂存差异检查退出0；包含原始浏览器文本的全量检查退出2，原因是原样innerText中的行尾制表符/空白，保留原始证据未改写，不涉及源码空白错误。

# 第一轮问题与本轮关系

以下“证据”均指本地合成环境，不代表线上部署状态。每组内精确请求、状态码和数据库差异见 requests.json；动作级未测路由见 action-coverage.json。历史问题已修不等于相关模块所有组合穷尽。

|第一轮|已实现位置/前置提交|本轮证据与剩余范围|
|---|---|---|
|F01 账号管理|11d032a；users、round2_access；本轮 action_access 上限和严格授权写入|matrix-final、extended-02；禁用/跨仓/自提权拒绝|
|F02 离职间接停用|11d032a；employees、round2_access|round2-versioned；本轮员工操作回包延续第五轮过滤|
|F03 账户管理|11d032a；payment_accounts|round2-versioned、extended-02；共享账户选择器本轮进一步剔除余额与银行字段|
|F04 备用金分离|11d032a、422ee2b；fund_authorization|final-round3 两组、partial-final；核验 operate 与批准 approve 分开|
|F05 工资分工|e4d7e05；financial_authorization、payroll|final-round3 两组、仅操作浏览器核薪；无全工资模块穷尽声明|
|F06 工资/报表读范围|bf15554、4bfdb4b、a28e128；round5_access|第五轮两组 622 请求；明确剩余读取路由|
|F07 报销自批自付|e4d7e05；financial_authorization|final-round3 两组，partial-final；原请求与金额断言保留|
|F08 父子单归属|11d032a；reimbursement review|round2-versioned、final-round3；同仓其他父单/外仓/混批拒绝|
|F09 请假自批/代录|7134907；attendance、employee_access|round4-media-final、仅审批浏览器；本人身份仍由实体绑定核对|
|F10 通用规则旁路|11d032a、7134907；settings/配置守卫|round2-versioned、round4-media-final、目录；采购专用版本/例外保护保留|
|F11 工资字段写入|7134907；employees/模板|related 回归、第五轮写回包；未改工资计算|
|F12 本人预支|e4d7e05；financial_authorization|final-round3、prior 回归；不恢复旧自动批准|
|F13 直接运营记账|7134907；income_expense|round4-media-final、related 回归；主管资金角色上限|
|F14 员工自助|7134907、43eaec0；employee_access|round4-media-final 275 基础及 320 媒体请求；正式绑定不变|
|F15 应付/计划执行|e4d7e05；financial_authorization|final-round3；动作目录独立操作授权，批准条件仍必须成立|
|F16 前后端不一致|本轮 ActionGate、能力标志、三档编辑、缓存刷新|browser-02 六场景；其余按钮静态映射不等于实际页面逐项验证|
|F17 菜单不能拆三档|本轮 action_catalog/action_access/access API|matrix-final 八组合、extended-02、browser-02；未知新路由拒绝|
|F18 证件附件泄露|bf15554；secure_uploads、round5_access|第五轮两组真实附件 120 请求及 round4 媒体；不能按菜单直接读他人证件|
|F19 审计字段/仓库|11d032a；data_history；本轮 action_permission_migration/users|extended-02 来源、仓库、原因、失败回滚；第五轮日志/XLSX字段保护|

|第一轮测试编号|本轮证据组|
|---|---|
|T01 账号|matrix-final、extended-02、round2-versioned|
|T02 账户|round2-versioned、extended-02|
|T03 备用金|round2-versioned、final-round3-versioned、partial-final|
|T04 工资|final-round3 两组、browser-02、prior 回归|
|T05 工资/报表读取|final-r5 两组、读取缺口清单|
|T06 付款与本人限制|final-round3 两组、partial-final|
|T07 请假/加班/预支本人|round4-media-final、final-round3、matrix-final|
|T08 规则|round2-versioned、round4-media-final、采购回归|
|T09 自助|round4-media-final 基础和媒体|
|T10 三档|matrix-final 66、extended-02 74、browser-02 六场景|
|T11 替换 ID/跨仓|前轮目标、extended-02、第五轮两组|
|T12 批量/附件/导出|final-round3、第五轮两组、round4-media-final；未测项保留|
|T13 停用撤销|final-round3、prior 回归；目录 disabled 始终委托原无条件拒绝|

后续审查优先：动作目录各状态/字段语义抽查、未直接实测读取路由、复杂最小办理表单及全部导入/批量页面、跨仓迟到响应的真实浏览器场景、已知成本/展示断言。这里只交付清单，不开展下一轮、不改变财务政策。

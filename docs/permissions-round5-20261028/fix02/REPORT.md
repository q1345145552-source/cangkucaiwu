# 第五轮 fix02：日志与导出的薪资字段权限

Marker：permissions7-r05-fix02-20261028。工作树/private/tmp/permissions-round5-20261028，分支codex/permissions-round5-20261028，补修基线4bfdb4bb48660b90d89e561e90eca96f300c7692。本次本地补修待独立复验，不进入第六轮；完整新增HEAD见最终回复/Git。fix01普通员工保存响应的修复保留。

## 根因、修改与职责

history_modules按模块菜单筛选，但history_values未结合工资字段权限。因此只有employees+modification_logs的财务仍可从employee历史及XLSX读base_salary等值。before/requests.json用真实JWT、独立localhost PG再次复现；50次请求中有174条失败断言（不是174次请求），包含919191/929292及嵌套薪资、银行和户名哨兵泄漏。

业务代码仅改两文件：

|位置/接口|目标与实现|
|---|---|
|core/round5_access.py::history_values|复用PAY_FIELDS与financial_reader(user,'payroll')；无工资资格时过滤工资字段及工资/扣款模板容器。员工、工资、模板、员工扣款实际模块上下文中的amount/rate/倍数也按薪资规则处理，不把其他业务amount全部隐藏|
|同一helper的结构递归|处理before_data/after_data内字典、数组、rule_values、嵌套模板、序列化JSON及field/key→old/new/value结构，防止换包装恢复敏感值；不可解析的结构化文本安全隐藏。原顶层非字典历史继续沿用隐藏，不扩大未知历史格式权限|
|history.py GET /history 与 GET /history/export|将每条真实记录的module传给同一字段策略；SQL模块菜单、仓库、分页/汇总条件保持。导出基于同一过滤结果，不对原数据库记录抹值|
|银行/证件/凭证|沿用日志比业务详情更严格的敏感值隐藏，并补齐银行名、户名、银行容器、收据列表/路径、照片缩略图等同类字段。管理员仍保留原必要薪资和仓库范围，日志不成为凭证直链；有工资权限财务仅在同时获对象模块和日志权限时读取必要工资字段|
|主管与其他日志入口|主管原现场白名单和changed_fields名称保留。/history/operators仅对象模块范围内操作人元信息；/settings/logs不输出detail正文。本次新增实际请求验证两入口，无扩权。未给缺少日志菜单账号开放日志|

实际别名employee、employees按一致字段政策；salary_templates/deduction_templates的rule_values用真实模块上下文判断。其余历史模块映射未扩大。工资审批、资金执行、规则、计价和模型均未改变。

## 新增固定回归

history_fields.py：最终final-02共54次真实请求，0失败，15个真实XLSX逐个解析全部工作表/单元格及ZIP内文件/元信息。无工资财务在员工读取、正常事实编辑、历史列表及同一导出URL一致看不到薪资；授予payroll后必要字段可读，再撤权后再次隐藏。每个账号全过程复用同一JWT，证据只记录token摘要，不靠换token刷新权限。

覆盖：employees+modification_logs；额外仅有薪资/扣款模板菜单但无payroll；合法授权与撤权；主管、管理员、无日志菜单、劳工、禁用、外仓header和query。使用非空薪资、工资模板金额、银行账号/银行名/户名、身份证、社保、护照和付款凭证哨兵；嵌套数组、JSON文本、field/key记录均检查。正常编辑仍200且不改变敏感原值；所有读取和拒绝检查业务表无变化。每次验证初始原始历史全文/摘要不变，makeup_request业务记录保留且不返回给日志页面。

已有授权报销历史普通amount 888888仍可读并实际导出，不把非薪资财务日志一律403，也不改金额口径。

## 复跑结果及限制

|验证|结果与位置|
|---|---|
|新增日志字段、撤权、导出|54请求0失败，final-02/requests.json；15个XLSX及文件摘要|
|fix01员工写响应|66请求0失败，writes/，包括JSON变体、上传及数据库不变|
|第五轮原目标|131请求0失败，target/|
|第五轮附件|60请求0失败，attachments/；先运行已有browser_setup恢复目标所需合成角色|
|第四轮关键保护|275+320请求通过，../prior/fix02-round4；保留标准JSON/+json/表单附件关联及本人限制|
|读取相关回归|29项28通过1失败0skip，regression-reads-03.xml；仍为管理员资金执行旧200预期实际403，后续金额断言未到达。与上次实际全文并列，不修成本政策|
|日志旧回归及真实基线|test_modification_log_permissions.py在独立detached 4bfdb4b工作树与当前各跑10项，均4通过6失败0skip。实际断言逐项对照见failure-comparison.json，不仅比较名字。旧测试期待仅日志菜单能读其他模块、非法仓库头回退及旧拒绝文案，与既有收口不一致；本次未删改它们，不计作通过|
|编译/格式|最终退出0，validation.json和原日志|
|前端|无前端/依赖变化；248源码/配置与既有构建副本重新逐字节核对。复用前候选完整tsc/build退出0和页面验证的未改范围，本次未重跑浏览器/构建|

第三轮8项成本/显示失败、第四轮5项源码/菜单失败及3条依赖未测继续保留，本次不重复无关整组；第二/三轮完整目标沿用fix01已保存265/277请求结果，不冒称本次新跑。新增纳入的6项日志旧失败另列，不用原“8+5+1”掩盖它们。

原覆盖清单169条未直接请求保留作基线。本次补测其中/history/operators和/settings/logs两条，见coverage-addendum.json；其余167条仍未直接请求，且已测路由也不代表所有角色/格式组合全覆盖。不改写旧覆盖证据冒称原来已测。没有外部AI、生产历史清理或全部历史格式扫描；未知自由文本中的敏感值需要独立离线审阅，本次按已识别字段及结构控制，不能保证任意随意命名的历史文字内容均可自动识别。

## 失败尝试与证据

before保留修复前泄漏；after-01原50目标通过。扩展final尝试选了recharge作为非薪资金额正向，但现有history_modules白名单没有recharge，返回空列表，非空导出断言失败；日志、已返回请求和实际空文件保留，尚未完成的请求无最终JSON，不能称完整最终证据。未为测试扩大模块权限，改用既有映射reimbursement后final-02通过。没有覆盖旧证据。

原fix01与第五轮已有JSON缺口仍按原报告保留。本次新增fixed regression为真实应用路由、JWT和合成PG；旧pytest采用其原SQLite夹具，仅作历史回归对照，不冒充本次PG目标。

## 兼容与边界

无迁移，无审计记录清理、批量改写或自动权限变更。原始日志字段仍完整存储，只投影响应副本；离线历史审阅另行授权。回退会重新开放无工资财务的日志泄漏，不是安全恢复方案。

只本地代码、合成验证和commit；未push/fetch、部署、SSH、读取.deploy/生产凭据、连接生产或修改真实数据。模型、库存计价、成本及期初口径未动；无自动任务、无其他会话派工。停止本轮隔离PG后提交，等待独立复验。

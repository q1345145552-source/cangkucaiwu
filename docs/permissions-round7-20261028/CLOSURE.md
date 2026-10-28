# F01–F19 与 T01–T13 逐项闭环

“已修原复现”仅表示原问题入口和已列分支有实现/请求证据，不表示全系统所有角色、状态和字段已穷尽。原第一轮静态位置、旧角色/字段/状态及172请求仍在 `../permissions-audit-round1-20261028/FINDINGS.md`、`action-matrix.json`、`requests.json`，不覆盖为修复前正确。当前精确路由、方法、输入字段、状态条件、关联服务位置、前端入口见 `final-action-matrix.json`；每条实际请求见 `final-request-index.jsonl.gz`，可按下面动作/证据编号检索。

|问题|原问题→最终实现|当前证据与判定|明确范围|
|---|---|---|---|
|F01|主管/财务建删他人账号→users及round2_access管理员角色上限、授权仓库、旧权限不能越级|accounts-round2-v1-01 `A-*`；管理目录、迁移及真实JWT测试。已修原复现|不把本人改密禁掉；新角色体系未新增|
|F02|离职停账号且自动核薪→employees离职事实与账号、工资交接分开|`test_round3_permissions.test_void_actions`、现场目标；Payroll/User快照。已修原复现|离职核算必须由合法工资动作办理；未改工资公式|
|F03|主管/财务改账户配置→payment_accounts管理员写、财务使用账户另判权|accounts `B-*`、管理三角色页面；账户性质800与400+400回归。已修原复现|主管最小资金来源选择不包含余额/银行等完整财务字段|
|F04|备用金开户拨付审核设置及自批→fund_authorization独立核验/批准/执行|accounts `C-*`、partial、fund_disbursement、chain资金证据。已修原复现|历史无批准拒绝，成本口径冲突另列，不把费用账通过冒称成本断言通过|
|F05|主管核薪发薪而财务缺权→payroll/financial_authorization真实工资交接|chain `A-*`、工资资金回归、仅操作核薪浏览器。已修原复现|不改变计算公式；批量、本人、已付、并发及回滚分支按索引列示|
|F06|主管读导出他人工资、成本资金→round5_access服务端职责/字段投影|reads-acceptance两种授权、history_fields、selectors-10工资候选拒绝。已修原复现|主管禁财务明细是已确认原则；不再列为待确认|
|F07|本人报销审核付款、主管付款→reimbursement与financial_authorization独立受益人约束|chain `B-*`、partial、reimbursement_payments。已修原复现|代录、本人、30/40、重复、回滚有专门证据；成本失败仍保留|
|F08|父单可审核其他单明细→全批父子、仓库、重复、状态前置校验|accounts `E-*`、报销目标及选择器跨父单拒绝。已修原复现|非法整批业务表/余额不变；不只检查状态码|
|F09|请假自批、代录本人已通过→onsite审批本人身份统一校验|onsite-round4-v1-01及媒体、请假/补卡/加班测试；审批-only手机。已修原复现|未知替代审批人未自动指定|
|F10|通用key/专用入口改规则→config_access白名单及管理员写，采购专用保护保留|accounts `D-*`、采购职责回归、配置测试。已修原复现|规则现值和默认金额不改，不恢复旧入口|
|F11|主管改工资字段/模板→员工字段白名单与模板管理员规则|现场目标、工资/扣款模板矩阵、写回包敏感哨兵。已修原复现|未因页面可编辑现场字段而开放银行/薪资|
|F12|本人/代录预支创建即出款→pending→核验→批准→独立执行；主管强制本人模式|remaining-bypasses-01 17请求；advance资金/回滚测试；chain新增合法录入适配。已修原复现及本轮发现旁路|未绑定主管不能代录；管理授权不足不阻断正式绑定的本人申请|
|F13|主管直接正式记账出款→income_expense/round4_cashier角色上限|onsite目标、money_record_scope、钱包与停用经营入口测试。已修原复现|财务合法记账保留；不自行新增财务门槛|
|F14|财务员工自助不可用→employee_access正式绑定、本人/仓库守卫|onsite及self相关真实路由、绑定停用/同名错绑负向。已修原复现|完整所有原生员工页面组合未穷尽，见浏览器清单|
|F15|单笔/计划付款角色不一致→共享execute_bill及逐单批准证据|chain应付/计划、supplier工作流、wallet真实计划回归。已修原复现|旧无prepare计划拒绝；跨仓/混币种/非法项整批拒绝|
|F16|页面按钮与接口不同→action catalogue能力、原生入口及最小办理|browser-final05 18场景，三列授权/切账号/撤权/手机/迟到响应。已修所测入口，页面覆盖部分|不宣称全部434动作均逐按钮浏览器实测|
|F17|菜单读写审批捆绑→版本化view/operate/approve∩角色∩范围|tiers-acceptance-01、migration-extended-01、selectors-10八组合。已修权限模型及所测组合|只有操作也不能读完整列表；管理员无权越仓|
|F18|同仓菜单授权可取他人证件→引用关系+用途/本人/字段守卫|reads-attachment两种授权、现场媒体、browser附件真实PNG/旧cookie撤权。已修原复现|不是仅判断200或隐藏图片；未验证所有真实浏览器缓存实现|
|F19|无头审计仓库为空、缺字段历史→账户对象授权仓库及事务字段审计|accounts `B-authorized-secondary-no-header-audit`、回滚及权限迁移审计。已修原账户复现|不宣称每个历史模块统一具备同等审计合同|

本轮新增的采购关联账单字段旁路由 `supplier_payable_read.can_read_bills` 补角色上限；`remaining-bypasses-01` 对主管历史全权限/版本权限负向和管理员/财务正向使用财务敏感哨兵。

## 验收编号对照

|编号|最终目标与关联问题|实际证据|判定及未测|
|---|---|---|---|
|T01|账号直接/间接管理；F01/F02|accounts A、现场离职及User/Payroll快照|原复现已修；本人与管理员范围保留|
|T02|账户配置；F03/F19|accounts B、账户性质回归、页面|原复现已修；无头对象审计及跨仓拒绝|
|T03|备用金职责分离；F04|accounts C、partial、fund/chain|权限目标有实测；成本口径断言未通过不掩盖|
|T04|工资交接；F05|chain A、payroll_expense/payroll_cash_advance及金额回归|核算/确认/支付角色已分开；未改公式|
|T05|工资/报表/导出范围；F06|reads、selectors、报表权限矩阵|已按确认职责实现，未穷尽所有导出列组合|
|T06|付款/本人/代录/计划；F07/F12/F15|chain、partial、remaining-bypasses、钱包|单笔/批量实测分支见请求索引；原成本失败另列|
|T07|请假/加班/预支自批；F09|onsite、self测试、chain|本人拦截保留并覆盖代录，不指定新审批人|
|T08|通用/专用/批量规则；F10/F11|accounts D、config、procurement_controls|权限旁路已修，规则金额及库存口径不改|
|T09|主管/财务自助；F14|onsite、正式绑定测试|接口所测链可用，原生页面组合非穷尽|
|T10|查看/操作/审批拆分；F17|tiers66、migration74、selectors52、browser|八组合后端及代表页面有证据，不把代表页当全页通过|
|T11|替换仓库/单据/员工/账户/父子ID；F08|accounts E、headers9、selectors及remaining-bypasses|原漏洞和新增伪造头已修；各路由组合看矩阵|
|T12|批量、旧接口、附件、导出；F06/F08/F18|reads、现场媒体、batch、cookie字节、退出码索引|有专门真实拒绝证据；遗留鉴权替身请求全部排除|
|T13|关闭撤销付款保持拒绝|chain正常路由、assert_disabled、目录七停用入口|未恢复；底层历史夹具不当接口验收|

## 提交归属

F01/F03/F04/F08/F10/F19起始修复第二轮；F05/F07/F12/F15第三轮；F02离职事实及F09/F13/F14/F11第四轮；F06/F18及回包/日志第五轮；F16/F17三档第六轮；本轮新增字段/实体选择、复杂办理、仓库头、主管预支和采购关联明细收口及集成证据。完整父子提交链见 `COMMIT-CHAIN.txt`；本轮最终提交须以交付时Git HEAD为准，不能使用第二轮旧HEAD替代。

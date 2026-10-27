# 第一轮权限问题清单

基线 854e389；仅本地合成数据。建议均未实施。每项“当前行为复现成功”不等于目标权限验收通过。

## F01 主管可创建删除财务，财务可创建劳工

分类：权限过宽/历史兼容。证据等级：本地接口实际验证；代码静态确认。

代码：backend/app/api/v1/users.py:115；backend/app/api/v1/users.py:372；backend/app/core/permissions.py:28。

测试/复现索引：T01-01、T01-02、T01-03、T01-04、T01-05。请求、角色、状态、响应、数据库前后差异见 requests.json；UI编号见 browser-results.json。

现状：全扩展权限主管创建财务200并可赋全权限，删除新财务200；财务新建劳工200。主管编辑既有账号403，因此不能据此说所有账号动作都放开。

影响：违反P1；主管可取得自己设定密码的财务账号，间接使用财务身份；财务也可管理下级账号。

建议修复位置与方向：账号新建/删除统一禁止主管和财务管理他人；旧全勾权限不能覆盖角色禁止；连同员工绑定/离职间接入口审查。

## F02 离职接口能间接停用他人账号并触发工资核算

分类：权限过宽/财务缺权/关联旁路。证据等级：本地接口实际验证；代码静态确认。

代码：backend/app/api/v1/employees.py:546；backend/app/api/v1/payroll.py:73；backend/app/api/v1/payroll.py:1093。

测试/复现索引：T01B-01、T01B-02。请求、角色、状态、响应、数据库前后差异见 requests.json；UI编号见 browser-results.json。

现状：主管给财务B办离职200，users.is_active=false且生成工资；财务给普通员工办离职200并停用账号。

影响：P1账号停用限制可由人事入口绕过；工资直接入口与内部计算服务角色策略不一致。这里生成工资不等于已发款。

建议修复位置与方向：将离职事实、账号启停、工资核算分清交接；在共享服务保证调用者不能借间接入口扩大动作权限。

## F03 主管改账户期初，主管和财务可启停账户

分类：权限过宽/规则。证据等级：本地接口实际验证；代码静态确认。

代码：backend/app/api/v1/payment_accounts.py:130；backend/app/api/v1/payment_accounts.py:172；backend/app/api/v1/payment_accounts.py:41。

测试/复现索引：T02-01、T02-02、T02-03、T02-05。请求、角色、状态、响应、数据库前后差异见 requests.json；UI编号见 browser-results.json。

现状：主管将合成期初100000改200000成功；主管停用、财务恢复成功；外仓账户修改403。

影响：违反P5；账户菜单授权同时给规则修改能力。内部调拨静态允许三角色，但本轮未实际执行调拨。

建议修复位置与方向：账户字段白名单与动作权限拆分；期初/启停仅管理员；调拨属于资金执行须按P3设计。

## F04 备用金开户拨付审核设置及本人补充申请自批

分类：权限过宽/自批。证据等级：本地接口实际验证；代码静态确认。

代码：backend/app/api/v1/expense_fund.py:145；backend/app/api/v1/expense_fund.py:296；backend/app/api/v1/expense_fund.py:533；backend/app/api/v1/expense_fund.py:720；backend/app/services/fund_disbursement.py:65。

测试/复现索引：T03-01、T03-02、T03-03、T03-04、T03-05、T03-06。请求、角色、状态、响应、数据库前后差异见 requests.json；UI编号见 browser-results.json。

现状：主管开户、拨付100、批量审核开销、改额度均200。财务A申请补充50并本人审批200，同事务增加备用金、拨付记录及正式expense_records。

影响：违反P3/P4/P5；审批与资金执行未分开。

建议修复位置与方向：请求、依据审核、批准、拨付分别判权和判本人；不能只隐藏按钮或更改注释。现有余额/费用口径不在本轮改动。

## F05 工资分工反转

分类：权限过宽/财务缺权。证据等级：本地接口实际验证；代码静态确认。

代码：backend/app/api/v1/payroll.py:73；backend/app/api/v1/payroll.py:1507；backend/app/api/v1/payroll.py:2044；backend/app/api/v1/payroll.py:1692。

测试/复现索引：T04-01、T04-02、T04-03、T04-04、T04-05、T04-06、T04-07、T10-05。请求、角色、状态、响应、数据库前后差异见 requests.json；UI编号见 browser-results.json。

现状：主管核算、确认、发放均成功；发放新增100支出。财务直接核算、确认、发放403。管理员发放200。

影响：主管越过P2职责；财务缺核算发放权。财务确认被拒符合目标，不能混称缺权。

建议修复位置与方向：统一单笔/批量/离职结算的动作授权：主管考勤事实，财务核算，管理员确认，财务发放；重算删除后的状态回退待业务确认。

## F06 主管可读导出他人工资与财务报表

分类：字段范围/导出/需要业务确认。证据等级：本地接口实际验证；代码静态确认。

代码：backend/app/api/v1/payroll.py:1228；backend/app/api/v1/payroll.py:2304；backend/app/api/v1/payroll.py:1419；backend/app/api/v1/reports.py:96。

测试/复现索引：T05-01、T05-02、T05-03、T05B-01、T05B-02、T05B-03。请求、角色、状态、响应、数据库前后差异见 requests.json；UI编号见 browser-results.json。

现状：主管获得同仓其他员工净工资/基本工资等字段并导出XLSX；可读成本资金欠款及收支导出；外仓报表参数403。财务能读工资但导出403。

影响：目前没有按主管职责做薪资字段脱敏；目标未明确主管可读哪些薪资/利润字段，不能把所有读取直接定性违规。

建议修复位置与方向：业务先确认字段白名单与导出权限；随后服务端序列化和导出共同执行，不能仅前端隐藏。

## F07 财务可自审自付报销，主管可付款

分类：自批/本人付款/权限过宽。证据等级：本地接口实际验证；代码静态确认。

代码：backend/app/api/v1/reimbursement.py:431；backend/app/api/v1/reimbursement.py:483；backend/app/services/reimbursement_payment.py:187。

测试/复现索引：T06-01、T06-02、T06-03、T06D-01、T06D-02、T06D-03。请求、角色、状态、响应、数据库前后差异见 requests.json；UI编号见 browser-results.json。

现状：财务A本人报销审核200后本人付款200；主管为自己报销付款200。管理员审核、财务B独立付款也200，重复付款400且DB不变。

影响：违反P3/P4；状态和幂等校验不能替代本人限制。

建议修复位置与方向：审核及付款共享服务按单据最终受益人/申请人核验；代录人不能取代本人判定；保留已付拒绝。

## F08 审核本仓报销可修改另一仓明细

分类：跨仓/关联明细越权。证据等级：本地接口实际验证；代码静态确认。

代码：backend/app/api/v1/reimbursement.py:431。

测试/复现索引：T11-05、T11-06。请求、角色、状态、响应、数据库前后差异见 requests.json；UI编号见 browser-results.json。

现状：直接审核外仓报销403；审核本仓报销1却提交item_id=8（属于外仓报销8）返回200，reimbursement_items[8].review_status由pending变approved。接口只按明细ID查询，未校验所属报销单。

影响：可篡改外仓审核事实，且本仓主单合计按外来明细金额重算；是数据库已证实越权，不是UI推测。

建议修复位置与方向：查询同时限定明细ID、reimbursement_id、warehouse；批量明细全量校验与事务原子性；检查同类父子单据入口。

## F09 主管能批准本人请假并代录本人已通过请假

分类：自批/代录旁路。证据等级：本地接口实际验证；代码静态确认。

代码：backend/app/api/v1/attendance.py:329；backend/app/api/v1/attendance.py:192；backend/app/api/v1/overtime.py:205。

测试/复现索引：T07-01、T07-02、T07-03、T07-04。请求、角色、状态、响应、数据库前后差异见 requests.json；UI编号见 browser-results.json。

现状：本人请假批准200；代录自己请假直接approved。本人加班核实403，主管审批预支403。

影响：请假本人约束缺失；不能把已存在的加班/预支拦截套用于请假。

建议修复位置与方向：统一本人判定覆盖正常审批、代录、批量；主管本人事实由谁核实需业务明确，本轮不指派替代人。

## F10 专用规则可由主管改，通用设置可让财务绕过

分类：规则/历史兼容/权限过宽。证据等级：本地接口实际验证；代码静态确认。

代码：backend/app/api/v1/expense_fund.py:785；backend/app/api/v1/overtime.py:776；backend/app/api/v1/suppliers.py:923；backend/app/core/config_access.py:6。

测试/复现索引：T08-01、T08-02、T08-03、T08-04、T08-05、T08-06、T08B-02。请求、角色、状态、响应、数据库前后差异见 requests.json；UI编号见 browser-results.json。

现状：主管采购门槛置0、价格阈值25、加班上限60成功。财务专用加班接口403，但备用金/settings写overtime_monthly_limit=70和purchase_approval_threshold=0成功。purchase_duty_separation_v1特定键403。

影响：违反P5；只修专用接口仍留旁路；零采购门槛影响既有自动生效路径。

建议修复位置与方向：通用配置按键白名单及统一管理员写权限；覆盖专用/旧路径/批量，不新增阈值或自动批准政策。

## F11 主管可以改薪资模板及员工工资字段

分类：字段越权/规则。证据等级：本地接口实际验证；代码静态确认。

代码：backend/app/api/v1/salary_template.py:118；backend/app/api/v1/employees.py:410；backend/app/api/v1/deduction_template.py:39。

测试/复现索引：T08-07、T08B-01、T08-08。请求、角色、状态、响应、数据库前后差异见 requests.json；UI编号见 browser-results.json。

现状：主管改薪资模板amount=999；员工daily_wage=987/base_salary=23456成功。外仓模板ID被400拒绝。财务模板写权限由静态角色条件也允许，未实际覆盖全部模板写组合。

影响：违反P5；员工档案编辑权限混入薪资规则字段。

建议修复位置与方向：员工字段白名单分离事实档案与薪资标准；模板/批量模板/扣款规则入口同一管理员策略。

## F12 财务本人预支直接批准并形成支出

分类：自批/本人付款/关联出款。证据等级：本地接口实际验证；代码静态确认。

代码：backend/app/api/v1/employee_advance.py:64；backend/app/services/employee_advance_funding.py:113。

测试/复现索引：T06B-01、T06B-02、T06B-03、T06-09、T06-10。请求、角色、状态、响应、数据库前后差异见 requests.json；UI编号见 browser-results.json。

现状：财务本人新建预支10：approval_status=approved并新增expense_records。主管本人新建待批不出款；主管给其他员工新建则approved且出款。财务审批端点403并不能阻止新建旁路。

影响：违反P3/P4；只修approve接口不足，资金已在create时执行。

建议修复位置与方向：按受益人及角色决定申请状态；独立审核批准执行；所有funding_source共用限制。不得自行扩大自动批准。

## F13 主管直接登记运营支出形成付款

分类：正式记账/付款旁路。证据等级：本地接口实际验证；代码静态确认。

代码：backend/app/api/v1/income_expense.py:206；backend/app/services/manual_wallet.py:39；backend/app/services/manual_wallet.py:57。

测试/复现索引：T06C-01、T06C-02、T06C-03。请求、角色、状态、响应、数据库前后差异见 requests.json；UI编号见 browser-results.json。

现状：主管运营收支form提交10成功，expense_records产生正式出款且approved_by=本人；账本可读。已停用经营报表入口403。

影响：违反P3；经营报表停用不等于钱包录入已停用。

建议修复位置与方向：在正式支出共享服务绑定已批准依据和执行身份；保留既有会计口径，不把本轮变成金额计算修复。

## F14 纳入考勤的财务仍不能用统一员工自助

分类：财务缺权/员工自助。证据等级：本地接口实际验证；代码静态确认。

代码：backend/app/core/employee_access.py:11；backend/app/core/employee_access.py:37。

测试/复现索引：T09-05、T09-06、T09-07、T09-08、T09B-01、T09B-02、T09B-04、T09B-05、T09C-01。请求、角色、状态、响应、数据库前后差异见 requests.json；UI编号见 browser-results.json。

现状：主管本人打卡/请假成功；已绑定员工且attendance_enabled=true的财务打卡、view=self请假和工资条等403。旧不带view请假在本夹具返回400未找到档案，不能说所有旧财务请假均403。

影响：不满足主管、财务都保留自助身份；绑定开关与实际自助判断不一致。

建议修复位置与方向：统一员工身份解析覆盖supervisor/staff，保留本人和仓库范围，不用管理端权限替代自助。

## F15 应付单笔付款拒绝财务，付款计划可执行

分类：批量旁路/财务缺权。证据等级：本地接口实际验证；代码静态确认。

代码：backend/app/api/v1/payable.py:260；backend/app/api/v1/payable.py:779；backend/app/services/payable_payment.py:11。

测试/复现索引：T06-05、T06-06、T06-07。请求、角色、状态、响应、数据库前后差异见 requests.json；UI编号见 browser-results.json。

现状：财务直接付应付403，同角色执行付款计划200，新增payment记录；主管直接付款200。

影响：单笔与批量角色不一致；现有匹配/余额/单据状态守卫不代表完成P3批准交接。

建议修复位置与方向：付款服务统一角色、批准依据和本人限制；计划逐单验证；财务执行权应按目标修正，而非一概封掉财务计划。

## F16 页面可见操作与接口允许不同

分类：前后端不一致。证据等级：本地页面实际验证；本地接口实际验证；代码静态确认。

代码：frontend/src/components/layout/DashboardLayout.tsx；frontend/src/app/(dashboard)/payroll/page.tsx；frontend/src/app/(dashboard)/accounts/page.tsx。

测试/复现索引：UI-1、UI-3、UI-6、T05-07、T04-01。请求、角色、状态、响应、数据库前后差异见 requests.json；UI编号见 browser-results.json。

现状：财务工资页有导出按钮而接口403；无扩展权限主管仍见计算按钮而接口403。财务账户页显示删除按钮，后端delete_account限制管理员/主管（删除实际请求未在本轮执行）。菜单对主管/财务以扩展权限清单判定，不能仅据静态roles数组说菜单不可见。

影响：误导操作、增加错误；这几项按钮可见本身不等于接口越权。

建议修复位置与方向：前后端使用相同动作能力结果，后端保持最终判权；同步菜单/按钮/字段，不单靠UI修复。

## F17 菜单授权不能稳定拆分查看操作审批

分类：权限颗粒度/历史兼容。证据等级：本地接口实际验证；代码静态确认。

代码：backend/app/core/permissions.py:28；backend/app/core/route_access.py:62。

测试/复现索引：T10-01、T10-02、T10-06、T10-07、T10-08、T10-09。请求、角色、状态、响应、数据库前后差异见 requests.json；UI编号见 browser-results.json。

现状：运营收支权限可共用读取账户但不能改账户；一旦授予收款账户，读取和修改都成功。历史全勾账号触发所有宽权限路径。

影响：局部有共用只读入口，但不能据此说系统已实现统一的查看/操作/审批权限分离。

建议修复位置与方向：先建立动作权限和字段约束；默认拒绝高风险角色越界，旧权限兼容不得覆盖明确禁止。

## F18 扩展菜单授权可读取同仓他人证件附件

分类：字段范围/附件/需要业务确认。证据等级：本地接口实际验证；代码静态确认。

代码：backend/app/api/secure_uploads.py:121；backend/app/api/secure_uploads.py:178。

测试/复现索引：T12B-03、T12B-05、T12B-04、T12B-06、T12B-09、T12B-11。请求、角色、状态、响应、数据库前后差异见 requests.json；UI编号见 browser-results.json。

现状：全权限主管、财务下载普通员工护照图片200；外仓403、无权限403、停用账号401。成功附件Cache-Control=private,no-store。

影响：同仓并不等于字段最小权限；哪些角色可读身份证/银行/工资附件需业务明确，未据此认定全部同仓读取非法。

建议修复位置与方向：附件按所属记录、字段用途、本人/管理能力鉴权；动态图片/缩略图与导出保持一致。

## F19 通用审计仓库取请求头且不保证字段历史

分类：审计记录。证据等级：本地接口实际验证；代码静态确认。

代码：backend/app/core/audit.py:63；backend/app/api/v1/payment_accounts.py:130。

测试/复现索引：T02-01。请求、角色、状态、响应、数据库前后差异见 requests.json；UI编号见 browser-results.json。

现状：不带X-Warehouse-ID的成功合成账户修改，其audit_logs.warehouse_id为空；仅method/path/status通用记录，账户修改没有DataChangeHistory前后值。

影响：按仓筛选日志可能看不到该条；角色/金额变更缺少独立字段历史证据。审计失败不影响业务，不能宣称强制不可缺失审计。

建议修复位置与方向：从已验证业务作用域写审计仓库；高风险动作记录操作者、批准依据、字段前后值，明确失败策略待业务确认。

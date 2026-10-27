# 本地请求证据索引

所有身份和数据合成。返回200若违反P1–P5是缺陷复现，不是目标验收通过。完整返回和DB前后见 requests.json。

|测试|角色ID|方法与路径|状态|变化表|关键响应|
|---|---|---|---|---|---|
|T01-01|supervisor 2|POST /users|200|users,audit_logs,data_change_history,user_warehouses|用户创建成功|
|T01-02|supervisor 2|DELETE /users/9|200|users,audit_logs,data_change_history,user_warehouses|已删除用户 audit-new-finance|
|T01-03|staff 3|POST /users|200|users,audit_logs,data_change_history,user_warehouses|用户创建成功|
|T01-04|supervisor 2|PUT /users/3|403|无变化|无权限编辑用户|
|T01-05|supervisor 6|POST /users|403|无变化|无此操作权限，需要: 系统设置|
|T02-01|supervisor 2|PUT /accounts/1|200|audit_logs,payment_accounts|更新成功|
|T02-02|supervisor 2|PUT /accounts/1/toggle-status|200|audit_logs,payment_accounts|状态已切换|
|T02-03|staff 3|PUT /accounts/1/toggle-status|200|audit_logs,payment_accounts|状态已切换|
|T02-04|supervisor 6|PUT /accounts/1|403|无变化|无此操作权限，需要: 收款账户|
|T02-05|supervisor 2|PUT /accounts/2|403|无变化|只能修改自己仓库的账户|
|T02-06|staff 7|GET /accounts|401|无变化|User not found or inactive|
|T03-01|supervisor 2|POST /expense-fund/accounts|200|audit_logs,expense_funds|备用金账户创建成功|
|T03-02|supervisor 2|POST /expense-fund/accounts/1/topup|200|audit_logs,data_change_history,expense_funds,income_expense_categories,expense_records,expense_fund_disbursements|充值成功，已记入运营支出|
|T03-03|supervisor 2|POST /expense-fund/review/batch|200|audit_logs,data_change_history,cost_identities,expense_fund_items|已通过1条记录|
|T03-04|supervisor 2|POST /expense-fund/settings|200|audit_logs,system_settings|设置已保存|
|T03-05|staff 3|POST /expense-fund/recharge/request|200|audit_logs,fund_recharge_requests|充值申请已提交，等待管理员审核|
|T03-06|staff 3|POST /expense-fund/recharge/review|200|audit_logs,data_change_history,expense_funds,fund_recharge_requests,expense_records,expense_fund_disbursements|充值申请已通过，已记入运营支出|
|T04-01|staff 3|POST /payroll/calculate|403|无变化|只有仓库管理员可以计算工资|
|T04-02|supervisor 2|POST /payroll/calculate|200|audit_logs,payroll_records|已为 1 名员工计算 2026-10 工资|
|T04-03|staff 3|POST /payroll/1/confirm|403|无变化|只有仓库管理员可以确认工资|
|T04-04|supervisor 2|POST /payroll/1/confirm|200|audit_logs,payroll_records|工资单已确认|
|T04-05|staff 3|POST /payroll/2/disburse|403|无变化|只有仓库管理员可以发放工资|
|T04-06|supervisor 2|POST /payroll/2/disburse|200|audit_logs,data_change_history,expense_records,payroll_records|已向 SYNTHETIC EMP 1 发放 100.00 泰铢工资|
|T04-07|warehouse_admin 1|POST /payroll/1/disburse|200|audit_logs,data_change_history,expense_records,payroll_records|已向 SYNTHETIC EMP 1 发放 100.00 泰铢工资|
|T05-01|supervisor 2|GET /payroll|200|无变化||
|T05-02|supervisor 2|GET /payroll/1|200|无变化|{}|
|T05-03|supervisor 2|GET /payroll/export|200|无变化|application/vnd.openxmlformats-officedocument.spreadsheetml.sheet|
|T05-04|supervisor 2|GET /reports/previews|200|无变化||
|T05-05|staff 3|GET /payroll|200|无变化||
|T05-06|staff 3|GET /payroll/1|200|无变化|{}|
|T05-07|staff 3|GET /payroll/export|403|无变化|只有仓库管理员/主管可以导出工资|
|T05-08|staff 3|GET /reports/previews|200|无变化||
|T05-09|supervisor 6|GET /payroll|403|无变化|无此操作权限，需要: 工资|
|T05-10|supervisor 6|GET /payroll/1|403|无变化|无此操作权限，需要: 工资|
|T05-11|supervisor 6|GET /payroll/export|403|无变化|无此操作权限，需要: 工资|
|T05-12|supervisor 6|GET /reports/previews|403|无变化|无此操作权限，需要: 报表中心|
|T05-13|warehouse_admin 8|GET /payroll|200|无变化||
|T05-14|warehouse_admin 8|GET /payroll/1|404|无变化|工资单不存在|
|T05-15|warehouse_admin 8|GET /payroll/export|200|无变化|application/vnd.openxmlformats-officedocument.spreadsheetml.sheet|
|T05-16|warehouse_admin 8|GET /reports/previews|200|无变化||
|T06-01|staff 3|POST /reimbursement/1/review|200|audit_logs,reimbursements,reimbursement_items|审批完成|
|T06-02|staff 3|POST /reimbursement/1/pay|200|audit_logs,data_change_history,expense_records,reimbursements,reimbursement_payments|付款成功|
|T06-03|supervisor 2|POST /reimbursement/2/pay|200|audit_logs,data_change_history,expense_records,reimbursements,reimbursement_payments|付款成功|
|T06-04|staff 4|POST /reimbursement/3/pay|200|audit_logs,data_change_history,expense_records,reimbursements,reimbursement_payments|付款成功|
|T06-05|staff 3|PUT /payable/1/pay?account_id=1&paid_amount=100|403|无变化|无权限|
|T06-06|supervisor 2|PUT /payable/1/pay?account_id=1&paid_amount=100|200|payable_bills,audit_logs,data_change_history,cost_identities,payable_payments|付款记录成功|
|T06-07|staff 3|PUT /payable/plans/1/execute?account_id=1|200|payable_bills,audit_logs,data_change_history,payable_plans,cost_identities,payable_payments|计划执行成功，已结算 1 笔账单|
|T06-08|supervisor 2|POST /employee-advances/1/approve|403|无变化|只有仓库管理员可以审批预支|
|T06-09|staff 3|POST /employee-advances/2/approve|403|无变化|只有仓库管理员可以审批预支|
|T06-10|warehouse_admin 1|POST /employee-advances/2/approve|200|audit_logs,data_change_history,expense_records,employee_advances|预支已通过|
|T06-11|supervisor 2|POST /expense-approvals/1/approve|403|无变化|只有仓库管理员可以审批|
|T06-12|supervisor 2|POST /expense-approvals/1/pay|403|无变化|只有仓库管理员可以审批|
|T07-01|supervisor 2|PUT /attendance/leaves/2/approve|200|audit_logs,leave_requests|已批准|
|T07-02|supervisor 2|POST /attendance/leaves/admin-record|200|audit_logs,leave_requests|已代录 1 条请假，跳过 0 天|
|T07-03|supervisor 2|POST /overtime/2/verify|403|无变化|本人不能核实自己的加班|
|T07-04|supervisor 2|POST /employee-advances/1/approve|403|无变化|只有仓库管理员可以审批预支|
|T07-05|supervisor 2|POST /overtime|200|audit_logs,overtime_tasks,overtime_assignments|加班任务创建成功|
|T08-01|supervisor 2|PUT /suppliers/purchase-approval-threshold|200|audit_logs,system_settings|采购审批门槛已设为 0.0 泰铢|
|T08-02|supervisor 2|PUT /suppliers/price-threshold|200|audit_logs,system_settings|价格阈值已设为 25.0%|
|T08-03|supervisor 2|PUT /overtime/limit|200|audit_logs,system_settings|加班上限已设为 60 小时/月|
|T08-04|staff 3|PUT /overtime/limit|403|无变化|只有仓库管理员可以设置加班上限|
|T08-05|staff 3|POST /expense-fund/settings|200|audit_logs,system_settings|设置已保存|
|T08-06|staff 3|POST /expense-fund/settings|200|audit_logs,system_settings|设置已保存|
|T08-07|supervisor 2|PUT /salary-templates/1|200|salary_templates,audit_logs|薪资模板已更新|
|T08-08|supervisor 2|PUT /employees/1|400|无变化|薪资模板不存在|
|T09-01|supervisor 2|GET /clock-in/today|200|无变化||
|T09-02|supervisor 2|GET /attendance/leaves?view=self|200|无变化||
|T09-03|supervisor 2|GET /overtime/pending?view=self|200|无变化||
|T09-04|supervisor 2|GET /payroll/my-payslip|200|无变化||
|T09-05|staff 3|GET /clock-in/today|403|无变化|无权限|
|T09-06|staff 3|GET /attendance/leaves?view=self|403|无变化|无此操作权限|
|T09-07|staff 3|GET /overtime/pending?view=self|403|无变化|无权限|
|T09-08|staff 3|GET /payroll/my-payslip|403|无变化|无权限|
|T09-09|staff 4|GET /clock-in/today|403|无变化|无权限|
|T09-10|staff 4|GET /attendance/leaves?view=self|403|无变化|无此操作权限|
|T09-11|staff 4|GET /overtime/pending?view=self|403|无变化|无权限|
|T09-12|staff 4|GET /payroll/my-payslip|403|无变化|无权限|
|T09-13|warehouse_labor 5|GET /clock-in/today|200|无变化||
|T09-14|warehouse_labor 5|GET /attendance/leaves?view=self|200|无变化||
|T09-15|warehouse_labor 5|GET /overtime/pending?view=self|200|无变化||
|T09-16|warehouse_labor 5|GET /payroll/my-payslip|200|无变化||
|T09-17|supervisor 6|GET /clock-in/today|403|无变化|无此操作权限，需要: 考勤|
|T09-18|supervisor 6|GET /attendance/leaves?view=self|403|无变化|无此操作权限|
|T09-19|supervisor 6|GET /overtime/pending?view=self|403|无变化|无此操作权限，需要: 加班|
|T09-20|supervisor 6|GET /payroll/my-payslip|403|无变化|无此操作权限，需要: 工资|
|T09-21|staff 7|GET /clock-in/today|401|无变化|User not found or inactive|
|T09-22|staff 7|GET /attendance/leaves?view=self|401|无变化|User not found or inactive|
|T09-23|staff 7|GET /overtime/pending?view=self|401|无变化|User not found or inactive|
|T09-24|staff 7|GET /payroll/my-payslip|401|无变化|User not found or inactive|
|T10-01|supervisor 6|GET /accounts|403|无变化|无此操作权限，需要: 收款账户 / 工资 / 应付账款 / 付款计划 / 到账流水 / 账期管理 / 费用审批 / 运营收支 / 其他收支|
|T10-02|supervisor 6|PUT /accounts/1|403|无变化|无此操作权限，需要: 收款账户|
|T10-03|supervisor 2|GET /accounts|200|无变化||
|T10-04|supervisor 2|PUT /accounts/1|200|audit_logs,payment_accounts|更新成功|
|T10-05|supervisor 2|POST /payroll/batch-confirm|200|audit_logs,payroll_records|已确认 1 条|
|T10-06|supervisor 6|GET /accounts|200|无变化||
|T10-07|supervisor 6|PUT /accounts/1|403|无变化|无此操作权限，需要: 收款账户|
|T10-08|supervisor 6|GET /accounts|200|无变化||
|T10-09|supervisor 6|PUT /accounts/1|200|audit_logs|更新成功|
|T11-01|supervisor 2|GET /accounts|403|无变化|无权访问所选仓库|
|T11-02|supervisor 2|GET /employees|200|无变化||
|T11-03|supervisor 2|GET /payroll/8|404|无变化|工资单不存在|
|T11-04|supervisor 2|PUT /attendance/leaves/8/approve|403|无变化|无权审批其他仓库的申请|
|T11-05|supervisor 2|POST /reimbursement/8/review|403|无变化|只能审批本仓库的报销单|
|T11-06|supervisor 2|POST /reimbursement/1/review|200|audit_logs,reimbursements,reimbursement_items|审批完成|
|T11-07|supervisor 2|POST /reimbursement/2/pay|400|无变化|付款账户不存在或不属于当前仓库|
|T11-08|supervisor 2|PUT /employees/8|403|无变化|只能编辑自己仓库的员工|
|T12-01|supervisor 2|POST /payroll/batch-confirm|403|无变化|包含无权操作的记录|
|T12-02|supervisor 2|GET /payable/batch-export|200|无变化||
|T12-03|supervisor 2|GET /payable/plans/export|200|无变化|application/vnd.openxmlformats-officedocument.spreadsheetml.sheet|
|T12-04|supervisor 2|GET /expense-fund/balance|200|无变化||
|T12-05|supervisor 6|GET /expense-fund/balance|403|无变化|无此操作权限，需要: 备用金管理|
|T12-06|supervisor 2|GET /clock-in/records/export?start_date=2026-10-01&end_date=2026-10-28|200|无变化|application/vnd.openxmlformats-officedocument.spreadsheetml.sheet|
|T12-07|staff 3|GET /payable/plans/export|200|无变化|application/vnd.openxmlformats-officedocument.spreadsheetml.sheet|
|T12B-01|warehouse_admin 1|GET /uploads/1/audit/passport-1.png|200|无变化|image/png|
|T12B-02|warehouse_admin 1|GET /uploads/2/audit/passport-8.png|403|无变化|无权访问|
|T12B-03|supervisor 2|GET /uploads/1/audit/passport-1.png|200|无变化|image/png|
|T12B-04|supervisor 2|GET /uploads/2/audit/passport-8.png|403|无变化|无权访问|
|T12B-05|staff 3|GET /uploads/1/audit/passport-1.png|200|无变化|image/png|
|T12B-06|staff 3|GET /uploads/2/audit/passport-8.png|403|无变化|无权访问|
|T12B-07|warehouse_labor 5|GET /uploads/1/audit/passport-1.png|403|无变化|无权访问|
|T12B-08|warehouse_labor 5|GET /uploads/2/audit/passport-8.png|403|无变化|无权访问|
|T12B-09|supervisor 6|GET /uploads/1/audit/passport-1.png|403|无变化|无权访问|
|T12B-10|supervisor 6|GET /uploads/2/audit/passport-8.png|403|无变化|无权访问|
|T12B-11|staff 7|GET /uploads/1/audit/passport-1.png|401|无变化|User not found or inactive|
|T12B-12|staff 7|GET /uploads/2/audit/passport-8.png|401|无变化|User not found or inactive|
|T12B-13|warehouse_admin 8|GET /uploads/1/audit/passport-1.png|403|无变化|无权访问|
|T12B-14|warehouse_admin 8|GET /uploads/2/audit/passport-8.png|200|无变化|image/png|
|T09B-01|supervisor 2|POST /clock-in|200|clock_in_records|早上上班打卡成功|
|T09B-02|staff 3|POST /clock-in|403|无变化|无权限|
|T09B-03|warehouse_labor 5|POST /clock-in|200|clock_in_records|早上上班打卡成功|
|T09B-04|supervisor 2|POST /attendance/leaves?view=self|200|audit_logs,leave_requests|请假申请已提交，等待审批|
|T09B-05|staff 3|POST /attendance/leaves?view=self|403|无变化|无此操作权限|
|T08B-01|supervisor 2|PUT /employees/1|200|employees,audit_logs|更新成功|
|T08B-02|staff 3|POST /expense-fund/settings|403|无变化|采购职责配置必须通过老板专属入口并核对版本，不能由备用金设置改写|
|T08B-03|supervisor 2|GET /supplier-controls/policy|403|无变化|仅仓库管理员可以查看采购风险看板|
|T01B-01|supervisor 2|POST /employees/4/resign|200|employees,users,audit_logs,data_change_history,payroll_records|已将SYNTHETIC EMP 4标记为离职（正常离职），已生成离职结算工资单（结算到 2026-10-15）|
|T01B-02|staff 3|POST /employees/1/resign|200|employees,users,audit_logs,data_change_history|已将SYNTHETIC EMP 1标记为离职（正常离职），本期工资已结算过，跳过|
|T06B-01|staff 3|POST /employee-advances|200|audit_logs,data_change_history,expense_records,employee_advances|预支记录已创建|
|T06B-02|supervisor 2|POST /employee-advances|200|audit_logs,employee_advances|预支记录已创建|
|T06B-03|supervisor 2|POST /employee-advances|200|audit_logs,data_change_history,expense_records,employee_advances|预支记录已创建|
|T06B-04|staff 3|POST /expense-approvals/2/pay|403|无变化|只有仓库管理员可以审批|
|T06C-01|supervisor 2|POST /income-expense/expense|200|audit_logs,data_change_history,cost_identities,expense_records|付款记录创建成功|
|T06C-02|supervisor 2|GET /income-expense/ledger|200|无变化||
|T06C-03|supervisor 2|GET /reports/operations|403|无变化|经营报表及客户应收、发货录入功能已停用|
|T05B-01|supervisor 2|GET /reports/income-expense?format=excel|200|无变化|application/vnd.openxmlformats-officedocument.spreadsheetml.sheet|
|T05B-02|supervisor 2|GET /reports/cost-funds-debt|200|无变化||
|T05B-03|supervisor 2|GET /reports/previews?warehouse_id=2|403|无变化|无权访问所选仓库|
|T05B-04|staff 3|GET /reports/income-expense?format=excel|200|无变化|application/vnd.openxmlformats-officedocument.spreadsheetml.sheet|
|T05B-05|staff 3|GET /reports/cost-funds-debt|200|无变化||
|T05B-06|staff 3|GET /reports/previews?warehouse_id=2|403|无变化|无权访问所选仓库|
|T06D-01|warehouse_admin 1|POST /reimbursement/1/review|200|audit_logs,reimbursements,reimbursement_items|审批完成|
|T06D-02|staff 4|POST /reimbursement/1/pay|200|audit_logs,data_change_history,expense_records,reimbursements,reimbursement_payments|付款成功|
|T06D-03|staff 4|POST /reimbursement/1/pay|400|无变化|该报销单已付款|
|T09C-01|staff 3|POST /attendance/leaves|400|无变化|未找到您的员工档案，请联系管理员|
|T13-01|warehouse_admin 1|POST /payroll/3/revoke-disbursement|400|无变化|撤销功能已停用 请用负数冲销记录处理|
|T13-02|warehouse_admin 1|POST /reimbursement/2/revoke-payment|400|无变化|撤销功能已停用 请用负数冲销记录处理|
|T13-03|warehouse_admin 1|POST /cash-advances/repayments/1/revoke|400|无变化|撤销功能已停用 请用负数冲销记录处理|
|T13-04|supervisor 2|POST /payroll/3/revoke-disbursement|400|无变化|撤销功能已停用 请用负数冲销记录处理|
|T13-05|supervisor 2|POST /reimbursement/2/revoke-payment|400|无变化|撤销功能已停用 请用负数冲销记录处理|
|T13-06|supervisor 2|POST /cash-advances/repayments/1/revoke|400|无变化|撤销功能已停用 请用负数冲销记录处理|
|T13-07|staff 3|POST /payroll/3/revoke-disbursement|400|无变化|撤销功能已停用 请用负数冲销记录处理|
|T13-08|staff 3|POST /reimbursement/2/revoke-payment|400|无变化|撤销功能已停用 请用负数冲销记录处理|
|T13-09|staff 3|POST /cash-advances/repayments/1/revoke|400|无变化|撤销功能已停用 请用负数冲销记录处理|
|T13-10|warehouse_labor 5|POST /payroll/3/revoke-disbursement|403|无变化|无权访问|
|T13-11|warehouse_labor 5|POST /reimbursement/2/revoke-payment|403|无变化|无权访问|
|T13-12|warehouse_labor 5|POST /cash-advances/repayments/1/revoke|403|无变化|无权访问|
|T13-13|supervisor 6|POST /payroll/3/revoke-disbursement|400|无变化|撤销功能已停用 请用负数冲销记录处理|
|T13-14|supervisor 6|POST /reimbursement/2/revoke-payment|400|无变化|撤销功能已停用 请用负数冲销记录处理|
|T13-15|supervisor 6|POST /cash-advances/repayments/1/revoke|403|无变化|无此操作权限，需要: 垫款单|
|T13-16|staff 7|POST /payroll/3/revoke-disbursement|401|无变化|User not found or inactive|
|T13-17|staff 7|POST /reimbursement/2/revoke-payment|401|无变化|User not found or inactive|
|T13-18|staff 7|POST /cash-advances/repayments/1/revoke|401|无变化|User not found or inactive|

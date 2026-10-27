# 本轮动作权限与入口对照

财务在代码中为 staff。所有允许项均叠加现有菜单、有效账号、对象仓库和状态条件；历史全权限不能突破角色上限。字段、位置和请求编号见 action-permissions.json。此表按注册接口列行，以下附表再拆分同接口的账号字段及审批动作。

|编号|动作/接口|角色与交接|页面|验证|
|---|---|---|---|---|
|A-01|POST /api/v1/auth/change-password|现有有效登录身份，本人旧密码校验；不需账号管理权限|个人设置 修改密码|A-finance-own-password|
|A-02|GET /api/v1/users|沿用原读取菜单、角色及授权仓库范围；本轮未扩大读取字段|/settings 用户管理|静态/相关回归；目标脚本未直测|
|A-03|GET /api/v1/users/permissions|沿用原读取菜单、角色及授权仓库范围；本轮未扩大读取字段|/settings 用户管理|静态/相关回归；目标脚本未直测|
|A-04|POST /api/v1/users|管理员在授权范围内操作；主管、财务拒绝；原菜单鉴权仍保留|/settings 用户管理|A-create-2, A-create-3, A-create-4, A-create-5, A-create-6, A-create-7, A-admin-create, A-finance-no-grants|
|A-05|PUT /api/v1/users/{user_id}|管理员在授权范围内操作；主管、财务拒绝；原菜单鉴权仍保留|/settings 用户管理|A-update-2, A-update-3, A-update-4, A-update-5, A-update-6, A-update-7, A-admin-foreign, A-forged-header, A-admin-update-local, A-admin-enable-local, A-admin-secondary-warehouse-outside-scope|
|A-06|DELETE /api/v1/users/{user_id}|管理员在授权范围内操作；主管、财务拒绝；原菜单鉴权仍保留|/settings 用户管理|A-delete-2, A-delete-3, A-delete-4, A-delete-5, A-delete-6, A-delete-7, A-admin-delete-new|
|B-07|POST /api/v1/accounts/transfers|主管拒绝；管理员、财务保留既有调拨能力和菜单约束；未新增调拨审批流程|/accounts 新建/编辑/启停/删除/调拨|B-supervisor-transfer-denied|
|B-08|GET /api/v1/accounts|沿用原读取菜单、角色及授权仓库范围；本轮未扩大读取字段|/accounts 新建/编辑/启停/删除/调拨|B-finance-select|
|B-09|POST /api/v1/accounts|管理员在授权范围内操作；主管、财务拒绝；原菜单鉴权仍保留|/accounts 新建/编辑/启停/删除/调拨|B-create-2, B-create-3, B-create-4, B-create-5, B-create-6, B-create-7, B-admin-create|
|B-10|PUT /api/v1/accounts/{account_id}|管理员在授权范围内操作；主管、财务拒绝；原菜单鉴权仍保留|/accounts 新建/编辑/启停/删除/调拨|B-update-2, B-update-3, B-update-4, B-update-5, B-update-6, B-update-7, B-admin-update-without-header, B-admin-extra-field, B-admin-cross, B-admin-forged-header, B-authorized-secondary-no-header-audit, B-selected-warehouse-mismatch, B-finance-no-grants|
|B-11|PUT /api/v1/accounts/{account_id}/toggle-status|管理员在授权范围内操作；主管、财务拒绝；原菜单鉴权仍保留|/accounts 新建/编辑/启停/删除/调拨|B-toggle-2, B-toggle-3, B-toggle-4, B-toggle-5, B-toggle-6, B-toggle-7, B-admin-toggle|
|B-12|DELETE /api/v1/accounts/{account_id}|管理员在授权范围内操作；主管、财务拒绝；原菜单鉴权仍保留|/accounts 新建/编辑/启停/删除/调拨|B-delete-2, B-delete-3, B-delete-4, B-delete-5, B-delete-6, B-delete-7, B-admin-delete-unused, B-delete-account-with-flow|
|D-13|PUT /api/v1/suppliers/purchase-match-policy|管理员在授权范围内操作；主管、财务拒绝；原菜单鉴权仍保留|配置中心采购规则/供应商专用策略|静态/相关回归；目标脚本未直测|
|D-14|PUT /api/v1/suppliers/price-threshold|管理员在授权范围内操作；主管、财务拒绝；原菜单鉴权仍保留|配置中心采购规则/供应商专用策略|D-supervisor-price-threshold, D-finance-price-threshold|
|D-15|PUT /api/v1/suppliers/purchase-approval-threshold|管理员在授权范围内操作；主管、财务拒绝；原菜单鉴权仍保留|配置中心采购规则/供应商专用策略|D-special-rule-2-/suppliers/purchase-approval-threshold, D-special-rule-3-/suppliers/purchase-approval-threshold|
|D-16|PUT /api/v1/suppliers/concentration-threshold|管理员在授权范围内操作；主管、财务拒绝；原菜单鉴权仍保留|配置中心采购规则/供应商专用策略|D-special-rule-2-/suppliers/concentration-threshold, D-special-rule-3-/suppliers/concentration-threshold|
|C-17|POST /api/v1/expense-fund/accounts|管理员在授权范围内操作；主管、财务拒绝；原菜单鉴权仍保留|/expense-fund 开户/用途记录/补充申请/核验/批准/执行|C-open-2, C-open-3, C-open-4|
|C-18|GET /api/v1/expense-fund/employees|沿用原读取菜单、角色及授权仓库范围；本轮未扩大读取字段|/expense-fund 开户/用途记录/补充申请/核验/批准/执行|静态/相关回归；目标脚本未直测|
|C-19|GET /api/v1/expense-fund/accounts|沿用原读取菜单、角色及授权仓库范围；本轮未扩大读取字段|/expense-fund 开户/用途记录/补充申请/核验/批准/执行|静态/相关回归；目标脚本未直测|
|C-20|GET /api/v1/expense-fund/payment-accounts|沿用原读取菜单、角色及授权仓库范围；本轮未扩大读取字段|/expense-fund 开户/用途记录/补充申请/核验/批准/执行|静态/相关回归；目标脚本未直测|
|C-21|GET /api/v1/expense-fund/accounts/{account_id}/disbursements|沿用原读取菜单、角色及授权仓库范围；本轮未扩大读取字段|/expense-fund 开户/用途记录/补充申请/核验/批准/执行|静态/相关回归；目标脚本未直测|
|C-22|POST /api/v1/expense-fund/accounts/{account_id}/topup|所有角色拒绝，旧直拨入口关闭|/expense-fund 开户/用途记录/补充申请/核验/批准/执行|C-direct-topup-2, C-direct-topup-3, C-direct-topup-4|
|C-23|GET /api/v1/expense-fund/accounts/{account_id}/items|沿用原读取菜单、角色及授权仓库范围；本轮未扩大读取字段|/expense-fund 开户/用途记录/补充申请/核验/批准/执行|静态/相关回归；目标脚本未直测|
|C-24|PUT /api/v1/expense-fund/accounts/{account_id}/items/{item_id}|管理员在授权范围内操作；主管、财务拒绝；原菜单鉴权仍保留|/expense-fund 开户/用途记录/补充申请/核验/批准/执行|C-edit-verified-expense-resets|
|C-25|DELETE /api/v1/expense-fund/accounts/{account_id}/items/{item_id}|管理员在授权范围内操作；主管、财务拒绝；原菜单鉴权仍保留|/expense-fund 开户/用途记录/补充申请/核验/批准/执行|C-void-selected-warehouse-mismatch|
|C-26|POST /api/v1/expense-fund/accounts/{account_id}/items|主管/财务仅本人受益账户；管理员可代录；角色与菜单及仓库共同约束|/expense-fund 开户/用途记录/补充申请/核验/批准/执行|C-supervisor-own-expense, C-supervisor-other-expense|
|C-27|POST /api/v1/expense-fund/accounts/{account_id}/upload-receipt|主管/财务仅本人受益账户；管理员可代录；角色与菜单及仓库共同约束|/expense-fund 开户/用途记录/补充申请/核验/批准/执行|静态/相关回归；目标脚本未直测|
|C-28|POST /api/v1/expense-fund/accounts/{account_id}/items/{item_id}/upload-receipt|管理员在授权范围内操作；主管、财务拒绝；原菜单鉴权仍保留|/expense-fund 开户/用途记录/补充申请/核验/批准/执行|静态/相关回归；目标脚本未直测|
|C-29|GET /api/v1/expense-fund/review/pending|沿用原读取菜单、角色及授权仓库范围；本轮未扩大读取字段|/expense-fund 开户/用途记录/补充申请/核验/批准/执行|静态/相关回归；目标脚本未直测|
|C-30|POST /api/v1/expense-fund/review/batch|verify：财务/管理员独立核验；approve/reject：管理员；全部明细先校验，本人/关联员工拒绝|/expense-fund 开户/用途记录/补充申请/核验/批准/执行|C-batch-approve-2, C-batch-approve-3, C-batch-approve-4, C-approve-before-verify, C-finance-verify-expense, C-stale-verification-rejected, C-finance-reverify-expense, C-admin-approve-expense, C-linked-finance-verify|
|C-31|POST /api/v1/expense-fund/recharge/request|主管/财务/管理员本人已有活跃备用金账户；不再隐式开户|/expense-fund 开户/用途记录/补充申请/核验/批准/执行|C-supervisor-request, C-finance-own-request, C-concurrent-request, C-rollback-request|
|C-32|GET /api/v1/expense-fund/recharge/requests|沿用原读取菜单、角色及授权仓库范围；本轮未扩大读取字段|/expense-fund 开户/用途记录/补充申请/核验/批准/执行|C-finance-queue|
|C-33|POST /api/v1/expense-fund/recharge/review|verify：独立财务/管理员；approve/reject：独立管理员|/expense-fund 开户/用途记录/补充申请/核验/批准/执行|C-supervisor-approve, C-finance-approve, C-finance-verify, C-admin-approve, C-finance-own-verify, C-finance-B-verify, C-finance-own-approve, C-admin-approve-finance, C-on-behalf-own-verify, C-foreign-request, C-concurrent-verify, C-concurrent-approve, C-linked-employee-self-verify, C-on-behalf-independent-verify, C-on-behalf-independent-approve, C-rollback-verify, C-rollback-approve, C-finance-no-menu, C-finance-no-grants|
|C-34|POST /api/v1/expense-fund/recharge/execute|独立有权限财务；财务本人申请允许独立管理员执行；实际申请人/受益人/员工关联均校验|/expense-fund 开户/用途记录/补充申请/核验/批准/执行|C-execute-unapproved, C-supervisor-execute, C-cross-account-execute, C-finance-execute, C-execute-retry, C-finance-own-pay, C-admin-pay-finance, C-legacy-approved-not-executable, C-linked-employee-self-execute, C-on-behalf-self-pay, C-on-behalf-independent-pay, C-execution-transaction-rollback, C-retry-after-rollback, C-legacy-paid-no-reexecution, C-state-only-no-approval-proof|
|D-35|GET /api/v1/expense-fund/settings|沿用原读取菜单、角色及授权仓库范围；本轮未扩大读取字段|/expense-fund 开户/用途记录/补充申请/核验/批准/执行|静态/相关回归；目标脚本未直测|
|D-36|POST /api/v1/expense-fund/settings|管理员在授权范围内操作；主管、财务拒绝；原菜单鉴权仍保留|/expense-fund 开户/用途记录/补充申请/核验/批准/执行|D-fund-settings-2, D-fund-settings-3, D-fund-settings-4, D-admin-forbidden-unknown, D-admin-forbidden-purchase_approval_threshold, D-admin-forbidden-overtime_monthly_limit, D-admin-forbidden-purchase_duty_separation_v1, D-admin-fund-valid, D-admin-fund-nan|
|C-37|GET /api/v1/expense-fund/balance|沿用原读取菜单、角色及授权仓库范围；本轮未扩大读取字段|/expense-fund 开户/用途记录/补充申请/核验/批准/执行|静态/相关回归；目标脚本未直测|
|C-38|GET /api/v1/expense-fund/alert|沿用原读取菜单、角色及授权仓库范围；本轮未扩大读取字段|/expense-fund 开户/用途记录/补充申请/核验/批准/执行|静态/相关回归；目标脚本未直测|
|E-39|GET /api/v1/reimbursement|沿用原读取菜单、角色及授权仓库范围；本轮未扩大读取字段|/reimbursement 审核明细；备用金付款使用后端 can_fund_pay|静态/相关回归；目标脚本未直测|
|E-40|GET /api/v1/reimbursement/{reimb_id}|沿用原读取菜单、角色及授权仓库范围；本轮未扩大读取字段|/reimbursement 审核明细；备用金付款使用后端 can_fund_pay|C-linked-payment-capability-1, C-linked-payment-capability-2, C-linked-payment-capability-3|
|E-41|POST /api/v1/reimbursement/{reimb_id}/review|非备用金报销沿用原鉴权；只修父子归属和事务；备用金关联批准须独立管理员且有核验证据|/reimbursement 审核明细；备用金付款使用后端 can_fund_pay|E-foreign, E-same-warehouse-other-parent, E-mixed, E-duplicate, E-missing, E-invalid-state, E-valid, E-linked-mixed-reject-atomic, E-linked-valid-admin-approve|
|E-42|POST /api/v1/reimbursement/{reimb_id}/pay|非备用金付款原权限不变；备用金关联须有效管理员批准及独立财务/财务本人申请的独立管理员|/reimbursement 审核明细；备用金付款使用后端 can_fund_pay|C-linked-supervisor-payment, C-linked-forged-header, C-linked-independent-payment, C-linked-repeat-payment|
|E-43|POST /api/v1/reimbursement/{reimb_id}/revoke-payment|停用守卫保持拒绝，不能恢复|/reimbursement 审核明细；备用金付款使用后端 can_fund_pay|E-reversal-still-disabled|
|D-44|GET /api/v1/config/work-schedule|沿用原读取菜单、角色及授权仓库范围；本轮未扩大读取字段|/config-center 只读/管理员保存|静态/相关回归；目标脚本未直测|
|D-45|PUT /api/v1/config/work-schedule|管理员在授权范围内操作；主管、财务拒绝；原菜单鉴权仍保留|/config-center 只读/管理员保存|D-bulk-rule-2, D-bulk-rule-3, D-admin-forged-header-rule|
|A-46|POST /api/v1/employees|管理员在授权范围内操作；主管、财务拒绝；原菜单鉴权仍保留|/employees 新建/绑定/登录字段/离职/删除|A-employee-create-2, A-employee-create-3|
|A-47|PUT /api/v1/employees/{employee_id}|主管/财务保留原业务字段；user_id/employee_no/password 仅管理员；原薪资字段问题不在本轮修复|/employees 新建/绑定/登录字段/离职/删除|A-employee-2-user_id, A-employee-2-employee_no, A-employee-2-password, A-employee-3-user_id, A-employee-3-employee_no, A-employee-3-password|
|A-48|POST /api/v1/employees/{employee_id}/resign|主管/财务保留原员工业务操作，但不改变登录状态；管理员管理登录状态还须通过目标账号角色、全部仓库检查|/employees 新建/绑定/登录字段/离职/删除|A-supervisor-resign-business-only|
|A-49|DELETE /api/v1/employees/{employee_id}|主管/财务保留原员工业务操作，但不改变登录状态；管理员管理登录状态还须通过目标账号角色、全部仓库检查|/employees 新建/绑定/登录字段/离职/删除|A-finance-delete-business-only, A-admin-linked-login-disable|
|A-50|POST /api/v1/employees/bind-existing-accounts|管理员在授权范围内操作；主管、财务拒绝；原菜单鉴权仍保留|/employees 新建/绑定/登录字段/离职/删除|A-bind-2, A-bind-3|
|D-51|PUT /api/v1/overtime/limit|管理员在授权范围内操作；主管、财务拒绝；原菜单鉴权仍保留|配置中心 加班上限|D-ot-2, D-ot-3, D-ot-4|
|D-52|PUT /api/v1/expense-approvals/threshold|管理员在授权范围内操作；主管、财务拒绝；原菜单鉴权仍保留|配置中心费用门槛|D-special-rule-2-/expense-approvals/threshold, D-special-rule-3-/expense-approvals/threshold|

## 同接口的动作拆分

|动作|输入|权限/状态|审计|
|---|---|---|---|
|修改用户名/显示名|username/display_name|用户管理只限管理员及原平台超管规则；员工入口 username 只允许劳工目标|既有账号历史|
|重置他人密码|password|主管/财务拒绝；管理员须授权目标范围；本人改密走独立接口|不记录密码明文|
|启用/停用登录账号|is_active|仅授权管理员，不能用员工离职或删除借权；员工业务状态与账号状态分别处理|账号历史；离职历史 account_disabled 如实记录|
|变更角色|role|主管/财务拒绝；管理员仍保留原“不得改角色”限制；不扩大超管能力|既有账号历史|
|变更仓库|warehouse_id/warehouse_ids|主管/财务拒绝，全部目标仓库须授权；原同级限制保留|既有账号历史|
|变更扩展菜单|extra_permissions|主管/财务拒绝；菜单不能突破硬性角色上限|既有账号历史|
|修改账户名称/币种/账号/期初/状态|账户配置字段；未知字段拒绝|仅授权管理员；已发生流水的删除及币种限制仍在|真实对象仓库、实际变更字段；账号/户名/备注脱敏|
|核验补充申请|action=verify|财务或管理员；本人及代录受益人/关联员工拒绝；pending|recharge_verify 快照，不出款|
|批准补充申请|action=approve|独立管理员；verified+匹配核验证据|recharge_approve 快照，不出款|
|驳回补充申请|action=reject|独立管理员；pending/verified/approved_ready，历史已付不可处理|recharge_reject|
|执行补充拨付|request_id/payment_account_id/receive_date|有效批准后独立执行；重复/并发只产生一次资金效果|recharge_execute+逐笔拨付+支出，同事务|
|批量核验开销|item_ids/action=verify|独立财务/管理员；整批合法 pending，凭证必需|item_verify，不付款|
|批量批准开销|item_ids/action=approve|独立管理员；verified+证据；关联报销不自动付款|item_approve|
|批量驳回开销|item_ids/action=reject|独立管理员；未批准待处理；已付不能借此退款|item_reject；保留既有未付退款口径|
|备用金设置单键写入|key/value|仅 fund_limit、fund_alert_threshold；管理员；其他模块/保留/未知 key 拒绝|既有写日志；不改默认值|
|配置中心批量规则写入|作息字段+overtime_limit|管理员；原字段验证和默认值不变|既有写日志|
|采购职责专用配置|专用版本、request_key、原因|原额外保护、版本与例外机制不变；通用设置不能写|原采购职责审计|
|报销批准/驳回明细|items.item_id/status|整批先校验父子/仓库/重复/状态；任何无效项整批无业务副作用|既有请求日志；合法金额只计当前父单|

不存在的备用金独立账户配置修改/停用/删除路由没有新建；本轮仅收口已有开户、设置及手工开销编辑/作废入口。完整员工薪资字段/模板规则和普通报销付款分工留待后续，不把它们写成已完成或待确认政策。

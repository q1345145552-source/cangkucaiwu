# 没有合法成功响应的注册入口
434条路由均有请求记录，不代表所有分支通过。以下13条没有2xx；不为补覆盖恢复停用功能或擅自增加职责。最终数字以final-coverage-summary.json为准。

|动作|接口|具体原因与后续依赖|
|---|---|---|
|customers.customer_receivables|/api/v1/customers/{customer_id}/receivables|经营报表/客户应收/信用发货旧入口已经停用；完整合法请求也拒绝，历史记录及钱包快照保持。|
|customers.link_customer_receipt|/api/v1/customers/{customer_id}/receipts/link|经营报表/客户应收/信用发货旧入口已经停用；完整合法请求也拒绝，历史记录及钱包快照保持。|
|suppliers.create_category|/api/v1/suppliers/categories|目录disabled；供应商分类新建入口不开放，未恢复旧分类策略。|
|suppliers.ai_evaluate|/api/v1/suppliers/{supplier_id}/ai-evaluation|AI评估注册角色为空且旧处理器只允许超管，各角色实际拒绝；若要启用需用户明确角色与外部服务授权，本轮未访问外部AI。|
|expense_fund.topup_account|/api/v1/expense-fund/accounts/{account_id}/topup|直接拨付已关闭；合法正向走补充申请、核验、管理员批准、独立执行，chain及accounts目标已测。|
|reimbursement.revoke_payment|/api/v1/reimbursement/{reimb_id}/revoke-payment|既有付款撤销停用守卫保持拒绝；不把底层遗留鉴权替身算作真实成功。|
|credit.list_shipments|/api/v1/credit/shipments|经营报表/客户应收/信用发货旧入口已经停用；完整合法请求也拒绝，历史记录及钱包快照保持。|
|credit.create_shipment|/api/v1/credit/{credit_id}/shipment|经营报表/客户应收/信用发货旧入口已经停用；完整合法请求也拒绝，历史记录及钱包快照保持。|
|credit.update_shipment|/api/v1/credit/{credit_id}/shipment/{shipment_id}|经营报表/客户应收/信用发货旧入口已经停用；完整合法请求也拒绝，历史记录及钱包快照保持。|
|credit.void_shipment|/api/v1/credit/{credit_id}/shipment/{shipment_id}/void|经营报表/客户应收/信用发货旧入口已经停用；完整合法请求也拒绝，历史记录及钱包快照保持。|
|reports.operating_report|/api/v1/reports/operations|经营报表/客户应收/信用发货旧入口已经停用；完整合法请求也拒绝，历史记录及钱包快照保持。|
|payroll.revoke_disbursement|/api/v1/payroll/{record_id}/revoke-disbursement|既有付款撤销停用守卫保持拒绝；不把底层遗留鉴权替身算作真实成功。|
|cash_advance.revoke_repayment|/api/v1/cash-advances/repayments/{repayment_id}/revoke|既有付款撤销停用守卫保持拒绝；不把底层遗留鉴权替身算作真实成功。|

from app.core.route_access import ManagementRouter as APIRouter
from app.api.v1 import auth, users, dashboard, customers, warehouses, payment_accounts, suppliers
from app.api.v1 import recharge, incoming, reconciliation, income_expense
from app.api.v1 import expense_fund, reimbursement, payable, credit, market, group_order, reports, cost_funds_debt
from app.api.v1 import upload, settings_api, exchange_rates, employees, clock_in, attendance, overtime, payroll
from app.api.v1 import history, efficiency
from app.api.v1 import config_api
from app.api.v1 import employee_advance
from app.api.v1 import salary_template
from app.api.v1 import deduction_template
from app.api.v1 import employee_deduction
from app.api.v1 import expense_approval
from app.api.v1 import cash_advance
from app.api.v1 import cost_identity
from app.api.v1 import sku_catalog
from app.api.v1 import supplier_quotes
from app.api.v1 import procurement_report

api_router = APIRouter()
api_router.include_router(procurement_report.router,prefix='/supplier-price-report',tags=['采购价差月报'])
api_router.include_router(supplier_quotes.router,prefix='/supplier-quotes',tags=['数量阶梯报价'])
api_router.include_router(sku_catalog.router,prefix='/sku-catalog',tags=['标准SKU目录'])
api_router.include_router(cost_identity.router,prefix='/expense-identities',tags=['费用身份核对'])
api_router.include_router(auth.router, prefix="/auth", tags=["认证"])
api_router.include_router(users.router, prefix="/users", tags=["用户"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["仪表盘"])
api_router.include_router(customers.router, prefix="/customers", tags=["客户档案"])
api_router.include_router(warehouses.router, prefix="/warehouses", tags=["仓库档案"])
api_router.include_router(payment_accounts.router, prefix="/accounts", tags=["收款账户"])
api_router.include_router(suppliers.router, prefix="/suppliers", tags=["供应商"])
api_router.include_router(recharge.router, prefix="/recharge", tags=["充值申报"])
api_router.include_router(incoming.router, prefix="/incoming", tags=["到账流水"])
api_router.include_router(reconciliation.router, prefix="/reconciliation", tags=["对账中心"])
api_router.include_router(income_expense.router, prefix="/income-expense", tags=["运营收支"])
api_router.include_router(expense_fund.router, prefix="/expense-fund", tags=["备用金"])
api_router.include_router(reimbursement.router, prefix="/reimbursement", tags=["报销"])
api_router.include_router(payable.router, prefix="/payable", tags=["应付账款"])
api_router.include_router(credit.router, prefix="/credit", tags=["账期"])
api_router.include_router(market.router, prefix="/market", tags=["商品展示区"])
api_router.include_router(group_order.router, prefix="/group-order", tags=["拼单"])
api_router.include_router(cost_funds_debt.router, prefix="/reports/cost-funds-debt", tags=["成本资金欠款"])
api_router.include_router(reports.router, prefix="/reports", tags=["报表中心"])
api_router.include_router(upload.router, prefix="/upload", tags=["文件上传"])
api_router.include_router(settings_api.router, prefix="/settings", tags=["系统设置"])
api_router.include_router(config_api.router, prefix="/config", tags=["配置中心"])
api_router.include_router(exchange_rates.router, tags=["汇率管理"])
api_router.include_router(employees.router, prefix="/employees", tags=["员工档案"])
api_router.include_router(clock_in.router, prefix="/clock-in", tags=["打卡签到"])
api_router.include_router(attendance.router, prefix="/attendance", tags=["考勤管理"])
api_router.include_router(overtime.router, prefix="/overtime", tags=["加班管理"])
api_router.include_router(payroll.router, prefix="/payroll", tags=["工资管理"])
api_router.include_router(history.router, prefix="/history", tags=["修改历史"])
api_router.include_router(efficiency.router, prefix="/efficiency", tags=["人效管理"])
api_router.include_router(employee_advance.router, prefix="/employee-advances", tags=["员工预支"])
api_router.include_router(salary_template.router, prefix="/salary-templates", tags=["薪资模板"])
api_router.include_router(deduction_template.router, prefix="/deduction-templates", tags=["扣款模板"])
api_router.include_router(employee_deduction.router, prefix="/employee-deductions", tags=["员工扣款"])
api_router.include_router(expense_approval.router, prefix="/expense-approvals", tags=["费用审批"])
api_router.include_router(cash_advance.router, prefix="/cash-advances", tags=["垫款单"])

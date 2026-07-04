from fastapi import APIRouter
from app.api.v1 import auth, users, dashboard, customers, warehouses, payment_accounts, suppliers
from app.api.v1 import recharge, incoming, reconciliation, income_expense
from app.api.v1 import expense_fund, reimbursement, payable, credit, market, group_order, reports
from app.api.v1 import upload, settings_api

api_router = APIRouter()
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
api_router.include_router(income_expense.router, prefix="/income-expense", tags=["收付款管理"])
api_router.include_router(expense_fund.router, prefix="/expense-fund", tags=["备用金"])
api_router.include_router(reimbursement.router, prefix="/reimbursement", tags=["报销"])
api_router.include_router(payable.router, prefix="/payable", tags=["应付账款"])
api_router.include_router(credit.router, prefix="/credit", tags=["账期"])
api_router.include_router(market.router, prefix="/market", tags=["商品展示区"])
api_router.include_router(group_order.router, prefix="/group-order", tags=["拼单"])
api_router.include_router(reports.router, prefix="/reports", tags=["报表中心"])
api_router.include_router(upload.router, prefix="/upload", tags=["文件上传"])
api_router.include_router(settings_api.router, prefix="/settings", tags=["系统设置"])

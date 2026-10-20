"""旧权限轮次的源码保护仍覆盖未改函数；钱包轮次修改的收付函数由端到端测试验证。"""
import ast

WALLET_FUNCTIONS = {
    'validate_manual_money', 'create_income', 'update_income', 'create_expense', 'update_expense',
    'list_expense', 'ledger', 'ledger_export', 'monthly_summary', 'operating_dashboard',
    'dashboard_cockpit', 'dashboard_trends', 'pay_bill', 'execute_plan', 'update_bill',
    'warehouse_summary',
    '_selected_dashboard', 'boss_todos',
    'plan_detail', 'record_repayment', 'list_credit_customers', 'credit_detail', 'list_accounts', 'create_account', 'update_account', 'delete_account', 'create_transfer',
    '_disbursement_funding', 'batch_disburse_payroll', 'disburse_payroll',
}


def without_wallet_contract_changes(source):
    tree = ast.parse(source)
    tree.body = [n for n in tree.body if not isinstance(n, (ast.Import,ast.ImportFrom))
        and not (isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name in WALLET_FUNCTIONS)
        and not (isinstance(n,ast.ClassDef) and n.name in ('RepaymentCreate','TransferRequest'))]
    return ast.unparse(tree)


WALLET_GUARDED_ROUTES = {
    ('POST','/api/v1/accounts/transfers'),
    *[('GET','/api/v1/income-expense'+path) for path in ('/expense','/ledger','/ledger/export','/monthly-summary','/operating-dashboard')],
    ('GET','/api/v1/reports/income-expense'), ('GET','/api/v1/reports/previews'), ('GET','/api/v1/incoming'),
    ('GET','/api/v1/incoming/by-request/{request_key}'),
    ('POST','/api/v1/incoming/{incoming_id}/screenshot'), ('GET','/api/v1/incoming/{incoming_id}/screenshot'),
}

"""Historic business guards exclude separately tested readers and payroll access boundary."""
import ast
from tests.non_labor_test_support import without_non_labor_guard

READERS = {'list_payroll', 'payroll_detail', 'list_advances', 'advance_detail',
    'list_reimbursements', 'get_reimb_detail', 'payment_history', 'reject_labor_management_payroll'}


def without_reference_readers(source):
    source = without_non_labor_guard(source)
    tree = ast.parse(source)
    has_payroll_boundary = any(isinstance(node, ast.AsyncFunctionDef)
        and node.name == 'reject_labor_management_payroll' for node in tree.body)
    tree.body = [node for node in tree.body if not (
        isinstance(node, ast.ImportFrom) and node.module == 'app.services.cash_advance_reference'
        or isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in READERS
    )]
    # Round 16 adds only this router-wide access boundary; older business guards
    # still compare every existing handler and formula without modification.
    for node in tree.body if has_payroll_boundary else []:
        if isinstance(node, ast.ImportFrom) and node.module in ('fastapi', 'app.core.permissions'):
            added_import = 'Request' if node.module == 'fastapi' else 'get_current_user'
            node.names = [name for name in node.names if name.name != added_import]
        if (isinstance(node, ast.Assign) and isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Name) and node.value.func.id == 'APIRouter'):
            node.value.keywords = [kw for kw in node.value.keywords
                if 'reject_labor_management_payroll' not in ast.unparse(kw)]
    return ast.unparse(tree)

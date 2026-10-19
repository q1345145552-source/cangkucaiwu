"""Older-round guards leave the round-15 readers to their dedicated behavior tests."""
import ast

READERS = {'list_payroll', 'payroll_detail', 'list_advances', 'advance_detail',
    'list_reimbursements', 'get_reimb_detail', 'payment_history'}


def without_reference_readers(source):
    tree = ast.parse(source)
    tree.body = [node for node in tree.body if not (
        isinstance(node, ast.ImportFrom) and node.module == 'app.services.cash_advance_reference'
        or isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in READERS
    )]
    return ast.unparse(tree)

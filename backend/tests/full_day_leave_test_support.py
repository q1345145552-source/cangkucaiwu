"""Normalize only round-12 additions when checking older route/formula guards."""
import ast


def before_full_day_guards(source):
    class WithoutFullDay(ast.NodeTransformer):
        def visit_ImportFrom(self, node):
            return None if node.module == 'app.services.full_day_leave' else node

        def visit_If(self, node):
            if isinstance(node.test, ast.Await) and isinstance(node.test.value, ast.Call) and isinstance(node.test.value.func, ast.Name) and node.test.value.func.id == 'approved_full_day_today':
                return None
            if ast.unparse(node.test) == "(lr.duration_type or 'full') == 'full'" and any(isinstance(n, ast.Name) and n.id == 'full_day_clock_warning' for n in ast.walk(node)):
                return None
            return self.generic_visit(node)

        def visit_Assign(self, node):
            if any(isinstance(n, ast.Name) and n.id == 'warning' for n in node.targets):
                return None
            if isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name) and node.value.func.id == 'full_day_net_hours':
                return None
            return self.generic_visit(node)

        def visit_Dict(self, node):
            pairs = [(k, v) for k, v in zip(node.keys, node.values) if not (
                isinstance(k, ast.Constant) and k.value == 'full_day_leave'
                or k is None and isinstance(v, ast.Name) and v.id == 'warning'
            )]
            node.keys, node.values = [k for k, _ in pairs], [v for _, v in pairs]
            return self.generic_visit(node)

        def visit_Call(self, node):
            if isinstance(node.func, ast.Name) and node.func.id == 'full_day_net_hours':
                return self.visit(node.args[1])
            return self.generic_visit(node)
    return ast.unparse(ast.fix_missing_locations(WithoutFullDay().visit(ast.parse(source))))

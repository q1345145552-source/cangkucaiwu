"""Historical business comparisons strip only the separately verified non-labor gate."""
import ast


def without_non_labor_guard(source):
    tree=ast.parse(source)
    tree.body=[node for node in tree.body if not (
        isinstance(node,ast.AsyncFunctionDef) and node.name=='require_non_labor')]
    for node in tree.body:
        if isinstance(node,ast.ImportFrom) and node.module=='app.core.permissions':
            node.names=[n for n in node.names if n.name!='require_non_labor']
        if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):
            for decorator in node.decorator_list:
                if not isinstance(decorator,ast.Call):
                    continue
                for keyword in decorator.keywords:
                    if keyword.arg=='dependencies' and isinstance(keyword.value,ast.List):
                        keyword.value.elts=[d for d in keyword.value.elts
                            if ast.unparse(d)!='Depends(require_non_labor)']
                decorator.keywords=[k for k in decorator.keywords
                    if not (k.arg=='dependencies' and isinstance(k.value,ast.List) and not k.value.elts)]
    return ast.unparse(tree)

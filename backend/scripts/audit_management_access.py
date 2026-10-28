"""Read-only registered-route inventory; no database connection or HTTP writes.

Run from backend: python -m scripts.audit_management_access --output FILE
"""
import argparse
import json
from collections import Counter
from pathlib import Path

from fastapi.routing import APIRoute
from app.main import app
from app.core.permissions import require_non_labor

MANAGEMENT = {'business_management', 'platform_management', 'shared_platform'}
KINDS = MANAGEMENT | {'account_utility', 'employee_self_or_management', 'protected_attachment', 'explicit_action_handler'}


def dependencies(node):
    yield node.call
    for child in node.dependencies:
        yield from dependencies(child)


def permission_labels(calls):
    labels = set()
    for call in calls:
        code = getattr(call, '__code__', None)
        cells = getattr(call, '__closure__', None)
        if not code or not cells:
            continue
        for key, cell in zip(code.co_freevars, cells):
            if key not in ('perm_key', 'perm_keys', 'permissions', 'management'):
                continue
            value = cell.cell_contents
            values = [value] if isinstance(value, str) else value if isinstance(value, (tuple, list, set)) else []
            labels.update(v for v in values if isinstance(v, str))
    return sorted(labels)


def inventory():
    result = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        calls = list(dependencies(route.dependant))
        access = (route.openapi_extra or {}).get('x-access-kind')
        for method in sorted(route.methods):
            result.append({'method': method, 'path': route.path,
                'module': route.endpoint.__module__.rsplit('.', 1)[-1], 'function': route.endpoint.__name__,
                'access': access or 'public_health', 'is_write': method not in ('GET', 'HEAD', 'OPTIONS'),
                'non_labor_guard': require_non_labor in calls,
                'permission_labels': permission_labels(calls),
                'dependencies': sorted(set(getattr(c, '__name__', type(c).__name__) for c in calls)),
                'business_access': '先拒绝劳工，再执行原角色、中文权限和仓库归属检查' if access in MANAGEMENT else
                    '本人及管理共用，按本人身份或管理权限分支检查' if access == 'employee_self_or_management' else
                    '文件身份、仓库及实际业务关联检查' if access == 'protected_attachment' else
                    '登录、本人资料、改密或仅附件会话工具' if access == 'account_utility' else '动作选择或迁移入口，鉴权后由处理函数独立检查动作授权' if access == 'explicit_action_handler' else '首页或健康检查'})
    return sorted(result, key=lambda r: (r['path'], r['method']))


def audit():
    rows = inventory()
    original = json.loads((Path(__file__).parents[1] / 'tests/fixtures/original_labor94.json').read_text())
    indexed = {(r['method'], r['path']): r for r in rows}
    compared = []
    for old in original['routes']:
        current = indexed.get((old['method'], old['path']))
        compared.append({**old, 'current_access': current['access'] if current else None,
            'current_module': current['module'] if current else None,
            'non_labor_guard': bool(current and current['non_labor_guard']),
            'result': '已保护' if current and current['non_labor_guard'] else '待人工核对，禁止自动视为已保护'})
    problems = [r for r in rows if (r['access']=='explicit_action_handler' and 'get_current_user' not in r['dependencies']) or (r['access'] in MANAGEMENT and not r['non_labor_guard']) or
        (r['access'] not in KINDS and (r['method'], r['path']) not in {('GET', '/'), ('GET', '/health')})]
    return {'total_method_paths': len(rows),
        'management_method_paths': sum(r['access'] in MANAGEMENT for r in rows),
        'access_kinds': dict(sorted(Counter(r['access'] for r in rows).items())),
        'management_by_module': dict(sorted(Counter(r['module'] for r in rows if r['access'] in MANAGEMENT).items())),
        'original_baseline': original['baseline'], 'original94_comparison': compared,
        'unprotected_or_unclassified': problems, 'routes': rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    report = audit()
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({k: report[k] for k in ('total_method_paths', 'management_method_paths', 'access_kinds')}, ensure_ascii=False))
    if report['unprotected_or_unclassified'] or any(not r['non_labor_guard'] for r in report['original94_comparison']):
        raise SystemExit('发现未保护或未分类入口，请人工核对')


if __name__ == '__main__':
    main()

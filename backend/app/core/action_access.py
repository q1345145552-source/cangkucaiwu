"""Versioned action grants intersect existing role, object, state and warehouse guards."""
import json
from pathlib import Path
from fastapi import HTTPException
from app.core.menu_registry import MENU_PERMISSIONS, MENU_PERMISSIONS_BY_KEY

VERSION = '@wf-actions:1'
PREFIX = '@wf-actions:'
TIERS = ('view', 'operate', 'approve')
SUPERVISOR_FINANCE_MODULES = {'payroll','salary_templates','deduction_templates','employee_deductions','reports','ledger','incoming','reconciliation','payable','payment_plans','operating','other_income_expense','cash_advances','credit'}
CATALOG = json.loads(Path(__file__).with_name('action_catalog.json').read_text())
ROUTES = {(method, row['path']): row for row in CATALOG['routes'] for method in row['methods']}
LABEL_KEYS = {item.label: item.menu_key for item in MENU_PERMISSIONS}


def grant_id(module, tier):
    return f'{module}:{tier}'


def variants(row):
    return list(row['variants']['values'].values()) if row.get('variants') else [row]


def role_grants(role):
    return {grant_id(module, variant['tier']) for row in CATALOG['routes']
            if row['mode'] == 'business' for variant in variants(row) if role in variant['roles']
            for module in row.get('grant_modules', [row['module_key']])
            if not (role == 'supervisor' and module in SUPERVISOR_FINANCE_MODULES)}


def permission_state(user):
    raw = user.extra_permissions
    if raw is None:
        raw = []
    if not isinstance(raw, list) or any(not isinstance(x, str) for x in raw):
        return {'version': 'invalid', 'grants': set(), 'unknown': [], 'reason': '权限格式无效'}
    markers = [x for x in raw if x.startswith(PREFIX)]
    ceiling = role_grants(user.role)
    if markers:
        grants = set(raw) - {VERSION}
        if markers != [VERSION] or len(raw) != len(set(raw)) or grants - ceiling:
            return {'version': 'invalid', 'grants': set(), 'unknown': sorted(grants - ceiling), 'reason': '未知版本、动作或超出角色上限'}
        return {'version': 1, 'grants': grants, 'unknown': [], 'reason': ''}
    known = {LABEL_KEYS[x] for x in raw if x in LABEL_KEYS}
    grants = {g for g in ceiling if g.rsplit(':', 1)[0] in known}
    return {'version': 'legacy', 'grants': grants, 'unknown': sorted(set(raw) - LABEL_KEYS.keys()), 'reason': '旧菜单保守兼容；未识别值不授予权限'}


def has_module(user, module, tier=None):
    if user.role == 'warehouse_admin':
        return True
    state = permission_state(user)
    if state['version'] == 'invalid':
        return False
    if state['version'] == 'legacy':
        item = MENU_PERMISSIONS_BY_KEY.get(module)
        return bool(item and item.label in (user.extra_permissions or []))
    return any(grant_id(module, lane) in state['grants'] for lane in ((tier,) if tier else TIERS))


def legacy_permission(user, label):
    """Old menu guards remain additional gates; an operate bit is not a view bit."""
    module = LABEL_KEYS.get(label)
    if module == 'sku_catalog' and permission_state(user)['version'] == 1 and has_module(user, 'sku_catalog_manage', 'operate'):
        return True  # Actual catalogue GET still requires sku_catalog:view in enforce_action/read_scope.
    return has_module(user, module) if module else False


def legacy_labels(user):
    if permission_state(user)['version'] == 'legacy':
        return [x for x in (user.extra_permissions or []) if isinstance(x, str) and x in LABEL_KEYS]
    return [item.label for item in MENU_PERMISSIONS if has_module(user, item.menu_key)]


def encode_permissions(role, grants):
    if not isinstance(grants, list) or any(not isinstance(g, str) for g in grants):
        raise HTTPException(400, '动作权限必须是明确的授权列表')
    if len(grants) != len(set(grants)) or set(grants) - role_grants(role):
        raise HTTPException(403, '包含未知动作或超出目标角色上限的权限')
    return [VERSION, *sorted(grants)]


def convert_legacy(user):
    state = permission_state(user)
    if state['version'] == 'invalid':
        raise HTTPException(409, '历史权限格式或版本冲突，请先独立核对')
    return [VERSION, *sorted(state['grants'])], state


def access_description(user):
    state = permission_state(user)
    actions = []
    for row in CATALOG['routes']:
        for variant in variants(row):
            allowed = user.role in variant['roles'] and (user.role in ('warehouse_admin', 'super_admin')
                or any(grant_id(m, variant['tier']) in state['grants'] for m in row.get('grant_modules', [row['module_key']])))
            if allowed:
                actions.append({'id': row['id'], 'module': row['module_key'], 'tier': variant['tier']})
    return {'version': state['version'], 'grants': sorted(state['grants']), 'actions': actions,
            'unknown_legacy_values': state['unknown'], 'compatibility_note': state['reason']}


def is_personal(row, request, user):
    if row['mode'] == 'self':
        return True  # Existing formal binding and actual ownership dependency must still run.
    if row.get('personal_variant') and (request.query_params.get('view') == 'self' or user.role == 'warehouse_labor'):
        return True
    if user.role == 'supervisor' and request.method == 'GET':
        from app.core.round5_access import PERSONAL_FINANCE_READ
        key = (row['module'].rsplit('.', 1)[-1], row['handler'])
        return key in PERSONAL_FINANCE_READ
    return False


async def enforce_action(request, user):
    route = request.scope.get('route')
    row = ROUTES.get((request.method, getattr(route, 'path', '')))
    if row is None:
        raise HTTPException(403, '该业务动作尚未登记，拒绝访问')
    if row['mode'] in ('utility', 'attachment', 'disabled') or is_personal(row, request, user):
        return  # Attachment helpers separately require current object module view grants.
    state = permission_state(user)
    if state['version'] == 'invalid':
        raise HTTPException(403, '权限配置无效，请联系仓库管理员核对')
    if row['mode'] == 'upload':
        if state['version'] == 'legacy':
            return  # Existing upload module and attachment ownership guards still run.
        if any(g.endswith(':operate') for g in state['grants']):
            return
        # A valid personal employee may attach evidence; never grants another object's read.
        from app.core.employee_access import own_employee
        from app.database import async_session_factory
        async with async_session_factory()() as db:
            if await own_employee(db, user) is not None:
                return
        raise HTTPException(403, '没有可使用的上传操作权限或本人身份')
    selected = row
    if row.get('variants'):
        # A role with no permitted variant must be denied before inspecting
        # approval payloads; malformed input cannot precede the role ceiling.
        if not any(user.role in v['roles'] for v in row['variants']['values'].values()):
            message = '无权访问' if user.role == 'warehouse_labor' else '超级管理员请使用各仓库管理员账号操作' if user.role == 'super_admin' else '该动作超出当前角色职责上限'
            raise HTTPException(403, message)
        try:
            body = await request.json()
        except (ValueError, UnicodeDecodeError):
            raise HTTPException(400, '请提供有效的动作参数')
        selected = row['variants']['values'].get(body.get(row['variants']['field'])) if isinstance(body, dict) else None
        if selected is None:
            raise HTTPException(400, '未知动作，不授予默认审批权限')
    if user.role not in selected['roles']:
        message = '该动作超出当前角色职责上限'
        if user.role == 'super_admin':
            message = '超级管理员请使用各仓库管理员账号操作'
        elif user.role == 'warehouse_labor':
            message = '无权访问'
        elif row['id'] == 'clock_in.batch_makeup_clock_in':
            message = '只能由仓库管理员批量补卡'
        elif row['id'] in ('clock_in.list_makeup_batches','clock_in.revoke_makeup_batch'):
            message = '只能由仓库管理员查看或撤销补卡批次'
        elif row['id'] in ('employees.set_max_limit','employees.batch_set_templates'):
            message = '规则及薪资扣款设置只能由仓库管理员修改'
        elif row['id'] == 'suppliers.delete_supplier':
            message = '供应商删除只能由仓库管理员操作'
        elif row['id'] == 'payroll.list_payroll':
            message = '无权查看工资数据'
        raise HTTPException(403, message)
    if user.role in ('warehouse_admin', 'super_admin'):
        return  # Existing administrator object/state limits still execute.
    if state['version'] == 'legacy':
        return  # Legacy menu gate remains, but never bypasses the same hard role ceiling.
    if not any(grant_id(m, selected['tier']) in state['grants'] for m in row.get('grant_modules', [row['module_key']])):
        raise HTTPException(403, {'message': '缺少当前动作授权', 'action': row['id'], 'required_tier': selected['tier']})


def capability_tiers(module):
    """Intersect state-aware hints with current grants; never replaces the write guard."""
    from functools import wraps
    def decorate(function):
        @wraps(function)
        async def guarded(db, user, *args, **kwargs):
            result = await function(db, user, *args, **kwargs)
            if permission_state(user)['version'] == 'legacy':
                return result
            return {key: (value and has_module(user, module, 'approve' if key in
                {'can_approve','can_confirm','can_reject'} else 'operate'))
                if key.startswith('can_') else value for key, value in result.items()}
        return guarded
    return decorate

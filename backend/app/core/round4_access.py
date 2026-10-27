"""Narrow action ceilings for bookkeeping, employment rules and onsite approvals.

These supplement, never replace, each route's menu, object and state checks.
"""
from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel
from fastapi.params import Form as FormParameter
from sqlalchemy import select, event, inspect
from app.core.permissions import Role
from app.core.round2_access import mutation_scope
from app.database import get_db
from app.models.employee import Employee
from app.models.user import User

BOOK_MODULES = {'income_expense', 'incoming', 'reconciliation'}
RULE_MODULES = {'salary_template', 'deduction_template', 'employee_deduction', 'exchange_rates'}
RULE_ACTIONS = {('employees', 'set_max_limit'), ('employees', 'batch_set_templates')}
EXISTING_RULE_ACTIONS = {('config_api','set_work_schedule_settings'), ('overtime','set_overtime_limit'),
    ('expense_fund','update_settings'), ('expense_approval','set_threshold'),
    ('suppliers','set_price_threshold'), ('suppliers','set_approval_threshold'), ('suppliers','set_concentration_threshold')}


def action_policy(module, name, methods):
    if not set(methods) & {'POST', 'PUT', 'PATCH', 'DELETE'}:
        return None
    if module in BOOK_MODULES:
        return 'bookkeeping'
    if module in RULE_MODULES or (module, name) in RULE_ACTIONS:
        return 'rules'
    if (module, name) in EXISTING_RULE_ACTIONS:
        return 'audit'
    if module in {'attendance', 'clock_in', 'overtime', 'employees'}:
        return 'scope'
    return None


def action_guard(policy):
    async def guard(request: Request, user=Depends(mutation_scope), db=Depends(get_db)):
        if user.role == Role.SUPER_ADMIN:
            raise HTTPException(403, '超级管理员请使用各仓库管理员账号操作')
        if policy == 'bookkeeping' and user.role not in (Role.WAREHOUSE_ADMIN, Role.STAFF):
            raise HTTPException(403, '正式记账只能由获授权财务或仓库管理员办理')
        if policy == 'rules' and user.role != Role.WAREHOUSE_ADMIN:
            raise HTTPException(403, '规则及薪资扣款设置只能由仓库管理员修改')
        # Existing handlers using get_wh_ids must respect the selected, verified header.
        if request.headers.get('X-Warehouse-ID') is not None:
            user._warehouse_ids = user._mutation_warehouse_ids
            user._all_warehouse_ids = user._mutation_warehouse_ids
        module = request.scope['route'].endpoint.__module__.rsplit('.', 1)[-1]
        if module == 'employees' and any(isinstance(field.type_, type) and issubclass(field.type_, BaseModel)
                for field in request.scope['route'].dependant.body_params):
            if request.headers.get('content-type') == '':
                raise HTTPException(415, 'Content-Type不能为空，请使用JSON媒体类型')
            # Inspect JSON-model routes regardless of media type. Invalid/non-JSON
            # bodies remain subject to the framework's model validation.
            try:
                body = await request.json()
            except (ValueError, UnicodeDecodeError):
                body = None
            protected = {'daily_wage', 'base_salary', 'salary_template_id', 'deduction_template_id',
                         'bank_account_number', 'bank_name', 'bank_account_holder', 'user_id', 'employee_no', 'password'}
            if isinstance(body, dict) and protected.intersection(body) and user.role != Role.WAREHOUSE_ADMIN:
                raise HTTPException(403, '薪资、扣款、银行及账号字段只能由仓库管理员修改')
        if any(isinstance(field.field_info, FormParameter) for field in request.scope['route'].dependant.body_params):
            allowed = {f.name for f in request.scope['route'].dependant.body_params}
            if set(await request.form()) - allowed:
                raise HTTPException(400, '请求包含不允许的字段')
        tracked = {}
        names = {AUDIT_TABLES[module]} if module in AUDIT_TABLES else set()
        if module == 'employee_deduction':
            names.add('employee_fixed_deductions')
        if module == 'employees':
            names.add('warehouses')
        def capture(session, flush_context, instances):
            for obj in set(session.new) | set(session.dirty) | set(session.deleted):
                if getattr(obj, '__tablename__', None) not in names or id(obj) in tracked:
                    continue
                state = inspect(obj)
                old = {} if obj in session.new else {
                    column.name: (state.attrs[column.name].history.deleted[0]
                        if state.attrs[column.name].history.deleted else getattr(obj, column.name))
                    for column in obj.__table__.columns}
                tracked[id(obj)] = (obj, old, obj in session.deleted)
        event.listen(db.sync_session, 'before_flush', capture)
        try:
            yield user
            await db.flush()
        finally:
            event.remove(db.sync_session, 'before_flush', capture)
        before, after = {}, {}
        for obj, old, deleted in tracked.values():
            key = (obj.__tablename__, obj.id)
            if old: before[key] = old
            if not deleted:
                await db.refresh(obj)
                after[key] = {c.name: getattr(obj, c.name) for c in obj.__table__.columns}
        await audit_changes(db, user, before, after)
    return guard


async def independent_employee(db, user, employee_id, *, related_user_id=None, message="本人事项不能由本人审批，请交独立授权人员处理"):
    """Either formal or attendance alias is enough to deny approval of oneself."""
    employee = await db.get(Employee, employee_id)
    if employee is None:
        raise HTTPException(404, '员工不存在')
    own_ids = set((await db.execute(select(Employee.id).where(Employee.user_id == user.id))).scalars())
    if user.attendance_employee_id:
        own_ids.add(user.attendance_employee_id)
    if employee_id in own_ids or related_user_id == user.id:
        raise HTTPException(403, message)
    # A second login bound to the same employee must not make its other login independent.
    if related_user_id:
        aliases = (await db.execute(select(User).where(User.id == related_user_id))).scalar_one_or_none()
        if aliases and aliases.attendance_employee_id in own_ids:
            raise HTTPException(403, message)
    return employee

AUDIT_TABLES = {
    'salary_template': 'salary_templates', 'deduction_template': 'deduction_templates',
    'employee_deduction': 'employee_deductions', 'employees': 'employees',
    'exchange_rates': 'exchange_rates',
    'config_api':'system_settings', 'overtime':'system_settings', 'expense_fund':'system_settings',
    'suppliers':'system_settings', 'expense_approval':'system_settings',
}

async def audit_changes(db, user, before, after):
    from app.services.data_history import record_history
    from app.services.financial_authorization import digest
    for key in sorted(before.keys() | after.keys()):
        old, new = before.get(key, {}), after.get(key, {})
        changed = sorted(k for k in old.keys() | new.keys() if old.get(k) != new.get(k))
        if not changed:
            continue
        rule_table = key[0] in {'salary_templates','deduction_templates','system_settings','warehouses','exchange_rates'}
        visible = [k for k in changed if rule_table and k not in {'created_at','updated_at'}
            and isinstance(new.get(k, old.get(k)), (str,int,float,bool,type(None)))]
        await record_history(db, module=key[0], record_id=key[1], operator=user,
            operation_type='r04_change', warehouse_id=(new or old).get('warehouse_id', (new or old).get('id') if key[0] == 'warehouses' else None),
            before={'sha256': digest(old), 'rule_values': {k:old.get(k) for k in visible}},
            after={'sha256': digest(new), 'changed_fields': changed, 'rule_values': {k:new.get(k) for k in visible}})

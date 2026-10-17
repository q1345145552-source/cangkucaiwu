"""Advance-only account selection and employee creation; never enables attendance."""
from datetime import datetime, time
from fastapi import HTTPException
from sqlalchemy import select
from app.core.timezone import thai_today
from app.models.employee import Employee
from app.models.user import User
from app.services.attendance_population import employee_account_roles
from app.services.data_history import record_history

MANAGER_ROLES = ('supervisor', 'warehouse_admin')
ROLE_LABELS = {'supervisor': '主管', 'warehouse_admin': '仓库管理员'}


async def manager_employee(db, user, *, lock=False):
    """Reuse live IDs or attendance history, never names. Include inactive archives to avoid duplicates."""
    query = select(Employee).where(Employee.user_id == user.id)
    if lock:
        query = query.with_for_update()
    bound = (await db.execute(query)).scalar_one_or_none()
    candidates = [bound] if bound else []
    if user.attendance_employee_id:
        linked = await db.get(Employee, user.attendance_employee_id)
        if linked is None:
            raise HTTPException(409, '关联员工档案不存在，请先处理员工档案')
        candidates.append(linked)
    if not candidates:
        employees = (await db.execute(select(Employee).where(Employee.warehouse_id == user.warehouse_id))).scalars().all()
        owners, _ = await employee_account_roles(db, employees)
        candidates = [e for e in employees if owners.get(e.id) and owners[e.id].id == user.id]
    unique = {e.id: e for e in candidates}
    if len(unique) > 1:
        raise HTTPException(409, '账号关联的员工档案不一致，请先处理员工档案')
    emp = next(iter(unique.values()), None)
    if emp:
        if emp.user_id not in (None, user.id):
            raise HTTPException(409, '该员工档案已绑定其他账号')
        if emp.warehouse_id != user.warehouse_id:
            raise HTTPException(409, '员工档案不属于该账号所在仓库')
        if emp.is_deleted or emp.status == 'resigned':
            raise HTTPException(400, '该账号的员工档案已离职或删除，请先处理员工档案')
    return emp


async def advance_recipient_options(db, wh_id):
    employees = (await db.execute(select(Employee).where(
        Employee.warehouse_id == wh_id, Employee.is_deleted == False, Employee.status != 'resigned',
    ).order_by(Employee.name, Employee.id))).scalars().all()
    owners, _ = await employee_account_roles(db, employees)
    seen = set()
    items = []
    for emp in employees:
        owner = owners.get(emp.id)
        if owner and owner.warehouse_id != wh_id:
            owner = None
        if owner:
            seen.add(owner.id)
        role = owner.role if owner else 'employee'
        items.append({'value': f'employee:{emp.id}', 'employee_id': emp.id,
                      'user_id': owner.id if owner else None, 'name': emp.name,
                      'employee_no': owner.username if owner else None,
                      'role': role, 'role_label': ROLE_LABELS.get(role, '员工')})
    accounts = (await db.execute(select(User).where(
        User.warehouse_id == wh_id, User.role.in_(MANAGER_ROLES), User.is_active == True,
    ).order_by(User.display_name, User.id))).scalars().all()
    for user in accounts:
        if user.id in seen:
            continue
        try:
            emp = await manager_employee(db, user)
        except HTTPException:
            continue  # Conflicted/deleted archives cannot be bypassed by account selection.
        if emp is not None:
            continue
        items.append({'value': f'user:{user.id}', 'employee_id': None, 'user_id': user.id,
                      'name': user.display_name, 'employee_no': user.username,
                      'role': user.role, 'role_label': ROLE_LABELS[user.role]})
    return items


async def resolve_advance_account(db, user_id, wh_id, operator):
    # Serializes simultaneous submissions for the same account in PostgreSQL.
    user = (await db.execute(select(User).where(
        User.id == user_id, User.warehouse_id == wh_id,
        User.role.in_(MANAGER_ROLES), User.is_active == True,
    ).with_for_update())).scalar_one_or_none()
    if user is None:
        raise HTTPException(404, '预支账号不存在或不属于当前仓库')
    emp = await manager_employee(db, user, lock=True)
    if emp is None:
        emp = Employee(name=user.display_name, position='仓库主管', warehouse_id=user.warehouse_id,
                       status='regular', user_id=user.id, hire_date=datetime.combine(thai_today(), time.min),
                       salary_template_id=None, deduction_template_id=None, created_by=operator.id)
        db.add(emp)
        await db.flush()
        await record_history(db, module='employee', record_id=emp.id, operator=operator,
            operation_type='create', warehouse_id=wh_id, after={
                'name': emp.name, 'employee_no': user.username, 'position': emp.position,
                'warehouse_id': wh_id, 'status': emp.status, 'user_id': user.id,
                'hire_date': emp.hire_date.isoformat(), 'salary_template_id': None,
                'deduction_template_id': None, 'source': 'employee_advances',
            })
    elif emp.user_id is None:
        emp.user_id = user.id
        await db.flush()
    return emp

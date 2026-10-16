"""Resolve account identity for statistics and display, without changing stored payroll."""
from sqlalchemy import select, or_
from app.models.user import User
from app.models.data_change_history import DataChangeHistory


async def employee_account_roles(db, employees):
    if not employees:
        return {}, set()
    warehouses = {e.warehouse_id for e in employees}
    linked_ids = {e.user_id for e in employees if e.user_id}
    users = (await db.execute(select(User).where(or_(
        User.warehouse_id.in_(warehouses), User.id.in_(linked_ids)
    )))).scalars().all()
    by_id = {u.id: u for u in users}
    owners = {}
    # History preserves identity after switching attendance off detaches both live links.
    ids = [u.id for u in users if u.role != 'warehouse_labor']
    if ids:
        history = (await db.execute(select(DataChangeHistory).where(
            DataChangeHistory.module == 'user', DataChangeHistory.record_id.in_(ids)
        ).order_by(DataChangeHistory.id))).scalars().all()
        for row in history:
            for data in (row.before_data, row.after_data):
                eid = (data or {}).get('attendance_employee_id')
                if isinstance(eid, int):
                    owners[eid] = by_id[row.record_id]
    for u in users:
        if u.attendance_employee_id:
            owners[u.attendance_employee_id] = u
    for e in employees:
        if e.user_id in by_id:
            owners[e.id] = by_id[e.user_id]
    supervisors = {e.id for e in employees if e.id in owners and owners[e.id].role == 'supervisor'}
    return owners, supervisors


def includes_efficiency(employee, owner):
    if owner is None or owner.role == 'warehouse_labor':
        return True  # Preserve existing labor and unbound employee behavior.
    return (owner.role == 'supervisor' and owner.attendance_enabled
            and owner.attendance_employee_id == employee.id
            and employee.user_id == owner.id and employee.warehouse_id == owner.warehouse_id)

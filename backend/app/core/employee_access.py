"""Employee self service, deliberately separate from management permissions."""
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.permissions import Role, get_current_user, check_staff_permission_any
from app.database import get_db
from app.models.employee import Employee
from app.core.messages import t, get_request_lang


def attendance_supervisor(user):
    return user.role == Role.SUPERVISOR and bool(user.attendance_enabled)


def employee_view(user):
    return user.role == Role.WAREHOUSE_LABOR or bool(getattr(user, '_employee_view', False))


async def own_employee(db, user):
    """Formal binding first; legacy fallback must be unique, unbound and in the primary warehouse."""
    query = select(Employee).where(Employee.warehouse_id == user.warehouse_id, Employee.is_deleted == False)
    if attendance_supervisor(user):
        return (await db.execute(query.where(Employee.id == user.attendance_employee_id,
            Employee.user_id == user.id))).scalar_one_or_none()
    bound = (await db.execute(query.where(Employee.user_id == user.id))).scalar_one_or_none()
    if bound:
        return bound
    for condition in (Employee.phone == user.username, Employee.name == user.display_name):
        matches = (await db.execute(query.where(Employee.user_id.is_(None), condition))).scalars().all()
        if len(matches) == 1:
            return matches[0]
        if matches:
            return None
    return None


def employee_access(*permissions, self_only=False):
    """Only explicitly registered routes accept view=self; management stays gated."""
    management = check_staff_permission_any(*permissions)

    async def dependency(request: Request, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
        requested = self_only or user.role == Role.WAREHOUSE_LABOR or request.query_params.get('view') == 'self'
        if requested:
            if user.role != Role.WAREHOUSE_LABOR and not attendance_supervisor(user):
                if self_only and permissions:
                    await management(user)
                raise HTTPException(403, '无权限' if self_only else '无此操作权限')
            emp = await own_employee(db, user)
            if not emp:
                raise HTTPException(403, t('employee_not_found_contact_admin', get_request_lang(request)))
            # Personal identity is independent of spoofed selected warehouse or employee query parameters.
            user._employee_view = True
            user._attendance_employee = emp
            user._active_wh_id = emp.warehouse_id
            user._warehouse_ids = [emp.warehouse_id]
            return user
        return await management(user)
    return dependency

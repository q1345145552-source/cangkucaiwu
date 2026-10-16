"""Employee self service, deliberately separate from management permissions."""
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.permissions import Role, get_current_user, check_staff_permission_any
from app.database import get_db
from app.models.employee import Employee


def attendance_supervisor(user):
    return user.role == Role.SUPERVISOR and bool(user.attendance_enabled)


def employee_view(user):
    return user.role == Role.WAREHOUSE_LABOR or bool(getattr(user, '_employee_view', False))


def employee_access(*permissions, self_only=False):
    """Only explicitly registered routes accept view=self; management stays gated."""
    management = check_staff_permission_any(*permissions)

    async def dependency(request: Request, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
        requested = self_only or request.query_params.get('view') == 'self'
        if requested:
            if user.role != Role.WAREHOUSE_LABOR and not attendance_supervisor(user):
                if self_only and permissions:
                    await management(user)
                raise HTTPException(403, '无权限' if self_only else '无此操作权限')
            if attendance_supervisor(user):
                emp = (await db.execute(select(Employee).where(
                    Employee.id == user.attendance_employee_id,
                    Employee.user_id == user.id,
                    Employee.warehouse_id == user.warehouse_id,
                    Employee.is_deleted == False,
                ))).scalar_one_or_none()
                if not emp:
                    raise HTTPException(403, '未关联有效的本人员工档案')
                # Personal identity belongs to its primary warehouse, not the selected management warehouse.
                user._employee_view = True
                user._attendance_employee = emp
                user._active_wh_id = emp.warehouse_id
                user._warehouse_ids = [emp.warehouse_id]
            return user
        return await management(user)
    return dependency

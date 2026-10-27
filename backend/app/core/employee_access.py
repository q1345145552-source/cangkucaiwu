"""Employee self service, deliberately separate from management permissions."""
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.permissions import Role, get_current_user, check_staff_permission_any, get_wh_ids
from app.database import get_db
from app.models.employee import Employee
from app.core.messages import t, get_request_lang


def attendance_supervisor(user):
    return user.role == Role.SUPERVISOR and bool(user.attendance_enabled)


def employee_view(user):
    return user.role == Role.WAREHOUSE_LABOR or bool(getattr(user, '_employee_view', False))


async def own_employee(db, user):
    """Only an unambiguous, active formal binding authorizes personal access."""
    rows = (await db.execute(select(Employee).where(Employee.user_id == user.id,
        Employee.is_deleted == False))).scalars().all()
    if len(rows) != 1:
        return None
    emp = rows[0]
    from app.models.user import User
    from app.models.warehouse import Warehouse
    wh = await db.get(Warehouse, emp.warehouse_id)
    if wh is None or not wh.is_active or emp.warehouse_id not in get_wh_ids(user):
        return None
    conflicts = (await db.execute(select(User.id).where(User.attendance_employee_id == emp.id,
        User.id != user.id, User.is_active == True))).scalars().all()
    if conflicts:
        return None
    if emp.status == 'resigned' or emp.warehouse_id != user.warehouse_id:
        return None
    if user.role == Role.SUPERVISOR and (not user.attendance_enabled or user.attendance_employee_id != emp.id):
        return None
    if user.attendance_employee_id not in (None, emp.id):
        return None
    return emp


def employee_access(*permissions, self_only=False):
    """Only explicitly registered routes accept view=self; management stays gated."""
    management = check_staff_permission_any(*permissions)

    async def dependency(request: Request, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
        requested = self_only or user.role == Role.WAREHOUSE_LABOR or request.query_params.get('view') == 'self'
        if requested:
            if user.role not in (Role.WAREHOUSE_LABOR, Role.SUPERVISOR, Role.STAFF, Role.WAREHOUSE_ADMIN):
                if self_only and permissions:
                    await management(user)
                raise HTTPException(403, '无权限' if self_only else '无此操作权限')
            emp = await own_employee(db, user)
            if not emp:
                raise HTTPException(403, t('employee_not_found_contact_admin', get_request_lang(request)))
            attendance_route = request.url.path.split('/')[3] in ('clock-in', 'attendance', 'overtime')
            if attendance_route and user.role != Role.WAREHOUSE_LABOR and (not user.attendance_enabled or user.attendance_employee_id != emp.id):
                raise HTTPException(403, '请先由管理员开通并关联本人考勤')
            header = request.headers.get('X-Warehouse-ID')
            if header is not None and header != str(emp.warehouse_id):
                raise HTTPException(403, '本人功能只能使用员工所属仓库')
            for field, expected in (('employee_id', emp.id), ('user_id', user.id), ('warehouse_id', emp.warehouse_id)):
                values = request.query_params.getlist(field)
                if any(value != str(expected) for value in values):
                    raise HTTPException(403, '本人功能不能查询其他员工或仓库')
            # Personal identity is independent of spoofed selected warehouse or employee query parameters.
            user._employee_view = True
            user._attendance_employee = emp
            user._active_wh_id = emp.warehouse_id
            user._warehouse_ids = [emp.warehouse_id]
            return user
        return await management(user)
    return dependency

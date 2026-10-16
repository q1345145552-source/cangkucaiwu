"""账号纳入考勤：复用/建立员工档案，不参与工资或考勤计算。"""
from datetime import datetime, time
from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.timezone import thai_today
from app.models.employee import Employee
from app.models.user import User
from app.models.data_change_history import DataChangeHistory
from app.services.data_history import record_history


async def bind_attendance_employee(db: AsyncSession, user: User, operator: User) -> tuple[Employee, bool]:
    """调用方须先锁定账号；双向绑定及历史关联均可复用，不按姓名认人。"""
    if user.warehouse_id is None:
        raise HTTPException(400, "请先为账号设置所属仓库，再开启纳入考勤")

    bound = (await db.execute(select(Employee).where(Employee.user_id == user.id).with_for_update())).scalar_one_or_none()
    employee_id = user.attendance_employee_id
    if employee_id is None and bound is not None:
        employee_id = bound.id
    if employee_id is None:
        # 关闭时两边关系均清空；账号修改日志保留最后一次关联编号。
        previous = (await db.execute(select(DataChangeHistory).where(
            DataChangeHistory.module == "user",
            DataChangeHistory.record_id == user.id,
            or_(
                DataChangeHistory.after_data["attendance_employee_id"].as_integer().is_not(None),
                DataChangeHistory.before_data["attendance_employee_id"].as_integer().is_not(None),
            ),
        ).order_by(DataChangeHistory.id.desc()).limit(1))).scalar_one_or_none()
        if previous is not None:
            employee_id = ((previous.after_data or {}).get("attendance_employee_id")
                           or (previous.before_data or {}).get("attendance_employee_id"))

    employee = None
    if employee_id is not None:
        employee = (await db.execute(select(Employee).where(Employee.id == employee_id).with_for_update())).scalar_one_or_none()
        if employee is None:
            raise HTTPException(400, "关联员工档案不存在，请先在员工档案中处理")
        if employee.user_id is not None and employee.user_id != user.id:
            raise HTTPException(409, "该员工档案已绑定其他账号")
        if employee.warehouse_id != user.warehouse_id:
            raise HTTPException(400, "员工档案不属于该账号所在仓库，请先处理员工档案")
        if employee.is_deleted:
            raise HTTPException(400, "关联员工档案已删除，请先在员工档案中处理")
        if bound is not None and bound.id != employee.id:
            raise HTTPException(409, "账号关联的员工档案不一致，请先处理员工档案")

    created = employee is None
    if created:
        employee = Employee(
            name=user.display_name,
            position="仓库主管",
            warehouse_id=user.warehouse_id,
            status="regular",
            user_id=user.id,
            hire_date=datetime.combine(thai_today(), time.min),
            salary_template_id=None,
            deduction_template_id=None,
            created_by=operator.id,
        )
        db.add(employee)
        await db.flush()
        await record_history(
            db, module="employee", record_id=employee.id, operator=operator,
            operation_type="create", warehouse_id=employee.warehouse_id,
            after={
                "name": employee.name, "employee_no": user.username,
                "position": employee.position, "warehouse_id": employee.warehouse_id,
                "status": employee.status, "user_id": user.id,
                "hire_date": employee.hire_date.isoformat(),
                "salary_template_id": None, "deduction_template_id": None,
                "source": "attendance_enabled",
            },
        )
    elif employee.user_id is None:
        employee.user_id = user.id
        await record_history(
            db, module="employee", record_id=employee.id, operator=operator,
            operation_type="edit", warehouse_id=employee.warehouse_id,
            before={"user_id": None},
            after={"user_id": user.id, "employee_no": user.username, "source": "attendance_enabled"},
        )
    user.attendance_employee_id = employee.id
    return employee, created

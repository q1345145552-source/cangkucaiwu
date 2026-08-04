from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.models.employee import Employee
from app.models.warehouse import Warehouse
from app.models.user import User
from app.core.permissions import get_current_user, get_wh_id, get_wh_ids, Role
from pydantic import BaseModel
from datetime import datetime, date, timedelta
from typing import Optional

router = APIRouter()

class EmployeeCreate(BaseModel):
    name: str
    position: str = "仓库劳工"
    myanmar_id: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    emergency_contact: Optional[str] = None
    hire_date: Optional[str] = None
    status: str = "trial"
    daily_wage: float = 400
    base_salary: float = 12000
    remark: Optional[str] = None

class EmployeeUpdate(BaseModel):
    name: Optional[str] = None
    position: Optional[str] = None
    myanmar_id: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    emergency_contact: Optional[str] = None
    hire_date: Optional[str] = None
    status: Optional[str] = None
    daily_wage: Optional[float] = None
    base_salary: Optional[float] = None
    remark: Optional[str] = None

class ResignRequest(BaseModel):
    reason: str  # voluntary / absconded / fired / contract_end / other
    resignation_date: str  # YYYY-MM-DD
    blacklisted: bool = False
    blacklist_reason: Optional[str] = None
    note: Optional[str] = None
    name: Optional[str] = None
    position: Optional[str] = None
    myanmar_id: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    emergency_contact: Optional[str] = None
    hire_date: Optional[str] = None
    status: Optional[str] = None
    daily_wage: Optional[float] = None
    base_salary: Optional[float] = None
    remark: Optional[str] = None

@router.get("")
async def list_employees(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    status: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPER_ADMIN):
        raise HTTPException(403, "无权限")
    
    wh_ids = get_wh_ids(current_user)
    query = select(Employee)
    count_q = select(func.count(Employee.id))
    if current_user.role != Role.SUPER_ADMIN:
        query = query.where(Employee.warehouse_id.in_(wh_ids))
        count_q = count_q.where(Employee.warehouse_id.in_(wh_ids))
    if status:
        query = query.where(Employee.status == status)
        count_q = count_q.where(Employee.status == status)
    
    total = (await db.execute(count_q)).scalar()
    result = await db.execute(
        query.order_by(Employee.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    emps = result.scalars().all()
    wh_ids_set = {e.warehouse_id for e in emps}
    wh_map = {}
    if wh_ids_set:
        whs = (await db.execute(select(Warehouse).where(Warehouse.id.in_(wh_ids_set)))).scalars().all()
        wh_map = {w.id: w.name for w in whs}
    
    return {
        "data": [{
            "id": e.id, "warehouse_id": e.warehouse_id, "warehouse_name": wh_map.get(e.warehouse_id, ""),
            "name": e.name, "position": e.position, "myanmar_id": e.myanmar_id,
            "address": e.address, "phone": e.phone, "emergency_contact": e.emergency_contact,
            "hire_date": e.hire_date.isoformat()[:10] if e.hire_date else None,
            "status": e.status, "daily_wage": e.daily_wage, "base_salary": e.base_salary,
            "remark": e.remark,
            "resignation_date": e.resignation_date.isoformat() if e.resignation_date else None,
            "resignation_reason": e.resignation_reason,
            "resignation_note": e.resignation_note,
            "blacklisted": e.blacklisted,
            "blacklist_reason": e.blacklist_reason,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        } for e in emps],
        "total": total, "page": page, "page_size": page_size,
    }

@router.post("")
async def create_employee(
    req: EmployeeCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in (Role.WAREHOUSE_ADMIN,):
        raise HTTPException(403, "只有仓库管理员可以创建员工")
    
    wh_id = get_wh_id(current_user)
    if not wh_id:
        raise HTTPException(400, "请先选择仓库")
    
    # Check max_employees limit
    wh = (await db.execute(select(Warehouse).where(Warehouse.id == wh_id))).scalar_one_or_none()
    if wh and wh.max_employees:
        # Count active (non-resigned) employees
        active_count = (await db.execute(
            select(func.count(Employee.id)).where(
                Employee.warehouse_id == wh_id,
                Employee.status != "resigned",
            )
        )).scalar()
        if active_count and active_count >= wh.max_employees:
            raise HTTPException(400, f"员工人数已达上限 ({wh.max_employees}人)，无法新增")
    
    hire_date = None
    if req.hire_date:
        try:
            hire_date = datetime.fromisoformat(req.hire_date)
        except:
            pass
    
    e = Employee(
        warehouse_id=wh_id, name=req.name, position=req.position,
        myanmar_id=req.myanmar_id, address=req.address, phone=req.phone,
        emergency_contact=req.emergency_contact, hire_date=hire_date,
        status=req.status, daily_wage=req.daily_wage, base_salary=req.base_salary,
        remark=req.remark, created_by=current_user.id,
    )
    db.add(e)
    await db.flush()
    return {"id": e.id, "message": "员工创建成功"}

@router.put("/{employee_id}")
async def update_employee(
    employee_id: int,
    req: EmployeeUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in (Role.WAREHOUSE_ADMIN,):
        raise HTTPException(403, "只有仓库管理员可以编辑员工")
    
    e = (await db.execute(select(Employee).where(Employee.id == employee_id))).scalar_one_or_none()
    if not e:
        raise HTTPException(404, "员工不存在")
    
    wh_ids = get_wh_ids(current_user)
    if e.warehouse_id not in wh_ids:
        raise HTTPException(403, "只能编辑自己仓库的员工")
    
    updates = req.model_dump(exclude_unset=True)
    if "hire_date" in updates and updates["hire_date"] is not None:
        try:
            updates["hire_date"] = datetime.fromisoformat(updates["hire_date"])
        except:
            del updates["hire_date"]
    
    for k, v in updates.items():
        setattr(e, k, v)
    await db.flush()
    return {"message": "更新成功"}

@router.post("/{employee_id}/resign")
async def resign_employee(
    employee_id: int,
    req: ResignRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in (Role.WAREHOUSE_ADMIN,):
        raise HTTPException(403, "只有仓库管理员可以操作")
    
    e = (await db.execute(select(Employee).where(Employee.id == employee_id))).scalar_one_or_none()
    if not e:
        raise HTTPException(404, "员工不存在")
    
    wh_ids = get_wh_ids(current_user)
    if e.warehouse_id not in wh_ids:
        raise HTTPException(403, "只能操作自己仓库的员工")
    
    # Parse resignation date
    try:
        resign_dt = datetime.strptime(req.resignation_date, "%Y-%m-%d").date()
    except:
        raise HTTPException(400, "日期格式错误，应为 YYYY-MM-DD")

    # Capture original status for payroll calculation
    emp_original_status = e.status

    # Update employee
    e.status = "resigned"
    e.resignation_date = resign_dt
    e.resignation_reason = req.reason
    e.resignation_note = req.note
    if req.blacklisted:
        e.blacklisted = True
        e.blacklist_reason = req.blacklist_reason or "被辞退"

    # Disable linked user account
    linked_user = await _find_linked_user(db, e)
    if linked_user:
        linked_user.is_active = False

    await db.flush()

    # Auto-settle current month payroll
    payroll_msg = ""
    try:
        period = resign_dt.strftime("%Y-%m")
        from app.models.payroll import PayrollRecord
        from app.models.clock_in_records import ClockInRecord
        from app.models.attendance import LeaveRequest, RestDay, Absence
        from app.models.overtime import OvertimeAssignment, OvertimeTask
        import calendar
        import json

        # Check if already calculated
        existing = (await db.execute(
            select(PayrollRecord).where(
                PayrollRecord.employee_id == employee_id,
                PayrollRecord.period == period,
            )
        )).scalar_one_or_none()
        if existing:
            payroll_msg = f"，{period}工资已存在(ID:{existing.id})"
        else:
            # Calculate from month start to resignation date
            month_start = date(resign_dt.year, resign_dt.month, 1)
            _, total_days = calendar.monthrange(resign_dt.year, resign_dt.month)
            month_end = date(resign_dt.year, resign_dt.month, total_days)

            # Get linked user for clock-in matching
            uid = linked_user.id if linked_user else None
            attendance_days = 0
            late_penalty_total = 0
            leave_days_count = 0
            rest_days_count = 0
            absence_days_count = 0

            if uid:
                clock_records = (await db.execute(
                    select(ClockInRecord).where(
                        ClockInRecord.user_id == uid,
                        ClockInRecord.clock_date >= month_start,
                        ClockInRecord.clock_date <= resign_dt,
                    ).order_by(ClockInRecord.clock_date, ClockInRecord.session)
                )).scalars().all()

                clock_by_date = {}
                for cr in clock_records:
                    k = cr.clock_date
                    if k not in clock_by_date:
                        clock_by_date[k] = set()
                    clock_by_date[k].add(cr.session)

                # Fetch leave/rest/absences
                leaves = (await db.execute(
                    select(LeaveRequest).where(
                        LeaveRequest.employee_id == employee_id,
                        LeaveRequest.leave_date >= month_start,
                        LeaveRequest.leave_date <= resign_dt,
                        LeaveRequest.status == "approved",
                    )
                )).scalars().all()
                leave_set = {lv.leave_date for lv in leaves}

                rests = (await db.execute(
                    select(RestDay).where(
                        RestDay.employee_id == employee_id,
                        RestDay.rest_date >= month_start,
                        RestDay.rest_date <= resign_dt,
                    )
                )).scalars().all()
                rest_set = {r.rest_date for r in rests}

                absences = (await db.execute(
                    select(Absence).where(
                        Absence.employee_id == employee_id,
                        Absence.absence_date >= month_start,
                        Absence.absence_date <= resign_dt,
                    )
                )).scalars().all()
                absence_set = {a.absence_date for a in absences}

                # Count days
                current = month_start
                while current <= resign_dt:
                    if current in rest_set:
                        rest_days_count += 1
                    elif current in leave_set:
                        leave_days_count += 1
                    elif current in absence_set:
                        absence_days_count += 1
                    elif current in clock_by_date:
                        if len(clock_by_date[current]) == 4:
                            attendance_days += 1
                        elif len(clock_by_date[current]) > 0:
                            attendance_days += 1
                    current += timedelta(days=1)

                # Sum late penalties
                late_penalty_total = sum(
                    cr.penalty_amount or 0
                    for cr in clock_records
                )

            # Overtime
            ot_amount = 0
            ot_hours = 0
            if uid:
                from sqlalchemy import func as safunc
                ot_row = (await db.execute(
                    select(
                        safunc.sum(OvertimeAssignment.earned_amount),
                        safunc.sum(OvertimeTask.hours),
                    )
                    .join(OvertimeTask, OvertimeTask.id == OvertimeAssignment.overtime_id)
                    .where(
                        OvertimeAssignment.user_id == uid,
                        OvertimeAssignment.confirmed == True,
                        OvertimeTask.date >= month_start,
                        OvertimeTask.date <= resign_dt,
                    )
                )).first()
                ot_amount = ot_row[0] or 0
                ot_hours = ot_row[1] or 0

            # Calculate base pay (capture original status before it was set to 'resigned')
            emp_status_label = emp_original_status
            if emp_status_label == "trial":
                base_pay = (e.daily_wage or 400) * attendance_days
                leave_deduction = (e.daily_wage or 400) * leave_days_count
                absence_deduction = (e.daily_wage or 400) * absence_days_count
            else:
                adjusted_days = total_days - 2
                if adjusted_days <= 0:
                    adjusted_days = total_days
                daily_rate = (e.base_salary or 12000) / adjusted_days
                base_pay = round(daily_rate * attendance_days, 2)
                leave_deduction = round(daily_rate * leave_days_count, 2)
                absence_deduction = round(daily_rate * absence_days_count, 2)

            total_deductions = late_penalty_total + leave_deduction + absence_deduction
            gross_pay = base_pay + ot_amount
            net_pay = round(gross_pay - total_deductions, 2)

            detail_data = {
                "attendance_days": attendance_days,
                "leave_days": leave_days_count,
                "rest_days": rest_days_count,
                "absence_days": absence_days_count,
                "late_penalty": late_penalty_total,
                "leave_deduction": round(leave_deduction, 2),
                "absence_deduction": round(absence_deduction, 2),
                "overtime_hours": round(ot_hours, 1),
                "overtime_pay": round(ot_amount, 2),
                "settlement_note": "离职结算",
            }

            record = PayrollRecord(
                warehouse_id=e.warehouse_id,
                employee_id=employee_id,
                period=period,
                status="pending",
                total_days_in_month=total_days,
                attendance_days=attendance_days,
                leave_days=leave_days_count,
                rest_days=rest_days_count,
                absence_days=absence_days_count,
                employee_status=emp_status_label,
                daily_wage=e.daily_wage or 400,
                base_salary=e.base_salary or 12000,
                base_pay=round(base_pay, 2),
                overtime_pay=round(ot_amount, 2),
                overtime_hours=round(ot_hours, 1),
                late_penalty=round(late_penalty_total, 2),
                leave_deduction=round(leave_deduction, 2),
                absence_deduction=round(absence_deduction, 2),
                gross_pay=round(gross_pay, 2),
                total_deductions=round(total_deductions, 2),
                net_pay=net_pay,
                detail=json.dumps(detail_data, ensure_ascii=False),
            )
            db.add(record)
            await db.flush()
            payroll_msg = f"，已生成离职结算工资单(ID:{record.id}，实发{net_pay:.0f}泰铢)"

    except Exception as ex:
        payroll_msg = f"，工资结算失败: {str(ex)}"

    reason_cn = {
        "voluntary": "正常离职", "absconded": "自离",
        "fired": "被辞退", "contract_end": "合同到期", "other": "其他"
    }

    return {
        "message": f"已将{e.name}标记为离职（{reason_cn.get(req.reason, req.reason)}）{payroll_msg}",
        "employee_id": e.id,
        "blacklisted": e.blacklisted,
    }


async def _find_linked_user(db: AsyncSession, emp: Employee):
    """Find linked user account for an employee"""
    user = (await db.execute(
        select(User).where(
            User.display_name == emp.name,
            User.role == "warehouse_labor",
            User.is_active == True,
        )
    )).scalar_one_or_none()
    if not user and emp.phone:
        user = (await db.execute(
            select(User).where(
                User.username == emp.phone,
                User.role == "warehouse_labor",
            )
        )).scalar_one_or_none()
    return user


@router.get("/max-limit")
async def get_max_limit(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in (Role.WAREHOUSE_ADMIN,):
        raise HTTPException(403, "无权限")
    wh_id = get_wh_id(current_user)
    if not wh_id:
        return {"max_employees": 50, "current_count": 0}
    wh = (await db.execute(select(Warehouse).where(Warehouse.id == wh_id))).scalar_one_or_none()
    max_val = wh.max_employees if wh and wh.max_employees else 50
    active_count = (await db.execute(
        select(func.count(Employee.id)).where(
            Employee.warehouse_id == wh_id, Employee.status != "resigned"
        )
    )).scalar()
    return {"max_employees": max_val, "current_count": active_count or 0}

@router.put("/max-limit")
async def set_max_limit(
    max_employees: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in (Role.WAREHOUSE_ADMIN,):
        raise HTTPException(403, "无权限")
    wh_id = get_wh_id(current_user)
    if not wh_id:
        raise HTTPException(400, "请先选择仓库")
    wh = (await db.execute(select(Warehouse).where(Warehouse.id == wh_id))).scalar_one_or_none()
    if not wh:
        raise HTTPException(404, "仓库不存在")
    wh.max_employees = max_employees
    await db.flush()
    return {"message": f"人数上限已设为 {max_employees}", "max_employees": max_employees}

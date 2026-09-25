"""系统设置：操作日志 + 数据备份"""
from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text as sa_text
from pydantic import BaseModel
from app.core.timezone import thai_now, thai_today
from datetime import datetime
from app.database import get_db
from app.models.audit_log import AuditLog
from app.models.expense_fund import SystemSetting
from app.models.user import User
from app.core.permissions import get_current_user, get_wh_id, Role
from app.services.schedule import get_schedule, parse_hhmm, FIELD_TO_KEY
import io
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment

router = APIRouter()


class BossContactSet(BaseModel):
    name: str = ""
    phone: str = ""


@router.get("/boss-contact")
async def get_boss_contact(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """读取老板联系方式（称呼 + 电话），用于采购单 PDF。"""
    if current_user.role not in (Role.SUPER_ADMIN, Role.WAREHOUSE_ADMIN):
        raise HTTPException(403, "无权限")
    rows = (await db.execute(
        select(SystemSetting).where(
            SystemSetting.warehouse_id == 0,
            SystemSetting.key.in_(["boss_contact_name", "boss_contact_phone"]),
        )
    )).scalars().all()
    m = {s.key: s.value for s in rows}
    return {"name": m.get("boss_contact_name") or "", "phone": m.get("boss_contact_phone") or ""}


@router.put("/boss-contact")
async def set_boss_contact(req: BossContactSet, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """保存老板联系方式（称呼 + 电话）。"""
    if current_user.role not in (Role.SUPER_ADMIN, Role.WAREHOUSE_ADMIN):
        raise HTTPException(403, "无权限")
    name = (req.name or "").strip()
    phone = (req.phone or "").strip()
    for key, val in (("boss_contact_name", name), ("boss_contact_phone", phone)):
        setting = (await db.execute(
            select(SystemSetting).where(SystemSetting.warehouse_id == 0, SystemSetting.key == key)
        )).scalar_one_or_none()
        if setting:
            setting.value = val
        else:
            db.add(SystemSetting(warehouse_id=0, key=key, value=val, updated_by=current_user.id))
    await db.flush()
    return {"message": "老板联系方式已保存", "name": name, "phone": phone}

class ScheduleSet(BaseModel):
    morning_start: str = "09:00"
    noon_break_start: str = "12:00"
    noon_break_end: str = "13:00"
    afternoon_end: str = "18:00"


SCHEDULE_FIELD_LABELS = {
    "morning_start": "早上上班时间",
    "noon_break_start": "中午休息开始",
    "noon_break_end": "中午休息结束",
    "afternoon_end": "下午下班时间",
}


@router.get("/schedule")
async def get_schedule_settings(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """读取仓库排班设置。管理员可编辑，主管只读；员工/劳工/超级管理员不可见。"""
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
        raise HTTPException(403, "无权限")
    wh_id = get_wh_id(current_user)
    sched = await get_schedule(db, wh_id)
    return {**sched, "editable": current_user.role == Role.WAREHOUSE_ADMIN, "warehouse_id": wh_id}


@router.put("/schedule")
async def set_schedule_settings(req: ScheduleSet, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """保存仓库排班设置（仅仓库管理员）。校验时间顺序：上班 < 午休开始 < 午休结束 < 下班。"""
    if current_user.role != Role.WAREHOUSE_ADMIN:
        raise HTTPException(403, "只有仓库管理员可以修改排班")
    wh_id = get_wh_id(current_user)
    if not wh_id:
        raise HTTPException(400, "请先选择仓库")

    raw = {
        "morning_start": (req.morning_start or "").strip(),
        "noon_break_start": (req.noon_break_start or "").strip(),
        "noon_break_end": (req.noon_break_end or "").strip(),
        "afternoon_end": (req.afternoon_end or "").strip(),
    }
    parsed = {}
    for field, val in raw.items():
        t = parse_hhmm(val)
        if not t:
            raise HTTPException(400, f"时间格式错误：{SCHEDULE_FIELD_LABELS[field]}")
        parsed[field] = t
    if not (parsed["morning_start"] < parsed["noon_break_start"] < parsed["noon_break_end"] < parsed["afternoon_end"]):
        raise HTTPException(400, "时间顺序不正确：上班 < 午休开始 < 午休结束 < 下班")

    for field, key in FIELD_TO_KEY.items():
        val_str = parsed[field].strftime("%H:%M")
        row = (await db.execute(
            select(SystemSetting).where(SystemSetting.warehouse_id == wh_id, SystemSetting.key == key)
        )).scalar_one_or_none()
        if row:
            row.value = val_str
            row.updated_by = current_user.id
            row.updated_at = thai_now()
        else:
            db.add(SystemSetting(warehouse_id=wh_id, key=key, value=val_str, updated_by=current_user.id))
    await db.flush()
    return {"message": "排班设置已保存", **{f: parsed[f].strftime("%H:%M") for f in FIELD_TO_KEY}}


@router.get("/logs")
async def operation_logs(
    page: int = 1, page_size: int = 20,
    user_id: int = None, action_type: str = None, date: str = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role != Role.SUPER_ADMIN:
        return {"data": [], "total": 0, "message": "仅超级管理员可查看操作日志"}
    query = select(AuditLog); count_q = select(func.count(AuditLog.id))
    if user_id: query = query.where(AuditLog.user_id == user_id); count_q = count_q.where(AuditLog.user_id == user_id)
    if action_type: query = query.where(AuditLog.action_type == action_type); count_q = count_q.where(AuditLog.action_type == action_type)
    if date: query = query.where(func.date(AuditLog.created_at) == date); count_q = count_q.where(func.date(AuditLog.created_at) == date)
    total = (await db.execute(count_q)).scalar()
    result = await db.execute(query.order_by(AuditLog.created_at.desc()).offset((page-1)*page_size).limit(page_size))
    logs = result.scalars().all()
    uid_map = {}
    uids = {l.user_id for l in logs if l.user_id}
    if uids:
        users = (await db.execute(select(User).where(User.id.in_(uids)))).scalars().all()
        uid_map = {u.id: u.display_name for u in users}
    return {"data": [{
        "id": l.id, "user_name": uid_map.get(l.user_id, ""),
        "action_type": l.action_type, "module": l.module, "target_id": l.target_id,
        "created_at": l.created_at.isoformat() if l.created_at else None,
    } for l in logs], "total": total, "page": page, "page_size": page_size}

@router.post("/backup")
async def backup_all_data(current_user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    if current_user.role != Role.SUPER_ADMIN:
        return {"error": "仅超级管理员可操作"}
    wb = Workbook()
    tables = [
        ("users", "id,username,display_name,role,warehouse_id,is_active,created_at"),
        ("warehouses", "id,name,code,is_active,created_at"),
        ("customers", "id,warehouse_id,customer_code,company_name,contact_person,credit_status,credit_limit"),
        ("payment_accounts", "id,warehouse_id,account_name,account_type,account_number,opening_balance"),
        ("suppliers", "id,name,contact_person,contact_info"),
        ("recharge_declarations", "id,warehouse_id,customer_id,declare_date,amount,currency,match_status"),
        ("incoming_flows", "id,warehouse_id,received_date,amount,currency,payer_name,match_status"),
        ("reconciliation_results", "id,warehouse_id,reconciliation_month,match_status,amount_diff"),
        ("income_records", "id,warehouse_id,amount,currency,income_date"),
        ("expense_records", "id,warehouse_id,amount,currency,expense_date"),
        ("expense_funds", "id,warehouse_id,employee_id,amount,purpose,status,remaining_balance"),
        ("reimbursements", "id,warehouse_id,employee_id,total_amount,currency,status"),
        ("payable_bills", "id,warehouse_id,supplier_id,bill_number,due_date,amount,paid_amount,status"),
        ("credit_customers", "id,warehouse_id,customer_id,credit_limit,current_debt,overdue_days,status"),
        ("market_items", "id,warehouse_id,name,quantity,price,status"),
        ("group_orders", "id,warehouse_id,item_name,target_quantity,target_price,status"),
    ]
    hf = PatternFill(start_color="2563EB", end_color="2563EB", fill_type="solid")
    hfont = Font(bold=True, color="FFFFFF")
    for tname, cols in tables:
        ws = wb.create_sheet(title=tname[:31])
        col_list = cols.split(",")
        for c, col in enumerate(col_list, 1):
            cell = ws.cell(row=1, column=c, value=col.strip())
            cell.font = hfont; cell.fill = hf
        try:
            result = await db.execute(sa_text(f"SELECT {cols} FROM {tname} LIMIT 5000"))
            rows = result.all()
            for r, row in enumerate(rows, 2):
                for c, val in enumerate(row, 1):
                    ws.cell(row=r, column=c, value=str(val)[:1000] if val is not None else "")
        except Exception:
            pass
    if "Sheet" in wb.sheetnames:
        del wb["Sheet"]
    output = io.BytesIO(); wb.save(output); output.seek(0)
    return StreamingResponse(output, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            headers={"Content-Disposition": f"attachment; filename=backup_{thai_now().strftime('%Y%m%d')}.xlsx"})

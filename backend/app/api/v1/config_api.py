"""配置中心：仓库作息 + 审批门槛（本轮审批门槛仅占位）。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from app.database import get_db
from app.models.user import User
from app.models.expense_fund import SystemSetting
from app.core.permissions import get_current_user, get_wh_id, Role
from app.core.timezone import thai_now
from app.services.schedule import (
    get_work_schedule, parse_hhmm, WORK_TIME_FIELDS, ORDER_FIELDS, OVERTIME_LIMIT_KEY,
)

router = APIRouter()

FIELD_LABELS = {
    "morning_start": "早上上班时间",
    "late_half": "迟到半小时红线",
    "late_one": "迟到1小时红线",
    "noon_break_start": "中午休息开始",
    "noon_break_end": "中午休息结束",
    "early_one": "早退1小时红线",
    "early_half": "早退半小时红线",
    "afternoon_end": "下午下班时间",
}


class WorkScheduleSet(BaseModel):
    morning_start: str
    late_half: str
    late_one: str
    noon_break_start: str
    noon_break_end: str
    early_one: str
    early_half: str
    afternoon_end: str
    overtime_limit: float = 50


@router.get("/work-schedule")
async def get_work_schedule_settings(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """读取仓库作息。管理员可编辑，主管只读；员工/劳工/超级管理员不可见。"""
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
        raise HTTPException(403, "无权限")
    wh_id = get_wh_id(current_user)
    sched = await get_work_schedule(db, wh_id)
    return {**sched, "editable": current_user.role == Role.WAREHOUSE_ADMIN, "warehouse_id": wh_id}


@router.put("/work-schedule")
async def set_work_schedule_settings(req: WorkScheduleSet, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """保存仓库作息（仅仓库管理员）。校验时间顺序：上班 < 迟到半小时 < 迟到1小时 < 午休开始 < 午休结束 < 早退1小时 < 早退半小时 < 下班。"""
    if current_user.role != Role.WAREHOUSE_ADMIN:
        raise HTTPException(403, "只有仓库管理员可以修改作息")
    wh_id = get_wh_id(current_user)
    if not wh_id:
        raise HTTPException(400, "请先选择仓库")

    raw = {field: (getattr(req, field) or "").strip() for field in ORDER_FIELDS}
    parsed = {}
    for field in ORDER_FIELDS:
        t = parse_hhmm(raw[field])
        if not t:
            raise HTTPException(400, f"时间格式错误：{FIELD_LABELS[field]}")
        parsed[field] = t
    for i in range(len(ORDER_FIELDS) - 1):
        if not (parsed[ORDER_FIELDS[i]] < parsed[ORDER_FIELDS[i + 1]]):
            raise HTTPException(400, "时间顺序不对")
    if req.overtime_limit is None or req.overtime_limit < 0:
        raise HTTPException(400, "加班月度上限不能为负数")

    # 保存 8 个时间点
    for field in ORDER_FIELDS:
        key = WORK_TIME_FIELDS[field][0]
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
    # 保存加班上限
    ot_val = str(req.overtime_limit)
    row = (await db.execute(
        select(SystemSetting).where(SystemSetting.warehouse_id == wh_id, SystemSetting.key == OVERTIME_LIMIT_KEY)
    )).scalar_one_or_none()
    if row:
        row.value = ot_val
        row.updated_by = current_user.id
        row.updated_at = thai_now()
    else:
        db.add(SystemSetting(warehouse_id=wh_id, key=OVERTIME_LIMIT_KEY, value=ot_val, updated_by=current_user.id))

    await db.flush()
    return {"message": "作息设置已保存", **{f: parsed[f].strftime("%H:%M") for f in ORDER_FIELDS}, "overtime_limit": req.overtime_limit}

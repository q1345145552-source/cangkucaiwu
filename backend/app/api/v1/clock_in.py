from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.models.user import User
from app.core.permissions import get_current_user, get_wh_id, Role
from pydantic import BaseModel
from datetime import datetime, date

router = APIRouter()

# Simple in-memory approach: store clock-in time in a JSON column on user
# But to keep it simple without modifying User model, we'll create a dedicated clock-in table

class ClockInRequest(BaseModel):
    remark: str | None = None

# Use a simple approach: store clock-in records as a feature that works
# We'll store it in a lightweight way using the database

def _get_clock_in_table():
    from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Date
    from app.database import Base
    from sqlalchemy.sql import func
    
    class ClockInRecord(Base):
        __tablename__ = "clock_in_records"
        id = Column(Integer, primary_key=True, index=True)
        user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
        warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=True)
        clock_date = Column(Date, nullable=False, index=True)
        clocked_in_at = Column(DateTime(timezone=True), server_default=func.now())
    
    return ClockInRecord

ClockInRecord = _get_clock_in_table()

@router.post("")
async def clock_in(
    req: ClockInRequest = ClockInRequest(),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in (Role.WAREHOUSE_LABOR,):
        raise HTTPException(403, "只有仓库劳工可以使用打卡功能")
    
    today = date.today()
    
    # Check if already clocked in today
    existing = (await db.execute(
        select(ClockInRecord).where(
            ClockInRecord.user_id == current_user.id,
            ClockInRecord.clock_date == today,
        )
    )).scalar_one_or_none()
    
    if existing:
        return {"message": "今日已打卡", "clocked_in_at": existing.clocked_in_at.isoformat()}
    
    wh_id = get_wh_id(current_user)
    record = ClockInRecord(
        user_id=current_user.id,
        warehouse_id=wh_id,
        clock_date=today,
    )
    db.add(record)
    await db.flush()
    return {"message": "打卡成功", "clocked_in_at": record.clocked_in_at.isoformat()}

@router.get("/today")
async def get_today(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in (Role.WAREHOUSE_LABOR,):
        raise HTTPException(403, "无权限")
    
    today = date.today()
    record = (await db.execute(
        select(ClockInRecord).where(
            ClockInRecord.user_id == current_user.id,
            ClockInRecord.clock_date == today,
        )
    )).scalar_one_or_none()
    
    if record:
        return {"clocked_in": True, "clocked_in_at": record.clocked_in_at.isoformat()}
    return {"clocked_in": False, "clocked_in_at": None}

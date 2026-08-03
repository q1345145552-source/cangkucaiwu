from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.models.user import User
from app.core.permissions import get_current_user, get_wh_id, Role
from datetime import datetime, date, time
import os, uuid, base64

router = APIRouter()

UPLOAD_DIR = "/app/uploads"

# Session constants
SESSIONS = {
    1: {"label": "早上上班", "time": time(9, 0)},
    2: {"label": "中午休息结束", "time": time(12, 0)},
    3: {"label": "下午上班", "time": time(13, 0)},
    4: {"label": "下午下班", "time": time(18, 0)},
}

def _get_clock_in_table():
    from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Date, Float
    from app.database import Base
    from sqlalchemy.sql import func as sqla_func

    class ClockInRecord(Base):
        __tablename__ = "clock_in_records"
        id = Column(Integer, primary_key=True, index=True)
        user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
        warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=True)
        clock_date = Column(Date, nullable=False, index=True)
        session = Column(Integer, nullable=False, comment="1-4 四个时段")
        clocked_in_at = Column(DateTime(timezone=True), server_default=sqla_func.now())
        photo_path = Column(String(500), nullable=True, comment="打卡照片路径")
        status = Column(String(20), default="normal", comment="normal/late_half/late_one/missed")
        penalty_amount = Column(Float, default=0, comment="迟到扣款金额(泰铢)")
        remark = Column(String(200), nullable=True)

    return ClockInRecord

ClockInRecord = _get_clock_in_table()


def _get_penalty(session: int, clocked_at: datetime) -> dict:
    """Calculate late penalty for session 1 (morning check-in)"""
    if session != 1:
        return {"status": "normal", "penalty_amount": 0}
    t = clocked_at.time()
    if t <= time(9, 5):
        return {"status": "normal", "penalty_amount": 0}
    elif t <= time(9, 30):
        return {"status": "late_half", "penalty_amount": 200}  # 扣半小时工钱 ≈ 200泰铢
    else:
        return {"status": "late_one", "penalty_amount": 400}  # 扣1小时工钱 ≈ 400泰铢


@router.post("")
async def clock_in(
    session: int = Form(...),
    photo_base64: str = Form(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in (Role.WAREHOUSE_LABOR,):
        raise HTTPException(403, "只有仓库劳工可以使用打卡功能")
    if session not in SESSIONS:
        raise HTTPException(400, "无效的打卡时段")

    today = date.today()
    now = datetime.now()

    # Check duplicate
    existing = (await db.execute(
        select(ClockInRecord).where(
            ClockInRecord.user_id == current_user.id,
            ClockInRecord.clock_date == today,
            ClockInRecord.session == session,
        )
    )).scalar_one_or_none()
    if existing:
        return {"message": f"今日{SESSIONS[session]['label']}已打卡", "clocked_in_at": existing.clocked_in_at.isoformat(), "duplicate": True}

    # Save photo
    photo_path = None
    if photo_base64:
        try:
            header, data = photo_base64.split(",", 1) if "," in photo_base64 else ("", photo_base64)
            img_bytes = base64.b64decode(data)
            wh_id = str(get_wh_id(current_user) or 0)
            today_str = today.isoformat()
            subdir = os.path.join(UPLOAD_DIR, wh_id, today_str, "clockin")
            os.makedirs(subdir, exist_ok=True)
            fname = f"{uuid.uuid4().hex}.jpg"
            fpath = os.path.join(subdir, fname)
            with open(fpath, "wb") as f:
                f.write(img_bytes)
            photo_path = f"uploads/{wh_id}/{today_str}/clockin/{fname}"
        except Exception:
            pass  # photo save failure shouldn't block clock-in

    wh_id = get_wh_id(current_user)
    penalty = _get_penalty(session, now)
    record = ClockInRecord(
        user_id=current_user.id,
        warehouse_id=wh_id,
        clock_date=today,
        session=session,
        clocked_in_at=now,
        photo_path=photo_path,
        status=penalty["status"],
        penalty_amount=penalty["penalty_amount"],
    )
    db.add(record)
    await db.flush()

    msg = f"{SESSIONS[session]['label']}打卡成功"
    if penalty["status"] != "normal":
        msg += f"，迟到扣{penalty['penalty_amount']}泰铢"

    return {
        "message": msg,
        "session": session,
        "clocked_in_at": record.clocked_in_at.isoformat(),
        "status": penalty["status"],
        "penalty_amount": penalty["penalty_amount"],
        "photo_path": photo_path,
    }


@router.get("/today")
async def get_today(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in (Role.WAREHOUSE_LABOR,):
        raise HTTPException(403, "无权限")

    today = date.today()
    records = (await db.execute(
        select(ClockInRecord).where(
            ClockInRecord.user_id == current_user.id,
            ClockInRecord.clock_date == today,
        ).order_by(ClockInRecord.session)
    )).scalars().all()

    completed = {r.session: {
        "session": r.session, "label": SESSIONS.get(r.session, {}).get("label", ""),
        "clocked_in_at": r.clocked_in_at.isoformat(), "status": r.status,
        "penalty_amount": r.penalty_amount, "photo_path": r.photo_path,
    } for r in records}

    return {
        "today": today.isoformat(),
        "sessions": [{"session": s, "label": v["label"], "time": str(v["time"])} for s, v in SESSIONS.items()],
        "completed": completed,
    }


@router.get("/records")
async def list_records(
    month: str = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Query by month (YYYY-MM) for the warehouse admin to review"""
    from app.models.employee import Employee
    from app.models.warehouse import Warehouse

    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.WAREHOUSE_LABOR):
        raise HTTPException(403, "无权限")

    query = select(ClockInRecord)
    if current_user.role == Role.WAREHOUSE_LABOR:
        query = query.where(ClockInRecord.user_id == current_user.id)
    else:
        from app.core.permissions import get_wh_ids
        query = query.where(ClockInRecord.warehouse_id.in_(get_wh_ids(current_user)))

    if month:
        query = query.where(func.to_char(ClockInRecord.clock_date, "YYYY-MM") == month)

    result = await db.execute(query.order_by(ClockInRecord.clock_date.desc(), ClockInRecord.session))
    records = result.scalars().all()

    uid_set = {r.user_id for r in records}
    users_map = {}
    if uid_set:
        us = (await db.execute(select(User).where(User.id.in_(uid_set)))).scalars().all()
        users_map = {u.id: u.display_name for u in us}

    return {"data": [{
        "id": r.id, "user_id": r.user_id, "user_name": users_map.get(r.user_id, ""),
        "clock_date": r.clock_date.isoformat(), "session": r.session,
        "label": SESSIONS.get(r.session, {}).get("label", ""),
        "clocked_in_at": r.clocked_in_at.isoformat() if r.clocked_in_at else None,
        "status": r.status, "penalty_amount": r.penalty_amount,
        "photo_path": r.photo_path,
    } for r in records]}


# Need to update router registration: keep the existing import in router.py unchanged

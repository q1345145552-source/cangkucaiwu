from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.models.user import User
from app.models.clock_in_records import ClockInRecord
from app.core.permissions import get_current_user, get_wh_id, Role
from app.core.timezone import thai_now, thai_today
from datetime import datetime, date, time
import os, uuid, base64

router = APIRouter()
UPLOAD_DIR = "/app/uploads"

SESSIONS = {
    1: {"label": "早上上班", "time": time(9, 0),   "window_start": time(6, 0),  "window_end": time(10, 0)},
    2: {"label": "中午休息结束", "time": time(12, 0), "window_start": time(11, 0), "window_end": time(13, 30)},
    3: {"label": "下午上班", "time": time(13, 0),  "window_start": time(12, 30),"window_end": time(14, 30)},
    4: {"label": "下午下班", "time": time(18, 0),  "window_start": time(17, 0), "window_end": time(23, 0)},
}

def _get_penalty(session: int, clocked_at: datetime) -> dict:
    """Only session 1 tracks late status. Penalty amount computed at payroll time."""
    if session != 1:
        return {"status": "normal", "penalty_amount": 0}
    t = clocked_at.time()
    if t <= time(9, 5):
        return {"status": "normal", "penalty_amount": 0}
    elif t <= time(9, 30):
        return {"status": "late_half", "penalty_amount": 0}  # amount computed at payroll
    else:
        return {"status": "late_one", "penalty_amount": 0}

@router.post("")
async def clock_in(
    session: int = Form(...),
    photo_base64: str = Form(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in (Role.WAREHOUSE_LABOR, Role.SUPER_ADMIN):
        raise HTTPException(403, "只有仓库劳工可以使用打卡功能")
    if session not in SESSIONS:
        raise HTTPException(400, "无效的打卡时段")

    today = thai_today()
    now = thai_now()
    now_t = now.time()

    # Time window check
    si = SESSIONS[session]
    ws = si["window_start"]
    we = si["window_end"]
    if now_t < ws or now_t > we:
        return {
            "message": f"不在{si['label']}打卡时间内（{ws.strftime('%H:%M')}-{we.strftime('%H:%M')}）",
            "outside_window": True,
        }

    # Check duplicate
    existing = (await db.execute(
        select(ClockInRecord).where(
            ClockInRecord.user_id == current_user.id,
            ClockInRecord.clock_date == today,
            ClockInRecord.session == session,
        )
    )).scalar_one_or_none()
    if existing:
        return {"message": f"今日{si['label']}已打卡", "clocked_in_at": existing.clocked_in_at.isoformat(), "duplicate": True}

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
            pass

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
        penalty_amount=0,  # computed at payroll time
    )
    db.add(record)
    await db.flush()

    msg = f"{si['label']}打卡成功"
    if penalty["status"] != "normal":
        msg += "（迟到，月底结算时扣款）"

    return {
        "message": msg,
        "session": session,
        "clocked_in_at": record.clocked_in_at.isoformat(),
        "status": penalty["status"],
        "penalty_amount": 0,
        "photo_path": photo_path,
    }

@router.get("/today")
async def get_today(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in (Role.WAREHOUSE_LABOR, Role.SUPER_ADMIN):
        raise HTTPException(403, "无权限")
    today = thai_today()
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
        "sessions": [{"session": s, "label": v["label"], "time": str(v["time"]),
                       "window_start": str(v["window_start"]), "window_end": str(v["window_end"])}
                      for s, v in SESSIONS.items()],
        "completed": completed,
    }

@router.get("/records")
async def list_records(
    month: str = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.models.employee import Employee
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.WAREHOUSE_LABOR, Role.SUPER_ADMIN):
        raise HTTPException(403, "无权限")
    query = select(ClockInRecord)
    if current_user.role == Role.WAREHOUSE_LABOR:
        query = query.where(ClockInRecord.user_id == current_user.id)
    elif current_user.role == Role.SUPER_ADMIN:
        pass  # super_admin sees all records
    else:
        # Filter by active (header-selected) warehouse, not all warehouses
        active_wh = get_wh_id(current_user)
        if active_wh:
            query = query.where(ClockInRecord.warehouse_id == active_wh)
    if month:
        query = query.where(func.to_char(ClockInRecord.clock_date, "YYYY-MM") == month)
    result = await db.execute(query.order_by(ClockInRecord.clock_date.desc(), ClockInRecord.session))
    records = result.scalars().all()
    uid_set = {r.user_id for r in records}
    users_map = {}
    if uid_set:
        us = (await db.execute(select(User).where(User.id.in_(uid_set)))).scalars().all()
        users_map = {u.id: u.display_name for u in us}
    emp_map = {}
    if uid_set:
        emps = (await db.execute(select(Employee).where(Employee.user_id.in_(uid_set)))).scalars().all()
        emp_map = {e.user_id: e.id for e in emps}
    return {"data": [{
        "id": r.id, "user_id": r.user_id, "user_name": users_map.get(r.user_id, ""),
        "employee_id": emp_map.get(r.user_id),
        "clock_date": r.clock_date.isoformat(), "session": r.session,
        "label": SESSIONS.get(r.session, {}).get("label", ""),
        "clocked_in_at": r.clocked_in_at.isoformat() if r.clocked_in_at else None,
        "status": r.status, "penalty_amount": r.penalty_amount,
        "photo_path": r.photo_path,
    } for r in records]}

@router.get("/photos")
async def get_photos(
    employee_id: int = Query(...),
    date: str = Query(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Admin: get all clock-in photos for a specific employee on a specific date"""
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPER_ADMIN):
        raise HTTPException(403, "只有管理员可以查看打卡照片")

    from app.models.employee import Employee

    # Try employee_id first, then fallback to user_id lookup
    emp = (await db.execute(
        select(Employee).where(Employee.id == employee_id)
    )).scalar_one_or_none()
    if not emp:
        # Fallback: perhaps employee_id is actually user_id
        emp = (await db.execute(
            select(Employee).where(Employee.user_id == employee_id)
        )).scalar_one_or_none()
    if not emp:
        # Last resort: try matching by user's display_name
        u = (await db.execute(
            select(User).where(User.id == employee_id)
        )).scalar_one_or_none()
        if u:
            emp = (await db.execute(
                select(Employee).where(Employee.name == u.display_name)
            )).scalar_one_or_none()
    if not emp:
        raise HTTPException(404, "员工不存在")

    if current_user.role != Role.SUPER_ADMIN:
        wh_ids = get_wh_ids(current_user)
        if emp.warehouse_id not in wh_ids:
            raise HTTPException(403, "无权查看该员工")

    # Get user_id from employee link
    uid = emp.user_id
    if not uid:
        # Fallback name matching
        u = (await db.execute(
            select(User).where(User.display_name == emp.name, User.role == "warehouse_labor")
        )).scalar_one_or_none()
        uid = u.id if u else None

    try:
        target_date = datetime.strptime(date, "%Y-%m-%d").date()
    except:
        raise HTTPException(400, "日期格式错误 YYYY-MM-DD")

    records = []
    if uid:
        records = (await db.execute(
            select(ClockInRecord).where(
                ClockInRecord.user_id == uid,
                ClockInRecord.clock_date == target_date,
            ).order_by(ClockInRecord.session)
        )).scalars().all()

    sessions_data = {}
    for r in records:
        sessions_data[r.session] = {
            "session": r.session,
            "label": SESSIONS.get(r.session, {}).get("label", ""),
            "clocked_in_at": r.clocked_in_at.isoformat() if r.clocked_in_at else None,
            "status": r.status,
            "penalty_amount": r.penalty_amount,
            "photo_path": r.photo_path,
        }

    all_sessions = []
    for s in [1, 2, 3, 4]:
        if s in sessions_data:
            all_sessions.append(sessions_data[s])
        else:
            all_sessions.append({
                "session": s,
                "label": SESSIONS.get(s, {}).get("label", ""),
                "clocked_in_at": None,
                "status": "missing",
                "penalty_amount": 0,
                "photo_path": None,
            })

    return {
        "employee_id": employee_id,
        "employee_name": emp.name,
        "date": date,
        "sessions": all_sessions,
    }

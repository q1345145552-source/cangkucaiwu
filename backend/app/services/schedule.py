"""仓库排班设置：每个仓库可配置四个上班时间点，存 SystemSetting key-value。

四个时间点按打卡时段顺序：
1. schedule_morning_start     早上上班
2. schedule_noon_break_start  中午休息开始
3. schedule_noon_break_end    中午休息结束
4. schedule_afternoon_end     下午下班
"""
from datetime import datetime, time
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.expense_fund import SystemSetting

KEY_MORNING_START = "schedule_morning_start"
KEY_NOON_BREAK_START = "schedule_noon_break_start"
KEY_NOON_BREAK_END = "schedule_noon_break_end"
KEY_AFTERNOON_END = "schedule_afternoon_end"

SCHEDULE_KEYS = [
    KEY_MORNING_START,
    KEY_NOON_BREAK_START,
    KEY_NOON_BREAK_END,
    KEY_AFTERNOON_END,
]

# 对外语义字段名 -> SystemSetting key
FIELD_TO_KEY = {
    "morning_start": KEY_MORNING_START,
    "noon_break_start": KEY_NOON_BREAK_START,
    "noon_break_end": KEY_NOON_BREAK_END,
    "afternoon_end": KEY_AFTERNOON_END,
}

DEFAULT_TIMES = {
    KEY_MORNING_START: "09:00",
    KEY_NOON_BREAK_START: "12:00",
    KEY_NOON_BREAK_END: "13:00",
    KEY_AFTERNOON_END: "18:00",
}

# 打卡时段 -> SystemSetting key（时段 1-4）
SESSION_KEY = {
    1: KEY_MORNING_START,
    2: KEY_NOON_BREAK_START,
    3: KEY_NOON_BREAK_END,
    4: KEY_AFTERNOON_END,
}


def parse_hhmm(s) -> time | None:
    """把 'HH:MM' 解析为 time；无效返回 None。"""
    if not isinstance(s, str):
        return None
    try:
        return datetime.strptime(s.strip(), "%H:%M").time()
    except (ValueError, TypeError):
        return None


def default_schedule() -> dict[str, str]:
    """默认排班（语义字段名 -> 'HH:MM'）。"""
    return {
        "morning_start": DEFAULT_TIMES[KEY_MORNING_START],
        "noon_break_start": DEFAULT_TIMES[KEY_NOON_BREAK_START],
        "noon_break_end": DEFAULT_TIMES[KEY_NOON_BREAK_END],
        "afternoon_end": DEFAULT_TIMES[KEY_AFTERNOON_END],
    }


async def get_schedule(db: AsyncSession, wh_id: int | None) -> dict[str, str]:
    """读取某仓库的排班，返回语义字段名 -> 'HH:MM'；未设置/无效回退默认。"""
    result = default_schedule()
    if not wh_id:
        return result
    rows = (await db.execute(
        select(SystemSetting).where(
            SystemSetting.warehouse_id == wh_id,
            SystemSetting.key.in_(SCHEDULE_KEYS),
        )
    )).scalars().all()
    m = {s.key: s.value for s in rows}
    for field, key in FIELD_TO_KEY.items():
        val = m.get(key)
        if val and parse_hhmm(val):
            result[field] = parse_hhmm(val).strftime("%H:%M")
    return result


async def get_session_times(db: AsyncSession, wh_id: int | None) -> dict[int, time]:
    """读取某仓库的四个打卡时段标准时间，返回 {1: time, 2: time, 3: time, 4: time}。"""
    sched = await get_schedule(db, wh_id)
    times: dict[int, time] = {}
    for session, key in SESSION_KEY.items():
        field = next(f for f, k in FIELD_TO_KEY.items() if k == key)
        parsed = parse_hhmm(sched[field])
        times[session] = parsed if parsed else parse_hhmm(DEFAULT_TIMES[key])
    return times

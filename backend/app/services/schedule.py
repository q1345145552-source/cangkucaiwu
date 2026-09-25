"""仓库作息（配置中心）：每个仓库可配置八个时间点 + 加班月度上限，存 SystemSetting key-value。

八个时间点（按一天时间从早到晚）：
1. morning_start    早上上班
2. late_half        迟到半小时红线
3. late_one         迟到1小时红线
4. noon_break_start 中午休息开始
5. noon_break_end   中午休息结束
6. early_one        早退1小时红线
7. early_half       早退半小时红线
8. afternoon_end    下午下班

加班月度上限沿用旧 key overtime_monthly_limit。
"""
from datetime import datetime, time
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.expense_fund import SystemSetting

# 语义字段名 -> (SystemSetting key, 默认 'HH:MM')
WORK_TIME_FIELDS = {
    "morning_start": ("schedule_morning_start", "09:00"),
    "late_half": ("schedule_late_half", "09:05"),
    "late_one": ("schedule_late_one", "09:31"),
    "noon_break_start": ("schedule_noon_break_start", "12:00"),
    "noon_break_end": ("schedule_noon_break_end", "13:00"),
    "early_one": ("schedule_early_one", "17:00"),
    "early_half": ("schedule_early_half", "17:30"),
    "afternoon_end": ("schedule_afternoon_end", "18:00"),
}

# 校验顺序（时间从早到晚）
ORDER_FIELDS = [
    "morning_start", "late_half", "late_one", "noon_break_start",
    "noon_break_end", "early_one", "early_half", "afternoon_end",
]

# 打卡时段 1-4 -> 语义字段名
SESSION_KEY = {
    1: "morning_start",
    2: "noon_break_start",
    3: "noon_break_end",
    4: "afternoon_end",
}

OVERTIME_LIMIT_KEY = "overtime_monthly_limit"
DEFAULT_OVERTIME_LIMIT = 50.0


def parse_hhmm(s) -> time | None:
    """把 'HH:MM' 解析为 time；无效返回 None。"""
    if not isinstance(s, str):
        return None
    try:
        return datetime.strptime(s.strip(), "%H:%M").time()
    except (ValueError, TypeError):
        return None


def default_work_schedule() -> dict:
    """默认作息：8 个时间点（'HH:MM'）+ 加班上限。"""
    result = {field: default for field, (_, default) in WORK_TIME_FIELDS.items()}
    result["overtime_limit"] = DEFAULT_OVERTIME_LIMIT
    return result


async def get_work_schedule(db: AsyncSession, wh_id: int | None) -> dict:
    """读取某仓库的作息配置，返回 8 个时间点（'HH:MM'）+ overtime_limit(float)。"""
    result = default_work_schedule()
    if not wh_id:
        return result
    keys = [key for key, _ in WORK_TIME_FIELDS.values()] + [OVERTIME_LIMIT_KEY]
    rows = (await db.execute(
        select(SystemSetting).where(
            SystemSetting.warehouse_id == wh_id,
            SystemSetting.key.in_(keys),
        )
    )).scalars().all()
    m = {s.key: s.value for s in rows}
    for field, (key, default) in WORK_TIME_FIELDS.items():
        val = m.get(key)
        parsed = parse_hhmm(val)
        if parsed:
            result[field] = parsed.strftime("%H:%M")
    ot = m.get(OVERTIME_LIMIT_KEY)
    try:
        result["overtime_limit"] = float(ot) if ot not in (None, "") else DEFAULT_OVERTIME_LIMIT
    except (ValueError, TypeError):
        result["overtime_limit"] = DEFAULT_OVERTIME_LIMIT
    return result


async def get_session_times(db: AsyncSession, wh_id: int | None) -> dict[int, time]:
    """读取某仓库的四个打卡时段标准时间，返回 {1: time, 2: time, 3: time, 4: time}。"""
    sched = await get_work_schedule(db, wh_id)
    times: dict[int, time] = {}
    for session, field in SESSION_KEY.items():
        parsed = parse_hhmm(sched[field])
        times[session] = parsed if parsed else parse_hhmm(WORK_TIME_FIELDS[field][1])
    return times

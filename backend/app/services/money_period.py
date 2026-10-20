"""Read-only calendar bounds for wallet queries; YYYY-MM already includes the year."""
import calendar
import re
from datetime import date

from fastapi import HTTPException
from app.core.timezone import thai_today


def _date(value):
    text = str(value)
    if not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', text):
        raise HTTPException(400, '日期格式错误，应为 YYYY-MM-DD')
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise HTTPException(400, '日期格式错误，应为有效的 YYYY-MM-DD')


def money_period(month=None, start_date=None, end_date=None, *, year=None, default_start=None, default_end=None):
    """Inclusive local business days, with a month/range intersection if both are supplied.

    Month always means the full specified calendar month, including a future month.
    No-month defaults remain a caller decision; no server-local timezone is consulted.
    """
    if year is not None:
        raise HTTPException(400, '不支持单独的 year 参数，请使用 month=YYYY-MM 指定年月')
    lower = upper = None
    if month is not None:
        if not re.fullmatch(r'[0-9]{4}-(0[1-9]|1[0-2])', str(month)):
            raise HTTPException(400, '月份格式错误，应为 YYYY-MM，例如 2026-09')
        y, m = map(int, str(month).split('-'))
        try:
            lower = date(y, m, 1)
            upper = date(y, m, calendar.monthrange(y, m)[1])
        except ValueError:
            raise HTTPException(400, '月份格式错误，应为有效的 YYYY-MM')
    start = _date(start_date) if start_date is not None else None
    end = _date(end_date) if end_date is not None else None
    if start and end and start > end:
        raise HTTPException(400, '开始日期不能晚于结束日期')
    today = thai_today()
    start = max(start, lower) if start and lower else start or lower or default_start or today.replace(day=1)
    end = min(end, upper) if end and upper else end or upper or default_end or today
    if start > end:
        raise HTTPException(400, '日期范围与所选月份不重合' if month is not None else '开始日期不能晚于结束日期')
    return start, end

"""Thailand timezone utilities (UTC+7)."""
from datetime import datetime, date, timezone, timedelta
import zoneinfo

THAI_TZ = zoneinfo.ZoneInfo("Asia/Bangkok")
THAI_OFFSET = timezone(timedelta(hours=7))


def thai_now() -> datetime:
    """Return current datetime in Thailand timezone (timezone-aware)."""
    return datetime.now(THAI_TZ)


def thai_today() -> date:
    """Return current date in Thailand timezone."""
    return datetime.now(THAI_TZ).date()

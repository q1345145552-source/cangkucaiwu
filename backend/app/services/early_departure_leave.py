"""Only decide whether approved leave covers a payroll early-departure event."""
from datetime import datetime
from app.core.timezone import THAI_TZ
from app.services.schedule import parse_hhmm, default_work_schedule


def leave_covers_early_departure(leave_info, clocked_at, work_date, schedule):
    # Caller supplies only the existing approved-leave aggregation.
    if not leave_info:
        return False
    if leave_info.get('full'):
        return True
    if clocked_at is None:
        return False
    local = clocked_at.astimezone(THAI_TZ) if clocked_at.tzinfo else clocked_at.replace(tzinfo=THAI_TZ)
    defaults = default_work_schedule()
    afternoon = parse_hhmm(schedule.get('noon_break_end')) or parse_hhmm(defaults['noon_break_end'])
    if leave_info.get('afternoon') and local >= datetime.combine(work_date, afternoon, tzinfo=THAI_TZ):
        return True
    if leave_info.get('hours_has'):
        end = parse_hhmm(schedule.get('afternoon_end')) or parse_hhmm(defaults['afternoon_end'])
        early_seconds = max((datetime.combine(work_date, end, tzinfo=THAI_TZ) - local).total_seconds(), 0.0)
        return (float(leave_info.get('hours', 0)) + 0.5) * 3600 >= early_seconds
    return False

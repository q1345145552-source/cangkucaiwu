"""Configured half-day leave hours shared by calendar and payroll."""
from datetime import datetime

from app.core.timezone import THAI_TZ
from app.services.schedule import default_work_schedule, parse_hhmm


def is_half_day_leave(info):
    return bool(info) and not info.get("full") and not info.get("hourly_missing") and bool(info.get("morning") or info.get("afternoon"))


def half_day_leave_hours(records, info, work_date, schedule):
    """Return configured leave hours and net punched hours, without double deduction.

    Only punched time overlapping the approved leave window is removed. Time
    already missing from punches is not deducted again. Inputs are never mutated.
    """
    defaults = default_work_schedule()
    def boundary(key):
        return datetime.combine(work_date, parse_hhmm(schedule.get(key)) or parse_hhmm(defaults[key]), tzinfo=THAI_TZ)
    windows = []
    for flag, start, end in (("morning", "morning_start", "noon_break_start"), ("afternoon", "noon_break_end", "afternoon_end")):
        if info.get(flag):
            windows.append((boundary(start), boundary(end)))
    leave_hours = sum(max((end - start).total_seconds(), 0) for start, end in windows) / 3600
    if len(records) not in (2, 4) or len({r.session for r in records}) != len(records) or any(r.clocked_in_at is None for r in records):
        return round(leave_hours, 2), 0.0
    times = sorted(r.clocked_in_at.replace(tzinfo=THAI_TZ) if r.clocked_in_at.tzinfo is None else r.clocked_in_at.astimezone(THAI_TZ) for r in records)
    seconds = 0.0
    for i in range(0, len(times), 2):
        start, end = times[i:i + 2]
        overlap = sum(max((min(end, b) - max(start, a)).total_seconds(), 0) for a, b in windows)
        seconds += max((end - start).total_seconds() - overlap, 0)
    return round(leave_hours, 2), round(max(seconds / 3600, 0), 2)

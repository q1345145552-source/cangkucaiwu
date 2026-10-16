"""Shared calendar/payroll net hours for hourly leave only."""
from datetime import datetime
from app.core.timezone import THAI_TZ
from app.services.schedule import parse_hhmm, default_work_schedule


def hourly_leave_net_hours(clock_hours, leave_hours, last_clocked_at, work_date, schedule, standard_hours):
    if leave_hours is None or leave_hours >= standard_hours:
        return 0.0
    early_hours = 0.0
    if last_clocked_at is not None:
        last = last_clocked_at
        if last.tzinfo is not None:
            last = last.astimezone(THAI_TZ)
        else:
            last = last.replace(tzinfo=THAI_TZ)
        end_time = parse_hhmm(schedule.get('afternoon_end')) or parse_hhmm(default_work_schedule()['afternoon_end'])
        end = datetime.combine(work_date, end_time, tzinfo=THAI_TZ)
        early_hours = max((end - last).total_seconds() / 3600.0, 0.0)
    deduction = max(float(leave_hours) - early_hours, 0.0)
    return round(max(float(clock_hours) - deduction, 0.0), 2)


def is_hourly_leave(info):
    return bool(info) and (bool(info.get('hourly_missing')) or (
        not info.get('full') and not info.get('morning') and not info.get('afternoon')
        and bool(info.get('hours_has'))
    ))


def hourly_clock_hours(records):
    """Use the same valid punch pairs in both callers, including incomplete data."""
    if len({r.session for r in records}) not in (2, 4) or len(records) not in (2, 4):
        return 0.0
    if any(r.clocked_in_at is None for r in records):
        return 0.0
    times = sorted(r.clocked_in_at for r in records)
    return sum(max((times[i + 1] - times[i]).total_seconds() / 3600.0, 0.0) for i in range(0, len(times), 2))

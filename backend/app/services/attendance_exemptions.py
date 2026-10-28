"""Warehouse day exemption: eight paid hours less approved leave, never punches."""
import calendar
from datetime import date
from fastapi import HTTPException
from sqlalchemy import select, text
from app.models.attendance_exemption import AttendanceExemption
from app.models.clock_in_records import ClockInRecord
from app.models.payroll import PayrollRecord
from app.services.half_day_leave import half_day_leave_hours


def valid_clock():
    return ClockInRecord.status.is_distinct_from('voided')

async def lock_day(db, warehouse_id, day):
    # Serialize exemption creation with every makeup entry; transaction-scoped.
    if db.get_bind().dialect.name != 'postgresql':
        from app.models.warehouse import Warehouse
        await db.execute(select(Warehouse.id).where(Warehouse.id == warehouse_id).with_for_update())
        return
    await db.execute(text('SELECT pg_advisory_xact_lock(:namespace, :day)'),
                     {'namespace': 180000000 + warehouse_id, 'day': day.toordinal()})

async def active_days(db, warehouse_id, start, end):
    return set((await db.execute(select(AttendanceExemption.date).where(
        AttendanceExemption.warehouse_id == warehouse_id, AttendanceExemption.status == 'active',
        AttendanceExemption.date >= start, AttendanceExemption.date <= end))).scalars())

async def ensure_makeup_allowed(db, warehouse_id, day):
    await lock_day(db, warehouse_id, day)
    if await active_days(db, warehouse_id, day, day):
        raise HTTPException(400, '该日期已设仓库豁免，无需补卡')


def exemption_hours(info, day, schedule):
    if not info:
        return 8.0, 0.0
    if info.get('full') or info.get('hourly_missing'):
        return 0.0, 8.0
    half, _ = half_day_leave_hours([], info, day, schedule)
    leave = min(8.0, max(0.0, half + float(info.get('hours') or 0)))
    return round(8.0 - leave, 2), round(leave, 2)

async def payroll_warning(db, warehouse_id, day):
    records = (await db.execute(select(PayrollRecord).where(
        PayrollRecord.warehouse_id == warehouse_id, PayrollRecord.voided.is_not(True)))).scalars()
    for record in records:
        # Legacy payroll without explicit boundaries retains its original half-month period.
        year, month = map(int, record.period.split('-'))
        start = record.settle_start_date or date(year, month, 16 if record.half == 'second_half' else 1)
        end = record.settle_end_date or date(year, month, calendar.monthrange(year, month)[1] if record.half == 'second_half' else 15)
        if start <= day <= end:
            return '该日期已有工资单，请手动重算才生效'
    return None


def data(row):
    return {key: (getattr(row,key).isoformat() if key in ('date','created_at','revoked_at') and getattr(row,key) else getattr(row,key))
            for key in ('id','warehouse_id','date','reason','created_by','created_by_name','created_at','status',
                        'revoked_by','revoked_by_name','revoked_at','revoke_reason')}

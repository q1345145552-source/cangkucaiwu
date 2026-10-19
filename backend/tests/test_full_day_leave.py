"""Full-day leave: real HTTP guards, preserved punches, calendar/payroll and identity."""
import asyncio
import ast
import json
import subprocess
from datetime import date, datetime
from pathlib import Path

import pytest
from sqlalchemy import select
from app.api.v1 import clock_in, payroll
from app.models import ClockInRecord, Employee, LeaveRequest, SalaryTemplate, User
from app.models.payroll import PayrollRecord
from app.core.messages import t
from tests.test_round2_permissions import auth
from tests.test_round3_permissions import hr_environment, snapshot

DAY = date(2026, 10, 16)


def freeze(monkeypatch):
    monkeypatch.setattr(clock_in, "thai_today", lambda: DAY)
    monkeypatch.setattr(clock_in, "thai_now", lambda: datetime(2026, 10, 16, 9))
    monkeypatch.setattr(payroll, "thai_today", lambda: date(2026, 10, 18))


async def leave(factory, duration="full", status="approved", **extra):
    async with factory() as db:
        item = LeaveRequest(employee_id=1, warehouse_id=1, leave_date=DAY,
            duration_type=duration, status=status, notified_at=datetime(2026, 10, 15), **extra)
        db.add(item); await db.flush()
        if duration is None:
            item.duration_type = None  # Real legacy SQL NULL, not the column's insert default.
        await db.commit()
        return item.id


async def punches(factory, sessions=(1, 2, 3, 4)):
    times = {1: 9, 2: 12, 3: 13, 4: 18}
    async with factory() as db:
        for session in sessions:
            db.add(ClockInRecord(user_id=5, warehouse_id=1, clock_date=DAY, session=session,
                clocked_in_at=datetime(2026, 10, 16, times[session]), status="normal"))
        await db.commit()


async def clock_snapshot(factory):
    async with factory() as db:
        return [tuple(r) for r in (await db.execute(select(ClockInRecord.__table__).order_by(ClockInRecord.id))).all()]


@pytest.mark.parametrize("lang", ["zh", "th", "my"])
@pytest.mark.parametrize("duration", ["full", None, ""])
def test_approved_full_blocks_all_sessions_even_duplicates(tmp_path, monkeypatch, lang, duration):
    async def run():
        freeze(monkeypatch)
        async with hr_environment(tmp_path, monkeypatch) as (_, f, c):
            await leave(f, duration); await punches(f, (1,))
            before = await clock_snapshot(f); old = await snapshot(f)
            today = await c.get('/api/v1/clock-in/today', headers=auth(5))
            assert today.status_code == 200 and today.json()['full_day_leave'] is True
            for session in (1, 2, 3, 4):
                r = await c.post('/api/v1/clock-in', headers={**auth(5), 'X-Language': lang}, data={'session': session})
                assert r.status_code == 400 and r.json() == {'detail': t('full_day_leave_cannot_clock', lang)}, r.text
            assert before == await clock_snapshot(f) and old == await snapshot(f)
            print('FULL_DAY_BLOCK', json.dumps({'language': lang, 'status': r.status_code, 'body': r.json()}, ensure_ascii=False))
    asyncio.run(run())


@pytest.mark.parametrize('duration,status', [('morning','approved'), ('afternoon','approved'), ('hours','approved'), ('full','pending'), ('full','rejected')])
def test_other_leave_allows_clock(tmp_path, monkeypatch, duration, status):
    async def run():
        freeze(monkeypatch)
        async with hr_environment(tmp_path, monkeypatch) as (_, f, c):
            await leave(f, duration, status, hours=2 if duration == 'hours' else None)
            r = await c.get('/api/v1/clock-in/today', headers=auth(5))
            assert r.status_code == 200 and r.json()['full_day_leave'] is False
            r = await c.post('/api/v1/clock-in', headers=auth(5), data={'session': 1})
            assert r.status_code == 200 and r.json()['session'] == 1, r.text
            print('OTHER_LEAVE_CLOCK', json.dumps({'duration':duration, 'status':status, 'response':r.json()}, ensure_ascii=False))
    asyncio.run(run())


@pytest.mark.parametrize('template_type', ['hourly','daily','monthly'])
@pytest.mark.parametrize('sessions', [(1, 2), (1, 2, 3, 4)])
def test_full_day_with_punches_zero_calendar_and_payroll_preserves_old(tmp_path, monkeypatch, template_type, sessions):
    async def run():
        freeze(monkeypatch)
        async with hr_environment(tmp_path, monkeypatch) as (_, f, c):
            await leave(f); await punches(f, sessions)
            async with f() as db:
                template = await db.get(SalaryTemplate, 1)
                template.type = template_type; template.amount = 12400 if template_type == 'monthly' else 400
                await db.commit()
                old_leaves = [tuple(r) for r in (await db.execute(select(LeaveRequest.__table__))).all()]
            old = await snapshot(f); old_clocks = await clock_snapshot(f)
            r = await c.get(f'/api/v1/attendance/calendar?start_date={DAY}&end_date={DAY}', headers=auth(1))
            assert r.status_code == 200, r.text
            event = next(e for e in r.json()['events'] if e['employee_id'] == 1)
            assert event['status'] == 'leave' and event['work_hours'] == 0
            assert event['clock_hours'] == (8 if len(sessions) == 4 else 3)  # raw punches retained
            assert await snapshot(f) == old
            r = await c.post('/api/v1/payroll/calculate', headers=auth(1), json={'end_date': str(DAY), 'employee_ids':[1]})
            assert r.status_code == 200, r.text
            async with f() as db:
                record = (await db.execute(select(PayrollRecord).where(PayrollRecord.employee_id == 1, PayrollRecord.settle_start_date == DAY))).scalar_one()
                detail = json.loads(record.detail)
                assert detail['daily_hours'][0]['hours'] == detail['work_hours'] == 0
                assert detail['daily_hours'][0]['attendance'] == record.attendance_days == 0
                assert record.base_pay == record.net_pay == 0, detail
                assert old_leaves == [tuple(row) for row in (await db.execute(select(LeaveRequest.__table__))).all()]
            assert (await snapshot(f))[:len(old)] == old
            assert await clock_snapshot(f) == old_clocks
            print('FULL_DAY_ZERO', json.dumps({'template':template_type,'punches':len(sessions),'calendar':event,'daily':detail['daily_hours'][0],'base_pay':record.base_pay,'net_pay':record.net_pay}, ensure_ascii=False))
    asyncio.run(run())


def test_approval_warning_preserves_punches_and_old_payroll(tmp_path, monkeypatch):
    async def run():
        freeze(monkeypatch)
        async with hr_environment(tmp_path, monkeypatch) as (_, f, c):
            r = await c.post('/api/v1/clock-in', headers=auth(5), data={'session':1}); assert r.status_code == 200
            lid = await leave(f, status='pending'); clocks = await clock_snapshot(f); old = await snapshot(f)
            r = await c.put(f'/api/v1/attendance/leaves/{lid}/approve', headers=auth(1))
            assert r.status_code == 200 and r.json() == {'message':'已批准','warning':'该员工当天已有打卡记录 请确认是否需要处理','clocked_dates':[str(DAY)]}
            assert clocks == await clock_snapshot(f) and old == await snapshot(f)
            assert (await c.get('/api/v1/clock-in/today', headers=auth(5))).json()['full_day_leave'] is True
            async with f() as db:
                lr=await db.get(LeaveRequest,lid); assert lr.status=='approved' and lr.reviewed_by==1 and lr.reviewed_at
            print('FULL_DAY_APPROVAL', json.dumps(r.json(), ensure_ascii=False))
    asyncio.run(run())


def test_proxy_warning_and_warehouse_isolation(tmp_path, monkeypatch):
    async def run():
        freeze(monkeypatch)
        async with hr_environment(tmp_path, monkeypatch) as (_, f, c):
            await punches(f, (1,)); before=await clock_snapshot(f)
            r=await c.post('/api/v1/attendance/leaves/admin-record',headers=auth(1),json={'employee_id':1,'start_date':str(DAY),'end_date':str(DAY)})
            assert r.status_code==200 and r.json()['clocked_dates']==[str(DAY)] and 'warning' in r.json()
            assert await clock_snapshot(f)==before
            # Other warehouse labor remains allowed; the same date does not leak across warehouses.
            assert (await c.get('/api/v1/clock-in/today',headers=auth(6))).json()['full_day_leave'] is False
            assert (await c.post('/api/v1/clock-in',headers=auth(6),data={'session':1})).status_code==200
    asyncio.run(run())


@pytest.mark.parametrize('identity',['phone','name','supervisor'])
def test_identity_mapping(tmp_path,monkeypatch,identity):
    async def run():
        freeze(monkeypatch)
        async with hr_environment(tmp_path,monkeypatch) as (_,f,c):
            uid=5
            async with f() as db:
                employee=await db.get(Employee,1)
                if identity=='supervisor':
                    uid=4;employee.user_id=4
                    user=await db.get(User,4);user.attendance_enabled=True;user.attendance_employee_id=1
                else:
                    employee.user_id=None
                    employee.phone='labor1' if identity=='phone' else None
                await db.commit()
            await leave(f)
            assert (await c.get('/api/v1/clock-in/today',headers=auth(uid))).json()['full_day_leave'] is True
            assert (await c.post('/api/v1/clock-in',headers=auth(uid),data={'session':1})).status_code==400
    asyncio.run(run())


def test_half_hourly_early_and_other_writes_unchanged():
    root=Path(__file__).resolve().parents[2]
    for name in ('half_day_leave','hourly_leave','early_departure_leave'):
        path=f'backend/app/services/{name}.py'
        assert (root/path).read_text()==subprocess.check_output(['git','show',f'6f9243b:{path}'],cwd=root,text=True)
    path='backend/app/api/v1/clock_in.py'
    def functions(source):return {n.name:ast.dump(n,include_attributes=False) for n in ast.parse(source).body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
    old=functions(subprocess.check_output(['git','show',f'6f9243b:{path}'],cwd=root,text=True));new=functions((root/path).read_text())
    assert {k:v for k,v in old.items() if k not in ('clock_in','get_today')}=={k:v for k,v in new.items() if k not in ('clock_in','get_today')}

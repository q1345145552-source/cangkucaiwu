"""Complete-month money assertions and unchanged eight-hour results."""
import asyncio
import json
import subprocess
from datetime import date, datetime
from pathlib import Path

import pytest
from sqlalchemy import select
from app.api.v1 import payroll
from app.models import User, Employee, SalaryTemplate, LeaveRequest, ClockInRecord, SystemSetting
from app.models.employee import EmployeeRestDate
from app.models.attendance_exemption import AttendanceExemption
from app.services import monthly_payroll
from tests.test_round3_permissions import hr_environment
from tests.monthly_leave_support import complete_month

BASELINE = '343bbc624d7304b33742cd8382257bea317a2772'
DAY = date(2026, 10, 4)

@pytest.mark.parametrize('standard,hours,expected', [
    (6,6,400),(6,3,200),(6,7,400),
    (8,6,300),(8,2,100),(8,8,400),(8,9,400),(8,None,400),
])
def test_complete_month_hourly_leave(tmp_path, monkeypatch, standard, hours, expected):
    async def run():
        async with hr_environment(tmp_path,monkeypatch) as (_,factory,_):
            async with factory() as db:
                end='16:00' if standard==6 else '18:00'
                await complete_month(db,monkeypatch,DAY,end,12000,'fixed')
                for key,value in [('schedule_afternoon_end',end),('schedule_early_one','15:00' if standard==6 else '17:00'),('schedule_early_half','15:30' if standard==6 else '17:30')]:
                    db.add(SystemSetting(warehouse_id=1,key=key,value=value))
                for session,clock in enumerate(('09:00','12:00','13:00',end),1):
                    db.add(ClockInRecord(user_id=5,warehouse_id=1,clock_date=DAY,session=session,clocked_in_at=datetime.fromisoformat('2026-10-04T'+clock),status='normal'))
                leave=LeaveRequest(employee_id=1,warehouse_id=1,leave_date=DAY,duration_type='hours',hours=hours,status='approved',notified_at=datetime(2026,10,3))
                db.add(leave)
                await db.commit()
                req=payroll.CalculateRequest(employee_ids=[1],end_date='2026-10-31')
                prep=await payroll._prepare_payroll(db,await db.get(User,3),1,req)
                payroll._validate_prep(prep)
                employee=await db.get(Employee,1)
                new=await monthly_payroll.compute_monthly_record(db,1,req,prep,employee)
                assert new.leave_deduction==expected
                assert new.absence_deduction==0
                assert new.early_penalty==0
                assert new.net_pay==12000-expected
                detail=json.loads(new.detail)
                target=next(d for d in detail['daily_hours'] if d['date']==str(DAY))
                expected_hours=0 if hours is None else max(standard-hours,0)
                assert target['hours']==expected_hours
                assert target['attendance']==pytest.approx(expected_hours/standard,abs=.0001)
                if standard==8:
                    new_values={c.name:getattr(new,c.name) for c in new.__table__.columns}
                    source=subprocess.check_output(['git','show',BASELINE+':backend/app/services/monthly_payroll.py'],cwd=Path(__file__).resolve().parents[2],text=True)
                    namespace={'__name__':'monthly_before'}
                    exec(compile(source,'monthly_before','exec'),namespace)
                    namespace['thai_now']=monthly_payroll.thai_now
                    old=await namespace['compute_monthly_record'](db,1,req,prep,employee)
                    assert {c.name:getattr(old,c.name) for c in old.__table__.columns}==new_values
                print('ACTUAL',standard,hours,'leave',new.leave_deduction,'net',new.net_pay,'baseline_equal',standard==8)
                await db.rollback()
    asyncio.run(run())


@pytest.mark.parametrize("full_leave,expected_hours,expected_net", [(False,8,12000),(True,0,11600)])
def test_monthly_exemption_precedence(tmp_path,monkeypatch,full_leave,expected_hours,expected_net):
    async def run():
        async with hr_environment(tmp_path,monkeypatch) as (_,factory,client):
            async with factory() as db:
                await complete_month(db,monkeypatch,DAY,amount=12000,mode="fixed")
                db.add(EmployeeRestDate(employee_id=1,warehouse_id=1,rest_date=DAY,is_rest=True,source="manual"))
                db.add(AttendanceExemption(warehouse_id=1,date=DAY,reason="合成豁免",created_by=1,created_by_name="测试管理员"))
                if full_leave:
                    db.add(LeaveRequest(employee_id=1,warehouse_id=1,leave_date=DAY,duration_type="full",status="approved",notified_at=datetime(2026,10,3)))
                await db.commit()
                req=payroll.CalculateRequest(employee_ids=[1],end_date="2026-10-31")
                prep=await payroll._prepare_payroll(db,await db.get(User,3),1,req)
                payroll._validate_prep(prep)
                row=await monthly_payroll.compute_monthly_record(db,1,req,prep,await db.get(Employee,1))
                target=next(d for d in json.loads(row.detail)['daily_hours'] if d['date']==str(DAY))
                assert target['status']=="exempt" and target['hours']==expected_hours
                assert row.net_pay==expected_net and row.absence_deduction==0
                await db.rollback()
            from tests.test_round2_permissions import auth
            response=await client.get(f"/api/v1/attendance/calendar?start_date={DAY}&end_date={DAY}",headers=auth(1))
            assert response.status_code==200
            event=next(e for e in response.json()['events'] if e['employee_id']==1)
            assert event['status']=="exempt" and event['work_hours']==expected_hours
    asyncio.run(run())

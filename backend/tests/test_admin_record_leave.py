"""Proxy leave immediately applies; employee applications remain pending."""
import ast
import asyncio
import json
import subprocess
from datetime import date, datetime
from pathlib import Path

import pytest
from sqlalchemy import delete, select
from app.models import ClockInRecord, Employee, LeaveRequest, RestDay
from app.models.payroll import PayrollRecord
import app.api.v1.payroll as payroll
from tests.test_round2_permissions import auth, set_perms
from tests.test_round3_permissions import hr_environment, snapshot

DAY='2026-10-04'
PATH='/api/v1/attendance/leaves/admin-record'

async def calendar(client):
 r=await client.get(f'/api/v1/attendance/calendar?start_date={DAY}&end_date={DAY}',headers=auth(1))
 assert r.status_code==200,r.text
 return next(e for e in r.json()['events'] if e['employee_id']==1)

async def setup(factory,punches=()):
 async with factory() as db:
  await db.execute(delete(RestDay).where(RestDay.employee_id==1))
  (await db.get(Employee,1)).hire_date=datetime(2026,10,4)
  for session,t in punches:
   db.add(ClockInRecord(user_id=5,warehouse_id=1,clock_date=date(2026,10,4),session=session,clocked_in_at=datetime.fromisoformat(DAY+'T'+t),status='normal'))
  await db.commit()


@pytest.mark.parametrize('uid',[1,4])
@pytest.mark.parametrize('duration,hours,punches,status,work,leave_hours',[
 ('full',None,[],'leave',0,None),
 ('hours',2,[(1,'09:00'),(2,'12:00'),(3,'13:00'),(4,'18:00')],'hours_leave',6,2),
 ('afternoon',None,[(1,'09:00'),(2,'12:00')],'half',3,5),
 ('morning',None,[(3,'13:00'),(4,'18:00')],'half',5,3),
])
def test_immediate_effect(tmp_path,monkeypatch,uid,duration,hours,punches,status,work,leave_hours):
 async def run():
  async with hr_environment(tmp_path,monkeypatch) as (_,factory,c):
   monkeypatch.setattr(payroll,'thai_today',lambda:date(2026,10,18))
   await set_perms(factory,4,['请假'])
   await setup(factory,punches)
   old_payroll=await snapshot(factory)
   payload={'employee_id':1,'start_date':DAY,'end_date':DAY,'duration_type':duration,'hours':hours,'notified_at':'2026-10-03T10:00'}
   r=await c.post(PATH,headers=auth(uid),json=payload)
   assert r.status_code==200,r.text
   assert r.json()=={'message':'已代录 1 条请假，跳过 0 天','created':1,'skipped':0}
   listing=await c.get('/api/v1/attendance/leaves',headers=auth(1))
   assert listing.status_code==200,listing.text
   row=next(x for x in listing.json()['data'] if x['employee_id']==1 and x['leave_date']==DAY)
   assert row['status']=='approved'
   async with factory() as db:
    leave=await db.get(LeaveRequest,row['id'])
    assert leave.reviewed_by==uid and leave.reviewed_at is not None
    assert leave.notified_at==datetime(2026,10,3,10)
   event=await calendar(c)
   assert (event['status'],event['work_hours'],event['leave_hours'])==(status,work,leave_hours)
   assert await snapshot(factory)==old_payroll
   # No automatic recalculation: create a new payroll only via explicit calculation.
   async with factory() as db:
    await db.execute(delete(PayrollRecord).where(PayrollRecord.employee_id==1));await db.commit()
   r_calc=await c.post('/api/v1/payroll/calculate',headers=auth(1),json={'end_date':DAY,'employee_ids':[1]})
   assert r_calc.status_code==200,r_calc.text
   async with factory() as db:
    rec=(await db.execute(select(PayrollRecord).where(PayrollRecord.employee_id==1))).scalar_one()
    assert json.loads(rec.detail)['work_hours']==work
    assert rec.base_pay==work*50
   duplicate=await c.post(PATH,headers=auth(uid),json=payload)
   assert duplicate.status_code==400 and duplicate.json()=={'detail':'该员工这一天已有请假记录'}
   reject=await c.put(f"/api/v1/attendance/leaves/{row['id']}/reject",headers=auth(1),data={'reason':'隔离测试重新代录'})
   assert reject.status_code==200 and reject.json()=={'message':'已驳回'}
   retry=await c.post(PATH,headers=auth(uid),json=payload)
   assert retry.status_code==200 and retry.json()['created']==1
   print('PROXY_RESULT',{'operator':uid,'duration':duration,'response':r.json(),'list':row,'calendar':event,'duplicate':duplicate.json(),'after_reject':retry.json()})
 asyncio.run(run())


def test_pending_employee_leave_blocks_proxy_until_rejected(tmp_path,monkeypatch):
 async def run():
  async with hr_environment(tmp_path,monkeypatch) as (_,factory,c):
   await setup(factory,[(1,'09:00'),(2,'12:00'),(3,'13:00'),(4,'18:00')])
   r=await c.post('/api/v1/attendance/leaves',headers=auth(5),data={'leave_date':DAY,'duration_type':'hours','hours':'2','leave_type':'personal'})
   assert r.status_code==200,r.text
   leave_id=r.json()['id']
   async with factory() as db:assert (await db.get(LeaveRequest,leave_id)).status=='pending'
   assert (await calendar(c))['work_hours']==8
   duplicate=await c.post(PATH,headers=auth(1),json={'employee_id':1,'start_date':DAY,'end_date':DAY})
   assert duplicate.status_code==400 and duplicate.json()['detail']=='该员工这一天已有请假记录'
   r=await c.put(f'/api/v1/attendance/leaves/{leave_id}/approve',headers=auth(1));assert r.status_code==200,r.text
   assert (await calendar(c))['work_hours']==6
 asyncio.run(run())


def test_batch_conflict_atomic_and_old_rows_unchanged(tmp_path,monkeypatch):
 async def run():
  async with hr_environment(tmp_path,monkeypatch) as (_,factory,c):
   async with factory() as db:
    db.add(LeaveRequest(employee_id=1,warehouse_id=1,leave_date=date(2026,10,5),status='pending',duration_type='full'))
    # Multiple existing approved rows must return the duplicate error, not a 500.
    for _ in range(2):db.add(LeaveRequest(employee_id=1,warehouse_id=1,leave_date=date(2026,10,6),status='approved',duration_type='full'))
    await db.commit()
    before=[tuple(r) for r in (await db.execute(select(LeaveRequest.__table__))).all()]
   for start,end in [('2026-10-04','2026-10-05'),('2026-10-06','2026-10-06')]:
    r=await c.post(PATH,headers=auth(1),json={'employee_id':1,'start_date':start,'end_date':end})
    assert r.status_code==400 and r.json()['detail']=='该员工这一天已有请假记录'
   async with factory() as db:assert [tuple(r) for r in (await db.execute(select(LeaveRequest.__table__))).all()]==before
 asyncio.run(run())


def test_only_admin_record_changed():
 root=Path(__file__).resolve().parents[2];name='backend/app/api/v1/attendance.py'
 def functions(source):return {n.name:ast.dump(n,include_attributes=False) for n in ast.parse(source).body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name!='admin_record_leave'}
 assert functions(subprocess.check_output(['git','show','15d53fa:'+name],cwd=root,text=True))==functions(subprocess.check_output(['git','show','cc9660d:'+name],cwd=root,text=True))
 assert not subprocess.check_output(['git','diff','cc9660d','15d53fa','--','frontend','backend/app/models','backend/app/services','backend/app/api/v1/payroll.py','backend/scripts'],cwd=root)


def test_successful_date_range_records_operator(tmp_path,monkeypatch):
 async def run():
  async with hr_environment(tmp_path,monkeypatch) as (_,factory,c):
   r=await c.post(PATH,headers=auth(1),json={'employee_id':1,'start_date':'2026-10-04','end_date':'2026-10-06','duration_type':'hours','hours':2})
   assert r.status_code==200 and r.json()=={'message':'已代录 3 条请假，跳过 0 天','created':3,'skipped':0}
   async with factory() as db:
    rows=(await db.execute(select(LeaveRequest).where(LeaveRequest.employee_id==1).order_by(LeaveRequest.leave_date))).scalars().all()
    assert [r.leave_date.isoformat() for r in rows]==['2026-10-04','2026-10-05','2026-10-06']
    assert all(r.status=='approved' and r.hours==2 and r.reviewed_by==1 and r.reviewed_at is not None for r in rows)
 asyncio.run(run())

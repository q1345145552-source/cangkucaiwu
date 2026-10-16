"""Enabled supervisor employee identity: real HTTP, no management grants, own-only data."""
import asyncio
from datetime import date, datetime
import pytest
from sqlalchemy import select
from app.models import User, Employee, ClockInRecord, LeaveRequest
from app.models.overtime import OvertimeTask, OvertimeAssignment
from app.models.payroll import PayrollRecord
from app.core.security import hash_password
from tests.test_round2_permissions import auth, set_perms, png
from tests.test_round3_permissions import snapshot
from tests.test_round4_permissions import attendance_environment
from app.core.menu_registry import MENU_PERMISSIONS

async def enable(factory):
    async with factory() as db:
        u=await db.get(User,4)
        u.attendance_enabled=True;u.attendance_employee_id=5;u.extra_permissions=[]
        db.add(Employee(id=5,name='supervisor',user_id=4,warehouse_id=1,hire_date=datetime(2026,10,1),salary_template_id=1,deduction_template_id=1))
        db.add(PayrollRecord(id=20,employee_id=5,warehouse_id=1,period='2026-10',half='first',net_pay=9876.54,status='confirmed'))
        for tid,needs in [(20,False),(21,True)]:
            db.add(OvertimeTask(id=tid,warehouse_id=1,date=date(2026,10,10),start_time='18:00',end_time='19:00',hours=1,hourly_rate=0,status='verified',needs_verification=needs,created_by=1))
            db.add(OvertimeAssignment(id=tid,overtime_id=tid,employee_id=5,user_id=4,actual_hours=1,earned_amount=50,confirmed=False))
        await db.commit()

SELF_READS=['/clock-in/today','/clock-in/records?view=self','/attendance/calendar?view=self','/attendance/leaves?view=self','/attendance/rest-days?view=self','/overtime?view=self','/overtime/pending','/overtime/monthly-hours?view=self&month=2026-10','/overtime/limit?view=self','/payroll/my-payslip','/employee-advances/my-debt']

def test_enabled_supervisor_real_self_flow_and_manager_separation(tmp_path,monkeypatch):
 async def run():
  async with attendance_environment(tmp_path,monkeypatch) as (_,factory,c):
   await enable(factory);before=await snapshot(factory)
   for path in SELF_READS:
    r=await c.get('/api/v1'+path,headers=auth(4));assert r.status_code==200,(path,r.text)
   r=await c.post('/api/v1/clock-in',headers=auth(4),data={'session':'1'});assert r.status_code==200,r.text
   today=(await c.get('/api/v1/clock-in/today',headers=auth(4))).json();assert '1' in today['completed']
   again=await c.post('/api/v1/clock-in',headers=auth(4),data={'session':'1'});assert again.json()['duplicate']
   cal=(await c.get('/api/v1/attendance/calendar?view=self&start_date=2026-10-01&end_date=2026-10-31',headers=auth(4))).json()
   assert [e['id'] for e in cal['employees']]==[5],cal
   pays=(await c.get('/api/v1/payroll/my-payslip',headers=auth(4))).json()['data'];assert [r['id'] for r in pays]==[20] and pays[0]['net_pay']==9876.54
   r=await c.post('/api/v1/attendance/leaves?view=self',headers=auth(4),data={'leave_date':'2026-10-17','leave_type':'personal','duration_type':'hours','hours':'2.3'});assert r.status_code==200,r.text
   async with factory() as db: assert (await db.get(LeaveRequest,r.json()['id'])).employee_id==5
   r=await c.post('/api/v1/overtime/20/confirm',headers=auth(4));assert r.status_code==200,r.text
   r=await c.post('/api/v1/overtime/21/dispute',headers=auth(4),data={'reason':'实际工时不符'},files={'file':('proof.png',png(),'image/png')});assert r.status_code==200,r.text
   for path in ['/attendance/calendar','/overtime','/clock-in/records','/payroll']:
    r=await c.get('/api/v1'+path,headers=auth(4));assert r.status_code==403 and '无此操作权限' in r.text,(path,r.text)
   assert await snapshot(factory)==before
   await set_perms(factory,4,[p.label for p in MENU_PERMISSIONS if p.selectable])
   for path in ['/attendance/calendar','/clock-in/records','/overtime']:
    r=await c.get('/api/v1'+path,headers=auth(4));assert r.status_code==200,(path,r.text)
   r=await c.post('/api/v1/overtime/3/verify',headers=auth(4),json={'assignments':[{'assignment_id':3,'actual_hours':1}]});assert r.status_code==200,r.text
   r=await c.post('/api/v1/clock-in/makeup',headers=auth(4),json={'employee_id':1,'date':'2026-10-11','sessions':[1,2,3,4],'reason':'测试补卡'});assert r.status_code==200,r.text
   async with factory() as db:
    u=await db.get(User,4);u.attendance_enabled=False;await db.commit()
   # Same token revoked immediately, management remains available.
   for path in SELF_READS:
    r=await c.get('/api/v1'+path,headers=auth(4));assert r.status_code==403,(path,r.text)
   assert (await c.get('/api/v1/attendance/calendar',headers=auth(4))).status_code==200
 asyncio.run(run())

@pytest.mark.parametrize('uid',[1,2,3,4,5])
def test_roles_not_expanded(tmp_path,monkeypatch,uid):
 async def run():
  async with attendance_environment(tmp_path,monkeypatch) as (_,factory,c):
   # Deliberately set the flag even on ineligible roles.
   async with factory() as db:
    u=await db.get(User,uid);u.attendance_enabled=uid!=4;u.extra_permissions=[p.label for p in MENU_PERMISSIONS if p.selectable];await db.commit()
   for method,path,data in [('POST','/clock-in',{'session':'1'}),('GET','/clock-in/today',None),('GET','/payroll/my-payslip',None),('GET','/overtime/pending',None),('POST','/overtime/1/confirm',None),('POST','/overtime/2/dispute',{'reason':'test'})]:
    r=await c.request(method,'/api/v1'+path,headers=auth(uid),data=data,**({'files':{'file':('proof.png',png(),'image/png')}} if path.endswith('/dispute') else {}))
    assert r.status_code==(200 if uid==5 else 403),(uid,path,r.text)
 asyncio.run(run())

@pytest.mark.parametrize('corruption',['unbound','other_user','other_warehouse','deleted'])
def test_invalid_binding_fail_closed(tmp_path,monkeypatch,corruption):
 async def run():
  async with attendance_environment(tmp_path,monkeypatch) as (_,factory,c):
   await enable(factory)
   async with factory() as db:
    u=await db.get(User,4);e=await db.get(Employee,5)
    if corruption=='unbound':u.attendance_employee_id=None
    if corruption=='other_user':e.user_id=1
    if corruption=='other_warehouse':e.warehouse_id=2
    if corruption=='deleted':e.is_deleted=True
    await db.commit()
   for path in SELF_READS:assert (await c.get('/api/v1'+path,headers=auth(4))).status_code==403,path
 asyncio.run(run())

def test_self_cannot_reach_other_employee_or_warehouse(tmp_path,monkeypatch):
 async def run():
  async with attendance_environment(tmp_path,monkeypatch) as (_,factory,c):
   await enable(factory)
   for tid in [1,4,10]:
    for action in ['confirm','dispute']:
     r=await c.post(f'/api/v1/overtime/{tid}/{action}',headers=auth(4));assert r.status_code in (400,404),r.text
   for eid in [1,2,4]:
    r=await c.get(f'/api/v1/clock-in/photos?view=self&employee_id={eid}&date=2026-10-10',headers=auth(4));assert r.status_code==403,r.text
   r=await c.get('/api/v1/overtime?view=self&employee_id=1',headers=auth(4));assert {t['id'] for t in r.json()['data']}=={20,21}
   r=await c.get('/api/v1/clock-in/records?view=self&user_id=5',headers=auth(4));assert [e['id'] for e in r.json()['employees']]==[5]
 asyncio.run(run())

def test_auth_exposes_live_identity(tmp_path,monkeypatch):
 async def run():
  async with attendance_environment(tmp_path,monkeypatch) as (_,factory,c):
   await enable(factory)
   async with factory() as db:
    u=await db.get(User,4);u.password_hash=hash_password('test-password');await db.commit()
   for path,body in [('/auth/login',{'username':'supervisor','password':'test-password'}),('/auth/me',None)]:
    r=await (c.post('/api/v1'+path,json=body) if body else c.get('/api/v1'+path,headers=auth(4)))
    assert r.status_code==200,r.text
    assert r.json()['attendance_enabled'] is True and r.json()['attendance_employee_id']==5
 asyncio.run(run())

def test_selected_management_warehouse_and_namesake_cannot_change_self_identity(tmp_path,monkeypatch):
 async def run():
  from app.models import UserWarehouse
  async with attendance_environment(tmp_path,monkeypatch) as (_,factory,c):
   await enable(factory)
   async with factory() as db:
    db.add(UserWarehouse(user_id=4,warehouse_id=2))
    # Names deliberately collide, while explicit bindings stay distinct.
    (await db.get(Employee,1)).name='supervisor'
    db.add(ClockInRecord(user_id=4,warehouse_id=2,clock_date=date(2026,10,9),session=1,clocked_in_at=datetime(2026,10,9,9),status='normal'))
    await db.commit()
   h={**auth(4),'X-Warehouse-ID':'2'}
   r=await c.post('/api/v1/clock-in',headers=h,data={'session':'1'});assert r.status_code==200,r.text
   async with factory() as db:
    row=(await db.execute(select(ClockInRecord).where(ClockInRecord.user_id==4,ClockInRecord.clock_date==date(2026,10,16)))).scalar_one();assert row.warehouse_id==1
   r=await c.get('/api/v1/clock-in/records?view=self',headers=h)
   assert [e['id'] for e in r.json()['employees']]==[5]
   assert len(r.json()['records'])==1
   r=await c.get('/api/v1/payroll/my-payslip',headers=h);assert [p['id'] for p in r.json()['data']]==[20]
   r=await c.post('/api/v1/attendance/leaves?view=self',headers=h,data={'leave_date':'2026-10-18'});assert r.status_code==200,r.text
   async with factory() as db:
    leave=await db.get(LeaveRequest,r.json()['id']);assert (leave.employee_id,leave.warehouse_id)==(5,1)
 asyncio.run(run())

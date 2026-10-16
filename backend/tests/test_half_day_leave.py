"""Half-day conversion uses warehouse configuration and actual punches."""
import asyncio
import json
from datetime import date, datetime
from types import SimpleNamespace
import pytest
from sqlalchemy import delete, select
from app.models import Employee, ClockInRecord, LeaveRequest, RestDay, SalaryTemplate, SystemSetting
from app.models.payroll import PayrollRecord
from app.services.half_day_leave import half_day_leave_hours
from app.services.schedule import default_work_schedule
import app.api.v1.payroll as payroll
from tests.test_round2_permissions import auth
from tests.test_round3_permissions import hr_environment, snapshot


@pytest.mark.parametrize('kind,punches,net,leave,attendance',[
 ('morning',[(3,'13:00'),(4,'18:00')],5,3,.625),
 ('afternoon',[(1,'09:00'),(2,'12:00')],3,5,.375),
 ('morning',[(3,'13:00'),(4,'17:00')],4,3,.5),
 ('morning',[(1,'09:00'),(2,'12:00'),(3,'13:00'),(4,'18:00')],5,3,.625),
])
@pytest.mark.parametrize('template_type',['daily','monthly','hourly'])
def test_calendar_and_payroll(tmp_path,monkeypatch,kind,punches,net,leave,attendance,template_type):
 async def run():
  async with hr_environment(tmp_path,monkeypatch) as (_,factory,c):
   monkeypatch.setattr(payroll,'thai_today',lambda:date(2026,10,18))
   async with factory() as db:
    await db.execute(delete(PayrollRecord).where(PayrollRecord.employee_id==1))
    await db.execute(delete(RestDay).where(RestDay.employee_id==1))
    (await db.get(Employee,1)).hire_date=datetime(2026,10,4)
    tpl=await db.get(SalaryTemplate,1);tpl.type=template_type;tpl.amount=12400 if template_type=='monthly' else 400
    for session,t in punches:
     db.add(ClockInRecord(user_id=5,warehouse_id=1,clock_date=date(2026,10,4),session=session,clocked_in_at=datetime.fromisoformat('2026-10-04T'+t),status='normal'))
    db.add(LeaveRequest(employee_id=1,warehouse_id=1,leave_date=date(2026,10,4),duration_type=kind,leave_type='personal',status='approved',notified_at=datetime(2026,10,3)))
    await db.commit()
    original=[tuple(r) for r in (await db.execute(select(LeaveRequest.__table__))).all()]
   before=await snapshot(factory)
   r=await c.get('/api/v1/attendance/calendar?start_date=2026-10-04&end_date=2026-10-04',headers=auth(1));assert r.status_code==200,r.text
   event=next(e for e in r.json()['events'] if e['employee_id']==1)
   assert (event['leave_hours'],event['work_hours'])==(leave,net)
   assert await snapshot(factory)==before
   r=await c.post('/api/v1/payroll/calculate',headers=auth(1),json={'end_date':'2026-10-04','employee_ids':[1]});assert r.status_code==200,r.text
   async with factory() as db:
    rec=(await db.execute(select(PayrollRecord).where(PayrollRecord.employee_id==1))).scalar_one();detail=json.loads(rec.detail)
    assert detail['work_hours']==net
    assert detail['daily_hours'][0]['attendance']==attendance
    assert rec.base_pay==net*50,(rec.base_pay,detail)
    assert [tuple(r) for r in (await db.execute(select(LeaveRequest.__table__))).all()]==original
    print('HALF_DAY',template_type,kind,{'leave_hours':leave,'net_hours':net,'attendance':attendance,'base_pay':rec.base_pay})
   # Change the same configuration source used by the configuration-center API.
   if kind=='morning' and net==5 and len(punches)==2:
    async with factory() as db:
     db.add(SystemSetting(warehouse_id=1,key='schedule_noon_break_start',value='11:00'));await db.commit()
    r=await c.get('/api/v1/attendance/calendar?start_date=2026-10-04&end_date=2026-10-04',headers=auth(1))
    event=next(e for e in r.json()['events'] if e['employee_id']==1)
    assert (event['leave_hours'],event['work_hours'])==(2,5)
    saved=await snapshot(factory)
    await c.get('/api/v1/payroll',headers=auth(1));assert await snapshot(factory)==saved
    r=await c.post(f'/api/v1/payroll/{rec.id}/recalc',headers=auth(1),json={'mode':'recalc','void_reason':'隔离测试作息折算'});assert r.status_code==200,r.text
    async with factory() as db:
     new=(await db.execute(select(PayrollRecord).where(PayrollRecord.recalc_from_id==rec.id))).scalar_one()
     assert json.loads(new.detail)['daily_hours'][0]['attendance']==round(5/7,4)
     assert new.base_pay==pytest.approx(250 if template_type=='hourly' else 285.71,abs=.01)
     await db.execute(delete(SystemSetting).where(SystemSetting.warehouse_id==1,SystemSetting.key=='schedule_noon_break_start'));await db.commit()
    r=await c.get('/api/v1/attendance/calendar?start_date=2026-10-04&end_date=2026-10-04',headers=auth(1))
    assert next(e for e in r.json()['events'] if e['employee_id']==1)['leave_hours']==3
 asyncio.run(run())


def test_timezone_and_missing_punches():
 from datetime import timezone
 day=date(2026,10,4);cfg=default_work_schedule()
 punches=[SimpleNamespace(session=i,clocked_in_at=datetime(2026,10,4,h,tzinfo=timezone.utc)) for i,h in [(3,6),(4,11)]]
 assert half_day_leave_hours(punches,{'morning':True},day,cfg)==(3,5)
 assert half_day_leave_hours(punches[:1],{'morning':True},day,cfg)==(3,0)
 assert half_day_leave_hours(punches,{'morning':True,'afternoon':True},day,cfg)==(8,0)


def test_only_half_day_paths_changed():
 import ast
 import subprocess
 from pathlib import Path
 root=Path(__file__).resolve().parents[2]
 class RemoveHalfDay(ast.NodeTransformer):
  def visit_If(self,node):
   if ast.unparse(node.test).startswith('is_half_day_leave('):return None
   return self.generic_visit(node)
  def visit_IfExp(self,node):
   self.generic_visit(node)
   if isinstance(node.test,ast.BoolOp) and any('is_half_day_leave(' in ast.unparse(v) for v in node.test.values):node.test=node.test.values[0]
   return node
 for module in ('attendance','payroll'):
  filename=f'backend/app/api/v1/{module}.py'
  def functions(source):
   return {n.name:ast.dump(RemoveHalfDay().visit(n),include_attributes=False) for n in ast.parse(source).body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
  assert functions(subprocess.check_output(['git','show','44d6c90:'+filename],cwd=root,text=True))==functions(subprocess.check_output(['git','show','cc9660d:'+filename],cwd=root,text=True))
 for filename in ('backend/app/services/hourly_leave.py','backend/app/services/early_departure_leave.py','backend/app/services/schedule.py'):
  assert (root/filename).read_bytes()==subprocess.check_output(['git','show','44d6c90:'+filename],cwd=root)
 assert not subprocess.check_output(['git','diff','44d6c90','cc9660d','--','frontend/src','backend/app/models','backend/scripts/seed.py'],cwd=root)


@pytest.mark.parametrize('duration,approval,punches,expected',[
 ('full','approved',[],0),
 ('morning','pending',['09:00','12:00','13:00','18:00'],8),
 ('afternoon','rejected',['09:00','12:00','13:00','18:00'],8),
 ('hours','approved',['09:00','12:00','13:00','18:00'],6),
])
def test_other_leave_paths(tmp_path,monkeypatch,duration,approval,punches,expected):
 async def run():
  async with hr_environment(tmp_path,monkeypatch) as (_,factory,c):
   monkeypatch.setattr(payroll,'thai_today',lambda:date(2026,10,18))
   async with factory() as db:
    await db.execute(delete(PayrollRecord).where(PayrollRecord.employee_id==1));await db.execute(delete(RestDay).where(RestDay.employee_id==1))
    (await db.get(Employee,1)).hire_date=datetime(2026,10,4)
    for session,t in enumerate(punches,1):
     db.add(ClockInRecord(user_id=5,warehouse_id=1,clock_date=date(2026,10,4),session=session,clocked_in_at=datetime.fromisoformat('2026-10-04T'+t),status='normal'))
    db.add(LeaveRequest(employee_id=1,warehouse_id=1,leave_date=date(2026,10,4),duration_type=duration,hours=2 if duration=='hours' else None,leave_type='personal',status=approval,notified_at=datetime(2026,10,3)))
    await db.commit()
   r=await c.get('/api/v1/attendance/calendar?start_date=2026-10-04&end_date=2026-10-04',headers=auth(1));assert r.status_code==200,r.text
   assert next(e for e in r.json()['events'] if e['employee_id']==1)['work_hours']==expected
   r=await c.post('/api/v1/payroll/calculate',headers=auth(1),json={'end_date':'2026-10-04','employee_ids':[1]});assert r.status_code==200,r.text
   async with factory() as db:
    rec=(await db.execute(select(PayrollRecord).where(PayrollRecord.employee_id==1))).scalar_one()
    assert json.loads(rec.detail)['work_hours']==expected
    assert rec.base_pay==expected*50
 asyncio.run(run())

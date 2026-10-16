"""Exact reported clock times; one shared decision in calendar and manual payroll calculation."""
import asyncio,json
from datetime import date,datetime
import pytest
from sqlalchemy import select,delete,update
from app.models import Employee,ClockInRecord,LeaveRequest,RestDay,SalaryTemplate,SystemSetting
from app.models.payroll import PayrollRecord
from app.api.v1 import payroll
from tests.test_round3_permissions import hr_environment,snapshot
from tests.test_round2_permissions import auth
from app.services.hourly_leave import hourly_leave_net_hours
from app.services.schedule import default_work_schedule

SAMPLE=['08:41:54','12:02:00','12:48:04','15:25:47']

@pytest.mark.parametrize('punches,leaves,end,expected',[
 (SAMPLE,[2.3],'18:00',5.96),
 (SAMPLE,[1.1,1.2],'18:00',5.96),
 (['09:00:00','12:00:00','13:00:00','18:00:00'],[2],'18:00',6),
 (['09:00:00','12:00:00','13:00:00','15:00:00'],[2],'18:00',5),
 (['09:00:00','12:00:00','13:00:00','17:00:00'],[2],'18:00',6),
 (['09:00:00','12:00:00','13:00:00','19:00:00'],[2],'18:00',7),
 (SAMPLE,[2.3],'16:00',4.23),
 (SAMPLE,[8],'18:00',0),
 (SAMPLE,[9],'18:00',0),
 (SAMPLE,[None],'18:00',0),
 ([],[2],'18:00',0),
])
@pytest.mark.parametrize('template_type',['daily','monthly','hourly'])
def test_calendar_payroll_same_net_hours(tmp_path,monkeypatch,punches,leaves,end,expected,template_type):
 async def run():
  async with hr_environment(tmp_path,monkeypatch) as (_,factory,c):
   monkeypatch.setattr(payroll,'thai_today',lambda:date(2026,10,18))
   async with factory() as db:
    await db.execute(delete(PayrollRecord).where(PayrollRecord.employee_id==1))
    await db.execute(delete(RestDay).where(RestDay.employee_id==1))
    e=await db.get(Employee,1);e.name='Khin Than Dar Tway';e.status='regular';e.hire_date=datetime(2026,10,4)
    tpl=await db.get(SalaryTemplate,1);tpl.type=template_type;tpl.amount=12400 if template_type=='monthly' else 400
    if end!='18:00':db.add(SystemSetting(warehouse_id=1,key='schedule_afternoon_end',value=end))
    # get_work_schedule uses scoped settings keys; exact key verified below.
    for session,t in enumerate(punches,1):
     db.add(ClockInRecord(user_id=5,warehouse_id=1,clock_date=date(2026,10,4),session=session,clocked_in_at=datetime.fromisoformat('2026-10-04T'+t),status='normal'))
    for h in leaves:db.add(LeaveRequest(employee_id=1,warehouse_id=1,leave_date=date(2026,10,4),leave_type='personal',duration_type='hours',hours=h,status='approved',notified_at=datetime(2026,10,3)))
    await db.commit()
    before_leave=[tuple(r) for r in (await db.execute(select(LeaveRequest.__table__))).all()]
   old=await snapshot(factory)
   response=await c.get('/api/v1/attendance/calendar?start_date=2026-10-04&end_date=2026-10-04',headers=auth(1));assert response.status_code==200,response.text
   event=next(e for e in response.json()['events'] if e['employee_id']==1)
   assert event['work_hours']==expected,event
   if leaves==[2.3]:assert event['status_label']=='请假2.3小时'
   assert await snapshot(factory)==old  # Reading never recalculates a saved payroll record.
   r=await c.post('/api/v1/payroll/calculate',headers=auth(1),json={'end_date':'2026-10-04','employee_ids':[1]});assert r.status_code==200,r.text
   async with factory() as db:
    rec=(await db.execute(select(PayrollRecord).where(PayrollRecord.employee_id==1))).scalar_one()
    detail=json.loads(rec.detail);day=detail['daily_hours'][0]
    assert day['hours']==event['work_hours']==detail['work_hours']==expected,(event,detail)
    standard=6 if end=='16:00' else 8
    assert day['attendance']==pytest.approx(expected/standard)
    if template_type in ('daily','hourly','monthly') and leaves==[2.3] and end=='18:00':assert rec.base_pay==298,detail
    assert [tuple(row) for row in (await db.execute(select(LeaveRequest.__table__))).all()]==before_leave
    if punches==SAMPLE and leaves==[2.3] and end=='18:00' and template_type=='daily':print('EXACT_CASE',event['status_label'],event['work_hours'],day,rec.base_pay)
 asyncio.run(run())


def test_only_hourly_branch_changed():
 import ast,subprocess
 from pathlib import Path
 root=Path(__file__).resolve().parents[2]
 class NormalizeHourly(ast.NodeTransformer):
  def visit_If(self,node):
   test=ast.unparse(node.test)
   if test.startswith("lt == 'hours' and lv_hours is not None") or test.startswith('is_hourly_leave('):return None
   if test=="leave_info['hours'] >= standard_hours":node.test=ast.parse('leave_hours_val >= standard_hours',mode='eval').body
   return self.generic_visit(node)
  def visit_Assign(self,node):
   if any(ast.unparse(t) in ("info['hourly_missing']",'net_hourly_hours') for t in node.targets):return None
   return self.generic_visit(node)
  def visit_IfExp(self,node):
   if ast.unparse(node.test).startswith('is_hourly_leave(') or ast.unparse(node.test)=='net_hourly_hours is not None':return self.visit(node.orelse)
   return self.generic_visit(node)
  def visit_Dict(self,node):
   pairs=[(k,v) for k,v in zip(node.keys,node.values) if not(isinstance(k,ast.Constant) and k.value=='work_sched')]
   node.keys=[p[0] for p in pairs];node.values=[p[1] for p in pairs]
   return self.generic_visit(node)
 for module in ('attendance','payroll'):
  name=f'backend/app/api/v1/{module}.py'
  def functions(source):
   return {n.name:ast.dump(NormalizeHourly().visit(n),include_attributes=False) for n in ast.parse(source).body if isinstance(n,(ast.AsyncFunctionDef,ast.FunctionDef))}
  assert functions(subprocess.check_output(['git','show','a19fa60:'+name],cwd=root,text=True))==functions((root/name).read_text()),module
 assert not subprocess.check_output(['git','diff','a19fa60','--','frontend/src','backend/scripts/seed.py','backend/app/models'],cwd=root)


def test_existing_payroll_and_leave_rows_never_rewritten_on_read(tmp_path,monkeypatch):
 async def run():
  async with hr_environment(tmp_path,monkeypatch) as (_,factory,c):
   async with factory() as db:
    (await db.get(PayrollRecord,1)).detail=json.dumps({'daily_hours':[{'date':'2026-10-04','hours':3.66}]})
    await db.execute(delete(RestDay).where(RestDay.employee_id==1))
    for session,t in enumerate(SAMPLE,1):db.add(ClockInRecord(user_id=5,warehouse_id=1,clock_date=date(2026,10,4),session=session,clocked_in_at=datetime.fromisoformat('2026-10-04T'+t),status='normal'))
    db.add(LeaveRequest(employee_id=1,warehouse_id=1,leave_date=date(2026,10,4),leave_type='personal',duration_type='hours',hours=2.3,status='approved'))
    await db.commit()
    leaves=[tuple(row) for row in (await db.execute(select(LeaveRequest.__table__))).all()]
   before=await snapshot(factory)
   r=await c.get('/api/v1/attendance/calendar?start_date=2026-10-04&end_date=2026-10-04',headers=auth(1));assert r.status_code==200,r.text
   assert next(e for e in r.json()['events'] if e['employee_id']==1)['work_hours']==5.96
   assert (await c.get('/api/v1/payroll',headers=auth(1))).status_code==200
   assert await snapshot(factory)==before
   async with factory() as db:assert [tuple(row) for row in (await db.execute(select(LeaveRequest.__table__))).all()]==leaves
 asyncio.run(run())


@pytest.mark.parametrize('stamp',['2026-10-04T15:25:47','2026-10-04T15:25:47+07:00','2026-10-04T08:25:47+00:00'])
def test_thailand_clock_timezone(stamp):
 assert hourly_leave_net_hours(5.963611111,2.3,datetime.fromisoformat(stamp),date(2026,10,4),default_work_schedule(),8)==5.96

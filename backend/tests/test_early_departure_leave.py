"""Approved leave exempts only early departure; hours, late penalties and old records remain unchanged."""
import asyncio,json,ast,subprocess
from pathlib import Path
from datetime import date,datetime
import pytest
from sqlalchemy import select,delete
from app.models import Employee,ClockInRecord,LeaveRequest,RestDay,SystemSetting
from app.models.payroll import PayrollRecord
import app.api.v1.payroll as payroll
from tests.test_round2_permissions import auth
from tests.test_round3_permissions import hr_environment,snapshot

SAMPLE=['08:41:54','12:02:00','12:48:04','15:25:47']

@pytest.mark.parametrize('duration,leave_hours,approval,last,early_expected',[
 ('hours',2.3,'approved','15:25:47',0),
 ('hours',.5,'approved','15:00:00',50),
 (None,None,None,'16:00:00',50),
 ('afternoon',None,'approved','16:00:00',0),
 ('morning',None,'approved','16:00:00',50),
 ('full',None,'approved','16:00:00',0),
 ('hours',None,'approved','16:00:00',0),
 ('hours',2.3,'pending','16:00:00',50),
 ('full',None,'rejected','16:00:00',50),
 ('hours',1.5,'approved','16:00:00',0),  # Exact 0.5h tolerance boundary.
 ('hours',1.5,'approved','15:59:59',50),
 ('hours',0,'approved','17:15:00',25),
 ('hours',0,'approved','17:30:00',0),
])
def test_manual_recalc_only_early_penalty_changes(tmp_path,monkeypatch,duration,leave_hours,approval,last,early_expected):
 async def run():
  async with hr_environment(tmp_path,monkeypatch) as (_,factory,c):
   monkeypatch.setattr(payroll,'thai_today',lambda:date(2026,10,18))
   async with factory() as db:
    await db.execute(delete(PayrollRecord).where(PayrollRecord.employee_id==1))
    await db.execute(delete(RestDay).where(RestDay.employee_id==1))
    emp=await db.get(Employee,1);emp.name='Khin Than Dar Tway';emp.status='regular';emp.hire_date=datetime(2026,10,4)
    times=(['09:00:00','12:00:00','13:00:00'] if duration is None else SAMPLE[:3])+[last]
    for session,t in enumerate(times,1):db.add(ClockInRecord(user_id=5,warehouse_id=1,clock_date=date(2026,10,4),session=session,clocked_in_at=datetime.fromisoformat('2026-10-04T'+t),status='normal'))
    if duration:db.add(LeaveRequest(employee_id=1,warehouse_id=1,leave_date=date(2026,10,4),duration_type=duration,hours=leave_hours,leave_type='personal',status=approval,notified_at=datetime(2026,10,3)))
    await db.commit()
    original_leaves=[tuple(r) for r in (await db.execute(select(LeaveRequest.__table__))).all()]
   # Calculate an old-rule fixture using the previous predicate, then restore the new rule.
   new_rule=payroll.leave_covers_early_departure
   monkeypatch.setattr(payroll,'leave_covers_early_departure',lambda *args:False)
   r=await c.post('/api/v1/payroll/calculate',headers=auth(1),json={'end_date':'2026-10-04','employee_ids':[1]});assert r.status_code==200,r.text
   async with factory() as db:old=(await db.execute(select(PayrollRecord).where(PayrollRecord.employee_id==1))).scalar_one();old_id=old.id;old_detail=json.loads(old.detail);old_amount=old.early_penalty
   before=await snapshot(factory)
   monkeypatch.setattr(payroll,'leave_covers_early_departure',new_rule)
   # Reads never alter the saved old paycheck.
   await c.get('/api/v1/attendance/calendar?start_date=2026-10-04&end_date=2026-10-04',headers=auth(1));await c.get('/api/v1/payroll',headers=auth(1))
   assert await snapshot(factory)==before
   r=await c.post(f'/api/v1/payroll/{old_id}/recalc',headers=auth(1),json={'mode':'recalc','void_reason':'测试已批准请假不罚早退'});assert r.status_code==200,r.text
   async with factory() as db:
    rec=(await db.execute(select(PayrollRecord).where(PayrollRecord.recalc_from_id==old_id))).scalar_one()
    detail=json.loads(rec.detail)
    assert rec.early_penalty==early_expected,(rec.early_penalty,r.text,detail)
    assert detail['work_hours']==old_detail['work_hours']
    assert detail['daily_hours']==old_detail['daily_hours']
    assert rec.late_penalty==0
    assert [tuple(row) for row in (await db.execute(select(LeaveRequest.__table__))).all()]==original_leaves
    if duration=='hours' and leave_hours==2.3 and approval=='approved' and last=='15:25:47':
     assert detail['work_hours']==5.96 and rec.base_pay==298 and rec.net_pay==298
     print('EXACT_RECALC',{'hours':detail['work_hours'],'early_before':old_amount,'early_after':rec.early_penalty,'net_pay':rec.net_pay})
    if duration is None:
     assert detail['work_hours']==6
     print('NO_LEAVE',{'hours':detail['work_hours'],'early_penalty':rec.early_penalty})
 asyncio.run(run())


@pytest.mark.parametrize('late_status,late_amount',[('late_half',25),('late_one',50)])
def test_late_penalties_unchanged_when_leave_exempts_early(tmp_path,monkeypatch,late_status,late_amount):
 async def run():
  async with hr_environment(tmp_path,monkeypatch) as (_,factory,c):
   monkeypatch.setattr(payroll,'thai_today',lambda:date(2026,10,18))
   async with factory() as db:
    await db.execute(delete(PayrollRecord).where(PayrollRecord.employee_id==1));await db.execute(delete(RestDay).where(RestDay.employee_id==1))
    (await db.get(Employee,1)).hire_date=datetime(2026,10,4)
    for session,t in enumerate(['09:20:00' if late_status=='late_half' else '09:40:00','12:00:00','13:00:00','16:00:00'],1):
     db.add(ClockInRecord(user_id=5,warehouse_id=1,clock_date=date(2026,10,4),session=session,clocked_in_at=datetime.fromisoformat('2026-10-04T'+t),status=late_status if session==1 else 'normal'))
    db.add(LeaveRequest(employee_id=1,warehouse_id=1,leave_date=date(2026,10,4),leave_type='personal',duration_type='afternoon',status='approved',notified_at=datetime(2026,10,3)))
    await db.commit()
   r=await c.post('/api/v1/payroll/calculate',headers=auth(1),json={'end_date':'2026-10-04','employee_ids':[1]});assert r.status_code==200,r.text
   async with factory() as db:
    rec=(await db.execute(select(PayrollRecord).where(PayrollRecord.employee_id==1))).scalar_one()
    assert rec.early_penalty==0 and rec.late_penalty==late_amount
 asyncio.run(run())


@pytest.mark.parametrize('info,clock,schedule,expected',[
 ({'hours_has':True,'hours':2.3},'15:25:47',{},True),
 ({'hours_has':True,'hours':.5},'15:00:00',{},False),
 ({'hours_has':True,'hours':.5},'15:00:00',{'afternoon_end':'16:00'},True),
 ({'hours_has':True,'hours':1.1+1.2},'15:25:47',{},True),
 ({'morning':True},'16:00:00',{},False),
 ({'afternoon':True},'12:50:00',{},False),
 ({'afternoon':True},'12:50:00',{'noon_break_end':'12:30'},True),
 ({'full':True},'12:00:00',{},True),
])
def test_scope_configuration_and_tolerance(info,clock,schedule,expected):
 from app.services.early_departure_leave import leave_covers_early_departure
 from app.services.schedule import default_work_schedule
 cfg={**default_work_schedule(),**schedule}
 assert leave_covers_early_departure(info,datetime.fromisoformat('2026-10-04T'+clock),date(2026,10,4),cfg)==expected


def test_source_change_is_only_early_departure_predicate():
 root=Path(__file__).resolve().parents[2]
 filename='backend/app/api/v1/payroll.py'
 before=ast.parse(subprocess.check_output(['git','show','3a88d08:'+filename],cwd=root,text=True));after=ast.parse(subprocess.check_output(['git','show','44d6c90:'+filename],cwd=root,text=True))
 class RemoveExemption(ast.NodeTransformer):
  def visit_If(self,node):
   if isinstance(node.test,ast.BoolOp) and len(node.test.values)==2 and ast.unparse(node.test.values[0])=='s4 is not None' and 'leave_covers_early_departure(' in ast.unparse(node.test.values[1]):node.test=node.test.values[0]
   return self.generic_visit(node)
 def functions(tree):return {n.name:ast.dump(RemoveExemption().visit(n),include_attributes=False) for n in tree.body if isinstance(n,(ast.AsyncFunctionDef,ast.FunctionDef))}
 assert functions(before)==functions(after)
 for name in ('backend/app/api/v1/attendance.py','backend/app/services/hourly_leave.py'):
  assert subprocess.check_output(['git','show','44d6c90:'+name],cwd=root)==subprocess.check_output(['git','show','3a88d08:'+name],cwd=root)
 assert not subprocess.check_output(['git','diff','3a88d08','44d6c90','--','frontend/src','backend/app/models','backend/scripts/seed.py'],cwd=root)

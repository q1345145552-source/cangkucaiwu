"""Same clock records -> same payroll; role/identity changes only efficiency population."""
import asyncio,json
from datetime import date,datetime
from sqlalchemy import select
from app.models import User,Employee,ClockInRecord
from app.models.payroll import PayrollRecord
from app.models.overtime import OvertimeAssignment,OvertimeTask
from app.api.v1.efficiency import _compute_week
from tests.test_round2_permissions import auth
from tests.test_round3_permissions import hr_environment,snapshot
from tests.test_round15_employee_self import enable


def test_same_payroll_and_efficiency_population(tmp_path,monkeypatch):
 async def run():
  async with hr_environment(tmp_path,monkeypatch) as (_,factory,c):
   await enable(factory)
   import app.api.v1.payroll as payroll
   monkeypatch.setattr(payroll,"thai_today",lambda:date(2026,10,18))
   async with factory() as db:
    # A new payroll period, same template, dates, status and clocks for both people.
    sup=await db.get(Employee,5);labor=await db.get(Employee,1)
    (await db.get(PayrollRecord,20)).settle_end_date=date(2026,10,15)
    for e in (sup,labor):e.hire_date=datetime(2026,10,16);e.status='regular';e.salary_template_id=1;e.deduction_template_id=1
    for uid in (4,5):
     for day in (16,17):
      for session,hour in ((1,9),(2,12),(3,13),(4,18)):
       db.add(ClockInRecord(user_id=uid,warehouse_id=1,clock_date=date(2026,10,day),session=session,clocked_in_at=datetime(2026,10,day,hour),status='normal'))
    await db.commit()
   before=await snapshot(factory)
   r=await c.post('/api/v1/payroll/calculate',headers=auth(1),json={'end_date':'2026-10-17'})
   assert r.status_code==200,r.text
   async with factory() as db:
    rows=(await db.execute(select(PayrollRecord).where(PayrollRecord.settle_start_date==date(2026,10,16),PayrollRecord.employee_id.in_([1,5])))).scalars().all()
    assert len(rows)==2,r.text
    a,b=sorted(rows,key=lambda r:r.employee_id)
    for field in ('attendance_days','base_pay','gross_pay','net_pay','total_deductions','late_penalty','absence_deduction'):
     assert getattr(a,field)==getattr(b,field),(field,getattr(a,field),getattr(b,field))
    assert json.loads(a.detail)['work_hours']==json.loads(b.detail)['work_hours']==16
    numbers={str(r.employee_id):{'hours':json.loads(r.detail)['work_hours'],'base_pay':r.base_pay,'net_pay':r.net_pay} for r in rows}
    week=await _compute_week(db,1,date(2026,10,12),date(2026,10,18))
    assert week['regular_hours']==32 and week['person_times']==4,week
    ids=[e['employee_id'] for e in week['employees']];assert 5 in ids
   listed=await c.get('/api/v1/payroll?period=2026-10',headers=auth(1));assert listed.status_code==200,listed.text
   records=listed.json()['data'];assert all(r['is_supervisor'] for r in records if r['employee_id']==5)
   assert all(not r['is_supervisor'] for r in records if r['employee_id']==1)
   # Reads and identity changes never rewrite existing payroll rows.
   after=await snapshot(factory);assert [r for r in after if r[0] in {v[0] for v in before}]==before
   off=await c.put('/api/v1/users/4',headers=auth(1),json={'attendance_enabled':False});assert off.status_code==200,off.text
   async with factory() as db:
    weekoff=await _compute_week(db,1,date(2026,10,12),date(2026,10,18))
    assert weekoff['regular_hours']==16 and weekoff['person_times']==2,weekoff
    assert all(e['user_id']!=4 and e['employee_id']!=5 for e in weekoff['employees'])
   assert await snapshot(factory)==after
   historical=(await c.get('/api/v1/payroll?period=2026-10',headers=auth(1))).json()['data']
   assert all(r['is_supervisor'] for r in historical if r['employee_id']==5)
   print('R16_ACTUAL',json.dumps({'payroll':numbers,'efficiency_on':[week['regular_hours'],week['person_times']],'efficiency_off':[weekoff['regular_hours'],weekoff['person_times']]}))
 asyncio.run(run())


def test_other_account_roles_and_disabled_supervisor_do_not_enter_efficiency(tmp_path,monkeypatch):
 async def run():
  from app.models import UserWarehouse
  from app.models.labor_efficiency import EfficiencyManualHour
  async with hr_environment(tmp_path,monkeypatch) as (_,factory,c):
   await enable(factory)
   async with factory() as db:
    db.add(User(id=9,username='off-supervisor',display_name='off',role='supervisor',warehouse_id=1,password_hash='unused',attendance_enabled=False))
    db.add(UserWarehouse(user_id=9,warehouse_id=1))
    for eid,uid in [(6,3),(7,1),(8,2),(9,9)]:
     u=await db.get(User,uid);u.attendance_employee_id=eid
     if uid!=9:u.attendance_enabled=True
     if uid==2:u.warehouse_id=None  # Super admins commonly have no primary warehouse.
     db.add(Employee(id=eid,user_id=uid,warehouse_id=1,name='excluded-'+str(uid),salary_template_id=1,deduction_template_id=1))
    db.add(ClockInRecord(user_id=4,warehouse_id=1,clock_date=date(2026,10,17),session=1,clocked_in_at=datetime(2026,10,17,9),status='normal'))
    db.add(OvertimeTask(id=30,warehouse_id=1,date=date(2026,10,16),start_time='18:00',end_time='19:00',hours=1,status='completed',created_by=1))
    for eid,uid in [(1,5),(5,4),(6,3),(7,1),(8,2),(9,9)]:
     for session,h in [(1,9),(2,12),(3,13),(4,18)]:
      db.add(ClockInRecord(user_id=uid,warehouse_id=1,clock_date=date(2026,10,16),session=session,clocked_in_at=datetime(2026,10,16,h),status='normal'))
     db.add(OvertimeAssignment(overtime_id=30,employee_id=eid,user_id=uid,confirmed=True,actual_hours=1,earned_amount=50))
    await db.commit()
    week=await _compute_week(db,1,date(2026,10,12),date(2026,10,18))
    assert week['regular_hours']==16 and week['overtime_hours']==2,week
    assert {e['user_id'] for e in week['employees'] if e['user_id']}=={4,5},week
   manual=await c.put('/api/v1/efficiency/manual-hour',headers=auth(1),json={'employee_id':5,'date':'2026-10-17','hours':3.5});assert manual.status_code==200,manual.text
   async with factory() as db:
    supplemented=await _compute_week(db,1,date(2026,10,12),date(2026,10,18));assert supplemented['regular_hours']==19.5,supplemented
   await c.put('/api/v1/users/4',headers=auth(1),json={'attendance_enabled':False})
   async with factory() as db:
    off=await _compute_week(db,1,date(2026,10,12),date(2026,10,18))
    assert off['regular_hours']==8 and off['overtime_hours']==1,off
 asyncio.run(run())


def test_calculation_formulas_and_other_payroll_actions_unchanged():
 import ast,subprocess
 from pathlib import Path
 root=Path(__file__).resolve().parents[2]
 def functions(source):return {n.name:ast.dump(n,include_attributes=False) for n in ast.parse(source).body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
 for file,allowed in [('payroll',{'list_payroll'}),('efficiency',{'_compute_week','_compute_overtime_hours'})]:
  name=f'backend/app/api/v1/{file}.py'
  before=functions(subprocess.check_output(['git','show','ed3d03b:'+name],text=True,cwd=root));after=functions((root/name).read_text())
  assert {k:v for k,v in before.items() if k not in allowed}=={k:v for k,v in after.items() if k not in allowed}

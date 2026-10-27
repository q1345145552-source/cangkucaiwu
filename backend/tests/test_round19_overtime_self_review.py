"""Only overtime verification changes: supervisor self-review denied, audit per person."""
import ast,asyncio,json,subprocess
from datetime import date,datetime
from pathlib import Path
import pytest
from fastapi import HTTPException
from sqlalchemy import select,delete
from app.models import User,Employee,SalaryTemplate,ClockInRecord
from app.models.overtime import OvertimeTask,OvertimeAssignment
from app.models.payroll import PayrollRecord
from app.models.data_change_history import DataChangeHistory
import app.api.v1.overtime as overtime
import app.api.v1.payroll as payroll
from tests.test_round2_permissions import auth,set_perms,png
from tests.test_round3_permissions import hr_environment,snapshot
from tests.test_round15_employee_self import enable

async def setup(factory):
 await enable(factory)
 await set_perms(factory,4,['加班'])
 async with factory() as db:
  await db.execute(delete(OvertimeAssignment));await db.execute(delete(OvertimeTask))
  (await db.get(SalaryTemplate,1)).overtime_half_hour_fee=25
  await db.commit()

async def create(c,employees,uid=4,day='2026-10-16'):
 r=await c.post('/api/v1/overtime',headers=auth(uid),json={'employee_ids':employees,'date':day,'start_time':'18:00','end_time':'19:00'})
 assert r.status_code==200,r.text
 return r.json()['id']

async def assignments(factory,tid):
 async with factory() as db:return (await db.execute(select(OvertimeAssignment).where(OvertimeAssignment.overtime_id==tid).order_by(OvertimeAssignment.id))).scalars().all()

async def verify(c,tid,ids,uid=4,hours=1):
 return await c.post(f'/api/v1/overtime/{tid}/verify',headers=auth(uid),json={'assignments':[{'assignment_id':i,'actual_hours':hours} for i in ids]})

async def state(factory):
 async with factory() as db:return {m.__tablename__:[tuple(r) for r in (await db.execute(select(m.__table__).order_by(m.id))).all()] for m in (OvertimeTask,OvertimeAssignment,DataChangeHistory)}


def test_three_required_flows_and_audit(tmp_path,monkeypatch):
 async def run():
  async with hr_environment(tmp_path,monkeypatch) as (_,factory,c):
   await setup(factory)
   tid=await create(c,[5]);own=(await assignments(factory,tid))[0]
   before=await state(factory)
   denied=await verify(c,tid,[own.id]);assert denied.status_code==403 and denied.json()=={'detail':'本人不能核实自己的加班'}
   assert await state(factory)==before
   other=await create(c,[1]);labor=(await assignments(factory,other))[0]
   allowed=await verify(c,other,[labor.id]);assert allowed.status_code==200,allowed.text
   assert allowed.json()=={'message':'加班核实完成','verified_count':1,'skipped_count':0,'skipped_names':[],'total_amount':50.0,'status':'已核实'}
   admin=await verify(c,tid,[own.id],uid=1);assert admin.status_code==200 and admin.json()['verified_count']==1 and admin.json()['total_amount']==50
   logs=await c.get('/api/v1/history?module=overtime',headers=auth(1));assert logs.status_code==200,logs.text
   assert logs.json()['total']==2
   assert {r['operator_id'] for r in logs.json()['data']}=={1,4}
   for row in logs.json()['data']:
    assert row['operation_type']=='verify' and row['after_data']['verified_by']==row['operator_id'] and row['after_data']['verified_at']
    assert row['record_id'] in (own.id,labor.id) and row['after_data']['earned_amount']==50
   print('ROUND19_REQUIRED',json.dumps({'self':{'status':denied.status_code,'body':denied.json()},'other':allowed.json(),'admin':admin.json(),'audits':logs.json()['data']},ensure_ascii=False))
 asyncio.run(run())


@pytest.mark.parametrize('uid,expected',[(1,200),(2,403),(3,403),(5,403)])
def test_admin_superadmin_and_other_roles(tmp_path,monkeypatch,uid,expected):
 async def run():
  async with hr_environment(tmp_path,monkeypatch) as (_,factory,c):
   await setup(factory);await set_perms(factory,3,['加班'])
   tid=await create(c,[5]);a=(await assignments(factory,tid))[0]
   r=await verify(c,tid,[a.id],uid=uid);assert r.status_code==expected,r.text
   if expected==200:
    async with factory() as db:
     h=(await db.execute(select(DataChangeHistory).where(DataChangeHistory.module=='overtime'))).scalar_one()
     assert h.operator_id==uid and h.after_data['verified_by']==uid
 asyncio.run(run())


@pytest.mark.parametrize('identity',['assignment','archive','attendance_link'])
def test_three_account_id_paths_no_name_check(tmp_path,monkeypatch,identity):
 async def run():
  async with hr_environment(tmp_path,monkeypatch) as (_,factory,c):
   await setup(factory);tid=await create(c,[5],uid=1);a=(await assignments(factory,tid))[0]
   async with factory() as db:
    e=await db.get(Employee,5);u=await db.get(User,4);r=await db.get(OvertimeAssignment,a.id)
    if identity=='assignment':e.user_id=None;u.attendance_employee_id=None
    if identity=='archive':r.user_id=None;u.attendance_employee_id=None
    if identity=='attendance_link':e.user_id=None;r.user_id=None
    e.name='完全不同的名字';await db.commit()
   r=await verify(c,tid,[a.id]);assert r.status_code==403 and r.json()['detail']=='本人不能核实自己的加班'
 asyncio.run(run())


def test_mixed_batch_preflight_and_only_other_person_allowed(tmp_path,monkeypatch):
 async def run():
  async with hr_environment(tmp_path,monkeypatch) as (_,factory,c):
   await setup(factory);tid=await create(c,[1,5]);rows=await assignments(factory,tid)
   before=await state(factory)
   r=await verify(c,tid,[x.id for x in rows]);assert r.status_code==403
   assert await state(factory)==before
   labor=next(x for x in rows if x.employee_id==1);own=next(x for x in rows if x.employee_id==5)
   async with factory() as db:(await db.get(Employee,1)).name='supervisor';await db.commit()
   r=await verify(c,tid,[labor.id]);assert r.status_code==200 and r.json()['status']=='待核实',r.text
   r=await verify(c,tid,[own.id],uid=1);assert r.status_code==200 and r.json()['status']=='已核实'
 asyncio.run(run())


def test_employee_confirm_dispute_and_salary_unchanged(tmp_path,monkeypatch):
 async def run():
  async with hr_environment(tmp_path,monkeypatch) as (_,factory,c):
   monkeypatch.setattr(payroll,'thai_today',lambda:date(2026,10,20))
   await setup(factory);tid=await create(c,[1,5]);a=await assignments(factory,tid)
   r=await verify(c,tid,[x.id for x in a],uid=1,hours=1.1);assert r.status_code==200 and r.json()['total_amount']==150,r.text
   for uid in (4,5):
    r=await c.post(f'/api/v1/overtime/{tid}/confirm',headers=auth(uid));assert r.status_code==200 and r.json()['earned_amount']==75,r.text
   # Separate task: the supervisor and labor can still dispute their own verified hours.
   other=await create(c,[1,5],day='2026-10-17');a=await assignments(factory,other)
   r=await verify(c,other,[x.id for x in a],uid=1);assert r.status_code==200
   for uid in (4,5):
    r=await c.post(f'/api/v1/overtime/{other}/dispute',headers=auth(uid),data={'reason':'实际小时有差异'},files={'file':('test.png',png(),'image/png')});assert r.status_code==200,r.text
   # Reverification clears disputes using the unchanged original logic, supervisor only verifies the labor.
   labor=next(x for x in a if x.employee_id==1);own=next(x for x in a if x.employee_id==5)
   assert (await verify(c,other,[labor.id])).status_code==200
   assert (await verify(c,other,[own.id],uid=1)).status_code==200
   # Actual payroll still uses the verified/confirmed 1.1h rounded up to 3 half-hours, 75 per employee.
   async with factory() as db:
    (await db.get(Employee,1)).hire_date=datetime(2026,10,16)
    for session,hour in ((1,9),(2,12),(3,13),(4,18)):
     db.add(ClockInRecord(user_id=5,warehouse_id=1,clock_date=date(2026,10,16),session=session,clocked_in_at=datetime(2026,10,16,hour),status='normal'))
    await db.commit()
   r=await c.post('/api/v1/payroll/calculate',headers=auth(1),json={'end_date':'2026-10-16','employee_ids':[1]});assert r.status_code==200,r.text
   async with factory() as db:
    rec=(await db.execute(select(PayrollRecord).where(PayrollRecord.employee_id==1,PayrollRecord.settle_start_date==date(2026,10,16)))).scalar_one()
    assert rec.overtime_pay==75 and rec.base_pay==400 and rec.net_pay==475
   print('ROUND19_PAYROLL',{'actual_hours':1.1,'half_hours':3,'overtime_pay':75,'base_pay':400,'net_pay':475})
 asyncio.run(run())


def test_skipped_confirmed_self_record_not_modified(tmp_path,monkeypatch):
 async def run():
  async with hr_environment(tmp_path,monkeypatch) as (_,factory,c):
   await setup(factory);tid=await create(c,[1,5]);rows=await assignments(factory,tid)
   own=next(x for x in rows if x.employee_id==5)
   assert (await verify(c,tid,[own.id],uid=1)).status_code==200
   assert (await c.post(f'/api/v1/overtime/{tid}/confirm',headers=auth(4))).status_code==200
   r=await verify(c,tid,[x.id for x in rows],hours=2)
   assert r.status_code==200 and r.json()['verified_count']==1 and r.json()['skipped_count']==1,r.text
   own2=next(x for x in await assignments(factory,tid) if x.id==own.id)
   assert own2.actual_hours==1 and own2.earned_amount==50
 asyncio.run(run())


def test_audit_failure_rolls_back_verification(tmp_path,monkeypatch):
 async def run():
  async with hr_environment(tmp_path,monkeypatch) as (_,factory,c):
   await setup(factory);tid=await create(c,[1]);a=(await assignments(factory,tid))[0];before=await state(factory)
   async def fail(db,**kwargs):
    await db.flush();raise HTTPException(500,'模拟核实日志失败')
   monkeypatch.setattr(overtime,'record_history',fail)
   r=await verify(c,tid,[a.id]);assert r.status_code==500
   assert await state(factory)==before
 asyncio.run(run())


def test_foreign_task_and_assignment_rejected(tmp_path,monkeypatch):
 async def run():
  async with hr_environment(tmp_path,monkeypatch) as (_,factory,c):
   await setup(factory);tid=await create(c,[1]);a=(await assignments(factory,tid))[0]
   async with factory() as db:
    db.add(OvertimeTask(id=100,warehouse_id=2,date=date(2026,10,16),start_time='18:00',end_time='19:00',hours=1,created_by=1,needs_verification=True))
    db.add(OvertimeAssignment(id=100,overtime_id=100,employee_id=2,user_id=6));await db.commit()
   assert (await verify(c,100,[100])).status_code==404
   assert (await verify(c,tid,[100])).status_code==400
 asyncio.run(run())


def test_only_verify_predicate_and_audit_changed():
 root=Path(__file__).resolve().parents[2];name='backend/app/api/v1/overtime.py'
 old=ast.parse(subprocess.check_output(['git','show','fa7708a:'+name],cwd=root,text=True));new=ast.parse(subprocess.check_output(['git','show','e950142:'+name],cwd=root,text=True))
 class Normalize(ast.NodeTransformer):
  def visit_If(self,node):
   if ast.unparse(node.test)=='current_user.role == Role.SUPERVISOR':return None
   if ast.unparse(node.test).startswith('current_user.role not in'):
    node.test.comparators[0].elts=[x for x in node.test.comparators[0].elts if ast.unparse(x)!='Role.SUPER_ADMIN']
   return self.generic_visit(node)
  def visit_Assign(self,node):
   if any(ast.unparse(t) in ('verified_at','audit_before') for t in node.targets):return None
   return self.generic_visit(node)
  def visit_Expr(self,node):
   if isinstance(node.value,ast.Await) and isinstance(node.value.value,ast.Call) and getattr(node.value.value.func,'id','')=='record_history':return None
   return self.generic_visit(node)
 def functions(tree):return {n.name:ast.dump(Normalize().visit(n) if n.name=='verify_overtime' else n,include_attributes=False) for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
 assert functions(old)==functions(new)
 assert not subprocess.check_output(['git','diff','fa7708a','e950142','--','frontend','backend/app/api/v1/payroll.py','backend/app/api/v1/attendance.py','backend/app/api/v1/clock_in.py','backend/app/models','backend/scripts'],cwd=root)


def test_monthly_limit_hours_and_cancel_unchanged(tmp_path,monkeypatch):
 async def run():
  async with hr_environment(tmp_path,monkeypatch) as (_,factory,c):
   await setup(factory)
   tid=await create(c,[1]);a=(await assignments(factory,tid))[0]
   assert (await verify(c,tid,[a.id])).status_code==200
   assert (await c.post(f'/api/v1/overtime/{tid}/confirm',headers=auth(5))).status_code==200
   pending=await create(c,[1],day='2026-10-17');other=(await assignments(factory,pending))[0]
   r=await c.put('/api/v1/overtime/limit',headers=auth(1),json={'max_hours':1});assert r.status_code==200,r.text
   before=await state(factory)
   r=await verify(c,pending,[other.id]);assert r.status_code==400 and '上限' in r.text,r.text
   assert await state(factory)==before
   r=await c.post('/api/v1/overtime',headers=auth(4),json={'employee_ids':[1],'date':'2026-10-18','start_time':'18:00','end_time':'19:00'})
   assert r.status_code==400 and '上限' in r.text,r.text
   monthly=await c.get('/api/v1/overtime/monthly-hours?month=2026-10',headers=auth(4));assert monthly.status_code==200,monthly.text
   row=next(x for x in monthly.json()['data'] if x['employee_id']==1)
   assert (row['total_hours'],row['total_amount'],row['task_count'])==(1,50,1)
   r=await c.delete(f'/api/v1/overtime/{pending}',headers=auth(4));assert r.status_code==200,r.text
   async with factory() as db:
    assert await db.get(OvertimeTask,pending) is None
    assert not (await db.execute(select(OvertimeAssignment).where(OvertimeAssignment.overtime_id==pending))).scalars().all()
 asyncio.run(run())

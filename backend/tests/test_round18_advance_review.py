"""Round 18: admin-only advance review; only approved debt enters payroll."""
import asyncio,ast,json,subprocess
from pathlib import Path
from datetime import date,datetime
import pytest
from fastapi import HTTPException
from sqlalchemy import select
from app.models import Employee,ClockInRecord
from app.models.employee_advance import EmployeeAdvance
from app.models.payroll import PayrollRecord
from app.models.data_change_history import DataChangeHistory
import app.api.v1.employee_advance as advance_api
import app.api.v1.payroll as payroll
from tests.test_round2_permissions import auth,set_perms
from tests.test_round3_permissions import snapshot
from tests.round3_flow_support import execute_advance, approve_advance, post_ok
from tests.advance_funding_test_support import funded_hr_environment as hr_environment

async def add(factory,status='pending',amount=100,wid=1,eid=1):
 async with factory() as db:
  r=EmployeeAdvance(warehouse_id=wid,employee_id=eid,amount=amount,advance_date=date(2026,10,16),period='2026-10',half='second_half',source='supervisor',status='unpaid',approval_status=status,deducted_amount=0,funding_source='company_account',payment_account_id=1,operator_id=4,expense_tracking_enabled=(status=='pending'))
  db.add(r);await db.commit();return r.id

async def get(factory,aid):
 async with factory() as db:
  r=await db.get(EmployeeAdvance,aid)
  return {'approval_status':r.approval_status,'reviewer_id':r.reviewer_id,'reviewed_at':r.reviewed_at,'reject_reason':r.reject_reason,'deducted_amount':r.deducted_amount,'status':r.status}


def test_admin_review_reject_state_guards_and_history(tmp_path,monkeypatch):
 async def run():
  async with hr_environment(tmp_path,monkeypatch) as (_,factory,c):
   aid=await add(factory);rid=await add(factory)
   old=await snapshot(factory)
   approved=await approve_advance(factory,c,aid)
   a=approved.json();assert a['approval_status']=='approved_ready' and a['reviewer_id']==1 and a['reviewed_at'] and a['reject_reason'] is None
   await post_ok(c,f'/employee-advances/{aid}/execute',3)
   rejected=await c.post(f'/api/v1/employee-advances/{rid}/reject',headers=auth(1),json={'reject_reason':' 不符合本次预支规则 '});assert rejected.status_code==200,rejected.text
   b=rejected.json();assert b['approval_status']=='rejected' and b['reviewer_id']==1 and b['reviewed_at'] and b['reject_reason']=='不符合本次预支规则'
   for path,body,message in [(f'{aid}/approve',None,'该预支已通过'),(f'{rid}/approve',None,'该预支已驳回，不能审批通过'),(f'{aid}/reject',{'reject_reason':'x'},'该预支已通过，不能驳回'),(f'{rid}/reject',{'reject_reason':'x'},'该预支已驳回')]:
    r=await c.post('/api/v1/employee-advances/'+path,headers=auth(1),**({'json':body} if body is not None else {}));assert r.status_code==400 and r.json()['detail']==message
   listing=await c.get('/api/v1/employee-advances',headers=auth(1));assert listing.status_code==200
   assert {x['approval_status'] for x in listing.json()['data']}=={'approved','rejected'}
   logs=await c.get('/api/v1/history?module=employee_advances',headers=auth(1));assert logs.status_code==200,logs.text
   assert logs.json()['total']==3
   funding=[h for h in logs.json()['data'] if h['operation_type']=='funding']
   assert len(funding)==1 and funding[0]['operator_id']==3 and funding[0]['after_data']['amount']==100
   review_logs=[h for h in logs.json()['data'] if h['operation_type'] in ('approve','reject')]
   assert len(review_logs)==2
   for h in review_logs:
    assert h['operator_id']==1 and h['created_at'] and h['after_data']['amount']==100 and h['after_data']['reviewed_at']
    assert h['operation_type'] in ('approve','reject') and h['warehouse_id']==1
   assert await snapshot(factory)==old
   print('ROUND18_REVIEW',json.dumps({'approved':a,'rejected':b},ensure_ascii=False))
 asyncio.run(run())


@pytest.mark.parametrize('uid',[2,3,4,5])
@pytest.mark.parametrize('grant',[False,True])
def test_only_warehouse_admin_can_review(tmp_path,monkeypatch,uid,grant):
 async def run():
  async with hr_environment(tmp_path,monkeypatch) as (_,factory,c):
   aid=await add(factory)
   if uid in (3,4):await set_perms(factory,uid,['员工预支'] if grant else [])
   for action in ('approve','reject'):
    r=await c.post(f'/api/v1/employee-advances/{aid}/{action}',headers=auth(uid),json={'reject_reason':'测试'})
    expected='超级管理员请使用各仓库管理员账号操作' if uid==2 else '无权访问' if uid==5 else '该动作超出当前角色职责上限'
    assert r.status_code==403 and r.json()=={'detail':expected}
   assert (await get(factory,aid))['approval_status']=='pending'
 asyncio.run(run())


@pytest.mark.parametrize('body',[None,{}, {'reject_reason':None},{'reject_reason':''},{'reject_reason':' \n\t '}])
def test_rejection_requires_reason(tmp_path,monkeypatch,body):
 async def run():
  async with hr_environment(tmp_path,monkeypatch) as (_,factory,c):
   aid=await add(factory)
   r=await c.post(f'/api/v1/employee-advances/{aid}/reject',headers=auth(1),**({'json':body} if body is not None else {}))
   assert r.status_code==400 and r.json()['detail']=='请填写驳回原因'
   assert (await get(factory,aid))['approval_status']=='pending'
 asyncio.run(run())


def test_cross_warehouse_and_missing_rejected(tmp_path,monkeypatch):
 async def run():
  async with hr_environment(tmp_path,monkeypatch) as (_,factory,c):
   aid=await add(factory,wid=2,eid=2)
   for target in (aid,999):
    for action in ('approve','reject'):
     r=await c.post(f'/api/v1/employee-advances/{target}/{action}',headers=auth(1),json={'reject_reason':'x'})
     assert r.status_code==404,r.text
   assert (await get(factory,aid))['approval_status']=='pending'
 asyncio.run(run())


async def prepare_work(factory):
 async with factory() as db:
  emp=await db.get(Employee,1);emp.status='regular';emp.hire_date=datetime(2026,10,16)
  for day in (16,17,18):
   for session,hour in ((1,9),(2,12),(3,13),(4,18)):
    db.add(ClockInRecord(user_id=5,warehouse_id=1,clock_date=date(2026,10,day),session=session,clocked_in_at=datetime(2026,10,day,hour),status='normal'))
  await db.commit()

async def calculate(c,end='2026-10-17'):
 r=await c.post('/api/v1/payroll/calculate',headers=auth(3),json={'end_date':end,'employee_ids':[1]});assert r.status_code==200,r.text

async def period_record(factory,day=16):
 async with factory() as db:
  return (await db.execute(select(PayrollRecord).where(PayrollRecord.employee_id==1,PayrollRecord.settle_start_date==date(2026,10,day),PayrollRecord.voided==False))).scalar_one()


def test_pending_approved_manual_recalc_exactly_100_and_carry(tmp_path,monkeypatch):
 async def run():
  async with hr_environment(tmp_path,monkeypatch) as (_,factory,c):
   monkeypatch.setattr(payroll,'thai_today',lambda:date(2026,10,20))
   await prepare_work(factory)
   aid=await add(factory);rejected=await add(factory,status='rejected',amount=200)
   legacy=await snapshot(factory)
   await calculate(c);first=await period_record(factory)
   assert first.base_pay==800 and first.advance_deduction==0 and first.net_pay==800
   saved=await snapshot(factory)
   r=await execute_advance(factory,c,aid)
   assert await snapshot(factory)==saved  # Approval never silently recalculates a paycheck.
   r=await c.post(f'/api/v1/payroll/{first.id}/recalc',headers=auth(3),json={'mode':'recalc','void_reason':'第十八轮隔离验证'});assert r.status_code==200,r.text
   second=await period_record(factory)
   assert second.base_pay==800 and second.advance_deduction==100 and second.net_pay==700
   assert first.net_pay-second.net_pay==100
   assert (await get(factory,rejected))['deducted_amount']==0
   # Recalculate a second time: rollback and reapply exactly 100, never 200.
   r=await c.post(f'/api/v1/payroll/{second.id}/recalc',headers=auth(3),json={'mode':'recalc','void_reason':'重复重算扣款回退验证'});assert r.status_code==200,r.text
   assert (await period_record(factory)).net_pay==700
   current=await snapshot(factory);assert [row for row in current if row[0] in {x[0] for x in legacy}]==legacy
   print('ROUND18_PAYROLL',{'before_net':800,'before_deduction':0,'after_net':700,'after_deduction':100,'difference':100,'rejected_deduction':0})
 asyncio.run(run())


def test_approved_remainder_rolls_to_next_period(tmp_path,monkeypatch):
 async def run():
  async with hr_environment(tmp_path,monkeypatch) as (_,factory,c):
   monkeypatch.setattr(payroll,'thai_today',lambda:date(2026,10,20))
   await prepare_work(factory);aid=await add(factory,status='approved',amount=1000)
   await calculate(c);first=await period_record(factory)
   assert first.net_pay==0 and first.advance_deduction==800 and first.remaining_debt==200
   state=await get(factory,aid);assert state['deducted_amount']==800 and state['status']=='partial'
   await calculate(c,'2026-10-18');second=await period_record(factory,18)
   assert second.base_pay==400 and second.advance_deduction==200 and second.net_pay==200 and second.remaining_debt==0
   assert (await get(factory,aid))['status']=='deducted'
   print('ROUND18_CARRY',{'first_deduct':800,'remaining':200,'next_deduct':200,'next_net':200})
 asyncio.run(run())


def test_review_history_failure_rolls_back(tmp_path,monkeypatch):
 async def run():
  async with hr_environment(tmp_path,monkeypatch) as (_,factory,c):
   aid=await add(factory)
   await post_ok(c,f'/employee-advances/{aid}/verify',3)
   before=await get(factory,aid)
   async def fail(db,**kwargs):
    await db.flush()
    raise HTTPException(500,'模拟修改日志失败')
   monkeypatch.setattr(advance_api,'record_history',fail)
   for action in ('approve','reject'):
    r=await c.post(f'/api/v1/employee-advances/{aid}/{action}',headers=auth(1),json={'reject_reason':'x'});assert r.status_code==500,r.text
    assert await get(factory,aid)==before
 asyncio.run(run())


def test_only_review_actions_and_one_payroll_filter_changed():
 root=Path(__file__).resolve().parents[2]
 name='backend/app/api/v1/employee_advance.py'
 def funcs(s):return {n.name:ast.dump(n,include_attributes=False) for n in ast.parse(s).body if isinstance(n,(ast.AsyncFunctionDef,ast.FunctionDef))}
 old=funcs(subprocess.check_output(['git','show','8882a6a:'+name],cwd=root,text=True));new=funcs(subprocess.check_output(['git','show','fa7708a:'+name],cwd=root,text=True))
 assert {k:new[k] for k in old}==old
 assert set(new)-set(old)=={'_advance_approver','_review_advance','approve_advance','reject_advance'}
 name='backend/app/api/v1/payroll.py'
 class RemoveApprovalFilter(ast.NodeTransformer):
  def visit_Call(self,node):
   self.generic_visit(node)
   node.args=[arg for arg in node.args if ast.unparse(arg)!='EmployeeAdvance.approval_status == AdvanceApprovalStatus.APPROVED.value']
   return node
 def money_funcs(s):return {n.name:ast.dump(RemoveApprovalFilter().visit(n),include_attributes=False) for n in ast.parse(s).body if isinstance(n,(ast.AsyncFunctionDef,ast.FunctionDef))}
 assert money_funcs(subprocess.check_output(['git','show','fa7708a:'+name],cwd=root,text=True))==money_funcs(subprocess.check_output(['git','show','8882a6a:'+name],cwd=root,text=True))
 assert not subprocess.check_output(['git','diff','8882a6a','fa7708a','--','frontend','backend/app/models','backend/scripts'],cwd=root)


def test_supervisor_self_advance_end_to_end(tmp_path,monkeypatch):
 async def run():
  from app.models import User
  async with hr_environment(tmp_path,monkeypatch) as (_,factory,c):
   monkeypatch.setattr(payroll,'thai_today',lambda:date(2026,10,20))
   await set_perms(factory,4,['员工预支'])
   async with factory() as db:
    u=await db.get(User,4);u.attendance_enabled=True;u.attendance_employee_id=1
    e=await db.get(Employee,1);e.user_id=4;e.status='regular';e.hire_date=datetime(2026,10,16)
    for day in (16,17):
     for session,hour in ((1,9),(2,12),(3,13),(4,18)):
      db.add(ClockInRecord(user_id=4,warehouse_id=1,clock_date=date(2026,10,day),session=session,clocked_in_at=datetime(2026,10,day,hour),status='normal'))
    await db.commit()
   r=await c.post('/api/v1/employee-advances',headers=auth(4),json={'employee_id':1,'amount':100,'advance_date':'2026-10-16','funding_source':'company_account','payment_account_id':1})
   assert r.status_code==200 and r.json()['approval_status']=='pending',r.text
   aid=r.json()['id'];await calculate(c);first=await period_record(factory)
   assert first.net_pay==800 and first.advance_deduction==0
   denied=await c.post(f'/api/v1/employee-advances/{aid}/approve',headers=auth(4));assert denied.status_code==403
   approved=await execute_advance(factory,c,aid)
   r=await c.post(f'/api/v1/payroll/{first.id}/recalc',headers=auth(3),json={'mode':'recalc','void_reason':'主管自己预支完整流程测试'})
   assert r.status_code==200,r.text
   second=await period_record(factory);assert second.net_pay==700 and second.advance_deduction==100
 asyncio.run(run())

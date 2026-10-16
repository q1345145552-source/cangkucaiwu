"""Advance approval metadata only: real HTTP, identity, scope and unchanged money code."""
import asyncio,ast,json,subprocess
from pathlib import Path
from datetime import datetime
import pytest
from sqlalchemy import select
from app.models import Employee,User
from app.models.employee_advance import EmployeeAdvance
from app.models.expense_fund import ExpenseFund,ExpenseFundItem
from app.core.menu_registry import MENU_PERMISSIONS_BY_KEY
from tests.test_round2_permissions import auth,set_perms
from tests.test_round3_permissions import hr_environment,snapshot
from tests.test_round15_employee_self import enable

FIELDS={'approval_status','reviewer_id','reviewed_at','reject_reason'}


def test_three_creation_cases_filter_and_self_read(tmp_path,monkeypatch):
 async def run():
  async with hr_environment(tmp_path,monkeypatch) as (_,factory,c):
   await enable(factory)
   await set_perms(factory,4,[MENU_PERMISSIONS_BY_KEY['employee_advances'].label])
   before=await snapshot(factory);created=[]
   for uid,eid,expected in [(1,5,'approved'),(4,5,'pending'),(4,1,'approved')]:
    r=await c.post('/api/v1/employee-advances',headers=auth(uid),json={'employee_id':eid,'amount':100,'advance_date':'2026-10-16','source':'supervisor','approval_status':'approved','reviewer_id':99})
    assert r.status_code==200,r.text
    data=r.json();assert data['approval_status']==expected
    assert FIELDS<=data.keys()
    assert all(data[k] is None for k in FIELDS-{'approval_status'})
    async with factory() as db:
     row=await db.get(EmployeeAdvance,data['id']);assert row.approval_status==expected and row.amount==100 and row.deducted_amount==0
    created.append(data)
   # Rejected fixture demonstrates all three states and preserves exact metadata.
   async with factory() as db:
    row=await db.get(EmployeeAdvance,created[0]['id']);row.approval_status='rejected';row.reviewer_id=1;row.reviewed_at=datetime(2026,10,16,12);row.reject_reason='测试拒绝原因';await db.commit()
   for status in ('pending','approved','rejected','待审批','已通过','已驳回'):
    r=await c.get('/api/v1/employee-advances',headers=auth(1),params={'approval_status':status});assert r.status_code==200,r.text
    expected={'待审批':'pending','已通过':'approved','已驳回':'rejected'}.get(status,status)
    assert r.json()['total']==1 and all(row['approval_status']==expected for row in r.json()['data'])
   invalid=await c.get('/api/v1/employee-advances?approval_status=invalid',headers=auth(1));assert invalid.status_code==422
   allrows=(await c.get('/api/v1/employee-advances',headers=auth(1))).json();assert allrows['total']==3
   own=await c.get('/api/v1/employee-advances/my-debt',headers=auth(4));assert own.status_code==200,own.text
   assert {r['id'] for r in own.json()['data']}=={created[0]['id'],created[1]['id']}
   rejection=next(r for r in own.json()['data'] if r['approval_status']=='rejected')
   assert rejection['reviewer_id']==1 and rejection['reviewed_at'].startswith('2026-10-16T12:00') and rejection['reject_reason']=='测试拒绝原因'
   assert own.json()['total_by_currency']==[{'currency':'THB','total':200.0}]
   assert await snapshot(factory)==before
   print('ROUND17_CREATIONS',json.dumps(created,ensure_ascii=False))
 asyncio.run(run())


def test_detached_supervisor_archive_still_self_and_same_name_not_identity(tmp_path,monkeypatch):
 async def run():
  async with hr_environment(tmp_path,monkeypatch) as (_,factory,c):
   await enable(factory);await set_perms(factory,4,[MENU_PERMISSIONS_BY_KEY['employee_advances'].label])
   r=await c.put('/api/v1/users/4',headers=auth(1),json={'attendance_enabled':False});assert r.status_code==200
   async with factory() as db:
    (await db.get(Employee,1)).name='supervisor';await db.commit()
   for eid,expected in [(5,'pending'),(1,'approved')]:
    r=await c.post('/api/v1/employee-advances',headers=auth(4),json={'employee_id':eid,'amount':25,'advance_date':'2026-10-16','source':'supervisor'})
    assert r.status_code==200 and r.json()['approval_status']==expected,r.text
 asyncio.run(run())


@pytest.mark.parametrize('uid',[1,2,3,4])
def test_permission_warehouse_and_delete_guards(tmp_path,monkeypatch,uid):
 async def run():
  async with hr_environment(tmp_path,monkeypatch) as (_,factory,c):
   if uid in (3,4):await set_perms(factory,uid,[])
   body={'employee_id':1,'amount':50,'advance_date':'2026-10-16','source':'supervisor'}
   if uid in (3,4):
    denied=await c.post('/api/v1/employee-advances',headers=auth(uid),json=body);assert denied.status_code==403 and '无此操作权限' in denied.text
    await set_perms(factory,uid,[MENU_PERMISSIONS_BY_KEY['employee_advances'].label])
   other=await c.post('/api/v1/employee-advances',headers=auth(uid),json={**body,'employee_id':2});assert other.status_code==404,other.text
   good=await c.post('/api/v1/employee-advances',headers=auth(uid),json=body);assert good.status_code==200 and good.json()['approval_status']=='approved',good.text
   async with factory() as db:
    db.add(EmployeeAdvance(id=100,employee_id=2,warehouse_id=2,amount=50,advance_date=datetime(2026,10,16).date(),period='2026-10',approval_status='pending'));await db.commit()
   baddelete=await c.delete('/api/v1/employee-advances/100',headers=auth(uid));assert baddelete.status_code==404
   for status in ('pending','approved'):
    rows=(await c.get('/api/v1/employee-advances',headers=auth(uid),params={'approval_status':status})).json()['data'];assert all(r['id']!=100 for r in rows)
   deleted=await c.delete('/api/v1/employee-advances/'+str(good.json()['id']),headers=auth(uid));assert deleted.status_code==200
 asyncio.run(run())


def test_startup_wired_and_payroll_frontend_unchanged():
 root=Path(__file__).resolve().parents[2]
 source=(root/'backend/scripts/seed.py').read_text()
 seed=next(n for n in ast.parse(source).body if isinstance(n,ast.AsyncFunctionDef) and n.name=='seed')
 assert any(isinstance(n,ast.Call) and getattr(n.func,'id','')=='_migrate_advance_approval_columns' for n in ast.walk(seed))
 assert (root/'backend/app/api/v1/payroll.py').read_bytes()==subprocess.check_output(['git','show','75021e9:backend/app/api/v1/payroll.py'],cwd=root)
 assert not subprocess.check_output(['git','diff','75021e9','--','frontend/src'],cwd=root)
 # Existing deletion, totals and fund business logic stay unchanged apart from read-only response additions.


def test_original_advance_money_actions_unchanged():
 root=Path(__file__).resolve().parents[2]
 name='backend/app/api/v1/employee_advance.py'
 old=ast.parse(subprocess.check_output(['git','show','75021e9:'+name],text=True,cwd=root));new=ast.parse((root/name).read_text())
 def get(tree,name):return next(n for n in tree.body if isinstance(n,ast.AsyncFunctionDef) and n.name==name)
 for name in ('advance_summary','delete_advance'):
  assert ast.dump(get(old,name),include_attributes=False)==ast.dump(get(new,name),include_attributes=False)
 def fund_body(tree):
  return next(n for n in get(tree,'create_advance').body if isinstance(n,ast.If) and ast.unparse(n.test)=="req.source == 'fund' and fund_account")
 assert ast.dump(fund_body(old),include_attributes=False)==ast.dump(fund_body(new),include_attributes=False)


def test_legacy_approved_advance_payroll_deduction_unchanged(tmp_path,monkeypatch):
 async def run():
  from datetime import date
  from app.models import ClockInRecord
  from app.models.payroll import PayrollRecord
  import app.api.v1.payroll as payroll
  async with hr_environment(tmp_path,monkeypatch) as (_,factory,c):
   monkeypatch.setattr(payroll,'thai_today',lambda:date(2026,10,18))
   async with factory() as db:
    emp=await db.get(Employee,1);emp.status='regular';emp.hire_date=datetime(2026,10,16)
    db.add(EmployeeAdvance(id=20,employee_id=1,warehouse_id=1,amount=100,deducted_amount=0,advance_date=date(2026,10,16),period='2026-10',status='unpaid'))
    for day in (16,17):
     for session,hour in ((1,9),(2,12),(3,13),(4,18)):
      db.add(ClockInRecord(user_id=5,warehouse_id=1,clock_date=date(2026,10,day),session=session,clocked_in_at=datetime(2026,10,day,hour),status='normal'))
    await db.commit()
   before=await snapshot(factory)
   r=await c.post('/api/v1/payroll/calculate',headers=auth(1),json={'end_date':'2026-10-17','employee_ids':[1]});assert r.status_code==200,r.text
   async with factory() as db:
    record=(await db.execute(select(PayrollRecord).where(PayrollRecord.employee_id==1,PayrollRecord.settle_start_date==date(2026,10,16)))).scalar_one()
    assert record.base_pay==800 and record.advance_deduction==100 and record.net_pay==700
    adv=await db.get(EmployeeAdvance,20);assert adv.approval_status=='approved' and adv.deducted_amount==100 and adv.status=='deducted'
   after=await snapshot(factory);assert [row for row in after if row[0] in {v[0] for v in before}]==before
   print('ROUND17_PAYROLL',{'base_pay':800,'advance_deduction':100,'net_pay':700})
 asyncio.run(run())

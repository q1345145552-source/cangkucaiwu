"""第十轮真实 HTTP：七模块读写、授权/撤权、劳工隔离、仓库及业务体不变。"""
import asyncio, ast, subprocess
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
import pytest
from sqlalchemy import select
from app.core.menu_registry import MENU_PERMISSIONS_BY_KEY
from app.models.employee_deduction import EmployeeDeduction, EmployeeFixedDeduction
from app.models.employee_advance import EmployeeAdvance
from tests.test_round2_permissions import auth, set_perms
from tests.test_round3_permissions import hr_environment, CASES as HR_CASES, call, snapshot
from tests.test_round6_permissions import CASES as R6_CASES

CASES=[c for c in HR_CASES if c[2] in ('employees','salary_templates','deduction_templates')]
CASES += [c for c in R6_CASES if c[2]=='labor_efficiency']
CASES += [('GET',p,'concentration',None) for p in ('/suppliers/concentration?month=2026-10','/suppliers/concentration-trend?months=1','/suppliers/concentration-threshold')]
CASES += [
 ('POST','/employee-deductions','employee_deductions',{'employee_id':1,'amount':20,'deduction_date':'2026-10-10','reason':'权限测试'}),
 ('GET','/employee-deductions','employee_deductions',None),
 ('DELETE','/employee-deductions/1','employee_deductions',None),
 ('GET','/employee-deductions/fixed?employee_id=1','employee_deductions',None),
 ('POST','/employee-deductions/fixed','employee_deductions',{'employee_id':1,'name':'宿舍费','amount':20}),
 ('PUT','/employee-deductions/fixed/1','employee_deductions',{'amount':25}),
 ('DELETE','/employee-deductions/fixed/1','employee_deductions',None),
 ('POST','/employee-advances','employee_advances',{'employee_id':1,'amount':20,'advance_date':'2026-10-10','source':'supervisor'}),
 ('GET','/employee-advances','employee_advances',None),
 ('GET','/employee-advances/summary','employee_advances',None),
 ('DELETE','/employee-advances/1','employee_advances',None),
]
@asynccontextmanager
async def r10_environment(tmp_path,monkeypatch):
 async with hr_environment(tmp_path,monkeypatch) as (engine,factory,client):
  async with factory() as db:
   for i in (1,2):
    db.add(EmployeeDeduction(id=i,warehouse_id=i,employee_id=i,amount=20,deduction_date=date(2026,10,10),period='2026-10',half='first_half',reason='测试'))
    db.add(EmployeeFixedDeduction(id=i,warehouse_id=i,employee_id=i,name='固定扣款',amount=10))
    db.add(EmployeeAdvance(id=i,warehouse_id=i,employee_id=i,amount=100,advance_date=date(2026,10,10),period='2026-10',source='supervisor',deducted_amount=0,status='unpaid'))
   await db.commit()
  yield engine,factory,client

@pytest.mark.parametrize('method,path,key,body',CASES,ids=[f'{m} {p}' for m,p,_,_ in CASES])
@pytest.mark.parametrize('uid,grant',[(3,False),(4,False),(3,True),(4,True),(1,False),(2,False),(5,True)],ids=['staff-deny','supervisor-deny','staff-grant','supervisor-grant','admin','super-admin','labor-with-all-perms'])
def test_endpoint_matrix(tmp_path,monkeypatch,method,path,key,body,uid,grant):
 async def run():
  async with r10_environment(tmp_path,monkeypatch) as (_,factory,client):
   if grant:
    perms=[MENU_PERMISSIONS_BY_KEY[key].label]
    if path.endswith('/resign'):perms.append(MENU_PERMISSIONS_BY_KEY['payroll'].label)
    await set_perms(factory,uid,perms)
   before=await snapshot(factory)
   r=await call(client,method,path,body,uid)
   if uid in (3,4) and not grant:
    assert r.status_code==403,r.text
    assert r.json()['detail'].startswith('无此操作权限'),r.text
   else:
    expected=403 if uid==5 else 200
    assert r.status_code==expected,r.text
   if not path.endswith('/resign'):assert await snapshot(factory)==before
 asyncio.run(run())

@pytest.mark.parametrize('uid',[1,2,3,4])
def test_id_and_batch_warehouse_checks(tmp_path,monkeypatch,uid):
 async def run():
  async with r10_environment(tmp_path,monkeypatch) as (_,factory,client):
   await set_perms(factory,uid,[p.label for p in MENU_PERMISSIONS_BY_KEY.values() if p.selectable])
   before=await snapshot(factory)
   requests=[
    ('PUT','/employees/2',{'name':'跨仓'}),('DELETE','/employees/2',None),
    ('POST','/employees/2/resign',{'reason':'voluntary','resignation_date':'2026-10-15'}),
    *[('POST','/employees/2/'+p,'photo') for p in ('photo','passport-photo','work-permit-photo')],
    ('POST','/employees/batch-set-templates',{'employee_ids':[1,2],'salary_template_id':1,'deduction_template_id':1}),
    ('POST','/employees/batch-set-templates',{'employee_ids':[1],'salary_template_id':2,'deduction_template_id':1}),
    ('POST','/employees/batch-set-templates',{'employee_ids':[1],'salary_template_id':1,'deduction_template_id':2}),
    *[(m,p+'/2',{'name':'跨仓'} if m=='PUT' else None) for p in ('/salary-templates','/deduction-templates') for m in ('PUT','DELETE')],
    ('POST','/employee-deductions',{'employee_id':2,'amount':20,'deduction_date':'2026-10-10','reason':'跨仓'}),
    ('DELETE','/employee-deductions/2',None),('GET','/employee-deductions/fixed?employee_id=2',None),
    ('POST','/employee-deductions/fixed',{'employee_id':2,'name':'跨仓','amount':20}),
    ('PUT','/employee-deductions/fixed/2',{'amount':25}),('DELETE','/employee-deductions/fixed/2',None),
    ('POST','/employee-advances',{'employee_id':2,'amount':20,'advance_date':'2026-10-10','source':'supervisor'}),
    ('DELETE','/employee-advances/2',None),
    ('PUT','/efficiency/manual-hour',{'employee_id':2,'date':'2026-10-10','hours':8}),
   ]
   for method,path,body in requests:
    r=await call(client,method,path,body,uid);assert r.status_code in (400,403,404),(path,r.text)
    assert await snapshot(factory)==before
   for path in ('/employees','/employee-deductions','/employee-advances'):
    r=await client.get('/api/v1'+path,headers={**auth(uid),'X-Warehouse-ID':'2'});assert r.status_code==200,r.text
    assert {x['id'] for x in r.json()['data']}=={1},(path,r.text)
 asyncio.run(run())

@pytest.mark.parametrize('uid',[3,4])
def test_shared_fixed_deductions_and_revocation(tmp_path,monkeypatch,uid):
 async def run():
  async with r10_environment(tmp_path,monkeypatch) as (_,factory,client):
   await set_perms(factory,uid,['员工档案'])
   for method,path,key,body in CASES:
    if '/employee-deductions/fixed' not in path:continue
    r=await call(client,method,path,body,uid);assert r.status_code==200,r.text
   # Employee-file access cannot grant the independent temporary deduction/advance APIs.
   for path in ('/employee-deductions','/employee-advances'):
    r=await client.get('/api/v1'+path,headers=auth(uid));assert r.status_code==403 and '无此操作权限' in r.text
   for key,path in [('employee_deductions','/employee-deductions'),('employee_advances','/employee-advances'),('labor_efficiency','/efficiency/standard')]:
    await set_perms(factory,uid,[MENU_PERMISSIONS_BY_KEY[key].label]);assert (await client.get('/api/v1'+path,headers=auth(uid))).status_code==200
    await set_perms(factory,uid,[]);r=await client.get('/api/v1'+path,headers=auth(uid));assert r.status_code==403 and '无此操作权限' in r.text
   r=await client.get('/api/v1/employee-advances/my-debt',headers=auth(5));assert r.status_code==200 and r.json()['total_by_currency']==[{'currency':'THB','total':100.0}]
 asyncio.run(run())

def test_business_bodies_and_config_exceptions_unchanged():
 root=Path(__file__).resolve().parents[1]
 class RemoveRoleChecks(ast.NodeTransformer):
  def visit_If(self,node):
   if 'current_user.role' in ast.unparse(node.test):return None
   return self.generic_visit(node)
  def visit_Expr(self,node):
   if isinstance(node.value,ast.Call) and getattr(node.value.func,'id','')=='_forbid_super_admin':return None
   return self.generic_visit(node)
 for file in ('employees','salary_template','deduction_template','efficiency','employee_deduction','employee_advance','suppliers'):
  name=f'backend/app/api/v1/{file}.py'
  old=ast.parse(subprocess.check_output(['git','show','8629b2f:'+name],text=True))
  new=ast.parse((root/'app/api/v1'/f'{file}.py').read_text())
  def bodies(tree):
   return {n.name:ast.dump(RemoveRoleChecks().visit(ast.Module(body=n.body,type_ignores=[])),include_attributes=False) for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name not in {"my_debt", "_compute_week", "_compute_overtime_hours", "_approval_fields", "create_advance", "list_advances", "_advance_approver", "_review_advance", "approve_advance", "reject_advance", "list_advance_recipients"}}
  assert bodies(old)==bodies(new),file
 for file in ('config_api','history'):
  name=f'backend/app/api/v1/{file}.py'
  assert subprocess.check_output(['git','show','8629b2f:'+name],text=True)==(root/'app/api/v1'/f'{file}.py').read_text()
 # The shared concentration threshold remains a configuration write: unchanged in full.
 def threshold_body(text):
  n=next(n for n in ast.parse(text).body if isinstance(n,ast.AsyncFunctionDef) and n.name=='set_concentration_threshold')
  return ast.dump(n,include_attributes=False)
 assert threshold_body(subprocess.check_output(['git','show','8629b2f:backend/app/api/v1/suppliers.py'],text=True))==threshold_body((root/'app/api/v1/suppliers.py').read_text())

@pytest.mark.parametrize('uid',[3,4])
def test_advance_fund_money_and_ownership_preserved(tmp_path,monkeypatch,uid):
 async def run():
  from datetime import datetime
  from app.models.expense_fund import ExpenseFund,ExpenseFundItem
  async with r10_environment(tmp_path,monkeypatch) as (_,factory,client):
   await set_perms(factory,uid,['员工预支'])
   async with factory() as db:
    for i,owner in ((1,4),(2,6)):
     db.add(ExpenseFund(id=i,warehouse_id=i,employee_id=owner,receive_date=datetime(2026,10,1),amount=100,remaining_balance=100,purpose='测试预支'))
    await db.commit()
   before=await snapshot(factory)
   async def counts():
    async with factory() as db:return (len((await db.execute(select(EmployeeAdvance))).scalars().all()),len((await db.execute(select(ExpenseFundItem))).scalars().all()))
   initial=await counts()
   for fund,amount,expected in ((2,20,404),(1,101,400)):
    r=await client.post('/api/v1/employee-advances',headers=auth(uid),json={'employee_id':1,'amount':amount,'advance_date':'2026-10-10','source':'fund','fund_account_id':fund})
    assert r.status_code==expected,r.text;assert await counts()==initial
   r=await client.post('/api/v1/employee-advances',headers=auth(uid),json={'employee_id':1,'amount':20,'advance_date':'2026-10-10','source':'fund','fund_account_id':1})
   assert r.status_code==200,r.text
   async with factory() as db:
    advance=await db.get(EmployeeAdvance,r.json()['id'])
    items=(await db.execute(select(ExpenseFundItem))).scalars().all()
    assert advance.amount==20 and advance.warehouse_id==1 and advance.source=='fund'
    assert len(items)==1 and items[0].amount==20 and items[0].fund_id==1 and items[0].category=='预支工资'
   assert await snapshot(factory)==before
 asyncio.run(run())

def test_config_and_history_actual_behavior(tmp_path,monkeypatch):
 async def run():
  from app.services.schedule import default_work_schedule
  async with r10_environment(tmp_path,monkeypatch) as (_,factory,client):
   for uid in (3,4):
    await set_perms(factory,uid,['配置中心','修改日志','采购分析'])
    read=await client.get('/api/v1/config/work-schedule',headers=auth(uid))
    assert read.status_code==(200 if uid==4 else 403),read.text
    if uid==4:assert read.json()['editable'] is False
    write=await client.put('/api/v1/config/work-schedule',headers=auth(uid),json=default_work_schedule())
    assert write.status_code==403 and '只有仓库管理员' in write.text
    write=await client.put('/api/v1/suppliers/concentration-threshold',headers=auth(uid),json={'threshold':80})
    assert write.status_code==403 and '只有仓库管理员' in write.text
    history=await client.get('/api/v1/history',headers=auth(uid));assert history.status_code==403 and '只有仓库管理员' in history.text
 asyncio.run(run())

def test_route_inventory():
 for key in ("employee_deductions","employee_advances"):
  assert MENU_PERMISSIONS_BY_KEY[key].as_dict()["default_roles"]==["warehouse_admin"]
 root=Path(__file__).resolve().parents[1]/'app/api/v1';seen=set()
 prefixes={'employees':'employees','salary_template':'salary-templates','deduction_template':'deduction-templates','efficiency':'efficiency','employee_deduction':'employee-deductions','employee_advance':'employee-advances','suppliers':'suppliers'}
 for file,prefix in prefixes.items():
  for n in ast.parse((root/(file+'.py')).read_text()).body:
   if not isinstance(n,ast.AsyncFunctionDef):continue
   for d in n.decorator_list:
    if not isinstance(d,ast.Call) or not isinstance(d.func,ast.Attribute):continue
    route=d.args[0].value
    if file=='employee_advance' and route=='/my-debt':continue
    if file=='suppliers' and (not route.startswith('/concentration') or d.func.attr!='get'):continue
    seen.add((d.func.attr.upper(),'/'+prefix+route))
 def normalize(p):return __import__('re').sub(r'/[123](?=/|$)','/{}',__import__('re').sub(r'\{[^}]+\}','{}',p.split('?')[0]))
 assert {(m,normalize(p)) for m,p in seen}==({(m,normalize(p)) for m,p,_,_ in CASES} | {("POST","/employee-advances/{}/approve"),("POST","/employee-advances/{}/reject"),("GET","/employee-advances/recipients")})

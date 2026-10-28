import asyncio,json
from datetime import date
import pytest
from sqlalchemy import select,func
from app.models.overtime import OvertimeTask,OvertimeAssignment
from app.models.employee_advance import EmployeeAdvance
from tests.test_round2_permissions import auth,set_perms
from tests.test_round3_permissions import hr_environment,snapshot
from tests.test_round18_advance_review import add
from tests.test_round19_overtime_self_review import setup,create,assignments,verify

async def todos(c,uid=1,headers=None):
 r=await c.get('/api/v1/dashboard/boss-todos',headers=headers or auth(uid));assert r.status_code==200,r.text
 assert r.headers['cache-control']=='no-store'
 d=r.json()
 for g in d.values():assert g['count']==len(g['items'])
 return d

def test_counts_and_handling(tmp_path,monkeypatch):
 async def run():
  async with hr_environment(tmp_path,monkeypatch) as (_,f,c):
   await setup(f);ids=[await add(f) for _ in range(3)];tid=await create(c,[1,5]);old=await snapshot(f)
   before=await todos(c)
   async with f() as db:
    counts=[(await db.execute(select(func.count(EmployeeAdvance.id)).where(EmployeeAdvance.warehouse_id==1,EmployeeAdvance.approval_status=='pending'))).scalar_one(),(await db.execute(select(func.count(OvertimeAssignment.id)).join(OvertimeTask).where(OvertimeTask.warehouse_id==1,OvertimeAssignment.actual_hours.is_(None)))).scalar_one()]
   assert counts==[before['advances']['count'],before['overtime']['count']]==[3,2]
   await set_perms(f,3,['员工预支'])
   finance=await todos(c,3);onsite=await todos(c,4)
   assert [finance['advances']['count'],finance['overtime']['count']]==[3,0]
   assert [onsite['advances']['count'],onsite['overtime']['count']]==[0,2]
   assert (await c.post(f'/api/v1/employee-advances/{ids[0]}/verify',headers=auth(3))).status_code==200
   assert (await c.post(f'/api/v1/employee-advances/{ids[0]}/approve',headers=auth(1))).status_code==200
   a=(await assignments(f,tid))[0];assert (await verify(c,tid,[a.id],uid=1)).status_code==200
   after=await todos(c);assert [after['advances']['count'],after['overtime']['count']]==[2,1]
   await set_perms(f,4,['加班','员工预支'])
   r=await c.get('/api/v1/employee-advances?approval_status=pending',headers=auth(3));assert r.status_code==200
   assert {x['id'] for x in r.json()['data']}=={x['id'] for x in after['advances']['items']}
   r=await c.get('/api/v1/overtime?pending_verification=true',headers=auth(4));assert r.status_code==200,r.text
   assert {x['id'] for t in r.json()['data'] for x in t['assignments']}=={x['id'] for x in after['overtime']['items']}
   for aid in ids[1:]:assert (await c.post(f'/api/v1/employee-advances/{aid}/reject',headers=auth(1),json={'reject_reason':'测试'})).status_code==200
   pending=after['overtime']['items'];assert (await verify(c,tid,[x['id'] for x in pending],uid=1)).status_code==200
   empty=await todos(c);assert empty['advances']['count']==empty['overtime']['count']==0
   assert await snapshot(f)==old
   print('ROUND20_COUNTS',json.dumps({'database':counts,'before':before,'after':after,'empty':empty},ensure_ascii=False))
 asyncio.run(run())

def test_warehouse_roles(tmp_path,monkeypatch):
 async def run():
  async with hr_environment(tmp_path,monkeypatch) as (_,f,c):
   await setup(f);own=await add(f);foreign=await add(f,wid=2,eid=2);await create(c,[1])
   d=await todos(c);assert [x['id'] for x in d['advances']['items']]==[own] and d['overtime']['count']==1
   assert (await c.get('/api/v1/dashboard/boss-todos',headers={**auth(1),'X-Warehouse-ID':'2'})).status_code==403
   assert (await c.get('/api/v1/dashboard/boss-todos',headers=auth(2))).status_code==403
   for uid in (5,6):assert (await c.get('/api/v1/dashboard/boss-todos',headers=auth(uid))).status_code==403
   assert (await c.get('/api/v1/dashboard/boss-todos')).status_code in (401,403)
   from app.models.user import User
   async with f() as db:(await db.get(User,6)).role='staff';await db.commit()
   await set_perms(f,6,['员工预支'])
   assert [x['id'] for x in (await todos(c,6))['advances']['items']]==[foreign]
 asyncio.run(run())

@pytest.mark.parametrize('kind',['verified','zero','confirmed','completed','no_verification','dispute'])
def test_pending_definition(tmp_path,monkeypatch,kind):
 async def run():
  async with hr_environment(tmp_path,monkeypatch) as (_,f,c):
   await setup(f);tid=await create(c,[1]);a=(await assignments(f,tid))[0]
   async with f() as db:
    t=await db.get(OvertimeTask,tid);r=await db.get(OvertimeAssignment,a.id)
    if kind in ('verified','dispute'):r.actual_hours=1;t.status='已核实'
    if kind=='zero':r.actual_hours=0
    if kind=='confirmed':r.confirmed=True
    if kind=='completed':t.status='completed'
    if kind=='no_verification':t.needs_verification=False
    if kind=='dispute':r.has_dispute=True
    await db.commit()
   expected=int(kind=='dispute');assert (await todos(c))['overtime']['count']==expected
   r=await c.get('/api/v1/overtime?pending_verification=true',headers=auth(1));assert r.status_code==200,r.text
   assert sum(len(t['assignments']) for t in r.json()['data'])==expected
   if expected:
    assert (await verify(c,tid,[a.id],uid=1)).status_code==200
    assert (await todos(c))['overtime']['count']==0
 asyncio.run(run())

def test_uncapped_counts(tmp_path,monkeypatch):
 async def run():
  async with hr_environment(tmp_path,monkeypatch) as (_,f,c):
   await setup(f)
   for _ in range(205):await add(f)
   async with f() as db:
    t=OvertimeTask(warehouse_id=1,date=date(2026,10,16),start_time='18:00',end_time='19:00',hours=1,created_by=1,needs_verification=True)
    db.add(t);await db.flush();db.add_all([OvertimeAssignment(overtime_id=t.id,employee_id=1) for _ in range(205)])
    for _ in range(201):db.add(OvertimeTask(warehouse_id=1,date=date(2026,10,17),start_time='18:00',end_time='19:00',hours=1,created_by=1,needs_verification=True,status='completed'))
    await db.commit()
   d=await todos(c);assert d['advances']['count']==d['overtime']['count']==205
   r=await c.get('/api/v1/overtime?pending_verification=true&page_size=1',headers=auth(1));assert r.status_code==200
   assert r.json()['total']==1 and len(r.json()['data'][0]['assignments'])==205
 asyncio.run(run())


def test_existing_review_and_business_functions_unchanged():
 import ast,subprocess
 from pathlib import Path
 root=Path(__file__).resolve().parents[2]
 for name,allowed in [('backend/app/api/v1/dashboard.py',{'boss_todos'}),('backend/app/api/v1/overtime.py',{'list_overtimes'}),('backend/app/api/v1/employee_advance.py',set())]:
  def funcs(s):return {n.name:ast.dump(n,include_attributes=False) for n in ast.parse(s).body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
  old=funcs(subprocess.check_output(['git','show','e950142:'+name],cwd=root,text=True));new=funcs(subprocess.check_output(['git','show','ba9cc23:'+name],cwd=root,text=True))
  assert {k:v for k,v in old.items() if k not in allowed}=={k:v for k,v in new.items() if k not in allowed}

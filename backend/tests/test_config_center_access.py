import ast, asyncio, json, subprocess
from pathlib import Path
import pytest
from sqlalchemy import select
from app.models import SystemSetting
from app.services.schedule import default_work_schedule, get_work_schedule
from tests.test_round2_permissions import auth, set_perms
from tests.test_round3_permissions import hr_environment, snapshot

PATHS=['/config/work-schedule','/expense-approvals/threshold','/suppliers/purchase-approval-threshold','/suppliers/concentration-threshold']

def body(path):return default_work_schedule() if path==PATHS[0] else {'threshold':80}

@pytest.mark.parametrize('uid,grant',[(1,False),(2,False),(3,False),(3,True),(4,False),(4,True),(5,True)])
def test_all_reads_writes_and_editable(tmp_path,monkeypatch,uid,grant):
 async def run():
  async with hr_environment(tmp_path,monkeypatch) as (_,f,c):
   await set_perms(f,uid,['配置中心'] if grant else [])
   for path in PATHS:
    read=await c.get('/api/v1'+path,headers=auth(uid))
    expected=200 if uid==1 or (uid in (3,4) and grant) or (uid==2 and path==PATHS[3]) else 403
    assert read.status_code==expected,(path,read.text)
    if path==PATHS[0] and expected==200:assert read.json()['editable']==(uid in (1,4))
    write=await c.put('/api/v1'+path,headers=auth(uid),json=body(path))
    assert write.status_code==(200 if uid==1 or (uid==4 and grant) else 403),(path,write.text)
    if uid==3 and grant:assert write.json()=={'detail':'财务只能查看配置中心'}
    if uid in (3,4) and not grant:
     assert read.json()['detail'].startswith('无此操作权限')
     assert write.json()['detail'].startswith('无此操作权限')
   if uid==3 and grant:
    print('CONFIG_FINANCE',json.dumps({'read':(await c.get('/api/v1'+PATHS[0],headers=auth(uid))).json(),'write':write.json()},ensure_ascii=False))
 asyncio.run(run())


def test_supervisor_save_restore_and_warehouse(tmp_path,monkeypatch):
 async def run():
  async with hr_environment(tmp_path,monkeypatch) as (_,f,c):
   await set_perms(f,4,['配置中心'])
   old=await snapshot(f)
   original=(await c.get('/api/v1'+PATHS[0],headers=auth(4))).json()
   changed={**default_work_schedule(),'morning_start':'08:30','late_half':'08:35','late_one':'08:50','overtime_limit':65}
   saved=await c.put('/api/v1'+PATHS[0],headers={**auth(4),'X-Warehouse-ID':'2'},json=changed)
   assert saved.status_code==200,saved.text
   assert saved.json()['morning_start']=='08:30' and saved.json()['overtime_limit']==65
   read=(await c.get('/api/v1'+PATHS[0],headers=auth(4))).json()
   assert read['editable'] and read['warehouse_id']==1 and read['morning_start']=='08:30'
   for path in PATHS[1:]:
    r=await c.put('/api/v1'+path,headers=auth(4),json={'threshold':80});assert r.status_code==200,r.text
    assert (await c.get('/api/v1'+path,headers=auth(4))).json()['threshold']==80
   async with f() as db:
    assert await get_work_schedule(db,2)==default_work_schedule()
    assert not (await db.execute(select(SystemSetting).where(SystemSetting.warehouse_id==2))).scalars().all()
   restored=await c.put('/api/v1'+PATHS[0],headers=auth(4),json={k:original[k] for k in default_work_schedule()})
   assert restored.status_code==200 and restored.json()['morning_start']==original['morning_start']
   assert await snapshot(f)==old
   print('CONFIG_SUPERVISOR',json.dumps({'saved':saved.json(),'read':read,'restored':restored.json()},ensure_ascii=False))
 asyncio.run(run())


@pytest.mark.parametrize('field,value,message',[('morning_start','bad','时间格式错误'),('late_half','08:00','时间顺序不对'),('overtime_limit',-1,'加班月度上限不能为负数')])
def test_validation_unchanged_and_atomic(tmp_path,monkeypatch,field,value,message):
 async def run():
  async with hr_environment(tmp_path,monkeypatch) as (_,f,c):
   await set_perms(f,4,['配置中心'])
   r=await c.put('/api/v1'+PATHS[0],headers=auth(4),json={**default_work_schedule(),field:value})
   assert r.status_code==400 and message in r.json()['detail']
   async with f() as db:assert await get_work_schedule(db,1)==default_work_schedule()
   for path in PATHS[1:3]:
    r=await c.put('/api/v1'+path,headers=auth(4),json={'threshold':-1});assert r.status_code==400
 asyncio.run(run())


def test_shared_reads_and_no_concentration_write_bypass(tmp_path,monkeypatch):
 async def run():
  async with hr_environment(tmp_path,monkeypatch) as (_,f,c):
   for uid in (3,4):
    for permission,path in [('费用审批',PATHS[1]),('供应商管理',PATHS[2]),('采购分析',PATHS[3])]:
     await set_perms(f,uid,[permission])
     r=await c.get('/api/v1'+path,headers=auth(uid))
     assert r.status_code==(403 if uid==3 and path==PATHS[2] else 200),r.text
    r=await c.put('/api/v1'+PATHS[3],headers=auth(uid),json={'threshold':80})
    assert r.status_code==403 and r.json()['detail'].startswith('无此操作权限')
 asyncio.run(run())


def test_only_config_access_changed_business_tail_identical():
 root=Path(__file__).resolve().parents[2]
 allowed={'config_api':{'get_work_schedule_settings','set_work_schedule_settings','get_attendance_times'},'expense_approval':{'set_threshold'},'suppliers':{'get_approval_threshold','set_approval_threshold','set_concentration_threshold'},'history':set()}
 for name,changed in allowed.items():
  p=f'backend/app/api/v1/{name}.py'
  def funcs(s):return {n.name:n for n in ast.parse(s).body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
  old=funcs(subprocess.check_output(['git','show','e970f41:'+p],cwd=root,text=True));new=funcs((root/p).read_text())
  assert {k:ast.dump(v,include_attributes=False) for k,v in old.items() if k not in changed}=={k:ast.dump(v,include_attributes=False) for k,v in new.items() if k not in changed}
  for key in changed:
   if key.startswith('get_'):continue
   def tail(node):
    index=next(i for i,n in enumerate(node.body) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='wh_id' for t in n.targets))
    return ast.dump(ast.Module(body=node.body[index:],type_ignores=[]),include_attributes=False)
   # Purchase threshold validates amount before getting the warehouse; all of it remains unchanged.
   if key=='set_approval_threshold':
    def tail(node):
     index=next(i for i,n in enumerate(node.body) if isinstance(n,ast.If) and ast.unparse(n.test)=='req.threshold < 0')
     return ast.dump(ast.Module(body=node.body[index:],type_ignores=[]),include_attributes=False)
   assert tail(old[key])==tail(new[key]),key


def test_shared_times_are_limited_without_config_permission(tmp_path,monkeypatch):
 async def run():
  async with hr_environment(tmp_path,monkeypatch) as (_,f,c):
   await set_perms(f,4,['配置中心'])
   changed={**default_work_schedule(),'morning_start':'08:30','late_half':'08:35','late_one':'08:50'}
   assert (await c.put('/api/v1/config/work-schedule',headers=auth(4),json=changed)).status_code==200
   await set_perms(f,4,[])
   assert (await c.get('/api/v1/config/work-schedule',headers=auth(4))).status_code==403
   r=await c.get('/api/v1/config/attendance-times',headers=auth(4))
   assert r.status_code==200 and r.json()=={'morning_start':'08:30','noon_break_start':'12:00','noon_break_end':'13:00','afternoon_end':'18:00'}
   for uid in (2,3,5):assert (await c.get('/api/v1/config/attendance-times',headers=auth(uid))).status_code==403
 asyncio.run(run())

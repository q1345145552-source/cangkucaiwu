"""第十四轮本机隔离测试：普通、已有档案、关闭过及绑定冲突账号。"""
import asyncio,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'backend'))
import pytest,uvicorn
from sqlalchemy import select, event
from tests.test_round3_permissions import hr_environment
from app.main import app
from app.models import User,UserWarehouse,Employee
from app.models.data_change_history import DataChangeHistory
from app.core.security import hash_password
from app.core.menu_registry import MENU_PERMISSIONS
from app.services.permission_migrations import run_permission_migrations
async def main():
 import tempfile
 patch=pytest.MonkeyPatch();folder=Path(tempfile.mkdtemp(prefix='cangkucaiwu-r7-'))
 async with hr_environment(folder,patch) as (engine,factory,_):
  # Test-only SQLite adapter; keep real ledger/month SQL unchanged.
  @event.listens_for(engine.sync_engine,'connect')
  def sqlite_functions(conn,_):conn.create_function('to_char',2,lambda value,fmt:str(value)[:7] if value else None)
  await engine.dispose()
  async with engine.begin() as conn:await run_permission_migrations(conn)
  password=hash_password('test-password')
  async with factory() as db:
   for u in (await db.execute(select(User))).scalars():u.password_hash=password
   for uid,name in ((7,'r14-conflict'),(8,'r14-existing'),(9,'r14-return')):
    db.add(User(id=uid,username=name,display_name=name,role='supervisor',password_hash=password,warehouse_id=1,extra_permissions=[]))
    db.add(UserWarehouse(user_id=uid,warehouse_id=1))
   await db.flush()
   db.add(Employee(id=3,warehouse_id=1,name='已有主管档案',user_id=8,salary_template_id=1,deduction_template_id=1))
   db.add(Employee(id=4,warehouse_id=1,name='保留的主管档案',user_id=None,salary_template_id=1,deduction_template_id=1))
   (await db.get(User,7)).attendance_employee_id=1
   db.add(DataChangeHistory(module='user',record_id=9,operator_id=1,operation_type='edit',before_data={'attendance_employee_id':4},after_data={'attendance_employee_id':None},warehouse_id=1))
   specs=[];uid=100
   for role in ('supervisor','staff'):
    for key,perms in [('none',[]),('all',[p.label for p in MENU_PERMISSIONS if p.selectable]),*[(p.menu_key,[p.label]) for p in MENU_PERMISSIONS if p.selectable]]:
     name=f'{role}_{key}'
     db.add(User(id=uid,username=name,display_name=name,role=role,password_hash=password,warehouse_id=1,extra_permissions=perms));db.add(UserWarehouse(user_id=uid,warehouse_id=1));specs.append({'username':name,'role':role,'key':key});uid+=1
   await db.commit()
  print('R14 isolated test backend ready',flush=True)
  await uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=18080,log_level='warning')).serve()
 patch.undo()
asyncio.run(main())

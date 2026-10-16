"""隔离菜单测试后端：使用 backend 测试依赖运行此文件，然后运行两个 .test.cjs；仅监听本机。"""
import asyncio,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'backend'))
import pytest,uvicorn
from sqlalchemy import select, event
from tests.test_round3_permissions import hr_environment
from app.main import app
from app.models import User,UserWarehouse
from tests.test_round15_employee_self import enable
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
  await enable(factory)
  password=hash_password('test-password')
  async with factory() as db:
   for u in (await db.execute(select(User))).scalars():u.password_hash=password
   specs=[];uid=100
   for role in ('supervisor','staff'):
    for key,perms in [('none',[]),('all',[p.label for p in MENU_PERMISSIONS if p.selectable]),*[(p.menu_key,[p.label]) for p in MENU_PERMISSIONS if p.selectable]]:
     name=f'{role}_{key}'
     db.add(User(id=uid,username=name,display_name=name,role=role,password_hash=password,warehouse_id=1,extra_permissions=perms));db.add(UserWarehouse(user_id=uid,warehouse_id=1));specs.append({'username':name,'role':role,'key':key});uid+=1
   await db.commit()
  print('R15 isolated test backend ready',flush=True)
  await uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=18080,log_level='warning')).serve()
 patch.undo()
asyncio.run(main())

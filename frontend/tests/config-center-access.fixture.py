"""Isolated config-center UI fixture, no production connection."""
import asyncio,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'backend'))
import pytest,uvicorn
from sqlalchemy import select,event
from tests.test_round3_permissions import hr_environment
from tests.test_round2_permissions import set_perms,auth
from app.models import User
from app.core.security import hash_password
from app.main import app
async def main():
 patch=pytest.MonkeyPatch()
 async with hr_environment(Path(tempfile.mkdtemp(prefix='config-center-ui-')),patch) as (engine,factory,client):
  @event.listens_for(engine.sync_engine,'connect')
  def sqlite_functions(conn,_):conn.create_function('to_char',2,lambda value,fmt:str(value)[:7] if value else None)
  await engine.dispose()
  for uid in (3,4):await set_perms(factory,uid,['配置中心'])
  async with factory() as db:
   for u in (await db.execute(select(User))).scalars():u.password_hash=hash_password('test-password')
   await db.commit()
  for path,value in [('/expense-approvals/threshold',42),('/suppliers/purchase-approval-threshold',123),('/suppliers/concentration-threshold',80)]:
   r=await client.put('/api/v1'+path,headers=auth(1),json={'threshold':value});assert r.status_code==200,r.text
  print('Isolated config center fixture ready',flush=True)
  await uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=18080,log_level='warning')).serve()
 patch.undo()
asyncio.run(main())

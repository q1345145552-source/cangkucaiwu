"""Disposable local boss todos UI fixture; never connects to production."""
import asyncio,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'backend'))
import pytest,uvicorn
from sqlalchemy import select,event
from tests.test_round3_permissions import hr_environment
from app.models import User
from app.core.security import hash_password
from app.main import app

async def main():
 patch=pytest.MonkeyPatch()
 async with hr_environment(Path(tempfile.mkdtemp(prefix='payroll-disbursement-')),patch) as (engine,factory,client):
  @event.listens_for(engine.sync_engine,'connect')
  def sqlite_functions(conn,_):conn.create_function('to_char',2,lambda value,fmt:str(value)[:7] if value else None)
  await engine.dispose()
  from tests.test_round19_overtime_self_review import setup,create
  from tests.test_round18_advance_review import add
  await setup(factory)
  for _ in range(3):await add(factory)
  await create(client,[1,5])
  async with factory() as db:
   for u in (await db.execute(select(User))).scalars():u.password_hash=hash_password('test-password')
   await db.commit()
  print('Isolated boss todos fixture ready on 127.0.0.1:18080',flush=True)
  await uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=18080,log_level='warning')).serve()
 patch.undo()
asyncio.run(main())

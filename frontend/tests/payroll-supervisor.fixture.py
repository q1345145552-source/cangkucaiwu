"""Round 16 local disposable payroll comparison UI fixture; no production connections."""
import asyncio,sys,tempfile
from pathlib import Path
from datetime import date,datetime
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'backend'))
import pytest,uvicorn
from sqlalchemy import select
from tests.test_round3_permissions import hr_environment
from tests.test_round15_employee_self import enable
from tests.test_round2_permissions import auth
from app.models import User,Employee,ClockInRecord
from app.models.payroll import PayrollRecord
from app.core.security import hash_password
from app.main import app
import app.api.v1.payroll as payroll

async def main():
 patch=pytest.MonkeyPatch()
 async with hr_environment(Path(tempfile.mkdtemp(prefix='cangkucaiwu-r16-')),patch) as (_,factory,client):
  await enable(factory)
  patch.setattr(payroll,'thai_today',lambda:date(2026,10,18))
  async with factory() as db:
   for u in (await db.execute(select(User))).scalars():u.password_hash=hash_password('test-password')
   (await db.get(PayrollRecord,20)).settle_end_date=date(2026,10,15)
   for eid in (1,5):
    e=await db.get(Employee,eid);e.hire_date=datetime(2026,10,16);e.status='regular'
   for uid in (4,5):
    for day in (16,17):
     for session,hour in ((1,9),(2,12),(3,13),(4,18)):
      db.add(ClockInRecord(user_id=uid,warehouse_id=1,clock_date=date(2026,10,day),session=session,clocked_in_at=datetime(2026,10,day,hour),status='normal'))
   await db.commit()
  r=await client.post('/api/v1/payroll/calculate',headers=auth(1),json={'end_date':'2026-10-17'})
  assert r.status_code==200,r.text
  print('Round16 local isolated backend ready',flush=True)
  await uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=18080,log_level='warning')).serve()
 patch.undo()
asyncio.run(main())

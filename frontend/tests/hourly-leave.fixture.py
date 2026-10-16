"""Local disposable exact-punch reproduction. Never connects to production."""
import asyncio,sys,tempfile
from pathlib import Path
from datetime import date,datetime
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'backend'))
import pytest,uvicorn
from sqlalchemy import select,delete
from tests.test_round3_permissions import hr_environment
from tests.test_round2_permissions import auth
from app.models import User,Employee,ClockInRecord,LeaveRequest,RestDay
from app.models.payroll import PayrollRecord
from app.core.security import hash_password
from app.main import app
import app.api.v1.payroll as payroll

async def main():
 patch=pytest.MonkeyPatch()
 async with hr_environment(Path(tempfile.mkdtemp(prefix='hourly-leave-')),patch) as (_,factory,client):
  patch.setattr(payroll,'thai_today',lambda:date(2026,10,18))
  async with factory() as db:
   for u in (await db.execute(select(User))).scalars():u.password_hash=hash_password('test-password')
   await db.execute(delete(PayrollRecord).where(PayrollRecord.employee_id==1))
   await db.execute(delete(RestDay).where(RestDay.employee_id==1))
   e=await db.get(Employee,1);e.name='Khin Than Dar Tway';e.hire_date=datetime(2026,10,4);e.status='regular'
   (await db.get(User,5)).display_name=e.name
   for session,t in enumerate(('08:41:54','12:02:00','12:48:04','15:25:47'),1):
    db.add(ClockInRecord(user_id=5,warehouse_id=1,clock_date=date(2026,10,4),session=session,clocked_in_at=datetime.fromisoformat('2026-10-04T'+t),status='normal'))
   db.add(LeaveRequest(employee_id=1,warehouse_id=1,leave_date=date(2026,10,4),leave_type='personal',duration_type='hours',hours=2.3,status='approved',notified_at=datetime(2026,10,3)))
   await db.commit()
  r=await client.post('/api/v1/payroll/calculate',headers=auth(1),json={'end_date':'2026-10-04','employee_ids':[1]});assert r.status_code==200,r.text
  print('Exact hourly leave local test backend ready',flush=True)
  await uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=18080,log_level='warning')).serve()
 patch.undo()
asyncio.run(main())

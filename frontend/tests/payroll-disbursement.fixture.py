"""Disposable local payroll/expense UI fixture; never connects to production."""
import asyncio,sys,tempfile
from pathlib import Path
from datetime import date
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'backend'))
import pytest,uvicorn
from sqlalchemy import select,event
from tests.test_round3_permissions import hr_environment
from app.models import User,UserWarehouse,Employee,PaymentAccount
from app.models.payroll import PayrollRecord
from app.core.security import hash_password
from app.main import app

async def main():
 patch=pytest.MonkeyPatch()
 async with hr_environment(Path(tempfile.mkdtemp(prefix='payroll-disbursement-')),patch) as (engine,factory,client):
  @event.listens_for(engine.sync_engine,'connect')
  def sqlite_functions(conn,_):conn.create_function('to_char',2,lambda value,fmt:str(value)[:7] if value else None)
  await engine.dispose()
  async with factory() as db:
   for u in (await db.execute(select(User))).scalars():u.password_hash=hash_password('test-password')
   db.add(PaymentAccount(id=3,warehouse_id=1,account_name='现金',account_type='cash',account_number='cash',status='active',currency='THB'))
   db.add(PaymentAccount(id=4,warehouse_id=1,account_name='停用账户',account_type='bank',account_number='inactive',status='inactive',currency='THB'))
   db.add(PaymentAccount(id=5,warehouse_id=1,account_name='美元账户',account_type='bank',account_number='usd',status='active',currency='USD'))
   (await db.get(PaymentAccount,2)).status='inactive'
   db.add(User(id=7,username='empty_admin',display_name='无可用账户测试管理员',role='warehouse_admin',warehouse_id=2,password_hash=hash_password('test-password'),extra_permissions=[]))
   db.add(UserWarehouse(user_id=7,warehouse_id=2))
   for eid,name in [(3,'批量员工甲'),(4,'批量员工乙'),(8,'手机发放员工'),(9,'工资单发放员工')]:
    db.add(Employee(id=eid,warehouse_id=1,name=name,status='regular'))
   for rid,eid,amount in [(11,3,100.01),(12,4,200.02),(13,8,345.67),(14,9,456.78)]:
    db.add(PayrollRecord(id=rid,warehouse_id=1,employee_id=eid,period='2026-10',half='first_half',settle_start_date=date(2026,10,1),settle_end_date=date(2026,10,15),status='confirmed',disbursed=False,net_pay=amount,base_pay=amount,detail='{}'))
   (await db.get(PayrollRecord,10)).status='confirmed'
   await db.commit()
  print('Isolated payroll disbursement fixture ready on 127.0.0.1:18080',flush=True)
  await uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=18080,log_level='warning')).serve()
 patch.undo()
asyncio.run(main())

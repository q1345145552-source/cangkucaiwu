"""Disposable loopback fixture for navigation only; browser checks never save business data."""
import os,sys,asyncio,tempfile,json
from pathlib import Path
from datetime import date
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'backend'))
os.environ['SECRET_KEY']='synthetic-global-page-back-only-20261028'
os.environ['INCOMING_TEST_DATABASE_URL']='postgresql+asyncpg://supplier_import@127.0.0.1:61135/postgres'
from pytest import MonkeyPatch
from sqlalchemy import select,func
from tests.test_supplier_workflow_round1 import setup
from tests.test_round2_permissions import auth
from app.models import User,Employee,CashAdvance
from app.database import Base
from app.main import app
import uvicorn
async def run():
 with MonkeyPatch.context() as mp:
  async with setup(Path(tempfile.mkdtemp(prefix='page-back-only-')),mp) as (_,factory,client):
   async with factory() as db:
    for uid in [3,4,5]:
     employee=Employee(warehouse_id=1,name=f'合成员工{uid}',user_id=uid,status='regular',base_salary=12000)
     db.add(employee);await db.flush();user=await db.get(User,uid);user.attendance_enabled=True;user.attendance_employee_id=employee.id
    db.add(CashAdvance(id=1,warehouse_id=1,payer_id=1,payer_name='合成垫款人',advance_date=date(2026,10,28),amount=3000,currency='THB',purpose='purchase',created_by_id=1,created_by_name='合成登记人'))
    await db.commit()
   Path('/tmp/global-page-back-auth.json').write_text(json.dumps({'admin':auth(1),'platform':auth(2),'staff':auth(3),'labor':auth(5)}))
   from app.core.action_access import ROUTES
   mp.setitem(ROUTES,('GET','/api/v1/_test/navigation-snapshot'),{'id':'synthetic.navigation.snapshot'})
   @app.get('/api/v1/_test/navigation-snapshot')
   async def snapshot():
    async with factory() as db:
     return {name:await db.scalar(select(func.count()).select_from(table)) for name,table in Base.metadata.tables.items() if name not in ['audit_logs','login_logs','alembic_version']}
   await uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=19510,log_level='warning')).serve()
asyncio.run(run())

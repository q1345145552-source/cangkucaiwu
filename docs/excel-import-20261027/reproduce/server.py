import os,sys,asyncio,json
from pathlib import Path
sys.path.insert(0,'/Users/xiongliu/Desktop/海外仓财务系统/backend')
os.environ['INCOMING_TEST_DATABASE_URL']='postgresql+asyncpg://supplier_import@127.0.0.1:61135/postgres'
os.environ['SECRET_KEY']='isolated-excel-import-synthetic-secret'
from pytest import MonkeyPatch
from tests.test_supplier_workflow_round1 import setup
from tests.test_round2_permissions import auth
from sqlalchemy import text
from app.models import Supplier,User
from app.models.supplier import SupplierCategory
from app.main import app
from app.core.security import hash_password
import uvicorn
async def main():
 folder=Path('/tmp/excel-import-browser-data');folder.mkdir(exist_ok=True)
 with MonkeyPatch.context() as mp:
  async with setup(folder,mp) as (_,factory,c):
   async with factory() as db:
    db.add_all([SupplierCategory(id=1,name='耗材商'),SupplierCategory(id=2,name='物流')]);await db.flush()
    (await db.get(Supplier,1)).category_id=1
    db.add_all([Supplier(id=3,warehouse_id=1,name='合成供应商乙',category_id=1),Supplier(id=4,warehouse_id=1,name='合成物流商',category_id=2)])
    await db.execute(text("SELECT setval(pg_get_serial_sequence('supplier_products','id'),(SELECT max(id) FROM supplier_products))"))
    (await db.get(User,1)).password_hash=hash_password('synthetic-import-test')
    await db.commit()
   Path('/tmp/excel-import-browser-auth.json').write_text(json.dumps(auth(1)))
   await uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=19140,log_level='warning')).serve()
asyncio.run(main())

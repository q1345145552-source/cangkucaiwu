"""Loopback-only synthetic fixture; all UI checks are read/preview/cancel, never real data."""
import sys,os,asyncio,tempfile,json,io
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'backend'))
os.environ['SECRET_KEY']='isolated-hide-logistics-modal-test-key-20261028'
os.environ['INCOMING_TEST_DATABASE_URL']='postgresql+asyncpg://supplier_import@127.0.0.1:61135/postgres'
from pytest import MonkeyPatch
from sqlalchemy import select,func
from tests.test_supplier_quotes_round6 import fixture,quoted
from tests.test_supplier_sku_round5 import sku,product,map_it
from tests.test_excel_import_repair import template,fill
from tests.test_round2_permissions import auth
from app.models import Supplier,User,StandardSKU,SystemSetting
from app.models.supplier import SupplierCategory
from app.database import Base
from app.main import app
import uvicorn

async def run():
 with MonkeyPatch.context() as mp:
  async with fixture(Path(tempfile.mkdtemp(prefix='hidden-logistics-modal-')),mp) as (_,f,c,_):
   async with f() as db:
    for id,name in [(1,'耗材商'),(2,'物流')]:
     if not await db.get(SupplierCategory,id):db.add(SupplierCategory(id=id,name=name))
    await db.flush();(await db.get(Supplier,1)).category_id=1
    db.add(Supplier(id=4,warehouse_id=1,category_id=2,name='合成旧物流档案',default_currency='THB'))
    db.add(SystemSetting(warehouse_id=1,key='purchase_approval_threshold',value='0'))
    (await db.get(User,3)).extra_permissions=['@wf-actions:1','suppliers:operate']
    await db.commit()
   s=await sku(c,name='合成白底袋');p=await product(c,product_name='合成白底袋');await map_it(c,p['id'],s)
   q,_=await quoted(c,p['id'],s,code='OPAQUE-TEST')
   out=Path('/tmp/hide-logistics-modal-fixture');out.mkdir(exist_ok=True)
   data=await template(c,'/suppliers/import-template/products?batch=true')
   (out/'products-preview.xlsx').write_bytes(fill(data,[['本仓供应商','合成预览袋','38×52cm','个',1.25,'THB',None,None,None,None,None]]))
   Path('/tmp/hide-logistics-modal-auth.json').write_text(json.dumps({'admin':auth(1),'operate':auth(3),'product_id':p['id'],'quote_id':q['id']}))
   # Register this fixture-only read endpoint; production action catalog is untouched.
   from app.core.action_access import ROUTES
   mp.setitem(ROUTES,('GET','/api/v1/_test/modal-snapshot'),{'id':'synthetic.snapshot'})
   @app.get('/api/v1/_test/modal-snapshot')
   async def snapshot():
    tables=['supplier_products','supplier_cross_border_prices','supplier_route_prices','supplier_quotes','supplier_quote_revisions','purchase_orders','payable_bills','payable_payments','expense_records','income_records','inventory_movements','purchase_receipt_events']
    async with f() as db:
     counts={name:await db.scalar(select(func.count()).select_from(Base.metadata.tables[name])) for name in tables if name in Base.metadata.tables}
     rows=(await db.execute(select(Supplier).order_by(Supplier.id))).scalars().all()
     return {'counts':counts,'suppliers':[{'id':r.id,'name':r.name,'category_id':r.category_id,'is_active':r.is_active} for r in rows]}
   await uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=19410,log_level='warning')).serve()
asyncio.run(run())

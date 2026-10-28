"""Real original logistics route with operate-only grant and existing price fields."""
from fixtures import *
from app.models.supplier import SupplierCrossBorderPrice
async def main():
 engine=create_async_engine(URL);factory=async_sessionmaker(engine,expire_on_commit=False)
 database._engine=engine;database._session_maker=factory
 async with factory() as db:
  user=await db.get(User,3);user.extra_permissions=['@wf-actions:1','suppliers:operate'];await db.commit()
 records=[]
 async with AsyncClient(transport=ASGITransport(app=app),base_url='http://round6.local') as client:
  headers={'Authorization':'Bearer '+create_access_token({'sub':'3'}),'X-Warehouse-ID':'1'}
  r=await client.get('/api/v1/access/catalog?role=staff',headers=headers);assert r.status_code==200
  contract=next(x['form'] for x in r.json()['routes'] if x['id']=='suppliers.add_logistics_price')
  assert set(contract['body']['properties'])=={'transport_method','cargo_type','origin_warehouse','price_per_cbm','estimated_days','currency','remark'}
  assert set(contract['body']['required'])=={'transport_method','cargo_type','origin_warehouse','price_per_cbm'}
  before=await snapshot(factory)
  body={'transport_method':'海运','cargo_type':'普货','origin_warehouse':'SYNTHETIC','price_per_cbm':5,'currency':'CNY'}
  r=await client.post('/api/v1/suppliers/1/logistics-prices',headers=headers,json=body);assert r.status_code==200,r.text
  after=await snapshot(factory);diff={t:{'before':before[t],'after':after[t]} for t in before if before[t]!=after[t]}
  assert set(diff)<= {'supplier_cross_border_prices','audit_logs','data_change_history'}
  async with factory() as db:
   saved=await db.get(SupplierCrossBorderPrice,r.json()['id']);assert saved.supplier_id==1 and saved.price_per_cbm==5 and saved.currency=='CNY'
  records.append({'id':'operate-only-logistics','method':'POST','path':'/suppliers/1/logistics-prices','request':body,'expected':200,'actual':r.status_code,'response':r.json(),'database_diff':diff,'errors':[]})
  before=await snapshot(factory);r=await client.get('/api/v1/suppliers',headers=headers);assert r.status_code==403
  assert await snapshot(factory)==before
  records.append({'id':'no-full-list','method':'GET','path':'/suppliers','expected':403,'actual':r.status_code,'response':r.json(),'database_diff':{},'errors':[]})
 (OUT/'requests.json').write_text(json.dumps(records,ensure_ascii=False,indent=2));(OUT/'status.json').write_text(json.dumps({'requests':3,'failures':[]}))
 await engine.dispose()
asyncio.run(main())

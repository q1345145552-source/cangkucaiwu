"""Only disposable localhost schemas; catalog, mapping and old procurement invariants."""
import asyncio,json,os,uuid,io
from pathlib import Path
from contextlib import asynccontextmanager
import pytest
from openpyxl import Workbook
from sqlalchemy import select,func,text
from app.models import StandardSKU,SupplierProduct,ProductSkuMappingEvent,ProductImportOperation,User,UserWarehouse,PurchaseOrder,CostIdentity,ProcurementPriceHistory
from app.services import sku_catalog as catalog
from tests.test_supplier_cost_identity_round4 import fixture as round4_fixture
from tests.test_supplier_workflow_round1 import request
from tests.test_incoming_operations import URL
from tests.test_round2_permissions import auth,png

pytestmark=pytest.mark.skipif(not URL,reason='Explicit disposable localhost PostgreSQL required')
ATTRS={'material':'PE','width':{'value':38,'unit':'cm'},'packaging':'single'}
ACTUAL={}
def actual(key,value):
 ACTUAL[key]=value
 if os.environ.get('SUPPLIER05_REPORT'):Path(os.environ['SUPPLIER05_REPORT']).write_text(json.dumps(ACTUAL,ensure_ascii=False,default=str,indent=2))

@asynccontextmanager
async def fixture(tmp_path,mp):
 async with round4_fixture(tmp_path,mp) as (engine,f,c,receipt):
  async with f() as db:
   for uid,perms in [(3,['供应商管理','标准SKU目录']),(4,['供应商管理','标准SKU目录','标准SKU管理']),(8,['标准SKU管理'])]:
    (await db.get(User,uid)).extra_permissions=perms
   db.add(User(id=10,username='catalog-reader',display_name='目录只读',password_hash='unused',role='staff',warehouse_id=1,extra_permissions=['标准SKU目录']))
   db.add(UserWarehouse(user_id=10,warehouse_id=1));await db.commit()
   await db.execute(text("SELECT setval(pg_get_serial_sequence('supplier_products','id'),(SELECT max(id) FROM supplier_products))"));await db.commit()
  yield engine,f,c,receipt

async def sku(c,**values):
 return await request(c,'POST','/sku-catalog',json={'code':'BAG-38','name':'标准袋','attributes':ATTRS,'base_unit':'个',**values})

async def product(c,**values):
 return await request(c,'POST','/suppliers/1/products',json={'product_name':'另一种叫法','spec':'38cm PE单只','unit_price':5,'unit':'个','currency':'THB','catalog_attributes':ATTRS,**values})

async def map_it(c,pid,s,uid=1,**values):
 p=await request(c,'GET',f'/sku-catalog/products/{pid}/candidates',uid=uid)
 return await request(c,'POST',f'/sku-catalog/products/{pid}/mapping',uid=uid,json={'request_key':uuid.uuid4().hex,'sku_id':s['id'],
  'expected_product_version':p['product_version'],'expected_sku_version':s['version'],'reason':'已逐项核对原规格及基本单位',**values})

def workbook(rows,headers=None):
 w=Workbook();w.active.append(headers or ['产品名','产品规格','规格报价','单价','单位','币种','标准SKU编码','结构化规格JSON','基本单位换算数'])
 for r in rows:w.active.append(r)
 b=io.BytesIO();w.save(b);return b.getvalue()

def test_exact_attributes_suggest_without_auto_merge_and_snapshot_is_immutable(tmp_path,monkeypatch):
 async def run():
  async with fixture(tmp_path,monkeypatch) as (_,f,c,receipt):
   s=await sku(c);p=await product(c);suggested=await request(c,'GET',f'/sku-catalog/products/{p["id"]}/candidates')
   assert suggested['candidates'][0]['id']==s['id'] and suggested['candidates'][0]['auto_mapped'] is False
   async with f() as db:
    assert (await db.get(SupplierProduct,p['id'])).standard_sku_id is None
    old=json.loads(json.dumps((await db.get(PurchaseOrder,1)).items))
   mapped=await map_it(c,p['id'],s)
   po=await request(c,'POST','/suppliers/1/purchase-order',json={'items':[{'product_id':p['id'],'quantity':2}]})
   detail=await request(c,'GET',f'/suppliers/purchase-orders/{po["order"]["id"]}')
   line=detail['items'][0];assert line['line_id'] and line['unit']=='个' and line['sku_mapping']['standard_sku_id']==s['id']
   assert line['sku_mapping']['base_quantity']=='2.00000000' and line['sku_mapping']['comparable'] is True
   async with f() as db:raw_new=json.loads(json.dumps((await db.get(PurchaseOrder,po['order']['id'])).items))
   changed=await request(c,'PUT',f'/sku-catalog/{s["id"]}',json={**{k:s[k] for k in ['code','name','attributes','base_unit','category_id','active']},'name':'目录新显示名','expected_version':s['version']})
   async with f() as db:
    assert (await db.get(PurchaseOrder,1)).items==old
    assert (await db.get(PurchaseOrder,po['order']['id'])).items==raw_new
    assert raw_new[0]['sku_mapping']==line['sku_mapping']
    history=(await db.execute(select(ProcurementPriceHistory).where(ProcurementPriceHistory.purchase_order_id==po['order']['id']))).scalar_one()
    assert history.currency=='THB' and history.unit=='个' and history.sku_snapshot==line['sku_mapping']
   listed=await request(c,'GET','/suppliers/1/products');r=next(r for r in listed['data'] if r['id']==p['id']);assert r['mapping_status']=='stale'
   actual('suggest_map_snapshot',{'suggested':suggested,'mapping':mapped,'new_line':line,'changed_catalog':changed,'old_orders_unchanged':True})
 asyncio.run(run())

def test_permissions_code_conflict_specs_units_and_cross_warehouse(tmp_path,monkeypatch):
 async def run():
  async with fixture(tmp_path,monkeypatch) as (_,f,c,receipt):
   body={'code':' bag-38 ','name':'标准袋','attributes':ATTRS,'base_unit':'个'}
   for uid in (2,3,5,8,9,10):await request(c,'POST','/sku-catalog',uid=uid,code=403,json=body)
   s=await request(c,'POST','/sku-catalog',uid=4,json=body);assert s['code']=='BAG-38'
   for uid in (1,3,4,10):assert (await request(c,'GET','/sku-catalog',uid=uid))['data']
   for uid in (2,5,8,9):await request(c,'GET','/sku-catalog',uid=uid,code=403)
   await request(c,'POST','/sku-catalog',code=409,json={**body,'attributes':{**ATTRS,'material':'PVC'}})
   await request(c,'POST','/sku-catalog',code=400,json={**body,'code':'BAD','base_unit':'不明单位'})
   p=await product(c,catalog_attributes={**ATTRS,'material':'PVC'})
   candidates=await request(c,'GET',f'/sku-catalog/products/{p["id"]}/candidates')
   await request(c,'POST',f'/sku-catalog/products/{p["id"]}/mapping',code=400,json={'request_key':'bad-spec','sku_id':s['id'],'expected_product_version':candidates['product_version'],'expected_sku_version':s['version'],'reason':'不能拿理由绕过规格'})
   await request(c,'POST',f'/sku-catalog/products/{p["id"]}/mapping',code=400,json={'request_key':'override-spec','sku_id':s['id'],'expected_product_version':candidates['product_version'],'expected_sku_version':s['version'],'confirmed_attributes':ATTRS,'reason':'不能用确认字段覆盖已记录的不同材质'})
   await request(c,'PUT',f'/sku-catalog/{s["id"]}',uid=7,warehouse='2',code=404,json={**body,'expected_version':s['version']})
   await request(c,'GET',f'/sku-catalog/products/{p["id"]}/candidates',uid=7,warehouse='2',code=404)
   assert (await request(c,'GET','/sku-catalog',uid=7,warehouse='2'))['data']==[]
   await request(c,'POST','/suppliers/categories?name=不应新增',code=403)
   actual('permissions_specs',{'code':s['code'],'read_only_users':[3,10],'manage_user':4,'no_read_or_write':[2,5,8,9],'cross_warehouse':404,'different_specs_not_merged':True})
 asyncio.run(run())

def test_concurrent_code_mapping_versions_and_replays(tmp_path,monkeypatch):
 async def run():
  async with fixture(tmp_path,monkeypatch) as (_,f,c,receipt):
   body={'code':'RACE','name':'并发目录','attributes':ATTRS,'base_unit':'piece'}
   responses=await asyncio.gather(c.post('/api/v1/sku-catalog',headers=auth(1),json=body),c.post('/api/v1/sku-catalog',headers=auth(1),json={**body,'attributes':{**ATTRS,'material':'PVC'}}))
   assert sorted(r.status_code for r in responses)==[200,409]
   a=await sku(c,code='MAP-A');b=await sku(c,code='MAP-B');p=await product(c)
   candidate=await request(c,'GET',f'/sku-catalog/products/{p["id"]}/candidates');assert candidate['multiple_candidates']
   def data(s,key):return {'request_key':key,'sku_id':s['id'],'expected_product_version':candidate['product_version'],'expected_sku_version':s['version'],'reason':'并发人工核对，不自动覆盖'}
   first,second=data(a,'map-race-a'),data(b,'map-race-b');path=f'/api/v1/sku-catalog/products/{p["id"]}/mapping'
   result=await asyncio.gather(c.post(path,headers=auth(4),json=first),c.post(path,headers=auth(4),json=second))
   assert sorted(r.status_code for r in result)==[200,409]
   winner=0 if result[0].status_code==200 else 1;payload=[first,second][winner]
   replay=await c.post(path,headers=auth(4),json=payload);assert replay.status_code==200 and replay.json()['id']==result[winner].json()['id']
   changed=await c.post(path,headers=auth(4),json={**payload,'reason':'不同内容不能改原请求'});assert changed.status_code==409
   async with f() as db:assert (await db.execute(select(func.count(ProductSkuMappingEvent.id)))).scalar_one()==1
   updates=await asyncio.gather(*[c.put(f'/api/v1/sku-catalog/{a["id"]}',headers=auth(1),json={**body,'code':'MAP-A','name':name,'expected_version':a['version']}) for name in ['第一位修改','第二位修改']])
   assert sorted(r.status_code for r in updates)==[200,409]
   actual('concurrency',{'create_status':[r.status_code for r in responses],'map_status':[r.status_code for r in result],'edit_status':[r.status_code for r in updates],'one_mapping_event':True,'replay':replay.json()})
 asyncio.run(run())

def test_tags_classification_readonly_and_references_survive_deactivation(tmp_path,monkeypatch):
 async def run():
  from app.models import SupplierCategory,Supplier,SupplierWarehouseTag,SupplierTagLink
  async with fixture(tmp_path,monkeypatch) as (_,f,c,receipt):
   async with f() as db:
    db.add(SupplierCategory(id=1,name='旧分类名',is_active='true'));await db.commit()
   s=await sku(c,category_id=1);p=await product(c);await map_it(c,p['id'],s)
   tag=await request(c,'POST','/sku-catalog/tags',json={'name':'本仓急用'})
   foreign=await request(c,'POST','/sku-catalog/tags',uid=7,warehouse='2',json={'name':'本仓急用'})
   for uid in (3,9,10,2,5):await request(c,'POST','/sku-catalog/tags',uid=uid,code=403,json={'name':'不应新增'})
   initial=await request(c,'GET','/sku-catalog/suppliers/1/tags')
   await request(c,'PUT','/sku-catalog/suppliers/1/tags',code=403,json={'tag_ids':[foreign['id']],'expected_version':initial['version']})
   linked=await request(c,'PUT','/sku-catalog/suppliers/1/tags',json={'tag_ids':[tag['id']],'expected_version':initial['version']})
   await request(c,'PUT','/sku-catalog/suppliers/1/tags',code=409,json={'tag_ids':[],'expected_version':initial['version']})
   stopped=await request(c,'PUT',f'/sku-catalog/tags/{tag["id"]}',json={'name':tag['name'],'active':False,'expected_version':tag['version']})
   assert (await request(c,'GET','/sku-catalog/suppliers/1/tags'))['tag_ids']==[tag['id']]
   await request(c,'DELETE','/suppliers/1',code=409)
   async with f() as db:
    (await db.get(SupplierCategory,1)).is_active='false';await db.commit()
   deactivated=await request(c,'PUT',f'/sku-catalog/{s["id"]}',json={**{k:s[k] for k in ('code','name','attributes','base_unit','category_id')},'active':False,'expected_version':s['version']})
   await request(c,'DELETE',f'/suppliers/1/products/{p["id"]}')
   async with f() as db:
    old=await db.get(SupplierProduct,p['id']);assert old is not None and old.catalog_active is False and old.standard_sku_id==s['id']
    assert (await db.get(SupplierCategory,1)).name=='旧分类名'
    assert (await db.execute(select(func.count(ProductSkuMappingEvent.id)))).scalar_one()==1
   actual('tags_soft_references',{'own_tag':tag,'other_warehouse_tag':foreign,'assignment':linked,'inactive_tag':stopped,'inactive_sku':deactivated,'product_and_mapping_kept':True,'old_category_name_kept':True})
 asyncio.run(run())

def test_excel_mapping_versions_concurrent_retry_and_hidden_fields(tmp_path,monkeypatch):
 async def run():
  async with fixture(tmp_path,monkeypatch) as (_,f,c,receipt):
   s=await sku(c);file=workbook([['映射导入袋','38cm PE',None,4,'个','THB',s['code'],json.dumps(ATTRS)]])
   path='/suppliers/1/import/products';files={'file':('map.xlsx',file,'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')}
   pre=await request(c,'POST',path,files=files);assert pre['valid'] and pre['rows'][0]['candidates']
   changed=await request(c,'PUT',f'/sku-catalog/{s["id"]}',json={**{k:s[k] for k in ('code','name','attributes','base_unit','category_id','active')},'name':'目录显示名已变','expected_version':s['version']})
   choice={'row_number':2,'decision':'map','confirmed':True,'sku_id':s['id'],'expected_sku_version':s['version'],'reason':'按原件人工核对'}
   old_data={'mode':'confirm','request_key':'map-import','preview_version':pre['preview_version'],'choices':json.dumps([choice])}
   failed=await request(c,'POST',path,code=409,files=files,data=old_data);assert failed['detail']['code']=='product_import_preview_changed'
   pre=await request(c,'POST',path,files=files);choice['expected_sku_version']=changed['version'];data={**old_data,'preview_version':pre['preview_version'],'choices':json.dumps([choice])}
   forged={**choice,'sku_id':'1'}
   await request(c,'POST',path,code=400,files=files,data={**data,'request_key':'forged-id','choices':json.dumps([forged])})
   responses=await asyncio.gather(*[c.post('/api/v1'+path,headers=auth(1),files=files,data=data) for _ in range(2)])
   assert [r.status_code for r in responses]==[200,200] and responses[0].json()['id']==responses[1].json()['id']
   other=workbook([['改了文件','38cm',None,7]])
   await request(c,'POST',path,code=409,files={'file':('map.xlsx',other,'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')},data=data)
   async with f() as db:
    assert (await db.execute(select(func.count(SupplierProduct.id)))).scalar_one()==2
    assert (await db.execute(select(func.count(ProductSkuMappingEvent.id)))).scalar_one()==1
    assert (await db.execute(select(func.count(ProductImportOperation.id)))).scalar_one()==1
   actual('excel_mapped_replay',{'stale_preview_rejected':failed,'statuses':[r.status_code for r in responses],'result':responses[0].json(),'only_one_product_event_import':True})
 asyncio.run(run())

@pytest.mark.parametrize('kind',['duplicate','existing','unit','json','same_code_specs','formula','foreign_supplier','unknown_header'])
def test_excel_invalid_inputs_have_line_numbers_without_partial_writes(tmp_path,monkeypatch,kind):
 async def run():
  async with fixture(tmp_path,monkeypatch) as (_,f,c,receipt):
   s=await sku(c);row=['导入核对袋','新规格',None,2,'个','THB',None,None];rows=[row];headers=None;path='/suppliers/1/import/products'
   if kind=='duplicate':rows=[row,row]
   if kind=='existing':rows=[['耗材',None,None,100,'个','THB']]
   if kind=='unit':rows=[[row[0],row[1],None,2,'神秘箱','THB']]
   if kind=='json':rows=[[row[0],row[1],None,2,'个','THB',None,'{"width":1,"width":2}']]
   if kind=='same_code_specs':rows=[[row[0],row[1],None,2,'个','THB',s['code'],json.dumps({**ATTRS,'material':'PVC'})]]
   if kind=='formula':rows=[[row[0],row[1],None,'=1+1','个','THB']]
   if kind=='foreign_supplier':path='/suppliers/import/products';headers=['供应商名称','产品名','产品规格','规格报价','单价'];rows=[['外仓供应商','外仓袋','旧',None,2]]
   if kind=='unknown_header':headers=['产品名','产品规格','规格报价','单价','标准SKU编号'];rows=[['未知隐藏ID','新',None,2,999]]
   blob=workbook(rows,headers);files={'file':('invalid.xlsx',blob,'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')};preview=await request(c,'POST',path,files=files)
   assert preview['valid'] is False and preview['errors'] and all(e['row_number']>=1 for e in preview['errors'])
   await request(c,'POST',path,code=422,files=files,data={'mode':'confirm','request_key':'invalid-'+kind,'preview_version':preview['preview_version'],'choices':json.dumps([{'row_number':r['row_number'],'decision':'unmapped','confirmed':True} for r in preview['rows']])})
   async with f() as db:assert (await db.execute(select(func.count(SupplierProduct.id)))).scalar_one()==1
   actual('invalid_'+kind,preview)
 asyncio.run(run())

def test_import_failure_after_first_mapping_rolls_back_and_same_file_recovers(tmp_path,monkeypatch):
 async def run():
  from fastapi import HTTPException
  async with fixture(tmp_path,monkeypatch) as (_,f,c,receipt):
   s=await sku(c);blob=workbook([[n,'38cm',None,2,'个','THB',s['code'],json.dumps(ATTRS)] for n in ['事务袋A','事务袋B']]);files={'file':('atomic.xlsx',blob,'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')};path='/suppliers/1/import/products'
   pre=await request(c,'POST',path,files=files);choices=[{'row_number':r['row_number'],'decision':'map','confirmed':True,'sku_id':s['id'],'expected_sku_version':s['version'],'reason':'逐行核对'} for r in pre['rows']]
   data={'mode':'confirm','request_key':'atomic-failure','preview_version':pre['preview_version'],'choices':json.dumps(choices)}
   original=catalog.map_product;counter=0
   async def fail(*args,**kwargs):
    nonlocal counter
    counter+=1
    if counter==2:raise HTTPException(500,'合成：第二条映射写入失败')
    return await original(*args,**kwargs)
   monkeypatch.setattr(catalog,'map_product',fail)
   await request(c,'POST',path,files=files,data=data,code=500)
   async with f() as db:
    for model,expected in [(SupplierProduct,1),(ProductSkuMappingEvent,0),(ProductImportOperation,0)]:assert (await db.execute(select(func.count(model.id)))).scalar_one()==expected
   monkeypatch.setattr(catalog,'map_product',original);saved=await request(c,'POST',path,files=files,data=data)
   assert saved['imported']==2
   actual('import_atomic_failure',{'first_half_writes':False,'same_original_file_recovered':saved})
 asyncio.run(run())

@pytest.mark.parametrize('old',[False,True])
def test_new_old_repeat_migration_history_readonly_and_missing_guards(tmp_path,monkeypatch,old):
 async def run():
  from app.services.sku_catalog_migration import migrate_sku_catalog,COLUMNS
  from scripts.audit_sku_mapping_candidates import audit
  from sqlalchemy import event
  async with fixture(tmp_path,monkeypatch) as (engine,f,c,receipt):
   if old:
    async with engine.begin() as conn:
     for table,cols in COLUMNS.items():
      for col in cols:await conn.execute(text(f'ALTER TABLE {table} DROP COLUMN {col} CASCADE'))
     for table in ['product_sku_mapping_events','product_import_operations','supplier_tag_links','supplier_warehouse_tags','standard_skus']:await conn.execute(text(f'DROP TABLE {table} CASCADE'))
    old_report=await audit(engine,1);assert old_report['catalog_table_present'] is False and old_report['data'][0]['unit_conversion'] is None
   async with engine.begin() as conn:
    await migrate_sku_catalog(conn);await migrate_sku_catalog(conn)
   changes=[]
   def trace(conn,cursor,statement,*args):
    if statement.lstrip().upper().startswith(('INSERT','UPDATE','DELETE')):changes.append(statement)
   event.listen(engine.sync_engine,'before_cursor_execute',trace)
   try:
    report=await audit(engine,1);endpoint=await request(c,'GET','/sku-catalog/history-candidates');assert not changes
   finally:event.remove(engine.sync_engine,'before_cursor_execute',trace)
   async with f() as db:
    p=await db.get(SupplierProduct,1);assert p.standard_sku_id is None and p.base_unit_factor is None and p.catalog_attributes is None
    assert (await db.execute(select(func.count(StandardSKU.id)))).scalar_one()==0
   async with engine.begin() as conn:
    await conn.execute(text('DROP INDEX uq_standard_sku_code'));await conn.execute(text('CREATE UNIQUE INDEX uq_standard_sku_code ON standard_skus(warehouse_id,code) WHERE active=true'))
   failed=await request(c,'POST','/sku-catalog',code=503,json={'code':'GUARD','name':'不能写','attributes':ATTRS,'base_unit':'piece'})
   assert failed['detail']['code']=='sku_catalog_guards_missing'
   assert (await request(c,'GET','/sku-catalog'))['data']==[]
   actual('migration_'+str(old),{'repeat_ready':True,'report':report,'endpoint':endpoint,'writes_during_reads':changes,'missing_or_wrong_predicate':failed,'old_references_not_fabricated':True})
 asyncio.run(run())

def test_old_price_reference_does_not_mix_currency_unit_or_sku_names(tmp_path,monkeypatch):
 async def run():
  async with fixture(tmp_path,monkeypatch) as (_,f,c,receipt):
   p=await product(c)
   for currency,unit,price in [('CNY','个',1),('THB','箱',0.5)]:
    await request(c,'POST','/suppliers/3/products',json={'product_name':'另一种叫法','spec':'38cm PE单只','unit_price':price,'unit':unit,'currency':currency})
   listing=await request(c,'GET','/suppliers/1/products');row=next(r for r in listing['data'] if r['id']==p['id']);assert row['min_price']==5 and row['mapping_status']=='unmapped' and row['comparable'] is False
   po=await request(c,'POST','/suppliers/1/purchase-order',json={'items':[{'product_id':p['id'],'quantity':1}]});assert po.get('need_reason') is not True
   actual('reference_currency_unit',{'own_quote':row,'order':po,'currency_and_box_quotes_not_compared':True})
 asyncio.run(run())

def test_pack_conversion_unknown_and_unmapped_legacy_purchase_chain(tmp_path,monkeypatch):
 async def run():
  async with fixture(tmp_path,monkeypatch) as (_,f,c,receipt):
   s=await sku(c);p=await product(c,unit='箱');mapped=await map_it(c,p['id'],s)
   listed=await request(c,'GET','/suppliers/1/products');r=next(r for r in listed['data'] if r['id']==p['id']);assert r['mapping_status']=='unit_unknown' and r['base_unit_factor'] is None and r['comparable'] is False
   po=await request(c,'POST','/suppliers/1/purchase-order',json={'items':[{'product_id':1,'quantity':2}]})
   oid=po['order']['id'];detail=await request(c,'GET',f'/suppliers/purchase-orders/{oid}');line=detail['items'][0]
   assert line['sku_mapping']['mapping_status']=='unmapped' and line['sku_mapping']['base_quantity'] is None
   received=await request(c,'POST',f'/suppliers/purchase-orders/{oid}/receive',data={'request_key':'legacy-receipt','items':json.dumps([{'line_id':line['line_id'],'received_quantity':2}])},files={'file':('proof.png',png(),'image/png')})
   paid=await request(c,'PUT',f'/payable/{po["payable_bill_id"]}/pay',params={'paid_amount':200,'account_id':1,'payment_method':'现金','request_key':'legacy-pay'})
   async with f() as db:assert (await db.execute(select(func.count(CostIdentity.id)))).scalar_one()==1
   actual('pack_unknown_legacy',{'mapped':mapped,'read_view':r,'old_unmapped_new_order_line':line,'received':received,'paid':paid,'one_cost_root':True})
 asyncio.run(run())

def test_excel_preview_confirm_replay_and_invalid_rows_are_atomic(tmp_path,monkeypatch):
 async def run():
  async with fixture(tmp_path,monkeypatch) as (_,f,c,receipt):
   file=workbook([['导入袋A','旧格式',None,3]],['产品名','产品规格','规格报价','单价'])
   path='/suppliers/1/import/products';files={'file':('products.xlsx',file,'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')}
   preview=await request(c,'POST',path,files=files);assert preview['valid'] and preview['imported']==0
   async with f() as db:assert (await db.execute(select(func.count(SupplierProduct.id)))).scalar_one()==1
   data={'mode':'confirm','preview_version':preview['preview_version'],'request_key':'import-legacy','choices':json.dumps([{'row_number':2,'decision':'unmapped','confirmed':True}])}
   saved=await request(c,'POST',path,files=files,data=data);again=await request(c,'POST',path,files=files,data=data);assert saved['data']==again['data'] and again['replayed']
   bad=workbook([['新袋B','未知',None,3,'个','THB'],['错误袋','错误',None,-1,'不明','THB']])
   badfiles={'file':('bad.xlsx',bad,'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')};pre=await request(c,'POST',path,files=badfiles);assert pre['valid'] is False and pre['errors'][0]['row_number']==3
   await request(c,'POST',path,files=badfiles,code=422,data={'mode':'confirm','preview_version':pre['preview_version'],'request_key':'bad-import','choices':json.dumps([{'row_number':r['row_number'],'decision':'unmapped','confirmed':True} for r in pre['rows']])})
   async with f() as db:
    assert (await db.execute(select(func.count(SupplierProduct.id)))).scalar_one()==2
    assert (await db.execute(select(func.count(ProductImportOperation.id)))).scalar_one()==1
   actual('excel_legacy_atomic',{'preview':preview,'saved':saved,'retry':again,'invalid_preview':pre,'no_partial_products':True})
 asyncio.run(run())

def test_explicit_mapping_ids_and_missing_foreign_key_fail_closed(tmp_path,monkeypatch):
 async def run():
  async with fixture(tmp_path,monkeypatch) as (engine,f,c,receipt):
   s=await sku(c);p=await product(c);v=await request(c,'GET',f'/sku-catalog/products/{p["id"]}/candidates')
   payload={'sku_id':s['id'],'expected_product_version':v['product_version'],'expected_sku_version':s['version'],'request_key':'strict-mapping','reason':'明确选择'}
   for invalid in [True,str(s['id'])]:await request(c,'POST',f'/sku-catalog/products/{p["id"]}/mapping',code=422,json={**payload,'sku_id':invalid})
   await request(c,'POST',f'/sku-catalog/products/{p["id"]}/mapping',code=422,json={k:v for k,v in payload.items() if k!='sku_id'})
   async with engine.begin() as conn:
    name=(await conn.execute(text("SELECT c.conname FROM pg_constraint c JOIN pg_class t ON t.oid=c.conrelid JOIN pg_namespace n ON n.oid=t.relnamespace WHERE n.nspname=current_schema() AND t.relname='product_sku_mapping_events' AND c.contype='f' AND pg_get_constraintdef(c.oid) LIKE 'FOREIGN KEY (product_id)%'"))).scalar_one()
    await conn.execute(text(f'ALTER TABLE product_sku_mapping_events DROP CONSTRAINT "{name}"'))
   failed=await request(c,'POST',f'/sku-catalog/products/{p["id"]}/mapping',code=503,json=payload)
   assert 'product_sku_mapping_events.product_id_foreign_key' in failed['detail']['missing']
   async with f() as db:
    assert (await db.get(SupplierProduct,p['id'])).standard_sku_id is None
    assert (await db.execute(select(func.count(ProductSkuMappingEvent.id)))).scalar_one()==0
   actual('strict_ids_missing_fk',{'invalid_and_omitted_ids':422,'missing_fk':failed,'no_partial_mapping':True})
 asyncio.run(run())

def test_global_legacy_import_supplier_only_can_keep_unmapped_not_map(tmp_path,monkeypatch):
 async def run():
  async with fixture(tmp_path,monkeypatch) as (_,f,c,receipt):
   s=await sku(c);await sku(c,code='BAG-ALIAS',name='同规格第二候选')
   p=await product(c);options=await request(c,'GET',f'/sku-catalog/products/{p["id"]}/candidates')
   assert options['multiple_candidates'] and all(not x['auto_mapped'] for x in options['candidates'])
   file=workbook([['本仓供应商','旧全局五列','原始规格',None,9]],['供应商名称','产品名','产品规格','规格报价','单价'])
   path='/suppliers/import/products';files={'file':('legacy.xlsx',file,'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')}
   pre=await request(c,'POST',path,uid=9,files=files);assert pre['valid'] and pre['rows'][0]['candidates']==[]
   data={'mode':'confirm','preview_version':pre['preview_version'],'request_key':'supplier-only-import','choices':json.dumps([{'row_number':2,'decision':'map','confirmed':True,'sku_id':s['id'],'expected_sku_version':s['version'],'confirmed_attributes':ATTRS,'reason':'不能用供应商权限越权管理SKU'}])}
   await request(c,'POST',path,uid=9,code=403,files=files,data=data)
   data['choices']=json.dumps([{'row_number':2,'decision':'unmapped','confirmed':True}])
   saved=await request(c,'POST',path,uid=9,files=files,data=data)
   async with f() as db:
    row=await db.get(SupplierProduct,saved['data'][0]['product_id']);assert row.standard_sku_id is None and row.product_name=='旧全局五列' and row.unit_price==9
   actual('global_legacy_supplier_only',{'preview':pre,'confirmed':saved,'no_directory_grant_no_mapping':True,'multiple_candidates':len(options['candidates'])})
 asyncio.run(run())

"""Only disposable localhost: actual frozen procurement, monthly read endpoints and CSV."""
import asyncio,json,os,uuid,copy,csv,io
from datetime import datetime,timezone
from decimal import Decimal
from pathlib import Path
from sqlalchemy import select,func,event
import pytest
from app.models import PurchaseOrder,ProcurementPriceHistory,PayableBill,SupplierProduct,User,ProcurementPriceAnomaly
from tests.test_supplier_quotes_round6 import fixture,quoted,preview,FEES
from tests.test_supplier_sku_round5 import sku,product,map_it,ATTRS
from tests.test_supplier_workflow_round1 import request
from tests.test_round2_permissions import auth
from tests.test_incoming_operations import URL
pytestmark=pytest.mark.skipif(not URL,reason='Explicit disposable localhost required')
ACTUAL={}
def actual(key,value):
 ACTUAL[key]=value
 if os.environ.get('SUPPLIER07_REPORT'):Path(os.environ['SUPPLIER07_REPORT']).write_text(json.dumps(ACTUAL,ensure_ascii=False,default=str,indent=2))

async def scenario(c,f,box=False):
 s=await sku(c);history_product=await product(c,product_name='历史同SKU叫法',unit_price=10);await map_it(c,history_product['id'],s)
 q,b=await quoted(c,history_product['id'],s,tiers=[{'min_quantity':'1','max_quantity':None,'unit_price':'10'}]);v=await preview(c,history_product['id'],q['id'],1)
 old=await request(c,'POST','/suppliers/1/purchase-order',json={'request_key':'history10','pricing_version':v['version'],'items':[{'product_id':history_product['id'],'quote_id':q['id'],'quantity':1}]})
 async with f() as db:
  (await db.get(PurchaseOrder,old['order']['id'])).created_at=datetime(2026,9,20,tzinfo=timezone.utc)
  h=(await db.execute(select(ProcurementPriceHistory))).scalar_one();h.created_at=datetime(2026,9,20,tzinfo=timezone.utc);await db.commit()
 other=await request(c,'POST','/suppliers/3/products',json={'product_name':'另一供应商同SKU','spec':'38cm PE','unit_price':7,'unit':'个','currency':'THB','catalog_attributes':ATTRS});await map_it(c,other['id'],s)
 low,lb=await quoted(c,other['id'],s,tiers=[{'min_quantity':'1','max_quantity':None,'unit_price':'7'}])
 if box:
  p=await product(c,product_name='整箱同SKU',unit='箱',unit_price=80);await map_it(c,p['id'],s,base_unit_factor='10')
  q,b=await quoted(c,p['id'],s,unit='箱',base_unit_factor='10',conversion_basis='合成规格核对一箱10个',tiers=[{'min_quantity':'1','max_quantity':None,'unit_price':'80'}]);qty=1
 else:
  p=history_product;q=await request(c,'PUT',f'/supplier-quotes/{q["id"]}',json={**b,'request_key':uuid.uuid4().hex,'expected_quote_version':q['version'],'tiers':[{'min_quantity':'1','max_quantity':None,'unit_price':'8'}]});qty=10
 v=await preview(c,p['id'],q['id'],qty)
 body={'request_key':'selected8','pricing_version':v['version'],'items':[{'product_id':p['id'],'quote_id':q['id'],'quantity':qty,'reason':'交期更合适，人工保留选择'}]}
 po=await request(c,'POST','/suppliers/1/purchase-order',json=body)
 return po,s,p,q,low,lb,body

@pytest.mark.parametrize('box',[False,True])
def test_exact_20_and_10_same_with_confirmed_box_readonly_export_and_frozen(tmp_path,monkeypatch,box):
 async def run():
  async with fixture(tmp_path,monkeypatch) as (engine,f,c,_):
   po,s,p,q,low,lb,body=await scenario(c,f,box)
   writes=[]
   def trace(conn,cursor,statement,*args):
    if statement.lstrip().upper().startswith(('INSERT','UPDATE','DELETE')):writes.append(statement)
   event.listen(engine.sync_engine,'before_cursor_execute',trace)
   try:
    report=await request(c,'GET','/supplier-price-report',params={'month':'2026-10'});assert report['total_lines']==1
    row=report['data'][0];assert row['base_unit_label']=='个' and report['groups'][0]['sku_code']=='BAG-38';assert row['historical_difference']=='20.00' and row['lowest_difference']=='10.00' and row['base_quantity']=='10'
    assert report['coverage']['denominator']==1 and report['coverage']['historical_calculable']==report['coverage']['lowest_calculable']==1
    assert report['coverage']['historical_percent']=='100.00' and report['coverage']['lowest_percent']=='100.00'
    assert report['groups'][0]['historical']['net']=='20.00' and report['groups'][0]['lowest']['net']=='10.00'
    line=await request(c,'GET',f'/supplier-price-report/orders/{po["order"]["id"]}/lines/{row["line_id"]}');assert line['data']==row
    exported=await c.get('/api/v1/supplier-price-report/export?month=2026-10',headers=auth(1));assert exported.status_code==200
    values=list(csv.reader(io.StringIO(exported.content.decode('utf-8-sig'))));assert values[1][20]=='20.00' and values[1][22]=='10.00'
    assert not writes
   finally:event.remove(engine.sync_engine,'before_cursor_execute',trace)
   await request(c,'PUT',f'/supplier-quotes/{low["id"]}',json={**lb,'request_key':'later-price','expected_quote_version':low['version'],'tiers':[{'min_quantity':'1','max_quantity':None,'unit_price':'1'}]})
   async with f() as db:
    h=(await db.execute(select(ProcurementPriceHistory).order_by(ProcurementPriceHistory.id))).scalars().first();h.unit_price=1000
    (await db.get(SupplierProduct,p['id'])).product_name='后来改名';await db.commit()
   after=await request(c,'GET','/supplier-price-report',params={'month':'2026-10'});assert after['data']==report['data'] and after['groups']==report['groups']
   actual('box' if box else 'piece',{'report':report,'csv':values,'after':after,'writes':writes})
 asyncio.run(run())

def test_permissions_selected_warehouse_and_exact_foreign_ids(tmp_path,monkeypatch):
 async def run():
  async with fixture(tmp_path,monkeypatch) as (_,f,c,_):
   po,*_=await scenario(c,f)
   for uid in (2,5,8,10):
    for path in ['/supplier-price-report?month=2026-10','/supplier-price-report/export?month=2026-10',f'/supplier-price-report/orders/{po["order"]["id"]}/lines/{po["order"]["items"][0]["line_id"]}']:
     await request(c,'GET',path,uid=uid,code=403)
   for uid in (1,3,4):assert (await request(c,'GET','/supplier-price-report',uid=uid,params={'month':'2026-10'}))['total_lines']==1
   assert not (await request(c,'GET','/supplier-price-report',uid=7,warehouse='2',params={'month':'2026-10'}))['data']
   await request(c,'GET',f'/supplier-price-report/orders/{po["order"]["id"]}/lines/{po["order"]["items"][0]["line_id"]}',uid=7,warehouse='2',code=404)
   for tail in ('','/export'):
    await request(c,'GET','/supplier-price-report'+tail,params={'month':'2026-10','supplier_id':2},code=404)
    await request(c,'GET','/supplier-price-report'+tail,params={'month':'2026-10','orderer_id':6},code=404)
   await request(c,'GET','/supplier-price-report',params={'month':'2026-13'},code=400)
   await request(c,'GET','/supplier-price-report',warehouse='all',code=400)
   actual('permissions',{'denied':[2,5,8,10],'allowed':[1,3,4],'other_selected_warehouse_empty':True,'foreign_filter_and_line':404})
 asyncio.run(run())

async def buy(c,p,q,quantity=1,supplier_id=1,uid=1):
 v=await request(c,'POST','/supplier-quotes/purchase-preview',json={'supplier_id':supplier_id,'items':[{'product_id':p['id'],'quote_id':q['id'],'quantity':quantity}]})
 body={'request_key':uuid.uuid4().hex,'pricing_version':v['version'],'items':[{'product_id':p['id'],'quote_id':q['id'],'quantity':quantity,'reason':'合成测试人工选择'}]}
 r=await request(c,'POST',f'/suppliers/{supplier_id}/purchase-order',uid=uid,json=body)
 if r.get('need_confirm'):r=await request(c,'POST',f'/suppliers/{supplier_id}/purchase-order',uid=uid,json={**body,'confirm_price_anomaly':True,'price_review_token':r['price_review_token']})
 assert r.get('order');return r

async def clone(f,po,*,at=None,status='confirmed',flow='completed',items=None,warehouse=1,supplier=1,creator=1):
 async with f() as db:
  lines=copy.deepcopy(items if items is not None else po['order']['items'])
  for it in lines:it['line_id']=uuid.uuid4().hex
  row=PurchaseOrder(warehouse_id=warehouse,supplier_id=supplier,order_number='CLONE-'+uuid.uuid4().hex,total_amount=po['order']['total_amount'],currency='THB',items=lines,status=status,flow_status=flow,created_by=creator,created_at=at or datetime(2026,10,20,tzinfo=timezone.utc));db.add(row);await db.commit()
  return row.id,lines

def test_different_quantities_same_product_lines_negative_differences_and_filters(tmp_path,monkeypatch):
 async def run():
  async with fixture(tmp_path,monkeypatch) as (_,f,c,_):
   po,s,p,q,low,lb,_=await scenario(c,f)
   v=await request(c,'POST','/supplier-quotes/purchase-preview',json={'supplier_id':1,'items':[{'product_id':p['id'],'quote_id':q['id'],'quantity':2},{'product_id':p['id'],'quote_id':q['id'],'quantity':3}]})
   two=await request(c,'POST','/suppliers/1/purchase-order',json={'request_key':'two-lines','pricing_version':v['version'],'items':[{'product_id':p['id'],'quote_id':q['id'],'quantity':2,'reason':'保留独立行'},{'product_id':p['id'],'quote_id':q['id'],'quantity':3,'reason':'保留独立行'}]})
   assert two['order']['items'][0]['line_id']!=two['order']['items'][1]['line_id']
   old=await request(c,'GET','/supplier-quotes/suppliers/1');qbody=next(x for x in old['data'] if x['id']==q['id'])
   info=await request(c,'GET',f'/sku-catalog/products/{p["id"]}/candidates')
   q=await request(c,'PUT',f'/supplier-quotes/{q["id"]}',json={'request_key':'price12','code':q['code'],'expected_quote_version':q['version'],'expected_product_version':info['product_version'],'expected_sku_version':s['version'],**{k:qbody['terms'][k] for k in ['currency','base_unit_factor','conversion_basis','valid_from','valid_to','fees','quality_tags','lead_days','active']},'unit':'个','tiers':[{'min_quantity':'1','max_quantity':None,'unit_price':'12'}]})
   costly=await buy(c,p,q,uid=4)
   report=await request(c,'GET','/supplier-price-report',params={'month':'2026-10'});assert report['total_lines']==4
   g=report['groups'][0];assert g['historical']['positive']=='25.00' and g['historical']['negative']=='-3.50' and g['historical']['net']=='21.50'
   assert g['lowest']['net']=='20.00'
   only=await request(c,'GET','/supplier-price-report',params={'month':'2026-10','orderer_id':4});assert only['total_lines']==1 and only['data'][0]['historical_difference']=='-3.50'
   assert (await request(c,'GET','/supplier-price-report',params={'month':'2026-10','supplier_id':3}))['total_lines']==0
   n=await request(c,'GET','/supplier-price-report',params={'month':'2026-10','view':'non_lowest'});assert n['total_lines']==4
   actual('negative_quantity_filters',report)
 asyncio.run(run())

def test_thai_half_open_month_current_status_and_actual_bill_void(tmp_path,monkeypatch):
 async def run():
  async with fixture(tmp_path,monkeypatch) as (_,f,c,_):
   po,*_=await scenario(c,f)
   dates=[datetime(2026,9,30,16,59,59,tzinfo=timezone.utc),datetime(2026,9,30,17,tzinfo=timezone.utc),datetime(2026,10,31,16,59,59,tzinfo=timezone.utc),datetime(2026,10,31,17,tzinfo=timezone.utc)]
   boundary=[await clone(f,po,at=x) for x in dates]
   for state,flow in [('pending','completed'),('rejected','completed'),('cancelled','completed'),('confirmed','cancelled')]:await clone(f,po,status=state,flow=flow)
   await clone(f,po,warehouse=2,supplier=2,creator=7)
   report=await request(c,'GET','/supplier-price-report',params={'month':'2026-10'});assert report['total_lines']==7 and report['coverage']['denominator']==3 and report['coverage']['state_excluded']==4
   assert report['groups'][0]['historical']['net']=='60.00' and report['groups'][0]['lowest']['net']=='30.00'
   ids={r['order_id'] for r in report['data']};assert boundary[0][0] not in ids and boundary[1][0] in ids and boundary[2][0] in ids and boundary[3][0] not in ids
   await request(c,'PUT',f'/payable/{po["payable_bill_id"]}/void',params={'void_reason':'合成作废核验'})
   after=await request(c,'GET','/supplier-price-report',params={'month':'2026-10'});assert after['coverage']['state_excluded']==5 and after['groups'][0]['historical']['net']=='40.00'
   row=next(r for r in after['data'] if r['order_id']==po['order']['id']);assert row['historical_difference'] is None and '作废' in row['state_exclusion']
   actual('thai_dates_status_void',{'before':report,'after':after})
 asyncio.run(run())

def test_currencies_fees_unknown_legacy_and_old_missing_line_are_separate(tmp_path,monkeypatch):
 async def run():
  async with fixture(tmp_path,monkeypatch) as (_,f,c,_):
   po,s,p,q,*_=await scenario(c,f)
   cny=await product(c,product_name='人民币同SKU',currency='CNY',unit_price=3);await map_it(c,cny['id'],s)
   cq,_=await quoted(c,cny['id'],s,currency='CNY',tiers=[{'min_quantity':'1','max_quantity':None,'unit_price':'3'}]);await buy(c,cny,cq,2)
   fee=await product(c,product_name='不同税费同SKU',unit_price=6);await map_it(c,fee['id'],s)
   fq,_=await quoted(c,fee['id'],s,fees={**FEES,'tax_mode':'excluded','tax_rate':'7'},tiers=[{'min_quantity':'1','max_quantity':None,'unit_price':'6'}]);await buy(c,fee,fq)
   unknown=await product(c,product_name='箱数未知',unit='箱',unit_price=4);await map_it(c,unknown['id'],s)
   uq,_=await quoted(c,unknown['id'],s,unit='箱',base_unit_factor=None,tiers=[{'min_quantity':'1','max_quantity':None,'unit_price':'4'}]);await buy(c,unknown,uq)
   unknownfee=await product(c,product_name='费用未知',unit_price=2);await map_it(c,unknownfee['id'],s)
   uf,_=await quoted(c,unknownfee['id'],s,fees={'tax_mode':'unknown','freight_mode':'unknown'},tiers=[{'min_quantity':'1','max_quantity':None,'unit_price':'2'}]);await buy(c,unknownfee,uf)
   legacy=await product(c,product_name='旧未映射',unit_price=5);await request(c,'POST','/suppliers/1/purchase-order',json={'items':[{'product_id':legacy['id'],'quantity':1}]})
   async with f() as db:
    db.add(PurchaseOrder(warehouse_id=1,supplier_id=1,order_number='OLD-WITHOUT-LINE-ID',total_amount=5,currency='THB',status='confirmed',created_at=datetime(2026,10,2,tzinfo=timezone.utc),items=[{'product_name':'旧记录','quantity':1,'unit_price':5,'pricing_snapshot':[]}]))
    await db.commit()
   report=await request(c,'GET','/supplier-price-report',params={'month':'2026-10'});assert report['total_lines']==7 and len(report['groups'])==3
   assert {g['group']['currency'] for g in report['groups']}=={'THB','CNY'}
   assert report['coverage']['historical_calculable']==1 and report['coverage']['lowest_calculable']==3
   missing=[r for r in report['data'] if r['group_key'] is None];assert len(missing)==4 and all(r['historical_difference'] is None and r['lowest_difference'] is None for r in missing)
   filtered=await request(c,'GET','/supplier-price-report',params={'month':'2026-10','currency':'CNY'});assert filtered['total_lines']==1 and filtered['groups'][0]['historical']['count']==0 and filtered['data'][0]['historical_difference'] is None
   actual('currency_terms_unknown',report)
 asyncio.run(run())

def test_pagination_full_export_exact_line_over200_and_formula_injection(tmp_path,monkeypatch):
 async def run():
  async with fixture(tmp_path,monkeypatch) as (_,f,c,_):
   po,*_=await scenario(c,f)
   for i in range(205):
    items=copy.deepcopy(po['order']['items']);items[0]['product_name']='=SUM(A1:A2)';items[0]['reason']='\t=2+2';items[0]['pricing_snapshot']['selection_reason']='\t=2+2'
    last,lines=await clone(f,po,items=items)
   report=await request(c,'GET','/supplier-price-report',params={'month':'2026-10','page':3,'page_size':100});assert report['total_lines']==206 and len(report['data'])==6
   assert report['groups'][0]['historical']['net']=='4120.00' and report['groups'][0]['lowest']['net']=='2060.00'
   detail=await request(c,'GET',f'/supplier-price-report/orders/{last}/lines/{lines[0]["line_id"]}');assert detail['data']['order_id']==last
   download=await c.get('/api/v1/supplier-price-report/export?month=2026-10',headers=auth(1));assert download.status_code==200
   rows=list(csv.reader(io.StringIO(download.content.decode('utf-8-sig'))));assert len(rows)==207
   assert sum(Decimal(r[20]) for r in rows[1:])==Decimal('4120') and sum(Decimal(r[22]) for r in rows[1:])==Decimal('2060')
   assert all(r[10].startswith("'=") and r[23].startswith("'\t=") for r in rows[1:] if r[1]!=str(po['order']['id']))
   assert len({(r[1],r[3]) for r in rows[1:]})==206
   actual('pagination_export',{'summary':report['groups'],'rows':len(rows)-1,'last_detail':detail,'formula_escaped':True})
 asyncio.run(run())

def test_all_tied_candidates_and_per_line_cent_rounding(tmp_path,monkeypatch):
 async def run():
  async with fixture(tmp_path,monkeypatch) as (_,f,c,_):
   po,s,p,q,low,lb,_=await scenario(c,f)
   tie,_=await quoted(c,low['product_id'],s,**{k:v for k,v in lb.items() if k not in ('request_key','code','expected_product_version','expected_sku_version')},code='TIED-7')
   data=await request(c,'GET','/supplier-quotes/suppliers/1');info=await request(c,'GET',f'/sku-catalog/products/{p["id"]}/candidates')
   q=await request(c,'PUT',f'/supplier-quotes/{q["id"]}',json={'request_key':'rounded','code':q['code'],'expected_quote_version':q['version'],'expected_product_version':info['product_version'],'expected_sku_version':s['version'],**{k:q['terms'][k] for k in ['currency','base_unit_factor','conversion_basis','valid_from','valid_to','fees','quality_tags','lead_days','active']},'unit':'个','tiers':[{'min_quantity':'1','max_quantity':None,'unit_price':'8.005'}]})
   v=await request(c,'POST','/supplier-quotes/purchase-preview',json={'supplier_id':1,'items':[{'product_id':p['id'],'quote_id':q['id'],'quantity':1},{'product_id':p['id'],'quote_id':q['id'],'quantity':1}]})
   new=await request(c,'POST','/suppliers/1/purchase-order',json={'request_key':'rounding-two','pricing_version':v['version'],'items':[{'product_id':p['id'],'quote_id':q['id'],'quantity':1,'reason':'逐行核对'},{'product_id':p['id'],'quote_id':q['id'],'quantity':1,'reason':'逐行核对'}]})
   report=await request(c,'GET','/supplier-price-report',params={'month':'2026-10'});rows=[r for r in report['data'] if r['order_id']==new['order']['id']]
   assert len(rows)==2 and all(r['historical_difference']=='1.00' and r['lowest_difference']=='1.01' for r in rows)
   assert all({x['id'] for x in r['lowest_candidates']}=={low['id'],tie['id']} for r in rows)
   assert report['groups'][0]['historical']['net']=='22.00' and report['groups'][0]['lowest']['net']=='12.02'
   actual('ties_round_each_line',report)
 asyncio.run(run())

@pytest.mark.parametrize('breakage',['foreign_quote','missing_factor','unknown_fee','bad_lowest','bad_history','duplicate_line_id','missing_mapping'])
def test_unreliable_frozen_evidence_is_not_zero_or_strict_savings(tmp_path,monkeypatch,breakage):
 async def run():
  async with fixture(tmp_path,monkeypatch) as (_,f,c,_):
   po,*_=await scenario(c,f)
   async with f() as db:
    row=await db.get(PurchaseOrder,po['order']['id']);items=copy.deepcopy(row.items);snap=items[0]['pricing_snapshot']
    if breakage=='foreign_quote':snap['selected_quote']['warehouse_id']=2
    if breakage=='missing_mapping':snap['selected_quote']['product_binding']['sku_mapping']=None
    if breakage=='missing_factor':snap['selected_quote']['terms']['base_unit_factor']=None
    if breakage=='unknown_fee':snap['selected_quote']['terms']['fees']['tax_mode']='unknown'
    if breakage=='bad_lowest':snap['lowest_comparable_price']='999'
    if breakage=='bad_history':snap['historical_price_review']['average_normalized_price']='999'
    if breakage=='duplicate_line_id':items.append(copy.deepcopy(items[0]))
    row.items=items;await db.commit()
   report=await request(c,'GET','/supplier-price-report',params={'month':'2026-10'});r=report['data'][0]
   if breakage=='bad_lowest':assert r['lowest_difference'] is None and r['historical_difference']=='20.00'
   elif breakage=='bad_history':assert r['historical_difference'] is None and r['lowest_difference']=='10.00'
   else:assert r['lowest_difference'] is None and r['historical_difference'] is None
   if breakage=='duplicate_line_id':
    assert report['coverage']['state_excluded']==2
    await request(c,'GET',f'/supplier-price-report/orders/{row.id}/lines/{items[0]["line_id"]}',code=409)
   actual('unreliable_'+breakage,report)
 asyncio.run(run())

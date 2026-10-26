"""Actual HTTP: historical warning is distinct from current lowest and frozen on creation."""
import asyncio,json,uuid,copy,os
from pathlib import Path
from sqlalchemy import select,func
from app.models import PurchaseOrder,ProcurementPriceHistory,ProcurementPriceAnomaly,PayableBill,SystemSetting
from tests.test_supplier_quotes_round6 import fixture,quoted,preview,FEES
from tests.test_supplier_sku_round5 import sku,product,map_it
from tests.test_supplier_workflow_round1 import request
import pytest
from tests.test_incoming_operations import URL
pytestmark=pytest.mark.skipif(not URL,reason='Disposable localhost required')
ACTUAL={}
def actual(k,v):
 ACTUAL[k]=v
 if os.environ.get('SUPPLIER06_FIX02_REPORT'):Path(os.environ['SUPPLIER06_FIX02_REPORT']).write_text(json.dumps(ACTUAL,ensure_ascii=False,default=str,indent=2))
async def base(c):
 s=await sku(c);p=await product(c,unit_price=100);await map_it(c,p['id'],s);q,b=await quoted(c,p['id'],s,tiers=[{'min_quantity':'1','max_quantity':None,'unit_price':'100'}]);v=await preview(c,p['id'],q['id'],1)
 old=await request(c,'POST','/suppliers/1/purchase-order',json={'request_key':'history-100','pricing_version':v['version'],'items':[{'product_id':p['id'],'quote_id':q['id'],'quantity':1}]})
 return s,p,q,b,old
async def change(c,p,q,b,price,**extra):
 q=await request(c,'PUT',f'/supplier-quotes/{q["id"]}',json={**b,'request_key':uuid.uuid4().hex,'expected_quote_version':q['version'],'tiers':[{'min_quantity':'1','max_quantity':None,'unit_price':str(price)}],**extra})
 v=await preview(c,p['id'],q['id'],1)
 return q,{'request_key':uuid.uuid4().hex,'pricing_version':v['version'],'items':[{'product_id':p['id'],'quote_id':q['id'],'quantity':1}]}

def test_warning_confirm_freezes_threshold_and_history_through_approval_and_replay(tmp_path,monkeypatch):
 async def run():
  async with fixture(tmp_path,monkeypatch) as (_,f,c,_receipt):
   s,p,q,b,old=await base(c);await request(c,'PUT','/suppliers/price-threshold',json={'threshold':10})
   q,body=await change(c,p,q,b,140)
   warning=await request(c,'POST','/suppliers/1/purchase-order',json=body)
   assert warning['need_confirm'] and len(warning['anomalies'])==1
   a=warning['anomalies'][0];assert a['historical_avg']==100 and a['exceed_percent']==40 and a['threshold']=='10.0' and warning['threshold']==10 and a['historical_avg_exact']=='100'
   async with f() as db:
    assert (await db.execute(select(func.count(PurchaseOrder.id)))).scalar_one()==2
    assert (await db.execute(select(func.count(ProcurementPriceAnomaly.id)))).scalar_one()==0
    db.add(SystemSetting(warehouse_id=1,key='purchase_approval_threshold',value='1'))
    history=(await db.execute(select(ProcurementPriceHistory))).scalar_one();snap=copy.deepcopy(history.pricing_snapshot);snap['unit_price']='700'
    db.add(ProcurementPriceHistory(warehouse_id=1,supplier_id=1,product_name='后来历史',unit_price=700,quantity=2,currency='THB',unit='个',pricing_snapshot=snap));await db.commit()
   await request(c,'PUT','/suppliers/price-threshold',json={'threshold':99})
   confirmed={**body,'confirm_price_anomaly':True,'price_review_token':warning['price_review_token']}
   po=await request(c,'POST','/suppliers/1/purchase-order',json=confirmed);assert po['pending']
   frozen=po['order']['items'][0]['pricing_snapshot']['historical_price_review'];assert frozen['historical_avg']=='100' and frozen['threshold']=='10.0' and frozen['confirmed']
   q,_=await change(c,p,q,b,1)
   await request(c,'PUT',f'/suppliers/purchase-approvals/{po["order"]["id"]}/approve')
   replay=await request(c,'POST','/suppliers/1/purchase-order',json=confirmed);assert replay['replayed'] and replay['order']['id']==po['order']['id']
   async with f() as db:
    rows=(await db.execute(select(ProcurementPriceAnomaly))).scalars().all();assert len(rows)==1 and rows[0].purchase_price==140 and rows[0].historical_avg==100 and rows[0].exceed_percent==40
    assert (await db.execute(select(func.count(PayableBill.id)).where(PayableBill.purchase_order_id==po['order']['id']))).scalar_one()==1
    assert (await db.get(PurchaseOrder,po['order']['id'])).items[0]['pricing_snapshot']['historical_price_review']==frozen
   actual('warn_confirm_approve_replay',{'warning':warning,'pending':po,'replay':replay,'one_anomaly':True,'one_ap':True})
 asyncio.run(run())

@pytest.mark.parametrize('patch',[{'currency':'CNY'},{'unit':'箱'},{'fees':{**FEES,'tax_mode':'excluded','tax_rate':'7'}},{'unknown':True}])
def test_incomparable_or_unknown_history_never_mixed(tmp_path,monkeypatch,patch):
 async def run():
  async with fixture(tmp_path,monkeypatch) as (_,f,c,_receipt):
   s,p,q,b,old=await base(c)
   async with f() as db:
    h=(await db.execute(select(ProcurementPriceHistory))).scalar_one();snap=copy.deepcopy(h.pricing_snapshot)
    if patch.get('currency'):h.currency='CNY';snap['selected_quote']['terms']['currency']='CNY'
    if patch.get('unit'):h.unit='箱';snap['unit']='箱';snap['selected_quote']['terms']['base_unit']='box'
    if patch.get('fees'):snap['selected_quote']['terms']['fees']=patch['fees']
    h.pricing_snapshot=None if patch.get('unknown') else snap;await db.commit()
   q,body=await change(c,p,q,b,140);po=await request(c,'POST','/suppliers/1/purchase-order',json=body)
   assert po['order']['id'] and po['anomalies']==[]
   r=po['order']['items'][0]['pricing_snapshot']['historical_price_review'];assert r['historical_avg'] is None and not r['available'] and not r['is_anomaly']
   actual('excluded_'+str(patch),r)
 asyncio.run(run())

def test_below_threshold_legacy_reference_and_signed_binding(tmp_path,monkeypatch):
 async def run():
  async with fixture(tmp_path,monkeypatch) as (_,f,c,_receipt):
   s,p,q,b,old=await base(c);await request(c,'PUT','/suppliers/price-threshold',json={'threshold':10})
   q,body=await change(c,p,q,b,105);po=await request(c,'POST','/suppliers/1/purchase-order',json=body);assert po['anomalies']==[]
   q,body=await change(c,p,q,b,140);w=await request(c,'POST','/suppliers/1/purchase-order',json=body);assert w['need_confirm']
   await request(c,'POST','/suppliers/1/purchase-order',code=409,json={**body,'request_key':'different','confirm_price_anomaly':True,'price_review_token':w['price_review_token']})
   rejected=await request(c,'POST','/suppliers/1/purchase-order',code=409,json={**body,'confirm_price_anomaly':True,'price_review_token':w['price_review_token']+'tampered'})
   assert rejected['detail']['code']=='quote_preview_changed' and rejected['detail']['not_created'] and rejected['detail']['request_key']==body['request_key']
   async with f() as db:db.add(ProcurementPriceHistory(warehouse_id=1,supplier_id=1,product_name='旧产品',spec='旧规格',unit_price=100,quantity=10,currency='THB',unit='个'));await db.commit()
   legacy=await product(c,product_name='旧产品',spec='旧规格',unit_price=140)
   request_body={'request_key':'legacy-warning','items':[{'product_id':legacy['id'],'quantity':1}]}
   w=await request(c,'POST','/suppliers/1/purchase-order',json=request_body);assert w['need_confirm'] and w['anomalies'][0]['basis']=='legacy_name_spec_unit_reference' and '旧口径参考' in w['anomalies'][0]['note']
   saved=await request(c,'POST','/suppliers/1/purchase-order',json={**request_body,'confirm_price_anomaly':True,'price_review_token':w['price_review_token']});assert saved['order']['id']
   assert saved['order']['items'][0]['pricing_snapshot']['lowest_comparable_price'] is None
   actual('threshold_legacy_binding',{'below_threshold':po,'legacy':saved,'wrong_key_or_tampered':409})
 asyncio.run(run())

def test_confirmed_unit_conversion_normalizes_history_and_keeps_original_unit_display(tmp_path,monkeypatch):
 async def run():
  async with fixture(tmp_path,monkeypatch) as (_,f,c,_receipt):
   s,p,q,b,old=await base(c)
   box=await product(c,product_name='同SKU整箱',unit='箱',unit_price=1400);await map_it(c,box['id'],s,base_unit_factor='10')
   q,b=await quoted(c,box['id'],s,unit='箱',base_unit_factor='10',conversion_basis='合成规格证实每箱10个',tiers=[{'min_quantity':'1','max_quantity':None,'unit_price':'1400'}])
   v=await preview(c,box['id'],q['id'],1);w=await request(c,'POST','/suppliers/1/purchase-order',json={'request_key':'box-review','pricing_version':v['version'],'items':[{'product_id':box['id'],'quote_id':q['id'],'quantity':1,'reason':'整箱交付'}]})
   assert w['need_confirm'];r=w['anomalies'][0]
   assert r['factor']=='10' and r['average_normalized_price']=='100' and r['historical_avg']==1000 and r['unit_price']==1400 and r['exceed_percent']==40 and r['original_unit']=='箱'
   actual('unit_conversion',r)
 asyncio.run(run())

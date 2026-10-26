"""Synthetic localhost only: owner risks and audit writes; no production targets."""
import asyncio,copy,csv,io,json,os
from datetime import datetime,timezone
from decimal import Decimal
from pathlib import Path
import pytest
from sqlalchemy import select,func,event
from app.models import PurchaseOrder,PayableBill,PayablePayment,PurchaseReceiptEvent,AuditLog,Supplier,User,SystemSetting,ProcurementPriceHistory,ProcurementPriceAnomaly,ExpenseRecord
from tests.test_procurement_month_round7 import fixture,scenario,clone,buy,product,map_it,quoted,request
from tests.test_round2_permissions import auth,png
from tests.test_incoming_operations import URL
pytestmark=pytest.mark.skipif(not URL,reason='Explicit disposable localhost required')
ACTUAL={}
def actual(k,v):
 ACTUAL[k]=v
 if os.environ.get('SUPPLIER08_REPORT'):Path(os.environ['SUPPLIER08_REPORT']).write_text(json.dumps(ACTUAL,ensure_ascii=False,default=str,indent=2))
async def board(c,**kw):return await request(c,'GET','/supplier-risk',params={'month':'2026-10','page_size':100,**kw})
async def setting(f,key,value):
 async with f() as db:
  r=(await db.execute(select(SystemSetting).where(SystemSetting.warehouse_id==1,SystemSetting.key==key))).scalar_one_or_none()
  if r:r.value=str(value)
  else:db.add(SystemSetting(warehouse_id=1,key=key,value=str(value)))
  await db.commit()
async def order(f,po,*,at=None,amount=80,person=1,supplier=1,currency='THB',status='confirmed',flow='completed',remark=None):
 pid,_=await clone(f,po,at=at,status=status,flow=flow,creator=person,supplier=supplier)
 async with f() as db:
  p=await db.get(PurchaseOrder,pid);p.total_amount=amount;p.currency=currency;p.remark=remark;await db.commit()
 return pid
async def counts(f):
 async with f() as db:return {m.__tablename__:(await db.execute(select(func.count()).select_from(m))).scalar_one() for m in [PurchaseOrder,PayableBill,PayablePayment,PurchaseReceiptEvent,ProcurementPriceHistory,ProcurementPriceAnomaly,ExpenseRecord]}

def test_frozen_strict_unknown_reasons_and_audit_only_writes(tmp_path,monkeypatch):
 async def run():
  async with fixture(tmp_path,monkeypatch) as (engine,f,c,_):
   po,s,p,q,low,lb,_=await scenario(c,f)
   legacy=await product(c,product_name='旧未映射',unit_price=5);await request(c,'POST','/suppliers/1/purchase-order',json={'items':[{'product_id':legacy['id'],'quantity':1}]})
   unknown=await product(c,product_name='费用未知',unit_price=2);await map_it(c,unknown['id'],s);uq,_=await quoted(c,unknown['id'],s,fees={'tax_mode':'unknown','freight_mode':'unknown'},tiers=[{'min_quantity':'1','max_quantity':None,'unit_price':'2'}]);await buy(c,unknown,uq)
   before=await counts(f);writes=[]
   def trace(conn,cursor,statement,*a):
    if statement.lstrip().upper().startswith(('INSERT','UPDATE','DELETE')):writes.append(statement)
   event.listen(engine.sync_engine,'before_cursor_execute',trace)
   try:
    r=await board(c);row=next(x for x in r['data'] if x['rule']=='non_lowest' and x['evidence'][0]['order_id']==po['order']['id']);assert row['state']=='attention' and row['detail']['price']['lowest_difference']=='10.00' and row['detail']['price']['historical_difference']=='20.00'
    assert '交期更合适' in row['detail']['price']['reason'] and row['detail']['price']['selected_quote']['terms']['lead_days']==2
    assert r['summary']['historical_price']['known']==1 and r['summary']['historical_price']['unavailable']==2 and r['summary']['historical_price']['attention']==0
    d=await request(c,'GET',f'/supplier-risk/signals/{row["id"]}',params={'month':'2026-10'});assert d['data']==row
    e=await c.get('/api/v1/supplier-risk/export?month=2026-10',headers=auth(1));assert e.status_code==200
   finally:event.remove(engine.sync_engine,'before_cursor_execute',trace)
   assert writes and all('INSERT INTO audit_logs' in s for s in writes),writes
   assert await counts(f)==before
   async with f() as db:
    logs=(await db.execute(select(AuditLog).where(AuditLog.module=='procurement_risk'))).scalars().all();assert {x.action_type for x in logs}=={'view','view_detail','export'} and len(logs)==3
    assert all(x.user_id==1 and x.warehouse_id==1 and x.detail['rule_version']==r['version'] and x.detail['at'] and 'token' not in json.dumps(x.detail).lower() and 'snapshot' not in json.dumps(x.detail).lower() for x in logs)
   await request(c,'PUT',f'/supplier-quotes/{low["id"]}',json={**lb,'request_key':'later-risk','expected_quote_version':low['version'],'tiers':[{'min_quantity':'1','max_quantity':None,'unit_price':'1'}]})
   assert (await board(c))['data']==r['data']
   actual('frozen_audit_readonly',{'report':r,'counts_before':before,'counts_after':await counts(f),'audits':[x.action_type for x in logs],'write_tables':['audit_logs']})
 asyncio.run(run())

def test_roles_even_hand_granted_scope_and_no_success_audit(tmp_path,monkeypatch):
 async def run():
  async with fixture(tmp_path,monkeypatch) as (_,f,c,_):
   await scenario(c,f);r=await board(c);sid=r['data'][0]['id']
   async with f() as db:
    for uid in (2,3,4,5):(await db.get(User,uid)).extra_permissions=['供应商管理','采购风险看板','采购分析']
    await db.commit()
   denied=[]
   for uid in (2,3,4,5):
    for tail in ('','/export',f'/signals/{sid}'):denied.append({'uid':uid,'path':tail,'response':await request(c,'GET','/supplier-risk'+tail,uid=uid,params={'month':'2026-10'},code=403)})
   async with f() as db:assert (await db.execute(select(func.count()).select_from(AuditLog).where(AuditLog.module=='procurement_risk'))).scalar_one()==1
   await request(c,'GET',f'/supplier-risk/signals/{sid}',uid=7,warehouse='2',params={'month':'2026-10'},code=404)
   assert (await request(c,'GET','/supplier-risk',uid=1,warehouse='2',params={'month':'2026-10'}))['orders']['included']==0
   for tail in ('','/export',f'/signals/{sid}'):await request(c,'GET','/supplier-risk'+tail,params={'month':'2026-10','supplier_id':2},code=404)
   await request(c,'GET','/supplier-risk',warehouse='all',code=400);actual('permissions',denied)
 asyncio.run(run())

def test_concentration_boundary_denominator_currency_status_empty_invalid(tmp_path,monkeypatch):
 async def run():
  async with fixture(tmp_path,monkeypatch) as (_,f,c,_):
   po,*_=await scenario(c,f)
   async with f() as db:(await db.get(PurchaseOrder,po['order']['id'])).status='rejected';await db.commit()
   await order(f,po,amount=700);await order(f,po,amount=300,supplier=3);await order(f,po,amount=200,currency='CNY');await order(f,po,amount=9999,status='pending');await order(f,po,amount=9999,flow='cancelled')
   await setting(f,'supplier_concentration_threshold',70);r=await board(c,rule='concentration');x=next(x for x in r['data'] if x['detail']['currency']=='THB' and x['detail']['supplier_id']==1)
   assert x['detail']['percent']=='70.00' and x['state']=='normal' and x['denominator']['amount']=='1000.00';assert r['orders']['totals_by_currency']=={'THB':'1000.00','CNY':'200.00'} and len(r['data'])==3
   await setting(f,'supplier_concentration_threshold','69.99');after=await board(c,rule='concentration');assert next(v for v in after['data'] if v['id']==x['id'])['state']=='attention'
   empty=await board(c,month='2001-01');assert empty['total']==0 and empty['orders']['included']==0 and all(v['percent'] is None for v in empty['summary'].values())
   await setting(f,'supplier_concentration_threshold','NaN');invalid=await board(c,rule='concentration');assert all(v['state']=='unavailable' for v in invalid['data'])
   actual('concentration',{'boundary':r,'above':after,'empty':empty,'invalid':invalid})
 asyncio.run(run())

def test_split_cross_month_minimal_crossing_dedup_and_isolation(tmp_path,monkeypatch):
 async def run():
  async with fixture(tmp_path,monkeypatch) as (_,f,c,_):
   po,*_=await scenario(c,f);await setting(f,'purchase_approval_threshold',1000)
   a=await order(f,po,amount=600,at=datetime(2026,9,30,16,50,tzinfo=timezone.utc),remark='合理急单，交期要求');b=await order(f,po,amount=400,at=datetime(2026,9,30,17,10,tzinfo=timezone.utc))
   for kw in ({'person':4},{'supplier':3},{'currency':'CNY'}):await order(f,po,amount=600,at=datetime(2026,9,30,17,15,tzinfo=timezone.utc),**kw)
   await order(f,po,amount=500,at=datetime(2026,10,2,18,tzinfo=timezone.utc));r=await board(c,rule='split_window');xs=[v for v in r['data'] if v['state']=='attention'];assert len(xs)==1
   x=xs[0];assert {e['order_id'] for e in x['evidence']}=={a,b} and x['detail']['amount']=='1000.00' and x['detail']['crossing_at'].startswith('2026-10-01') and '合理急单' in x['evidence'][0]['remark']
   assert any(v['state']=='unavailable' and v['detail']['currency']=='CNY' for v in r['data'])
   assert (await board(c,rule='split_window'))['data']==r['data'];prev=await board(c,month='2026-09',rule='split_window');assert not any(v['state']=='attention' for v in prev['data']);actual('split',{'report':r,'previous_month':prev,'members':[a,b]})
 asyncio.run(run())

def test_actual_receipt_events_self_other_80_20_retry_voided_and_legacy(tmp_path,monkeypatch):
 async def run():
  async with fixture(tmp_path,monkeypatch) as (_,f,c,_):
   _,s,p,q,*_=await scenario(c,f);po=await buy(c,p,q,100);oid=po['order']['id'];lid=po['order']['items'][0]['line_id']
   async def receive(key,qty,uid=1):return await request(c,'POST',f'/suppliers/purchase-orders/{oid}/receive',uid=uid,data={'request_key':key,'items':json.dumps([{'line_id':lid,'received_quantity':qty}])},files={'file':('proof.png',png(),'image/png')})
   def mine(r,rule):return [x for x in r['data'] if x['rule']==rule and x['evidence'][0]['order_id']==oid]
   first=await receive('r08-80',80);again=await receive('r08-80',80);assert first['receipt_event_id']==again['receipt_event_id'];short=mine(await board(c),'receipt_quantity')[0];assert short['state']=='info' and short['detail']['quantity']['received_quantity']==80 and '分批' in short['explanation']
   second=await receive('r08-20',20,4);r=await board(c);self_other=mine(r,'self_receipt');assert len(self_other)==2 and {x['state'] for x in self_other}=={'normal','attention'};matched=mine(r,'receipt_quantity')[0];assert matched['state']=='normal' and matched['detail']['quantity']['received_quantity']==100
   third=await receive('r08-1',1);over=mine(await board(c),'receipt_quantity')[0];assert over['state']=='attention' and over['detail']['quantity']['over_quantity']==1
   async with f() as db:(await db.get(PurchaseReceiptEvent,third['receipt_event_id'])).status='voided';await db.commit()
   final=mine(await board(c),'receipt_quantity')[0];assert final['state']=='normal';actual('receipts',{'first':first,'retry':again,'second':second,'short':short,'self_other':self_other,'matched':matched,'over':over,'voided_event':final})
 asyncio.run(run())

def test_new_supplier_reliable_first_and_missing_dates(tmp_path,monkeypatch):
 async def run():
  async with fixture(tmp_path,monkeypatch) as (_,f,c,_):
   po,*_=await scenario(c,f)
   async with f() as db:(await db.get(Supplier,3)).created_at=datetime(2026,10,1,tzinfo=timezone.utc);await db.commit()
   await order(f,po,supplier=3,at=datetime(2026,10,10,tzinfo=timezone.utc));r=await board(c,rule='new_supplier');assert next(x for x in r['data'] if x['detail']['supplier_id']==3)['state']=='info';assert next(x for x in r['data'] if x['detail']['supplier_id']==1)['state']=='unavailable'
   async with f() as db:(await db.get(Supplier,3)).created_at=None;await db.commit()
   after=await board(c,rule='new_supplier');assert all(x['state']=='unavailable' for x in after['data']);actual('new_supplier',{'before':r,'after':after})
 asyncio.run(run())

def test_full_export_over200_exact_signal_and_formula_safe(tmp_path,monkeypatch):
 async def run():
  async with fixture(tmp_path,monkeypatch) as (_,f,c,_):
   po,*_=await scenario(c,f)
   for i in range(205):await order(f,po,remark='=SUM(A1:A2)')
   r=await board(c,rule='non_lowest',page=3);assert r['total']==206 and len(r['data'])==6;last=r['data'][-1];d=await request(c,'GET',f'/supplier-risk/signals/{last["id"]}',params={'month':'2026-10','rule':'non_lowest'});assert d['data']==last
   e=await c.get('/api/v1/supplier-risk/export?month=2026-10&rule=non_lowest',headers=auth(1));assert e.status_code==200;rows=list(csv.reader(io.StringIO(e.content.decode('utf-8-sig'))));assert len(rows)==207 and len({x[1] for x in rows[1:]})==206
   assert sum(Decimal(x[12]) for x in rows[1:])==4120 and sum(Decimal(x[13]) for x in rows[1:])==2060
   async with f() as db:
    p=await db.get(PurchaseOrder,last['evidence'][0]['order_id']);items=copy.deepcopy(p.items);items[0]['reason']='\t=1+1';p.items=items;await db.commit()
   e=await c.get('/api/v1/supplier-risk/export?month=2026-10&rule=non_lowest',headers=auth(1));cells=list(csv.reader(io.StringIO(e.content.decode('utf-8-sig'))));assert any(x[14].startswith("'\t=") for x in cells[1:]);assert r['summary']['non_lowest']['attention']==206
   actual('export',{'signals':r['total'],'csv_rows':len(rows)-1,'history_sum':'4120.00','lowest_sum':'2060.00','last':d,'formula_safe':True})
 asyncio.run(run())

def test_real_high_price_negative_reference_all_ties_and_bill_void(tmp_path,monkeypatch):
 async def run():
  async with fixture(tmp_path,monkeypatch) as (_,f,c,_):
   po,s,p,q,low,lb,_=await scenario(c,f)
   tie,_=await quoted(c,low['product_id'],s,**{k:v for k,v in lb.items() if k not in ('request_key','code','expected_product_version','expected_sku_version')},code='RISK-TIED-7')
   info=await request(c,'GET',f'/sku-catalog/products/{p["id"]}/candidates')
   q=await request(c,'PUT',f'/supplier-quotes/{q["id"]}',json={'request_key':'risk-high-12','code':q['code'],'expected_quote_version':q['version'],'expected_product_version':info['product_version'],'expected_sku_version':s['version'],**{k:q['terms'][k] for k in ['currency','base_unit_factor','conversion_basis','valid_from','valid_to','fees','quality_tags','lead_days','active']},'unit':'个','tiers':[{'min_quantity':'1','max_quantity':None,'unit_price':'12'}]})
   high=await buy(c,p,q);oid=high['order']['id'];r=await board(c);h=next(x for x in r['data'] if x['rule']=='historical_price' and x['evidence'][0]['order_id']==oid);n=next(x for x in r['data'] if x['rule']=='non_lowest' and x['evidence'][0]['order_id']==oid)
   assert h['state']=='attention' and h['detail']['price']['historical_difference']=='-3.00' and h['detail']['percent']=='33.33'
   assert {x['id'] for x in n['detail']['price']['lowest_candidates']}=={low['id'],tie['id']}
   filtered=await board(c,rule='historical_price',state='attention');assert filtered['orders']['included']==1 and filtered['orders']['totals_by_currency']=={'THB':'12.00'}
   e=await c.get('/api/v1/supplier-risk/export?month=2026-10&rule=historical_price&state=attention',headers=auth(1));rows=list(csv.reader(io.StringIO(e.content.decode('utf-8-sig'))));assert len(rows)==2 and rows[1][12]=='-3.00'
   await request(c,'PUT',f'/payable/{high["payable_bill_id"]}/void',params={'void_reason':'本地风险看板作废验证'})
   after=await board(c);assert not any(e['order_id']==oid for x in after['data'] for e in x['evidence'])
   actual('high_price_ties_void',{'high':h,'non_lowest':n,'filtered':filtered,'csv_signed_negative':rows[1][12],'after_void':after})
 asyncio.run(run())

@pytest.mark.parametrize('damage',['duplicate_line_id','legacy_unknown'])
def test_unreliable_line_identity_is_visible_unavailable_not_missing_or_duplicate_signal(tmp_path,monkeypatch,damage):
 async def run():
  async with fixture(tmp_path,monkeypatch) as (_,f,c,_):
   po,*_=await scenario(c,f);oid=po['order']['id']
   async with f() as db:
    p=await db.get(PurchaseOrder,oid);items=copy.deepcopy(p.items)
    if damage=='duplicate_line_id':items.append(copy.deepcopy(items[0]))
    else:items[0].pop('line_id');p.receipt_baseline=None
    p.items=items;await db.commit()
   r=await board(c);mine=[x for x in r['data'] if any(e['order_id']==oid for e in x['evidence'])]
   assert len({x['id'] for x in mine})==len(mine)
   expected=2 if damage=='duplicate_line_id' else 1
   for rule in ('historical_price','non_lowest','receipt_quantity'):
    group=[x for x in mine if x['rule']==rule];assert len(group)==expected and all(x['state']=='unavailable' for x in group)
   assert all('#purchase-line-' not in e['url'] for x in mine if x['rule']=='receipt_quantity' for e in x['evidence'])
   actual('unreliable_'+damage,{'report':r})
 asyncio.run(run())

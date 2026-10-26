"""Synthetic localhost HTTP/SQL only; no real inventory or money."""
import asyncio,csv,io,json,os,uuid
from pathlib import Path
from contextlib import asynccontextmanager
from datetime import datetime,timedelta
from decimal import Decimal
import pytest
from sqlalchemy import select,event
from app.models import InventoryStocktake,InventoryControl,InventoryMovement,User,PurchaseReceiptEvent
from app.models.payable import MonthlyOrderVolume
from app.services import inventory_analysis as analysis
from app.core.timezone import THAI_TZ,thai_now
from tests.test_inventory_round10 import opening,issue,returned,detail,listing,num,receive
from tests.test_procurement_risk_round8 import fixture as base_fixture,scenario,buy,request,counts
from tests.test_supplier_sku_round5 import sku
from tests.test_round2_permissions import auth
from tests.test_incoming_operations import URL
pytestmark=pytest.mark.skipif(not URL,reason='Own disposable loopback PostgreSQL only')
ACTUAL={}
def actual(name,value):
 ACTUAL[name]=value
 if os.environ.get('SUPPLIER11_REPORT'):Path(os.environ['SUPPLIER11_REPORT']).write_text(json.dumps(ACTUAL,ensure_ascii=False,default=str,indent=2))
@asynccontextmanager
async def fixture(tmp,mp):
 async with base_fixture(tmp,mp)as values:
  async with values[1]()as db:
   for uid in (2,3,4,5):
    u=await db.get(User,uid);u.extra_permissions=list(set(u.extra_permissions or [])|{'耗材库存'})
   await db.commit()
  yield values
async def setup(c):
 s=await sku(c);o,_=await opening(c,s,at=datetime(2026,9,1,tzinfo=THAI_TZ));return s,o['account']
async def submit(c,a,amount='95',uid=4,code=200,**kw):
 b={'request_key':uuid.uuid4().hex,'counted_quantity':amount,'expected_version':a['version'],'count_reason':'按实物逐件盘点，合成验证',**kw}
 return await request(c,'POST',f'/inventory/accounts/{a["id"]}/counts',uid=uid,json=b,code=code),b
async def review(c,r,decision='approve',uid=1,code=200,**kw):
 b={'request_key':uuid.uuid4().hex,'decision':decision,'expected_count_version':r['version'],'review_reason':'老板核查凭据后审核实盘差异，合成验证',**kw}
 return await request(c,'POST',f'/inventory/counts/{r["id"]}/review',uid=uid,json=b,code=code),b
async def controls(c,a,minimum='95',ratio='2',uid=1,code=200,**kw):
 old=await request(c,'GET',f'/inventory/accounts/{a["id"]}/controls',uid=uid)
 b={'request_key':uuid.uuid4().hex,'minimum_quantity':minimum,'receipt_usage_ratio':ratio,'stockpiling_note':'本月备货计划与库存增加需老板核实，不认定回扣','expected_version':old['version'],'change_reason':'老板明确本仓SKU试点提醒参数',**kw}
 return await request(c,'PUT',f'/inventory/accounts/{a["id"]}/controls',uid=uid,json=b,code=code),b
async def report(c,month='2026-10',**kw):return await request(c,'GET','/inventory/analysis',params={'month':month},**kw)

def test_count_no_change_until_owner_review_and_exact_replay(tmp_path,monkeypatch):
 async def run():
  async with fixture(tmp_path,monkeypatch)as(_,f,c,_):
   _,a=await setup(c);before=await counts(f);entry,b=await submit(c,a)
   assert entry['data']['status']=='pending' and entry['account']['available_quantity']=='100'
   assert(await request(c,'POST',f'/inventory/accounts/{a["id"]}/counts',uid=4,json=b))['replayed']
   assert await num(f,InventoryStocktake)==1 and await num(f,InventoryMovement)==1
   done,body=await review(c,entry['data']);assert done['account']['available_quantity']=='95'
   replay=await request(c,'POST',f'/inventory/counts/{entry["data"]["id"]}/review',json=body)
   assert replay['replayed']and await num(f,InventoryMovement)==2
   records=(await detail(c,a['id']))['data'];assert records[0]['quantity']=='-5'and records[0]['kind']=='stocktake_adjustment'and records[1]['quantity']=='100'
   again,_=await review(c,entry['data'],code=409);assert again['detail']['not_executed']and await counts(f)==before
   actual('reviewed_count',{'submitted':entry,'approved':done,'replay':replay,'journal':records,'old_counts':before})
 asyncio.run(run())

def test_concurrent_approvals_and_intervening_issue_require_recount(tmp_path,monkeypatch):
 async def run():
  async with fixture(tmp_path,monkeypatch)as(_,f,c,_):
   _,a=await setup(c);x,_=await submit(c,a,'90');y,_=await submit(c,a,'80')
   bodies=[{'request_key':'approve-race-'+str(i),'decision':'approve','expected_count_version':r['data']['version'],'review_reason':'并发审批合成验证'}for i,r in enumerate((x,y))]
   rs=await asyncio.gather(*[c.post(f'/api/v1/inventory/counts/{r["data"]["id"]}/review',headers=auth(1),json=b)for r,b in zip((x,y),bodies)])
   assert sorted(r.status_code for r in rs)==[200,409]and await num(f,InventoryMovement)==2
   win=next(i for i,r in enumerate(rs)if r.status_code==200);r=(x,y)[win]
   assert(await request(c,'POST',f'/inventory/counts/{r["data"]["id"]}/review',json=bodies[win]))['replayed']
   a=(await detail(c,a['id']))['account'];pending,_=await submit(c,a,'70');out,_=await issue(c,a,'1')
   denied,_=await review(c,pending['data'],code=409);assert denied['detail']['not_executed']
   rejected,_=await review(c,pending['data'],'reject');assert rejected['account']['available_quantity']==out['account']['available_quantity']
   fresh,_=await submit(c,out['account'],'70');done,_=await review(c,fresh['data']);assert done['account']['available_quantity']=='70'
   actual('concurrency',{'race':[{'status':r.status_code,'body':r.json()}for r in rs],'stale':denied,'rejected':rejected,'fresh':done})
 asyncio.run(run())

def test_late_failure_rolls_back_review_adjustment_and_receipt(tmp_path,monkeypatch):
 async def run():
  from app.services import inventory as stock
  async with fixture(tmp_path,monkeypatch)as(_,f,c,_):
   _,a=await setup(c);entry,_=await submit(c,a);original=stock.finish
   async def fail(*args,**kw):raise RuntimeError('injected after adjustment before commit')
   monkeypatch.setattr(stock,'finish',fail)
   with pytest.raises(RuntimeError):await review(c,entry['data'])
   monkeypatch.setattr(stock,'finish',original)
   assert(await detail(c,a['id']))['account']['available_quantity']=='100'and await num(f,InventoryMovement)==1
   rows=await request(c,'GET','/inventory/counts',params={'account_id':a['id']});assert rows['data'][0]['status']=='pending'
   done,_=await review(c,rows['data'][0]);assert done['account']['available_quantity']=='95'
 asyncio.run(run())

def test_bounds_unknown_opening_and_no_direct_reversal_bypass(tmp_path,monkeypatch):
 async def run():
  async with fixture(tmp_path,monkeypatch)as(_,f,c,_):
   _,s,p,q,*_=await scenario(c,f);po=await buy(c,p,q,100);await receive(c,po,80)
   a=(await listing(c))['data'][0];await submit(c,a,'80',code=400)
   o,_=await opening(c,s);a=o['account'];await submit(c,a,'-1',code=400);await submit(c,a,'1.000000001',code=400)
   entry,_=await submit(c,a,'0');await review(c,entry['data'],review_reason=' ',code=400)
   done,_=await review(c,entry['data']);assert done['account']['available_quantity']=='0'
   await request(c,'POST',f'/inventory/movements/{done["movement_id"]}/reverse',json={'request_key':'no-count-bypass','expected_version':done['account']['version'],'reverse_reason':'不能绕过新的盘点审核'},code=400)
 asyncio.run(run())

def test_explicit_thresholds_idempotency_and_low_stock_recovers(tmp_path,monkeypatch):
 async def run():
  async with fixture(tmp_path,monkeypatch)as(_,f,c,_):
   _,a=await setup(c);before=(await report(c))['data'][0];assert before['low_stock_state']=='unavailable'
   setting,b=await controls(c,a);assert(await request(c,'PUT',f'/inventory/accounts/{a["id"]}/controls',json=b))['replayed']and await num(f,InventoryControl)==1
   await request(c,'PUT',f'/inventory/accounts/{a["id"]}/controls',json={**b,'request_key':'stale-setting','minimum_quantity':'5'},code=409)
   await controls(c,a,ratio='1',code=400);await controls(c,a,stockpiling_note='',code=400)
   normal=(await report(c))['data'][0];assert normal['low_stock_state']=='normal'
   out,_=await issue(c,a,'10');low=(await report(c))['data'][0];assert low['closing_quantity']=='90'and low['low_stock_state']=='attention'
   await returned(c,out['movement_id'],out['account'],'10');recovered=(await report(c))['data'][0];assert recovered['closing_quantity']=='100'and recovered['low_stock_state']=='normal'
   actual('low_stock',{'unconfigured':before,'controls':setting,'normal':normal,'after_issue':low,'after_return':recovered})
 asyncio.run(run())

def test_month_boundaries_and_late_opening_not_guessed(tmp_path,monkeypatch):
 async def run():
  async with fixture(tmp_path,monkeypatch)as(_,f,c,_):
   _,s,p,q,*_=await scenario(c,f);await opening(c,s,at=datetime(2026,9,1,tzinfo=THAI_TZ));po=await buy(c,p,q,100);rec=await receive(c,po,80)
   a=(await listing(c))['data'][0];await issue(c,a,'30');await controls(c,a)
   async with f()as db:
    m=(await db.execute(select(InventoryMovement).where(InventoryMovement.kind=='receipt'))).scalar_one();m.occurred_at=datetime(2026,9,20,tzinfo=THAI_TZ)
    e=await db.get(PurchaseReceiptEvent,rec['receipt_event_id']);e.received_at=m.occurred_at;await db.commit()
   sep=(await report(c,'2026-09'))['data'][0];october=(await report(c))['data'][0]
   assert tuple(sep[k]for k in('opening_quantity','received_quantity','net_issued_quantity','closing_quantity'))==('100','80','0','180')
   assert tuple(october[k]for k in('opening_quantity','received_quantity','net_issued_quantity','closing_quantity'))==('180','0','30','150')
   s2=await sku(c,code='LATE-OPENING');await opening(c,s2,'5',at=thai_now()-timedelta(days=1));late=next(r for r in(await report(c))['data']if r['sku_id']==s2['id'])
   assert late['opening_quantity']is None and late['closing_quantity']=='5'and late['usage_state']=='unavailable'
   await report(c,'2099-01',code=400);actual('cross_month',{'september':sep,'october':october,'late':late})
 asyncio.run(run())

def test_denominator_missing_zero_duplicate_and_currencies_not_invented_or_mixed(tmp_path,monkeypatch):
 async def run():
  async with fixture(tmp_path,monkeypatch)as(_,f,c,_):
   _,a=await setup(c);out,_=await issue(c,a,'20');ret,_=await returned(c,out['movement_id'],out['account'],'1')
   missing=await report(c);assert missing['order_volume']['order_count']is None
   async with f()as db:db.add(MonthlyOrderVolume(warehouse_id=1,month='2026-10',order_count=0));await db.commit()
   zero=await report(c);assert zero['order_volume']['order_count']==0 and not zero['order_volume']['available']
   async with f()as db:
    (await db.execute(select(MonthlyOrderVolume))).scalar_one().order_count=100
    db.add(MonthlyOrderVolume(warehouse_id=2,month='2026-10',order_count=999))
    for mid,cur,amount in[(out['movement_id'],'THB',100),(ret['movement_id'],'CNY',200)]:
     m=await db.get(InventoryMovement,mid);m.cost_amount=amount;m.cost_currency=cur
    await db.commit()
   known=await report(c);cost=known['data'][0]['cost'];assert known['order_volume']['order_count']==100 and cost['per_order_by_currency']is None
   assert cost['observed_currencies']==['CNY','THB']and cost['verified_totals_by_currency']is None
   example=analysis.per_order({'THB':Decimal(100),'CNY':Decimal(200)},100);assert example=={'THB':'1.00','CNY':'2.00'}and analysis.per_order({'THB':Decimal(100)},0)is None
   async with f()as db:db.add(MonthlyOrderVolume(warehouse_id=1,month='2026-10',order_count=50));await db.commit()
   duplicate=await report(c);assert duplicate['order_volume']['order_count']is None
   actual('cost_denominator',{'missing':missing['order_volume'],'zero':zero['order_volume'],'known_volume_missing_cost':known,'duplicate':duplicate['order_volume'],'calculator_separate_currency_example':example})
 asyncio.run(run())

def test_owner_risk_csv_and_review_evidence_staleness(tmp_path,monkeypatch):
 async def run():
  async with fixture(tmp_path,monkeypatch)as(_,f,c,_):
   _,s,p,q,*_=await scenario(c,f);await opening(c,s,at=datetime(2026,9,1,tzinfo=THAI_TZ));po=await buy(c,p,q,100);await receive(c,po,80)
   a=(await listing(c))['data'][0];out,_=await issue(c,a,'30');await controls(c,a);before=await counts(f)
   r=await report(c);row=r['data'][0];assert row['closing_quantity']=='150'and row['usage_state']=='attention'
   board=await request(c,'GET','/supplier-risk',params={'month':'2026-10','rule':'inventory_usage'});sig=board['data'][0];assert board['total']==1 and sig['detail']['inventory']==row
   exp=await c.get('/api/v1/inventory/analysis/export?month=2026-10',headers=auth(1));cells=list(csv.reader(io.StringIO(exp.content.decode('utf-8-sig'))));assert len(cells)==2 and cells[1][6:12]==['100','110','80','30','0','150']
   er=await c.get('/api/v1/supplier-risk/export?month=2026-10&rule=inventory_usage',headers=auth(1));rc=list(csv.reader(io.StringIO(er.content.decode('utf-8-sig'))));assert len(rc)==2 and json.loads(rc[1][16])['inventory']['closing_quantity']=='150'
   d=await request(c,'GET',f'/supplier-risk/signals/{sig["id"]}',params={'month':'2026-10'});rv=d['data']['review']
   await request(c,'POST',f'/supplier-risk/signals/{sig["id"]}/reviews',params={'month':'2026-10'},json={'request_key':'stock-risk-cleared','expected_evidence_version':rv['evidence_version'],'expected_latest_review_id':0,'conclusion':'cleared','review_reason':'老板核实本月合理备货，保留依据'})
   await issue(c,out['account'],'1');changed=await request(c,'GET',f'/supplier-risk/signals/{sig["id"]}',params={'month':'2026-10'});assert changed['data']['review']['stale']and changed['data']['review']['history'][0]['conclusion']=='cleared'
   scoped=await request(c,'GET','/supplier-risk',params={'month':'2026-10','supplier_id':1});assert not any(x['rule'].startswith('inventory_')for x in scoped['data'])and'不能按'in scoped['inventory']['message']
   assert await counts(f)==before;actual('risk',{'analysis':r,'board':board,'csv':cells,'risk_csv_rows':len(rc)-1,'stale_review':changed['data']['review']})
 asyncio.run(run())

def test_new_route_roles_office_submission_and_warehouse_isolation(tmp_path,monkeypatch):
 async def run():
  async with fixture(tmp_path,monkeypatch)as(_,f,c,_):
   _,a=await setup(c);entry,_=await submit(c,a);config,_=await controls(c,a)
   routes=[('GET','/inventory/counts',{'params':{'account_id':a['id']}}),('POST',f'/inventory/accounts/{a["id"]}/counts',{'json':{'request_key':'deny','counted_quantity':'1','expected_version':a['version'],'count_reason':'测试'}}),('POST',f'/inventory/counts/{entry["data"]["id"]}/review',{'json':{'request_key':'deny-review','decision':'approve','expected_count_version':entry['data']['version'],'review_reason':'测试'}}),('GET',f'/inventory/accounts/{a["id"]}/controls',{}),('PUT',f'/inventory/accounts/{a["id"]}/controls',{'json':{'request_key':'deny-controls','minimum_quantity':'1','receipt_usage_ratio':None,'stockpiling_note':'','expected_version':config['controls']['version'],'change_reason':'测试'}}),('GET','/inventory/analysis',{}),('GET','/inventory/analysis/export',{})]
   denied=[]
   for uid in(2,5):
    for method,path,options in routes:denied.append({'uid':uid,'method':method,'path':path,'response':await request(c,method,path,uid=uid,code=403,**options)})
   for uid in(3,4):
    await request(c,'GET','/inventory/counts',uid=uid,params={'account_id':a['id']});await review(c,entry['data'],uid=uid,code=403)
    await request(c,'GET','/inventory/analysis',uid=uid,code=403);await request(c,'GET','/inventory/analysis/export',uid=uid,code=403)
    created,_=await submit(c,a,'99',uid=uid);assert created['data']['status']=='pending'
   for method,path,options in routes[:5]:await request(c,method,path,uid=7,warehouse='2',code=403,**options)
   assert(await report(c,uid=7,warehouse='2'))['data']==[]
   async with f()as db:(await db.get(User,4)).extra_permissions=[];await db.commit()
   await request(c,'GET','/inventory/counts',uid=4,params={'account_id':a['id']},code=403)
   actual('roles',{'denied':denied,'office_submit_only':True,'foreign_account_rejected':True})
 asyncio.run(run())

def test_read_only_analysis_and_zero_difference_adjustment_has_trace(tmp_path,monkeypatch):
 async def run():
  async with fixture(tmp_path,monkeypatch)as(engine,f,c,_):
   _,a=await setup(c);entry,_=await submit(c,a,'100');done,_=await review(c,entry['data']);assert done['account']['available_quantity']=='100'and await num(f,InventoryMovement)==2
   journal=(await detail(c,a['id']))['data'];assert journal[0]['quantity']=='0'and journal[0]['kind']=='stocktake_adjustment'
   writes=[]
   def trace(conn,cursor,statement,*args):
    if statement.lstrip().upper().startswith(('INSERT','UPDATE','DELETE')):writes.append(statement)
   event.listen(engine.sync_engine,'before_cursor_execute',trace)
   try:await report(c)
   finally:event.remove(engine.sync_engine,'before_cursor_execute',trace)
   assert writes==[];actual('read_only',{'business_writes':0,'zero_count_trace':journal})
 asyncio.run(run())

def test_cross_month_return_and_reversal_are_signed_not_negative_consumption_risk(tmp_path,monkeypatch):
 async def run():
  from tests.test_inventory_round10 import reverse
  async with fixture(tmp_path,monkeypatch)as(_,f,c,_):
   _,a=await setup(c);out,_=await issue(c,a,'10');await controls(c,a)
   async with f()as db:
    (await db.get(InventoryMovement,out['movement_id'])).occurred_at=datetime(2026,9,25,tzinfo=THAI_TZ);await db.commit()
   ret,_=await returned(c,out['movement_id'],out['account'],'5');sep=(await report(c,'2026-09'))['data'][0];october=(await report(c))['data'][0]
   assert sep['net_issued_quantity']=='10'and sep['closing_quantity']=='90'
   assert october['opening_quantity']=='90'and october['net_issued_quantity']=='-5'and october['closing_quantity']=='95'and october['usage_state']=='info'and october['receipt_usage_ratio']is None
   await reverse(c,ret['movement_id'],ret['account']);after=(await report(c))['data'][0]
   assert after['net_issued_quantity']=='0'and after['closing_quantity']=='90'and(await report(c,'2026-09'))['data'][0]==sep
   actual('cross_month_return',{'september':sep,'october_return':october,'after_return_reversal':after})
 asyncio.run(run())

def test_reminders_keep_each_sku_unit_separate_and_export_escapes_notes(tmp_path,monkeypatch):
 async def run():
  async with fixture(tmp_path,monkeypatch)as(_,f,c,_):
   _,a=await setup(c);box=await sku(c,code='BOX-ONLY',base_unit='box');opened,_=await opening(c,box,'5',at=datetime(2026,9,1,tzinfo=THAI_TZ));b=opened['account']
   await controls(c,a,minimum='95',stockpiling_note='=SUM(A1:A2)');await controls(c,b,minimum='2',ratio=None)
   await issue(c,a,'10');r=await report(c);piece=next(x for x in r['data']if x['account_id']==a['id']);boxed=next(x for x in r['data']if x['account_id']==b['id'])
   assert piece['closing_quantity']=='90'and piece['low_stock_state']=='attention'and boxed['closing_quantity']=='5'and boxed['low_stock_state']=='normal'
   exported=await c.get('/api/v1/inventory/analysis/export?month=2026-10',headers=auth(1));rows=list(csv.reader(io.StringIO(exported.content.decode('utf-8-sig'))));assert len(rows)==3 and any(x[19].startswith("'=SUM")for x in rows[1:])
   assert{(x[5],x[11])for x in rows[1:]}=={('piece','90'),('box','5')}
   actual('separate_unit_and_csv',{'data':r['data'],'csv':rows})
 asyncio.run(run())

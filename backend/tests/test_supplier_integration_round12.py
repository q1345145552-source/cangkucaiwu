"""End-to-end supplier/finance/stock integration on a disposable localhost database."""
import asyncio,copy,json,os,uuid
from pathlib import Path
from contextlib import asynccontextmanager
from datetime import date,datetime
from decimal import Decimal
import pytest
from sqlalchemy import select,func,text
from fastapi import HTTPException
from app.models import (User,PurchaseOrder,PayableBill,PayablePayment,PaymentAccount,InventoryAccount,
 InventoryMovement,InventoryStocktake,ExpenseRecord,CostIdentity,ProcurementActionException,ProcurementDutyExecution,SystemSetting)
from app.models.payable import MonthlyOrderVolume
from app.core.timezone import THAI_TZ
from app.services.account_balances import current_account_balances
from tests.test_inventory_round11 import fixture as round11_fixture,controls as inventory_controls,submit as count_submit,review as count_review,report
from tests.test_inventory_round10 import opening,issue,returned,detail as stock_detail
from tests.test_procurement_controls_round9 import policy,context,grant,controls as duty_fields,receive
from tests.test_supplier_sku_round5 import sku,product,map_it,ATTRS
from tests.test_supplier_quotes_round6 import quoted,preview
from tests.test_procurement_risk_round8 import setting,buy,request
from tests.test_supplier_cost_identity_round4 import invoice,create as register_cost
from tests.test_round2_permissions import auth,png
from tests.test_incoming_operations import URL
pytestmark=pytest.mark.skipif(not URL,reason='Explicit own loopback PostgreSQL only')
ACTUAL={}
def actual(key,value):
 ACTUAL[key]=value
 if os.environ.get('SUPPLIER12_REPORT'):Path(os.environ['SUPPLIER12_REPORT']).write_text(json.dumps(ACTUAL,ensure_ascii=False,indent=2,default=str))
@asynccontextmanager
async def fixture(tmp,mp):
 async with round11_fixture(tmp,mp)as values:
  import app.services.account_balances as balances
  mp.setattr(balances,'thai_today',lambda:date(2026,10,27))
  async with values[1]()as db:
   for uid in(3,4):
    u=await db.get(User,uid);u.extra_permissions=list(set(u.extra_permissions)|{'应付账款','付款计划','运营收支','备用金管理','耗材库存'})
   db.add(MonthlyOrderVolume(warehouse_id=1,month='2026-10',order_count=100,updated_by=1));await db.commit()
  yield values
async def balance(f):
 async with f()as db:
  a=await db.get(PaymentAccount,1);return(await current_account_balances(db,[a]))[a.id]
async def prepare(c,f):
 s=await sku(c);p=await product(c,unit_price=10,product_name='本仓组合验收耗材');await map_it(c,p['id'],s)
 q,qbody=await quoted(c,p['id'],s)
 p2=await request(c,'POST','/suppliers/3/products',json={'product_name':'同规格另一供应商','spec':'PE38','unit_price':9,'unit':'个','currency':'THB','catalog_attributes':ATTRS});await map_it(c,p2['id'],s)
 low,lowbody=await quoted(c,p2['id'],s,tiers=[{'min_quantity':'1','max_quantity':None,'unit_price':'9'}])
 await setting(f,'purchase_approval_threshold','500');await policy(c,True,True)
 opened,_=await opening(c,s,'100',at=datetime(2026,9,1,tzinfo=THAI_TZ))
 po=await buy(c,p,q,100);assert po['pending']and po['order']['total_amount']==1000
 return s,p,q,qbody,low,lowbody,opened,po
async def approve_other(c,po):
 ctx=await context(c,po['order']['id'],'approve')
 blocked=await request(c,'PUT',f'/suppliers/purchase-approvals/{po["order"]["id"]}/approve',json={'request_key':'r12-self-denied',**duty_fields(ctx)},code=403)
 other=await context(c,po['order']['id'],'approve',uid=4)
 approved=await request(c,'PUT',f'/suppliers/purchase-approvals/{po["order"]["id"]}/approve',uid=4,json={'request_key':'r12-other-approved',**duty_fields(other)})
 return approved,blocked
async def receive_once(c,po,qty,key):
 ctx=await context(c,po['order']['id'],'receive');g,_=await grant(c,ctx)
 r=await receive(c,ctx,po,qty,key,g['data']['id']);return r,ctx,g
async def confirm(c,bid):return await request(c,'PUT',f'/payable/{bid}/confirm',json={'reason':'老板核对实收明细和发票，组合合成验收'})
async def pay(c,bid,amount,key,code=200):return await request(c,'PUT',f'/payable/{bid}/pay',code=code,params={'paid_amount':amount,'account_id':1,'payment_method':'现金','request_key':key})

def test_complete_quote_approval_80_plus20_split_payments_stock_risk_count_and_cross_channel(tmp_path,monkeypatch):
 async def run():
  async with fixture(tmp_path,monkeypatch)as(_,f,c,receipt):
   start=await balance(f);assert start==10000
   s,p,q,qbody,low,lowbody,opened,po=await prepare(c,f);approved,blocked=await approve_other(c,po);bid=approved['payable_bill_id']
   identity=invoice(no='R12-FULL-1000');await request(c,'PUT',f'/payable/{bid}',json={'invoice_identity':identity})
   await request(c,'PUT','/suppliers/purchase-match-policy',json={'strict':True})
   r80,ctx,g=await receive_once(c,po,80,'r12-first80');repeat=await receive(c,ctx,po,80,'r12-first80',g['data']['id']);assert repeat['replayed']
   assert r80['inventory']['recorded_lines']==1
   stock=(await request(c,'GET','/inventory'))['data'][0];assert stock['available_quantity']=='180'
   await confirm(c,bid);before=(await request(c,'GET',f'/payable/{bid}/detail'));assert before['matching']['payment_cap']==800
   first=await pay(c,bid,300,'r12-first300');again=await pay(c,bid,300,'r12-first300');assert first['payment_id']==again['payment_id']and await balance(f)==9700
   over=await pay(c,bid,501,'r12-over-cap',code=400);assert'已记录实收金额'in over['detail']
   await register_cost(c,'expense',receipt,identity=identity,amount=1000,code=409)
   # The consumed receipt authorization cannot be reused for a different delivery.
   current=await context(c,po['order']['id'],'receive');await receive(c,current,po,20,'r12-used-grant20',g['data']['id'],code=403)
   r20,_,_=await receive_once(c,po,20,'r12-next20');assert r20['inventory']['recorded_lines']==1
   await pay(c,bid,700,'r12-stale-review',code=400);await confirm(c,bid)
   second=await pay(c,bid,700,'r12-second700');final=await request(c,'GET',f'/payable/{bid}/detail')
   assert(final['amount'],final['paid_amount'],final['remaining_amount'])==(1000,1000,0)
   assert[p['amount']for p in final['payments']]==[700,300]or[p['amount']for p in final['payments']]==[300,700]
   assert await balance(f)==9000
   await pay(c,bid,700,'r12-second700');assert await balance(f)==9000
   # Changing today's cheapest quote must not restate the original purchase evidence.
   await request(c,'PUT',f'/supplier-quotes/{low["id"]}',json={**lowbody,'request_key':'r12-later-cheap','expected_quote_version':low['version'],'tiers':[{'min_quantity':'1','max_quantity':None,'unit_price':'1'}]})
   prices=await request(c,'GET','/supplier-price-report',params={'month':'2026-10'});pr=next(x for x in prices['data']if x['order_id']==po['order']['id']);assert pr['lowest_difference']=='100.00'and pr['historical_difference']is None
   a=(await request(c,'GET','/inventory'))['data'][0];out,_=await issue(c,a,'30');assert out['account']['available_quantity']=='170'
   pending,_=await count_submit(c,out['account'],'165');assert pending['account']['available_quantity']=='170'
   checked,_=await count_review(c,pending['data']);assert checked['account']['available_quantity']=='165'
   await inventory_controls(c,a,minimum='180',ratio='2');ana=await report(c);assert ana['data'][0]['closing_quantity']=='165'and ana['data'][0]['cost']['per_order_by_currency']is None
   risk=await request(c,'GET','/supplier-risk',params={'month':'2026-10','rule':'inventory_usage'});assert risk['data'][0]['detail']['inventory']==ana['data'][0]and risk['data'][0]['evidence'][0]['url']==f'/inventory?account_id={a["id"]}'
   async with f()as db:
    payments=(await db.execute(select(PayablePayment).where(PayablePayment.bill_id==bid))).scalars().all();assert len(payments)==2 and sum(x.amount for x in payments)==1000
    assert(await db.execute(select(func.count()).select_from(ExpenseRecord))).scalar_one()==0
    old=await db.get(PurchaseOrder,1);assert old.total_amount==1000 and old.items==[{'product_name':'耗材','quantity':10}]
    journals=(await db.execute(select(InventoryMovement).order_by(InventoryMovement.id))).scalars().all();assert[x.quantity for x in journals]==list(map(Decimal,['100','80','20','-30','-5']))
   actual('complete_chain',{'purchase':po,'self_denied':blocked,'other_approved':approved,'receipt80':r80,'receipt80_replayed':repeat,'paid300':first,'after300_balance':9700,'cap_blocked':over,'receipt20':r20,'paid700':second,'payable_final':final,'balance_before':start,'balance_after':9000,'quote_frozen':pr,'inventory':ana,'risk':risk,'journals':[{'id':x.id,'quantity':str(x.quantity),'kind':x.kind}for x in journals],'expense_rows':0,'legacy_po_unchanged':True})
 asyncio.run(run())

def test_failed_stock_receipt_preserves_previous_payment_and_unconsumed_exception(tmp_path,monkeypatch):
 async def run():
  from app.services import inventory
  async with fixture(tmp_path,monkeypatch)as(_,f,c,_):
   *_,po=await prepare(c,f);approved,_=await approve_other(c,po);bid=approved['payable_bill_id']
   # Default payment policy remains compatible until explicitly enabled.
   await pay(c,bid,300,'r12-paid-before-receipt');assert await balance(f)==9700
   ctx=await context(c,po['order']['id'],'receive');g,_=await grant(c,ctx);real=inventory.record_receipt
   async def fail(*args,**kw):raise HTTPException(500,'合成库存保存失败，整事务回滚')
   monkeypatch.setattr(inventory,'record_receipt',fail);await receive(c,ctx,po,80,'r12-stock-fail',g['data']['id'],code=500)
   monkeypatch.setattr(inventory,'record_receipt',real)
   async with f()as db:
    assert(await db.get(ProcurementActionException,g['data']['id'])).status=='active'
    assert(await db.get(PayableBill,bid)).paid_amount==300
    assert(await db.execute(select(func.count()).select_from(InventoryMovement))).scalar_one()==1
   assert await balance(f)==9700
   accepted=await receive(c,ctx,po,80,'r12-stock-fail',g['data']['id']);assert accepted['inventory']['recorded_lines']==1
   assert(await request(c,'GET',f'/payable/{bid}/detail'))['paid_amount']==300
   actual('receipt_rollback_with_prior_payment',{'initial_payment':300,'balance_before_after_failure':9700,'exception_not_consumed_on_failure':True,'retry':accepted})
 asyncio.run(run())

def test_exact_inventory_target_outside_list_page_still_scoped_and_related_permissions(tmp_path,monkeypatch):
 async def run():
  async with fixture(tmp_path,monkeypatch)as(_,f,c,_):
   targets=[]
   for i in range(22):
    s=await sku(c,code='PAGE-'+str(i));o,_=await opening(c,s,'100',at=datetime(2026,9,1,tzinfo=THAI_TZ));targets.append(o['account'])
   target=targets[-1];first=await request(c,'GET','/inventory',params={'page_size':20});assert target['id']not in[x['id']for x in first['data']]
   risk=await request(c,'GET','/supplier-risk',params={'month':'2026-10','rule':'inventory_usage','page_size':100});link=next(x for x in risk['data']if x['detail']['inventory']['account_id']==target['id'])['evidence'][0]['url']
   assert link==f'/inventory?account_id={target["id"]}'
   exact=await request(c,'GET',f'/inventory/accounts/{target["id"]}');assert exact['account']['sku']['code']=='PAGE-21'
   for uid in(2,5):await request(c,'GET',f'/inventory/accounts/{target["id"]}',uid=uid,code=403)
   await request(c,'GET',f'/inventory/accounts/{target["id"]}',uid=7,warehouse='2',code=403)
   # Supplier-only permission must not acquire inventory data through the new link.
   async with f()as db:(await db.get(User,4)).extra_permissions=['供应商管理'];await db.commit()
   await request(c,'GET',f'/inventory/accounts/{target["id"]}',uid=4,code=403)
   actual('exact_cross_page_stock',{'first_page_ids':[a['id']for a in first['data']],'target':exact['account'],'risk_url':link,'foreign_labor_super_and_revoked_denied':True})
 asyncio.run(run())

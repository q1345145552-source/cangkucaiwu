"""真实 PostgreSQL：同一实收只核销一次，申报不是收款。"""
import asyncio
import json
import os
from datetime import date, datetime
from pathlib import Path
import pytest
from sqlalchemy import select, func
from app.models import Customer, PaymentAccount, IncomingFlow
from app.models.credit import CreditCustomer, CreditRepayment
from app.models.recharge import RechargeDeclaration, ReconciliationResult
from app.services.customer_receivables import positions
from tests.test_credit_shipments import shipments_environment, payload, wallet
from tests.test_incoming_operations import body, URL
from tests.test_round2_permissions import auth

pytestmark=pytest.mark.skipif(not URL,reason='Requires explicit loopback PostgreSQL')
REPORT={}
def actual(name,data):
 REPORT[name]=data
 if os.environ.get('CUSTOMER_RECEIVABLE_TEST_REPORT'):Path(os.environ['CUSTOMER_RECEIVABLE_TEST_REPORT']).write_text(json.dumps(REPORT,ensure_ascii=False,indent=2,default=str))
async def state(factory,cid=1,**kw):
 async with factory() as db:return (await positions(db,[1],[cid],**kw)).get(cid,{})
async def ship(client,amount,**kw):
 r=await client.post('/api/v1/credit/1/shipment',headers=auth(1),json=payload(amount=str(amount),**kw));assert r.status_code==200,r.text;return r.json()
async def receive(client,amount,**kw):
 r=await client.post('/api/v1/incoming',headers=auth(1),json=body(amount=amount,customer_id=1,**kw));assert r.status_code==200,r.text;return r.json()


def test_core_facts_600_then_declaration_then_500_two_links_no_duplicate_then_prepay_consumed(tmp_path,monkeypatch):
 async def run():
  async with shipments_environment(tmp_path,monkeypatch) as (_,f,c):
   await ship(c,1000);first=await receive(c,600)
   s1=(await state(f))['THB'];assert (s1['shipped'],s1['received'],s1['applied'],s1['outstanding'],s1['prepayment'])==(1000,600,600,400,0)
   async with f() as db:
    d=RechargeDeclaration(warehouse_id=1,customer_id=1,declare_date=datetime(2026,10,20),amount=300,currency='THB',declarer_id=1);db.add(d);await db.flush();declaration=d.id;await db.commit()
   assert (await state(f))['THB']==s1
   second=await receive(c,500);s2=(await state(f))['THB']
   assert (s2['shipped'],s2['received'],s2['applied'],s2['outstanding'],s2['prepayment'])==(1000,1100,1000,0,100)
   async with f() as db:
    db.add(ReconciliationResult(warehouse_id=1,declaration_id=declaration,flow_id=second['id'],match_status='manual_matched',reconciliation_month='2026-10'))
    db.add(CreditRepayment(credit_customer_id=1,incoming_flow_id=second['id'],repayment_date=datetime(2026,10,20),amount=500));await db.commit()
   linked=(await state(f))['THB'];assert linked==s2 and linked['receipt_count']==2
   await ship(c,80);s3=(await state(f))['THB'];assert s3['prepayment']==20 and s3['outstanding']==0 and s3['received']==1100
   w=await wallet(f);assert w['wallet_income']==1100 and w['wallet_flow_count']==2 and w['balance']==1100
   actual('core',{'after_600':s1,'declaration_only_unchanged':True,'after_500':s2,'after_double_link':linked,'after_ship_80':s3,'wallet':w})
 asyncio.run(run())


def test_prepay_first_150_shipment_and_cross_month_statement(tmp_path,monkeypatch):
 async def run():
  async with shipments_environment(tmp_path,monkeypatch) as (_,f,c):
   await receive(c,100,received_date='2026-09-30');before=(await state(f))['THB'];assert before['prepayment']==100 and before['applied']==0
   await ship(c,150,ship_date='2026-10-01')
   after=(await state(f))['THB'];assert after['outstanding']==50 and after['prepayment']==0 and after['applied']==100
   period=(await state(f,start_date=date(2026,10,1),end_date=date(2026,10,31),sources=True))['THB']
   assert period['opening_signed_balance']==-100 and len(period['events'])==1 and period['events'][0]['outstanding_after']==50
   actual('prepay_first',{'before':before,'after':after,'october_statement':period,'wallet':await wallet(f)})
 asyncio.run(run())


def test_unassigned_name_not_used_and_conflicting_customer_links_not_allocated(tmp_path,monkeypatch):
 async def run():
  async with shipments_environment(tmp_path,monkeypatch) as (_,f,c):
   await ship(c,1000)
   raw=body(amount=600,payer_name='客户A');r=await c.post('/api/v1/incoming',headers=auth(1),json=raw);assert r.status_code==200
   assert (await state(f))['THB']['received']==0
   async with f() as db:
    d=RechargeDeclaration(warehouse_id=1,customer_id=1,declare_date=datetime(2026,10,20),amount=600,currency='THB',declarer_id=1);db.add(d);await db.flush()
    db.add(ReconciliationResult(warehouse_id=1,declaration_id=d.id,flow_id=r.json()['id'],match_status='matched',reconciliation_month='2026-10'));await db.commit()
   assert (await state(f))['THB']['received']==600
   async with f() as db:
    d=RechargeDeclaration(warehouse_id=1,customer_id=3,declare_date=datetime(2026,10,20),amount=600,currency='THB',declarer_id=1);db.add(d);await db.flush()
    db.add(ReconciliationResult(warehouse_id=1,declaration_id=d.id,flow_id=r.json()['id'],match_status='matched',reconciliation_month='2026-10'));await db.commit()
   assert (await state(f))['THB']['received']==0 and not await state(f,3)
   assert (await wallet(f))['wallet_income']==600
   actual('no_guessing',{'payer_name_only_received':0,'one_explicit_match_received':600,'conflicting_matches_received':0,'company_wallet_still':600})
 asyncio.run(run())


def test_currencies_and_mixed_warehouse_batch_atomic(tmp_path,monkeypatch):
 async def run():
  async with shipments_environment(tmp_path,monkeypatch) as (_,f,c):
   async with f() as db:
    db.add(PaymentAccount(id=3,warehouse_id=1,account_name='人民币',account_type='cash',account_number='-',currency='CNY',opening_balance=0,opening_balance_date=date(2026,10,1)));await db.commit()
   await ship(c,1000);await receive(c,600);await receive(c,200,currency='CNY',account_id=3)
   result=await state(f);assert result['THB']['outstanding']==400 and result['CNY']['prepayment']==200
   before=await wallet(f)
   records=[{k:v for k,v in body(amount=10,customer_id=cid).items() if k!='request_key'} for cid in (1,2)]
   r=await c.post('/api/v1/incoming/batch-import',headers=auth(1),json={'request_key':'round11-foreign-batch','records':records});assert r.status_code==403
   assert await wallet(f)==before
   actual('currencies_batch',{'positions':result,'mixed_warehouse_batch_status':403,'batch_wallet_unchanged':True})
 asyncio.run(run())

async def statement(client,cid=1,uid=1,**query):
 r=await client.get(f'/api/v1/customers/{cid}/receivables',headers=auth(uid),params=query)
 assert r.status_code==200,r.text
 return r.json()


def test_http_same_source_match_credit_unmatch_and_all_read_consumers_agree(tmp_path,monkeypatch):
 async def run():
  async with shipments_environment(tmp_path,monkeypatch) as (_,f,c):
   await ship(c,1000)
   received=await receive(c,600)
   async with f() as db:
    d=RechargeDeclaration(warehouse_id=1,customer_id=1,declare_date=datetime(2026,10,20),amount=300,currency='THB',declarer_id=1)
    db.add(d);await db.flush();did=d.id;await db.commit()
   matched=await c.post('/api/v1/reconciliation/manual-match',headers=auth(1),params={'declaration_id':did,'flow_id':received['id']})
   assert matched.status_code==200,matched.text
   payment=await c.post('/api/v1/credit/1/payment',headers=auth(1),json={'incoming_flow_id':received['id'],'repayment_date':'2026-10-20','amount':600,'request_key':'same-real-money'})
   assert payment.status_code==200,payment.text
   s=await statement(c);pos=s['by_currency']['THB'];assert (pos['received'],pos['outstanding'],pos['receipt_count'])==(600,400,1)
   assert len(pos['events'])==2
   customers=(await c.get('/api/v1/customers',headers=auth(1))).json()
   assert next(r for r in customers['data'] if r['id']==1)['receivables']['THB']['outstanding']==400
   credits=(await c.get('/api/v1/credit',headers=auth(1))).json()
   assert next(r for r in credits['data'] if r['id']==1)['current_debt']==400
   detail=(await c.get('/api/v1/credit/1/detail',headers=auth(1))).json();assert detail['current_debt']==400
   dashboard=(await c.get('/api/v1/credit/dashboard',headers=auth(1))).json();assert dashboard['currency_totals']['THB']['total_debt']==400
   preview=(await c.get('/api/v1/reports/previews',headers=auth(1))).json();assert preview['previews']['credit']['preview_by_currency']['THB']==400
   report=(await c.get('/api/v1/reports/credit',headers=auth(1))).json();assert report['total_debt_by_currency']['THB']==400
   cockpit=(await c.get('/api/v1/dashboard/cockpit?month=2026-10',headers=auth(1))).json()
   assert next(r for r in cockpit['finance']['receivable_payable']['receivable'] if r['currency']=='THB')['amount']==400
   async with f() as db:rr=(await db.execute(select(ReconciliationResult))).scalar_one();rrid=rr.id
   for method,path,kwargs in [('PUT',f'/recharge/{did}',{'json':{'customer_id':3,'declare_date':'2026-10-20','amount':300,'currency':'THB'}}),('DELETE',f'/recharge/{did}',{})]:
    r=await c.request(method,'/api/v1'+path,headers=auth(1),**kwargs);assert r.status_code==400,r.text
   unmatch=await c.post('/api/v1/reconciliation/unmatch',headers=auth(1),params={'record_id':rrid});assert unmatch.status_code==200
   assert (await statement(c))['by_currency']['THB']==pos
   assert (await wallet(f))['wallet_income']==600
   actual('http_consistency',{'matched':matched.json(),'credit_link':payment.json(),'all_pages_outstanding':400,'unique_received':600,'unmatch_keeps_receipt':unmatch.json(),'source_ids':[(e['source'],e['source_id']) for e in pos['events']]})
 asyncio.run(run())


def test_receipt_link_concurrency_ownership_permissions_scope_and_rollback(tmp_path,monkeypatch):
 async def run():
  from app.models import User
  from app.models.data_change_history import DataChangeHistory
  import app.services.data_history as history
  from app.main import app
  from httpx import AsyncClient,ASGITransport
  async with shipments_environment(tmp_path,monkeypatch) as (_,f,c):
   raw=await c.post('/api/v1/incoming',headers=auth(1),json=body(amount=100))
   fid=raw.json()['id'];before=await wallet(f)
   rs=await asyncio.gather(*[c.post('/api/v1/customers/1/receipts/link',headers=auth(3),json={'incoming_flow_id':fid}) for _ in range(10)])
   assert all(r.status_code==200 for r in rs),[(r.status_code,r.text) for r in rs]
   assert sum(r.json()['linked'] for r in rs)==1
   assert await wallet(f)==before
   r=await c.post('/api/v1/customers/3/receipts/link',headers=auth(1),json={'incoming_flow_id':fid});assert r.status_code==409
   for uid in (2,5):
    for method,path,kw in [('GET','/customers/1/receivables',{}),('POST','/customers/1/receipts/link',{'json':{'incoming_flow_id':fid}})]:
     assert (await c.request(method,'/api/v1'+path,headers=auth(uid),**kw)).status_code==403
   for cid,uid in [(2,1),(1,7)]:assert (await c.get(f'/api/v1/customers/{cid}/receivables',headers=auth(uid))).status_code==403
   assert (await c.get('/api/v1/customers/1/receivables',headers={**auth(1),'X-Warehouse-ID':'2'})).status_code==403
   foreign=await c.post('/api/v1/incoming',headers=auth(7),json=body(amount=100,customer_id=2,account_id=2))
   assert foreign.status_code==200
   assert (await c.post('/api/v1/customers/1/receipts/link',headers=auth(1),json={'incoming_flow_id':foreign.json()['id']})).status_code==403
   async with f() as db:
    assert (await db.execute(select(func.count(DataChangeHistory.id)))).scalar_one()==1
    (await db.get(User,3)).extra_permissions=['充值申报'];await db.commit()
   assert (await c.get('/api/v1/customers/1/receivables',headers=auth(3))).status_code==403
   shared=await c.get('/api/v1/customers',headers=auth(3));assert shared.status_code==200
   assert all('receivables' not in r for r in shared.json()['data'])
   empty=(await c.post('/api/v1/incoming',headers=auth(1),json=body(amount=25))).json()
   async def fail(*args,**kwargs):raise RuntimeError('isolated history failure')
   with monkeypatch.context() as mp:
    mp.setattr(history,'record_history',fail)
    async with AsyncClient(transport=ASGITransport(app=app,raise_app_exceptions=False),base_url='http://isolated') as h:
     failed=await h.post('/api/v1/customers/1/receipts/link',headers=auth(1),json={'incoming_flow_id':empty['id']});assert failed.status_code==500
   async with f() as db:assert (await db.get(IncomingFlow,empty['id'])).customer_id is None
   actual('link_safety',{'parallel_requests':10,'new_links':1,'wallet_unchanged_by_link':True,'other_customer':409,'foreign_receipt':403,'labor_superadmin':403,'revoked_permission':403,'shared_selector_still_works':200,'failed_history_binding_rolled_back':True})
 asyncio.run(run())


def test_credit_new_receipt_idempotence_conflicts_concurrency_and_atomic_failure(tmp_path,monkeypatch):
 async def run():
  import app.api.v1.credit as credit
  from httpx import AsyncClient,ASGITransport
  from app.main import app
  async with shipments_environment(tmp_path,monkeypatch) as (_,f,c):
   await ship(c,1000)
   data={'request_key':'round11-payment','repayment_date':'2026-10-20','amount':600,'account_id':1}
   rs=await asyncio.gather(*[c.post('/api/v1/credit/1/payment',headers=auth(1),json=data) for _ in range(10)])
   assert all(r.status_code==200 for r in rs),[(r.status_code,r.text) for r in rs]
   assert len({r.json()['id'] for r in rs})==len({r.json()['incoming_flow_id'] for r in rs})==1
   assert (await wallet(f))['wallet_income']==600 and (await state(f))['THB']['outstanding']==400
   assert (await c.post('/api/v1/credit/1/payment',headers=auth(1),json={**data,'amount':601})).status_code==409
   assert (await c.post('/api/v1/credit/3/payment',headers=auth(1),json=data)).status_code==409
   async def fail(*args,**kwargs):raise RuntimeError('isolated repayment history failure')
   before=await wallet(f)
   with monkeypatch.context() as mp:
    mp.setattr(credit,'record_history',fail)
    async with AsyncClient(transport=ASGITransport(app=app,raise_app_exceptions=False),base_url='http://isolated') as h:
     failed=await h.post('/api/v1/credit/1/payment',headers=auth(1),json={**data,'request_key':'failure','amount':25});assert failed.status_code==500
   assert await wallet(f)==before
   async with f() as db:assert (await db.execute(select(func.count(CreditRepayment.id)))).scalar_one()==1
   actual('credit_concurrency',{'requests':10,'actual_receipts':1,'repayment_markers':1,'real_received':600,'debt':400,'failed_request_wallet_unchanged':True})
 asyncio.run(run())


def test_historical_manual_debt_unlinked_payments_manual_income_quarantined_and_cache_preserved(tmp_path,monkeypatch):
 async def run():
  from app.models import IncomeRecord,IncomeExpenseCategory
  async with shipments_environment(tmp_path,monkeypatch) as (_,f,c):
   async with f() as db:
    (await db.get(Customer,1)).debt_amount=777
    (await db.get(CreditCustomer,1)).current_debt=999
    db.add(CreditRepayment(credit_customer_id=1,repayment_date=datetime(2026,9,1),amount=55))
    db.add(IncomeExpenseCategory(id=1,warehouse_id=1,type='income',name='赔偿',category_group='other'));await db.flush()
    db.add_all([IncomeRecord(warehouse_id=1,customer_id=1,category_id=1,account_id=1,income_date=datetime(2026,10,20),amount=v,currency='THB') for v in (200,-10)])
    await db.commit()
   before_wallet=await wallet(f)
   await ship(c,1000);await receive(c,600)
   r=await statement(c);p=r['by_currency']['THB']
   assert (p['received'],p['applied'],p['outstanding'],p['prepayment'])==(600,600,400,0)
   assert len(r['review_items'])==5 and r['needs_review']
   assert {v['type'] for v in r['review_items']}=={'legacy_manual_debt','legacy_unlinked_payment','manual_income_purpose_unconfirmed','legacy_credit_cache_difference'}
   async with f() as db:
    assert (await db.get(Customer,1)).debt_amount==777 and (await db.get(CreditCustomer,1)).current_debt==999
    assert (await db.execute(select(func.count(CreditRepayment.id)))).scalar_one()==1
    assert (await db.execute(select(func.sum(IncomeRecord.amount)))).scalar_one()==190
   actual('historical_review',{'legacy_debt_preserved':777,'credit_cache_preserved':999,'unlinked_repayment_preserved':55,'manual_incomes_preserved':[200,-10],'pending_review_count':5,'verified_outstanding':400,'verified_received':600,'wallet_before':before_wallet,'wallet_after':await wallet(f)})
 asyncio.run(run())


def test_customer_receipt_migration_old_new_repeated_failure_savepoint_and_legacy_retry(tmp_path,monkeypatch):
 async def run():
  from sqlalchemy import text
  from sqlalchemy.ext.asyncio import AsyncConnection
  from scripts.seed import _migrate_customer_receipt_identity
  async with shipments_environment(tmp_path,monkeypatch) as (engine,f,c):
   old_body=body(amount=123);old=(await c.post('/api/v1/incoming',headers=auth(1),json=old_body)).json()
   async with engine.begin() as conn:
    fingerprint=(await conn.execute(text('SELECT request_fingerprint FROM incoming_flows'))).scalar_one()
    await _migrate_customer_receipt_identity(conn);await _migrate_customer_receipt_identity(conn)
    await conn.execute(text('ALTER TABLE incoming_flows DROP COLUMN customer_id CASCADE'))
    await _migrate_customer_receipt_identity(conn);await _migrate_customer_receipt_identity(conn)
    row=(await conn.execute(text('SELECT amount,customer_id,request_fingerprint FROM incoming_flows'))).one()
    assert tuple(row)==(123,None,fingerprint)
    original=AsyncConnection.execute
    async def fail(self,statement,*args,**kwargs):
     if 'ADD COLUMN IF NOT EXISTS customer_id' in str(statement):return await original(self,text('SELECT round11_missing_column'),*args,**kwargs)
     return await original(self,statement,*args,**kwargs)
    with monkeypatch.context() as mp:
     mp.setattr(AsyncConnection,'execute',fail)
     with pytest.raises(Exception):await _migrate_customer_receipt_identity(conn)
    assert (await conn.execute(text('SELECT count(*) FROM incoming_flows'))).scalar_one()==1
   replay=await c.post('/api/v1/incoming',headers=auth(1),json=old_body)
   assert replay.status_code==200 and replay.json()['id']==old['id'] and not replay.json()['created']
   assert (await wallet(f))['wallet_income']==123 and not await state(f)
   actual('migration',{'new_old_repeat':True,'savepoint_failure_transaction_usable':True,'historical_amount':123,'historical_customer_id':None,'request_fingerprint_unchanged':True,'old_retry_creates_new_money':False})
 asyncio.run(run())


def test_same_receipt_cannot_concurrently_match_two_customers_and_amount_currency_date_checks(tmp_path,monkeypatch):
 async def run():
  async with shipments_environment(tmp_path,monkeypatch) as (_,f,c):
   raw=(await c.post('/api/v1/incoming',headers=auth(1),json=body(amount=100))).json()
   async with f() as db:
    declarations=[RechargeDeclaration(warehouse_id=1,customer_id=cid,declare_date=datetime(2026,10,20),amount=100,currency='THB',declarer_id=1) for cid in (1,3)]
    db.add_all(declarations);await db.flush();ids=[d.id for d in declarations];await db.commit()
   rs=await asyncio.gather(*[c.post('/api/v1/reconciliation/manual-match',headers=auth(1),params={'declaration_id':did,'flow_id':raw['id']}) for did in ids])
   assert sorted(r.status_code for r in rs)==[200,400]
   both=[await state(f,cid) for cid in (1,3)]
   assert sum(p.get('THB',{}).get('received',0) for p in both)==100
   fid=(await receive(c,25))['id']
   for kw in [{'amount':24},{'repayment_date':'2026-10-19'}]:
    r=await c.post('/api/v1/credit/1/payment',headers=auth(1),json={'incoming_flow_id':fid,'repayment_date':'2026-10-20','amount':25,**kw});assert r.status_code==400,r.text
   assert (await c.post('/api/v1/credit/4/payment',headers=auth(1),json={'incoming_flow_id':fid,'repayment_date':'2026-10-20','amount':25})).status_code==400
   assert (await wallet(f))['wallet_income']==125
   actual('source_validation',{'parallel_match_status':[r.status_code for r in rs],'unique_100_source_received_total':100,'wrong_amount_date_currency':400,'wallet':await wallet(f)})
 asyncio.run(run())


def test_cache_only_manual_amount_and_cents_do_not_net_other_customers_prepayment(tmp_path,monkeypatch):
 async def run():
  from app.services.customer_receivables import customer_credit_totals
  async with shipments_environment(tmp_path,monkeypatch) as (_,f,c):
   async with f() as db:
    (await db.get(CreditCustomer,3)).current_debt=888;await db.commit()
   review=await statement(c,3)
   assert review['needs_review'] and review['review_items'][0]['type']=='legacy_credit_cache_difference'
   assert review['by_currency']['THB']['outstanding']==0
   await ship(c,'0.10',order_count=1)
   r=await c.post('/api/v1/credit/3/shipment',headers=auth(1),json=payload(amount='0.20',order_count=1));assert r.status_code==200
   async with f() as db:
    assert await customer_credit_totals(db,[1])=={'THB':.3}
    assert (await db.get(CreditCustomer,3)).current_debt==888
    assert (await db.get(CreditCustomer,1)).current_debt is None
   await receive(c,1)
   balances=await state(f);b=await state(f,3)
   assert balances['THB']['prepayment']==.9 and b['THB']['outstanding']==.2
   async with f() as db:assert await customer_credit_totals(db,[1])=={'THB':.2}
   actual('cache_and_customer_separation',{'manual_cache_kept':888,'manual_cache_as_receivable':0,'positive_receivables_before_receipt':.3,'customer_A_prepayment':.9,'customer_B_still_owes':.2,'warehouse_positive_receivables':.2})
 asyncio.run(run())


def test_cross_warehouse_malformed_historical_match_cannot_touch_foreign_source(tmp_path,monkeypatch):
 async def run():
  async with shipments_environment(tmp_path,monkeypatch) as (_,f,c):
   foreign=(await c.post('/api/v1/incoming',headers=auth(7),json=body(amount=100,account_id=2,customer_id=2))).json()
   async with f() as db:
    d=RechargeDeclaration(warehouse_id=1,customer_id=1,declare_date=datetime(2026,10,20),amount=100,currency='THB',declarer_id=1);db.add(d);await db.flush();did=d.id
    rr=ReconciliationResult(warehouse_id=1,declaration_id=did,flow_id=foreign['id'],match_status='manual_matched',reconciliation_month='2026-10');db.add(rr);await db.flush();rid=rr.id;await db.commit()
   refused=await c.post('/api/v1/reconciliation/unmatch',headers=auth(1),params={'record_id':rid})
   assert refused.status_code==403,refused.text
   match=await c.post('/api/v1/reconciliation/manual-match',headers=auth(1),params={'declaration_id':did,'flow_id':foreign['id']});assert match.status_code==403
   async with f() as db:
    assert (await db.get(IncomingFlow,foreign['id'])).match_status=='unmatched'
    assert await db.get(ReconciliationResult,rid) is not None
   assert not await state(f)
   actual('malformed_foreign_match',{'unmatch_status':403,'new_match_status':403,'foreign_source_unchanged':True,'old_match_preserved_for_review':True,'foreign_money_allocated_to_local':0})
 asyncio.run(run())

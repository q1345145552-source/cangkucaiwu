"""Only disposable loopback PostgreSQL and synthetic customer XT10022."""
import asyncio,json
from datetime import datetime
from pathlib import Path
from sqlalchemy import select,func
from httpx import AsyncClient,ASGITransport
from app.main import app
from app.models import Customer,User,UserWarehouse,IncomingFlow,RechargeDeclaration
from app.models.recharge import ReconciliationResult
from app.services.customer_receivables import positions
from tests.test_incoming_operations import environment,body,numbers
from tests.test_round2_permissions import auth
from tests.evidence_path import evidence_dir
OUT=evidence_dir('incoming-suggestions-20261028')
def save(name,value):OUT.joinpath(name).write_text(json.dumps(value,ensure_ascii=False,indent=2,default=str))
async def seed(f):
 async with f() as db:
  customer=await db.get(Customer,1);customer.customer_code='XT10022';customer.company_name='合成客户甲'
  db.add_all([Customer(id=2,warehouse_id=1,customer_code='XT20022',company_name='合成客户乙'),Customer(id=3,warehouse_id=2,customer_code='XT10022',company_name='外仓同名客户')])
  (await db.get(User,4)).extra_permissions=['到账流水','对账中心']
  await db.flush()
  values=[(1,1,1,20,3000,'THB','unmatched'),(2,1,2,20,3000,'THB','unmatched'),(3,1,2,20,4000,'THB','unmatched'),(4,1,1,15,3000,'THB','unmatched'),(5,1,2,15,4000,'THB','unmatched'),(6,2,3,20,3000,'THB','unmatched'),(7,1,1,20,3000,'CNY','unmatched'),(8,1,1,20,3000,'THB','matched')]
  for id,wid,cid,day,amount,cur,status in values:db.add(RechargeDeclaration(id=id,warehouse_id=wid,customer_id=cid,declare_date=datetime(2026,10,day),amount=amount,currency=cur,match_status=status,declarer_id=1,screenshot='synthetic-proof.png'))
  await db.commit()
async def position(f):
 async with f() as db:return (await positions(db,[1],[1])).get(1,{}).get('THB',{'received':0,'prepayment':0,'receipt_count':0})
async def receive(c,**kw):return await c.post('/api/v1/incoming',headers=auth(1),json=body(amount=3000,payer_name='XT10022',**kw))
async def match(c,did,fid,uid=1):return await c.post('/api/v1/reconciliation/manual-match',headers=auth(uid),params={'declaration_id':did,'flow_id':fid})
def test_suggestions_ranking_optional_customer_and_five_day_rule(tmp_path,monkeypatch):
 async def run():
  async with environment(tmp_path,monkeypatch) as (_,f,c):
   await seed(f);r=await receive(c);assert r.status_code==200,r.text
   data=r.json();assert data['customer_id'] is None and data['match_status']=='unmatched'
   ss=data['suggestions'];assert [s['declaration_id'] for s in ss]==[1,2,4,3]
   assert [s['matched_count'] for s in ss]==[3,2,2,1]
   assert ss[2]['date_distance_days']==5 and '日期相差不超过3天' not in ss[2]['matched_conditions']
   assert (await position(f))['received']==0 and await numbers(f)=={'count':1,'balance':3000}
   blank=await c.post('/api/v1/incoming',headers=auth(1),json=body(amount=123,payer_name='未知付款方',customer_id=None));assert blank.status_code==200 and blank.json()['customer_id'] is None
   save('step1-create.json',{'http':r.status_code,'response':data,'customer_before_match':await position(f)})
   save('step5-empty-customer.json',{'http':blank.status_code,'response':blank.json()})
   save('step2-five-days.json',{'rule':'用户确认超过三天可按金额或名称命中','candidate':ss[2]})
 asyncio.run(run())
def test_confirm_undo_rematch_no_duplicate_money(tmp_path,monkeypatch):
 async def run():
  async with environment(tmp_path,monkeypatch) as (_,f,c):
   await seed(f);fid=(await receive(c)).json()['id']
   listing=await c.get('/api/v1/reconciliation/unmatched?start_date=2026-10-01&end_date=2026-10-31',headers=auth(1));assert listing.status_code==200,listing.text
   assert listing.json()['incoming'][0]['suggestions'][0]['declaration_id']==1
   before=await position(f);r=await match(c,1,fid);assert r.status_code==200,r.text
   matched=r.json();after=await position(f);assert after['received']==after['prepayment']==3000 and after['receipt_count']==1
   async with f() as db:assert (await db.get(IncomingFlow,fid)).customer_id==1 and (await db.get(RechargeDeclaration,1)).match_status=='matched'
   retry=await match(c,1,fid);assert retry.status_code==400 and await position(f)==after
   undone=await c.post('/api/v1/reconciliation/unmatch',headers=auth(1),params={'record_id':matched['id']});assert undone.status_code==200,undone.text
   assert undone.json()['customer_binding_reverted'] and (await position(f))['received']==0
   async with f() as db:assert (await db.get(IncomingFlow,fid)).customer_id is None and (await db.get(RechargeDeclaration,1)).match_status=='unmatched'
   again=await match(c,1,fid);assert again.status_code==200 and (await position(f))['received']==3000
   assert await numbers(f)=={'count':1,'balance':3000}
   save('step3-match.json',{'listing':listing.json(),'http':r.status_code,'response':matched,'customer_before':before,'customer_after':after,'wallet':await numbers(f)})
   save('step4-undo.json',{'http':undone.status_code,'response':undone.json(),'customer_received_after_undo':0,'rematch':again.json(),'wallet':await numbers(f)})
 asyncio.run(run())
def test_concurrent_match_and_unmatch_are_atomic(tmp_path,monkeypatch):
 async def run():
  async with environment(tmp_path,monkeypatch) as (_,f,c):
   await seed(f);fid=(await receive(c)).json()['id']
   rs=await asyncio.gather(*(match(c,1,fid) for _ in range(6)));assert sorted(r.status_code for r in rs)==[200,400,400,400,400,400]
   rid=next(r.json()['id'] for r in rs if r.status_code==200)
   rs=await asyncio.gather(*(c.post('/api/v1/reconciliation/unmatch',headers=auth(1),params={'record_id':rid}) for _ in range(4)))
   assert sum(r.status_code==200 for r in rs)==1 and all(r.status_code in (200,404,409) for r in rs)
   assert (await position(f))['received']==0 and await numbers(f)=={'count':1,'balance':3000}
 asyncio.run(run())
def test_permission_warehouse_and_currency_guards(tmp_path,monkeypatch):
 async def run():
  async with environment(tmp_path,monkeypatch) as (_,f,c):
   await seed(f);fid=(await receive(c)).json()['id']
   for did,uid,code in [(6,1,403),(7,1,400),(1,3,403),(1,7,403)]:assert (await match(c,did,fid,uid)).status_code==code
   async with f() as db:db.add(UserWarehouse(user_id=1,warehouse_id=2));await db.commit()
   r=await c.get('/api/v1/reconciliation/unmatched?start_date=2026-10-01&end_date=2026-10-31',headers={**auth(1),'X-Warehouse-ID':'2'});assert r.status_code==200 and not r.json()['incoming']
   assert (await position(f))['received']==0
 asyncio.run(run())
def test_match_audit_failure_rolls_back(tmp_path,monkeypatch):
 async def run():
  import app.services.data_history as history
  async with environment(tmp_path,monkeypatch) as (_,f,c):
   await seed(f);fid=(await receive(c)).json()['id'];original=history.record_history
   async def fail(*args,**kw):
    if kw['module']=='reconciliation':raise RuntimeError('synthetic audit failure')
    return await original(*args,**kw)
   monkeypatch.setattr(history,'record_history',fail)
   async with AsyncClient(transport=ASGITransport(app=app,raise_app_exceptions=False),base_url='http://isolated-test') as faulty:assert (await match(faulty,1,fid)).status_code==500
   async with f() as db:
    assert (await db.get(IncomingFlow,fid)).customer_id is None and (await db.get(RechargeDeclaration,1)).match_status=='unmatched'
    assert (await db.execute(select(func.count()).select_from(ReconciliationResult))).scalar_one()==0
   assert (await position(f))['received']==0 and (await numbers(f))['balance']==3000
 asyncio.run(run())

def test_date_boundary_name_only_and_zero_conditions(tmp_path,monkeypatch):
 async def run():
  async with environment(tmp_path,monkeypatch) as (_,f,c):
   await seed(f)
   async with f() as db:
    db.add_all([RechargeDeclaration(id=9,warehouse_id=1,customer_id=2,declare_date=datetime(2026,10,23),amount=4000,currency='THB',declarer_id=1),RechargeDeclaration(id=10,warehouse_id=1,customer_id=2,declare_date=datetime(2026,10,24),amount=4000,currency='THB',declarer_id=1),RechargeDeclaration(id=11,warehouse_id=1,customer_id=2,declare_date=datetime(2026,10,17),amount=4000,currency='THB',declarer_id=1)])
    await db.commit()
   data=(await receive(c)).json();ss={s['declaration_id']:s for s in data['suggestions']}
   assert ss[9]['matched_count']==ss[11]['matched_count']==1 and ss[9]['date_distance_days']==ss[11]['date_distance_days']==3 and 10 not in ss
   name_only=await c.post('/api/v1/incoming',headers=auth(1),json=body(received_date='2026-09-01',amount=123,payer_name='合成客户甲'))
   assert name_only.status_code==200 and all(s['matched_count']==1 and s['customer_id']==1 for s in name_only.json()['suggestions'])
   none=await c.post('/api/v1/incoming',headers=auth(1),json=body(received_date='2026-09-01',amount=123,payer_name='完全未知'))
   assert none.status_code==200 and none.json()['suggestions']==[] and none.json()['customer_id'] is None
 asyncio.run(run())
def test_unmatch_audit_failure_restores_all_changes(tmp_path,monkeypatch):
 async def run():
  import app.services.data_history as history
  async with environment(tmp_path,monkeypatch) as (_,f,c):
   await seed(f);fid=(await receive(c)).json()['id'];rid=(await match(c,1,fid)).json()['id'];original=history.record_history
   async def fail(*args,**kw):
    if kw['operation_type']=='unmatch':raise RuntimeError('synthetic undo audit failure')
    return await original(*args,**kw)
   monkeypatch.setattr(history,'record_history',fail)
   async with AsyncClient(transport=ASGITransport(app=app,raise_app_exceptions=False),base_url='http://isolated-test') as faulty:
    r=await faulty.post('/api/v1/reconciliation/unmatch',headers=auth(1),params={'record_id':rid});assert r.status_code==500
   async with f() as db:
    assert (await db.get(IncomingFlow,fid)).customer_id==1 and (await db.get(RechargeDeclaration,1)).match_status=='matched'
    assert await db.get(ReconciliationResult,rid)
   assert (await position(f))['received']==3000 and (await numbers(f))['balance']==3000
 asyncio.run(run())
def test_no_schema_balance_or_recharge_submission_changes():
 import subprocess
 root=Path(__file__).resolve().parents[2]
 for path in ['backend/app/models/recharge.py','backend/app/schemas/business.py','backend/app/services/customer_receivables.py','backend/app/services/account_balances.py','backend/app/api/v1/recharge.py','backend/app/services/incoming_receipts.py']:
  assert (root/path).read_text()==subprocess.check_output(['git','show',('87a461b:' if path in ('backend/app/schemas/business.py','backend/app/api/v1/recharge.py') else '92160ed:')+path],cwd=root,text=True)

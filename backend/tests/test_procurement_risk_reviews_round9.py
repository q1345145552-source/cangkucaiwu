"""Server evidence identity and append-only conclusions; synthetic localhost only."""
import asyncio,csv,io,copy
from sqlalchemy import select
from app.models import ProcurementRiskReview,ProcurementActionException,ProcurementDutyExecution
from app.services import procurement_risk as risk
from tests.test_procurement_controls_round9 import fixture,scenario,setting,order,request,actual,num
from tests.test_round2_permissions import auth

async def current(c,month='2026-10',**scope):
 result=await request(c,'GET','/supplier-risk',params={'month':month,'rule':'concentration','page_size':100,**scope})
 return next(r for r in result['data'] if r['detail']['supplier_id']==1 and r['detail']['currency']=='THB')
def body(row,key='review-key',conclusion='cleared',why='已逐项核对凭证和供货情况'):
 return {'request_key':key,'expected_evidence_version':row['review']['evidence_version'],'expected_latest_review_id':row['review']['latest_review_id'],'conclusion':conclusion,'review_reason':why}
async def save(c,row,payload,month='2026-10',**scope):
 return await request(c,'POST',f'/supplier-risk/signals/{row["id"]}/reviews',params={'month':month,**scope},json=payload)

def test_same_signal_different_month_scope_evidence_and_rule_version_do_not_inherit(tmp_path,monkeypatch):
 async def run():
  async with fixture(tmp_path,monkeypatch) as (_,f,c,_):
   po,*_=await scenario(c,f);await order(f,po,amount=300,supplier=3)
   initial=await current(c);first=await save(c,initial,body(initial,'first'));snapshot=copy.deepcopy(first['data']['snapshot'])
   same=await current(c);assert same['review']['status']=='cleared' and not same['review']['stale']
   september=await current(c,month='2026-09');assert september['id']==initial['id'] and september['review']['status']=='pending' and not september['review']['history']
   narrowed=await current(c,supplier_id=1);assert narrowed['id']==initial['id'] and narrowed['detail']['percent']=='100.00' and narrowed['review']['status']=='pending'
   assert narrowed['review']['subject_key']!=initial['review']['subject_key']
   await setting(f,'supplier_concentration_threshold','20');changed=await current(c);assert changed['review']['stale'] and changed['review']['status']=='pending' and changed['review']['message'].startswith('证据已变化')
   await request(c,'POST',f'/supplier-risk/signals/{initial["id"]}/reviews',params={'month':'2026-10'},json=body(initial,'old-evidence'),code=409)
   second=await save(c,changed,body(changed,'second','follow_up','需补充供应商说明'));after=await current(c);assert after['review']['status']=='follow_up' and len(after['review']['history'])==2
   assert after['review']['history'][1]['snapshot']==snapshot
   monkeypatch.setattr(risk,'VERSION','synthetic-rule-version-v2');versioned=await current(c);assert versioned['id']!=initial['id'] and versioned['review']['stale'] and versioned['review']['status']=='pending' and len(versioned['review']['history'])==2
   assert await num(f,ProcurementActionException)==0 and await num(f,ProcurementDutyExecution)==0
   actual('review_identity',{'initial':initial,'first':first,'other_month':september,'narrowed':narrowed,'changed':changed,'second':second,'after':after,'versioned':versioned})
 asyncio.run(run())

def test_exact_request_replay_concurrent_latest_guard_and_immutable_export(tmp_path,monkeypatch):
 async def run():
  async with fixture(tmp_path,monkeypatch) as (_,f,c,_):
   await scenario(c,f);row=await current(c);payload=body(row,'lost-response',why='\t=SUM(1,2)')
   first=await save(c,row,payload);repeat=await save(c,row,payload);assert repeat['replayed'] and repeat['data']['id']==first['data']['id'] and await num(f,ProcurementRiskReview)==1
   await request(c,'POST',f'/supplier-risk/signals/{row["id"]}/reviews',params={'month':'2026-10'},json={**payload,'review_reason':'changed same key'},code=409)
   fresh=await current(c);a=body(fresh,'race-review-a','follow_up');b=body(fresh,'race-review-b','pending')
   responses=await asyncio.gather(*[c.post(f'/api/v1/supplier-risk/signals/{row["id"]}/reviews?month=2026-10',headers=auth(1),json=v) for v in (a,b)])
   assert sorted(r.status_code for r in responses)==[200,409] and await num(f,ProcurementRiskReview)==2
   history=await request(c,'GET','/supplier-risk/reviews',params={'month':'2026-10'});assert history['total']==2 and history['data'][1]['snapshot']==first['data']['snapshot']
   export=await c.get('/api/v1/supplier-risk/reviews/export?month=2026-10',headers=auth(1));assert export.status_code==200
   rows=list(csv.reader(io.StringIO(export.content.decode('utf-8-sig'))));assert len(rows)==3 and any(r[5].startswith("'=") for r in rows[1:])
   actual('review_replay_concurrency',{'first':first,'repeat':repeat,'race':[{'status':r.status_code,'body':r.json()} for r in responses],'history':history,'csv_rows':len(rows)-1,'csv_formula_safe':True})
 asyncio.run(run())

def test_owner_only_foreign_unknown_and_no_client_snapshot_authority(tmp_path,monkeypatch):
 async def run():
  async with fixture(tmp_path,monkeypatch) as (_,f,c,_):
   await scenario(c,f);row=await current(c);payload=body(row)
   for uid in (2,3,4,5):
    await request(c,'POST',f'/supplier-risk/signals/{row["id"]}/reviews',uid=uid,params={'month':'2026-10'},json=payload,code=403)
    await request(c,'GET','/supplier-risk/reviews',uid=uid,params={'month':'2026-10'},code=403)
    await request(c,'GET','/supplier-risk/reviews/export',uid=uid,params={'month':'2026-10'},code=403)
   await request(c,'POST',f'/supplier-risk/signals/{row["id"]}/reviews',uid=7,warehouse='2',params={'month':'2026-10'},json=payload,code=404)
   await request(c,'POST','/supplier-risk/signals/fake-signal/reviews',params={'month':'2026-10'},json=payload,code=404)
   await request(c,'POST',f'/supplier-risk/signals/{row["id"]}/reviews',params={'month':'2026-10'},json={**payload,'snapshot':{'fake':True}},code=422)
   assert await num(f,ProcurementRiskReview)==0
   actual('review_permissions',{'all_nonowners':403,'foreign_or_unknown':404,'client_snapshot':422,'review_count':0})
 asyncio.run(run())

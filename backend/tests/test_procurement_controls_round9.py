"""Actual HTTP on disposable localhost only; never production."""
import asyncio,json,os,uuid,copy
from pathlib import Path
from datetime import timedelta
import pytest
from sqlalchemy import select,func
from app.models import PurchaseOrder,PayableBill,PurchaseReceiptEvent,ProcurementActionException,ProcurementDutyExecution,ProcurementRiskReview,SystemSetting,User,Warehouse
from app.services import procurement_controls as duty
from app.core.timezone import thai_now
from tests.test_procurement_risk_round8 import fixture,scenario,buy,setting,order,request
from tests.test_round2_permissions import auth,png
from tests.test_incoming_operations import URL
pytestmark=pytest.mark.skipif(not URL,reason='Explicit disposable localhost only')
ACTUAL={}
def actual(k,v):
 ACTUAL[k]=v
 if os.environ.get('SUPPLIER09_REPORT'):Path(os.environ['SUPPLIER09_REPORT']).write_text(json.dumps(ACTUAL,ensure_ascii=False,default=str,indent=2))
async def policy(c,approve=False,receive=False,key=None):
 old=await request(c,'GET','/supplier-controls/policy')
 body={'no_self_approve':approve,'no_self_receive':receive,'expected_version':old['version'],'request_key':key or uuid.uuid4().hex,'change_reason':'合成测试明确启用或关闭职责规则'}
 return await request(c,'PUT','/supplier-controls/policy',json=body),body
async def context(c,po,action,uid=1):return await request(c,'GET',f'/supplier-controls/orders/{po}/context',uid=uid,params={'action':action})
def controls(c):return {'expected_policy_version':c['policy_version'],'expected_business_version':c['business_version']}
async def grant(c,ctx,key=None,**patch):
 body={'po_id':ctx['purchase_order_id'],'action':ctx['action'],'operator_id':ctx['operator_id'],**controls(ctx),'expires_at':(thai_now()+timedelta(hours=1)).isoformat(),'grant_reason':'老板明确批准一次同人操作，合成测试','request_key':key or uuid.uuid4().hex,**patch}
 return await request(c,'POST','/supplier-controls/exceptions',json=body),body
async def num(f,m):
 async with f() as db:return (await db.execute(select(func.count()).select_from(m))).scalar_one()
async def receive(c,ctx,po,qty,key,exception_id=None,code=200,uid=1):
 data={'request_key':key,'items':json.dumps([{'line_id':po['order']['items'][0]['line_id'],'received_quantity':qty}]),**controls(ctx)}
 if exception_id is not None:data['exception_id']=str(exception_id)
 return await request(c,'POST',f'/suppliers/purchase-orders/{po["order"]["id"]}/receive',uid=uid,code=code,data=data,files={'file':('arrival.png',png(),'image/png')})

def test_defaults_versions_owner_and_generic_setting_bypass(tmp_path,monkeypatch):
 async def run():
  async with fixture(tmp_path,monkeypatch) as (_,f,c,_):
   initial=await request(c,'GET','/supplier-controls/policy');assert not initial['no_self_approve'] and not initial['no_self_receive'] and initial['revision']==0
   async with f() as db:
    db.add(Warehouse(id=0,name='synthetic legacy global',code='GLOBAL0'));await db.flush()
    db.add(SystemSetting(warehouse_id=0,key=duty.KEY,value='malicious-global'));await db.commit()
   assert (await request(c,'GET','/supplier-controls/policy'))==initial
   saved,body=await policy(c,True,True);again=await request(c,'PUT','/supplier-controls/policy',json=body);assert again['replayed'] and again['policy']==saved['policy']
   await request(c,'PUT','/supplier-controls/policy',json={**body,'request_key':'new-but-stale'},code=409)
   async with f() as db:
    for uid in (2,3,4,5):(await db.get(User,uid)).extra_permissions=['供应商管理','采购风险看板','备用金管理']
    await db.commit()
   for uid in (2,3,4,5):
    await request(c,'PUT','/supplier-controls/policy',uid=uid,json={**body,'request_key':'denied-'+str(uid)},code=403)
    await request(c,'GET','/supplier-controls/exceptions',uid=uid,code=403)
    await request(c,'GET','/supplier-risk/reviews',uid=uid,code=403)
   await request(c,'POST','/expense-fund/settings',uid=4,json={'key':duty.KEY,'value':'{}'},code=403)
   assert (await request(c,'GET','/supplier-controls/policy'))['no_self_approve']
   actual('policy',{'initial':initial,'saved':saved,'repeat':again})
 asyncio.run(run())

def test_exception_misuse_revocation_expiry_unknown_creator_and_stale_context(tmp_path,monkeypatch):
 async def run():
  async with fixture(tmp_path,monkeypatch) as (_,f,c,_):
   _,s,p,q,*_=await scenario(c,f);po=await buy(c,p,q,100);other_po=await buy(c,p,q,101);oid=po['order']['id'];await policy(c,False,True)
   ctx=await context(c,oid,'receive');g,_=await grant(c,ctx);ident=g['data']['id']
   foreign_operator=await context(c,oid,'receive',4);await receive(c,foreign_operator,po,1,'wrong-actor',ident,uid=4,code=403)
   oc=await context(c,other_po['order']['id'],'receive');await receive(c,oc,other_po,1,'wrong-po',ident,code=403)
   await request(c,'GET',f'/supplier-controls/exceptions/{ident}',uid=7,warehouse='2',code=404)
   await request(c,'POST',f'/supplier-controls/exceptions/{ident}/revoke',json={'request_key':'revoke1','revoke_reason':'撤回合成授权'})
   await receive(c,ctx,po,1,'revoked-grant',ident,code=403)
   g2,_=await grant(c,ctx);id2=g2['data']['id']
   async with f() as db:(await db.get(ProcurementActionException,id2)).expires_at=thai_now()-timedelta(seconds=1);await db.commit()
   await receive(c,ctx,po,1,'expired-grant',id2,code=403)
   g3,_=await grant(c,ctx);await policy(c,False,False)
   await receive(c,ctx,po,1,'stale-policy',g3['data']['id'],code=409)
   await policy(c,False,True)
   async with f() as db:(await db.get(PurchaseOrder,oid)).created_by=None;await db.commit()
   unknown=await context(c,oid,'receive');assert unknown['unknown_creator'];await receive(c,unknown,po,1,'unknown-creator',code=409)
   assert await num(f,PurchaseReceiptEvent)==0
   actual('misuse',{'revoked_id':ident,'expired_id':id2,'invalidated_policy_grant':g3,'unknown':unknown,'receipt_count':0})
 asyncio.run(run())

def test_concurrent_same_exception_only_one_execution_and_config_race(tmp_path,monkeypatch):
 async def run():
  async with fixture(tmp_path,monkeypatch) as (_,f,c,_):
   _,s,p,q,*_=await scenario(c,f);po=await buy(c,p,q,100);oid=po['order']['id'];await policy(c,False,True);ctx=await context(c,oid,'receive');g,_=await grant(c,ctx);ident=g['data']['id']
   async def send(key):
    data={'request_key':key,'items':json.dumps([{'line_id':po['order']['items'][0]['line_id'],'received_quantity':80}]),**controls(ctx),'exception_id':str(ident)}
    return await c.post(f'/api/v1/suppliers/purchase-orders/{oid}/receive',headers=auth(1),data=data,files={'file':('photo.png',png(),'image/png')})
   responses=await asyncio.gather(send('concurrent-a'),send('concurrent-b'));assert sorted(r.status_code for r in responses)==[200,409]
   assert await num(f,PurchaseReceiptEvent)==1
   winner=next(i for i,r in enumerate(responses) if r.status_code==200);replay=await send(['concurrent-a','concurrent-b'][winner]);assert replay.status_code==200 and replay.json()['replayed']
   latest=await request(c,'GET','/supplier-controls/policy');base={'expected_version':latest['version'],'no_self_approve':False,'no_self_receive':False,'change_reason':'并发版本测试'}
   changes=await asyncio.gather(*[c.put('/api/v1/supplier-controls/policy',headers=auth(1),json={**base,'request_key':'policy-race-'+str(i)}) for i in range(2)])
   assert sorted(r.status_code for r in changes)==[200,409]
   actual('concurrency',{'receipt_statuses':[r.status_code for r in responses],'receipt_results':[r.json() for r in responses],'replay':replay.json(),'policy_statuses':[r.status_code for r in changes],'events':1})
 asyncio.run(run())

def test_policy_changes_serialized_with_business_and_original_success_replay(tmp_path,monkeypatch):
 async def run():
  async with fixture(tmp_path,monkeypatch) as (_,f,c,_):
   _,s,p,q,*_=await scenario(c,f);po=await buy(c,p,q,100);oid=po['order']['id'];await policy(c,False,True);ctx=await context(c,oid,'receive');g,_=await grant(c,ctx);ident=g['data']['id']
   change={'no_self_approve':False,'no_self_receive':False,'expected_version':ctx['policy_version'],'request_key':'toggle-race','change_reason':'老板并发关闭'}
   data={'request_key':'race-receive','items':json.dumps([{'line_id':po['order']['items'][0]['line_id'],'received_quantity':80}]),**controls(ctx),'exception_id':str(ident)}
   a,b=await asyncio.gather(c.put('/api/v1/supplier-controls/policy',headers=auth(1),json=change),c.post(f'/api/v1/suppliers/purchase-orders/{oid}/receive',headers=auth(1),data=data,files={'file':('photo.png',png(),'image/png')}))
   assert a.status_code==200 and b.status_code in (200,409)
   expected=1 if b.status_code==200 else 0;assert await num(f,PurchaseReceiptEvent)==expected
   async with f() as db:assert (await db.get(ProcurementActionException,ident)).status==('used' if expected else 'active')
   if expected:
    again=await c.post(f'/api/v1/suppliers/purchase-orders/{oid}/receive',headers=auth(1),data=data,files={'file':('photo.png',png(),'image/png')});assert again.status_code==200 and again.json()['replayed']
   actual('config_business_race',{'policy':a.json(),'business_status':b.status_code,'business':b.json(),'event_count':expected})
 asyncio.run(run())

def test_self_approval_exception_replay_other_legal_and_auto_unchanged(tmp_path,monkeypatch):
 async def run():
  async with fixture(tmp_path,monkeypatch) as (_,f,c,_):
   _,s,p,q,*_=await scenario(c,f);await setting(f,'purchase_approval_threshold',1);po=await buy(c,p,q,100);oid=po['order']['id'];assert po['pending'] and po['payable_bill_id'] is None
   await policy(c,True,True);ctx=await context(c,oid,'approve');assert ctx['needs_exception']
   denied=await request(c,'PUT',f'/suppliers/purchase-approvals/{oid}/approve',json={'request_key':'self-denied',**controls(ctx),'override':True,'reason':'fake override'},code=403)
   g,_=await grant(c,ctx);ident=g['data']['id'];body={'request_key':'approved-once',**controls(ctx),'exception_id':ident}
   result=await request(c,'PUT',f'/suppliers/purchase-approvals/{oid}/approve',json=body);repeat=await request(c,'PUT',f'/suppliers/purchase-approvals/{oid}/approve',json=body);assert repeat['replayed'] and repeat['payable_bill_id']==result['payable_bill_id']
   await request(c,'PUT',f'/suppliers/purchase-approvals/{oid}/approve',json={**body,'request_key':'reuse-grant'},code=409)
   async with f() as db:assert (await db.get(ProcurementActionException,ident)).status=='used'
   other=await buy(c,p,q,101);oc=await context(c,other['order']['id'],'approve',4);accepted=await request(c,'PUT',f'/suppliers/purchase-approvals/{other["order"]["id"]}/approve',uid=4,json={'request_key':'other-approver',**controls(oc)});assert accepted['duty_operator_id']==4
   await setting(f,'purchase_approval_threshold',10000);auto=await buy(c,p,q,1);assert not auto['pending'] and auto['payable_bill_id']
   actual('approval',{'denied':denied,'grant':g,'approved':result,'repeat':repeat,'other':accepted,'auto':auto})
 asyncio.run(run())

def test_receipt_80_plus20_failure_not_consumed_and_original_replay(tmp_path,monkeypatch):
 async def run():
  import app.services.image_utils as images
  from fastapi import HTTPException
  async with fixture(tmp_path,monkeypatch) as (_,f,c,_):
   _,s,p,q,*_=await scenario(c,f);po=await buy(c,p,q,100);oid=po['order']['id'];await policy(c,False,True);ctx=await context(c,oid,'receive')
   await receive(c,ctx,po,80,'denied-self',code=403);g,_=await grant(c,ctx);ident=g['data']['id'];original=images.save_image
   def fail(*args,**kwargs):raise HTTPException(500,'synthetic photograph save failure')
   monkeypatch.setattr(images,'save_image',fail);await receive(c,ctx,po,80,'receive-once',ident,code=500);assert await num(f,PurchaseReceiptEvent)==0
   async with f() as db:assert (await db.get(ProcurementActionException,ident)).status=='active'
   monkeypatch.setattr(images,'save_image',original);a=await receive(c,ctx,po,80,'receive-once',ident);retry=await receive(c,ctx,po,80,'receive-once',ident);assert retry['replayed'] and retry['receipt_event_id']==a['receipt_event_id']
   other=await context(c,oid,'receive',4);b=await receive(c,other,po,20,'other20',uid=4);assert await num(f,PurchaseReceiptEvent)==2
   detail=await request(c,'GET',f'/suppliers/purchase-orders/{oid}');assert detail['items'][0]['received_quantity']==100 and detail['bill']['paid_amount']==0
   actual('receipt',{'grant':g,'first80':a,'retry':retry,'other20':b,'detail':detail})
 asyncio.run(run())

def test_exact_nonexecution_proof_allows_unknown_request_recovery_after_policy_toggle(tmp_path,monkeypatch):
 async def run():
  async with fixture(tmp_path,monkeypatch) as (_,f,c,_):
   _,s,p,q,*_=await scenario(c,f);po=await buy(c,p,q,100);oid=po['order']['id'];before=await context(c,oid,'receive')
   # Client lost response before delivery; owner turns on rules before retry arrives.
   await policy(c,False,True)
   failed=await receive(c,before,po,1,'not-delivered-before-toggle',code=403)
   detail=failed['detail'];assert detail['code']=='procurement_duty_changed' and detail['not_executed'] and detail['request_key']=='not-delivered-before-toggle'
   assert await num(f,PurchaseReceiptEvent)==0
   now=await context(c,oid,'receive');g,_=await grant(c,now)
   result=await receive(c,now,po,1,detail['request_key'],g['data']['id']);assert result['receipt_event_id'] and await num(f,PurchaseReceiptEvent)==1
   again=await receive(c,now,po,1,detail['request_key'],g['data']['id']);assert again['replayed'] and await num(f,PurchaseReceiptEvent)==1
 asyncio.run(run())

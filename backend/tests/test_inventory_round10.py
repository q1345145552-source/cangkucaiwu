"""Actual HTTP/SQL on disposable loopback PostgreSQL; never real stock or cash."""
import asyncio, json, os, uuid, copy
from pathlib import Path
from datetime import timedelta
from decimal import Decimal
import pytest
from sqlalchemy import select, func
from app.models import (InventoryAccount, InventoryMovement, InventoryReceiptLink, InventoryOperation,
                        InventoryPolicy, PurchaseReceiptEvent, PurchaseOrder, StandardSKU, User, ExpenseRecord,
                        PayablePayment, PaymentAccount, ProcurementDutyExecution)
from app.services import inventory as stock
from app.core.timezone import thai_now
from tests.test_procurement_risk_round8 import fixture, scenario, buy, product, request, counts
from tests.test_supplier_sku_round5 import sku
from tests.test_round2_permissions import auth, png
from tests.test_incoming_operations import URL
pytestmark = pytest.mark.skipif(not URL, reason='Explicit disposable localhost only')
ACTUAL={}
def actual(key, value):
    ACTUAL[key]=value
    if os.environ.get('SUPPLIER10_REPORT'):Path(os.environ['SUPPLIER10_REPORT']).write_text(json.dumps(ACTUAL,ensure_ascii=False,default=str,indent=2))
async def listing(c,**kw):return await request(c,'GET','/inventory',**kw)
async def detail(c,ident,**kw):return await request(c,'GET',f'/inventory/accounts/{ident}',**kw)
async def num(f,m):
    async with f() as db:return (await db.execute(select(func.count()).select_from(m))).scalar_one()
async def opening(c,s,amount='100',unit=None,uid=1,key=None,at=None,code=200,**patch):
    unit=unit or s['base_unit'];rows=(await request(c,'GET','/inventory/catalog',uid=uid))['data'];target=next(x for x in rows if x['id']==s['id'])['opening_target']
    if unit!=s['base_unit']:
        target=next(x for x in (await listing(c,uid=uid))['data'] if x['sku_id']==s['id'] and x['base_unit']==unit)
    body={'request_key':key or uuid.uuid4().hex,'sku_id':s['id'],'base_unit':unit,'opening_quantity':amount,
          'occurred_at':(at or thai_now()-timedelta(days=1)).isoformat(),'confirmed':True,'expected_version':target['version'],
          'change_reason':'合成测试实际核实期初，不由采购历史推算',**patch}
    return await request(c,'POST','/inventory/openings',uid=uid,code=code,json=body),body
async def receive(c,po,amount=80,key=None,code=200,uid=1):
    return await request(c,'POST',f'/suppliers/purchase-orders/{po["order"]["id"]}/receive',uid=uid,code=code,
        data={'request_key':key or uuid.uuid4().hex,'items':json.dumps([{'line_id':po['order']['items'][0]['line_id'],'received_quantity':amount}])},
        files={'file':('synthetic-stock.png',png(),'image/png')})
async def issue(c,account,amount='30',key=None,uid=1,code=200,**patch):
    body={'request_key':key or uuid.uuid4().hex,'issued_quantity':amount,'expected_version':account['version'],'purpose':'合成耗材领用',**patch}
    return await request(c,'POST',f'/inventory/accounts/{account["id"]}/issues',uid=uid,code=code,json=body),body
async def reverse(c,ident,account,key=None,uid=1,code=200):
    body={'request_key':key or uuid.uuid4().hex,'expected_version':account['version'],'reverse_reason':'合成错记，反向冲销并留原流水'}
    return await request(c,'POST',f'/inventory/movements/{ident}/reverse',uid=uid,code=code,json=body),body
async def returned(c,ident,account,amount='10',key=None,code=200):
    body={'request_key':key or uuid.uuid4().hex,'expected_version':account['version'],'returned_quantity':amount,'return_reason':'实际退回原领用的耗材，合成测试'}
    return await request(c,'POST',f'/inventory/movements/{ident}/returns',code=code,json=body),body

def test_100_plus_80_minus_30_is_150_and_no_cash_cost_or_old_data_change(tmp_path,monkeypatch):
    async def run():
        async with fixture(tmp_path,monkeypatch) as (_,f,c,_):
            _,s,p,q,*_=await scenario(c,f);po=await buy(c,p,q,100);before=await counts(f)
            opened,body=await opening(c,s);r=await receive(c,po,80,key='stock80');again=await receive(c,po,80,key='stock80');assert again['replayed']
            account=(await listing(c))['data'][0];assert account['available_quantity']=='180'
            out,outbody=await issue(c,account);assert out['account']['available_quantity']=='150'
            d=await detail(c,account['id']);assert [x['kind'] for x in d['data']]==['issue','receipt','opening']
            assert sum(Decimal(x['quantity']) for x in d['data'])==150 and all(x['cost_amount'] is None for x in d['data'])
            assert d['data'][1]['source_id']==r['receipt_event_id'] and d['data'][1]['source_line_id']==po['order']['items'][0]['line_id']
            assert await num(f,InventoryReceiptLink)==1 and await num(f,InventoryMovement)==3
            after=await counts(f);assert after=={**before,'purchase_receipt_events':before['purchase_receipt_events']+1}
            original=await request(c,'GET','/suppliers/purchase-orders/1');assert original['total_amount']==1000 and original['items'][0]['quantity']==10
            actual('100_80_30',{'opening':opened,'receipt':r,'receipt_retry':again,'issue':out,'journal':d,'business_counts_before':before,'after':after,'amounts_pending':True})
    asyncio.run(run())

def test_unknown_opening_is_not_zero_and_explicit_earlier_opening_only(tmp_path,monkeypatch):
    async def run():
        async with fixture(tmp_path,monkeypatch) as (_,f,c,_):
            _,s,p,q,*_=await scenario(c,f);po=await buy(c,p,q,100);await receive(c,po)
            account=(await listing(c))['data'][0];assert account['recorded_quantity']=='80' and account['available_quantity'] is None and not account['opening_confirmed']
            blocked,_=await issue(c,account,'1',code=400)
            await opening(c,s,at=thai_now(),code=400)
            opened,body=await opening(c,s);retry=await request(c,'POST','/inventory/openings',json=body);assert retry['replayed']
            await opening(c,s,code=409)
            issued,_=await issue(c,opened['account']);assert issued['account']['available_quantity']=='150'
            actual('unknown_opening',{'before':account,'blocked':blocked,'confirmed':opened,'issue':issued})
    asyncio.run(run())

def test_pending_unmapped_receipt_explicit_resolution_and_original_snapshot_unchanged(tmp_path,monkeypatch):
    async def run():
        async with fixture(tmp_path,monkeypatch) as (_,f,c,_):
            s=await sku(c);po=await request(c,'POST','/suppliers/1/purchase-order',json={'items':[{'product_id':1,'quantity':10}]})
            raw=copy.deepcopy(po['order']['items']);receipt=await receive(c,po,10,key='unmapped10');assert receipt['inventory']['pending_lines']==1
            assert not (await listing(c))['data'];pending=(await request(c,'GET','/inventory/pending-receipts'))['data'][0]
            body={'request_key':'explicit-map','sku_id':s['id'],'expected_sku_version':s['version'],'base_unit_factor':'2','expected_source_fingerprint':pending['source_fingerprint'],'confirmation_reason':'老板按包装实物核实每件等于2个基本单位，合成证据'}
            resolved=await request(c,'POST',f'/inventory/pending-receipts/{pending["id"]}/resolve',json=body);assert resolved['account']['recorded_quantity']=='20' and resolved['account']['available_quantity'] is None
            assert (await request(c,'POST',f'/inventory/pending-receipts/{pending["id"]}/resolve',json=body))['replayed']
            await request(c,'POST',f'/inventory/pending-receipts/{pending["id"]}/resolve',json={**body,'request_key':'another-map'},code=409)
            assert await num(f,InventoryMovement)==1
            async with f() as db:
                original=(await db.get(PurchaseOrder,po['order']['id'])).items
                assert all({k:v for k,v in x.items() if k not in ('received_quantity','diff_quantity','line_id_source','historical_received_quantity','batch_received_quantity','remaining_quantity','over_quantity','quantity_status','unit_status')}=={k:v for k,v in y.items() if k not in ('received_quantity','diff_quantity','line_id_source','historical_received_quantity','batch_received_quantity','remaining_quantity','over_quantity','quantity_status','unit_status')} for x,y in zip(original,raw))
            actual('pending_resolution',{'receipt':receipt,'pending':pending,'resolved':resolved})
    asyncio.run(run())

def test_concurrent_issues_cannot_make_negative_and_original_replay_is_one_row(tmp_path,monkeypatch):
    async def run():
        async with fixture(tmp_path,monkeypatch) as (_,f,c,_):
            s=await sku(c);opened,_=await opening(c,s);account=opened['account']
            bodies=[{'request_key':'issue-race-'+str(i),'issued_quantity':'80','expected_version':account['version'],'purpose':'并发合成领用'} for i in range(2)]
            path=f'/api/v1/inventory/accounts/{account["id"]}/issues';rs=await asyncio.gather(*[c.post(path,headers=auth(1),json=b) for b in bodies]);assert sorted(r.status_code for r in rs)==[200,409]
            win=next(i for i,r in enumerate(rs) if r.status_code==200);again=await c.post(path,headers=auth(1),json=bodies[win]);assert again.status_code==200 and again.json()['replayed']
            assert await num(f,InventoryMovement)==2
            now=(await detail(c,account['id']))['account'];assert now['available_quantity']=='20';await issue(c,now,'21',code=400)
            await request(c,'POST',f'/inventory/accounts/{account["id"]}/issues',json={**bodies[win],'issued_quantity':'1'},code=409)
            actual('concurrent_issues',{'responses':[{'status':r.status_code,'body':r.json()} for r in rs],'replay':again.json(),'current':now})
    asyncio.run(run())

def test_concurrent_same_receipt_only_one_inbound_and_no_legacy_backfill(tmp_path,monkeypatch):
    async def run():
        from app.services.inventory_migration import MODELS,migrate_inventory
        async with fixture(tmp_path,monkeypatch) as (engine,f,c,_):
            _,s,p,q,*_=await scenario(c,f);po=await buy(c,p,q,100)
            async def send():return await receive(c,po,80,key='same-physical-batch')
            a,b=await asyncio.gather(send(),send());assert a['receipt_event_id']==b['receipt_event_id']
            assert await num(f,InventoryMovement)==await num(f,InventoryReceiptLink)==1
            async with f() as db:
                x=(await db.execute(select(ProcurementDutyExecution).where(ProcurementDutyExecution.action=='receive'))).scalar_one();saved=dict(x.response);saved.pop('inventory',None);x.response=saved;await db.commit()
            old_events=await num(f,PurchaseReceiptEvent)
            async with engine.begin() as conn:
                for m in reversed(MODELS):await conn.run_sync(lambda c,m=m:m.__table__.drop(c,checkfirst=True))
                await migrate_inventory(conn);await migrate_inventory(conn)
            assert not (await listing(c))['data'];again=await send();assert again['replayed']
            assert await num(f,InventoryMovement)==await num(f,InventoryReceiptLink)==0 and await num(f,PurchaseReceiptEvent)==old_events
            actual('receipt_idempotency_upgrade',{'a':a,'b':b,'legacy_retry':again,'legacy_stock_backfill_count':0})
    asyncio.run(run())

def test_returns_and_reversals_append_history_and_cannot_double_restore(tmp_path,monkeypatch):
    async def run():
        async with fixture(tmp_path,monkeypatch) as (_,f,c,_):
            s=await sku(c);o,_=await opening(c,s);i,_=await issue(c,o['account']);mid=i['movement_id']
            r,_=await returned(c,mid,i['account']);assert r['account']['available_quantity']=='80'
            await returned(c,mid,r['account'],'21',code=400);await reverse(c,mid,r['account'],code=400)
            rv,_=await reverse(c,r['movement_id'],r['account']);assert rv['account']['available_quantity']=='70'
            r2,_=await returned(c,mid,rv['account'],'30');assert r2['account']['available_quantity']=='100'
            rv2,_=await reverse(c,r2['movement_id'],r2['account']);final,body=await reverse(c,mid,rv2['account']);assert final['account']['available_quantity']=='100'
            assert (await request(c,'POST',f'/inventory/movements/{mid}/reverse',json=body))['replayed']
            await reverse(c,mid,final['account'],code=400);await reverse(c,o['movement_id'],final['account'],code=400);await reverse(c,final['movement_id'],final['account'],code=400)
            d=await detail(c,o['account']['id']);assert sum(Decimal(x['quantity']) for x in d['data'])==100 and len(d['data'])==7
            assert next(x for x in d['data'] if x['id']==mid)['status']=='reversed'
            actual('returns_reversals',d)
    asyncio.run(run())

def test_reverse_receipt_checks_available_stock_and_old_receipt_cannot_reapply(tmp_path,monkeypatch):
    async def run():
        async with fixture(tmp_path,monkeypatch) as (_,f,c,_):
            _,s,p,q,*_=await scenario(c,f);o,_=await opening(c,s,'0');po=await buy(c,p,q,100);r=await receive(c,po,80,key='inbound80')
            d=await detail(c,o['account']['id']);inbound=next(x for x in d['data'] if x['kind']=='receipt');issued,_=await issue(c,d['account'],'70')
            await reverse(c,inbound['id'],issued['account'],code=400)
            rt,_=await returned(c,issued['movement_id'],issued['account'],'70');rev,body=await reverse(c,inbound['id'],rt['account']);assert rev['account']['available_quantity']=='0'
            again=await receive(c,po,80,key='inbound80');assert again['replayed']
            assert (await detail(c,o['account']['id']))['account']['available_quantity']=='0'
            async with f() as db:assert (await db.get(PurchaseReceiptEvent,r['receipt_event_id'])).status=='active'
            actual('reverse_inbound',{'before_reverse':rt,'reverse':rev,'receipt_retry':again,'current':await detail(c,o['account']['id'])})
    asyncio.run(run())

def test_receipt_and_manual_failure_roll_back_whole_transaction(tmp_path,monkeypatch):
    from fastapi import HTTPException
    async def run():
        async with fixture(tmp_path,monkeypatch) as (_,f,c,_):
            _,s,p,q,*_=await scenario(c,f);po=await buy(c,p,q,100);original=stock.record_receipt
            async def fail(*a,**k):await original(*a,**k);raise HTTPException(500,'合成入库后事务失败')
            monkeypatch.setattr(stock,'record_receipt',fail);await receive(c,po,key='failed-inbound',code=500)
            assert await num(f,InventoryMovement)==await num(f,InventoryReceiptLink)==await num(f,InventoryAccount)==await num(f,PurchaseReceiptEvent)==0
            monkeypatch.setattr(stock,'record_receipt',original);r=await receive(c,po,key='failed-inbound');assert r['inventory']['recorded_lines']==1
            o,_=await opening(c,s);finish=stock.finish
            async def fail_finish(*a,**k):await finish(*a,**k);raise HTTPException(500,'合成领用落库后失败')
            monkeypatch.setattr(stock,'finish',fail_finish);await issue(c,o['account'],key='failed-issue',code=500)
            assert (await detail(c,o['account']['id']))['account']['available_quantity']=='180'
            monkeypatch.setattr(stock,'finish',finish);i,_=await issue(c,o['account'],key='failed-issue');assert i['account']['available_quantity']=='150'
            actual('atomic_failures',{'receipt_retry':r,'issue_retry':i,'movement_count':await num(f,InventoryMovement)})
    asyncio.run(run())

def test_units_frozen_receipt_mapping_and_warehouses_do_not_mix(tmp_path,monkeypatch):
    async def run():
        async with fixture(tmp_path,monkeypatch) as (_,f,c,_):
            _,s,p,q,*_=await scenario(c,f);po=await buy(c,p,q,100);opened,_=await opening(c,s)
            fresh=(await request(c,'GET','/sku-catalog'))['data'][0]
            updated=await request(c,'PUT',f'/sku-catalog/{s["id"]}',json={**{k:fresh[k] for k in ('code','name','attributes','category_id','active')},'base_unit':'box','expected_version':fresh['version']})
            box,_=await opening(c,updated,'5');await receive(c,po,80)
            rows=(await listing(c))['data'];assert {x['base_unit']:x['available_quantity'] for x in rows}=={'piece':'180','box':'5'}
            async with f() as db:
                receipt=(await db.execute(select(InventoryMovement).where(InventoryMovement.kind=='receipt'))).scalar_one();assert receipt.source_snapshot['base_unit']=='piece' and receipt.source_snapshot['base_unit_factor']=='1'
            await request(c,'GET',f'/inventory/accounts/{opened["account"]["id"]}',uid=7,warehouse='2',code=403)
            await request(c,'GET','/inventory',uid=7,warehouse='2',params={'sku_id':s['id']},code=403)
            assert (await request(c,'GET','/inventory',uid=7,warehouse='2'))['data']==[]
            second=await request(c,'POST','/sku-catalog',uid=7,warehouse='2',json={'code':s['code'],'name':'外仓同编码','attributes':{'material':'PE'},'base_unit':'piece'})
            target=(await request(c,'GET','/inventory/catalog',uid=7,warehouse='2'))['data'][0]['opening_target']
            await request(c,'POST','/inventory/openings',uid=7,warehouse='2',json={'request_key':'outside-opening','sku_id':second['id'],'base_unit':'piece','opening_quantity':'999','expected_version':target['version'],'occurred_at':(thai_now()-timedelta(days=1)).isoformat(),'confirmed':True,'change_reason':'外仓独立真实期初合成验证'})
            assert {x['base_unit']:x['available_quantity'] for x in (await listing(c))['data']}=={'piece':'180','box':'5'}
            await request(c,'GET','/inventory',warehouse='all',code=400)
            actual('units_warehouse',{'original_frozen_receipt':receipt.source_snapshot,'own_accounts':rows,'other_sku':second,'no_mixed_total':True})
    asyncio.run(run())

def test_permission_registry_owner_actions_and_all_labor_routes_denied(tmp_path,monkeypatch):
    from app.core.menu_registry import MENU_PERMISSIONS_BY_KEY,STAFF_PERMISSIONS
    async def run():
        async with fixture(tmp_path,monkeypatch) as (_,f,c,_):
            s=await sku(c);o,ob=await opening(c,s);aid=o['account']['id'];i,ib=await issue(c,o['account'],'10')
            await request(c,'GET','/inventory',uid=3,code=403)
            async with f() as db:
                for uid in (2,3,4,5):(await db.get(User,uid)).extra_permissions=list(set((await db.get(User,uid)).extra_permissions or [])|{'耗材库存'})
                await db.commit()
            for uid in (3,4):
                assert (await listing(c,uid=uid))['total']==1
                await request(c,'POST','/inventory/openings',uid=uid,json={**ob,'request_key':'denied-opening-'+str(uid)},code=403)
                pv=await request(c,'GET','/inventory/policy',uid=uid)
                await request(c,'PUT','/inventory/policy',uid=uid,json={'request_key':'denied-policy'+str(uid),'valuation_method':'quantity_only','expected_version':pv['version'],'change_reason':'不能越权配置'},code=403)
                await request(c,'POST',f'/inventory/movements/{i["movement_id"]}/reverse',uid=uid,json={'request_key':'denied-reverse'+str(uid),'expected_version':i['account']['version'],'reverse_reason':'不能越权冲销'},code=403)
            real,_=await issue(c,i['account'],'1',uid=3);assert real['account']['available_quantity']=='89'
            denied=[]
            endpoints=[('GET','/inventory',None),('GET','/inventory/catalog',None),('GET','/inventory/policy',None),('PUT','/inventory/policy',{'request_key':'x','valuation_method':'quantity_only','expected_version':'a'*64,'change_reason':'测试'}),('POST','/inventory/openings',ob),('GET','/inventory/pending-receipts',None),('POST','/inventory/pending-receipts/1/resolve',{'request_key':'x','sku_id':s['id'],'expected_sku_version':s['version'],'base_unit_factor':'1','expected_source_fingerprint':'a'*64,'confirmation_reason':'测试'}),('GET',f'/inventory/accounts/{aid}',None),('POST',f'/inventory/accounts/{aid}/issues',ib),('POST',f'/inventory/movements/{i["movement_id"]}/returns',{'request_key':'x','returned_quantity':'1','expected_version':'a'*64,'return_reason':'测试'}),('POST',f'/inventory/movements/{i["movement_id"]}/reverse',{'request_key':'x','expected_version':'a'*64,'reverse_reason':'测试'})]
            for uid in (2,5):
                for method,path,body in endpoints:
                    denied.append({'uid':uid,'method':method,'path':path,'return':await request(c,method,path,uid=uid,code=403,**({'json':body} if body else {}))})
            item=MENU_PERMISSIONS_BY_KEY['inventory'].as_dict();assert item['label']=='耗材库存' and item['selectable'] and item['default_roles']==['warehouse_admin'] and len(STAFF_PERMISSIONS)==8
            actual('roles',{'denied':denied,'menu':item,'permitted_staff_issue':real})
    asyncio.run(run())

def test_quantity_precision_and_explicit_quantity_policy_no_false_zero_cost(tmp_path,monkeypatch):
    async def run():
        async with fixture(tmp_path,monkeypatch) as (_,f,c,_):
            s=await sku(c);o,_=await opening(c,s,'100.12345678');a=o['account'];assert a['available_quantity']=='100.12345678'
            for value in ('-1','0','NaN','1e3','1.000000001','10000000000000000'):
                await issue(c,a,value,code=400)
            good,_=await issue(c,a,'0.12345678');assert good['account']['available_quantity']=='100'
            old=await request(c,'GET','/inventory/policy');assert old['valuation_method']=='unconfigured' and old['amount'] is None
            body={'request_key':'explicit-quantity-only','valuation_method':'quantity_only','expected_version':old['version'],'change_reason':'未选FIFO或均价，仅确认本阶段数量台账'}
            saved=await request(c,'PUT','/inventory/policy',json=body);again=await request(c,'PUT','/inventory/policy',json=body);assert again['replayed'] and saved['policy']['amount'] is None
            await request(c,'PUT','/inventory/policy',json={**body,'request_key':'stale-policy'},code=409)
            await request(c,'PUT','/inventory/policy',json={**body,'valuation_method':'fifo','request_key':'unsupported'},code=422)
            d=await detail(c,a['id']);assert all(x['cost_amount'] is None and x['cost_currency'] is None for x in d['data'])
            actual('precision_policy',{'issue':good,'policy':saved,'repeat':again,'journal':d})
    asyncio.run(run())

def test_resolving_older_pending_receipt_cannot_double_add_to_later_opening(tmp_path,monkeypatch):
    async def run():
        async with fixture(tmp_path,monkeypatch) as (_,f,c,_):
            s=await sku(c);po=await request(c,'POST','/suppliers/1/purchase-order',json={'items':[{'product_id':1,'quantity':10}]});await receive(c,po,10)
            pending=(await request(c,'GET','/inventory/pending-receipts'))['data'][0]
            # Owner independently counted a later real opening; do not guess that the earlier receipt is extra.
            o,_=await opening(c,s,'100',at=thai_now()-timedelta(milliseconds=1))
            body={'request_key':'older-than-baseline','sku_id':s['id'],'expected_sku_version':s['version'],'base_unit_factor':'1','expected_source_fingerprint':pending['source_fingerprint'],'confirmation_reason':'明确核查旧收货是否已包含在期初'}
            rejected=await request(c,'POST',f'/inventory/pending-receipts/{pending["id"]}/resolve',json=body,code=409)
            assert (await detail(c,o['account']['id']))['account']['available_quantity']=='100' and (await request(c,'GET','/inventory/pending-receipts'))['total']==1
            actual('pending_before_opening',{'rejection':rejected,'unchanged':await detail(c,o['account']['id'])})
    asyncio.run(run())

def test_pending_target_sku_version_change_cannot_silently_change_unit(tmp_path,monkeypatch):
    async def run():
        async with fixture(tmp_path,monkeypatch) as (_,f,c,_):
            s=await sku(c);po=await request(c,'POST','/suppliers/1/purchase-order',json={'items':[{'product_id':1,'quantity':10}]});await receive(c,po,10)
            pending=(await request(c,'GET','/inventory/pending-receipts'))['data'][0]
            body={'request_key':'stale-target-sku','sku_id':s['id'],'expected_sku_version':s['version'],'base_unit_factor':'1','expected_source_fingerprint':pending['source_fingerprint'],'confirmation_reason':'按选择时的基本单位核实，不能静默改成后来版本'}
            updated=await request(c,'PUT',f'/sku-catalog/{s["id"]}',json={**{k:s[k] for k in ('code','name','attributes','category_id','active')},'base_unit':'box','expected_version':s['version']})
            blocked=await request(c,'POST',f'/inventory/pending-receipts/{pending["id"]}/resolve',json=body,code=409)
            assert blocked['detail']['not_executed'] and await num(f,InventoryMovement)==0
            accepted=await request(c,'POST',f'/inventory/pending-receipts/{pending["id"]}/resolve',json={**body,'expected_sku_version':updated['version']});assert accepted['account']['base_unit']=='box'
            actual('target_version',{'rejected':blocked,'explicit_new_target':accepted})
    asyncio.run(run())

def test_inconsistent_frozen_factor_is_pending_not_guessed_or_blocking_original_receipt(tmp_path,monkeypatch):
    async def run():
        async with fixture(tmp_path,monkeypatch) as (_,f,c,_):
            _,s,p,q,*_=await scenario(c,f);po=await buy(c,p,q,100)
            async with f() as db:
                row=await db.get(PurchaseOrder,po['order']['id']);items=copy.deepcopy(row.items);items[0]['sku_mapping']['base_unit_factor']='2';row.items=items;await db.commit()
            result=await receive(c,po,80);assert result['inventory']['pending_lines']==1 and await num(f,InventoryMovement)==0
            pending=(await request(c,'GET','/inventory/pending-receipts'))['data'][0];assert '不一致' in pending['pending_reason']
            assert (await request(c,'GET',f'/suppliers/purchase-orders/{po["order"]["id"]}'))['items'][0]['received_quantity']==80
            actual('bad_frozen_factor',{'receipt_still_recorded':result,'pending':pending,'stock_not_guessed':True})
    asyncio.run(run())

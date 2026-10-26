"""Only explicit localhost PostgreSQL and disposable schemas; no real orders or funds."""
import asyncio,json,os,uuid
from contextlib import asynccontextmanager
from pathlib import Path
import pytest
from sqlalchemy import select,func,text
from fastapi import HTTPException
from app.models import PurchaseOrder,PayableBill,PurchaseReceiptEvent,DataChangeHistory,SystemSetting
from app.models.supplier import SupplierProduct
from app.services import purchase_matching as match
from app.services.purchase_receipt_migration import migrate_purchase_receipts
from tests.test_supplier_workflow_round1 import setup,request
from tests.test_round2_permissions import png,auth
from tests.test_incoming_operations import URL

pytestmark=pytest.mark.skipif(not URL,reason='Explicit isolated localhost PostgreSQL required')
ACTUAL={}
def actual(name,data):
    ACTUAL[name]=data
    if os.environ.get('SUPPLIER03_REPORT'):Path(os.environ['SUPPLIER03_REPORT']).write_text(json.dumps(ACTUAL,ensure_ascii=False,indent=2,default=str))

@asynccontextmanager
async def fixture(tmp_path,mp):
    mp.setenv('UPLOAD_DIR',str(tmp_path/'uploads'))
    import app.services.image_utils as images
    original=images.save_image
    mp.setattr(images,'save_image',lambda content,folder,prefix,name:original(content,
        str(tmp_path/'uploads'/'legacy-save'/Path(folder).name) if folder.startswith('/app/') else folder,prefix,name))
    async with setup(tmp_path,mp) as result:
        async with result[1]() as db:
            product=await db.get(SupplierProduct,1);product.unit_price=10;product.unit='件';await db.commit()
        yield result

async def order(c,quantity=100,items=None):
    payload={'request_key':uuid.uuid4().hex,'items':items or [{'product_id':1,'quantity':quantity}]}
    r=await c.post('/api/v1/suppliers/1/purchase-order',headers={**auth(1),'X-Warehouse-ID':'1'},json=payload)
    if r.status_code==409 and r.json()['detail'].get('candidates'):
        payload['duplicate_confirmation']={'candidate_ids':[it['id'] for it in r.json()['detail']['candidates']],'reason':'隔离测试不同采购批次'}
        r=await c.post('/api/v1/suppliers/1/purchase-order',headers={**auth(1),'X-Warehouse-ID':'1'},json=payload)
    assert r.status_code==200,r.text
    poid=r.json()['order']['id']
    return await request(c,'GET',f'/suppliers/purchase-orders/{poid}')

async def receive(c,po,quantities,key=None,code=200,uid=1,warehouse='1',photo=None,remark='隔离测试收货'):
    rows=quantities if isinstance(quantities,list) else [{'line_id':po['items'][0]['line_id'],'received_quantity':quantities}]
    return await request(c,'POST',f'/suppliers/purchase-orders/{po["id"]}/receive',uid=uid,warehouse=warehouse,code=code,
        data={'items':json.dumps(rows),'request_key':key or uuid.uuid4().hex,'remark':remark},
        files={'file':('receipt.png',photo if photo is not None else png(),'image/png')})

async def detail(c,po):return await request(c,'GET',f'/suppliers/purchase-orders/{po["id"]}')
async def review(c,bid,reason='核实本次匹配依据及差异'):
    return await request(c,'PUT',f'/payable/{bid}/confirm',json={'reason':reason})

def test_100_80_20_batches_photos_and_review_invalidation(tmp_path,monkeypatch):
    async def run():
        async with fixture(tmp_path,monkeypatch) as (_,f,c):
            po=await order(c);bid=po['bill']['id'];lid=po['items'][0]['line_id']
            first=await receive(c,po,80);after80=await detail(c,po)
            assert after80['items'][0]['received_quantity']==80 and after80['items'][0]['remaining_quantity']==20
            assert after80['bill']['need_boss_confirm']=='true' and after80['matching']['status']=='different'
            await request(c,'PUT',f'/payable/{bid}/confirm',code=400,json={})
            reviewed=await review(c,bid);assert reviewed['review']['snapshot']['purchase']['events'][0]['id']==first['id']
            assert (await detail(c,po))['matching']['review_valid']
            second=await receive(c,po,20);after100=await detail(c,po)
            assert after100['items'][0]['received_quantity']==100 and after100['items'][0]['diff_quantity']==0
            assert after100['receipt_status']=='received' and after100['matching']['status']=='matched'
            assert after100['matching']['review_status']=='stale' and after100['bill']['need_boss_confirm']=='true'
            assert [r['items'][0]['quantity'] for r in after100['receipt_batches']]==[80,20]
            assert first['photo_path']!=second['photo_path']
            for event in after100['receipt_batches']:
                response=await c.get(f'/api/v1/suppliers/purchase-orders/{po["id"]}/receipts/{event["id"]}/photo',headers={**auth(1),'X-Warehouse-ID':'1'})
                assert response.status_code==200 and response.content
            await review(c,bid,'补收完成，重新核实100件')
            await review(c,bid,'补收完成，重新核实100件')
            final=await detail(c,po);assert final['matching']['review_valid'] and final['bill']['need_boss_confirm']=='false'
            async with f() as db:
                assert (await db.execute(select(func.count(DataChangeHistory.id)).where(DataChangeHistory.operation_type=='match_confirm'))).scalar_one()==2
                assert (await db.get(PurchaseOrder,po['id'])).receipt_baseline['lines'][0]['quantity']==0
            actual('100_80_20',{'after80':after80,'after100':after100,'final':final,'line_id_unchanged':lid==final['items'][0]['line_id']})
    asyncio.run(run())

def test_request_idempotency_concurrency_and_db_unique(tmp_path,monkeypatch):
    async def run():
        async with fixture(tmp_path,monkeypatch) as (_,f,c):
            po=await order(c)
            pair=await asyncio.gather(*[receive(c,po,30,key='same-receipt') for _ in range(2)])
            assert pair[0]['id']==pair[1]['id']
            mismatch=await receive(c,po,31,key='same-receipt',code=409)
            different=await asyncio.gather(receive(c,po,20,key='second'),receive(c,po,50,key='third'))
            final=await detail(c,po)
            assert final['items'][0]['received_quantity']==100 and len(final['receipt_batches'])==3
            async with f() as db:
                from sqlalchemy.exc import IntegrityError
                old=await db.get(PurchaseReceiptEvent,pair[0]['id'])
                with pytest.raises(IntegrityError):
                    async with db.begin_nested():
                        db.add(PurchaseReceiptEvent(warehouse_id=1,purchase_order_id=po['id'],request_key='same-receipt',
                            request_fingerprint='bad',items=[],photo_path='bad',operator_id=1,operator_name='合成',source='test',status='active'))
                        await db.flush()
            actual('concurrency',{'same_request':pair,'different_requests':different,'mismatch':mismatch,'final':final})
    asyncio.run(run())

def test_duplicate_names_stay_distinct_and_bad_quantities_rejected(tmp_path,monkeypatch):
    async def run():
        async with fixture(tmp_path,monkeypatch) as (_,f,c):
            po=await order(c,items=[{'product_id':1,'quantity':100},{'product_id':1,'quantity':50}]);a,b=[i['line_id'] for i in po['items']]
            assert a!=b
            for invalid in [0,-1,1.5,True,2147483648]:
                denied=await c.post('/api/v1/suppliers/1/purchase-order',headers={**auth(1),'X-Warehouse-ID':'1'},
                    json={'request_key':uuid.uuid4().hex,'items':[{'product_id':1,'quantity':invalid}]})
                assert denied.status_code==422,denied.text
            errors=[]
            for q in [-1,1.2,True,'2',None,float('inf')]:
                r=await receive(c,po,[{'line_id':a,'received_quantity':q}],code=400);errors.append({'input':str(q),'body':r})
            for rows in [[{'line_id':a,'received_quantity':1},{'line_id':a,'received_quantity':2}],
                         [{'line_id':'foreign:42','received_quantity':1}],
                         [{'product_name':po['items'][0]['product_name'],'received_quantity':1}],
                         [{'line_id':a,'received_quantity':0}]]:
                await receive(c,po,rows,code=400)
            await receive(c,po,[{'line_id':a,'received_quantity':80},{'line_id':b,'received_quantity':15}])
            after=await detail(c,po);assert [i['received_quantity'] for i in after['items']]==[80,15]
            async with f() as db:assert (await db.execute(select(func.count(PurchaseReceiptEvent.id)))).scalar_one()==1
            actual('distinct_lines_invalid',{'errors':errors,'after':after})
    asyncio.run(run())

def test_photo_failure_rolls_back_and_same_request_recovers(tmp_path,monkeypatch):
    async def run():
        import app.services.image_utils as images
        async with fixture(tmp_path,monkeypatch) as (_,f,c):
            po=await order(c);original=images.save_image
            def fail(*a,**kw):raise HTTPException(500,'isolated receipt photo failure')
            monkeypatch.setattr(images,'save_image',fail)
            error=await receive(c,po,80,key='photo-retry',code=500)
            async with f() as db:
                assert (await db.execute(select(func.count(PurchaseReceiptEvent.id)))).scalar_one()==0
                saved=await db.get(PurchaseOrder,po['id']);assert saved.receipt_status=='not_received' and saved.items[0].get('received_quantity') is None
            monkeypatch.setattr(images,'save_image',original)
            retried=await receive(c,po,80,key='photo-retry');again=await receive(c,po,80,key='photo-retry')
            assert retried['id']==again['id'] and (await detail(c,po))['items'][0]['received_quantity']==80
            actual('photo_rollback',{'error':error,'retry':retried,'same_event':again})
    asyncio.run(run())

def test_legacy_base_paid_history_and_unknown_matching_remain_honest(tmp_path,monkeypatch):
    async def run():
        async with fixture(tmp_path,monkeypatch) as (_,f,c):
            async with f() as db:
                po=await db.get(PurchaseOrder,1);po.items=[{'product_name':'旧耗材','quantity':10,'received_quantity':5,'diff_quantity':5}]
                po.receipt_status='partially_received';po.arrival_photo='/uploads/old-evidence.png'
                bill=await db.get(PayableBill,1);bill.paid_amount=300;bill.status='partially_paid';await db.commit()
            before=await request(c,'GET','/suppliers/purchase-orders/1')
            assert before['receipt_batches']==[] and before['items'][0]['received_quantity']==5
            assert before['matching']['quantity_match']=='unknown' and before['matching']['payment_cap'] is None
            await receive(c,before,3)
            await receive(c,before,2)
            after=await detail(c,before)
            assert after['items'][0]['received_quantity']==10 and after['receipt_baseline']['lines'][0]['quantity']==5
            assert after['receipt_baseline']['photo_path']=='/uploads/old-evidence.png'
            assert after['bill']['paid_amount']==300 and after['bill']['remaining_amount']==700
            assert after['matching']['quantity_match']=='unknown'
            actual('legacy',{'before':before,'after':after,'historical_payments_unchanged':True})
    asyncio.run(run())

def test_overreceipt_matching_and_financial_edits_expire_review(tmp_path,monkeypatch):
    async def run():
        async with fixture(tmp_path,monkeypatch) as (_,f,c):
            po=await order(c);bid=po['bill']['id']
            await receive(c,po,110);over=await detail(c,po)
            assert over['items'][0]['over_quantity']==10 and over['matching']['receipt_quantity_match']=='different'
            await review(c,bid)
            await request(c,'PUT',f'/payable/{bid}',json={'amount':1001})
            changed=await detail(c,po)
            assert changed['matching']['amount_match']=='different' and changed['matching']['review_status']=='stale'
            assert changed['bill']['need_boss_confirm']=='true'
            actual('over_and_edit',{'over':over,'changed':changed})
    asyncio.run(run())

def test_strict_default_compatible_and_enabled_received_cap(tmp_path,monkeypatch):
    async def run():
        async with fixture(tmp_path,monkeypatch) as (_,f,c):
            po=await order(c);bid=po['bill']['id']
            cfg=await request(c,'GET','/suppliers/purchase-match-policy');assert not cfg['strict']
            await request(c,'PUT',f'/payable/{bid}/pay',params={'paid_amount':100,'account_id':1,'request_key':'default-before-receipt'})
            await request(c,'PUT','/suppliers/purchase-match-policy',json={'strict':True})
            await receive(c,po,80);await review(c,bid)
            blocked=await request(c,'PUT',f'/payable/{bid}/pay',code=400,params={'paid_amount':701,'account_id':1,'request_key':'over-cap'})
            assert '不能超过已记录实收金额' in blocked['detail']
            paid=await request(c,'PUT',f'/payable/{bid}/pay',params={'paid_amount':700,'account_id':1,'request_key':'up-to-cap'})
            await receive(c,po,20)
            await request(c,'PUT',f'/payable/{bid}/pay',code=400,params={'paid_amount':200,'account_id':1,'request_key':'stale-review'})
            await review(c,bid);await request(c,'PUT',f'/payable/{bid}/pay',params={'paid_amount':200,'account_id':1,'request_key':'finish-after-review'})
            final=await detail(c,po);assert final['bill']['paid_amount']==1000 and final['matching']['review_valid']
            actual('strict',{'default':cfg,'blocked':blocked,'partial_payment':paid,'final':final})
    asyncio.run(run())

def test_unlinked_prepayment_non_goods_and_unknown_are_distinct(tmp_path,monkeypatch):
    async def run():
        from tests.test_supplier_dedup_round2 import create,form
        async with fixture(tmp_path,monkeypatch) as (_,f,c):
            await request(c,'PUT','/suppliers/purchase-match-policy',json={'strict':True})
            results=[]
            for i,k in enumerate(['prepayment','non_goods','unknown']):
                result=await create(c,form(bill_number=f'KIND-{k}',amount=str(51+i),matching_kind=k))
                b=await request(c,'GET',f'/payable/{result["id"]}/detail')
                assert b['matching']['quantity_match']==('unknown' if k=='unknown' else 'not_applicable')
                await request(c,'PUT',f'/payable/{result["id"]}/pay',code=400 if k=='unknown' else 200,
                    params={'paid_amount':1,'account_id':1,'request_key':f'kind-{k}'})
                results.append(b)
            actual('document_kinds',results)
    asyncio.run(run())

def test_permissions_scope_redaction_and_policy_management(tmp_path,monkeypatch):
    async def run():
        async with fixture(tmp_path,monkeypatch) as (_,f,c):
            po=await order(c);await receive(c,po,80,uid=9)
            supplier_only=await request(c,'GET',f'/suppliers/purchase-orders/{po["id"]}',uid=9)
            assert supplier_only['bill'] is None and supplier_only['matching'] is None and supplier_only['receipt_batches']
            for uid in [2,4,5,8]:await receive(c,po,1,uid=uid,code=403)
            await receive(c,po,1,warehouse='2',code=403)
            for uid in [3,9]:await request(c,'PUT',f'/payable/{po["bill"]["id"]}/confirm',uid=uid,code=403,json={'reason':'forbidden'})
            for uid in [2,3,4,5,9]:await request(c,'PUT','/suppliers/purchase-match-policy',uid=uid,code=403,json={'strict':True})
            # A granted supervisor can manage only the selected warehouse configuration.
            from app.models import User
            async with f() as db:
                (await db.get(User,9)).extra_permissions=['供应商管理','配置中心'];await db.commit()
            await request(c,'PUT','/suppliers/purchase-match-policy',uid=9,json={'strict':True})
            assert (await request(c,'GET','/suppliers/purchase-match-policy',warehouse='2'))['strict'] is False
            actual('permissions',{'supplier_only':supplier_only,'denied_labor_super_foreign_and_ungranted':True})
    asyncio.run(run())

@pytest.mark.parametrize('old_received',[False,True])
def test_new_old_repeat_migration_no_fabricated_history(tmp_path,monkeypatch,old_received):
    async def run():
        async with fixture(tmp_path,monkeypatch) as (engine,f,c):
            async with engine.begin() as conn:
                if old_received:await conn.execute(text('UPDATE purchase_orders SET items=CAST(:items AS JSON) WHERE id=1'),
                    {'items':json.dumps([{'product_name':'旧行','quantity':10,'received_quantity':5}])})
                before=(await conn.execute(text('SELECT id,items,arrival_photo,total_amount FROM purchase_orders ORDER BY id'))).all()
                # Emulate the pre-receipt schema, so later inventory FK tables must not exist yet.
                from app.services.inventory_migration import MODELS, migrate_inventory
                for model in reversed(MODELS):
                    await conn.run_sync(lambda c,m=model:m.__table__.drop(c,checkfirst=True))
                await conn.execute(text('DROP TABLE purchase_receipt_events'))
                for table,cols in [('purchase_orders',['receipt_baseline']),('payable_bills',['matching_kind','match_lines','match_review'])]:
                    for col in cols:await conn.execute(text(f'ALTER TABLE {table} DROP COLUMN {col}'))
                await migrate_purchase_receipts(conn);await migrate_purchase_receipts(conn)
                await migrate_inventory(conn)
                for model in MODELS:
                    assert (await conn.execute(text(f'SELECT count(*) FROM {model.__tablename__}'))).scalar_one()==0
                assert before==(await conn.execute(text('SELECT id,items,arrival_photo,total_amount FROM purchase_orders ORDER BY id'))).all()
                assert (await conn.execute(text('SELECT count(*) FROM purchase_receipt_events'))).scalar_one()==0
                assert (await conn.execute(text('SELECT receipt_baseline FROM purchase_orders WHERE id=1'))).scalar_one() is None
            original=await request(c,'GET','/suppliers/purchase-orders/1')
            assert original['receipt_batches']==[]
            actual(f'migration_{old_received}',{'original':original,'no_fabricated_events':True,'repeat_ok':True})
    asyncio.run(run())


def test_payment_and_receipt_are_serialized_without_changing_paid_history(tmp_path,monkeypatch):
    async def run():
        async with fixture(tmp_path,monkeypatch) as (_,f,c):
            po=await order(c);bid=po['bill']['id'];await receive(c,po,80);await review(c,bid)
            async def pay():
                return await c.put(f'/api/v1/payable/{bid}/pay',headers={**auth(1),'X-Warehouse-ID':'1'},
                    params={'paid_amount':100,'account_id':1,'request_key':'payment-v-receipt'})
            results=await asyncio.wait_for(asyncio.gather(receive(c,po,20),pay()),timeout=10)
            assert results[1].status_code in (200,400)
            after=await detail(c,po)
            assert after['items'][0]['received_quantity']==100 and after['matching']['review_status']=='stale'
            assert after['bill']['paid_amount']==(100 if results[1].status_code==200 else 0)
            # Fully paid historical bills retain their exact totals/status while new receipt evidence is recorded.
            async with f() as db:
                old=await db.get(PayableBill,1);old.paid_amount=1000;old.status='paid';await db.commit()
            historical=await request(c,'GET','/suppliers/purchase-orders/1')
            await receive(c,historical,8)
            final=await request(c,'GET','/payable/1/detail')
            assert final['paid_amount']==1000 and final['status']=='paid' and final['remaining_amount']==0 and not final['payments']
            actual('receipt_payment_race',{'concurrent_payment_status':results[1].status_code,'after':after,'paid_history_after':final})
    asyncio.run(run())


def test_corrupt_history_and_missing_guard_fail_closed_but_reads_do_not_write(tmp_path,monkeypatch):
    async def run():
        from sqlalchemy import event
        async with fixture(tmp_path,monkeypatch) as (engine,f,c):
            po=await order(c)
            async with f() as db:
                old=await db.get(PurchaseOrder,1);old.items=[{'line_id':['invalid'],'quantity':10,'received_quantity':-2}];await db.commit()
            writes=[]
            def trace(conn,cursor,statement,*a):
                if statement.lstrip().upper().startswith(('UPDATE','DELETE','INSERT')):writes.append(statement)
            event.listen(engine.sync_engine,'before_cursor_execute',trace)
            try:bad=await request(c,'GET','/suppliers/purchase-orders/1');assert not writes
            finally:event.remove(engine.sync_engine,'before_cursor_execute',trace)
            assert bad['receipt_issues'] and bad['items'][0]['received_quantity'] is None
            await receive(c,bad,1,code=409)
            async with engine.begin() as conn:
                await conn.execute(text('ALTER TABLE purchase_receipt_events DROP CONSTRAINT uq_purchase_receipt_operation'))
            blocked=await receive(c,po,1,code=503)
            assert (await detail(c,po))['receipt_batches']==[]
            async with engine.begin() as conn:
                with pytest.raises(HTTPException):
                    async with conn.begin_nested():await migrate_purchase_receipts(conn)
            actual('bad_history_guard',{'bad_history':bad,'blocked':blocked,'read_writes':writes})
    asyncio.run(run())


def test_decimal_price_precision_and_receipt_photo_permissions(tmp_path,monkeypatch):
    async def run():
        async with fixture(tmp_path,monkeypatch) as (_,f,c):
            async with f() as db:
                (await db.get(SupplierProduct,1)).unit_price=.125;await db.commit()
            po=await order(c,quantity=8);bid=po['bill']['id']
            await request(c,'PUT','/suppliers/purchase-match-policy',json={'strict':True})
            batch=await receive(c,po,4);await review(c,bid)
            after=await detail(c,po);assert after['matching']['payment_cap']==.5 and after['bill']['amount']==1
            await request(c,'PUT',f'/payable/{bid}/pay',code=400,params={'paid_amount':.51,'account_id':1,'request_key':'precision-over'})
            await request(c,'PUT',f'/payable/{bid}/pay',params={'paid_amount':.5,'account_id':1,'request_key':'precision-exact'})
            path=f'/suppliers/purchase-orders/{po["id"]}/receipts/{batch["id"]}/photo'
            for uid in (2,4,5):
                r=await c.get('/api/v1'+path,headers={**auth(uid),'X-Warehouse-ID':'1'});assert r.status_code==403
            r=await c.get('/api/v1'+path,headers={**auth(1),'X-Warehouse-ID':'2'});assert r.status_code==403
            r=await c.get('/api/v1'+path,headers={**auth(9),'X-Warehouse-ID':'1'});assert r.status_code==200
            wrong=await c.get(f'/api/v1/suppliers/purchase-orders/1/receipts/{batch["id"]}/photo',headers={**auth(1),'X-Warehouse-ID':'1'});assert wrong.status_code==403
            actual('precision_photos',{'unit_price':.125,'received_cap':.5,'bill_amount':1,'exact_payment':.5,'photo_scope_denials':True})
    asyncio.run(run())


def test_previous_manual_request_contract_and_explicit_unknown_replay(tmp_path,monkeypatch):
    async def run():
        from tests.test_supplier_dedup_round2 import create,form
        async with fixture(tmp_path,monkeypatch) as (_,f,c):
            data=form(amount='52')
            old=await create(c,data)
            async with f() as db:
                (await db.get(PayableBill,old['id'])).matching_kind=None;await db.commit()
            retry=await create(c,{**data,'matching_kind':'unknown'})
            assert retry['id']==old['id'] and retry['replayed']
            actual('round2_request_compatibility',{'original':old,'retry':retry})
    asyncio.run(run())


def test_same_wrong_line_subtotals_cannot_fake_three_way_match(tmp_path,monkeypatch):
    async def run():
        async with fixture(tmp_path,monkeypatch) as (_,f,c):
            po=await order(c);bid=po['bill']['id'];await receive(c,po,100)
            async with f() as db:
                saved=await db.get(PurchaseOrder,po['id']);saved.items=[{**r,'subtotal':950} for r in saved.items]
                bill=await db.get(PayableBill,bid);bill.match_lines=match.bill_lines(saved.items);await db.commit()
            state=await detail(c,po)
            assert state['matching']['amount_match']=='matched' and state['matching']['line_amount_match']=='different'
            assert state['matching']['status']=='different' and state['bill']['amount']==1000
            await request(c,'PUT','/suppliers/purchase-match-policy',json={'strict':True})
            await review(c,bid,'已看到行小计异常，不能把错误标成一致')
            blocked=await request(c,'PUT',f'/payable/{bid}/pay',code=400,params={'paid_amount':1,'account_id':1,'request_key':'bad-line-math'})
            actual('line_arithmetic',{'state':state,'strict_blocked':blocked})
    asyncio.run(run())


def test_malformed_bill_line_ids_stay_unknown_without_repair(tmp_path,monkeypatch):
    async def run():
        async with fixture(tmp_path,monkeypatch) as (_,f,c):
            po=await order(c);bid=po['bill']['id'];await receive(c,po,100)
            outcomes=[]
            for invalid_id in (['bad'], {'bad':'id'}, None, 12, '', True):
                async with f() as db:
                    bill=await db.get(PayableBill,bid)
                    malformed=match.bill_lines(po['items'])
                    malformed['items'][0]['line_id']=invalid_id
                    bill.match_lines=malformed;await db.commit()
                state=await detail(c,po)
                assert state['matching']['quantity_match']=='unknown'
                assert state['matching']['line_amount_match']=='unknown'
                assert state['matching']['status']=='unknown'
                async with f() as db:
                    assert (await db.get(PayableBill,bid)).match_lines==malformed
                outcomes.append({'stored_id':invalid_id,'status':state['matching']['status']})
            await request(c,'PUT','/suppliers/purchase-match-policy',json={'strict':True})
            await review(c,bid,'历史账单行编号异常，不能猜配')
            blocked=await request(c,'PUT',f'/payable/{bid}/pay',code=400,
                params={'paid_amount':1,'account_id':1,'request_key':'malformed-bill-line'})
            actual('malformed_bill_lines',{'cases':outcomes,'strict_blocked':blocked})
    asyncio.run(run())

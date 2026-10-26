"""Real local PostgreSQL and HTTP; no production connection or fixtures."""
import asyncio, json, os
from contextlib import asynccontextmanager
from datetime import date, datetime
from pathlib import Path
import pytest
from fastapi import HTTPException
from sqlalchemy import select, func, event, text
from app.models import User, UserWarehouse, Supplier, PurchaseOrder, PayableBill, PayablePayment, PaymentAccount
from app.models.supplier import SupplierProduct
from app.models.payable import PayablePlan
from tests.test_incoming_operations import environment, URL
from tests.test_round2_permissions import auth, png

pytestmark = pytest.mark.skipif(not URL, reason='Requires explicit isolated local PostgreSQL')
ACTUAL = {}
def actual(key,value):
    ACTUAL[key] = value
    if os.environ.get('SUPPLIER01_REPORT'):
        Path(os.environ['SUPPLIER01_REPORT']).write_text(json.dumps(ACTUAL,ensure_ascii=False,indent=2,default=str))

@asynccontextmanager
async def setup(tmp_path, mp):
    async with environment(tmp_path,mp) as (engine,f,c):
        async with f() as db:
            for uid,perms in [(3,['应付账款']), (4,[]), (1,[])]:
                (await db.get(User,uid)).extra_permissions=perms
            for uid,perms in [(8,['付款计划']),(9,['供应商管理'])]:
                db.add(User(id=uid,username=f'supplier-{uid}',display_name=f'测试{uid}',password_hash='unused',role='supervisor',warehouse_id=1,extra_permissions=perms))
            await db.flush()
            db.add_all([UserWarehouse(user_id=8,warehouse_id=1),UserWarehouse(user_id=9,warehouse_id=1),UserWarehouse(user_id=1,warehouse_id=2)])
            (await db.get(PaymentAccount,1)).opening_balance=10000
            db.add(PaymentAccount(id=3,warehouse_id=1,account_name='人民币账户',account_type='cash',account_number='-',opening_balance=10000,currency='CNY',opening_balance_date=date(2026,10,1)))
            db.add_all([Supplier(id=1,warehouse_id=1,name='本仓供应商'),Supplier(id=2,warehouse_id=2,name='外仓供应商')])
            await db.flush()
            db.add(SupplierProduct(id=1,supplier_id=1,product_name='耗材',unit_price=100,currency='THB'))
            po=PurchaseOrder(id=1,warehouse_id=1,supplier_id=1,order_number='OLD-PO-1',total_amount=1000,currency='THB',items=[{'product_name':'耗材','quantity':10}],status='confirmed',created_at=datetime(2020,1,1))
            db.add(po);await db.flush()
            db.add(PayableBill(id=1,warehouse_id=1,supplier_id=1,bill_number='OLD-BILL-1',bill_date=datetime(2020,1,1),due_date=datetime(2026,12,20),amount=1000,currency='THB',paid_amount=0,status='pending',purchase_order_id=1,source='purchase_order'))
            await db.flush();po.payable_bill_id=1;await db.commit()
            for table in ("purchase_orders","payable_bills"):
                await db.execute(text(f"SELECT setval(pg_get_serial_sequence('{table}','id'),(SELECT max(id) FROM {table}))"))
            await db.commit()
        yield engine,f,c

async def request(c, method, path, uid=1, warehouse='1', code=200, **kwargs):
    r=await c.request(method,'/api/v1'+path,headers={**auth(uid),'X-Warehouse-ID':warehouse},**kwargs)
    assert r.status_code==code,(method,path,r.status_code,r.text)
    return r.json()

def test_new_order_real_two_payments_voucher_failure_retry_and_read_only(tmp_path,monkeypatch):
    async def run():
        import app.services.image_utils as images
        async with setup(tmp_path,monkeypatch) as (engine,f,c):
            created=await request(c,'POST','/suppliers/1/purchase-order',json={'items':[{'product_id':1,'quantity':10}]})
            poid=created['order']['id'];bid=created['payable_bill_id'];assert bid and not created['pending']
            po=await request(c,'GET',f'/suppliers/purchase-orders/{poid}')
            assert po['items'][0].get('received_quantity') is None and po['bill']['id']==bid
            assert po['bill']['amount']==1000 and po['bill']['paid_amount']==0
            parameters={'paid_amount':300,'account_id':1,'payment_method':'现金','request_key':'supplier-first-300'}
            first=await request(c,'PUT',f'/payable/{bid}/pay',params=parameters)
            again=await request(c,'PUT',f'/payable/{bid}/pay',params=parameters);assert again['payment_id']==first['payment_id']
            partial=await request(c,'GET',f'/payable/{bid}/detail');assert partial['paid_amount']==300 and partial['remaining_amount']==700 and len(partial['payments'])==1
            def fail(*a,**k):raise HTTPException(500,'isolated voucher failure')
            original=images.save_image;monkeypatch.setattr(images,'save_image',fail)
            await request(c,'POST',f'/payable/{bid}/upload-voucher',code=500,files={'file':('proof.png',png(),'image/png')})
            assert (await request(c,'GET',f'/payable/{bid}/detail'))['paid_amount']==300
            monkeypatch.setattr(images,'save_image',lambda content,_folder,prefix,name:original(content,str(tmp_path/'vouchers'),prefix,name))
            await request(c,'POST',f'/payable/{bid}/upload-voucher',files={'file':('proof.png',png(),'image/png')})
            await request(c,'PUT',f'/payable/{bid}/pay',params={'paid_amount':700,'account_id':1,'payment_method':'银行转账','request_key':'supplier-second-700'})
            changes=[]
            def trace(conn,cursor,statement,*args):
                if statement.lstrip().upper().startswith(('INSERT','UPDATE','DELETE')):changes.append(statement)
            event.listen(engine.sync_engine,'before_cursor_execute',trace)
            try:
                final=await request(c,'GET',f'/payable/{bid}/detail')
                linked=await request(c,'GET',f'/suppliers/purchase-orders/{poid}')
                await request(c,'GET','/payable/stats',params={'all_dates':True})
                assert not changes
            finally:event.remove(engine.sync_engine,'before_cursor_execute',trace)
            assert final['paid_amount']==1000 and final['remaining_amount']==0
            assert [p['amount'] for p in final['payments']]==[300,700] and final['legacy_paid_amount']==0
            assert linked['bill']['paid_amount']==1000 and linked['bill']['status']=='paid'
            assert all(p['account_name'] and p['operator_name'] and p['paid_at'] for p in final['payments'])
            actual('1000_300_700',{'created':created,'partial':partial,'final':final,'read_write_queries':changes,'voucher_failure_did_not_duplicate':True})
    asyncio.run(run())

def test_summary_drill_currency_legacy_and_plan_records(tmp_path,monkeypatch):
    async def run():
        async with setup(tmp_path,monkeypatch) as (_,f,c):
            async with f() as db:
                bill=await db.get(PayableBill,1);bill.paid_amount=400;bill.due_date=datetime(2020,2,1)
                db.add(PayableBill(id=2,warehouse_id=1,supplier_id=1,bill_number='CNY-2',bill_date=datetime(2020,1,1),due_date=datetime(2026,12,1),amount=50,paid_amount=0,currency='CNY',status='pending'))
                db.add(PayableBill(id=3,warehouse_id=1,supplier_id=1,bill_number='VOID',bill_date=datetime(2020,1,1),due_date=datetime(2020,2,1),amount=999,paid_amount=0,currency='THB',status='voided'))
                db.add(PayablePlan(id=1,warehouse_id=1,plan_name='原有计划',planned_date=datetime(2026,10,26),total_amount=400,bill_ids=[1]))
                await db.commit()
            await request(c,'PUT','/payable/1/pay',params={'paid_amount':200,'account_id':1,'request_key':'legacy-200'})
            detail=await request(c,'GET','/payable/1/detail')
            assert detail['legacy_paid_amount']==400 and detail['recorded_payment_total']==200 and detail['paid_amount']==600
            summary=await request(c,'GET','/payable/stats',params={'all_dates':True,'supplier_id':1})
            assert summary['month_total'] is None and summary['month_total_by_currency']=={'THB':1000,'CNY':50}
            assert summary['month_paid_by_currency']=={'THB':600,'CNY':0}
            assert summary['month_unpaid_by_currency']=={'THB':400,'CNY':50}
            assert summary['overdue_by_currency']=={'THB':400,'CNY':0}
            for group in summary['supplier_summary']:
                drill=await request(c,'GET','/payable',params={'supplier_id':group['supplier_id'],'currency':group['currency'],'effective_only':True,'page_size':200})
                assert len(drill['data'])==group['bill_count']
                assert sum(b['amount'] for b in drill['data'])==group['total_amount']
                assert sum(b['paid_amount'] for b in drill['data'])==group['paid_amount']
            await request(c,'PUT','/payable/plans/1/execute',params={'account_id':1})
            after=await request(c,'GET','/payable/1/detail')
            assert after['paid_amount']==1000 and after['legacy_paid_amount']==400 and after['recorded_payment_total']==600
            assert [p['amount'] for p in after['payments']]==[200,400]
            actual('summary_legacy_plan',{'before_plan_summary':summary,'legacy_detail':detail,'after_plan':after})
    asyncio.run(run())

def test_permissions_selected_warehouse_and_corrupt_history_fail_closed(tmp_path,monkeypatch):
    async def run():
        async with setup(tmp_path,monkeypatch) as (_,f,c):
            results=[]
            for uid in (1,3,8):
                b=await request(c,'GET','/payable/1/detail',uid=uid);assert b['id']==1
                assert (await request(c,'GET','/suppliers/purchase-orders/1',uid=uid))['bill']['id']==1
                assert [s['id'] for s in (await request(c,'GET','/suppliers',uid=uid))['data']]==[1]
                results.append({'user':uid,'detail':200,'purchase':200})
            redacted=await request(c,'GET','/suppliers/purchase-orders/1',uid=9)
            assert redacted['bill'] is None and not redacted['can_read_payable']
            for path in ('/payable/1/detail','/payable/stats'):
                await request(c,'GET',path,uid=9,code=403)
            for uid in (2,4,5,7):
                for path in ('/payable/1/detail','/suppliers/purchase-orders/1'):
                    await request(c,'GET',path,uid=uid,warehouse='2' if uid==7 else '1',code=403)
            for header in ('2','999','garbage'):
                await request(c,'GET','/payable/1/detail',warehouse=header,code=403)
            await request(c,'POST','/suppliers/2/purchase-order',code=403,json={'items':[{'product_id':1,'quantity':1}]})
            await request(c,'PUT','/payable/1/pay',uid=3,code=403,params={'paid_amount':10,'account_id':1})
            async with f() as db:
                (await db.get(PurchaseOrder,1)).payable_bill_id=None;await db.commit()
            error=await request(c,'GET','/payable/1/detail',code=409)
            await request(c,'GET','/suppliers/purchase-orders/1',code=409)
            async with f() as db:assert (await db.get(PurchaseOrder,1)).payable_bill_id is None
            actual('permissions',{'allowed':results,'supplier_only':redacted,'history_error':error,'labor_foreign_super_denied':True})
    asyncio.run(run())

def test_pending_approval_creates_one_link_and_unknown_paid_value_stays_unknown(tmp_path,monkeypatch):
    async def run():
        from app.models import SystemSetting
        async with setup(tmp_path,monkeypatch) as (_,f,c):
            async with f() as db:
                db.add(SystemSetting(warehouse_id=1,key='purchase_approval_threshold',value='500'))
                await db.commit()
            created=await request(c,'POST','/suppliers/1/purchase-order',json={'items':[{'product_id':1,'quantity':10}]})
            poid=created['order']['id'];assert created['pending'] and created['payable_bill_id'] is None
            waiting=await request(c,'GET',f'/suppliers/purchase-orders/{poid}')
            assert waiting['bill'] is None and '待审批' in waiting['bill_message']
            approved=await request(c,'PUT',f'/suppliers/purchase-approvals/{poid}/approve')
            after=await request(c,'GET',f'/suppliers/purchase-orders/{poid}')
            assert after['bill']['id']==approved['payable_bill_id'] and after['status']=='confirmed'
            await request(c,'PUT',f'/suppliers/purchase-approvals/{poid}/approve',code=400)
            async with f() as db:
                assert (await db.execute(select(func.count(PayableBill.id)).where(PayableBill.purchase_order_id==poid))).scalar_one()==1
                (await db.get(PayableBill,1)).paid_amount=None;await db.commit()
            missing=await request(c,'GET','/payable/1/detail')
            assert missing['paid_amount'] is None and missing['remaining_amount'] is None and missing['legacy_paid_amount'] is None
            assert missing['warnings']
            actual('approval_and_missing',{'pending':waiting,'approved':after,'unknown_paid':missing})
    asyncio.run(run())

def test_over_200_old_documents_exact_lookup_and_receipt_refresh_guard(tmp_path,monkeypatch):
    async def run():
        import app.services.image_utils as images
        async with setup(tmp_path,monkeypatch) as (engine,f,c):
            async with f() as db:
                for i in range(1000,1205):
                    db.add(PurchaseOrder(id=i,warehouse_id=1,supplier_id=1,order_number=f'NEW-PO-{i}',total_amount=1,currency='THB',items=[],status='confirmed',created_at=datetime(2026,10,25)))
                    db.add(PayableBill(id=i,warehouse_id=1,supplier_id=1,bill_number=f'NEW-BILL-{i}',bill_date=datetime(2026,10,25),due_date=datetime(2026,11,1),amount=1,paid_amount=0,currency='THB',status='pending'))
                await db.commit()
            first=await request(c,'GET','/suppliers/purchase-orders',params={'page_size':200})
            assert first['total']==206 and 1 not in [p['id'] for p in first['data']]
            first_bills=await request(c,'GET','/payable',params={'page_size':200})
            assert first_bills['total']==206 and 1 not in [b['id'] for b in first_bills['data']]
            old=await request(c,'GET','/payable/1/detail',params={'month':'2026-10'})
            assert old['bill_date'].startswith('2020-01') and old['purchase_order_id']==1
            original=images.save_image
            monkeypatch.setattr(images,'save_image',lambda content,_folder,prefix,name:original(content,str(tmp_path/'arrivals'),prefix,name))
            await request(c,'POST','/suppliers/purchase-orders/1/receive',files={'file':('arrival.png',png(),'image/png')},data={'items':json.dumps([{'product_name':'耗材','received_quantity':8}])})
            after=await request(c,'GET','/suppliers/purchase-orders/1')
            assert after['receipt_status']=='partially_received' and after['items'][0]['received_quantity']==8 and after['items'][0]['diff_quantity']==2
            assert after['bill']['need_boss_confirm']=='true'
            denied=await request(c,'PUT','/payable/1/pay',code=400,params={'paid_amount':300,'account_id':1,'request_key':'must-confirm'})
            assert '需老板确认' in denied['detail']
            await request(c,'PUT','/payable/1/confirm')
            await request(c,'PUT','/payable/1/pay',params={'paid_amount':300,'account_id':1,'request_key':'after-confirm'})
            final=await request(c,'GET','/suppliers/purchase-orders/1')
            assert final['bill']['paid_amount']==300 and final['bill']['remaining_amount']==700
            actual('over200_and_receive',{'total':206,'old_detail':old,'after_receive':after,'payment_blocked':denied,'after_confirm_payment':final})
    asyncio.run(run())


def test_unknown_summary_drill_and_bad_history_remain_explicit(tmp_path,monkeypatch):
    async def run():
        async with setup(tmp_path,monkeypatch) as (engine,f,c):
            async with f() as db:
                (await db.get(PayableBill,1)).paid_amount=None
                db.add(PurchaseOrder(id=2,warehouse_id=1,supplier_id=1,order_number='LEGACY-UNLINKED',
                    total_amount=700,currency='THB',items=[],status='confirmed'))
                await db.flush()
                db.add(PayableBill(id=2,warehouse_id=1,supplier_id=1,bill_number='LEGACY-700',
                    bill_date=datetime(2020,1,1),due_date=datetime(2020,2,1),amount=700,paid_amount=200,
                    currency='THB',status='partially_paid',purchase_order_id=2))
                db.add(PayableBill(id=3,warehouse_id=1,supplier_id=1,bill_number='KNOWN-CNY',
                    bill_date=datetime(2020,1,1),due_date=datetime(2026,12,1),amount=50,paid_amount=0,
                    currency='CNY',status='pending'))
                await db.commit()
            summary=await request(c,'GET','/payable/stats',params={'all_dates':True})
            thb=next(g for g in summary['supplier_summary'] if g['currency']=='THB')
            assert thb['bill_count']==2 and thb['total_amount']==1700
            assert thb['paid_amount'] is None and thb['unpaid_amount'] is None and thb['overdue_amount'] is None
            assert thb['known_paid_amount']==200 and thb['known_unpaid_amount']==500 and thb['known_overdue_amount']==500
            assert thb['unknown_payment_count']==1 and thb['link_warning_bill_ids']==[2]
            assert summary['month_total_by_currency']=={'THB':1700,'CNY':50}
            assert summary['month_paid_by_currency']=={'THB':None,'CNY':0}
            assert summary['month_unpaid_by_currency']=={'THB':None,'CNY':50}
            assert summary['month_paid_known_by_currency']=={'THB':200,'CNY':0}
            drill=await request(c,'GET','/payable',params={'supplier_id':1,'currency':'THB','effective_only':True})
            assert drill['total']==2 and sum(b['amount'] for b in drill['data'])==1700
            unknown=next(b for b in drill['data'] if b['id']==1)
            assert unknown['paid_amount'] is None and unknown['remaining_amount'] is None and unknown['payment_totals_unknown']
            assert next(b for b in drill['data'] if b['id']==2)['link_warning']
            detail=await request(c,'GET','/payable/1/detail')
            assert detail['paid_amount'] is None and detail['remaining_amount'] is None
            bad=await request(c,'GET','/payable/2/detail',code=409)
            async with f() as db:
                assert (await db.get(PurchaseOrder,2)).payable_bill_id is None
                assert (await db.get(PayableBill,1)).paid_amount is None
            actual('unknown_summary',{'summary':summary,'drill':drill,'unknown_detail':detail,'history_detail_error':bad})
    asyncio.run(run())


def test_multi_member_selected_warehouse_lists_create_pdf_receipt_and_actions(tmp_path,monkeypatch):
    async def run():
        import app.services.image_utils as images
        async with setup(tmp_path,monkeypatch) as (_,f,c):
            async with f() as db:
                db.add(SupplierProduct(id=2,supplier_id=2,product_name='B仓耗材',unit_price=100,currency='THB'))
                await db.commit()
            bpo=await request(c,'POST','/suppliers/2/purchase-order',warehouse='2',json={'items':[{'product_id':2,'quantity':10}]})
            bpid=bpo['order']['id']
            observations=[]
            for warehouse,poid,foreign in [('1',1,bpid),('2',bpid,1)]:
                listing=await request(c,'GET','/suppliers/purchase-orders',warehouse=warehouse)
                assert [p['id'] for p in listing['data']]==[poid] and listing['total']==1
                detail=await request(c,'GET',f'/suppliers/purchase-orders/{poid}',warehouse=warehouse)
                assert detail['warehouse_id']==int(warehouse) and detail['warehouse_name']==f'测试仓{warehouse}'
                await request(c,'GET',f'/suppliers/purchase-orders/{foreign}',warehouse=warehouse,code=403)
                await request(c,'POST',f'/suppliers/purchase-orders/{foreign}/mark-sent',warehouse=warehouse,code=403)
                await request(c,'POST',f'/suppliers/purchase-orders/{poid}/mark-sent',warehouse=warehouse)
                observations.append({'selected_warehouse':warehouse,'list_ids':[poid],'detail_and_action':200,'other_member_warehouse':403})
            await request(c,'GET','/suppliers/purchase-orders',warehouse='all',code=400)
            original=images.save_image
            monkeypatch.setattr(images,'save_image',lambda content,_folder,prefix,name:original(content,str(tmp_path/'multi-warehouse'),prefix,name))
            form={'supplier_id':'2','bill_number':'B-MANUAL','bill_date':'2026-10-26','due_date':'2026-12-01','amount':'250','currency':'THB'}
            created=await request(c,'POST','/payable',warehouse='2',data=form,files={'file':('proof.png',png(),'image/png')})
            await request(c,'POST','/payable',warehouse='1',code=403,data=form,files={'file':('proof.png',png(),'image/png')})
            pdf=await c.get(f'/api/v1/suppliers/purchase-orders/{bpid}/pdf',headers={**auth(1),'X-Warehouse-ID':'2'})
            assert pdf.status_code==200 and pdf.content.startswith(b'%PDF')
            await request(c,'GET',f'/suppliers/purchase-orders/{bpid}/pdf',warehouse='1',code=403)
            receipt=await request(c,'POST',f'/suppliers/purchase-orders/{bpid}/receipt',warehouse='2',files={'file':('proof.png',png(),'image/png')})
            await request(c,'POST',f'/suppliers/purchase-orders/{bpid}/receipt',warehouse='1',code=403,files={'file':('proof.png',png(),'image/png')})
            detail=await request(c,'GET',f'/payable/{created["id"]}/detail',warehouse='2')
            assert detail['warehouse_id']==2 and detail['amount']==250
            async with f() as db:
                for wid,poid in [(1,1),(2,bpid)]:
                    po=await db.get(PurchaseOrder,poid);po.receipt_status='partially_received'
                    po.items=[{'product_name':'scope-test','quantity':1,'received_quantity':0,'diff_quantity':1}]
                    db.add(PurchaseOrder(id=5000+wid,warehouse_id=wid,supplier_id=wid,order_number=f'PENDING-{wid}',
                        items=[],total_amount=10,currency='THB',status='pending'))
                await db.commit()
            auxiliary=[]
            for wid,poid in [(1,1),(2,bpid)]:
                approvals=await request(c,'GET','/suppliers/purchase-approvals',warehouse=str(wid))
                differences=await request(c,'GET','/suppliers/purchase-receipt-discrepancies',warehouse=str(wid))
                assert [p['id'] for p in approvals['pending']]==[5000+wid]
                assert [p['purchase_order_id'] for p in differences['data']]==[poid]
                auxiliary.append({'warehouse':wid,'pending_ids':[5000+wid],'difference_purchase_ids':[poid]})
            actual('multi_warehouse',{'membership_warehouses':[1,2],'selections':observations,'all_mode':400,'manual_bill':created,'pdf_status':pdf.status_code,'pdf_bytes':len(pdf.content),'receipt':receipt,'auxiliary_lists':auxiliary})
    asyncio.run(run())

"""Round02: real local PostgreSQL transactions, races, history and migrations; no production."""
import asyncio, json, os, uuid
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
import pytest
from sqlalchemy import select, func, text
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException
from app.models import PayableBill, PurchaseOrder, Supplier
from app.models.data_change_history import DataChangeHistory
from app.services.payable_dedup_migration import migrate_payable_dedup, conflict_report
from app.core.payable_constraints import GUARDS, missing_guards
from tests.test_supplier_workflow_round1 import setup, request
from tests.test_round2_permissions import auth, png
from tests.test_incoming_operations import URL

pytestmark=pytest.mark.skipif(not URL,reason='Explicit local PostgreSQL required')
ACTUAL={}
def actual(name,data):
    ACTUAL[name]=data
    if os.environ.get('SUPPLIER02_REPORT'):
        Path(os.environ['SUPPLIER02_REPORT']).write_text(json.dumps(ACTUAL,ensure_ascii=False,indent=2,default=str))

@asynccontextmanager
async def fixture(tmp_path,mp):
    import app.services.image_utils as images
    original=images.save_image
    mp.setattr(images,'save_image',lambda content,_folder,prefix,name:original(content,str(tmp_path/'images'),prefix,name))
    async with setup(tmp_path,mp) as result:yield result

def form(**kw):
    return {'supplier_id':'1','bill_number':'ROUND2-NEW','bill_date':'2026-10-26','due_date':'2026-12-01',
        'amount':'100','currency':'THB','request_key':uuid.uuid4().hex,**kw}
async def create(c,data,code=200,**kw):
    return await request(c,'POST','/payable',code=code,data=data,files={'file':('proof.png',png(),'image/png')},**kw)
async def pending(db,ident,status='pending',number=None):
    db.add(PurchaseOrder(id=ident,warehouse_id=1,supplier_id=1,order_number=number or f'PENDING-{ident}',
        total_amount=75,currency='THB',items=[],status=status))
    await db.commit()

def test_history_same_number_candidates_are_local_and_never_permanently_exempt(tmp_path,monkeypatch):
    async def run():
        async with fixture(tmp_path,monkeypatch) as (_,f,c):
            async with f() as db:
                for bid,wid,sid,no in [(10,1,1,'  HIST-01 '),(11,1,1,'HIST-01'),(12,2,2,'HIST-01')]:
                    db.add(PayableBill(id=bid,warehouse_id=wid,supplier_id=sid,bill_number=no,bill_date=datetime(2020,1,1),
                        due_date=datetime(2026,12,1),amount=bid,currency='THB',paid_amount=0,status='pending',is_duplicate_warned='true'))
                await db.commit()
            data=form(bill_number='HIST-01',amount='333')
            challenge=(await create(c,data,409))['detail']
            assert not challenge['hard_duplicate'] and [b['id'] for b in challenge['candidates']]==[10,11]
            assert '12' not in json.dumps(challenge)
            data['duplicate_confirmation']=json.dumps({'candidate_ids':[10,11],'reason':'不同批次业务，已核对原凭证'})
            saved=await create(c,data);again=await create(c,data);assert saved['id']==again['id'] and again['replayed']
            fresh=(await create(c,form(bill_number='HIST-01',amount='444'),409))['detail']
            assert len(fresh['candidates'])==3
            async with f() as db:
                b=await db.get(PayableBill,saved['id']);assert b.bill_number=='HIST-01'
                assert b.duplicate_confirmation['candidate_ids']==[10,11] and b.duplicate_confirmation['operator_id']==1
                assert (await db.get(PayableBill,10)).bill_number=='  HIST-01 '
            actual('history_number',{'challenge':challenge,'saved':saved,'replay':again,'new_registration_still_checked':fresh})
    asyncio.run(run())

def test_verified_invoice_hard_identity_is_not_bill_number_or_amount(tmp_path,monkeypatch):
    async def run():
        async with fixture(tmp_path,monkeypatch) as (_,f,c):
            async with f() as db:
                db.add(Supplier(id=3,warehouse_id=1,name='同一真实供应商的另一个档案'))
                await db.commit()
            identity={'issuer_identifier':'OFFICIAL-TAX-ID','series':'2026/VAT','number':'INV-01','verified':True}
            first=await create(c,form(invoice_identity=json.dumps(identity)))
            blocked=(await create(c,form(supplier_id='3',bill_number='ANOTHER-REGISTER',amount='300',invoice_identity=json.dumps(identity)),409))['detail']
            assert blocked['hard_duplicate'] and [x['id'] for x in blocked['candidates']]==[first['id']]
            # Hyphens/series are meaningful: never strip them or infer identity from equal amounts.
            other=await create(c,form(bill_number='DIFFERENT-INVOICE',amount='301',invoice_identity=json.dumps({**identity,'number':'INV01'})))
            unknown=await create(c,form(bill_number='NO-INVOICE-IDENTITY',amount='302'))
            async with f() as db:
                assert (await db.get(PayableBill,unknown['id'])).invoice_identity_key is None
                a=await db.get(PayableBill,first['id']);b=await db.get(PayableBill,other['id'])
                assert a.invoice_identity_key!=b.invoice_identity_key and a.invoice_identity['number']=='INV-01'
            actual('invoice_identity',{'first':first,'hard_duplicate':blocked,'different_punctuation':other,'unknown_identity':unknown})
    asyncio.run(run())

def test_suspicion_window_confirmation_audit_and_void_reopen(tmp_path,monkeypatch):
    async def run():
        from app.config import get_settings
        async with fixture(tmp_path,monkeypatch) as (_,f,c):
            first=await create(c,form(bill_number='BUSINESS-A'))
            data=form(bill_number='BUSINESS-B')
            q=(await create(c,data,409))['detail'];ids=[x['id'] for x in q['candidates']]
            data['duplicate_confirmation']=json.dumps({'candidate_ids':ids,'reason':''})
            await create(c,data,409)
            data['duplicate_confirmation']=json.dumps({'candidate_ids':ids,'reason':'第二次独立采购，凭证已核对'})
            second=await create(c,data)
            async with f() as db:
                b=await db.get(PayableBill,second['id']);confirmation=b.duplicate_confirmation
                logs=(await db.execute(select(DataChangeHistory).where(DataChangeHistory.record_id==b.id,
                    DataChangeHistory.operation_type=='duplicate_confirm'))).scalars().all()
                assert len(logs)==1 and logs[0].after_data==confirmation
                assert confirmation['reason']=='第二次独立采购，凭证已核对' and confirmation['confirmed_at'] and confirmation['operator_id']==1
            await create(c,form(bill_number='NEXT-DAY',bill_date='2026-10-27'))
            monkeypatch.setattr(get_settings(),'PAYABLE_DUPLICATE_WINDOW_DAYS',3)
            changed=(await create(c,form(bill_number='WINDOW',bill_date='2026-10-29'),409))['detail'];assert changed['window_days']==3
            actual('suspicion_confirmation',{'first':first,'second':second,'confirmation':confirmation,'window_three_days':changed})
    asyncio.run(run())

def test_invalid_inputs_are_4xx_before_attachment_and_permissions_remain(tmp_path,monkeypatch):
    async def run():
        import app.services.image_utils as images
        async with fixture(tmp_path,monkeypatch) as (_,f,c):
            calls=[]
            def forbidden(*a,**k):calls.append(True);raise AssertionError('invalid input wrote an attachment')
            monkeypatch.setattr(images,'save_image',forbidden)
            results=[]
            for overrides in [{'bill_date':''},{'due_date':'invalid'},{'amount':'0'},{'amount':'-1'},{'amount':'nan'},{'amount':'inf'},
                {'bill_number':''},{'request_key':''},{'invoice_identity':'{"verified":true}'}]:
                r=await c.post('/api/v1/payable',headers={**auth(1),'X-Warehouse-ID':'1'},data=form(**overrides),files={'file':('x.png',png(),'image/png')})
                assert 400<=r.status_code<500,r.text;results.append({'input':overrides,'status':r.status_code,'body':r.json()})
            for uid in [2,3,4,5]:await create(c,form(),403,uid=uid)
            await create(c,form(supplier_id='2'),403)
            assert not calls
            async with f() as db:assert (await db.execute(select(func.count(PayableBill.id)))).scalar_one()==1
            actual('invalid_and_permissions',results)
    asyncio.run(run())

def test_double_approval_and_request_replays_create_one_bill(tmp_path,monkeypatch):
    async def run():
        async with fixture(tmp_path,monkeypatch) as (_,f,c):
            async with f() as db:await pending(db,10)
            replies=await asyncio.gather(*[request(c,'PUT','/suppliers/purchase-approvals/10/approve') for _ in range(2)])
            assert replies[0]['payable_bill_id']==replies[1]['payable_bill_id']
            async with f() as db:
                assert (await db.execute(select(func.count(PayableBill.id)).where(PayableBill.purchase_order_id==10))).scalar_one()==1
                po=await db.get(PurchaseOrder,10);assert po.payable_bill_id==replies[0]['payable_bill_id'] and po.status=='confirmed'
                db.add(PayableBill(warehouse_id=1,supplier_id=1,bill_number='BYPASS',bill_date=datetime(2026,10,26),due_date=datetime(2026,12,1),
                    amount=75,currency='THB',purchase_order_id=10,status='pending'))
                with pytest.raises(IntegrityError):await db.flush()
                await db.rollback()
            data=form(bill_number='REPLAY',amount='450')
            same=await asyncio.gather(create(c,dict(data)),create(c,dict(data)))
            assert same[0]['id']==same[1]['id']
            await create(c,{**data,'amount':'451'},409)
            actual('double_approval_and_replay',{'approvals':replies,'manual_replays':same,'direct_db_duplicate_rejected':True})
    asyncio.run(run())

def test_manual_association_races_approval_and_other_manual(tmp_path,monkeypatch):
    async def run():
        async with fixture(tmp_path,monkeypatch) as (_,f,c):
            async with f() as db:await pending(db,10)
            data=form(bill_number='RACE',purchase_order_number='PENDING-10',amount='75')
            responses=await asyncio.gather(c.post('/api/v1/payable',headers={**auth(1),'X-Warehouse-ID':'1'},data=data,files={'file':('p.png',png(),'image/png')}),
                c.put('/api/v1/suppliers/purchase-approvals/10/approve',headers={**auth(1),'X-Warehouse-ID':'1'},json={}))
            assert responses[0].status_code in (400,409) and responses[1].status_code==200
            async with f() as db:
                assert (await db.execute(select(func.count(PayableBill.id)).where(PayableBill.purchase_order_id==10))).scalar_one()==1
                await pending(db,11,'confirmed')
            async def associate(n):
                return await c.post('/api/v1/payable',headers={**auth(1),'X-Warehouse-ID':'1'},
                    data=form(bill_number=f'ASSOC-{n}',purchase_order_number='PENDING-11',bill_date='2026-10-28',amount='80'),files={'file':('p.png',png(),'image/png')})
            pair=await asyncio.gather(associate(1),associate(2));assert sorted(r.status_code for r in pair)==[200,409]
            async with f() as db:
                assert (await db.execute(select(func.count(PayableBill.id)).where(PayableBill.purchase_order_id==11))).scalar_one()==1
                po=await db.get(PurchaseOrder,11);assert po.payable_bill_id
            actual('association_races',{'approval_race':[{'status':r.status_code,'body':r.json()} for r in responses],
                'manual_race':[{'status':r.status_code,'body':r.json()} for r in pair]})
    asyncio.run(run())

def test_attachment_failure_rolls_back_bill_and_link(tmp_path,monkeypatch):
    async def run():
        import app.services.image_utils as images
        async with fixture(tmp_path,monkeypatch) as (_,f,c):
            async with f() as db:await pending(db,10,'confirmed')
            original=images.save_image
            def fail(*a,**k):raise HTTPException(500,'isolated attachment failure')
            monkeypatch.setattr(images,'save_image',fail)
            data=form(purchase_order_number='PENDING-10',amount='75')
            failed=await create(c,data,500)
            async with f() as db:
                assert (await db.get(PurchaseOrder,10)).payable_bill_id is None
                assert (await db.execute(select(func.count(PayableBill.id)))).scalar_one()==1
            monkeypatch.setattr(images,'save_image',original)
            saved=await create(c,data)
            actual('rollback',{'failure':failed,'retry':saved,'half_link_or_extra_bill':False})
    asyncio.run(run())

def test_purchase_number_ambiguity_is_local_conflict_not_scalar_500(tmp_path,monkeypatch):
    async def run():
        async with fixture(tmp_path,monkeypatch) as (_,f,c):
            async with f() as db:
                await pending(db,10,'confirmed','  SAME-PO ')
                await pending(db,11,'confirmed','SAME-PO')
            response=(await create(c,form(purchase_order_number='SAME-PO'),409))['detail']
            assert response['purchase_ids']==[10,11]
            await create(c,form(purchase_order_number='NOT-IN-THIS-WAREHOUSE'),404)
            actual('ambiguous_purchase_number',response)
            # Editing must use the same conservative normalization as creation, not Unicode strip().
            async with f() as db:
                await pending(db,12,'confirmed','\u00a0KEEP-UNICODE\u00a0')
                await pending(db,13,'confirmed','KEEP-UNICODE')
            saved=await create(c,form(bill_number='EDIT-NORMALIZATION',amount='333'))
            await request(c,'PUT',f'/payable/{saved["id"]}',json={'purchase_order_number':'\u00a0KEEP-UNICODE\u00a0'})
            async with f() as db:
                assert (await db.get(PayableBill,saved['id'])).purchase_order_id==12
                assert (await db.get(PurchaseOrder,12)).payable_bill_id==saved['id']
                assert (await db.get(PurchaseOrder,13)).payable_bill_id is None
            actual('conservative_edit_normalization',{'selected_purchase_id':12,'different_unicode_number_not_selected':13})
    asyncio.run(run())

@pytest.mark.parametrize('legacy_conflict',[False,True])
def test_migration_repeat_history_report_and_fail_closed(tmp_path,monkeypatch,legacy_conflict):
    async def run():
        async with fixture(tmp_path,monkeypatch) as (engine,f,c):
            async with engine.begin() as conn:
                for name in GUARDS:await conn.execute(text(f'DROP INDEX {name}'))
                for table,fields in [('payable_bills',['invoice_identity','invoice_identity_key','create_request_key','create_request_fingerprint','duplicate_confirmation']),
                    ('purchase_orders',['request_key','request_fingerprint'])]:
                    for field in fields:await conn.execute(text(f'ALTER TABLE {table} DROP COLUMN {field}'))
                if legacy_conflict:
                    await conn.execute(text("INSERT INTO payable_bills(id,warehouse_id,supplier_id,bill_number,bill_date,due_date,amount,paid_amount,status,currency,purchase_order_id) VALUES(2,1,1,'HISTORY-CONFLICT','2020-01-01','2026-12-01',25,0,'pending','THB',1)"))
                before=(await conn.execute(text('SELECT id,amount,paid_amount,purchase_order_id,bill_number FROM payable_bills ORDER BY id'))).all()
                preflight=await conflict_report(conn)
                assert len(preflight['unavailable_before_column_migration'])==3
                first=await migrate_payable_dedup(conn);second=await migrate_payable_dedup(conn)
                after=(await conn.execute(text('SELECT id,amount,paid_amount,purchase_order_id,bill_number FROM payable_bills ORDER BY id'))).all()
                assert before==after and first['ready']==(not legacy_conflict) and second['ready']==(not legacy_conflict)
                assert len(await missing_guards(conn))==(1 if legacy_conflict else 0)
            if legacy_conflict:
                error=(await create(c,form(),409))['detail'];assert error['code']=='payable_constraints_blocked'
                assert first['conflicts']['active_purchase_conflicts'][0]['bill_ids']==[1,2]
                assert (await request(c,'GET','/payable/1/detail'))['id']==1
            else:assert (await create(c,form()))['id']
            async with engine.connect() as conn:
                await conn.execute(text('SET TRANSACTION READ ONLY'))
                report=await conflict_report(conn,1)
                assert (await conn.execute(text('SHOW transaction_read_only'))).scalar_one()=='on'
                await conn.rollback()
            actual('migration_conflict' if legacy_conflict else 'migration_clean',{'first':first,'second':second,'readonly_report':report,'history_unchanged':True})
    asyncio.run(run())


def test_parallel_purchase_requests_invoice_requests_and_reject_race(tmp_path,monkeypatch):
    async def run():
        async with fixture(tmp_path,monkeypatch) as (_,f,c):
            payload={'request_key':'same-purchase-request','items':[{'product_id':1,'quantity':10}]}
            pair=await asyncio.gather(*[request(c,'POST','/suppliers/1/purchase-order',json=dict(payload)) for _ in range(2)])
            assert pair[0]['order']['id']==pair[1]['order']['id'] and pair[0]['payable_bill_id']==pair[1]['payable_bill_id']
            identity=json.dumps({'issuer_identifier':'ISSUER-RACE','series':'2026','number':'R-1','verified':True})
            async def invoice(n):
                return await c.post('/api/v1/payable',headers={**auth(1),'X-Warehouse-ID':'1'},data=form(bill_number=f'INVOICE-RACE-{n}',
                    amount='333',invoice_identity=identity),files={'file':('x.png',png(),'image/png')})
            invoices=await asyncio.gather(invoice(1),invoice(2));assert sorted(r.status_code for r in invoices)==[200,409]
            async with f() as db:await pending(db,20)
            response=await asyncio.gather(c.put('/api/v1/suppliers/purchase-approvals/20/approve',headers={**auth(1),'X-Warehouse-ID':'1'},json={}),
                c.put('/api/v1/suppliers/purchase-approvals/20/reject',headers={**auth(1),'X-Warehouse-ID':'1'},json={'reason':'测试驳回'}))
            assert sorted(r.status_code for r in response)==[200,400]
            async with f() as db:
                po=await db.get(PurchaseOrder,20)
                count=(await db.execute(select(func.count(PayableBill.id)).where(PayableBill.purchase_order_id==20))).scalar_one()
                assert (po.status=='confirmed' and count==1 and po.payable_bill_id) or (po.status=='rejected' and count==0 and po.payable_bill_id is None)
                assert (await db.execute(select(func.count(PurchaseOrder.id)).where(PurchaseOrder.request_key=='same-purchase-request'))).scalar_one()==1
            actual('parallel_purchase_and_invoice',{'same_purchase_requests':pair,'invoice_statuses':[r.status_code for r in invoices],
                'approval_vs_reject':[r.status_code for r in response],'no_half_link':True})
    asyncio.run(run())


def test_voided_invoice_reopen_requires_new_confirmation_and_purchase_is_not_silently_reopened(tmp_path,monkeypatch):
    async def run():
        async with fixture(tmp_path,monkeypatch) as (_,f,c):
            identity=json.dumps({'issuer_identifier':'ISSUER-VOID','series':'2026','number':'VOID-1','verified':True})
            data=form(invoice_identity=identity)
            first=await create(c,data)
            await request(c,'PUT',f'/payable/{first["id"]}/void',params={'void_reason':'原单错误，测试作废'})
            again={**data,'request_key':uuid.uuid4().hex}
            challenge=(await create(c,again,409))['detail'];assert not challenge['hard_duplicate']
            again['duplicate_confirmation']=json.dumps({'candidate_ids':[r['id'] for r in challenge['candidates']],'reason':'原单已作废，重新核对凭证登记'})
            reopened=await create(c,again)
            await request(c,'PUT','/payable/1/void',params={'void_reason':'测试原采购账单作废'})
            blocked=await create(c,form(purchase_order_number='OLD-PO-1',amount='1000'),409)
            async with f() as db:
                assert (await db.get(PayableBill,first['id'])).status=='voided'
                assert (await db.get(PurchaseOrder,1)).payable_bill_id==1
            actual('void_reopen',{'original':first,'challenge':challenge,'new_bill':reopened,'purchase_not_auto_reopened':blocked})
    asyncio.run(run())


def test_wrong_same_name_index_is_blocked_not_reported_as_ready(tmp_path,monkeypatch):
    async def run():
        async with fixture(tmp_path,monkeypatch) as (engine,f,c):
            async with engine.begin() as conn:
                await conn.execute(text('DROP INDEX uq_payable_active_purchase'))
                await conn.execute(text('CREATE INDEX uq_payable_active_purchase ON payable_bills(purchase_order_id)'))
                result=await migrate_payable_dedup(conn)
                assert not result['ready'] and 'uq_payable_active_purchase' in result['missing_guards']
            blocked=(await create(c,form(),409))['detail'];assert blocked['code']=='payable_constraints_blocked'
            assert (await request(c,'GET','/payable/1/detail'))['amount']==1000
            actual('wrong_index_fail_closed',{'migration':result,'blocked':blocked,'old_read_still_works':True})
    asyncio.run(run())

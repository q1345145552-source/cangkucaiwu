"""Only disposable localhost PostgreSQL: four channels, actual HTTP and transaction rollback."""
import asyncio,json,os,uuid,itertools
from contextlib import asynccontextmanager
from pathlib import Path
from datetime import datetime
import pytest
from sqlalchemy import select,func,text
from app.models import CostIdentity,ExpenseRecord,ExpenseApproval,ExpenseFund,ExpenseFundItem,IncomeExpenseCategory,Supplier,PayableBill,PayablePayment,PaymentAccount
from app.services import cost_identity as costs
from app.services.account_balances import current_account_balances
from tests.test_supplier_workflow_round1 import setup,request
from tests.test_round2_permissions import png,auth
from tests.test_incoming_operations import URL

pytestmark=pytest.mark.skipif(not URL,reason='Explicit disposable localhost PostgreSQL required')
ACTUAL={}
def actual(name,value):
    ACTUAL[name]=value
    if os.environ.get('SUPPLIER04_REPORT'):Path(os.environ['SUPPLIER04_REPORT']).write_text(json.dumps(ACTUAL,ensure_ascii=False,default=str,indent=2))

@asynccontextmanager
async def fixture(tmp_path,mp):
    import app.services.image_utils as images
    import app.api.v1.expense_fund as api
    mp.setenv('UPLOAD_DIR',str(tmp_path/'uploads'));mp.setattr(api,'UPLOAD_DIR',str(tmp_path/'uploads'))
    original=images.save_image
    mp.setattr(images,'save_image',lambda content,folder,prefix,name:original(content,str(tmp_path/'uploads'/Path(folder).relative_to('/app/uploads')) if folder.startswith('/app/uploads/') else folder,prefix,name))
    async with setup(tmp_path,mp) as (engine,f,c):
        from app.config import get_settings
        mp.setattr(get_settings(),'PAYABLE_DUPLICATE_WINDOW_DAYS',7)
        import app.services.account_balances as balances
        mp.setattr(balances,'thai_today',lambda:datetime(2026,10,26).date())
        # Freeze the payment clock too: otherwise after midnight a test payment
        # lands after the balance fixture's fixed Oct26 as-of date.
        import app.api.v1.expense_approval as approvals
        from app.core.timezone import THAI_TZ
        mp.setattr(approvals,'thai_now',lambda:datetime(2026,10,26,12,tzinfo=THAI_TZ))
        mp.setattr(approvals,'thai_today',lambda:datetime(2026,10,26).date())
        async with f() as db:
            db.add(IncomeExpenseCategory(id=1,warehouse_id=1,type='expense',category_group='operating',name='耗材'))
            db.add(ExpenseFund(id=1,warehouse_id=1,employee_id=4,receive_date=datetime(2026,10,1),amount=10000,
                remaining_balance=10000,fund_limit=20000,status='active',purpose='合成备用金',currency='THB'))
            db.add(Supplier(id=3,warehouse_id=1,name='同开票方别名'));await db.commit()
            await db.execute(text("SELECT setval(pg_get_serial_sequence('income_expense_categories','id'),(SELECT max(id) FROM income_expense_categories))"));await db.commit()
        receipt=(await request(c,'POST','/expense-fund/accounts/1/upload-receipt',files={'file':('proof.png',png(),'image/png')}))['receipt']
        yield engine,f,c,receipt

def invoice(no='INV-01',issuer='TAX-EXACT'):
    return {'issuer_identifier':issuer,'series':'VAT/2026','number':no,'verified':True}

def test_exact_origin_voucher_keeps_legacy_paths_private_and_scoped(tmp_path,monkeypatch):
    async def run():
        from sqlalchemy import event
        async with fixture(tmp_path,monkeypatch) as (engine,f,c,receipt):
            bill=await create(c,'payable',receipt,identity=invoice(),key='origin-voucher')
            path=f'/api/v1/expense-identities/payable/{bill["id"]}'
            changes=[]
            def trace(conn,cursor,statement,*args):
                if statement.lstrip().upper().startswith(('INSERT','UPDATE','DELETE')):changes.append(statement)
            event.listen(engine.sync_engine,'before_cursor_execute',trace)
            try:
                for uid in (1,3,8):
                    response=await c.get(path,headers={**auth(uid),'X-Warehouse-ID':'1'},params={'voucher_index':0})
                    assert response.status_code==200 and response.content==png(),(response.status_code,response.text)
                    assert response.headers['cache-control']=='private, no-store'
                for uid in (2,4,5):
                    assert (await c.get(path,headers={**auth(uid),'X-Warehouse-ID':'1'},params={'voucher_index':0})).status_code==403
                assert (await c.get(path,headers={**auth(7),'X-Warehouse-ID':'2'},params={'voucher_index':0})).status_code==404
                assert (await c.get(path,headers=auth(1),params={'voucher_index':1})).status_code==404
                assert (await c.get(path,headers=auth(1),params={'voucher_index':-1})).status_code==422
                assert not changes
            finally:event.remove(engine.sync_engine,'before_cursor_execute',trace)
            async with f() as db:
                b=await db.get(PayableBill,bill['id']);legacy_path=b.bill_attachment
                b.bill_attachment='/uploads/2/private-proof.png';await db.commit()
            assert (await c.get(path,headers=auth(1),params={'voucher_index':0})).status_code==404
            async with f() as db:
                (await db.get(PayableBill,bill['id'])).bill_attachment='/uploads/../private-proof.png';await db.commit()
            assert (await c.get(path,headers=auth(1),params={'voucher_index':0})).status_code==404
            # The general upload route remains closed for unscoped legacy paths.
            assert (await c.get(legacy_path,headers=auth(1))).status_code==404
            actual('exact_origin_voucher',{'authorized_roles':[1,3,8],'denied_roles':[2,4,5],'cross_warehouse':404,'read_write_queries':changes,'generic_upload_policy_unchanged':True})
    asyncio.run(run())

async def create(c,kind,receipt,*,identity=None,amount=100,supplier=1,key=None,confirmation=None,code=200,activate=True,uid=1):
    key=key or uuid.uuid4().hex
    extra={'supplier_id':supplier,'invoice_identity':identity,'request_key':key,'cost_confirmation':confirmation}
    if kind=='payable':
        data={'supplier_id':str(supplier),'bill_number':'R4-'+key[:12],'bill_date':'2026-10-26','due_date':'2026-12-01',
            'amount':str(amount),'currency':'THB','request_key':key}
        if identity:data['invoice_identity']=json.dumps(identity)
        if confirmation:data['cost_confirmation']=json.dumps(confirmation)
        return await request(c,'POST','/payable',uid=uid,code=code,data=data,files={'file':('proof.png',png(),'image/png')})
    if kind=='expense':
        data={'category_id':'1','account_id':'1','supplier_id':str(supplier),'amount':str(amount),'currency':'THB','expense_date':'2026-10-26','remark':'合成真实费用','request_key':key}
        if identity:data['invoice_identity']=json.dumps(identity)
        if confirmation:data['cost_confirmation']=json.dumps(confirmation)
        return await request(c,'POST','/income-expense/expense',uid=uid,code=code,data=data,files={'files':('proof.png',png(),'image/png')})
    if kind=='fund_item':
        return await request(c,'POST','/expense-fund/accounts/1/items',uid=uid,code=code,
            json={**extra,'expense_date':'2026-10-26','category':'耗材','amount':amount,'currency':'THB','description':'合成开销','receipt':receipt})
    import base64
    result=await request(c,'POST','/expense-approvals',uid=uid,code=code,
        json={**extra,'amount':amount,'currency':'THB','purpose':'合成审批','expense_date':'2026-10-26','fund_source':'company','payment_account_id':1})
    if code!=200 or not activate:return result
    if result['status']=='pending':await request(c,'POST',f'/expense-approvals/{result["id"]}/approve')
    return await request(c,'POST',f'/expense-approvals/{result["id"]}/pay',json={
        'payment_account_id':1,'voucher_base64':'data:image/png;base64,'+base64.b64encode(png()).decode(),'cost_confirmation':confirmation})

async def snapshot(f):
    async with f() as db:
        a=await db.get(PaymentAccount,1)
        return {'roots':(await db.execute(select(func.count(CostIdentity.id)))).scalar_one(),
            'bills':(await db.execute(select(func.count(PayableBill.id)))).scalar_one(),
            'approvals':(await db.execute(select(func.count(ExpenseApproval.id)))).scalar_one(),
            'fund_items':(await db.execute(select(func.count(ExpenseFundItem.id)))).scalar_one(),
            'expenses':(await db.execute(select(func.count(ExpenseRecord.id)))).scalar_one(),
            'balance':float((await current_account_balances(db,[a]))[a.id])}

PAIRS=list(itertools.combinations(('payable','approval','fund_item','expense'),2))
@pytest.mark.parametrize('first,second',PAIRS)
def test_six_pairs_hard_and_distinct_invoice_reason(tmp_path,monkeypatch,first,second):
    async def run():
        async with fixture(tmp_path,monkeypatch) as (_,f,c,receipt):
            saved=await create(c,first,receipt,identity=invoice())
            before=await snapshot(f)
            blocked=await create(c,second,receipt,identity=invoice(),code=409)
            assert blocked['detail']['hard_duplicate']
            assert await snapshot(f)==before
            challenge=(await create(c,second,receipt,identity=invoice('INV-02'),code=409))['detail']
            assert not challenge['hard_duplicate']
            confirm={'candidate_refs':[v['ref'] for v in challenge['candidates']],'version':challenge['version'],'reason':'不同业务原票，已逐笔核对'}
            other=await create(c,second,receipt,identity=invoice('INV-02'),confirmation=confirm)
            async with f() as db:
                roots=(await db.execute(select(CostIdentity).where(CostIdentity.active.is_(True)))).scalars().all()
                assert len(roots)==2 and len({r.invoice_key for r in roots})==2
            actual(first+'_'+second,{'first':saved,'hard':blocked,'before_after_block_equal':before,'challenge':challenge,'other':other})
    asyncio.run(run())


def confirmation(challenge):
    return {'candidate_refs':[v['ref'] for v in challenge['candidates']],'version':challenge['version'],'reason':'独立业务，原票和来源已核对'}

def test_cross_channel_concurrent_identity_has_one_root_and_no_half_writes(tmp_path,monkeypatch):
    async def run():
        async with fixture(tmp_path,monkeypatch) as (_,f,c,receipt):
            key1,key2=uuid.uuid4().hex,uuid.uuid4().hex;ident=json.dumps(invoice())
            a={'supplier_id':'1','bill_number':'RACE','bill_date':'2026-10-26','due_date':'2026-12-01','amount':'100','currency':'THB','request_key':key1,'invoice_identity':ident}
            b={'supplier_id':'3','category_id':'1','account_id':'1','expense_date':'2026-10-26','amount':'100','currency':'THB','request_key':key2,'invoice_identity':ident}
            responses=await asyncio.gather(c.post('/api/v1/payable',headers=auth(1),data=a,files={'file':('proof.png',png(),'image/png')}),
                c.post('/api/v1/income-expense/expense',headers=auth(1),data=b,files={'files':('proof.png',png(),'image/png')}))
            assert sorted(r.status_code for r in responses)==[200,409],[(r.status_code,r.text) for r in responses]
            s=await snapshot(f);assert s['roots']==1 and (s['bills']-1)+s['expenses']==1 and s['fund_items']==s['approvals']==0
            assert s['balance']==(9900 if responses[1].status_code==200 else 10000)
            actual('concurrent',{'responses':[{'status':r.status_code,'body':r.json()} for r in responses],'snapshot':s})
    asyncio.run(run())


def test_request_replay_same_event_and_changed_content_rejected(tmp_path,monkeypatch):
    async def run():
        async with fixture(tmp_path,monkeypatch) as (_,f,c,receipt):
            outcomes={}
            for index,kind in enumerate(('payable','approval','fund_item','expense')):
                key=uuid.uuid4().hex;args={'identity':invoice('RETRY-'+kind),'amount':100+index,'key':key}
                first=await create(c,kind,receipt,**args);before=await snapshot(f)
                again=await create(c,kind,receipt,**args);assert first['id']==again['id'] and await snapshot(f)==before
                bad=await create(c,kind,receipt,**{**args,'amount':200+index},code=409)
                assert await snapshot(f)==before
                outcomes[kind]={'first':first,'again':again,'changed':bad,'unchanged':before}
            actual('replays',outcomes)
    asyncio.run(run())


def test_approval_payment_race_and_both_derived_channels_share_one_root(tmp_path,monkeypatch):
    async def run():
        import base64
        async with fixture(tmp_path,monkeypatch) as (_,f,c,receipt):
            a=await create(c,'approval',receipt,identity=invoice(),activate=False)
            await request(c,'POST',f'/expense-approvals/{a["id"]}/approve')
            body={'payment_account_id':1,'voucher_base64':'data:image/png;base64,'+base64.b64encode(png()).decode()}
            response=await asyncio.gather(*[c.post(f'/api/v1/expense-approvals/{a["id"]}/pay',headers=auth(1),json=body) for _ in range(2)])
            assert all(r.status_code==200 for r in response)
            async with f() as db:
                origin=await db.get(ExpenseApproval,a['id']);child=await db.get(ExpenseRecord,origin.expense_record_id)
                assert child.cost_identity_id==origin.cost_identity_id and child.supplier_id==1
                assert (await db.execute(select(func.count(CostIdentity.id)))).scalar_one()==1
            await request(c,'DELETE',f'/income-expense/expense/{child.id}',code=400)
            # Separate genuine expense, paid from fund: no operating expense and only one origin.
            b=await request(c,'POST','/expense-approvals',json={'supplier_id':1,'invoice_identity':invoice('FUND-APP'),'request_key':uuid.uuid4().hex,
                'amount':101,'currency':'THB','purpose':'备用金支付合成费用','expense_date':'2026-10-26','fund_source':'fund'})
            await request(c,'POST',f'/expense-approvals/{b["id"]}/approve')
            paid=await request(c,'POST',f'/expense-approvals/{b["id"]}/pay',json={'voucher_base64':body['voucher_base64']})
            async with f() as db:
                origin=await db.get(ExpenseApproval,b['id']);fund_item=await db.get(ExpenseFundItem,origin.fund_item_id)
                assert fund_item.cost_identity_id==origin.cost_identity_id and origin.expense_record_id is None
                assert (await db.execute(select(func.count(CostIdentity.id)))).scalar_one()==2
            blocked=await request(c,'POST','/expense-fund/review/batch',code=400,json={'item_ids':[fund_item.id],'action':'reject'})
            async with f() as db:
                from app.models import User
                (await db.get(User,3)).extra_permissions=['备用金管理'];await db.commit()
            visible=await request(c,'GET','/expense-fund/accounts/1/items',uid=3)
            item=next(v for v in visible['data'] if v['id']==fund_item.id)
            assert item['invoice_identity'] is None and item['cost_origin_restricted']
            parent=await request(c,'GET',f'/expense-identities/fund_item/{fund_item.id}',uid=3)
            assert 'identity' not in parent and 'origin' not in parent
            await request(c,'GET',f'/expense-identities/approval/{b["id"]}',uid=3,code=403)
            actual('derived',{'company_payments':[r.json() for r in response],'fund_payment':paid,'fund_child_blocked':blocked,'snapshot':await snapshot(f)})
    asyncio.run(run())


def test_two_pending_approvals_same_invoice_only_one_payment_activates(tmp_path,monkeypatch):
    async def run():
        import base64
        async with fixture(tmp_path,monkeypatch) as (_,f,c,receipt):
            pending=[await create(c,'approval',receipt,identity=invoice(),activate=False) for _ in range(2)]
            for a in pending:await request(c,'POST',f'/expense-approvals/{a["id"]}/approve')
            body={'payment_account_id':1,'voucher_base64':'data:image/png;base64,'+base64.b64encode(png()).decode()}
            results=await asyncio.gather(*[c.post(f'/api/v1/expense-approvals/{a["id"]}/pay',headers=auth(1),json=body) for a in pending])
            assert sorted(r.status_code for r in results)==[200,409]
            async with f() as db:
                roots=(await db.execute(select(CostIdentity))).scalars().all()
                assert len(roots)==2 and sum(r.active for r in roots)==1
            s=await snapshot(f);assert s['expenses']==1 and s['balance']==9900
            actual('pending_activation_race',{'responses':[{'status':r.status_code,'body':r.json()} for r in results],'snapshot':s})
    asyncio.run(run())


def test_installments_void_paid_protection_and_unpaid_reopen(tmp_path,monkeypatch):
    async def run():
        async with fixture(tmp_path,monkeypatch) as (_,f,c,receipt):
            a=await create(c,'payable',receipt,identity=invoice(),amount=1000)
            await request(c,'PUT',f'/payable/{a["id"]}/pay',params={'paid_amount':300,'account_id':1,'request_key':'cost-part-300'})
            async with f() as db:assert (await db.execute(select(func.count(CostIdentity.id)))).scalar_one()==1
            await request(c,'PUT',f'/payable/{a["id"]}/pay',params={'paid_amount':700,'account_id':1,'request_key':'cost-part-700'})
            async with f() as db:
                assert (await db.execute(select(func.count(CostIdentity.id)))).scalar_one()==1
                assert (await db.execute(select(func.count(PayablePayment.id)))).scalar_one()==2
            await create(c,'fund_item',receipt,identity=invoice(),amount=1000,code=409)
            # Legitimately voided unpaid invoice is reusable. Paid/part-paid cannot release it.
            unpaid=await create(c,'payable',receipt,identity=invoice('UNPAID'),amount=110)
            await request(c,'PUT',f'/payable/{unpaid["id"]}/void',params={'void_reason':'未付原单作废'})
            reopened=await create(c,'fund_item',receipt,identity=invoice('UNPAID'),amount=110)
            partial=await create(c,'payable',receipt,identity=invoice('PART'),amount=120)
            await request(c,'PUT',f'/payable/{partial["id"]}/pay',params={'paid_amount':20,'account_id':1,'request_key':'cost-part-20'})
            await request(c,'PUT',f'/payable/{partial["id"]}/void',params={'void_reason':'保留已付部分'})
            blocked=await create(c,'expense',receipt,identity=invoice('PART'),amount=120,code=409)
            actual('installments_lifecycle',{'first':a,'unpaid':unpaid,'reopened':reopened,'part_paid_blocked':blocked,'snapshot':await snapshot(f)})
    asyncio.run(run())


def test_fund_rejection_release_reactivation_and_paid_tombstone(tmp_path,monkeypatch):
    async def run():
        async with fixture(tmp_path,monkeypatch) as (_,f,c,receipt):
            a=await create(c,'fund_item',receipt,identity=invoice())
            await request(c,'POST','/expense-fund/review/batch',json={'item_ids':[a['id']],'action':'reject'})
            b=await create(c,'expense',receipt,identity=invoice())
            await request(c,'POST','/expense-fund/review/batch',code=409,json={'item_ids':[a['id']],'action':'approve'})
            async with f() as db:assert (await db.get(ExpenseFundItem,a['id'])).review_status=='rejected'
            await request(c,'DELETE',f'/income-expense/expense/{b["id"]}')
            denied=await create(c,'payable',receipt,identity=invoice(),code=409)
            tombstone=await request(c,'GET',f'/expense-identities/expense/{b["id"]}')
            assert tombstone['identity']['cost_active'] and tombstone['document']['source_deleted']
            actual('release_tombstone',{'fund':a,'expense':b,'repeated_blocked':denied,'tombstone':tombstone})
    asyncio.run(run())


def test_changed_candidate_version_and_paid_identity_cannot_be_erased(tmp_path,monkeypatch):
    async def run():
        async with fixture(tmp_path,monkeypatch) as (_,f,c,receipt):
            a=await create(c,'payable',receipt,identity=invoice())
            q=(await create(c,'fund_item',receipt,identity=invoice('OTHER'),code=409))['detail']
            proof=confirmation(q)
            async with f() as db:old_version=(await db.execute(select(CostIdentity.version).where(CostIdentity.source_type=='payable',CostIdentity.source_id==a['id']))).scalar_one()
            await request(c,'PUT',f'/payable/{a["id"]}',json={'bill_date':'2026-10-25'})
            async with f() as db:
                root=(await db.execute(select(CostIdentity).where(CostIdentity.source_type=='payable',CostIdentity.source_id==a['id']))).scalar_one()
                actual('version_before_retry',{'old_challenge':q,'old_root_version':old_version,'new_root_version':root.version,'new_root_date':root.expense_date})
                assert root.expense_date==datetime(2026,10,25).date() and root.version!=old_version
            changed=(await create(c,'fund_item',receipt,identity=invoice('OTHER'),confirmation=proof,code=409))['detail']
            assert q['version']!=changed['version']
            saved=await create(c,'fund_item',receipt,identity=invoice('OTHER'),confirmation=confirmation(changed))
            e=await create(c,'expense',receipt,identity=invoice('PAID'),amount=101)
            await request(c,'PUT',f'/income-expense/expense/{e["id"]}',code=400,data={
                'category_id':'1','account_id':'1','amount':'101','currency':'THB','expense_date':'2026-10-26','invoice_identity':''})
            async with f() as db:assert (await db.get(CostIdentity,e['cost_identity_id'])).invoice_key is not None
            actual('version_identity',{'old':q,'changed':changed,'saved':saved,'paid':e})
    asyncio.run(run())


def test_alias_exact_identity_scope_and_private_candidates(tmp_path,monkeypatch):
    async def run():
        from app.models import User
        async with fixture(tmp_path,monkeypatch) as (_,f,c,receipt):
            a=await create(c,'expense',receipt,identity=invoice(),amount=102)
            await create(c,'payable',receipt,identity=invoice(),supplier=3,amount=900,code=409)
            async with f() as db:
                (await db.get(User,4)).extra_permissions=['应付账款'];await db.commit()
            hidden=await create(c,'payable',receipt,identity=invoice('ALIAS-OTHER'),supplier=3,amount=102,uid=4,code=409)
            assert hidden['detail']['code']=='cost_duplicate_restricted' and 'candidates' not in hidden['detail']
            assert '102' not in json.dumps(hidden) and 'href' not in json.dumps(hidden)
            for uid in (2,5):
                await request(c,'GET','/expense-identities/suppliers',uid=uid,code=403)
                await request(c,'GET',f'/expense-identities/expense/{a["id"]}',uid=uid,code=403)
            await request(c,'GET',f'/expense-identities/expense/{a["id"]}',uid=4,code=403)
            await request(c,'GET',f'/expense-identities/expense/{a["id"]}',uid=7,warehouse='2',code=404)
            # Same exact invoice in a genuinely different warehouse is independent.
            async with f() as db:
                from app.models import UserWarehouse
                db.add(UserWarehouse(user_id=1,warehouse_id=2)) if not (await db.execute(select(UserWarehouse).where(UserWarehouse.user_id==1,UserWarehouse.warehouse_id==2))).first() else None
                await db.commit()
            other=await request(c,'POST','/payable',warehouse='2',data={'supplier_id':'2','bill_number':'OTHER-WAREHOUSE','bill_date':'2026-10-26','due_date':'2026-12-01','amount':'102','currency':'THB','request_key':uuid.uuid4().hex,'invoice_identity':json.dumps(invoice())},files={'file':('proof.png',png(),'image/png')})
            actual('permissions_alias',{'saved':a,'restricted':hidden,'other_warehouse':other})
    asyncio.run(run())


def test_all_four_concurrent_activations_only_one_effective_expense(tmp_path,monkeypatch):
    async def run():
        import base64
        async with fixture(tmp_path,monkeypatch) as (_,f,c,receipt):
            approval=await create(c,'approval',receipt,identity=invoice(),activate=False)
            await request(c,'POST',f'/expense-approvals/{approval["id"]}/approve')
            ident=json.dumps(invoice());body={'payment_account_id':1,'voucher_base64':'data:image/png;base64,'+base64.b64encode(png()).decode()}
            responses=await asyncio.gather(
                c.post('/api/v1/payable',headers=auth(1),data={'supplier_id':'1','bill_number':'FOUR-RACE','bill_date':'2026-10-26','due_date':'2026-12-01','amount':'100','currency':'THB','request_key':uuid.uuid4().hex,'invoice_identity':ident},files={'file':('p.png',png(),'image/png')}),
                c.post(f'/api/v1/expense-approvals/{approval["id"]}/pay',headers=auth(1),json=body),
                c.post('/api/v1/expense-fund/accounts/1/items',headers=auth(1),json={'supplier_id':1,'invoice_identity':invoice(),'request_key':uuid.uuid4().hex,'expense_date':'2026-10-26','category':'耗材','amount':100,'currency':'THB','description':'并发合成','receipt':receipt}),
                c.post('/api/v1/income-expense/expense',headers=auth(1),data={'supplier_id':'1','category_id':'1','account_id':'1','expense_date':'2026-10-26','amount':'100','currency':'THB','request_key':uuid.uuid4().hex,'invoice_identity':ident},files={'files':('p.png',png(),'image/png')}))
            assert sorted(r.status_code for r in responses)==[200,409,409,409],[(r.status_code,r.text) for r in responses]
            winner=next(i for i,r in enumerate(responses) if r.status_code==200)
            async with f() as db:
                roots=(await db.execute(select(CostIdentity))).scalars().all();assert sum(r.active for r in roots)==1
                a=await db.get(ExpenseApproval,approval['id']);assert a.status==('paid' if winner==1 else 'approved')
            s=await snapshot(f);assert s['balance']==(9900 if winner in (1,3) else 10000)
            assert s['expenses']==(1 if winner in (1,3) else 0) and s['fund_items']==(1 if winner==2 else 0) and s['bills']==(2 if winner==0 else 1)
            actual('four_way_race',{'winner':winner,'responses':[{'status':r.status_code,'body':r.json()} for r in responses],'snapshot':s})
    asyncio.run(run())


@pytest.mark.parametrize('old',[False,True])
def test_empty_old_repeat_migration_read_only_history_and_missing_guard(tmp_path,monkeypatch,old):
    async def run():
        from app.services.cost_identity_migration import migrate_cost_identities,ensure_cost_guards
        from scripts.audit_cost_identity_history import report
        from sqlalchemy import event
        async with fixture(tmp_path,monkeypatch) as (engine,f,c,receipt):
            if old:
                async with engine.begin() as conn:
                    for table in ('payable_bills','expense_approvals','expense_fund_items','expense_records'):
                        await conn.execute(text(f'ALTER TABLE {table} DROP COLUMN cost_identity_id'))
                    await conn.execute(text('DROP TABLE cost_identities'))
                    await conn.execute(text('UPDATE payable_bills SET paid_amount=NULL,status=\'voided\',invoice_identity_key=:key,invoice_identity=CAST(:doc AS JSON) WHERE id=1'),{'key':costs.parse_identity(invoice(),type('U',(),{'id':1})())[1],'doc':json.dumps({'issuer_identifier':'TAX-EXACT','series':'VAT/2026','number':'INV-01'})})
                    await conn.execute(text("INSERT INTO payable_bills(id,warehouse_id,supplier_id,bill_number,bill_date,due_date,amount,currency,paid_amount,status,invoice_identity_key,invoice_identity) VALUES(10,1,1,'LEGACY-CONFLICT','2020-01-01','2020-02-01',102,'THB',0,'pending',:key,CAST(:doc AS JSON))"),{'key':costs.parse_identity(invoice(),type('U',(),{'id':1})())[1],'doc':json.dumps({'issuer_identifier':'TAX-EXACT','series':'VAT/2026','number':'INV-01'})})
            async with engine.begin() as conn:
                before=(await conn.execute(text('SELECT id,amount,paid_amount,status,invoice_identity_key FROM payable_bills ORDER BY id'))).all()
                await migrate_cost_identities(conn);await migrate_cost_identities(conn)
                after=(await conn.execute(text('SELECT id,amount,paid_amount,status,invoice_identity_key FROM payable_bills ORDER BY id'))).all()
                assert before==after and (await conn.execute(text('SELECT count(*) FROM cost_identities'))).scalar_one()==0
                columns=(await conn.execute(text("SELECT table_name,is_nullable FROM information_schema.columns WHERE table_schema=current_schema() AND column_name='cost_identity_id'"))).all()
                assert len(columns)==4 and all(v[1]=='YES' for v in columns)
            writes=[]
            def trace(conn,cursor,statement,*args):
                if statement.lstrip().upper().startswith(('INSERT','UPDATE','DELETE')):writes.append(statement)
            event.listen(engine.sync_engine,'before_cursor_execute',trace)
            try:
                async with f() as db:
                    await db.execute(text('SET TRANSACTION READ ONLY'));scan=await report(db,1);await db.rollback()
                await request(c,'GET','/expense-identities/payable/1');assert not writes
            finally:event.remove(engine.sync_engine,'before_cursor_execute',trace)
            if old:
                assert len(scan['known_invoice_conflicts'])==1 and set(scan['known_invoice_conflicts'][0]['payable_ids'])=={1,10}
                # Unknown payment is not zero even when the legacy row says voided.
                blocked=await create(c,'fund_item',receipt,identity=invoice(),code=409)
                assert blocked['detail']['hard_duplicate']
            async with engine.begin() as conn:await conn.execute(text('DROP INDEX uq_cost_active_invoice'))
            before=await snapshot(f)
            await create(c,'expense',receipt,identity=invoice('GUARD'),amount=103,code=503)
            assert await snapshot(f)==before
            await request(c,'GET','/expense-identities/payable/1')
            actual('migration_'+str(old),{'before_after_equal':True,'empty_registry':True,'columns':[list(v) for v in columns],'history':scan,'read_dml':writes,'missing_guard_no_side_effect':before})
    asyncio.run(run())


def test_photo_failure_rolls_back_registry_and_disbursement_is_not_a_cost_root(tmp_path,monkeypatch):
    async def run():
        import app.services.image_utils as images
        from fastapi import HTTPException
        async with fixture(tmp_path,monkeypatch) as (_,f,c,receipt):
            original=images.save_image;before=await snapshot(f)
            def fail(*a,**k):raise HTTPException(500,'本机合成图片保存失败')
            monkeypatch.setattr(images,'save_image',fail)
            await create(c,'payable',receipt,identity=invoice(),code=500)
            assert await snapshot(f)==before
            monkeypatch.setattr(images,'save_image',original)
            topup=await request(c,'POST','/expense-fund/accounts/1/topup',json={'amount':500,'payment_account_id':1,'receive_date':'2026-10-26'})
            async with f() as db:
                assert (await db.execute(select(func.count(CostIdentity.id)))).scalar_one()==0
                expenses=(await db.execute(select(ExpenseRecord))).scalars().all();assert len(expenses)==1 and expenses[0].cost_identity_id is None
            actual('failure_transfer',{'before_after_failure_equal':before,'topup':topup,'after':await snapshot(f)})
    asyncio.run(run())


def test_new_writes_require_request_key_and_fund_request_binds_actual_account(tmp_path,monkeypatch):
    async def run():
        async with fixture(tmp_path,monkeypatch) as (_,f,c,receipt):
            before=await snapshot(f)
            results=[]
            for path,kwargs in [('/expense-approvals',{'json':{'amount':100,'purpose':'缺请求编号','expense_date':'2026-10-26'}}),
                ('/expense-fund/accounts/1/items',{'json':{'amount':100,'expense_date':'2026-10-26','category':'耗材','description':'缺请求编号','receipt':receipt}}),
                ('/income-expense/expense',{'data':{'amount':'100','category_id':'1','account_id':'1','expense_date':'2026-10-26','currency':'THB'}})]:
                results.append(await request(c,'POST',path,code=400,**kwargs))
            assert await snapshot(f)==before
            key=uuid.uuid4().hex;saved=await create(c,'fund_item',receipt,key=key,identity=invoice())
            async with f() as db:
                db.add(ExpenseFund(id=2,warehouse_id=1,employee_id=1,receive_date=datetime(2026,10,1),amount=10000,
                    remaining_balance=10000,status='active',purpose='另一合成备用金',currency='THB'));await db.commit()
            denied=await request(c,'POST','/expense-fund/accounts/2/items',code=409,json={
                'supplier_id':1,'invoice_identity':invoice(),'request_key':key,'amount':100,'expense_date':'2026-10-26',
                'category':'耗材','currency':'THB','description':'合成开销','receipt':receipt})
            async with f() as db:assert (await db.execute(select(func.count(ExpenseFundItem.id)))).scalar_one()==1
            actual('request_contract',{'missing_key':results,'saved':saved,'other_fund_denied':denied})
    asyncio.run(run())

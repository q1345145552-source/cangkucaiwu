"""客户发货：真实 PostgreSQL、HTTP、并发重试和零钱包变化。"""
import asyncio
import json
import os
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, func, text
from app.main import app
from app.models import User, Customer, PaymentAccount, IncomingFlow
from app.models.credit import CreditCustomer, CreditShipment, CreditRepayment
from app.models.data_change_history import DataChangeHistory
from app.services.account_balances import current_account_balances
from scripts.seed import _migrate_credit_shipments
from tests.test_incoming_operations import environment, URL
from tests.test_round2_permissions import auth

pytestmark = pytest.mark.skipif(not URL, reason='Requires explicit loopback PostgreSQL')
REPORT = {}
def actual(name, value):
    REPORT[name] = value
    if os.environ.get('CREDIT_SHIPMENT_TEST_REPORT'):
        Path(os.environ['CREDIT_SHIPMENT_TEST_REPORT']).write_text(json.dumps(REPORT,ensure_ascii=False,indent=2,default=str))

@pytest.fixture(autouse=True)
def retained_entries():
    """仅本模块及显式导入此 fixture 的历史测试验证保留的实现。

    生产入口仍无条件封闭；test_retired_operating_entries 不使用此 override。
    """
    from app.core.retired_entries import require_operating_entries_enabled
    sentinel = object()
    old = app.dependency_overrides.get(require_operating_entries_enabled, sentinel)
    app.dependency_overrides[require_operating_entries_enabled] = lambda: None
    try:
        yield
    finally:
        if old is sentinel:
            app.dependency_overrides.pop(require_operating_entries_enabled, None)
        else:
            app.dependency_overrides[require_operating_entries_enabled] = old


@asynccontextmanager
async def shipments_environment(tmp_path, monkeypatch):
    async with environment(tmp_path, monkeypatch) as (engine, factory, client):
        async with factory() as db:
            for uid in (3,4): (await db.get(User,uid)).extra_permissions=['账期管理']
            (await db.get(Customer,1)).company_name='客户A'
            db.add_all([Customer(id=2,warehouse_id=2,customer_code='FOREIGN',company_name='外仓客户'),
                Customer(id=3,warehouse_id=1,customer_code='B',company_name='客户B'),
                Customer(id=4,warehouse_id=1,customer_code='CNY',company_name='人民币客户',default_currency='CNY')])
            await db.flush()
            db.add_all([CreditCustomer(id=i,warehouse_id=2 if i==2 else 1,customer_id=i,credit_limit=10000,
                currency='CNY' if i==4 else 'THB',status='active') for i in (1,2,3,4)])
            await db.commit()
        yield engine, factory, client


def payload(**kw):
    return {'ship_date':'2026-09-30','order_count':3,'amount':'600.00','currency':'THB','order_no':'ROUND10-A',
        'remark':'3单运费，不是三条发货记录','request_key':uuid.uuid4().hex,**kw}

async def wallet(factory):
    from app.services.wallet import flow_query
    async with factory() as db:
        ac=await db.get(PaymentAccount,1)
        q=flow_query(db,[1]); rows=(await db.execute(select(q.c.amount,q.c.type))).all()
        return {'incoming_records':(await db.execute(select(func.count(IncomingFlow.id)))).scalar_one(),
            'wallet_flow_count':len(rows), 'wallet_income':sum(v for v,k in rows if k=='income'),
            'wallet_expense':sum(v for v,k in rows if k=='expense'), 'balance':float((await current_account_balances(db,[ac]))[1])}

async def post(c,cid=1,uid=1,**kw):
    r=await c.post(f'/api/v1/credit/{cid}/shipment',headers=auth(uid),json=payload(**kw)); assert r.status_code==200,r.text; return r.json()


def test_three_orders_one_fact_600_debt_and_no_wallet_changes(tmp_path,monkeypatch):
    async def run():
        async with shipments_environment(tmp_path,monkeypatch) as (_,f,c):
            before=await wallet(f); row=await post(c)
            assert row['order_count']==3 and row['amount']==row['current_debt']==600 and row['created']
            listed=(await c.get('/api/v1/credit/shipments?month=2026-09',headers=auth(1))).json()
            assert listed['total']==1 and listed['totals_by_currency']=={'THB':{'record_count':1,'order_count':3,'amount':600,'unknown_order_count_records':0}}
            detail=(await c.get('/api/v1/credit/1/detail?month=2026-09',headers=auth(1))).json()
            assert detail['shipment_totals']=={'record_count':1,'order_count':3,'unknown_order_count_records':0,'amount':600,'currency':'THB'}
            assert detail['shipments'][0]['customer_id']==1 and detail['shipments'][0]['warehouse_id']==1
            assert await wallet(f)==before=={'incoming_records':0,'wallet_flow_count':0,'wallet_income':0,'wallet_expense':0,'balance':0}
            actual('three_orders_600',{'response':row,'list':listed,'wallet_before':before,'wallet_after':await wallet(f)})
    asyncio.run(run())


def test_concurrent_retry_independent_identical_and_payload_conflict(tmp_path,monkeypatch):
    async def run():
        async with shipments_environment(tmp_path,monkeypatch) as (_,f,c):
            data=payload(); rs=await asyncio.gather(*[c.post('/api/v1/credit/1/shipment',headers=auth(1),json=data) for _ in range(10)])
            assert all(r.status_code==200 for r in rs),[(r.status_code,r.text) for r in rs]
            assert len({r.json()['id'] for r in rs})==1 and sum(r.json()['created'] for r in rs)==1
            for _ in range(3): assert not (await c.post('/api/v1/credit/1/shipment',headers=auth(1),json=data)).json()['created']
            assert (await c.post('/api/v1/credit/1/shipment',headers=auth(1),json={**data,'amount':'601'})).status_code==409
            assert (await c.post('/api/v1/credit/3/shipment',headers=auth(1),json=data)).status_code==409
            second=await post(c)
            assert second['current_debt']==1200
            async with f() as db:
                assert (await db.execute(select(func.count(CreditShipment.id)))).scalar_one()==2
                (await db.get(CreditCustomer,3)).credit_limit=500;await db.commit()
            limit=await asyncio.gather(*[c.post('/api/v1/credit/3/shipment',headers=auth(1),json=payload(amount='300')) for _ in range(2)])
            assert sorted(r.status_code for r in limit)==[200,400]
            actual('concurrent',{'requests':10,'sequential_retries':3,'first_record_ids':[r.json()['id'] for r in rs],
                'independent_same_amount_debt':1200,'credit_limit_parallel_status':[r.status_code for r in limit]})
    asyncio.run(run())


def test_edit_void_preserves_history_and_account_with_any_repayment_is_locked(tmp_path,monkeypatch):
    async def run():
        async with shipments_environment(tmp_path,monkeypatch) as (_,f,c):
            row=await post(c);sid=row['id']; data=payload(amount='450',order_count=2);data.pop('request_key')
            changed=await c.put(f'/api/v1/credit/1/shipment/{sid}',headers=auth(3),json=data)
            assert changed.status_code==200 and changed.json()['current_debt']==450
            void=await c.post(f'/api/v1/credit/1/shipment/{sid}/void',headers=auth(4),json={'reason':'录入批次错误'})
            assert void.status_code==200 and void.json()['current_debt']==0 and void.json()['status']=='voided'
            assert (await c.post(f'/api/v1/credit/1/shipment/{sid}/void',headers=auth(1),json={'reason':'重复'})).status_code==400
            detail=(await c.get('/api/v1/credit/1/detail',headers=auth(1))).json()
            assert len(detail['shipments'])==1 and detail['shipment_totals']['record_count']==0
            # Other aggregate consumers must not resurrect voided facts.
            for path in ['/credit','/credit/dashboard','/credit/alerts','/credit/assessment']:
                response=await c.get('/api/v1'+path,headers=auth(1));assert response.status_code==200,response.text
            async with f() as db:
                assert (await db.get(CreditShipment,sid)).voided_by==4
                assert (await db.execute(select(func.count(DataChangeHistory.id)).where(DataChangeHistory.module=='credit'))).scalar_one()==3
            row=await post(c,cid=3)
            async with f() as db:
                db.add(CreditRepayment(credit_customer_id=3,repayment_date=datetime(2026,10,1),amount=100));await db.commit()
            for method,path,body in [('PUT',f'/credit/3/shipment/{row["id"]}',data),('POST',f'/credit/3/shipment/{row["id"]}/void',{'reason':'试改'})]:
                r=await c.request(method,'/api/v1'+path,headers=auth(1),json=body);assert r.status_code==409 and '已有回款' in r.text
            assert (await wallet(f))['wallet_flow_count']==0
            actual('edit_void',{'after_edit_debt':450,'after_void_debt':0,'record_retained':True,'histories':3,'with_repayment_edit_void':409})
    asyncio.run(run())


def test_dates_currencies_customers_pagination_and_legacy_unknown_orders(tmp_path,monkeypatch):
    async def run():
        async with shipments_environment(tmp_path,monkeypatch) as (_,f,c):
            await post(c);await post(c,cid=3,amount='999',ship_date='2026-10-01')
            await post(c,cid=4,amount='200',currency='CNY',ship_date='2026-09-01')
            await post(c,cid=2,uid=7,amount='999')
            rows=(await c.get('/api/v1/credit/shipments?month=2026-09&page_size=1',headers=auth(1))).json()
            assert rows['total']==2 and len(rows['data'])==1
            assert {cur:t['amount'] for cur,t in rows['totals_by_currency'].items()}=={'THB':600,'CNY':200}
            for query,total,amount in [('customer_id=1&month=2026-09',1,600),('currency=CNY&month=2026-09',1,200),('month=2026-10',1,999),('month=2027-01',0,0),('start_date=2026-09-30&end_date=2026-09-30',1,600)]:
                r=(await c.get('/api/v1/credit/shipments?'+query,headers=auth(1))).json();assert r['total']==total;assert sum(x['amount'] for x in r['totals_by_currency'].values())==amount
            for q in ['month=2026-13','start_date=bad','start_date=2026-10-01&end_date=2026-09-01','currency=USD']:
                assert (await c.get('/api/v1/credit/shipments?'+q,headers=auth(1))).status_code==400
            assert (await c.post('/api/v1/credit/1/shipment',headers=auth(1),json=payload(currency='CNY'))).status_code==400
            async with f() as db:
                db.add(CreditShipment(credit_customer_id=1,ship_date=datetime(2026,12,31),amount=10));await db.commit()
            old=(await c.get('/api/v1/credit/shipments?month=2026-12',headers=auth(1))).json()
            assert old['data'][0]['order_count'] is None and old['totals_by_currency']['THB']['unknown_order_count_records']==1
            dashboard=(await c.get('/api/v1/credit/dashboard',headers=auth(1))).json()
            assert dashboard['total_debt'] is None and dashboard['currency_totals']['CNY']['total_debt']==200
            actual('filters',{'september':rows['totals_by_currency'],'october_THB':999,'foreign_999_excluded':True,'old_order_count':None})
    asyncio.run(run())


def test_permission_scope_ids_and_invalid_payload(tmp_path,monkeypatch):
    async def run():
        async with shipments_environment(tmp_path,monkeypatch) as (_,f,c):
            row=await post(c);sid=row['id'];statuses={}
            for uid in (2,5):
                for method,path,body in [('GET','/credit/shipments',None),('POST','/credit/1/shipment',payload()),('PUT',f'/credit/1/shipment/{sid}',{k:v for k,v in payload().items() if k!='request_key'}),('POST',f'/credit/1/shipment/{sid}/void',{'reason':'test'})]:
                    r=await c.request(method,'/api/v1'+path,headers=auth(uid),json=body);assert r.status_code==403
                statuses[str(uid)]=403
            for uid in (3,4): assert (await c.get('/api/v1/credit/shipments',headers=auth(uid))).status_code==200
            async with f() as db:
                (await db.get(User,3)).extra_permissions=[];await db.commit()
            assert (await c.get('/api/v1/credit/shipments',headers=auth(3))).status_code==403
            assert (await c.post('/api/v1/credit/1/shipment',headers=auth(3),json=payload())).status_code==403
            for uid,cid in [(1,2),(7,1)]: assert (await c.post(f'/api/v1/credit/{cid}/shipment',headers=auth(uid),json=payload())).status_code==403
            assert (await c.put(f'/api/v1/credit/3/shipment/{sid}',headers=auth(1),json={k:v for k,v in payload().items() if k!='request_key'})).status_code==404
            for path in ['/credit/shipments','/credit/1/detail']:
                r=await c.get('/api/v1'+path,headers={**auth(1),'X-Warehouse-ID':'2'});assert r.status_code==403
            assert (await c.post('/api/v1/credit',headers=auth(1),json={'customer_id':2,'credit_limit':1000})).status_code==403
            for kw in [{'order_count':0},{'order_count':1.5},{'amount':'0'},{'amount':'1.001'},{'ship_date':'2026-02-30'},{'request_key':''},{'currency':'USD'}]:
                r=await c.post('/api/v1/credit/1/shipment',headers=auth(1),json=payload(**kw));assert r.status_code==422,r.text
            actual('roles_and_scope',{'admin':200,'authorized_staff_supervisor':200,'without_permission':403,'labor_superadmin':403,'foreign_header':403,'foreign_record_in_parent':404,'foreign_customer':403})
    asyncio.run(run())


def test_failure_rolls_back_and_migration_old_new_repeat(tmp_path,monkeypatch):
    async def run():
        import app.services.credit_shipments as service
        async with shipments_environment(tmp_path,monkeypatch) as (engine,f,c):
            async def failed(*args,**kwargs): raise RuntimeError('isolated history failure')
            with monkeypatch.context() as mp:
                mp.setattr(service,'record_history',failed)
                async with AsyncClient(transport=ASGITransport(app=app,raise_app_exceptions=False),base_url='http://isolated') as transport:
                    r=await transport.post('/api/v1/credit/1/shipment',headers=auth(1),json=payload());assert r.status_code==500
            async with f() as db:
                assert (await db.execute(select(func.count(CreditShipment.id)))).scalar_one()==0
                db.add(CreditShipment(credit_customer_id=1,ship_date=datetime(2026,1,1),amount=123));(await db.get(CreditCustomer,1)).current_debt=123
                await db.commit()
            columns=['order_count','currency','request_key','request_fingerprint','status','updated_at','voided_by','voided_at','void_reason']
            async with engine.begin() as conn:
                # New schema migration and repeated startup.
                await _migrate_credit_shipments(conn);await _migrate_credit_shipments(conn)
                for col in columns: await conn.execute(text(f'ALTER TABLE credit_shipments DROP COLUMN {col} CASCADE'))
                await conn.execute(text('ALTER TABLE credit_customers DROP COLUMN currency'))
                await _migrate_credit_shipments(conn);await _migrate_credit_shipments(conn)
                old=(await conn.execute(text('SELECT amount,order_count,currency,request_key,status FROM credit_shipments'))).one()
                assert tuple(old)==(123,None,None,None,None)
                assert (await conn.execute(text('SELECT current_debt FROM credit_customers WHERE id=1'))).scalar_one()==123
            await post(c,amount='100')
            assert (await wallet(f))['wallet_flow_count']==0
            actual('migration_failure',{'new_and_old_upgrade_repeated':True,'historical_amount':123,'historical_order_count':None,'historical_status':None,'failure_record_count':0,'wallet_flows':0})
    asyncio.run(run())


def test_role_writes_year_bounds_currency_snapshot_and_savepoint_failure(tmp_path,monkeypatch):
    async def run():
        from sqlalchemy.ext.asyncio import AsyncConnection
        async with shipments_environment(tmp_path,monkeypatch) as (engine,f,c):
            for uid,value,when in [(3,'0.10','2026-12-31'),(4,'0.20','2027-01-01')]:
                row=await post(c,uid=uid,amount=value,ship_date=when,order_count=1)
                assert row['current_debt']==(.1 if uid==3 else .3)
            for month,value in [('2026-12',.1),('2027-01',.2)]:
                r=(await c.get('/api/v1/credit/shipments?month='+month,headers=auth(1))).json()
                assert r['total']==1 and r['totals_by_currency']['THB']['amount']==value
            async with f() as db:
                (await db.get(Customer,1)).default_currency='CNY'
                await db.commit()
            # Existing account keeps its explicit currency when customer defaults change.
            await post(c,amount='0.10',order_count=1)
            mismatch=await c.post('/api/v1/credit/1/shipment',headers=auth(1),json=payload(currency='CNY'))
            assert mismatch.status_code==400
            cockpit=(await c.get('/api/v1/dashboard/cockpit?month=2026-10',headers=auth(1))).json()
            assert {r['currency']:r['amount'] for r in cockpit['finance']['receivable_payable']['receivable']}['THB']==.4
            previews=(await c.get('/api/v1/reports/previews',headers=auth(1))).json()
            assert previews['previews']['credit']['preview_by_currency']['THB']==.4
            async with engine.begin() as conn:
                original=AsyncConnection.execute
                async def fail(self,statement,*args,**kwargs):
                    if 'ADD COLUMN IF NOT EXISTS order_count' in str(statement):
                        return await original(self,text('SELECT missing_round10_column'),*args,**kwargs)
                    return await original(self,statement,*args,**kwargs)
                with monkeypatch.context() as mp:
                    mp.setattr(AsyncConnection,'execute',fail)
                    with pytest.raises(Exception): await _migrate_credit_shipments(conn)
                assert (await conn.execute(text('SELECT 1'))).scalar_one()==1
                await _migrate_credit_shipments(conn)
            assert (await wallet(f))['wallet_flow_count']==0
            actual('edges',{'staff_create':200,'supervisor_create':200,'december':.1,'january':.2,'debt_after_cents':.4,
                'customer_default_changed_existing_account_still_THB':True,'migration_savepoint_error_outer_transaction_usable':True,'wallet_flow_count':0})
    asyncio.run(run())

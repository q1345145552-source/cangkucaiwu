"""Real loopback PostgreSQL: overview uses authorized active warehouses and actual wallet facts."""
import asyncio
import json
import os
from contextlib import asynccontextmanager
from datetime import date, datetime
from pathlib import Path

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select, text, event, delete

from app.main import app
from app.models import Warehouse, User, UserWarehouse, Customer, PaymentAccount, IncomingFlow, IncomeExpenseCategory, ExpenseRecord, RechargeDeclaration, AccountTransfer
from tests.test_incoming_operations import environment, URL
from tests.test_round2_permissions import auth

pytestmark = pytest.mark.skipif(not URL, reason='Requires explicitly configured local PostgreSQL')
RESULTS = {}
PERIOD = {'start_date':'2026-10-01','end_date':'2026-10-31'}


def actual(name, result):
    RESULTS[name] = result
    if os.environ.get('WAREHOUSE_SUMMARY_TEST_REPORT'):
        Path(os.environ['WAREHOUSE_SUMMARY_TEST_REPORT']).write_text(json.dumps(RESULTS,ensure_ascii=False,indent=2,default=str))


@asynccontextmanager
async def overview_environment(tmp_path, mp):
    async with environment(tmp_path,mp) as (engine,factory,client):
        async with factory() as db:
            db.add_all([Warehouse(id=3,name='空仓',code='EMPTY'),Warehouse(id=4,name='停用仓秘密',code='INACTIVE',is_active=False),Warehouse(id=5,name='外仓秘密',code='FOREIGN')])
            db.add(User(id=8,username='test-8',display_name='单仓管理员',password_hash='unused',role='warehouse_admin',warehouse_id=1))
            await db.flush()
            for uid in (1,3,4):
                (await db.get(User,uid)).extra_permissions=['报表中心']
                db.add(UserWarehouse(user_id=uid,warehouse_id=2))
            db.add_all([UserWarehouse(user_id=1,warehouse_id=3),UserWarehouse(user_id=1,warehouse_id=4)])
            db.add(UserWarehouse(user_id=8,warehouse_id=1))
            db.add(Customer(id=2,warehouse_id=2,customer_code='B-CUSTOMER',company_name='B测试客户'))
            db.add_all([PaymentAccount(id=3,warehouse_id=1,account_name='人民币A',account_number='-',account_type='cash',currency='CNY'),
                PaymentAccount(id=4,warehouse_id=2,account_name='人民币B',account_number='-',account_type='cash',currency='CNY'),
                PaymentAccount(id=5,warehouse_id=1,account_name='银行A',account_number='-',account_type='bank',currency='THB')])
            db.add_all([IncomeExpenseCategory(id=1,warehouse_id=1,name='运营费用',type='expense',category_group='operating'),IncomeExpenseCategory(id=2,warehouse_id=2,name='运营费用',type='expense',category_group='operating')])
            await db.flush()
            for wid,thb,cny,thbexp,cnyexp,cnyaccount in [(1,100,50,20,5,3),(2,200,70,40,7,4)]:
                db.add_all([IncomingFlow(warehouse_id=wid,account_id=wid,amount=thb,currency='THB',received_date=datetime(2026,10,20),payment_method='现金',entrant_id=1),
                    IncomingFlow(warehouse_id=wid,account_id=cnyaccount,amount=cny,currency='CNY',received_date=datetime(2026,10,20),payment_method='现金',entrant_id=1),
                    ExpenseRecord(warehouse_id=wid,category_id=wid,account_id=wid,amount=thbexp,currency='THB',expense_date=datetime(2026,10,20)),
                    ExpenseRecord(warehouse_id=wid,category_id=wid,account_id=cnyaccount,amount=cnyexp,currency='CNY',expense_date=datetime(2026,10,20)),
                    RechargeDeclaration(warehouse_id=wid,customer_id=wid,declare_date=datetime(2026,10,20),amount=999,currency='THB',declarer_id=1,match_status='unmatched')])
            db.add(AccountTransfer(warehouse_id=1,from_account_id=1,to_account_id=5,amount=10,currency='THB',transfer_date=date(2026,10,20),request_key='overview-internal',operator_id=1))
            await db.commit()
        yield engine,factory,client


async def get(c,uid=1,header=None,**params):
    headers=auth(uid)
    if header is not None:headers['X-Warehouse-ID']=str(header)
    return await c.get('/api/v1/dashboard/warehouse-summary',headers=headers,params={**PERIOD,**params})


def test_single_all_currency_counts_and_wallet_report_alignment(tmp_path,monkeypatch):
    async def run():
        async with overview_environment(tmp_path,monkeypatch) as (engine,_,c):
            statements=[]
            def track(conn,cursor,statement,*args):statements.append(statement)
            event.listen(engine.sync_engine,'before_cursor_execute',track)
            results={}
            try:
                for header,inc,exp,net,ids in [(1,100,20,80,[1]),(2,200,40,160,[2]),('all',300,60,240,[1,2,3])]:
                    r=await get(c,header=header);assert r.status_code==200,r.text;p=r.json();results[str(header)]=p
                    assert [w['warehouse_id'] for w in p['data']]==ids
                    assert p['totals']['income_by_currency']['THB']==inc and p['totals']['expense_by_currency']['THB']==exp and p['totals']['net_by_currency']['THB']==net
                    assert p['totals']['income_count']==p['totals']['expense_count']==2*(2 if header=='all' else 1)
                    assert p['totals']['total_income'] is None
                assert results['all']['totals']['income_by_currency']['CNY']==120
                assert results['all']['totals']['expense_by_currency']['CNY']==12
                assert results['all']['totals']['net_by_currency']['CNY']==108
                for header in (1,2):
                    report=await c.get('/api/v1/income-expense/monthly-summary',headers=auth(7 if header==2 else 8),params=PERIOD)
                    assert report.json()['income_by_currency']==results[str(header)]['totals']['income_by_currency']
                    assert report.json()['expense_by_currency']==results[str(header)]['totals']['expense_by_currency']
                assert not any(s.lstrip().upper().startswith(('INSERT','UPDATE','DELETE')) for s in statements)
            finally:event.remove(engine.sync_engine,'before_cursor_execute',track)
            actual('amounts',results)
    asyncio.run(run())


def test_office_roles_permission_membership_and_old_token_revocation(tmp_path,monkeypatch):
    async def run():
        async with overview_environment(tmp_path,monkeypatch) as (_,factory,c):
            results=[]
            for uid in (3,4):
                for wid,amount in [(1,100),(2,200)]:
                    r=await get(c,uid,header=wid);assert r.status_code==200 and r.json()['totals']['income_by_currency']['THB']==amount
                    results.append({'user':uid,'warehouse':wid,'status':r.status_code,'income_thb':amount})
                assert (await get(c,uid,header='all')).status_code==403
                cached_headers={**auth(uid),'X-Warehouse-ID':'2'}
                async with factory() as db:
                    await db.execute(delete(UserWarehouse).where(UserWarehouse.user_id==uid,UserWarehouse.warehouse_id==2));await db.commit()
                r=await c.get('/api/v1/dashboard/warehouse-summary',headers=cached_headers);assert r.status_code==403 and '测试仓2' not in r.text
                async with factory() as db:(await db.get(User,uid)).extra_permissions=[];await db.commit()
                r=await get(c,uid,header=1);assert r.status_code==403 and '无此操作权限' in r.text
            actual('office',{'positive':results,'old_token_removed_membership':403,'removed_report_permission':403,'office_all':403})
    asyncio.run(run())


def test_forged_batch_inactive_roles_and_unassigned_no_leak(tmp_path,monkeypatch):
    async def run():
        async with overview_environment(tmp_path,monkeypatch) as (engine,factory,c):
            cases=[{'header':5},{'header':4},{'header':'bad'},{'warehouse_id':5},{'warehouse_ids':[1,5]},
                {'header':1,'warehouse_id':2},{'header':'all','warehouse_ids':[1,4]}]
            replies=[]
            for options in cases:
                r=await get(c,**options);assert r.status_code==403 and '秘密' not in r.text and '300' not in r.text;replies.append({'options':options,'status':r.status_code,'body':r.json()})
            for uid in (2,5):
                r=await get(c,uid,header='all');assert r.status_code==403 and '测试仓' not in r.text
            good=await get(c,header='all',warehouse_ids=[1,2]);assert good.status_code==200 and good.json()['warehouse_count']==2
            empty=await get(c,header=3);assert empty.status_code==200 and empty.json()['data'][0]['income_count']==0 and empty.json()['totals']['total_income']==0
            async with factory() as db:
                await db.execute(delete(UserWarehouse).where(UserWarehouse.user_id==1));(await db.get(User,1)).warehouse_id=None;await db.commit()
            r=await get(c);assert r.status_code==200 and r.json()['data']==[] and r.json()['totals']['total_income']==0
            assert (await get(c,header=1)).status_code==403
            actual('guards',{'forged':replies,'super_labor':403,'valid_admin_batch':200,'empty_warehouse':empty.json(),'unassigned':r.json()})
    asyncio.run(run())


def test_dates_legacy_fields_and_failure_is_not_zero(tmp_path,monkeypatch):
    async def run():
        import app.services.warehouse_summary as service
        async with overview_environment(tmp_path,monkeypatch) as (_,_,c):
            r=await get(c,header=1);p=r.json();assert p['data'][0]['recharge_total']==999 and p['data'][0]['incoming_total'] is None
            assert p['data'][0]['incoming_total_by_currency']=={'THB':100,'CNY':50} and p['data'][0]['unmatched_count']==1
            old=await c.get('/api/v1/dashboard/warehouse-summary',headers=auth(1));assert old.status_code==200 and old.json()['start_date']=='0001-01-01'
            sept=await get(c,header=1,start_date='2026-09-01',end_date='2026-09-30');assert sept.json()['totals']['total_income']==0
            for params in [{'start_date':'not-date'},{'start_date':'2026-11-01','end_date':'2026-10-01'},{'month':'2026-13'}]:
                assert (await get(c,header=1,**params)).status_code==400
            async def fail(*args,**kwargs):raise RuntimeError('isolated database read failure')
            monkeypatch.setattr(service,'summarize',fail)
            async with AsyncClient(transport=ASGITransport(app=app,raise_app_exceptions=False),base_url='http://isolated') as http:
                r=await http.get('/api/v1/dashboard/warehouse-summary',headers=auth(1));assert r.status_code==500 and 'total_income' not in r.text
            actual('dates_and_failure',{'legacy_declaration_informational_only':999,'income_thb':100,'unmatched':1,'september_income':0,'invalid_date':400,'injected_read_error':500})
    asyncio.run(run())

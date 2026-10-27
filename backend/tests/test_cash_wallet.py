"""Real PostgreSQL: cash is a normal wallet account; operation IDs never duplicate money."""
import asyncio
import json
import os
import uuid
from contextlib import asynccontextmanager
from datetime import date,datetime
from pathlib import Path

import pytest
from sqlalchemy import select,func,text
from sqlalchemy.ext.asyncio import create_async_engine
from app.models import PaymentAccount,IncomeExpenseCategory,IncomeRecord,ExpenseRecord,User,AccountTransfer
from app.services.account_balances import current_account_balances
from scripts.seed import _migrate_manual_wallet_operations
from tests.test_incoming_operations import environment,URL,body
from tests.test_round2_permissions import auth

pytestmark=pytest.mark.skipif(not URL,reason='Requires configured loopback native PostgreSQL')
RESULTS={}
RANGE={'start_date':'2026-10-01','end_date':'2026-10-31'}


def actual(name,value):
    RESULTS[name]=value
    if os.environ.get('CASH_WALLET_TEST_REPORT'):
        Path(os.environ['CASH_WALLET_TEST_REPORT']).write_text(json.dumps(RESULTS,ensure_ascii=False,indent=2,default=str))


@asynccontextmanager
async def cash_environment(tmp_path,mp):
    import app.api.v1.payment_accounts as accounts
    import app.services.cost_funds_debt as dates
    mp.setattr(accounts,'thai_today',lambda:date(2026,10,20));mp.setattr(dates,'thai_today',lambda:date(2026,10,20))
    async with environment(tmp_path,mp) as (engine,factory,client):
        async with factory() as db:
            await db.execute(text("SELECT setval(pg_get_serial_sequence('payment_accounts','id'),2,true)"))
            db.add_all([IncomeExpenseCategory(id=1,warehouse_id=1,type='expense',name='运营费用',category_group='operating'),
                IncomeExpenseCategory(id=2,warehouse_id=1,type='income',name='其他收入',category_group='other')])
            for uid in (3,4):(await db.get(User,uid)).extra_permissions=['收款账户','运营收支','其他收支','到账流水','资金流水','报表中心']
            await db.commit()
        ids=[]
        for kind,name in [('cash','前台钱箱'),('bank','公司银行')]:
            r=await client.post('/api/v1/accounts',headers=auth(1),json={'account_name':name,'account_type':kind,'account_number':'',
                'opening_balance':0,'opening_balance_date':'2026-10-01','currency':'THB'})
            assert r.status_code==200,r.text;ids.append(r.json()['id'])
        yield engine,factory,client,*ids


async def balances(factory,*ids):
    async with factory() as db:
        accounts=(await db.execute(select(PaymentAccount).where(PaymentAccount.id.in_(ids)))).scalars().all()
        return {k:float(v) for k,v in (await current_account_balances(db,accounts)).items()}


def payment(account,key=None,amount=200):
    return {'category_id':1,'account_id':account,'amount':amount,'currency':'THB','expense_date':'2026-10-20','request_key':key or uuid.uuid4().hex,'remark':'cash payment'}


def receipt(account,key=None,amount=1000):
    return {'category_id':2,'account_id':account,'amount':amount,'currency':'THB','income_date':'2026-10-20','request_key':key or uuid.uuid4().hex,'remark':'cash receipt'}


def test_cash_receive_pay_transfer_reports_and_balances(tmp_path,monkeypatch):
    async def run():
        async with cash_environment(tmp_path,monkeypatch) as (_,factory,c,cash,bank):
            assert await balances(factory,cash,bank)=={cash:0,bank:0}
            r=await c.post('/api/v1/incoming',headers=auth(1),json=body(account_id=cash,payment_method='现金'))
            assert r.status_code==200 and await balances(factory,cash,bank)=={cash:1000,bank:0}
            r=await c.post('/api/v1/income-expense/expense',headers=auth(1),data=payment(cash,'cash-main-payment'))
            assert r.status_code==200,r.text
            assert await balances(factory,cash,bank)=={cash:800,bank:0}
            transfer={'from_account_id':cash,'to_account_id':bank,'amount':300,'transfer_date':'2026-10-20','request_key':'cash-main-transfer'}
            r=await c.post('/api/v1/accounts/transfers',headers=auth(1),json=transfer);assert r.status_code==200,r.text
            final=await balances(factory,cash,bank);assert final=={cash:500,bank:300}
            views={}
            for path in ['/income-expense/ledger','income-expense/monthly-summary','reports/income-expense']:
                r=await c.get('/api/v1/'+path.lstrip('/'),headers=auth(1),params=RANGE);assert r.status_code==200,r.text
                payload=r.json();views[path]=payload
                assert payload.get('income_by_currency',payload.get('total_income_by_currency'))=={'THB':1000}
                assert payload.get('expense_by_currency',payload.get('total_expense_by_currency'))=={'THB':200}
            ledger=views['/income-expense/ledger'];assert ledger['total']==4 and sum(r['is_internal_transfer'] for r in ledger['data'])==2
            report=await c.get('/api/v1/reports/cost-funds-debt',headers=auth(1),params=RANGE);assert report.status_code==200
            thb=next(b for b in report.json()['currencies'] if b['currency']=='THB')
            assert thb['costs']['total']==200
            api_balances=(await c.get('/api/v1/accounts',headers=auth(1))).json()['data']
            assert {a['id']:a['current_balance'] for a in api_balances if a['id'] in (cash,bank)}==final
            actual('primary',{'cash_start':0,'after_receipt':1000,'after_payment':800,'after_transfer':final,'total_funds':800,'income':1000,'expense':200,'ledger_rows':4,'internal_rows':2})
    asyncio.run(run())


def test_manual_cash_concurrent_retries_and_independent_identical_amounts(tmp_path,monkeypatch):
    async def run():
        import app.api.v1.income_expense as api
        async with cash_environment(tmp_path,monkeypatch) as (_,factory,c,cash,bank):
            for kind,payload in [('income',receipt(cash,'same-income')),('expense',payment(cash,'same-expense'))]:
                # Synchronize the real HTTP clients before calling the app. The
                # production cost lock serializes expense requests, so a barrier
                # inside account validation cannot be reached by all ten clients.
                barrier=asyncio.Barrier(10)
                args={'json':payload} if kind=='income' else {'data':payload}
                async def together():
                    await asyncio.wait_for(barrier.wait(),20)
                    return await c.post('/api/v1/income-expense/'+kind,headers=auth(1),**args)
                replies=await asyncio.gather(*(together() for _ in range(10)))
                assert all(r.status_code==200 for r in replies),[(r.status_code,r.text) for r in replies]
                assert len({r.json()['id'] for r in replies})==1 and sum(r.json()['created'] for r in replies)==1
                for _ in range(3):
                    r=await c.post('/api/v1/income-expense/'+kind,headers=auth(1),**args);assert r.status_code==200 and not r.json()['created']
                changed={**payload,'amount':payload['amount']+1}
                r=await c.post('/api/v1/income-expense/'+kind,headers=auth(1),**({'json':changed} if kind=='income' else {'data':changed}))
                assert r.status_code==409
            assert (await balances(factory,cash))[cash]==800
            for kind,payload in [('income',receipt(cash,'independent-income')),('expense',payment(cash,'independent-expense'))]:
                r=await c.post('/api/v1/income-expense/'+kind,headers=auth(1),**({'json':payload} if kind=='income' else {'data':payload}))
                assert r.status_code==200 and r.json()['created']
            async with factory() as db:
                assert (await db.execute(select(func.count(IncomeRecord.id)))).scalar_one()==2
                assert (await db.execute(select(func.count(ExpenseRecord.id)))).scalar_one()==2
            assert (await balances(factory,cash))[cash]==1600
            async with factory() as db:(await db.get(PaymentAccount,cash)).status='inactive';await db.commit()
            replay=await c.post('/api/v1/income-expense/expense',headers=auth(1),data=payment(cash,'same-expense'))
            assert replay.status_code==200 and not replay.json()['created']
            rejected=await c.post('/api/v1/income-expense/expense',headers=auth(1),data=payment(cash,'new-on-disabled'))
            assert rejected.status_code==400 and '停用' in rejected.text
            actual('manual_idempotency',{'concurrency_each':10,'retries_each':3,'first_income_rows':1,'first_expense_rows':1,'first_balance':800,'independent_income_rows':2,'independent_expense_rows':2,'final_balance':1600,'changed_payload':409})
    asyncio.run(run())


def test_transfer_concurrency_and_failures_are_atomic(tmp_path,monkeypatch):
    async def run():
        import app.services.data_history as history
        import app.api.v1.income_expense as manual
        async with cash_environment(tmp_path,monkeypatch) as (_,factory,c,cash,bank):
            assert (await c.post('/api/v1/income-expense/income',headers=auth(1),json=receipt(cash))).status_code==200
            p={'from_account_id':cash,'to_account_id':bank,'amount':300,'transfer_date':'2026-10-20','request_key':'transfer-once'}
            replies=await asyncio.gather(*[c.post('/api/v1/accounts/transfers',headers=auth(1),json=p) for _ in range(10)])
            assert all(r.status_code==200 for r in replies) and len({r.json()['id'] for r in replies})==1
            assert await balances(factory,cash,bank)=={cash:700,bank:300}
            r=await c.post('/api/v1/accounts/transfers',headers=auth(1),json={**p,'request_key':'another-transfer'});assert r.status_code==200
            assert await balances(factory,cash,bank)=={cash:400,bank:600}
            async def fail(*args,**kwargs):raise RuntimeError('isolated transaction fault after insert')
            original=history.record_history;monkeypatch.setattr(history,'record_history',fail)
            with pytest.raises(RuntimeError,match='isolated transaction fault'):
                await c.post('/api/v1/accounts/transfers',headers=auth(1),json={**p,'amount':100,'request_key':'failed-transfer'})
            monkeypatch.setattr(history,'record_history',original)
            original=manual.record_history;monkeypatch.setattr(manual,'record_history',fail)
            with pytest.raises(RuntimeError,match='isolated transaction fault'):
                await c.post('/api/v1/income-expense/expense',headers=auth(1),data=payment(cash,'failed-payment',100))
            monkeypatch.setattr(manual,'record_history',original)
            assert await balances(factory,cash,bank)=={cash:400,bank:600}
            async with factory() as db:
                assert (await db.execute(select(func.count(AccountTransfer.id)))).scalar_one()==2
                assert (await db.execute(select(func.count(ExpenseRecord.id)))).scalar_one()==0
            r=await c.post('/api/v1/income-expense/expense',headers=auth(1),data=payment(cash,'too-much',401))
            assert r.status_code==400 and '余额不足' in r.text
            async with factory() as db:(await db.get(PaymentAccount,cash)).status='inactive';await db.commit()
            replay=await c.post('/api/v1/accounts/transfers',headers=auth(1),json=p)
            assert replay.status_code==200 and replay.json()['id']==replies[0].json()['id']
            rejected=await c.post('/api/v1/accounts/transfers',headers=auth(1),json={**p,'request_key':'new-on-disabled'})
            assert rejected.status_code==400 and '停用' in rejected.text
            actual('atomicity',{'transfer_concurrency':10,'first_transfer_rows':1,'first_balances':{cash:700,bank:300},'second_independent_balances':{cash:400,bank:600},'after_two_injected_failures':{cash:400,bank:600},'transfer_rows':2,'expense_rows':0,'insufficient_payment':400})
    asyncio.run(run())


def test_cash_account_currency_warehouse_status_and_roles(tmp_path,monkeypatch):
    async def run():
        async with cash_environment(tmp_path,monkeypatch) as (_,factory,c,cash,bank):
            async with factory() as db:(await db.get(PaymentAccount,bank)).status='inactive';await db.commit()
            for path,payload,mode in [('income',receipt(cash),'json'),('expense',payment(cash),'data')]:
                no_key={k:v for k,v in payload.items() if k!='request_key'}
                r=await c.post('/api/v1/income-expense/'+path,headers=auth(1),**{mode:no_key});assert r.status_code==400 and '请求编号' in r.text
                for change in [{'account_id':2},{'currency':'CNY'},{'account_id':bank}]:
                    r=await c.post('/api/v1/income-expense/'+path,headers=auth(1),**{mode:{**payload,**change}});assert r.status_code==400
            transfer={'from_account_id':cash,'to_account_id':bank,'amount':1,'transfer_date':'2026-10-20','request_key':'invalid-transfer'}
            for target in (2,bank):
                assert (await c.post('/api/v1/accounts/transfers',headers=auth(1),json={**transfer,'to_account_id':target})).status_code==400
            async with factory() as db:
                a=await db.get(PaymentAccount,bank);a.status='active';a.currency='CNY';await db.commit()
            r=await c.post('/api/v1/accounts/transfers',headers=auth(1),json=transfer);assert r.status_code==400 and '同币种' in r.text
            async with factory() as db:(await db.get(PaymentAccount,bank)).currency='THB';await db.commit()
            r=await c.post('/api/v1/accounts/transfers',headers=auth(1),json=transfer);assert r.status_code==400 and '余额不足' in r.text
            for uid in (2,5):
                for path,payload in [('/accounts/transfers',{'from_account_id':cash,'to_account_id':bank,'amount':1,'transfer_date':'2026-10-20','request_key':uuid.uuid4().hex}),('/income-expense/income',receipt(cash)),('/incoming',body(account_id=cash))]:
                    assert (await c.post('/api/v1'+path,headers=auth(uid),json=payload)).status_code==403
                assert (await c.post('/api/v1/income-expense/expense',headers=auth(uid),data=payment(cash))).status_code==403
            async with factory() as db:(await db.get(User,4)).extra_permissions=[];await db.commit()
            assert (await c.post('/api/v1/income-expense/income',headers=auth(4),json=receipt(cash))).status_code==403
            assert await balances(factory,cash)=={cash:0}
            actual('guards',{'missing_cash_operation':400,'foreign_currency_inactive':400,'labor_super':403,'revoked_supervisor':403,'cash_unchanged':0})
    asyncio.run(run())


def test_transfer_same_key_different_account_pairs_never_duplicates(tmp_path,monkeypatch):
    async def run():
        import app.api.v1.payment_accounts as api
        async with cash_environment(tmp_path,monkeypatch) as (_,factory,c,cash,bank):
            assert (await c.post('/api/v1/income-expense/income',headers=auth(1),json=receipt(cash))).status_code==200
            other=[]
            for name,opening in [('另一现金',1000),('另一银行',0)]:
                r=await c.post('/api/v1/accounts',headers=auth(1),json={'account_name':name,'account_type':'cash' if opening else 'bank','account_number':'test','opening_balance':opening,'opening_balance_date':'2026-10-01','currency':'THB'})
                assert r.status_code==200;other.append(r.json()['id'])
            barrier=asyncio.Barrier(2);original=api.current_account_balances
            async def together(*args,**kwargs):
                await asyncio.wait_for(barrier.wait(),20);return await original(*args,**kwargs)
            monkeypatch.setattr(api,'current_account_balances',together)
            payloads=[{'from_account_id':source,'to_account_id':target,'amount':100,'transfer_date':'2026-10-20','request_key':'global-collision'} for source,target in [(cash,bank),tuple(other)]]
            replies=await asyncio.gather(*[c.post('/api/v1/accounts/transfers',headers=auth(1),json=p) for p in payloads])
            assert sorted(r.status_code for r in replies)==[200,409]
            result=await balances(factory,cash,bank,*other)
            assert sum(result.values())==2000 and sorted(result.values())==[0,100,900,1000]
            async with factory() as db:assert (await db.execute(select(func.count(AccountTransfer.id)))).scalar_one()==1
            actual('transfer_key_collision',{'simultaneous_disjoint_pairs':2,'responses':sorted(r.status_code for r in replies),'transfer_rows':1,'total_funds':2000,'balances':result})
    asyncio.run(run())


def test_manual_operation_migration_new_old_repeat_and_restart(tmp_path,monkeypatch):
    async def run():
        async with cash_environment(tmp_path,monkeypatch) as (engine,factory,c,cash,bank):
            async with factory() as db:
                db.add(IncomeRecord(warehouse_id=1,category_id=2,account_id=cash,amount=1000,currency='THB',income_date=datetime(2026,10,20)))
                db.add(ExpenseRecord(warehouse_id=1,category_id=1,account_id=cash,amount=200,currency='THB',expense_date=datetime(2026,10,20)))
                await db.commit()
            async with engine.begin() as conn:
                schema=(await conn.execute(text('SELECT current_schema()'))).scalar_one()
                await _migrate_manual_wallet_operations(conn);await _migrate_manual_wallet_operations(conn)
                for table in ['income_records','expense_records']:
                    await conn.execute(text(f'ALTER TABLE {table} DROP COLUMN request_key CASCADE'))
                    await conn.execute(text(f'ALTER TABLE {table} DROP COLUMN request_fingerprint'))
                await _migrate_manual_wallet_operations(conn);await _migrate_manual_wallet_operations(conn)
            restarted=create_async_engine(URL,connect_args={'server_settings':{'search_path':schema}})
            try:
                async with restarted.begin() as conn:
                    await _migrate_manual_wallet_operations(conn)
                    counts={}
                    for table,amount in [('income_records',1000),('expense_records',200)]:
                        rows=(await conn.execute(text(f'SELECT amount,request_key,request_fingerprint FROM {table}'))).all()
                        assert len(rows)==1 and rows[0]==(amount,None,None);counts[table]=len(rows)
            finally:await restarted.dispose()
            actual('migration',{'new_run_twice':True,'old_upgrade_twice':True,'new_connection_restart':True,'historical':counts,'old_keys_null':True,'amounts':[1000,200]})
    asyncio.run(run())

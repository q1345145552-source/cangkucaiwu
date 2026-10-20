"""Native PostgreSQL evidence for the month-only money range, not an HTTP-500 repair."""
import asyncio
import json
import os
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from io import BytesIO
from pathlib import Path

import pytest
from app.models import PaymentAccount
from app.models.income_expense import IncomeExpenseCategory, ExpenseRecord, IncomeRecord
from app.models.supplier import Supplier
from app.models.payable import PayableBill
from app.models.wallet import PayablePayment
from app.models.user import User
from sqlalchemy import text, event
from app.main import app
from app.database import get_db
from tests.test_incoming_operations import environment, URL
from tests.test_round2_permissions import auth

pytestmark = pytest.mark.skipif(not URL, reason='Requires configured loopback native PostgreSQL')
RESULTS = {}


def actual(name, value):
    RESULTS[name] = value
    if os.environ.get('MONTH_RANGE_TEST_REPORT'):
        Path(os.environ['MONTH_RANGE_TEST_REPORT']).write_text(json.dumps(RESULTS, ensure_ascii=False, indent=2, default=str))


@asynccontextmanager
async def month_environment(tmp_path, monkeypatch):
    import app.services.money_period as period
    import app.services.cost_funds_debt as projection
    monkeypatch.setattr(period, 'thai_today', lambda: date(2026,10,20))
    monkeypatch.setattr(projection, 'thai_today', lambda: date(2026,10,20))
    async with environment(tmp_path, monkeypatch) as (engine, factory, client):
        async with factory() as db:
            (await db.get(PaymentAccount, 1)).opening_balance = 10000
            db.add(IncomeExpenseCategory(id=1, warehouse_id=1, type='expense', name='月界测试', category_group='operating'))
            await db.flush()
            db.add_all([ExpenseRecord(id=1, warehouse_id=1, category_id=1, account_id=1, currency='THB',
                amount=200, expense_date=datetime(2026,9,15,12), remark='SEPTEMBER-200'),
                ExpenseRecord(id=2, warehouse_id=1, category_id=1, account_id=1, currency='THB',
                amount=300, expense_date=datetime(2026,10,15,12), remark='OCTOBER-300')])
            await db.commit()
        yield engine, factory, client


def test_month_only_has_both_bounds_and_matches_explicit_range(tmp_path, monkeypatch):
    async def run():
        async with month_environment(tmp_path, monkeypatch) as (_, factory, client):
            results = {}
            for month in ('2026-09', '2026-10'):
                response = await client.get('/api/v1/income-expense/expense', headers=auth(1), params={'month':month, 'currency':'THB'})
                assert response.status_code == 200, response.text
                results[month] = response.json()
            actual('month_only', results)
            assert results['2026-09']['totals_by_currency'] == {'THB':200}, results
            assert results['2026-10']['totals_by_currency'] == {'THB':300}, results
            assert [r['remark'] for r in results['2026-09']['data']] == ['SEPTEMBER-200']
            explicit = await client.get('/api/v1/income-expense/expense', headers=auth(1), params={
                'start_date':'2026-09-01','end_date':'2026-09-30','currency':'THB'})
            assert explicit.status_code == 200 and explicit.json() == results['2026-09']
    asyncio.run(run())


JSON_READS = ['/income-expense/expense', '/income-expense/monthly-summary', '/income-expense/ledger',
    '/income-expense/operating-dashboard', '/reports/income-expense', '/reports/cost-funds-debt',
    '/reports/cost-funds-debt/costs', '/reports/cost-funds-debt/flows']


def expense_total(path, payload, cur='THB'):
    if path in ('/income-expense/expense','/reports/cost-funds-debt/costs'):
        return payload['totals_by_currency'].get(cur,0)
    if path == '/reports/income-expense': return payload['total_expense_by_currency'].get(cur,0)
    if path == '/reports/cost-funds-debt':
        return next((b['costs']['total'] for b in payload['currencies'] if b['currency']==cur),0)
    return payload['expense_by_currency'].get(cur,0)


def test_month_list_total_and_reports_match_without_writes(tmp_path,monkeypatch):
    async def run():
        async with month_environment(tmp_path,monkeypatch) as (engine,factory,client):
            statements=[]
            def trace(conn,cursor,statement,*_):statements.append(statement)
            event.listen(engine.sync_engine,'before_cursor_execute',trace)
            checked=[]
            try:
                for month,last,amount in [('2026-09','30',200),('2026-10','31',300)]:
                    for path in JSON_READS:
                        response=await client.get('/api/v1'+path,headers=auth(1),params={'month':month})
                        assert response.status_code==200,(path,response.status_code,response.text)
                        assert expense_total(path,response.json())==amount,(path,response.text)
                        explicit=await client.get('/api/v1'+path,headers=auth(1),params={'start_date':month+'-01','end_date':month+'-'+last})
                        assert explicit.status_code==200 and explicit.json()==response.json(),(path,explicit.text,response.text)
                        checked.append({'month':month,'path':path,'status':200,'expense':amount,'explicit_range_equal':True})
                assert not any(s.lstrip().upper().startswith(('INSERT','UPDATE','DELETE')) for s in statements)
            finally:event.remove(engine.sync_engine,'before_cursor_execute',trace)
            actual('list_summary_reports',{'data':checked,'writes':0})
    asyncio.run(run())


def test_end_of_day_new_year_and_utc_boundary_ignore_database_timezone(tmp_path,monkeypatch):
    async def run():
        async with month_environment(tmp_path,monkeypatch) as (_,factory,client):
            async with factory() as db:
                first=await db.get(ExpenseRecord,1);first.amount=190;first.expense_date=datetime(2026,9,30,23,59,59,999999)
                second=await db.get(ExpenseRecord,2);second.amount=280;second.expense_date=datetime(2026,10,1)
                db.add_all([ExpenseRecord(id=3,warehouse_id=1,category_id=1,account_id=1,currency='THB',amount=370,expense_date=datetime(2026,12,31,23,59,59,999999)),
                    ExpenseRecord(id=4,warehouse_id=1,category_id=1,account_id=1,currency='THB',amount=460,expense_date=datetime(2027,1,1)),
                    ExpenseRecord(id=5,warehouse_id=1,category_id=1,account_id=1,currency='THB',amount=900,expense_date=datetime(2025,9,15)),
                    ExpenseRecord(id=6,warehouse_id=1,category_id=1,account_id=1,currency='THB',amount=800,expense_date=datetime(2027,9,15))])
                db.add(Supplier(id=1,warehouse_id=1,name='boundary supplier'));await db.flush()
                db.add(PayableBill(id=1,warehouse_id=1,supplier_id=1,bill_number='UTC-BOUNDARY',bill_date=datetime(2026,9,1),due_date=datetime(2027,2,1),amount=1000,paid_amount=100,legacy_paid_amount=0));await db.flush()
                for n,stamp,amount in [(1,'2026-09-30T16:59:59.999999+00:00',10),(2,'2026-09-30T17:00:00+00:00',20),
                    (3,'2026-12-31T16:59:59.999999+00:00',30),(4,'2026-12-31T17:00:00+00:00',40)]:
                    db.add(PayablePayment(id=n,warehouse_id=1,bill_id=1,account_id=1,currency='THB',amount=amount,
                        paid_at=datetime.fromisoformat(stamp),operator_id=1))
                await db.commit()
            previous=app.dependency_overrides.get(get_db)
            checked=[]
            try:
                async with factory() as db:
                    async def fixed_connection():yield db
                    app.dependency_overrides[get_db]=fixed_connection
                    for zone in ('UTC','Asia/Bangkok','America/Los_Angeles'):
                        await db.execute(text("SET TIME ZONE '"+zone+"'"))
                        assert (await db.execute(text("SELECT current_setting('TimeZone')"))).scalar_one()==zone
                        for month,amount in [('2025-09',900),('2026-09',200),('2026-10',300),('2026-12',400),('2027-01',500),('2027-09',800)]:
                            for path in ('/income-expense/expense','/reports/income-expense','/reports/cost-funds-debt'):
                                response=await client.get('/api/v1'+path,headers=auth(1),params={'month':month})
                                assert response.status_code==200 and expense_total(path,response.json())==amount,(zone,month,path,response.text)
                            checked.append({'server_timezone':zone,'month':month,'expense':amount})
                        cross=await client.get('/api/v1/income-expense/expense',headers=auth(1),params={'start_date':'2026-12-31','end_date':'2027-01-01'})
                        assert cross.status_code==200 and expense_total('/income-expense/expense',cross.json())==900
            finally:
                if previous is None:app.dependency_overrides.pop(get_db,None)
                else:app.dependency_overrides[get_db]=previous
            actual('thai_calendar_utc_year_boundaries',{'data':checked,'cross_year_two_days':900,
                'utc_165959_999999':'Thai previous day 23:59:59.999999','utc_170000':'Thai next day 00:00:00'})
    asyncio.run(run())


def test_month_keeps_currency_warehouse_other_filters_and_pagination(tmp_path,monkeypatch):
    async def run():
        async with month_environment(tmp_path,monkeypatch) as (_,factory,client):
            async with factory() as db:
                db.add(PaymentAccount(id=3,warehouse_id=1,account_name='CNY cash',account_type='cash',account_number='-',currency='CNY'))
                db.add(IncomeExpenseCategory(id=2,warehouse_id=2,type='expense',name='foreign',category_group='operating'));await db.flush()
                db.add_all([ExpenseRecord(id=3,warehouse_id=1,category_id=1,account_id=3,currency='CNY',amount=50,expense_date=datetime(2026,9,20)),
                    ExpenseRecord(id=4,warehouse_id=2,category_id=2,account_id=2,currency='THB',amount=999,expense_date=datetime(2026,9,15),remark='FOREIGN-DO-NOT-READ')])
                for uid in (3,4):(await db.get(User,uid)).extra_permissions=['运营收支','其他收支','报表中心','资金流水']
                await db.commit()
            for uid in (1,3,4):
                for path in JSON_READS:
                    response=await client.get('/api/v1'+path,headers=auth(uid),params={'month':'2026-09','page_size':1})
                    assert response.status_code==200 and 'FOREIGN-DO-NOT-READ' not in response.text,(uid,path,response.text)
                    assert expense_total(path,response.json(),'THB')==200 and expense_total(path,response.json(),'CNY')==50
            pages=[]
            for page in (1,2):
                r=await client.get('/api/v1/income-expense/expense',headers=auth(1),params={'month':'2026-09','page':page,'page_size':1})
                assert r.status_code==200 and r.json()['total']==2 and len(r.json()['data'])==1
                assert r.json()['totals_by_currency']=={'THB':200,'CNY':50}
                pages.append(r.json())
            for filters,expected in [({'currency':'THB'},{'THB':200}),({'account_id':3},{'CNY':50}),({'category_id':2},{}),({'cost_category':'月界测试','currency':'THB'},{'THB':200})]:
                r=await client.get('/api/v1/income-expense/expense',headers=auth(1),params={'month':'2026-09',**filters})
                assert r.status_code==200 and r.json()['totals_by_currency']==expected,(filters,r.text)
            foreign=await client.get('/api/v1/income-expense/expense',headers=auth(7),params={'month':'2026-09','currency':'THB'})
            assert foreign.status_code==200 and expense_total('/income-expense/expense',foreign.json())==999
            for uid in (2,5):assert (await client.get('/api/v1/income-expense/expense',headers=auth(uid),params={'month':'2026-09'})).status_code==403
            async with factory() as db:
                (await db.get(User,3)).extra_permissions=[];await db.commit()
            assert (await client.get('/api/v1/income-expense/expense',headers=auth(3),params={'month':'2026-09'})).status_code==403
            actual('scope_currency_pages',{'THB':200,'CNY':50,'other_warehouse_own_total':999,'pages':pages,'revoked_labor_super':403})
    asyncio.run(run())


def test_invalid_month_year_and_dates_are_clear_400_without_new_contract(tmp_path,monkeypatch):
    async def run():
        async with month_environment(tmp_path,monkeypatch) as (_,factory,client):
            bad=[{'month':m} for m in ('9','09','2026-9','2026-00','2026-13','0000-01','10000-01','2026-09-01','','2026-09 ')]
            bad += [{'year':'2026'},{'month':'2026-09','year':'2026'},{'month':'09','year':'2026'},
                {'start_date':'20260901'},{'end_date':'2026-09-31'},{'start_date':'2026-09-30','end_date':'2026-09-01'},
                {'month':'2026-09','start_date':'2026-10-01'},{'month':'2026-09','end_date':'2026-08-31'}, {'start_date':''}]
            results=[]
            for path in JSON_READS+['/income-expense/income','/income-expense/income/export','/income-expense/ledger/export','/reports/cost-funds-debt/advances']:
                for params in bad:
                    r=await client.get('/api/v1'+path,headers=auth(1),params=params)
                    assert r.status_code==400 and isinstance(r.json()['detail'],str),(path,params,r.status_code,r.text)
                    results.append({'path':path,'params':params,'status':400,'detail':r.json()['detail']})
            for params,amount in [({'month':'2026-09','start_date':'2026-08-01','end_date':'2026-09-20'},200),
                ({'month':'2026-09','start_date':'2026-09-20'},0),({'month':'2027-12'},0),({'month':'2024-02'},0),({'month':'9999-12'},0)]:
                r=await client.get('/api/v1/income-expense/expense',headers=auth(1),params=params)
                assert r.status_code==200 and expense_total('/income-expense/expense',r.json())==amount,(params,r.text)
            # Round 5 aligns no-date records with the page and summary's current-month default.
            current=await client.get('/api/v1/income-expense/expense',headers=auth(1))
            assert current.status_code==200 and expense_total('/income-expense/expense',current.json())==300
            all_time=await client.get('/api/v1/income-expense/expense',headers=auth(1),params={'start_date':'1900-01-01'})
            assert all_time.status_code==200 and expense_total('/income-expense/expense',all_time.json())==500
            summary=await client.get('/api/v1/income-expense/monthly-summary',headers=auth(1))
            assert summary.status_code==200 and summary.json()['start_date']=='2026-10-01' and summary.json()['end_date']=='2026-10-20' and expense_total('/income-expense/monthly-summary',summary.json())==300
            actual('invalid_inputs',results)
            actual('defaults_and_intersection',{'unfiltered_expense':300,'explicit_history':500,'default_summary_october_to_today':300,'month_and_dates':'intersection; disjoint is 400','future_leap_max_year':200})
    asyncio.run(run())


def test_income_and_excel_include_entire_last_day_with_same_bounds(tmp_path,monkeypatch):
    async def run():
        import openpyxl
        async with month_environment(tmp_path,monkeypatch) as (_,factory,client):
            async with factory() as db:
                db.add(IncomeExpenseCategory(id=2,warehouse_id=1,type='income',name='other',category_group='other'));await db.flush()
                db.add_all([IncomeRecord(id=1,warehouse_id=1,category_id=2,account_id=1,currency='THB',amount=80,income_date=datetime(2026,9,30,23,59,59,999999),remark='LAST-DAY'),
                    IncomeRecord(id=2,warehouse_id=1,category_id=2,account_id=1,currency='THB',amount=90,income_date=datetime(2026,10,1),remark='NEXT-MONTH')]);await db.commit()
            for params in ({'month':'2026-09'},{'start_date':'2026-09-01','end_date':'2026-09-30'}):
                listed=await client.get('/api/v1/income-expense/income',headers=auth(1),params=params)
                assert listed.status_code==200 and listed.json()['total']==1 and listed.json()['data'][0]['amount']==80
                exported=await client.get('/api/v1/income-expense/income/export',headers=auth(1),params=params)
                assert exported.status_code==200
                rows=list(openpyxl.load_workbook(BytesIO(exported.content)).active.values)
                assert len(rows)==2 and rows[1][2]=='LAST-DAY' and rows[1][3]==80
                ledger=await client.get('/api/v1/income-expense/ledger/export',headers=auth(1),params=params)
                assert ledger.status_code==200
                table=list(openpyxl.load_workbook(BytesIO(ledger.content)).active.values)
                assert len(table)==3 and 'NEXT-MONTH' not in str(table)
            actual('income_export_last_day',{'included':'2026-09-30 23:59:59.999999','amount':80,'excluded':'2026-10-01 00:00:00','income_rows':1,'ledger_rows':2})
    asyncio.run(run())

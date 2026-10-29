"""Warehouse-card HTTP contract on isolated SQLite and opt-in loopback PostgreSQL."""
import asyncio
import json
import os
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from urllib.parse import urlparse

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.database as database
from app.main import app
from app.models import (AccountTransfer, Employee, EmployeeAdvance, ExpenseFund, ExpenseFundItem,
    ExpenseRecord, IncomeExpenseCategory, IncomingFlow, PaymentAccount, PayableBill,
    Supplier, User, UserWarehouse, Warehouse)
from app.models.attendance import LeaveRequest, RestDay
from app.models.attendance_exemption import AttendanceExemption
from app.models.clock_in_records import ClockInRecord
from app.models.expense_fund import FundRechargeRequest
from app.models.overtime import OvertimeAssignment, OvertimeTask
from app.services import wallet, warehouse_cards
from tests.test_round2_permissions import auth

DAY = date(2026, 10, 30)
NOW = datetime(2026, 10, 30, 9)
PATH = '/api/v1/dashboard/warehouse-cards'


@asynccontextmanager
async def environment(tmp_path, mp, warehouse_count=2):
    url = os.environ.get('WAREHOUSE_CARDS_DATABASE_URL')
    admin, schema = None, 'warehouse_cards_' + uuid.uuid4().hex
    if url:
        assert urlparse(url).hostname in ('127.0.0.1', 'localhost'), 'Only isolated loopback databases allowed'
        admin = create_async_engine(url)
        async with admin.begin() as conn:
            await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine = create_async_engine(url, connect_args={'server_settings': {'search_path': schema}})
    else:
        engine = create_async_engine(f'sqlite+aiosqlite:///{tmp_path / "cards.db"}')
    factory = async_sessionmaker(engine, expire_on_commit=False)
    mp.setattr(database, 'async_session_factory', lambda: factory)
    mp.setattr(warehouse_cards, 'thai_today', lambda: DAY)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(database.Base.metadata.create_all)
        async with factory() as db:
            db.add_all([Warehouse(id=n, name=f'合成仓{n}', code=f'W{warehouse_count-n:02}')
                        for n in range(1, warehouse_count+1)])
            await db.flush()
            for uid, role in ((1,'warehouse_admin'),(2,'super_admin'),(3,'staff'),
                              (4,'supervisor'),(5,'warehouse_labor'),(6,'warehouse_admin')):
                db.add(User(id=uid, username=f'cards-{uid}', display_name=f'合成账号{uid}',
                    password_hash='unused', role=role, warehouse_id=1, extra_permissions=[]))
            await db.flush()
            for uid in range(1,6):
                db.add_all([UserWarehouse(user_id=uid, warehouse_id=n) for n in range(1,warehouse_count+1)])
            for wid in range(1,warehouse_count+1):
                db.add(Supplier(id=wid, warehouse_id=wid, name=f'合成供应商{wid}'))
                db.add(PaymentAccount(id=wid, warehouse_id=wid, account_name=f'合成THB{wid}',
                    account_number='synthetic', account_type='cash', currency='THB'))
                db.add(IncomeExpenseCategory(id=wid, warehouse_id=wid, name='合成支出', type='expense'))
            await db.commit()
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://isolated-test') as client:
            yield engine, factory, client
    finally:
        await engine.dispose()
        if admin:
            async with admin.begin() as conn:
                await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            await admin.dispose()


async def get(client, uid=1, header=None):
    headers = auth(uid)
    if header is not None:
        headers['X-Warehouse-ID'] = header
    return await client.get(PATH, headers=headers)


def by_id(response):
    assert response.status_code == 200, response.text
    return {r['warehouse_id']: r for r in response.json()['data']}


def employee(eid, wid=1, **values):
    return Employee(id=eid, warehouse_id=wid, name=f'合成员工{eid}', **{'status':'regular', **values})


async def add_people(db):
    db.add_all([employee(101), employee(102,2)])
    await db.flush()


async def add_todo(db, key, wid, done=False):
    eid = 100 + wid
    if key == 'employee_advances':
        db.add(EmployeeAdvance(warehouse_id=wid, employee_id=eid, amount=10, advance_date=DAY,
            period='2026-10', approval_status='approved' if done else 'pending', status='unpaid'))
    elif key.startswith('overtime_'):
        task = OvertimeTask(warehouse_id=wid, date=DAY, start_time='18:00', end_time='19:00',
            created_by=1, needs_verification=key.endswith('verification'), status='completed' if done else 'pending')
        db.add(task)
        await db.flush()
        db.add(OvertimeAssignment(overtime_id=task.id, employee_id=eid, confirmed=done,
            actual_hours=None if key.endswith('verification') else 1, has_dispute=False))
    elif key == 'expense_fund_review':
        fund = ExpenseFund(warehouse_id=wid, employee_id=1, amount=0, receive_date=NOW, purpose='合成')
        db.add(fund)
        await db.flush()
        db.add(ExpenseFundItem(fund_id=fund.id, expense_date=NOW, category='合成', amount=1,
            description='合成开销', review_status='approved' if done else 'pending'))
    elif key == 'purchase_approval':
        from app.models.supplier import PurchaseOrder
        db.add(PurchaseOrder(warehouse_id=wid, supplier_id=wid, order_number=uuid.uuid4().hex,
            total_amount=1, items=[], status='confirmed' if done else 'pending'))
    elif key == 'receipt_review':
        db.add(PayableBill(warehouse_id=wid, supplier_id=wid, bill_number=uuid.uuid4().hex,
            bill_date=NOW, due_date=NOW, amount=1, status='voided' if done else 'pending', need_boss_confirm='true'))


def test_two_warehouses_do_not_mix(tmp_path, monkeypatch):
    async def run():
        async with environment(tmp_path, monkeypatch) as (_, factory, client):
            async with factory() as db:
                await add_people(db)
                for wid, amount in ((1,123),(2,456)):
                    db.add(IncomingFlow(warehouse_id=wid, received_date=NOW, amount=amount,
                        currency='THB', payment_method='现金', entrant_id=1))
                    await add_todo(db, 'purchase_approval', wid)
                await add_todo(db, 'purchase_approval', 2)
                await db.commit()
            data=by_id(await get(client))
            assert data[1]['income_by_currency']==[{'currency':'THB','amount':'123.00'}]
            assert data[2]['income_by_currency']==[{'currency':'THB','amount':'456.00'}]
            assert [data[n]['todos']['purchase_approval'] for n in (1,2)]==[1,2]
            assert all(data[n]['has_data'] for n in (1,2))
    asyncio.run(run())


@pytest.mark.parametrize('key', warehouse_cards.TODO_KEYS)
def test_each_todo_pending_and_completed(tmp_path, monkeypatch, key):
    async def run():
        async with environment(tmp_path, monkeypatch) as (_, factory, client):
            async with factory() as db:
                await add_people(db)
                await add_todo(db,key,1)
                await add_todo(db,key,1,True)
                await db.commit()
            data=by_id(await get(client))
            assert data[1]['todos'][key]==1
            assert data[1]['todos']['total']==1
            assert data[2]['todos']['total']==0
    asyncio.run(run())


def test_verified_advance_and_cross_warehouse_employee(tmp_path, monkeypatch):
    async def run():
        async with environment(tmp_path, monkeypatch) as (_, factory, client):
            async with factory() as db:
                await add_people(db)
                for eid,status,voided in ((101,'verified',False),(101,'pending',True),(102,'pending',False)):
                    db.add(EmployeeAdvance(warehouse_id=1, employee_id=eid, amount=1, advance_date=DAY,
                        period='2026-10', approval_status=status, status='voided' if voided else 'unpaid'))
                await db.commit()
            assert by_id(await get(client))[1]['todos']['employee_advances']==1
    asyncio.run(run())


def test_fund_review_includes_pending_recharge(tmp_path, monkeypatch):
    async def run():
        async with environment(tmp_path, monkeypatch) as (_, factory, client):
            async with factory() as db:
                fund=ExpenseFund(warehouse_id=1,employee_id=1,amount=0,receive_date=NOW,purpose='合成')
                db.add(fund); await db.flush()
                for wid,status in ((1,'pending'),(1,'approved'),(2,'pending')):
                    db.add(FundRechargeRequest(fund_id=fund.id,warehouse_id=wid,applicant_id=1,amount=1,status=status))
                db.add(ExpenseFundItem(fund_id=fund.id,expense_date=NOW,category='测试',amount=1,
                    description='已作废',review_status='pending',voided_at=NOW))
                await db.commit()
            data=by_id(await get(client))
            assert data[1]['todos']['expense_fund_review']==1
            assert data[2]['todos']['expense_fund_review']==0
    asyncio.run(run())


def test_receipt_amount_difference_without_flag(tmp_path, monkeypatch):
    async def run():
        async with environment(tmp_path,monkeypatch) as (_,factory,client):
            async with factory() as db:
                for status,confirmed in (('pending',8),('pending',10),('voided',8)):
                    db.add(PayableBill(warehouse_id=1,supplier_id=1,bill_number=uuid.uuid4().hex,
                        bill_date=NOW,due_date=NOW,amount=10,confirmed_amount=confirmed,status=status,need_boss_confirm='false'))
                await db.commit()
            assert by_id(await get(client))[1]['todos']['receipt_review']==1
    asyncio.run(run())


def test_wallet_matches_direct_totals_and_excludes_transfers(tmp_path, monkeypatch):
    async def run():
        async with environment(tmp_path,monkeypatch) as (_,factory,client):
            async with factory() as db:
                for wid in (1,2):
                    for cur,mult in (('THB',1),('CNY',2)):
                        db.add(IncomingFlow(warehouse_id=wid,received_date=NOW,amount=100*wid*mult,
                            currency=cur,payment_method='现金',entrant_id=1))
                        db.add(ExpenseRecord(warehouse_id=wid,category_id=wid,expense_date=NOW,
                            amount=20*wid*mult,currency=cur))
                    db.add(AccountTransfer(warehouse_id=wid,from_account_id=1,to_account_id=2,
                        transfer_date=DAY,amount=9999,currency='THB',operator_id=1,request_key=uuid.uuid4().hex))
                await db.commit()
            response=await get(client); data=by_id(response)
            async with factory() as db:
                for wid in (1,2):
                    expected={(cur,kind):format(wallet.money(amount),'.2f') for cur,kind,amount in await wallet.totals(db,[wid],DAY,DAY)}
                    for kind in ('income','expense'):
                        assert {r['currency']:r['amount'] for r in data[wid][kind+'_by_currency']}=={
                            cur:amount for (cur,k),amount in expected.items() if k==kind}
                    assert data[wid]['income_by_currency']==[{'currency':'CNY','amount':f'{200*wid}.00'}, {'currency':'THB','amount':f'{100*wid}.00'}]
            print('WAREHOUSE_CARDS_RAW_JSON',json.dumps(response.json(),ensure_ascii=False))
    asyncio.run(run())


@pytest.mark.parametrize('leave_type,expected', [('full',0),('',0),(None,0),('hours',1),('morning',1),('afternoon',1)])
def test_attendance_leave_types(tmp_path,monkeypatch,leave_type,expected):
    async def run():
        async with environment(tmp_path,monkeypatch) as (_,factory,client):
            async with factory() as db:
                db.add(employee(101,user_id=5)); await db.flush()
                db.add(LeaveRequest(warehouse_id=1,employee_id=101,leave_date=DAY,status='approved',duration_type=leave_type,hours=2))
                db.add(ClockInRecord(warehouse_id=1,user_id=5,clock_date=DAY,session=1))
                await db.flush()
                if leave_type is None:
                    await db.execute(text('UPDATE leave_requests SET duration_type = NULL'))
                await db.commit()
            assert by_id(await get(client))[1]['attendance']=={'expected':expected,'actual':expected}
    asyncio.run(run())


def test_attendance_exemption_afternoon_voided_and_distinct_people(tmp_path,monkeypatch):
    async def run():
        async with environment(tmp_path,monkeypatch) as (_,factory,client):
            async with factory() as db:
                for uid in (101,102,103):
                    db.add(User(id=uid,username=f'labor-{uid}',display_name=f'合成{uid}',password_hash='unused',role='warehouse_labor',warehouse_id=1))
                await db.flush()
                db.add_all([employee(101,user_id=101),employee(102,user_id=102),employee(103,user_id=103),employee(104,2)])
                db.add(AttendanceExemption(warehouse_id=2,date=DAY,reason='合成豁免',created_by=1,created_by_name='测试',status='active'))
                for uid,session,status in ((101,2,'normal'),(102,1,'voided'),(103,1,'normal'),(103,1,'normal')):
                    db.add(ClockInRecord(warehouse_id=1,user_id=uid,clock_date=DAY,session=session,status=status))
                await db.commit()
            data=by_id(await get(client))
            assert data[1]['attendance']=={'expected':3,'actual':1}
            assert data[2]['attendance']=={'expected':0,'actual':0}
    asyncio.run(run())


def test_population_helper_and_rest_day(tmp_path,monkeypatch):
    async def run():
        async with environment(tmp_path,monkeypatch) as (_,factory,client):
            async with factory() as db:
                supervisor=await db.get(User,4)
                db.add_all([employee(101,user_id=4),employee(102,status='resigned')])
                await db.flush()
                supervisor.attendance_enabled=True; supervisor.attendance_employee_id=101
                db.add(RestDay(warehouse_id=1,employee_id=101,rest_date=DAY))
                await db.commit()
            assert by_id(await get(client))[1]['attendance']=={'expected':0,'actual':0}
    asyncio.run(run())


def test_disabled_unassigned_empty_and_sorting(tmp_path,monkeypatch):
    async def run():
        async with environment(tmp_path,monkeypatch) as (_,factory,client):
            response=await get(client)
            assert [r['warehouse_id'] for r in response.json()['data']]==[2,1]
            assert all(not r['has_data'] for r in response.json()['data'])
            async with factory() as db:
                (await db.get(Warehouse,2)).is_active=False
                db.add(Warehouse(id=3,name='未分配',code='A'))
                await db.commit()
            assert list(by_id(await get(client)))==[1]
            assert (await get(client,6)).json()['data']==[]  # Primary warehouse is not membership.
    asyncio.run(run())


@pytest.mark.parametrize('uid,status', [(1,200),(3,200),(4,200),(5,403),(2,403)])
def test_role_contract(tmp_path,monkeypatch,uid,status):
    async def run():
        async with environment(tmp_path,monkeypatch) as (_,_,client):
            assert (await get(client,uid)).status_code==status
    asyncio.run(run())


@pytest.mark.parametrize('uid',[1,3,4])
def test_header_is_ignored_but_old_scope_guards_remain(tmp_path,monkeypatch,uid):
    async def run():
        async with environment(tmp_path,monkeypatch) as (_,_,client):
            reference=(await get(client,uid)).json()
            for header in ('all','1','2','999999','invalid'):
                response=await get(client,uid,header)
                assert response.status_code==200,response.text
                assert response.json()==reference
            old=await client.get('/api/v1/dashboard/boss-todos',headers={**auth(uid),'X-Warehouse-ID':'999999'})
            assert old.status_code==403
            assert (await client.post(PATH,headers=auth(uid),json={})).status_code==405
    asyncio.run(run())


def test_eight_warehouses_constant_sql_and_read_only(tmp_path,monkeypatch):
    async def run():
        async with environment(tmp_path,monkeypatch,8) as (engine,factory,client):
            async with factory() as db:
                db.add_all([employee(100+n,n) for n in range(1,9)])
                await db.commit()
            statements=[]
            def capture(conn,cursor,statement,parameters,context,executemany):
                statements.append(statement)
            event.listen(engine.sync_engine,'before_cursor_execute',capture)
            try:
                data=by_id(await get(client))
            finally:
                event.remove(engine.sync_engine,'before_cursor_execute',capture)
            assert len(data)==8
            assert all(sql.lstrip().upper().startswith('SELECT') for sql in statements)
            assert len(statements)==11, len(statements)
            assert all(row['attendance']=={'expected':1,'actual':0} for row in data.values())
            print('EIGHT_WAREHOUSE_SQL_COUNT',len(statements))
    asyncio.run(run())


def test_unauthenticated(tmp_path,monkeypatch):
    async def run():
        async with environment(tmp_path,monkeypatch) as (_,_,client):
            assert (await client.get(PATH)).status_code==403
    asyncio.run(run())


def test_legacy_attendance_account_map_and_inactive_employees(tmp_path,monkeypatch):
    async def run():
        async with environment(tmp_path,monkeypatch) as (_,factory,client):
            async with factory() as db:
                db.add_all([employee(101,phone='cards-5'), employee(102,user_id=3),
                    employee(103,is_deleted=True), employee(104,hire_date=NOW+timedelta(days=1))])
                db.add(ClockInRecord(warehouse_id=1,user_id=5,clock_date=DAY,session=1))
                await db.commit()
            assert by_id(await get(client))[1]['attendance']=={'expected':1,'actual':1}
    asyncio.run(run())


def test_thai_day_excludes_other_business_dates(tmp_path,monkeypatch):
    async def run():
        async with environment(tmp_path,monkeypatch) as (_,factory,client):
            async with factory() as db:
                for offset in (-1,0,1):
                    db.add(IncomingFlow(warehouse_id=1,received_date=NOW+timedelta(days=offset),
                        amount=100,currency='THB',payment_method='现金',entrant_id=1))
                await db.commit()
            response=await get(client)
            assert response.json()['date']=='2026-10-30'
            assert response.json()['timezone']=='Asia/Bangkok'
            assert by_id(response)[1]['income_by_currency']==[{'currency':'THB','amount':'100.00'}]
    asyncio.run(run())

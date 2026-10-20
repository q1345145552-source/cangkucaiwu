"""Round 6 reuses the round-5 money-record contract against loopback native PostgreSQL."""
import asyncio
import json
import os
from contextlib import asynccontextmanager
from datetime import date,datetime
from io import BytesIO
from pathlib import Path

import pytest
from openpyxl import load_workbook
from sqlalchemy import select,func,event
from app.models import (User,PaymentAccount,IncomeExpenseCategory,IncomeRecord,ExpenseRecord,Employee,
    IncomingFlow,RechargeDeclaration)
from app.models.employee_advance import EmployeeAdvance
from tests.test_incoming_operations import environment,URL
from tests.test_round2_permissions import auth
from tests.test_money_record_scope import check_scope,read,RANGE

pytestmark=pytest.mark.skipif(not URL,reason='Requires configured loopback native PostgreSQL')
RESULTS={}


def actual(name,value):
    RESULTS[name]=value
    if os.environ.get('OTHER_CURRENCY_TEST_REPORT'):
        Path(os.environ['OTHER_CURRENCY_TEST_REPORT']).write_text(json.dumps(RESULTS,ensure_ascii=False,indent=2,default=str))


@asynccontextmanager
async def other_environment(tmp_path,mp):
    import app.services.cost_funds_debt as dates
    mp.setattr(dates,'thai_today',lambda:date(2026,10,20))
    async with environment(tmp_path,mp) as (engine,factory,client):
        async with factory() as db:
            db.add_all([PaymentAccount(id=3,warehouse_id=1,account_name='人民币现金',account_type='cash',account_number='3',currency='CNY'),
                PaymentAccount(id=4,warehouse_id=1,account_name='停用账户',account_type='cash',account_number='4',currency='THB',status='inactive'),
                IncomeExpenseCategory(id=1,warehouse_id=1,type='income',name='其他收入',category_group='other'),
                IncomeExpenseCategory(id=2,warehouse_id=1,type='expense',name='其他支出',category_group='other'),
                IncomeExpenseCategory(id=3,warehouse_id=1,type='income',name='运营收入',category_group='operating'),
                IncomeExpenseCategory(id=4,warehouse_id=2,type='income',name='外仓分类',category_group='other')])
            for uid in (3,4):(await db.get(User,uid)).extra_permissions=['其他收支']
            await db.commit()
        yield engine,factory,client


async def create(client,amount,currency,account,uid=1):
    r=await client.post('/api/v1/income-expense/income',headers=auth(uid),json={'category_id':1,'account_id':account,
        'amount':amount,'currency':currency,'income_date':'2026-10-20','remark':currency+'-'+str(amount)})
    assert r.status_code==200,r.text
    return r.json()['id']


def test_two_currencies_filter_full_page_totals_and_export(tmp_path,monkeypatch):
    async def run():
        async with other_environment(tmp_path,monkeypatch) as (_,factory,client):
            await create(client,100,'THB',1);await create(client,200,'CNY',3)
            all_rows,summary,sheet=await check_scope(client,'income',{'THB':100,'CNY':200},2,category_group='other')
            assert summary['total_income'] is None  # No mixed-currency scalar or zero fallback.
            pages=[]
            for page in (1,2):
                data=await read(client,'income',category_group='other',page=page,page_size=1)
                assert len(data['data'])==1 and data['total']==2 and data['totals_by_currency']=={'THB':100,'CNY':200}
                pages.append(data['data'][0]['currency'])
            assert set(pages)=={'THB','CNY'}
            filtered={}
            for cur,amt in [('THB',100),('CNY',200)]:
                data,_,_=await check_scope(client,'income',{cur:amt},1,category_group='other',currency=cur)
                assert data['data'][0]['currency']==cur and data['data'][0]['amount']==amt
                filtered[cur]={'rows':1,'amount':amt}
            for uid in (3,4):await check_scope(client,'income',{'THB':100,'CNY':200},2,uid=uid,category_group='other')
            actual('two_currencies',{'all':all_rows['totals_by_currency'],'rows':2,'mixed_scalar':summary['total_income'],
                'filtered':filtered,'page_size_1_currencies':pages,'export_rows':len(sheet)-1,'source':'money_records'})
    asyncio.run(run())


def test_other_group_dates_accounts_search_foreign_and_invalid_states(tmp_path,monkeypatch):
    async def run():
        async with other_environment(tmp_path,monkeypatch) as (engine,factory,client):
            await create(client,100,'THB',1);await create(client,200,'CNY',3)
            async with factory() as db:
                db.add_all([IncomeRecord(id=10,warehouse_id=1,category_id=1,account_id=1,amount=50,currency='THB',income_date=datetime(2026,9,15),remark='SEPTEMBER-50'),
                    IncomeRecord(id=11,warehouse_id=1,category_id=3,account_id=1,amount=700,currency='THB',income_date=datetime(2026,10,20),remark='OPERATING-DO-NOT-MIX'),
                    IncomeRecord(id=12,warehouse_id=2,category_id=4,account_id=2,amount=999,currency='THB',income_date=datetime(2026,10,20),remark='SECRET-WH2-999'),
                    IncomingFlow(id=1,warehouse_id=1,account_id=1,amount=500,currency='THB',received_date=datetime(2026,10,20),entrant_id=1),
                    RechargeDeclaration(warehouse_id=1,customer_id=1,declare_date=datetime(2026,10,20),amount=777,currency='THB',declarer_id=1),
                    Employee(id=1,warehouse_id=1,name='test worker',hire_date=datetime(2026,10,1))])
                await db.flush()
                for eid,amount,account,cur in [(1,20,1,'THB'),(2,30,3,'CNY'),(3,10,1,'THB'),(4,11,1,'THB'),(5,12,1,'THB')]:
                    db.add(ExpenseRecord(id=eid,warehouse_id=1,category_id=2,account_id=account,amount=amount,currency=cur,expense_date=datetime(2026,10,20)))
                await db.flush()
                for eid,approval,state in [(3,'pending','unpaid'),(4,'rejected','unpaid'),(5,'approved','voided')]:
                    db.add(EmployeeAdvance(warehouse_id=1,employee_id=1,amount=eid+7,advance_date=date(2026,10,20),period='2026-10',
                        approval_status=approval,status=state,expense_record_id=eid))
                await db.commit()
            statements=[]
            def trace(conn,cursor,statement,*_):statements.append(statement)
            event.listen(engine.sync_engine,'before_cursor_execute',trace)
            scenarios=[({'account_id':1},{'THB':100},1),({'account_id':3},{'CNY':200},1),({'account_id':2},{},0),
                ({'category_id':1},{'THB':100,'CNY':200},2),({'category_id':3},{},0),({'category_id':4},{},0),
                ({'search':'THB-100'},{'THB':100},1),({'search':'CNY-200'},{'CNY':200},1),({'search':'missing'},{},0),
                ({'start_date':'2026-09-01','end_date':'2026-09-30'},{'THB':50},1),({'end_date':'2026-10-19'},{},0)]
            try:
                for filters,expected,count in scenarios:
                    rows,_,_=await check_scope(client,'income',expected,count,category_group='other',**filters)
                    assert 'SECRET-WH2' not in json.dumps(rows)
                _,summary,_=await check_scope(client,'expense',{'THB':20,'CNY':30},2,category_group='other')
                assert summary['income_by_currency']=={'THB':100,'CNY':200} and summary['total_expense'] is None
                await check_scope(client,'income',{'THB':999},1,uid=7,category_group='other')
                for uid in (2,5):
                    for path in ('income','income/export','expense','expense/export','monthly-summary'):
                        r=await client.get('/api/v1/income-expense/'+path,headers=auth(uid),params={**RANGE,'category_group':'other'})
                        assert r.status_code==403
                assert not any(s.lstrip().upper().startswith(('INSERT','UPDATE','DELETE')) for s in statements)
            finally:event.remove(engine.sync_engine,'before_cursor_execute',trace)
            actual('filters_and_expense',{'income':{'THB':100,'CNY':200},'expense':{'THB':20,'CNY':30},'scenarios':len(scenarios),
                'foreign_warehouse':999,'excluded_pending_rejected_voided':33,'unreceived_declaration_excluded':777,'writes_on_reads':0,'labor_and_super':403})
    asyncio.run(run())


def test_create_edit_account_currency_warehouse_and_permissions(tmp_path,monkeypatch):
    async def run():
        async with other_environment(tmp_path,monkeypatch) as (_,factory,client):
            payload={'category_id':1,'account_id':1,'amount':100,'currency':'THB','income_date':'2026-10-20'}
            blocked=[]
            for change,message in [({'currency':'CNY'},'账户币种不一致'),({'account_id':2},'账户不存在或不属于当前仓库'),
                ({'account_id':4},'账户已停用'),({'category_id':4},'收支分类不存在或不属于当前仓库')]:
                r=await client.post('/api/v1/income-expense/income',headers=auth(1),json={**payload,**change})
                assert r.status_code==400 and r.json()['detail']==message,r.text
                blocked.append({'params':change,'status':400,'detail':message})
            async with factory() as db: assert (await db.execute(select(func.count(IncomeRecord.id)))).scalar_one()==0
            rid=await create(client,100,'THB',1)
            r=await client.put(f'/api/v1/income-expense/income/{rid}',headers=auth(1),json={**payload,'currency':'CNY'})
            assert r.status_code==400 and r.json()['detail']=='账户币种不一致'
            rows=await read(client,'income',category_group='other');assert rows['totals_by_currency']=={'THB':100}
            r=await client.put(f'/api/v1/income-expense/income/{rid}',headers=auth(1),json={**payload,'currency':'CNY','account_id':3,'amount':200})
            assert r.status_code==200,r.text
            await check_scope(client,'income',{'CNY':200},1,category_group='other')
            for uid in (2,5):
                r=await client.post('/api/v1/income-expense/income',headers=auth(uid),json=payload)
                assert r.status_code==403
            actual('account_validation',{'blocked':blocked,'bad_edit':400,'bad_edit_retains':{'THB':100},'valid_edit':{'CNY':200},'labor_super_create':403})
    asyncio.run(run())

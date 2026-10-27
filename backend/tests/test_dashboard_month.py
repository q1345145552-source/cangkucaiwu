"""Real PostgreSQL calendar-month dashboard and same-response cards/charts."""
import asyncio
import json
import os
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import select, func, delete, event
from app.models import Warehouse, User, UserWarehouse, PaymentAccount, IncomingFlow, ExpenseRecord, IncomeExpenseCategory, RechargeDeclaration, AccountTransfer
from tests.test_incoming_operations import environment, URL
from tests.test_round2_permissions import auth

pytestmark=pytest.mark.skipif(not URL,reason='Requires explicitly configured local PostgreSQL')
RESULTS={}


def actual(name,result):
    RESULTS[name]=result
    if os.environ.get('DASHBOARD_MONTH_TEST_REPORT'):
        Path(os.environ['DASHBOARD_MONTH_TEST_REPORT']).write_text(json.dumps(RESULTS,ensure_ascii=False,indent=2,default=str))


@asynccontextmanager
async def dashboard_environment(tmp_path,mp):
    import app.api.v1.dashboard as dashboard
    mp.setattr(dashboard,'thai_today',lambda:date(2026,10,20))
    async with environment(tmp_path,mp) as (engine,factory,client):
        async with factory() as db:
            db.add_all([Warehouse(id=3,name='空仓',code='EMPTY'),Warehouse(id=4,name='外仓秘密',code='PRIVATE'),Warehouse(id=5,name='停用仓秘密',code='DISABLED',is_active=False)])
            await db.flush()
            db.add_all([UserWarehouse(user_id=1,warehouse_id=2),UserWarehouse(user_id=1,warehouse_id=3),UserWarehouse(user_id=1,warehouse_id=5)])
            for uid in (3,4):db.add(UserWarehouse(user_id=uid,warehouse_id=2))
            db.add_all([PaymentAccount(id=3,warehouse_id=1,account_name='A人民币',account_number='-',account_type='cash',currency='CNY'),
                PaymentAccount(id=4,warehouse_id=2,account_name='B人民币',account_number='-',account_type='cash',currency='CNY'),
                PaymentAccount(id=5,warehouse_id=1,account_name='A银行',account_number='-',account_type='bank',currency='THB')])
            db.add_all([IncomeExpenseCategory(id=1,warehouse_id=1,name='运营费用',type='expense',category_group='operating'),IncomeExpenseCategory(id=2,warehouse_id=2,name='运营费用',type='expense',category_group='operating')])
            await db.flush()
            for wid,month,inc,exp,cnyinc,cnyexp in [(1,9,1000,200,100,10),(1,10,700,300,70,30),(2,9,500,50,50,5),(2,10,900,90,90,9)]:
                when=datetime(2026,month,15)
                for cur,account,received,paid in [('THB',wid,inc,exp),('CNY',wid+2,cnyinc,cnyexp)]:
                    db.add(IncomingFlow(warehouse_id=wid,account_id=account,amount=received,currency=cur,received_date=when,entrant_id=1,payment_method='现金'))
                    db.add(ExpenseRecord(warehouse_id=wid,category_id=wid,account_id=account,amount=paid,currency=cur,expense_date=when))
            db.add(RechargeDeclaration(warehouse_id=1,customer_id=1,declare_date=datetime(2026,9,15),amount=777,currency='THB',declarer_id=1))
            db.add(AccountTransfer(warehouse_id=1,from_account_id=1,to_account_id=5,amount=50,currency='THB',transfer_date=date(2026,9,15),request_key='month-internal',operator_id=1))
            await db.commit()
        yield engine,factory,client


def headers(uid=1,wid=1):return {**auth(uid),'X-Warehouse-ID':str(wid)}


def amounts(rows):return {r['currency']:r['amount'] for r in rows}


async def cockpit(c,month=None,uid=1,wid=1):
    return await c.get('/api/v1/dashboard/cockpit',headers=headers(uid,wid),params={'month':month} if month is not None else {})


def test_calendar_month_cards_daily_graphs_counts_and_same_scope_report(tmp_path,monkeypatch):
    async def run():
        async with dashboard_environment(tmp_path,monkeypatch) as (engine,_,c):
            statements=[]
            def track(conn,cursor,statement,*args):statements.append(statement)
            event.listen(engine.sync_engine,'before_cursor_execute',track);results={}
            try:
                for month,inc,exp,cnyinc,cnyexp,days in [('2026-09',1000,200,100,10,30),('2026-10',700,300,70,30,31)]:
                    r=await cockpit(c,month);assert r.status_code==200,r.text;p=r.json();card=p['finance']['month']
                    assert amounts(card['income'])=={'THB':inc,'CNY':cnyinc}
                    assert amounts(card['expense'])=={'THB':exp,'CNY':cnyexp}
                    assert amounts(card['net'])=={'THB':inc-exp,'CNY':cnyinc-cnyexp} and card['profit']==card['net']
                    assert card['income_count_by_currency']==card['expense_count_by_currency']=={'THB':1,'CNY':1}
                    for cur in ['THB','CNY']:
                        points=p['trends']['income_expense'][cur];funds=p['trends']['funds'][cur]
                        assert len(points)==days and all(x['date'].startswith(month) for x in points)
                        assert sum(x['income'] for x in points)==amounts(card['income'])[cur]
                        assert sum(x['expense'] for x in points)==amounts(card['expense'])[cur]
                        assert sum(x['incoming']+x['other_income'] for x in funds)==amounts(card['income'])[cur]
                        assert sum(x['amount'] for x in p['trends']['expense_categories'][cur])==amounts(card['expense'])[cur]
                    assert sum(x['recharge'] for x in p['trends']['funds']['THB'])==(777 if month=='2026-09' else 0)
                    report=await c.get('/api/v1/dashboard/warehouse-summary',headers=headers(),params={'month':month});assert report.status_code==200
                    assert report.json()['totals']['income_by_currency']==amounts(card['income'])
                    assert report.json()['totals']['expense_by_currency']==amounts(card['expense'])
                    standalone=await c.get('/api/v1/dashboard/trends',headers=headers(),params={'month':month});assert standalone.status_code==200 and standalone.json()==p['trends']
                    results[month]={'period':p['period'],'card':card,'chart_days':days,'chart_income':sum(x['income'] for x in p['trends']['income_expense']['THB']),'chart_expense':sum(x['expense'] for x in p['trends']['income_expense']['THB'])}
                assert (await cockpit(c)).json()['period']['month']=='2026-10'
                assert not any(s.lstrip().upper().startswith(('INSERT','UPDATE','DELETE')) for s in statements)
            finally:event.remove(engine.sync_engine,'before_cursor_execute',track)
            actual('months',results)
    asyncio.run(run())


def test_authorized_all_office_scope_denials_and_same_token_revocation(tmp_path,monkeypatch):
    async def run():
        async with dashboard_environment(tmp_path,monkeypatch) as (_,factory,c):
            results={}
            for month,inc,exp in [('2026-09',1500,250),('2026-10',1600,390)]:
                r=await cockpit(c,month,wid='all');assert r.status_code==200,r.text;p=r.json()
                assert [w['id'] for w in p['warehouses']]==[1,2,3]
                assert amounts(p['finance']['month']['income'])['THB']==inc and amounts(p['finance']['month']['expense'])['THB']==exp
                results[month]=p['finance']['month']
            assert (await cockpit(c,'2026-09',3,2)).status_code==403
            async with factory() as db:
                (await db.get(User,3)).extra_permissions=['报表中心'];await db.commit()
            for uid in (3,4):
                r=await cockpit(c,'2026-09',uid,2);assert r.status_code==(403 if uid==4 else 200)
                if uid==3:assert amounts(r.json()['finance']['month']['income'])['THB']==500
                assert (await cockpit(c,'2026-09',uid,'all')).status_code==403
                token=headers(uid,2)
                async with factory() as db:
                    await db.execute(delete(UserWarehouse).where(UserWarehouse.user_id==uid,UserWarehouse.warehouse_id==2));await db.commit()
                r=await c.get('/api/v1/dashboard/cockpit',headers=token,params={'month':'2026-09'});assert r.status_code==403 and '测试仓2' not in r.text
            for uid in (2,5):
                for path in ['/cockpit','/trends']:
                    r=await c.get('/api/v1/dashboard'+path,headers=headers(uid),params={'month':'2026-09'});assert r.status_code==403
            for wid in [4,5,'bad']:
                r=await cockpit(c,'2026-09',wid=wid);assert r.status_code==403 and '秘密' not in r.text
            actual('warehouses',{'all':results,'granted_office_b_income_thb':500,'office_all':403,'old_token_revoked':403,'labor_super':403,'foreign_inactive_bad':403})
    asyncio.run(run())


def test_month_year_local_midnight_utc_boundaries_empty_future_and_invalid(tmp_path,monkeypatch):
    async def run():
        from app.models import Reimbursement, ReimbursementPayment
        async with dashboard_environment(tmp_path,monkeypatch) as (_,factory,c):
            async with factory() as db:
                for when,value in [(datetime(2026,9,30,23,59,59),11),(datetime(2026,10,1),13),(datetime(2026,12,31,23,59,59),250),(datetime(2027,1,1),350)]:
                    db.add(IncomingFlow(warehouse_id=1,account_id=1,amount=value,currency='THB',received_date=when,entrant_id=1))
                for i,stamp,value in [(1,datetime(2026,9,30,16,59,59,tzinfo=timezone.utc),10),(2,datetime(2026,9,30,17,tzinfo=timezone.utc),11)]:
                    db.add(Reimbursement(id=i,warehouse_id=1,employee_id=1,total_amount=value,currency='THB',submit_date=datetime(2026,9,1),status='paid',funding_source='company_account'))
                    await db.flush()
                    db.add(ReimbursementPayment(reimbursement_id=i,warehouse_id=1,amount=value,currency='THB',funding_source='company_account',payment_account_id=1,previous_status='approved',paid_by_id=1,paid_by_name='test',paid_at=stamp,status='active'))
                await db.commit()
            expected={'2026-09':(1011,210),'2026-10':(713,311),'2026-12':(250,0),'2027-01':(350,0),'2024-02':(0,0),'2028-01':(0,0)};actuals={}
            for month,(income,expense) in expected.items():
                r=await cockpit(c,month);assert r.status_code==200,r.text;p=r.json();card=p['finance']['month']
                assert amounts(card['income'])['THB']==income and amounts(card['expense'])['THB']==expense
                assert sum(x['income'] for x in p['trends']['income_expense']['THB'])==income
                assert sum(x['expense'] for x in p['trends']['income_expense']['THB'])==expense
                if month=='2024-02':assert len(p['trends']['income_expense']['THB'])==29
                actuals[month]={'income_thb':income,'expense_thb':expense,'net_thb':income-expense}
            for month in ['','2026','2026-9','2026-00','2026-13','0000-01','not-month']:
                for path in ['/cockpit','/trends']:
                    r=await c.get('/api/v1/dashboard'+path,headers=headers(),params={'month':month});assert r.status_code==400,(month,r.text)
            empty=await cockpit(c,'2026-09',wid=3);assert empty.status_code==200 and amounts(empty.json()['finance']['month']['income'])=={'THB':0,'CNY':0}
            actual('boundaries',{'monthly':actuals,'invalid':400,'empty':0,'utc_before_17Z_in_september':10,'utc_at_17Z_in_october':11})
    asyncio.run(run())


def test_realtime_todos_follow_scope_and_efficiency_calendar_clips(tmp_path,monkeypatch):
    async def run():
        from app.models import Employee, EmployeeAdvance
        from app.models.clock_in_records import ClockInRecord
        from app.core.timezone import THAI_TZ
        async with dashboard_environment(tmp_path,monkeypatch) as (_,factory,c):
            async with factory() as db:
                db.add(User(id=9,username='worker-b',display_name='B员工',password_hash='unused',role='warehouse_labor',warehouse_id=2));await db.flush()
                db.add_all([Employee(id=1,warehouse_id=1,name='A员工',user_id=5,status='regular'),Employee(id=2,warehouse_id=2,name='B员工',user_id=9,status='regular')]);await db.flush()
                for wid in (1,2):db.add(EmployeeAdvance(warehouse_id=wid,employee_id=wid,amount=100*wid,advance_date=date(2026,10,20),period='2026-10',approval_status='pending'))
                for d in [date(2026,9,30),date(2026,10,1)]:
                    for session,hour in [(1,9),(2,17)]:db.add(ClockInRecord(warehouse_id=1,user_id=5,clock_date=d,session=session,clocked_in_at=datetime(d.year,d.month,d.day,hour,tzinfo=THAI_TZ)))
                await db.commit()
            results={}
            for month in ['2026-09','2026-10']:
                p=(await cockpit(c,month)).json();assert p['people']['efficiency']['person_times']==1
                results[month]=p['people']['efficiency']
            for wid,count in [(1,1),(2,1),('all',2)]:
                r=await c.get('/api/v1/dashboard/boss-todos',headers=headers(wid=wid));assert r.status_code==200 and r.json()['advances']['count']==count
                assert {x['warehouse_id'] for x in r.json()['advances']['items']}==({1,2} if wid=='all' else {wid})
            actual('realtime_and_efficiency',{'month_efficiency':results,'pending_advance_a':1,'pending_advance_b':1,'pending_all':2,'pending_does_not_add_wallet_expense':True})
    asyncio.run(run())


def test_signed_adjustments_remain_in_cards_charts_and_failures_not_zero(tmp_path,monkeypatch):
    async def run():
        from httpx import AsyncClient, ASGITransport
        from app.main import app
        import app.services.dashboard_period as service
        async with dashboard_environment(tmp_path,monkeypatch) as (_,factory,c):
            async with factory() as db:
                db.add(IncomeExpenseCategory(id=3,warehouse_id=1,name='冲销',type='expense',category_group='operating'));await db.flush()
                db.add(ExpenseRecord(warehouse_id=1,category_id=3,account_id=1,amount=-50,currency='THB',expense_date=datetime(2026,10,16)));await db.commit()
            p=(await cockpit(c,'2026-10')).json();card=p['finance']['month'];assert amounts(card['expense'])['THB']==250 and amounts(card['net'])['THB']==450
            assert any(x['expense']==-50 for x in p['trends']['income_expense']['THB'])
            assert {'name':'冲销','amount':-50} in p['trends']['expense_categories']['THB']
            async def fail(*args,**kwargs):raise RuntimeError('isolated wallet read fault')
            monkeypatch.setattr(service,'monthly_view',fail)
            async with AsyncClient(transport=ASGITransport(app=app,raise_app_exceptions=False),base_url='http://isolated') as http:
                r=await http.get('/api/v1/dashboard/cockpit',headers=headers(),params={'month':'2026-10'});assert r.status_code==500 and 'finance' not in r.text
            actual('signed_and_failure',{'original_expense_thb':300,'adjustment_thb':-50,'expense_thb':250,'net_thb':450,'injected_fault':500})
    asyncio.run(run())


def test_procurement_split_payments_order_days_and_anomalies_share_selected_month(tmp_path,monkeypatch):
    async def run():
        from app.models import Supplier, PurchaseOrder, PayableBill, PayablePayment
        from app.models.supplier import ProcurementPriceAnomaly, ProcurementNonLowestRecord
        async with dashboard_environment(tmp_path,monkeypatch) as (_,factory,c):
            async with factory() as db:
                await db.execute(delete(ExpenseRecord).where(ExpenseRecord.warehouse_id==1,ExpenseRecord.currency=='THB'))
                db.add(Supplier(id=1,warehouse_id=1,name='测试供应商A'));await db.flush()
                db.add(PayableBill(id=1,warehouse_id=1,supplier_id=1,bill_number='AUG-PAID-LATER',bill_date=datetime(2026,8,1),due_date=datetime(2026,8,31),amount=500,paid_amount=500,legacy_paid_amount=0,currency='THB',status='paid'));await db.flush()
                for i,month,value in [(1,9,200),(2,10,300)]:
                    db.add(PayablePayment(id=i,warehouse_id=1,bill_id=1,account_id=1,amount=value,currency='THB',paid_at=datetime(2026,month,15,5,tzinfo=timezone.utc),operator_id=1))
                for i,(month,d) in enumerate([(9,15),(10,15),(10,16)],1):
                    stamp=datetime(2026,month,d,5,tzinfo=timezone.utc)
                    db.add(PurchaseOrder(warehouse_id=1,supplier_id=1,order_number='ORDER-'+str(i),total_amount=100,currency='THB',items=[],created_at=stamp))
                    db.add(ProcurementPriceAnomaly(warehouse_id=1,product_name='测试物料',purchase_price=100,created_at=stamp))
                    db.add(ProcurementNonLowestRecord(warehouse_id=1,product_name='测试物料',selected_price=100,created_at=stamp))
                await db.commit()
            results={}
            for month,paid,count in [('2026-09',200,1),('2026-10',300,2)]:
                p=(await cockpit(c,month)).json();proc=p['finance']['procurement']
                assert amounts(proc['expense'])['THB']==paid
                assert amounts(p['finance']['month']['expense'])['THB']==paid
                assert sum(x['amount'] for x in p['trends']['procurement_suppliers']['THB'])==paid
                assert p['trends']['procurement_suppliers']['THB'][0]['name']=='测试供应商A'
                assert sum(x['count'] for x in p['trends']['orders']['THB'])==count
                assert proc['price_anomaly_count']==proc['non_lowest_count']==count
                results[month]={'procurement_paid_thb':paid,'expense_card_thb':paid,'supplier_chart_thb':paid,'order_count':count,'price_anomaly':count,'non_lowest':count}
            actual('procurement',results)
    asyncio.run(run())

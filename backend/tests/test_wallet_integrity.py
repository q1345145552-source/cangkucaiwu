"""跨模块金额、付款归期、账户归属、事务回滚和权限的真实 HTTP 验收。"""
import asyncio
import uuid
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
import pytest
from sqlalchemy import select, func
from app.models import (PaymentAccount, IncomingFlow, CreditRepayment, CreditCustomer, CashAdvance,
    PayableBill, PayablePayment, Supplier, AccountTransfer)
from app.models.credit import CreditShipment
from app.models.payroll import PayrollRecord
from app.models.payable import PayablePlan
from tests.test_wallet_basis import clean, views, get, post, RANGE, fixed, prepare_bill
from tests.test_round2_permissions import auth


def test_internal_transfer_balances_only_no_income_or_expense_and_idempotency(tmp_path, monkeypatch):
    async def run():
        async with clean(tmp_path, monkeypatch) as (f,c):
            async with f() as db:
                db.add(PaymentAccount(id=3,warehouse_id=1,account_name='银行',account_type='bank',account_number='3',opening_balance=1000,currency='THB'))
                db.add(PaymentAccount(id=4,warehouse_id=1,account_name='人民币',account_type='bank',account_number='4',opening_balance=1000,currency='CNY'))
                await db.commit()
            before = await views(c)
            body={'from_account_id':1,'to_account_id':3,'amount':200,'transfer_date':'2026-10-20','request_key':'transfer-1'}
            a=await post(c,'/accounts/transfers',json=body)
            b=await post(c,'/accounts/transfers',json=body)
            assert a['id']==b['id']
            after=await views(c)
            for k in ('ledger_income','ledger_expense','company_income','company_expense','unified_cost','company_outflow'):
                assert after[k]==before[k]==0
            balances={a['id']:a['current_balance'] for a in (await get(c,'/accounts'))['data']}
            assert balances[1]==9800 and balances[3]==1200
            default=await get(c,'/income-expense/ledger',**RANGE)
            assert default['total']==2 and all(r['is_internal_transfer'] for r in default['data'])
            one=await get(c,'/income-expense/ledger',**RANGE,account_id=1)
            assert one['total_expense']==200
            for extra in ({'to_account_id':4,'request_key':'bad-cur'}, {'to_account_id':2,'request_key':'bad-wh'},
                {'to_account_id':1,'request_key':'same'}, {'amount':10001,'request_key':'over'},
                {'transfer_date':'2099-01-01','request_key':'future'}):
                r=await c.post('/api/v1/accounts/transfers',headers=auth(1),json={**body,**extra})
                if extra.get('request_key')=='over':
                    assert r.status_code==200 and r.json()['warning']['balance_after']==-201,r.text
                else:assert r.status_code==400,r.text
            for uid in (5,6):
                r=await c.post('/api/v1/accounts/transfers',headers=auth(uid),json=body)
                assert r.status_code==403
            async with f() as db: assert (await db.execute(select(func.count(AccountTransfer.id)))).scalar_one()==2
    asyncio.run(run())


def test_purchase_legacy_snapshot_plan_rollback_and_payment_request_idempotency(tmp_path, monkeypatch):
    async def run():
        import app.services.payable_payment as payment
        monkeypatch.setattr(payment,'thai_now',lambda:fixed(2026,10,20))
        async with clean(tmp_path, monkeypatch) as (f,c):
            async with f() as db:
                db.add(Supplier(id=1,warehouse_id=1,name='供应商'))
                db.add(PayableBill(id=1,warehouse_id=1,supplier_id=1,bill_number='LEGACY',bill_date=datetime(2026,9,1),due_date=datetime(2026,12,1),
                    amount=1000,paid_amount=300,paid_at=fixed(2026,9,30),currency='THB',status='partially_paid'))
                db.add(PayableBill(id=2,warehouse_id=1,supplier_id=1,bill_number='CNY',bill_date=datetime(2026,10,1),due_date=datetime(2026,12,1),amount=100,currency='CNY'))
                db.add(PayablePlan(id=1,warehouse_id=1,plan_name='混币种不得部分执行',planned_date=datetime(2026,10,20),total_amount=800,bill_ids=[1,2]))
                await db.commit()
            assert (await views(c,start_date='2026-09-01',end_date='2026-09-30'))['company_expense']==300
            r=await c.put('/api/v1/payable/plans/1/execute',params={'account_id':1},headers=auth(1))
            assert r.status_code==409  # Historical plan lacks verified preparation.
            await prepare_bill(f,c,1)
            await prepare_bill(f,c,2)
            created=await c.post('/api/v1/payable/plans',headers=auth(3),json={'plan_name':'合成混币种计划','planned_date':'2026-10-20','bill_ids':[1,2]})
            assert created.status_code==200,created.text
            mixed=await c.put(f'/api/v1/payable/plans/{created.json()["id"]}/execute',headers=auth(3),params={'account_id':1})
            assert mixed.status_code==409 and '币种' in mixed.text,mixed.text
            async with f() as db:
                assert (await db.get(PayableBill,1)).paid_amount==300
                assert (await db.execute(select(func.count(PayablePayment.id)))).scalar_one()==0
            params={'paid_amount':600,'account_id':1,'request_key':'purchase-one'}
            for _ in range(2):
                r=await c.put('/api/v1/payable/1/pay',params=params,headers=auth(3));assert r.status_code==200,r.text
            assert (await views(c))['company_expense']==600
            assert (await views(c,start_date='2026-09-01',end_date='2026-09-30'))['company_expense']==300
            async with f() as db:
                bill=await db.get(PayableBill,1)
                assert bill.legacy_paid_amount==300 and bill.paid_amount==900
                assert (await db.execute(select(func.count(PayablePayment.id)))).scalar_one()==1
            r=await c.put('/api/v1/payable/1/void',params={'void_reason':'只取消未付余额'},headers=auth(1));assert r.status_code==200
            assert (await views(c))['unified_cost']==600
    asyncio.run(run())


def test_credit_existing_receipt_not_counted_twice_and_warehouse_currency_amount_validation(tmp_path, monkeypatch):
    async def run():
        async with clean(tmp_path, monkeypatch) as (f,c):
            async with f() as db:
                db.add(CreditCustomer(id=1,warehouse_id=1,customer_id=1,credit_limit=10000,current_debt=1000))
                db.add(CreditShipment(credit_customer_id=1,ship_date=datetime(2026,10,1),amount=1000))
                db.add(IncomingFlow(id=1,warehouse_id=1,received_date=datetime(2026,10,20),amount=300,currency='THB',account_id=1,entrant_id=1))
                await db.commit()
            before=await views(c)
            body={'repayment_date':'2026-10-20','amount':300,'incoming_flow_id':1}
            r=await post(c,'/credit/1/payment',json=body)
            assert r['current_debt']==700
            assert (await views(c))['company_income']==before['company_income']==300
            r=await c.post('/api/v1/credit/1/payment',headers=auth(1),json=body);assert r.status_code==400
            for extra in ({'incoming_flow_id':999}, {'amount':200}, {'repayment_date':'2026-10-19'}):
                r=await c.post('/api/v1/credit/1/payment',headers=auth(1),json={**body,**extra});assert r.status_code==400
            async with f() as db:
                assert (await db.execute(select(func.count(IncomingFlow.id)))).scalar_one()==1
                assert (await db.execute(select(func.count(CreditRepayment.id)))).scalar_one()==1
    asyncio.run(run())


def test_account_opening_anchor_does_not_roll_with_month_and_warehouse_currency_checks(tmp_path, monkeypatch):
    async def run():
        from app.services.account_balances import balances_at
        async with clean(tmp_path, monkeypatch) as (f,c):
            receipt=await c.post('/api/v1/incoming',headers=auth(1),json={'request_key':uuid.uuid4().hex,'received_date':'2026-10-20','amount':500,'account_id':1,'currency':'THB'})
            assert receipt.status_code==200,receipt.text
            async with f() as db:
                account=await db.get(PaymentAccount,1);account.opening_balance_date=date(2026,10,1);await db.commit()
            async with f() as db:
                account=await db.get(PaymentAccount,1)
                assert (await balances_at(db,[account],date(2026,10,1)))[1]==10000
                assert (await balances_at(db,[account],date(2026,11,1)))[1]==10500
                assert (await balances_at(db,[account],date(2026,12,1)))[1]==10500
            for body in ({'account_id':2,'currency':'THB'},{'account_id':1,'currency':'CNY'},{'currency':'THB'}):
                r=await c.post('/api/v1/incoming',headers=auth(1),json={'request_key':uuid.uuid4().hex,'received_date':'2026-10-20','amount':500,**body})
                assert r.status_code==400
            r=await c.post('/api/v1/income-expense/income',headers=auth(1),json={'category_id':80,'account_id':2,'amount':100,'currency':'THB','income_date':'2026-10-20'})
            assert r.status_code==400
    asyncio.run(run())


def test_incoming_batch_owns_accounts_and_rolls_back_whole_import(tmp_path, monkeypatch):
    async def run():
        async with clean(tmp_path, monkeypatch) as (f,c):
            item={'received_date':'2026-10-20','amount':100,'currency':'THB','account_id':1}
            r=await c.post('/api/v1/incoming/batch-import',headers=auth(1),json={'request_key':uuid.uuid4().hex,'records':[item,{**item,'account_id':2}]})
            assert r.status_code==400
            async with f() as db: assert (await db.execute(select(func.count(IncomingFlow.id)))).scalar_one()==0
            r=await c.post('/api/v1/incoming/batch-import',headers=auth(1),json={'request_key':uuid.uuid4().hex,'records':[{**item,'warehouse_id':2}]})
            assert r.status_code==403
            r=await c.post('/api/v1/incoming/batch-import',headers=auth(1),json={'request_key':uuid.uuid4().hex,'records':[item]})
            assert r.status_code==200,r.text
            assert (await views(c))['cash_current_api']==10100
    asyncio.run(run())


def test_credit_new_receipt_retry_is_idempotent_and_category_filter_includes_fund_payout(tmp_path, monkeypatch):
    async def run():
        from tests.test_fund_disbursement import environment,topup
        from app.models.income_expense import IncomeExpenseCategory
        async with environment(tmp_path,monkeypatch) as (_,f,c,fid):
            r=await topup(c,fid);assert r.status_code==200,r.text
            async with f() as db:
                category=(await db.execute(select(IncomeExpenseCategory).where(IncomeExpenseCategory.name=='备用金拨付'))).scalars().first()
                cid=category.id
                db.add(CreditCustomer(id=1,warehouse_id=1,customer_id=1,credit_limit=10000,current_debt=1000))
                db.add(CreditShipment(credit_customer_id=1,ship_date=datetime(2026,10,1),amount=1000));await db.commit()
            filtered=await get(c,'/income-expense/expense',**RANGE,category_id=cid)
            assert filtered['total']==1 and filtered['data'][0]['amount']==10000
            body={'repayment_date':'2026-10-20','amount':300,'account_id':1,'request_key':'credit-one'}
            for _ in range(2):
                r=await post(c,'/credit/1/payment',json=body)
                assert r['current_debt']==700
            r=await c.post('/api/v1/credit/1/payment',headers=auth(1),json={**body,'account_id':2})
            assert r.status_code==409
            async with f() as db:
                assert (await db.execute(select(func.count(IncomingFlow.id)))).scalar_one()==1
                assert (await db.execute(select(func.count(CreditRepayment.id)))).scalar_one()==1
    asyncio.run(run())

@pytest.mark.parametrize('uid,expected', [(1,200),(2,403),(3,200),(4,403),(5,403)])
def test_receipt_and_payment_roles_with_required_accounts_and_original_payroll_roles(tmp_path,monkeypatch,uid,expected):
    async def run():
        from tests.test_round2_permissions import set_perms
        async with clean(tmp_path,monkeypatch) as (f,c):
            await set_perms(f,uid,['账期管理','应付账款','付款计划','工资','到账流水','运营收支'])
            async with f() as db:
                db.add(CreditCustomer(id=1,warehouse_id=1,customer_id=1,credit_limit=10000,current_debt=1000))
                db.add(CreditShipment(credit_customer_id=1,ship_date=datetime(2026,10,1),amount=1000))
                db.add(Supplier(id=1,warehouse_id=1,name='测试供应商'))
                db.add(PayableBill(id=1,warehouse_id=1,supplier_id=1,bill_number='PAY',bill_date=datetime(2026,10,1),due_date=datetime(2026,12,1),amount=100))
                db.add(PayablePlan(id=1,warehouse_id=1,plan_name='计划',planned_date=datetime(2026,10,20),total_amount=100,bill_ids=[1]));await db.commit()
            r=await c.post('/api/v1/credit/1/payment',headers=auth(uid),json={'repayment_date':'2026-10-20','amount':100,'account_id':1})
            assert r.status_code==expected,r.text
            r=await c.put('/api/v1/payable/plans/1/execute',headers=auth(uid),params={'account_id':1})
            assert r.status_code==(409 if uid in (1,3) else 403),r.text
            from tests.round3_flow_support import prepare_payroll
            await prepare_payroll(f,c,2)
            r=await c.post('/api/v1/payroll/2/disburse',headers=auth(uid),json={'account_id':1,'funding_source':'company_account'})
            assert r.status_code==(200 if uid==3 else 403),r.text
    asyncio.run(run())


def test_company_expense_approval_uses_chosen_account_and_actual_payment_day_once(tmp_path,monkeypatch):
    async def run():
        import base64
        from tests.test_round2_permissions import png
        import app.api.v1.expense_approval as approval_api
        monkeypatch.setattr(approval_api,'thai_now',lambda:fixed(2026,10,20))
        async with clean(tmp_path,monkeypatch) as (f,c):
            a=await post(c,'/expense-approvals',json={'amount':1000,'purpose':'公司费用实际付款','expense_date':'2026-09-30',
                'fund_source':'company','currency':'THB','payment_account_id':1})
            assert (await views(c))['company_expense']==0
            await post(c,f'/expense-approvals/{a["id"]}/approve')
            image='data:image/png;base64,'+base64.b64encode(png()).decode()
            r=await c.post(f'/api/v1/expense-approvals/{a["id"]}/pay',headers=auth(1),json={'voucher_base64':image,'payment_account_id':2})
            assert r.status_code==400
            assert (await views(c))['company_expense']==0
            await post(c,f'/expense-approvals/{a["id"]}/pay',json={'voucher_base64':image,'payment_account_id':1})
            actual=await views(c)
            assert actual['company_expense']==actual['old_report_expense']==actual['unified_cost']==1000
            assert actual['cash_current_api']==actual['cash_report_close']==9000
            rows=await get(c,'/income-expense/expense',**RANGE)
            assert rows['data'][0]['category_name']=='运营支出'
            assert (await views(c,start_date='2026-09-01',end_date='2026-09-30'))['company_expense']==0
            r=await c.post(f'/api/v1/expense-approvals/{a["id"]}/pay',headers=auth(1),json={'voucher_base64':image,'payment_account_id':1})
            assert r.status_code==200 and r.json()['already_paid']
            assert (await views(c))['company_expense']==1000
    asyncio.run(run())


def test_historical_reversed_flow_keeps_reason_but_does_not_change_money(tmp_path,monkeypatch):
    async def run():
        from app.models.cash_advance_repayment import CashAdvanceRepayment
        async with clean(tmp_path,monkeypatch) as (f,c):
            async with f() as db:
                loan=CashAdvance(warehouse_id=1,payer_id=4,payer_name='测试主管',advance_date=date(2026,10,1),amount=1000,
                    purpose='salary',status='confirmed',currency='THB',repaid_amount=0,created_by_id=1,created_by_name='老板')
                db.add(loan);await db.flush()
                db.add(CashAdvanceRepayment(cash_advance_id=loan.id,warehouse_id=1,repayment_date=date(2026,10,10),amount=1000,
                    account_id=1,account_name='现金',currency='THB',payment_method='cash',voucher_path='historical.png',created_by_id=1,
                    created_by_name='老板',status='revoked',revoke_reason='历史账户选择错误'))
                await db.commit()
            r=await get(c,'/income-expense/ledger',**RANGE)
            assert r['total_expense']==0 and r['data'][0]['status_label']=='已冲销'
            assert '历史账户选择错误' in r['data'][0]['remark']
            assert (await views(c))['cash_current_api']==10000
    asyncio.run(run())


def test_purchase_advance_repayment_matches_procurement_card_report_and_supplier_chart(tmp_path,monkeypatch):
    async def run():
        from app.models.cash_advance_repayment import CashAdvanceRepayment
        async with clean(tmp_path,monkeypatch) as (f,c):
            async with f() as db:
                loan=CashAdvance(warehouse_id=1,payer_id=4,payer_name='测试主管',advance_date=date(2026,10,1),amount=1000,
                    purpose='purchase',status='confirmed',currency='THB',repaid_amount=300,created_by_id=1,created_by_name='老板')
                db.add(loan);await db.flush()
                db.add(CashAdvanceRepayment(cash_advance_id=loan.id,warehouse_id=1,repayment_date=date(2026,10,10),amount=300,
                    account_id=1,account_name='现金',currency='THB',payment_method='cash',voucher_path='historical.png',created_by_id=1,
                    created_by_name='老板',status='active'));await db.commit()
            cockpit=await get(c,'/dashboard/cockpit')
            report=await get(c,'/reports/cost-funds-debt',**RANGE)
            block=next(b for b in report['currencies'] if b['currency']=='THB')
            card=next(r['amount'] for r in cockpit['finance']['procurement']['expense'] if r['currency']=='THB')
            assert card==next(r['amount'] for r in block['costs']['data'] if r['name']=='采购')==300
            assert sum(r['amount'] for r in cockpit['finance']['month']['expense'])==300
            assert all(r['amount']==0 for r in cockpit['finance']['month']['operating_expense'])
            trends=await get(c,'/dashboard/trends')
            assert sum(r['amount'] for r in trends['procurement_suppliers']['THB'])==300
    asyncio.run(run())


@pytest.mark.parametrize('path',[
    '/income-expense/expense','/income-expense/ledger','/income-expense/ledger/export',
    '/income-expense/monthly-summary','/income-expense/operating-dashboard',
    '/reports/income-expense','/reports/previews','/incoming',
])
def test_unified_wallet_queries_never_expose_management_money_to_labor(tmp_path,monkeypatch,path):
    async def run():
        from tests.test_cash_advance_references import snapshot
        async with clean(tmp_path,monkeypatch) as (f,c):
            before=await snapshot(f)
            r=await c.get('/api/v1'+path,headers=auth(5))
            assert r.status_code==403 and r.json()=={'detail':'无权访问'},r.text
            assert await snapshot(f)==before
    asyncio.run(run())

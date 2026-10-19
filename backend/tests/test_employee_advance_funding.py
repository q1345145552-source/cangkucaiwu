"""三种来源的真实HTTP、资金成本、审批、额度共享、作废与事务回滚。"""
import asyncio
import ast
from contextlib import asynccontextmanager
from datetime import date, datetime
from decimal import Decimal
import json
from pathlib import Path
import subprocess

import pytest
from sqlalchemy import event, func, select
from app.models import PaymentAccount, SalaryTemplate
from app.models.cash_advance import CashAdvance
from app.models.employee_advance import EmployeeAdvance
from app.models.expense_fund import ExpenseFund, ExpenseFundItem
from app.models.income_expense import ExpenseRecord
from app.models.payroll import PayrollRecord
from app.services import employee_advance_funding as funding
from app.services.account_balances import current_account_balances
from app.services.cash_advance_payroll import lock_payroll_advance
from app.services.reimbursement_payment import lock_advance
from tests.test_round2_permissions import auth, set_perms
from tests.test_round3_permissions import hr_environment, snapshot
from tests.test_employee_advance_expense import supervisor_self

BASE = '/api/v1/employee-advances'
BODY = {'employee_id': 1, 'amount': 1000, 'advance_date': '2026-10-16',
        'funding_source': 'company_account', 'payment_account_id': 1}


@asynccontextmanager
async def environment(tmp, patch):
    async with hr_environment(tmp, patch) as (engine, factory, client):
        @event.listens_for(engine.sync_engine, 'connect')
        def functions(conn, _):
            conn.create_function('to_char', 2, lambda value, fmt: str(value)[:7] if value else None)
        await engine.dispose()
        for uid in (3, 4):
            await set_perms(factory, uid, ['员工预支'])
        async with factory() as db:
            account = await db.get(PaymentAccount, 1)
            account.opening_balance, account.account_type = 20000, 'cash'
            db.add(PaymentAccount(id=3, warehouse_id=1, account_name='人民币', account_number='3',
                account_type='bank', currency='CNY', opening_balance=20000))
            for aid, wid, status, cur, amount in [(1,1,'confirmed','THB',10000), (2,2,'confirmed','THB',10000),
                    (3,1,'pending','THB',10000), (4,1,'confirmed','CNY',10000), (5,1,'confirmed','THB',100)]:
                db.add(CashAdvance(id=aid, warehouse_id=wid, payer_id=4, payer_name='测试主管',
                    advance_date=date(2026,10,16), amount=amount, currency=cur, purpose='salary',
                    status=status, repaid_amount=0, created_by_id=1, created_by_name='老板'))
            for fid, wid in [(1,1), (2,2)]:
                db.add(ExpenseFund(id=fid, warehouse_id=wid, employee_id=4, receive_date=datetime(2026,10,1),
                    amount=10000, remaining_balance=10000, currency='THB', purpose='测试', status='active'))
            await db.commit()
        yield engine, factory, client


async def state(factory):
    async with factory() as db:
        account, fund = await db.get(PaymentAccount, 1), await db.get(ExpenseFund, 1)
        expenses = (await db.execute(select(ExpenseRecord))).scalars().all()
        return {'balance': float((await current_account_balances(db, [account]))[1]),
            'expenses': len(expenses), 'expense_amount': sum(r.amount for r in expenses),
            'fund_available': float(await funding.fund_available_amount(db, fund))}


async def ledger(client):
    r = await client.get('/api/v1/income-expense/ledger', headers=auth(1), params={
        'start_date':'2026-10-01', 'end_date':'2026-10-31', 'page_size':100})
    assert r.status_code == 200, r.text
    return r.json()


async def create(client, uid=1, **values):
    return await client.post(BASE, headers=auth(uid), json={**BODY, **values})


@pytest.mark.parametrize('source', ['company_account', 'cash_advance', 'expense_fund'])
def test_source_money_cost_ledger_and_void(tmp_path, monkeypatch, source):
    async def run():
        async with environment(tmp_path, monkeypatch) as (_, f, c):
            old = await snapshot(f)
            before, flows_before = await state(f), await ledger(c)
            r = await create(c, funding_source=source, cash_advance_id=1, fund_account_id=1)
            assert r.status_code == 200, r.text
            aid = r.json()['id']
            after, flows_after = await state(f), await ledger(c)
            assert after['balance'] == before['balance'] - (1000 if source == 'company_account' else 0)
            assert after['expenses'] == before['expenses'] + (1 if source == 'company_account' else 0)
            assert after['expense_amount'] == before['expense_amount'] + (1000 if source == 'company_account' else 0)
            assert after['fund_available'] == before['fund_available'] - (1000 if source == 'expense_fund' else 0)
            assert flows_after['total'] == flows_before['total'] + (1 if source == 'company_account' else 0)
            if source == 'company_account':
                row = next(x for x in flows_after['data'] if '预支单 #' in (x.get('remark') or ''))
                assert row['amount'] == 1000 and row['account_id'] == 1 and '员工1' in row['remark']
                costs = (await c.get('/api/v1/income-expense/expense', headers=auth(1),
                    params={'category_group':'operating'})).json()
                assert len(costs['data']) == 1 and costs['data'][0]['category_name'] == '员工预支'
            elif source == 'cash_advance':
                loans = (await c.get('/api/v1/cash-advances', headers=auth(1))).json()['data']
                loan = next(x for x in loans if x['id'] == 1)
                assert (loan['employee_advance_used_amount'], loan['available_amount'], loan['outstanding_amount']) == (1000,9000,10000)
                history = (await c.get('/api/v1/cash-advances/1/repayments', headers=auth(1))).json()['employee_advance_usage']
                assert history['data'][0]['employee_advance_id'] == aid and history['employee_advance_used_amount'] == 1000
            else:
                async with f() as db:
                    a = await db.get(EmployeeAdvance, aid)
                    item = await db.get(ExpenseFundItem, a.fund_item_id)
                    assert item.cost_record_only and item.review_status == 'approved' and a.expense_record_id is None
            assert await snapshot(f) == old
            print('ADVANCE_FUNDING', json.dumps({'source':source, 'before':before, 'after':after,
                'flows_before':flows_before['total'], 'flows_after':flows_after['total'], 'response':r.json()}, ensure_ascii=False))
            result = await c.request('DELETE', f'{BASE}/{aid}', headers=auth(1), json={'void_reason':'资金来源回归测试'})
            assert result.status_code == 200, result.text
            assert await state(f) == before and (await ledger(c))['total'] == flows_before['total']
            assert await snapshot(f) == old
    asyncio.run(run())


@pytest.mark.parametrize('source', ['company_account', 'cash_advance', 'expense_fund'])
def test_pending_no_money_then_approval_once_and_rejection(tmp_path, monkeypatch, source):
    async def run():
        async with environment(tmp_path, monkeypatch) as (_, f, c):
            await supervisor_self(f)
            before = await state(f)
            r = await create(c, uid=4, funding_source=source, cash_advance_id=1, fund_account_id=1)
            assert r.status_code == 200 and r.json()['approval_status'] == 'pending', r.text
            assert await state(f) == before
            opts = (await c.get(BASE+'/funding-options', headers=auth(4))).json()
            assert next(x for x in opts['cash_advances'] if x['id'] == 1)['available_amount'] == 10000
            approved = await c.post(f"{BASE}/{r.json()['id']}/approve", headers=auth(1))
            assert approved.status_code == 200, approved.text
            saved = await state(f)
            assert saved['balance'] == 20000 - (1000 if source == 'company_account' else 0)
            assert saved['fund_available'] == 10000 - (1000 if source == 'expense_fund' else 0)
            if source == 'cash_advance':
                opts = (await c.get(BASE+'/funding-options', headers=auth(4))).json()
                assert next(x for x in opts['cash_advances'] if x['id'] == 1)['available_amount'] == 9000
            repeat = await c.post(f"{BASE}/{r.json()['id']}/approve", headers=auth(1))
            assert repeat.status_code == 400 and await state(f) == saved
            pending = await create(c, uid=4, funding_source=source, cash_advance_id=1, fund_account_id=1)
            rejected = await c.post(f"{BASE}/{pending.json()['id']}/reject", headers=auth(1), json={'reject_reason':'不批准'})
            assert rejected.status_code == 200 and await state(f) == saved
    asyncio.run(run())


@pytest.mark.parametrize('values,message', [
    ({'funding_source':None}, '请选择资金来源'), ({'funding_source':'nope'}, '资金来源无效'),
    ({'payment_account_id':None}, '请选择公司付款账户'), ({'payment_account_id':2}, '付款账户不存在或不属于当前仓库'),
    ({'amount':20001}, '公司账户余额不足'), ({'payment_account_id':3,'currency':'THB'}, '付款账户币种与预支不一致'),
    ({'funding_source':'cash_advance'}, '请选择垫款单'),
    ({'funding_source':'cash_advance','cash_advance_id':2}, '垫款单不存在或不属于当前仓库'),
    ({'funding_source':'cash_advance','cash_advance_id':3}, '只能使用已确认的垫款单'),
    ({'funding_source':'cash_advance','cash_advance_id':4}, '垫款单币种与预支不一致'),
    ({'funding_source':'cash_advance','cash_advance_id':5}, '垫款单剩余金额不足'),
    ({'funding_source':'expense_fund'}, '请选择备用金账户'),
    ({'funding_source':'expense_fund','fund_account_id':2}, '备用金账户不存在或不属于当前仓库'),
    ({'funding_source':'expense_fund','fund_account_id':1,'amount':10001}, '超出备用金可用余额'),
])
def test_validation_no_partial_writes(tmp_path, monkeypatch, values, message):
    async def run():
        async with environment(tmp_path, monkeypatch) as (_, f, c):
            before = await state(f)
            r = await create(c, **values)
            assert r.status_code == 400 and r.json()['detail'].startswith(message), r.text
            assert await state(f) == before
            async with f() as db:
                assert (await db.execute(select(func.count()).select_from(EmployeeAdvance))).scalar_one() == 0
            print('FUNDING_DENIED', r.status_code, r.json()['detail'])
    asyncio.run(run())


@pytest.mark.parametrize('source', ['company_account', 'cash_advance', 'expense_fund'])
def test_approval_rechecks_resources_and_keeps_pending_on_failure(tmp_path, monkeypatch, source):
    async def run():
        async with environment(tmp_path, monkeypatch) as (_, f, c):
            await supervisor_self(f)
            r = await create(c, uid=4, funding_source=source, cash_advance_id=1, fund_account_id=1)
            aid = r.json()['id']
            async with f() as db:
                if source == 'company_account': (await db.get(PaymentAccount,1)).opening_balance = 0
                elif source == 'cash_advance': (await db.get(CashAdvance,1)).repaid_amount = 10000
                else: (await db.get(ExpenseFund,1)).remaining_balance = 0
                await db.commit()
            before = await state(f)
            r = await c.post(f'{BASE}/{aid}/approve', headers=auth(1))
            assert r.status_code == 400, r.text
            async with f() as db:
                a = await db.get(EmployeeAdvance, aid)
                assert a.approval_status == 'pending' and a.reviewer_id is None and a.reviewed_at is None
            assert await state(f) == before
    asyncio.run(run())


@pytest.mark.parametrize('source', ['company_account', 'cash_advance', 'expense_fund'])
def test_history_failure_rolls_back_all_money_and_records(tmp_path, monkeypatch, source):
    async def run():
        async with environment(tmp_path, monkeypatch) as (_, f, c):
            before = await state(f)
            async def fail(*args, **kw): raise RuntimeError('资金留痕故障')
            monkeypatch.setattr(funding, 'record_history', fail)
            with pytest.raises(RuntimeError, match='资金留痕故障'):
                await create(c, funding_source=source, cash_advance_id=1, fund_account_id=1)
            assert await state(f) == before
            async with f() as db:
                assert (await db.execute(select(func.count()).select_from(EmployeeAdvance))).scalar_one() == 0
    asyncio.run(run())


def test_shared_cash_capacity_cannot_be_reused(tmp_path, monkeypatch):
    async def run():
        async with environment(tmp_path, monkeypatch) as (_, f, c):
            r = await create(c, funding_source='cash_advance', cash_advance_id=1, amount=10000)
            assert r.status_code == 200, r.text
            again = await create(c, funding_source='cash_advance', cash_advance_id=1, amount=1)
            assert again.status_code == 400 and again.json()['detail'] == '垫款单剩余金额不足'
            from types import SimpleNamespace
            async with f() as db:
                with pytest.raises(Exception, match='垫款单剩余金额不足'):
                    await lock_payroll_advance(db,1,1,[SimpleNamespace(net_pay=1)])
                with pytest.raises(Exception, match='垫款单剩余金额不足'):
                    await lock_advance(db,SimpleNamespace(warehouse_id=1,currency='THB'),1,Decimal(1))
            rows = (await c.get('/api/v1/payroll/cash-advance-sources', headers=auth(1))).json()['data']
            assert next(x for x in rows if x['id'] == 1)['available_amount'] == 0
    asyncio.run(run())


@pytest.mark.parametrize('uid', [1, 4])
def test_three_sources_share_original_salary_cap(tmp_path, monkeypatch, uid):
    async def run():
        async with environment(tmp_path, monkeypatch) as (_, f, c):
            async with f() as db:
                t = await db.get(SalaryTemplate,1)
                t.type, t.amount = 'monthly', 10000
                await db.commit()
            if uid == 4:
                await supervisor_self(f)
            for values in [{'amount':4000}, {'funding_source':'cash_advance','cash_advance_id':1,'amount':3000},
                    {'funding_source':'expense_fund','fund_account_id':1,'amount':3000}]:
                r = await create(c, uid=uid, **values)
                assert r.status_code == 200, r.text
            r = await create(c, uid=uid, amount=1)
            assert r.status_code == 400 and '当前可用 0.00 元' in r.json()['detail']
            print('MIXED_SOURCE_CAP', r.json())
    asyncio.run(run())


def test_old_null_funding_no_backfill_and_original_salary_deduction(tmp_path, monkeypatch):
    async def run():
        async with environment(tmp_path, monkeypatch) as (_, f, c):
            await supervisor_self(f)
            async with f() as db:
                db.add(EmployeeAdvance(warehouse_id=1,employee_id=1,amount=1000,currency='THB',
                    advance_date=date(2026,10,16),period='2026-10',source='supervisor',
                    approval_status='approved',expense_tracking_enabled=False))
                await db.commit()
            before, old = await state(f), await snapshot(f)
            r = await c.post('/api/v1/payroll/calculate', headers=auth(1),
                json={'end_date':'2026-10-18','employee_ids':[1]})
            assert r.status_code == 200, r.text
            async with f() as db:
                p = (await db.execute(select(PayrollRecord).where(PayrollRecord.settle_start_date==date(2026,10,16),PayrollRecord.employee_id==1))).scalar_one()
                assert (p.base_pay,p.advance_deduction,p.net_pay) == (1200,1000,200)
                a = (await db.execute(select(EmployeeAdvance))).scalar_one()
                assert a.funding_source is None and a.payment_account_id is None and a.cash_advance_id is None
            assert await state(f) == before
            assert [r for r in await snapshot(f) if r[0] in {x[0] for x in old}] == old
            print('LEGACY_FUNDING', {'funding_source':None,'expenses':0,'base_pay':1200,'advance':1000,'net_pay':200})
    asyncio.run(run())


def test_options_wh_isolation_and_advance_permission_only(tmp_path, monkeypatch):
    async def run():
        async with environment(tmp_path, monkeypatch) as (_, _, c):
            for uid in (1,3,4):
                r = await c.get(BASE+'/funding-options', headers=auth(uid))
                assert r.status_code == 200, r.text
                data = r.json()
                assert {a['id'] for a in data['accounts']} == {1,3}
                assert {a['id'] for a in data['funds']} == {1}
                assert {a['id'] for a in data['cash_advances']} == {1,4,5}
            assert (await c.get(BASE+'/funding-options', headers=auth(5))).status_code == 403
    asyncio.run(run())


def test_salary_functions_and_cap_unchanged():
    from tests.full_day_leave_test_support import before_full_day_guards
    name = 'backend/app/api/v1/payroll.py'
    before = ast.parse(before_full_day_guards(subprocess.check_output(['git','show','3e19093:'+name]).decode()))
    after = ast.parse(before_full_day_guards(Path(name.removeprefix('backend/')).read_text()))
    functions = lambda t: {n.name: ast.dump(n,include_attributes=False) for n in t.body
        if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name != 'payroll_cash_advance_sources'}
    assert functions(before) == functions(after)
    cap = 'backend/app/services/employee_advance_limit.py'
    assert subprocess.check_output(['git','show','3e19093:'+cap]).decode() == Path(cap.removeprefix('backend/')).read_text()


def test_fund_review_cannot_refund_an_approved_advance(tmp_path, monkeypatch):
    async def run():
        async with environment(tmp_path, monkeypatch) as (_, f, c):
            r = await create(c, funding_source='expense_fund', fund_account_id=1)
            assert r.status_code == 200, r.text
            async with f() as db:
                item_id = (await db.get(EmployeeAdvance, r.json()['id'])).fund_item_id
            before = await state(f)
            r = await c.post('/api/v1/expense-fund/review/batch', headers=auth(1),
                json={'item_ids':[item_id], 'action':'reject', 'remark':'不应绕过预支作废'})
            assert r.status_code == 400 and r.json()['detail'] == '员工预支关联开销请在员工预支中处理'
            assert await state(f) == before
    asyncio.run(run())


def test_cny_sources_keep_original_exchange_rate_cap(tmp_path, monkeypatch):
    async def run():
        from datetime import timezone
        from app.models.recharge import ExchangeRate
        async with environment(tmp_path, monkeypatch) as (_, f, c):
            async with f() as db:
                t = await db.get(SalaryTemplate, 1)
                t.type, t.amount = 'monthly', 10000
                db.add(ExchangeRate(warehouse_id=1,from_currency='CNY',to_currency='THB',rate=5,
                    effective_from=datetime(2026,10,1,tzinfo=timezone.utc)))
                await db.commit()
            a = await create(c, payment_account_id=3, currency='CNY', amount=1000)
            b = await create(c, funding_source='cash_advance',cash_advance_id=4,currency='CNY',amount=1000)
            assert a.status_code == b.status_code == 200, (a.text,b.text)
            r = await create(c, funding_source='expense_fund', fund_account_id=1, amount=1)
            assert r.status_code == 400 and '当前可用 0.00 元' in r.json()['detail']
    asyncio.run(run())


@pytest.mark.parametrize('source,message', [('company_account','付款账户已停用'),
    ('expense_fund','备用金账户已停用或结清')])
def test_inactive_source_hidden_and_direct_request_rejected(tmp_path, monkeypatch, source, message):
    async def run():
        async with environment(tmp_path, monkeypatch) as (_, f, c):
            async with f() as db:
                if source == 'company_account': (await db.get(PaymentAccount,1)).status = 'inactive'
                else: (await db.get(ExpenseFund,1)).status = 'settled'
                await db.commit()
            before = await state(f)
            r = await create(c, funding_source=source, fund_account_id=1)
            assert r.status_code == 400 and r.json()['detail'] == message
            assert await state(f) == before
            opts = (await c.get(BASE+'/funding-options', headers=auth(1))).json()
            assert 1 not in {a['id'] for a in opts['accounts' if source == 'company_account' else 'funds']}
    asyncio.run(run())


def test_company_balance_keeps_cent_precision_after_fractional_advances(tmp_path, monkeypatch):
    async def run():
        async with environment(tmp_path, monkeypatch) as (_, f, c):
            async with f() as db:
                (await db.get(PaymentAccount,1)).opening_balance = 1
                await db.commit()
            for amount in (0.1,0.1,0.1,0.7):
                r = await create(c, amount=amount)
                assert r.status_code == 200, r.text
            assert (await state(f))['balance'] == 0
    asyncio.run(run())


@pytest.mark.parametrize('source,message', [('company_account','公司账户余额不足'),
    ('cash_advance','只能使用已确认的垫款单'), ('expense_fund','超出备用金可用余额')])
def test_locked_validation_refreshes_previously_loaded_resource(tmp_path, monkeypatch, source, message):
    async def run():
        from fastapi import HTTPException
        async with environment(tmp_path, monkeypatch) as (_, f, _):
            async with f() as held:
                # 与新建先校验、再锁定执行相同，刻意保留ORM缓存对象。
                _, cached = await funding.validate_funding(held,source,1,1000,
                    payment_account_id=1,cash_advance_id=1,fund_account_id=1)
                assert cached.id == 1
                async with f() as changed:
                    if source == 'company_account': (await changed.get(PaymentAccount,1)).opening_balance = 0
                    elif source == 'cash_advance':
                        loan = await changed.get(CashAdvance,1)
                        loan.repaid_amount, loan.status = 10000, 'repaid'
                    else: (await changed.get(ExpenseFund,1)).remaining_balance = 0
                    await changed.commit()
                with pytest.raises(HTTPException) as rejected:
                    await funding.validate_funding(held,source,1,1000,payment_account_id=1,
                        cash_advance_id=1,fund_account_id=1,lock=True)
                assert rejected.value.status_code == 400 and rejected.value.detail.startswith(message)
    asyncio.run(run())

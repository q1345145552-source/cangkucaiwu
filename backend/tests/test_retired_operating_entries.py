"""撤入口：真实 PostgreSQL/HTTP 验证封闭接口、原记录保留及钱包金额不变。"""
import asyncio
import json
import os
from datetime import date, datetime
from pathlib import Path

import pytest
from sqlalchemy import select, func, event
from app.models import User, Customer, PaymentAccount, IncomeExpenseCategory, IncomeRecord, ExpenseRecord
from app.models.credit import CreditCustomer, CreditShipment
from app.core.menu_registry import MENU_PERMISSIONS
from tests.test_incoming_operations import environment, URL
from tests.test_round2_permissions import auth

pytestmark = pytest.mark.skipif(not URL, reason='Requires explicit loopback PostgreSQL')
CLOSED = [
    ('GET', '/reports/operations', None),
    ('GET', '/customers/1/receivables', None),
    ('POST', '/customers/1/receipts/link', {'incoming_flow_id': 1}),
    ('GET', '/credit/shipments', None),
    ('POST', '/credit/1/shipment', {'ship_date': '2026-09-01', 'order_count': 2, 'amount': 300, 'currency': 'THB', 'request_key': 'disabled-entry'}),
    ('PUT', '/credit/1/shipment/1', {'ship_date': '2026-09-01', 'order_count': 2, 'amount': 300, 'currency': 'THB'}),
    ('POST', '/credit/1/shipment/1/void', {'reason': '不应执行'}),
]

async def seed(factory):
    async with factory() as db:
        for uid in (3, 4):
            (await db.get(User, uid)).extra_permissions = [m.label for m in MENU_PERMISSIONS if m.selectable]
        customer = await db.get(Customer, 1)
        customer.company_name = '撤入口测试客户'
        customer.total_shipments, customer.total_shipping_cost = 2, 900
        account = await db.get(PaymentAccount, 1)
        account.opening_balance, account.opening_balance_date = 10000, date(2026, 9, 1)
        db.add(PaymentAccount(id=3, warehouse_id=1, account_name='测试人民币现金', account_type='cash', account_number='-', opening_balance=1000, opening_balance_date=date(2026, 9, 1), currency='CNY'))
        db.add_all([IncomeExpenseCategory(id=1, warehouse_id=1, type='income', name='其他收入', category_group='other'), IncomeExpenseCategory(id=2, warehouse_id=1, type='expense', name='运营支出', category_group='operating')])
        db.add(CreditCustomer(id=1, warehouse_id=1, customer_id=1, credit_limit=10000, currency='THB', status='active'))
        await db.flush()
        db.add(CreditShipment(id=1, credit_customer_id=1, ship_date=datetime(2026, 9, 1), amount=900, order_count=2, currency='THB', status='active'))
        for rid, cur, aid, income, expense in [(1, 'THB', 1, 1000, 400), (2, 'CNY', 3, 200, 50)]:
            db.add(IncomeRecord(id=rid, warehouse_id=1, category_id=1, account_id=aid, amount=income, currency=cur, income_date=datetime(2026, 9, 2), confirmed_by=1))
            db.add(ExpenseRecord(id=rid, warehouse_id=1, category_id=2, account_id=aid, amount=expense, currency=cur, expense_date=datetime(2026, 9, 3), approved_by=1))
        await db.commit()

async def snapshots(client):
    result = {}
    for path in ('/reports/income-expense', '/reports/cost-funds-debt', '/income-expense/ledger'):
        r = await client.get('/api/v1' + path, headers=auth(1), params={'start_date':'2026-09-01', 'end_date':'2026-09-30'})
        assert r.status_code == 200, (path, r.text)
        result[path] = r.json()
    return result

def test_closed_routes_all_roles_keep_history_and_wallet(tmp_path, monkeypatch):
    async def run():
        async with environment(tmp_path, monkeypatch) as (engine, factory, client):
            await seed(factory)
            before = await snapshots(client)
            captured = json.loads((Path(__file__).parent / 'fixtures/retired_operating_wallet_before.json').read_text())
            for value in before.values():
                assert value["internal_transfers"]["by_currency"] == {}
            assert {path:{k:v for k,v in value.items() if k != "internal_transfers"} for path,value in before.items()} == captured
            statements = []
            def trace(conn, cursor, statement, *args): statements.append(statement)
            event.listen(engine.sync_engine, 'before_cursor_execute', trace)
            results = []
            try:
                for uid in (1, 2, 3, 4, 5, 7):
                    for method, path, payload in CLOSED:
                        r = await client.request(method, '/api/v1' + path, headers=auth(uid), **({'json':payload} if payload else {}))
                        assert r.status_code == 403, (uid, method, path, r.text)
                        if uid in (1, 3, 4, 7): assert r.json() == {'detail':'经营报表及客户应收、发货录入功能已停用'}
                        results.append({'user_id':uid, 'method':method, 'path':path, 'status':r.status_code, 'body':r.json()})
            finally:
                event.remove(engine.sync_engine, 'before_cursor_execute', trace)
            assert not any(s.lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE')) for s in statements)
            assert await snapshots(client) == before
            async with factory() as db:
                old = await db.get(CreditShipment, 1)
                assert (old.amount, old.order_count, old.status) == (900, 2, 'active')
                customer = await db.get(Customer, 1)
                assert (customer.total_shipments, customer.total_shipping_cost) == (2, 900)
            # Original customer CRUD reads and shared selectors remain accessible.
            pages = {}
            for uid in (1, 3, 4):
                for path in ('/customers', '/customers/1', '/recharge', '/incoming', '/accounts', '/payable', '/reports/previews', '/income-expense/expense', '/reports/cost-funds-debt', '/credit'):
                    r = await client.get('/api/v1' + path, headers=auth(uid))
                    assert r.status_code == 200, (uid, path, r.text)
                    pages[f'{uid}:{path}'] = r.status_code
            if os.environ.get('RETIRED_ENTRIES_TEST_REPORT'):
                Path(os.environ['RETIRED_ENTRIES_TEST_REPORT']).write_text(json.dumps({'blocked':results, 'before':before, 'after':await snapshots(client), 'read_regression':pages, 'history_kept':True, 'blocked_mutation_count':0}, ensure_ascii=False, indent=2))
    asyncio.run(run())

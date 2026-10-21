"""第十七轮第一批：只收口15个已复现写接口，其他角色及员工自助保持原样。"""
import asyncio
import ast
import json
import os
import re
import subprocess
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.routing import APIRoute
from sqlalchemy import select

from app.main import app
from app.core.permissions import require_non_labor
from app.core.menu_registry import MENU_PERMISSIONS
from app.models.supplier import Supplier
from app.models.payable import PayableBill, PayablePlan, PlanTemplate
from app.models.income_expense import IncomeRecord, IncomeExpenseCategory
from app.models import PaymentAccount
from app.models.credit import CreditCustomer
from app.models.market import MarketItem
from app.models.group_order import GroupOrder
from tests.test_round2_permissions import auth, set_perms
from tests.test_round4_permissions import attendance_environment
from tests.test_cash_advance_references import snapshot


# 第十七轮已实际复现并关闭的15条；后续批次单独声明，原15条继续回归。
CASES = [
    ('PUT', '/customers/{customer_id}', '/customers/1', {'company_name':'更新客户'}),
    ('PUT', '/accounts/{account_id}', '/accounts/1', {'account_name':'更新账户','account_type':'bank','account_number':'changed'}),
    ('PUT', '/accounts/{account_id}/toggle-status', '/accounts/1/toggle-status', None),
    ('PUT', '/suppliers/{supplier_id}', '/suppliers/1', {'name':'更新供应商'}),
    ('DELETE', '/suppliers/{supplier_id}', '/suppliers/3', None),
    ('POST', '/recharge', '/recharge', {'customer_id':1,'declare_date':'2026-10-20','amount':50}),
    ('PUT', '/income-expense/income/{income_id}', '/income-expense/income/90', {'category_id':90,'account_id':1,'amount':15,'income_date':'2026-10-10'}),
    ('DELETE', '/income-expense/income/{income_id}', '/income-expense/income/90', None),
    ('PUT', '/payable/plans/{plan_id}/execute', '/payable/plans/1/execute?account_id=1', None),
    ('DELETE', '/payable/plan-templates/{template_id}', '/payable/plan-templates/1', None),
    ('POST', '/credit/{credit_id}/payment', '/credit/1/payment', {'repayment_date':'2026-10-20','amount':10,'account_id':1}),
    ('POST', '/market/{item_id}/purchase', '/market/1/purchase', {'contact_info':'测试购买'}),
    ('PUT', '/market/{item_id}/confirm', '/market/1/confirm', None),
    ('POST', '/group-order/{go_id}/join', '/group-order/1/join', {'quantity':1}),
    ('POST', '/reimbursement', '/reimbursement', {'submit_date':'2026-10-20','items':[{'category':'交通费','amount':10}]}),
]
ALL_PERMISSIONS = [p.label for p in MENU_PERMISSIONS if p.selectable]


@asynccontextmanager
async def environment(tmp_path, monkeypatch):
    tmp_path.mkdir(exist_ok=True)
    async with attendance_environment(tmp_path, monkeypatch) as (engine, factory, client):
        import app.services.payable_payment as payments
        from app.core.timezone import THAI_TZ
        monkeypatch.setattr(payments, 'thai_now', lambda: datetime(2026,10,20,12,tzinfo=THAI_TZ))
        async with factory() as db:
            (await db.get(PaymentAccount,1)).opening_balance = 20000
            db.add(IncomeExpenseCategory(id=90,warehouse_id=1,type='income',name='实际收入',category_group='other'))
            db.add_all([Supplier(id=i,warehouse_id=1,name=f'测试供应商{i}') for i in (1,3)])
            db.add(PayableBill(id=1,warehouse_id=1,supplier_id=1,bill_number='GUARD-1',
                bill_date=datetime(2026,10,1),due_date=datetime(2026,12,30),amount=100))
            db.add(PayablePlan(id=1,warehouse_id=1,plan_name='测试计划',
                planned_date=datetime(2026,10,20),total_amount=100,bill_ids=[1]))
            db.add(PlanTemplate(id=1,warehouse_id=1,name='测试计划模板',bill_ids=[1]))
            db.add(IncomeRecord(id=90,warehouse_id=1,category_id=1,account_id=1,
                amount=10,income_date=datetime(2026,10,10)))
            db.add(CreditCustomer(id=1,warehouse_id=1,customer_id=1,credit_limit=10000,
                status='active',current_debt=100))
            db.add(MarketItem(id=1,warehouse_id=1,uploader_id=4,name='测试商品',
                quantity=1,price=100,status='approved'))
            db.add(GroupOrder(id=1,warehouse_id=1,initiator_id=4,item_name='测试拼单',
                target_quantity=10,target_price=5,deadline=datetime(2026,12,30)))
            await db.commit()
        yield engine, factory, client


async def call(client, case, uid):
    method, _, path, body = case
    return await client.request(method, '/api/v1'+path, headers=auth(uid),
        **({'json':body} if body is not None else {}))


@pytest.mark.parametrize('case', CASES, ids=lambda c:f'{c[0]} {c[1]}')
def test_each_write_rejects_labor_without_changes_even_with_permissions(tmp_path, monkeypatch, case):
    async def run():
        async with environment(tmp_path, monkeypatch) as (_, factory, client):
            for uid in (5,6):
                await set_perms(factory, uid, ALL_PERMISSIONS)
            before = await snapshot(factory)
            for uid in (5,6):
                response = await call(client, case, uid)
                assert response.status_code == 403 and response.json() == {'detail':'无权访问'}, response.text
                # Guard precedes body/path validation and a forged employee-view query.
                invalid_path = re.sub(r'\{[^}]+\}', 'not-an-id', case[1])
                response = await client.request(case[0], '/api/v1'+invalid_path,
                    headers={**auth(uid),'X-Warehouse-ID':'all'},params={'view':'self'},json={})
                assert response.status_code == 403 and response.json() == {'detail':'无权访问'}, response.text
            assert await snapshot(factory) == before
    asyncio.run(run())


async def no_guard():
    """仅测试用：恢复加守卫前的依赖行为，不修改处理函数或其他依赖。"""


@pytest.mark.parametrize('case', CASES, ids=lambda c:f'{c[0]} {c[1]}')
@pytest.mark.parametrize('uid,granted', [(1,False),(2,False),(3,True),(4,True),(3,False),(4,False)])
def test_all_other_roles_preserve_original_responses(tmp_path, monkeypatch, case, uid, granted):
    async def run():
        results = []
        for enabled in (False,True):
            with monkeypatch.context() as scoped:
                if not enabled:
                    scoped.setitem(app.dependency_overrides, require_non_labor, no_guard)
                async with environment(tmp_path/str(enabled), scoped) as (_,factory,client):
                    if granted:
                        await set_perms(factory,uid,ALL_PERMISSIONS)
                    response = await call(client,case,uid)
                    results.append((response.status_code,response.json()))
                    if case[1]=="/market/{item_id}/confirm" and (uid==1 or granted):
                        assert response.status_code==403 and "只有超级管理员" in response.text
                    elif uid==1 or granted:
                        assert response.status_code==200,response.text
        assert results[0]==results[1],results
    asyncio.run(run())


def test_batch_report_admin_all_fifteen_and_original_credit_rejection(tmp_path, monkeypatch):
    async def run():
        async with environment(tmp_path,monkeypatch) as (_,factory,client):
            before = await snapshot(factory)
            rows = []
            for case in CASES:
                response = await call(client,case,5)
                assert response.status_code==403 and response.json()=={'detail':'无权访问'}
                rows.append({'method':case[0],'path':'/api/v1'+case[1],
                    'labor':{'status':response.status_code,'body':response.json()}})
            assert await snapshot(factory)==before
            for case,row in zip(CASES,rows):
                if case[1] in ('/income-expense/income/{income_id}', '/payable/plans/{plan_id}/execute','/credit/{credit_id}/payment'):
                    async with factory() as db:
                        (await db.get(PaymentAccount,1)).status = 'active'
                        await db.commit()
                response = await call(client,case,1)
                expected=403 if case[1]=='/market/{item_id}/confirm' else 200
                assert response.status_code==expected,response.text
                row['warehouse_admin']={'status':response.status_code,'body':response.json()}
            # Correct a previous static-audit false positive: existing explicit role branch.
            credit=await client.put('/api/v1/credit/1',headers=auth(5),json={'credit_limit':20000})
            assert credit.status_code==403 and credit.json()=={'detail':'无权访问'},credit.text
            async with factory() as db:
                assert (await db.get(CreditCustomer,1)).credit_limit==10000
            report={'environment':'isolated SQLite, synthetic data, not production','batch1':rows,
                'blocked_requests_all_tables_unchanged':True,'scope':'round17 first fifteen regression',
                'prior_audit_correction':{'method':'PUT','path':'/api/v1/credit/{credit_id}',
                    'status':credit.status_code,'body':credit.json(),'note':'原误报保留；当前统一守卫在原角色判断之前拒绝劳工'}}
            if os.environ.get('NON_LABOR_BATCH1_REPORT'):
                Path(os.environ['NON_LABOR_BATCH1_REPORT']).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    asyncio.run(run())


def test_original_fifteen_stay_protected_under_current_management_router():
    # The old batch-only source snapshot predates the authorised default management router.
    # Check today's registered guards and retain the original batch's coverage instead.
    from scripts.audit_management_access import audit, MANAGEMENT
    from tests.test_non_labor_batch2_writes import CASES as BATCH2
    from tests.test_non_labor_read_group1 import CASES as READ_GROUP1
    result=audit()
    current={(r['method'],r['path']) for r in result['routes'] if r['access'] in MANAGEMENT}
    expected={(method,'/api/v1'+template) for method,template,_,_ in CASES+BATCH2+READ_GROUP1}
    assert expected <= current
    assert result['unprotected_or_unclassified']==[]
    for route in app.routes:
        if isinstance(route,APIRoute) and (route.openapi_extra or {}).get('x-access-kind') in MANAGEMENT:
            assert route.dependant.dependencies[0].call is require_non_labor

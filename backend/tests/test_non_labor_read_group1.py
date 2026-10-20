"""第十九轮：7个管理读取入口，保留共享选择器权限及原查询结果。"""
import asyncio
import ast
import json
import os
import re
import subprocess
from contextlib import asynccontextmanager
from datetime import date, datetime
from pathlib import Path

import pytest
from fastapi.routing import APIRoute
from sqlalchemy import event, select
from sqlalchemy.exc import MissingGreenlet
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.core.permissions import require_non_labor
from app.core.menu_registry import MENU_PERMISSIONS_BY_KEY
from app.models.user import User
from app.models.customer import PaymentAccount
from app.models.recharge import IncomingFlow
from app.models.expense_fund import ExpenseFund, ExpenseFundItem
from app.models.reimbursement import Reimbursement
from tests.test_round2_permissions import auth, set_perms
from tests.test_non_labor_guard import environment as batch1_environment, ALL_PERMISSIONS, no_guard
from tests.test_cash_advance_references import snapshot

CASES = [
    ('GET','/users','/users',None),
    ('GET','/dashboard/stats','/dashboard/stats',None),
    ('GET','/dashboard/pending-tasks','/dashboard/pending-tasks',None),
    ('GET','/dashboard/warehouse-summary','/dashboard/warehouse-summary',None),
    ('GET','/customers','/customers',None),
    ('GET','/customers/{customer_id}','/customers/1',None),
    ('GET','/accounts','/accounts',None),
]
SHARED = [('customers',key) for key in ('customers','recharge','incoming','credit')]+[
    ('accounts',key) for key in ('accounts','payroll','operating','other_income_expense')]


@asynccontextmanager
async def environment(tmp_path,monkeypatch):
    async with batch1_environment(tmp_path,monkeypatch) as (engine,factory,_):
        # 仅为隔离SQLite提供PostgreSQL已有的日期格式函数，运行时查询不变。
        @event.listens_for(engine.sync_engine,'connect')
        def functions(conn,_):
            conn.create_function('to_char',2,lambda value,fmt:str(value)[:7] if value else None)
        await engine.dispose()
        import app.api.v1.dashboard as dashboard
        monkeypatch.setattr(dashboard,'thai_today',lambda:date(2026,10,20))
        async with factory() as db:
            for wid,uid in ((1,4),(2,6)):
                db.add(IncomingFlow(id=wid,warehouse_id=wid,received_date=datetime(2026,10,16),
                    amount=100 if wid==1 else 9000,entrant_id=1))
                db.add(ExpenseFund(id=wid,warehouse_id=wid,employee_id=uid,receive_date=datetime(2026,10,1),
                    amount=1000,remaining_balance=1000,currency='THB',purpose='隔离测试'))
                db.add(ExpenseFundItem(id=wid,fund_id=wid,expense_date=datetime(2026,10,16),
                    category='耗材',amount=10,description='隔离测试开销',review_status='pending'))
                db.add(Reimbursement(id=wid,warehouse_id=wid,employee_id=uid,submit_date=datetime(2026,10,16),
                    total_amount=20,status='pending'))
                (await db.get(PaymentAccount,wid)).opening_balance=10000 if wid==1 else 90000
            await db.commit()
        # 旧仓库汇总本身会500：读取真实HTTP结果，不把服务端异常伪装成200。
        async with AsyncClient(transport=ASGITransport(app=app,raise_app_exceptions=False),base_url='http://test') as client:
            yield engine,factory,client


async def get(client,path,uid):
    return await client.get('/api/v1'+path,headers=auth(uid))


def response_data(response):
    try:return response.json()
    except ValueError:return response.text


@pytest.mark.parametrize('case',CASES,ids=lambda c:c[1])
def test_labor_seven_denied_before_queries_and_without_changes(tmp_path,monkeypatch,case):
    async def run():
        async with environment(tmp_path,monkeypatch) as (engine,factory,client):
            for uid in (5,6):await set_perms(factory,uid,ALL_PERMISSIONS)
            before=await snapshot(factory)
            statements=[]
            def track(conn,cursor,statement,*args):statements.append(statement)
            event.listen(engine.sync_engine,'before_cursor_execute',track)
            try:
                for uid in (5,6):
                    for path in (case[2],re.sub(r'\{[^}]+\}','not-an-id',case[1])):
                        r=await client.get('/api/v1'+path,headers={**auth(uid),'X-Warehouse-ID':'all'},
                            params={'view':'self','warehouse_id':2})
                        assert r.status_code==403 and r.json()=={'detail':'无权访问'},r.text
                # 只有认证读取users/user_warehouses；没有执行业务查询或写SQL。
                for statement in statements:
                    assert not statement.lstrip().upper().startswith(('INSERT','UPDATE','DELETE'))
                    tables=re.findall(r'\b(?:FROM|JOIN)\s+(\w+)',statement,re.I)
                    assert set(tables)<= {'users','user_warehouses'},statement
            finally:event.remove(engine.sync_engine,'before_cursor_execute',track)
            assert await snapshot(factory)==before
    asyncio.run(run())


@pytest.mark.parametrize('case',CASES,ids=lambda c:c[1])
@pytest.mark.parametrize('uid,granted',[(1,False),(2,False),(3,True),(4,True),(3,False),(4,False)])
def test_other_roles_exact_original_results_and_original_failure(tmp_path,monkeypatch,case,uid,granted):
    async def run():
        async with environment(tmp_path,monkeypatch) as (_,factory,client):
            if granted:await set_perms(factory,uid,ALL_PERMISSIONS)
            before=await snapshot(factory)
            results=[]
            for enabled in (False,True):
                with monkeypatch.context() as scoped:
                    if not enabled:scoped.setitem(app.dependency_overrides,require_non_labor,no_guard)
                    response=await get(client,case[2],uid)
                    results.append((response.status_code,response_data(response)))
            assert results[0]==results[1],results
            if uid==2:
                expected=200 if case[1]=='/users' else 403
            elif case[1]=='/dashboard/warehouse-summary':expected=403 if uid in (3,4) and not granted else 200
            elif uid in (3,4) and not granted and not case[1].startswith('/dashboard/'):expected=403
            else:expected=200
            assert response.status_code==expected,(case,uid,response.text)
            assert await snapshot(factory)==before
    asyncio.run(run())


@pytest.mark.parametrize('uid',[3,4])
@pytest.mark.parametrize('resource,key',SHARED)
def test_each_shared_permission_alone_can_load_scoped_selector(tmp_path,monkeypatch,uid,resource,key):
    async def run():
        async with environment(tmp_path,monkeypatch) as (_,factory,client):
            await set_perms(factory,uid,[MENU_PERMISSIONS_BY_KEY[key].label])
            before=await snapshot(factory)
            r=await get(client,'/'+resource+'?page_size=99999',uid)
            assert r.status_code==200,r.text
            assert {row['warehouse_id'] for row in r.json()['data']}=={1}
            assert {row['id'] for row in r.json()['data']}==({1,3} if resource=='customers' else {1})
            if resource=='customers' and key!='customers':
                denied=await get(client,'/customers/1',uid)
                assert denied.status_code==403 and '无此操作权限' in denied.json()['detail']
            assert await snapshot(factory)==before
            await set_perms(factory,uid,[])
            before_denied=await snapshot(factory)
            denied=await get(client,'/'+resource,uid)
            assert denied.status_code==403 and '无此操作权限' in denied.json()['detail']
            assert await snapshot(factory)==before_denied
    asyncio.run(run())


@pytest.mark.parametrize('uid',[1,3,4])
def test_original_warehouse_scopes_filters_and_dashboard_numbers(tmp_path,monkeypatch,uid):
    async def run():
        async with environment(tmp_path,monkeypatch) as (_,factory,client):
            await set_perms(factory,uid,ALL_PERMISSIONS)
            before=await snapshot(factory)
            for path in ('/users','/customers','/accounts'):
                r=await get(client,path,uid);assert r.status_code==200,r.text
                assert {row['warehouse_id'] for row in r.json()['data']}=={1}
            r=await get(client,'/customers/2',uid)
            assert r.status_code==403 and r.json()=={'detail':'无权查看其他仓库的客户'}
            assert (await get(client,'/customers?search=客户1',uid)).json()['total']==1
            assert (await get(client,'/users?role=warehouse_labor',uid)).json()['total']==2
            stats=await get(client,'/dashboard/stats',uid)
            assert stats.status_code==200,stats.text
            assert stats.json()=={'total_recharge_month':100.0,'total_incoming_month':100.0,
                'unmatched_count':1,'pending_market_review':0,'pending_group_orders':1,
                'pending_expense_fund_reviews':1,'pending_reimbursements':1}
            tasks=await get(client,'/dashboard/pending-tasks',uid)
            assert tasks.status_code==200 and len(tasks.json()['data'])==2
            assert {row['id'] for row in tasks.json()['data']}=={1}
            for path in ('/dashboard/cockpit','/dashboard/trends','/dashboard/boss-todos'):
                r=await get(client,path,uid);assert r.status_code==200,(path,r.text)
            assert await snapshot(factory)==before
    asyncio.run(run())


def test_shared_page_requests_and_complete_report(tmp_path,monkeypatch):
    async def run():
        async with environment(tmp_path,monkeypatch) as (_,factory,client):
            before=await snapshot(factory);rows=[]
            for case in CASES:
                r=await get(client,case[2],5)
                assert r.status_code==403 and r.json()=={'detail':'无权访问'}
                rows.append({'method':'GET','path':'/api/v1'+case[2],
                    'labor':{'status':r.status_code,'body':r.json()}})
            assert await snapshot(factory)==before
            checks=[]
            for uid,key,paths in [
                (4,'recharge',['/recharge','/customers?page_size=99999']),
                (3,'operating',['/income-expense/operating-dashboard?start_date=2026-10-01&end_date=2026-10-31',
                    '/income-expense/categories?type=expense&category_group=operating','/accounts']),
                (4,'credit',['/credit','/credit/dashboard','/credit/alerts','/customers?page_size=100']),
                (3,'incoming',['/incoming','/customers?page_size=99999']),
            ]:
                await set_perms(factory,uid,[MENU_PERMISSIONS_BY_KEY[key].label])
                responses=[]
                for path in paths:
                    r=await get(client,path,uid)
                    assert r.status_code==200,(path,r.text)
                    responses.append({'path':'/api/v1'+path,'status':r.status_code,'body':r.json()})
                checks.append({'role':'staff' if uid==3 else 'supervisor','only_permission':MENU_PERMISSIONS_BY_KEY[key].label,
                    'responses':responses})
            management=[]
            for uid in (1,3,4,2):
                if uid in (3,4):await set_perms(factory,uid,ALL_PERMISSIONS)
                responses=[]
                for case in CASES:
                    r=await get(client,case[2],uid)
                    responses.append({'path':'/api/v1'+case[2],'status':r.status_code,'body':response_data(r)})
                management.append({'user_id':uid,'responses':responses})
            r=await get(client,'/dashboard/stats',1)
            with monkeypatch.context() as scoped:
                scoped.setitem(app.dependency_overrides,require_non_labor,no_guard)
                baseline=await get(client,'/dashboard/stats',1)
            assert baseline.status_code==r.status_code==200 and baseline.json()==r.json()
            report={'environment':'isolated SQLite; synthetic data; not production','labor':rows,
                'shared_page_requests':checks,'other_roles':management,'admin_dashboard_stats':r.json(),
                'admin_dashboard_stats_before':baseline.json(),
                'known_fixed_failure':{'path':'/api/v1/dashboard/warehouse-summary','before_status':500,
                    'after_status':200,'cause':'第8轮改为显式授权仓库查询；真实PostgreSQL验收见test_warehouse_summary.py'}}
            if os.environ.get('NON_LABOR_READ1_REPORT'):
                Path(os.environ['NON_LABOR_READ1_REPORT']).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    asyncio.run(run())


def test_warehouse_summary_old_lazy_loading_failure_reproduced_without_query_change(tmp_path,monkeypatch):
    async def run():
        import app.api.v1.dashboard as dashboard
        root=Path(__file__).resolve().parents[2]
        source=subprocess.check_output(['git','show','c04f7a4:backend/app/api/v1/dashboard.py'],cwd=root,text=True)
        node=next(n for n in ast.parse(source).body if isinstance(n,ast.AsyncFunctionDef) and n.name=='warehouse_summary')
        node.decorator_list=[]
        namespace=vars(dashboard).copy()
        exec(compile(ast.Module(body=[node],type_ignores=[]),'original_warehouse_summary','exec'),namespace)
        async with environment(tmp_path,monkeypatch) as (_,factory,_):
            for function in (namespace['warehouse_summary'],):
                async with factory() as db:
                    user=await db.get(User,1)
                    with pytest.raises(MissingGreenlet):await function(current_user=user,db=db)
    asyncio.run(run())


def test_existing_guards_remain_first_and_round11_only_changes_receivable_reads():
    from tests.non_labor_test_support import without_non_labor_guard
    from tests.test_non_labor_guard import CASES as BATCH1
    from tests.test_non_labor_batch2_writes import CASES as BATCH2
    routes=[r for r in app.routes if isinstance(r,APIRoute)
        and any(d.call is require_non_labor for d in r.dependant.dependencies)]
    expected={(method,'/api/v1'+template) for method,template,_,_ in BATCH1+BATCH2+CASES}
    from tests.wallet_contract_support import WALLET_GUARDED_ROUTES
    expected.update(WALLET_GUARDED_ROUTES)
    # 第3轮已收口其余管理路由；旧7条仍必须在，不能再断言只有旧清单。
    assert expected <= {(method,r.path) for r in routes for method in r.methods}
    assert all(r.dependant.dependencies[0].call is require_non_labor for r in routes)
    root=Path(__file__).resolve().parents[2]
    for name in ('users','dashboard','customers','payment_accounts'):
        path='backend/app/api/v1/'+name+'.py'
        old=subprocess.check_output(['git','show','b5829bef2f88a86ebe3dab2ef72dc3284edae29a:'+path],cwd=root,text=True)
        def protected(source):
            tree=ast.parse(source)
            tree.body=[n for n in tree.body if not isinstance(n,(ast.Import,ast.ImportFrom))
                and not (isinstance(n,(ast.AsyncFunctionDef,ast.FunctionDef,ast.ClassDef)) and n.name in ({'dashboard':{'dashboard_cockpit'},'customers':{'CustomerReceiptLink','_scoped_customer','customer_receivables','link_customer_receipt','list_customers'}}.get(name,set())))]
            return ast.unparse(tree)
        assert protected((root/path).read_text())==protected(old),path

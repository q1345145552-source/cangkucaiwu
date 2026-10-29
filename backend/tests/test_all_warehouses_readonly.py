"""Every registered write method is exercised through HTTP without replacing guards."""
import asyncio
import re
from collections import Counter
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import event, func, literal, select, text, union_all
from starlette.requests import Request

import app.database as database
from app.main import app
from app.models import Customer, User, UserWarehouse
from app.core.permissions import get_current_user, get_wh_id
from app.core.round5_access import read_scope
from app.core.security import create_access_token, hash_password, verify_password
from app.api.v1.dashboard import warehouse_cards
from tests.test_round2_permissions import auth
from tests.test_warehouse_cards import environment


WRITE_METHODS = {'POST','PUT','PATCH','DELETE'}
SELF_ROUTES = {('POST','/api/v1/auth/login'),('POST','/api/v1/auth/change-password'),
               ('POST','/api/v1/auth/attachment-session')}
ALL_WRITES = sorted({(m,r.path) for r in app.routes if isinstance(r,APIRoute)
                     for m in r.methods & WRITE_METHODS})
BLOCKED_WRITES = [r for r in ALL_WRITES if r not in SELF_ROUTES]
READONLY_POSTS = {'/api/v1/payroll/preview','/api/v1/supplier-quotes/purchase-preview',
                  '/api/v1/settings/backup','/api/v1/suppliers/ai-compare'}
MESSAGE = '全部仓汇总只读 请先进入具体仓库再操作'
GETS = ['/api/v1/dashboard/warehouse-cards','/api/v1/dashboard/boss-todos',
        '/api/v1/dashboard/warehouse-summary','/api/v1/warehouses','/api/v1/users',
        '/api/v1/customers','/api/v1/accounts','/api/v1/incoming',
        '/api/v1/employee-advances','/api/v1/salary-templates']


@pytest.fixture(scope='module')
def sandbox(tmp_path_factory):
    # One disposable schema and event loop for the exhaustive parameterization.
    # Each rejected request independently compares ALL model table counts.
    runner=asyncio.Runner()
    mp=pytest.MonkeyPatch()
    context=environment(tmp_path_factory.mktemp('all-readonly'),mp)
    engine,factory,client=runner.run(context.__aenter__())
    async def prepare():
        async with factory() as db:
            db.add(Customer(id=1,warehouse_id=1,customer_code='SYN-EXISTING',company_name='合成原客户'))
            db.add(User(id=91,username='synthetic-self',display_name='合成本人账号',role='warehouse_admin',
                warehouse_id=1,password_hash=hash_password('Synthetic-Old-2026'),extra_permissions=[]))
            await db.flush()
            db.add(UserWarehouse(user_id=91,warehouse_id=1))
            await db.flush()
            if engine.dialect.name=='postgresql':
                for table in database.Base.metadata.tables.values():
                    if 'id' in table.c and table.c.id.primary_key:
                        await db.execute(text(f"SELECT setval(pg_get_serial_sequence('{table.name}','id'),COALESCE((SELECT MAX(id) FROM {table.name}),0)+100)"))
            await db.commit()
    try:
        runner.run(prepare())
        yield runner,engine,factory,client
    finally:
        runner.run(context.__aexit__(None,None,None))
        runner.close()
        mp.undo()


async def table_counts(factory):
    queries=[select(literal(t.name),func.count()).select_from(t) for t in database.Base.metadata.tables.values()]
    async with factory() as db:
        return dict((await db.execute(union_all(*queries))).all())


def body_for(path):
    return {'action':'verify'} if path in ('/api/v1/expense-fund/review/batch',
        '/api/v1/expense-fund/recharge/review') else {}


async def rejected(sandbox,method,path,uid=1):
    _,engine,factory,client=sandbox
    before=await table_counts(factory)
    sql=[]
    def capture(conn,cursor,statement,parameters,context,executemany):
        sql.append(statement)
    event.listen(engine.sync_engine,'before_cursor_execute',capture)
    try:
        response=await client.request(method,re.sub(r'\{[^}]+\}','1',path),
            headers={**auth(uid),'X-Warehouse-ID':'all'},json=body_for(path))
    finally:
        event.remove(engine.sync_engine,'before_cursor_execute',capture)
    assert response.status_code==403,(method,path,response.status_code,response.text)
    assert response.json()['detail']==MESSAGE,(method,path,response.text)
    # Detect UPDATE as well as inserts/deletes, even if row totals would not change.
    assert sql and all(s.lstrip().upper().startswith('SELECT') for s in sql),(method,path,sql)
    assert await table_counts(factory)==before,(method,path)


def test_inventory_is_complete_and_post_previews_are_not_exempt():
    assert len(ALL_WRITES)==222
    assert Counter(m for m,_ in ALL_WRITES)=={'POST':145,'PUT':53,'DELETE':24}
    assert len(BLOCKED_WRITES)==219
    assert SELF_ROUTES.issubset(ALL_WRITES)
    assert all(('POST',p) in BLOCKED_WRITES for p in READONLY_POSTS)
    assert ('PUT','/api/v1/users/{user_id}') in BLOCKED_WRITES
    for r in app.routes:
        if isinstance(r,APIRoute) and r.methods & WRITE_METHODS and r.path!='/api/v1/auth/login':
            def has_auth(d):
                return d.call is get_current_user or any(has_auth(c) for c in d.dependencies)
            assert has_auth(r.dependant),r.path


@pytest.mark.parametrize('method,path',BLOCKED_WRITES,ids=[f'{m} {p}' for m,p in BLOCKED_WRITES])
def test_every_write_is_403_and_all_tables_unchanged(sandbox,method,path):
    sandbox[0].run(rejected(sandbox,method,path))


@pytest.mark.parametrize('uid',[3,4],ids=['finance','supervisor'])
def test_non_admin_all_preserves_403_for_every_business_write(sandbox,uid):
    # Before this change, all 438 requests were measured as 403 on e27a1eb.
    async def run():
        for method,path in BLOCKED_WRITES:
            await rejected(sandbox,method,path,uid)
    sandbox[0].run(run())


@pytest.mark.parametrize('path',GETS)
def test_get_requests_still_work_in_all_mode(sandbox,path):
    async def run():
        response=await sandbox[3].get(path,headers={**auth(1),'X-Warehouse-ID':'all'})
        assert response.status_code==200,(path,response.text)
        assert MESSAGE not in response.text
    sandbox[0].run(run())


SINGLE_WRITES=[
    ('POST','/api/v1/customers',{'customer_code':'SYN-NEW','company_name':'合成新客户'}),
    ('PUT','/api/v1/customers/1',{'company_name':'合成改名客户'}),
    ('POST','/api/v1/accounts',{'account_name':'合成新账户','account_type':'cash','account_number':'SYN-NEW','currency':'THB'}),
    ('PUT','/api/v1/accounts/1',{'account_name':'合成改名账户','account_type':'cash','account_number':'SYN-OLD','currency':'THB'}),
    ('POST','/api/v1/suppliers',{'name':'合成新供应商'}),
    ('PUT','/api/v1/suppliers/1',{'name':'合成改名供应商'}),
    ('POST','/api/v1/users',{'username':'synthetic-new-user','display_name':'合成主管','password':'Synthetic-New-2026','role':'supervisor','warehouse_ids':[1]}),
    ('POST','/api/v1/salary-templates',{'name':'合成日薪','type':'daily','amount':400}),
    ('POST','/api/v1/deduction-templates',{'name':'合成扣款'}),
    ('POST','/api/v1/income-expense/categories',{'name':'合成类别','type':'expense'}),
]


@pytest.mark.parametrize('method,path,body',SINGLE_WRITES,ids=[f'{m} {p}' for m,p,_ in SINGLE_WRITES])
def test_ten_single_warehouse_writes_succeed(sandbox,method,path,body):
    async def run():
        response=await sandbox[3].request(method,path,headers={**auth(1),'X-Warehouse-ID':'1'},json=body)
        assert response.status_code==200,(method,path,response.text)
    sandbox[0].run(run())


def test_self_login_all_is_allowed(sandbox):
    async def run():
        response=await sandbox[3].post('/api/v1/auth/login',headers={'X-Warehouse-ID':'all'},
            json={'username':'synthetic-self','password':'Synthetic-Old-2026'})
        assert response.status_code==200,response.text
        assert response.json()['user_id']==91
    sandbox[0].run(run())


def test_self_change_password_all_is_allowed(sandbox):
    async def run():
        response=await sandbox[3].post('/api/v1/auth/change-password',headers={**auth(91),'X-Warehouse-ID':'all'},
            json={'old_password':'Synthetic-Old-2026','new_password':'Synthetic-Changed-2026'})
        assert response.status_code==200,response.text
        async with sandbox[2]() as db:
            assert verify_password('Synthetic-Changed-2026',(await db.get(User,91)).password_hash)
    sandbox[0].run(run())


def test_self_attachment_session_and_clear_all_are_allowed(sandbox):
    async def run():
        for clear in (False,True):
            response=await sandbox[3].post('/api/v1/auth/attachment-session',
                headers={**auth(91),'X-Warehouse-ID':'all'},json={'clear':clear})
            assert response.status_code==200 and response.json()=={'ok':True}
            assert 'set-cookie' in response.headers
    sandbox[0].run(run())


def fake_request(method,path):
    return Request({'type':'http','method':method,'path':path,'query_string':b'',
        'headers':[(b'x-warehouse-id',b'all')],
        'route':SimpleNamespace(path=path,endpoint=warehouse_cards)})


def test_both_card_exceptions_only_apply_to_exact_get(sandbox):
    async def run():
        async with sandbox[2]() as db:
            credentials=HTTPAuthorizationCredentials(scheme='Bearer',credentials=create_access_token({'sub':'3'}))
            path='/api/v1/dashboard/warehouse-cards'
            request=fake_request('GET',path)
            user=await get_current_user(request,credentials,db)
            assert await read_scope(request,user,db) is user
            assert get_wh_id(user)==1  # Existing primary-warehouse fallback is unchanged.
            for method in WRITE_METHODS:
                with pytest.raises(HTTPException) as error:
                    await get_current_user(fake_request(method,path),credentials,db)
                assert error.value.status_code==403 and error.value.detail==MESSAGE
                with pytest.raises(HTTPException) as scope_error:
                    await read_scope(fake_request(method,path),user,db)
                assert scope_error.value.status_code==403
            other=fake_request('GET','/api/v1/dashboard/warehouse-summary')
            with pytest.raises(HTTPException) as error:
                await get_current_user(other,credentials,db)
            assert error.value.status_code==403
            with pytest.raises(HTTPException) as error:
                await read_scope(other,user,db)
            assert error.value.status_code==403
        response=await sandbox[3].post(path,headers={**auth(1),'X-Warehouse-ID':'all'},json={})
        assert response.status_code==405  # Unregistered method does not become a card endpoint.
    sandbox[0].run(run())

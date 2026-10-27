"""第二轮：16 条真实 HTTP 请求、共用接口、仓库隔离、启动迁移回归。

使用隔离 SQLite 文件；不连接线上数据库。运行见 requirements-test.txt。
"""
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from io import BytesIO

import pytest
from httpx import ASGITransport, AsyncClient
from PIL import Image
from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

import app.database as database
from app.main import app
from app.core.security import create_access_token
from app.core.menu_registry import MENU_PERMISSIONS_BY_KEY
from app.models import User, Warehouse, UserWarehouse, Customer, PaymentAccount, RechargeDeclaration, SystemSetting
from app.services.permission_migrations import (
    backfill_round2_permissions, ROUND2_PERMISSION_MARKER, ROUND2_PERMISSIONS,
)

pytest.importorskip('aiosqlite')
pytest.importorskip('greenlet')

RECHARGE = {"customer_id": 1, "declare_date": "2026-10-16", "amount": 100}
CUSTOMER = {"customer_code": "NEW", "company_name": "新客户"}
ACCOUNT = {"account_name": "新账户", "account_type": "bank", "account_number": "123"}
# 删除使用无关联的客户 3，其他请求使用客户 1。
CASES = [
    ('GET', '/recharge', 'recharge', None),
    ('POST', '/recharge', 'recharge', RECHARGE),
    ('GET', '/recharge/1', 'recharge', None),
    ('PUT', '/recharge/1', 'recharge', RECHARGE),
    ('DELETE', '/recharge/1', 'recharge', None),
    ('GET', '/customers', 'customers', None),
    ('POST', '/customers', 'customers', CUSTOMER),
    ('GET', '/customers/1', 'customers', None),
    ('PUT', '/customers/1', 'customers', {'company_name': '已编辑'}),
    ('DELETE', '/customers/3', 'customers', None),
    ('GET', '/accounts', 'accounts', None),
    ('POST', '/accounts', 'accounts', ACCOUNT),
    ('PUT', '/accounts/1', 'accounts', ACCOUNT),
    ('PUT', '/accounts/1/toggle-status', 'accounts', None),
    ('DELETE', '/accounts/1', 'accounts', None),
    ('POST', '/upload/recharge-screenshot', 'recharge', 'upload'),
]


def png():
    buf = BytesIO()
    Image.new('RGB', (2, 2), 'white').save(buf, format='PNG')
    return buf.getvalue()


@asynccontextmanager
async def environment(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'round2.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(database, 'async_session_factory', lambda: factory)
    import app.api.v1.upload as upload
    monkeypatch.setattr(upload, 'UPLOAD_DIR', str(tmp_path / 'uploads'))
    try:
        async with engine.begin() as conn:
            await conn.run_sync(database.Base.metadata.create_all)
        async with factory() as db:
            db.add_all([Warehouse(id=i, name=f'仓{i}', code=f'WH{i}') for i in (1, 2)])
            for uid, role in enumerate(('warehouse_admin', 'super_admin', 'staff', 'supervisor'), 1):
                db.add(User(id=uid, username=role, display_name=role, role=role,
                            password_hash='unused', warehouse_id=1, extra_permissions=[]))
                db.add(UserWarehouse(user_id=uid, warehouse_id=1))
            db.add_all([Customer(id=i, warehouse_id=(2 if i == 2 else 1),
                                customer_code=f'C{i}', company_name=f'客户{i}') for i in (1, 2, 3)])
            db.add_all([PaymentAccount(id=i, warehouse_id=i, account_name=f'账户{i}',
                                      account_type='bank', account_number=str(i)) for i in (1, 2)])
            db.add_all([RechargeDeclaration(id=i, warehouse_id=i, customer_id=i,
                                            declare_date=datetime(2026, 10, 16), amount=100,
                                            declarer_id=1) for i in (1, 2)])
            await db.commit()
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
            yield engine, factory, client
    finally:
        await engine.dispose()


def auth(uid):
    return {'Authorization': 'Bearer ' + create_access_token({'sub': str(uid)})}


async def set_perms(factory, uid, permissions):
    async with factory() as db:
        await db.execute(update(User).where(User.id == uid).values(extra_permissions=permissions))
        await db.commit()


async def request(client, method, path, body, uid):
    kwargs = {'headers': auth(uid)}
    if body == 'upload':
        kwargs.update(data={'recharge_id': '1'}, files={'file': ('test.png', png(), 'image/png')})
    elif body is not None:
        kwargs['json'] = body
    return await client.request(method, '/api/v1' + path, **kwargs)


@pytest.mark.parametrize('method,path,module,body', CASES, ids=[f'{m} {p}' for m,p,_,_ in CASES])
@pytest.mark.parametrize('uid,granted', [(3, False), (4, False), (3, True), (4, True), (1, False), (2, False)],
                         ids=['staff-deny','supervisor-deny','staff-allow','supervisor-allow','admin','super-admin'])
def test_every_endpoint(tmp_path, monkeypatch, method, path, module, body, uid, granted):
    async def run():
        async with environment(tmp_path, monkeypatch) as (_, factory, client):
            if granted:
                await set_perms(factory, uid, [MENU_PERMISSIONS_BY_KEY[module].label])
            response = await request(client, method, path, body, uid)
            if uid in (3, 4) and not granted:
                assert response.status_code == 403, response.text
                assert response.json()['detail'].startswith('无此操作权限'), response.text
            else:
                # 保留旧业务规则：财务不能新建/删除客户和账户；超管多数业务操作原本被拒。
                staff_business_denied = uid == 3 and (method, path) in {
                    ('POST','/customers'), ('DELETE','/customers/3'),
                    ('POST','/accounts'), ('DELETE','/accounts/1'),
                }
                super_business_denied = uid == 2 and (method, path) not in {
                    ('GET','/recharge/1'), ('GET','/customers/1'), ('POST','/upload/recharge-screenshot'),
                }
                account_config_denied = uid in (3, 4) and path.startswith("/accounts") and method != "GET"
                expected = 403 if staff_business_denied or super_business_denied or account_config_denied else 200
                assert response.status_code == expected, response.text
                if expected == 403:
                    assert not response.json()['detail'].startswith('无此操作权限')
    asyncio.run(run())


@pytest.mark.parametrize('uid', [3, 4])
def test_shared_reads_and_upload(tmp_path, monkeypatch, uid):
    async def run():
        async with environment(tmp_path, monkeypatch) as (_, factory, client):
            for key in ('customers', 'recharge', 'incoming', 'credit'):
                await set_perms(factory, uid, [MENU_PERMISSIONS_BY_KEY[key].label])
                response = await client.get('/api/v1/customers', headers=auth(uid))
                assert response.status_code == 200, response.text
                assert {r['warehouse_id'] for r in response.json()['data']} == {1}
                if key in ('incoming', 'credit'):
                    page_api = '/incoming' if key == 'incoming' else '/credit'
                    page_result = await client.get('/api/v1' + page_api, headers=auth(uid))
                    assert page_result.status_code == 200, page_result.text
                if key != 'customers':
                    assert (await client.get('/api/v1/customers/1', headers=auth(uid))).status_code == 403
            for key in ('accounts', 'operating', 'other_income_expense'):
                await set_perms(factory, uid, [MENU_PERMISSIONS_BY_KEY[key].label])
                response = await client.get('/api/v1/accounts', headers=auth(uid))
                assert response.status_code == 200, response.text
                assert {r['warehouse_id'] for r in response.json()['data']} == {1}
                if key != 'accounts':
                    assert (await client.put('/api/v1/accounts/1', json=ACCOUNT, headers=auth(uid))).status_code == 403
                    page_result = await client.get('/api/v1/income-expense/income', headers=auth(uid))
                    assert page_result.status_code == 200, page_result.text
            await set_perms(factory, uid, ['到账流水'])
            assert (await request(client, 'POST', '/upload/recharge-screenshot', 'upload', uid)).status_code == 200
            # 无关权限不能放行共用接口。
            await set_perms(factory, uid, ['报销管理'])
            for path in ('/customers', '/accounts'):
                assert (await client.get('/api/v1' + path, headers=auth(uid))).status_code == 403
            assert (await request(client, 'POST', '/upload/recharge-screenshot', 'upload', uid)).status_code == 403
    asyncio.run(run())


@pytest.mark.parametrize('uid', [1, 3, 4])
def test_warehouse_isolation(tmp_path, monkeypatch, uid):
    async def run():
        async with environment(tmp_path, monkeypatch) as (_, factory, client):
            await set_perms(factory, uid, list(ROUND2_PERMISSIONS))
            for path in ('/recharge','/customers','/accounts'):
                result = await client.get('/api/v1' + path, headers=auth(uid))
                assert result.status_code == 200, result.text
                assert {r['warehouse_id'] for r in result.json()['data']} == {1}
            for method, path, body in [
                ('GET','/recharge/2',None), ('PUT','/recharge/2',RECHARGE), ('DELETE','/recharge/2',None),
                ('GET','/customers/2',None), ('PUT','/customers/2',{'company_name':'越权'}), ('DELETE','/customers/2',None),
                ('PUT','/accounts/2',ACCOUNT), ('PUT','/accounts/2/toggle-status',None), ('DELETE','/accounts/2',None),
            ]:
                result = await request(client, method, path, body, uid)
                assert result.status_code == 403, result.text
            response = await client.post('/api/v1/upload/recharge-screenshot', headers=auth(uid),
                                         data={'recharge_id':'2'}, files={'file':('test.png',png(),'image/png')})
            assert response.status_code == 403, response.text
            # 本仓申报也不能通过提交外仓客户 ID 绕过隔离。
            for method, path in [('POST', '/recharge'), ('PUT', '/recharge/1')]:
                response = await client.request(method, '/api/v1' + path, headers=auth(uid),
                                                json={**RECHARGE, 'customer_id': 2})
                assert response.status_code == 403, response.text
                assert response.json()['detail'] == '只能使用申报所属仓库的客户'
            # 伪造仓库请求头不能扩大仓库范围。
            result = await client.get('/api/v1/customers', headers={**auth(uid),'X-Warehouse-ID':'2'})
            assert {r['warehouse_id'] for r in result.json()['data']} == {1}
    asyncio.run(run())


def test_migration_database_idempotence_and_revocation(tmp_path, monkeypatch):
    async def run():
        async with environment(tmp_path, monkeypatch) as (engine, factory, _):
            await set_perms(factory, 3, None)
            await set_perms(factory, 4, ['到账流水', ROUND2_PERMISSIONS[0], ROUND2_PERMISSIONS[0]])
            async with factory() as db:
                db.add(User(id=5, username='inactive', display_name='停用财务', role='staff',
                            password_hash='unused', is_active=False, extra_permissions=['自定义旧权限']))
                await db.commit()
            async with engine.begin() as conn:
                assert await backfill_round2_permissions(conn) == 3
            async with factory() as db:
                rows = (await db.execute(select(User.id, User.extra_permissions).order_by(User.id))).all()
                values = dict(rows)
                assert values[1] == values[2] == []
                assert values[3] == list(ROUND2_PERMISSIONS)
                assert values[4] == ['到账流水', *ROUND2_PERMISSIONS]
                assert values[5] == ['自定义旧权限', *ROUND2_PERMISSIONS]
                assert (await db.execute(select(func.count(SystemSetting.id)).where(
                    SystemSetting.key == ROUND2_PERMISSION_MARKER))).scalar_one() == 1
                print('\n迁移后数据库权限：', values)
            # 重启跳过标记，管理员后续撤销的权限不会被补回。
            await set_perms(factory, 3, [])
            async with engine.begin() as conn:
                assert await backfill_round2_permissions(conn) == 0
            async with factory() as db:
                assert (await db.execute(select(User.extra_permissions).where(User.id == 3))).scalar_one() == []
    asyncio.run(run())


def test_migration_rolls_back_marker_and_users(tmp_path, monkeypatch):
    async def run():
        async with environment(tmp_path, monkeypatch) as (engine, factory, _):
            with pytest.raises(RuntimeError):
                async with engine.begin() as conn:
                    await backfill_round2_permissions(conn)
                    raise RuntimeError('simulate startup transaction failure')
            async with factory() as db:
                assert (await db.execute(select(User.extra_permissions).where(User.id == 3))).scalar_one() == []
                assert (await db.execute(select(SystemSetting.id).where(
                    SystemSetting.key == ROUND2_PERMISSION_MARKER))).first() is None
    asyncio.run(run())


def test_route_inventory_has_no_missing_endpoint():
    actual = {(method, route.path.removeprefix('/api/v1')) for route in app.routes
              if getattr(route,'path','').startswith(('/api/v1/recharge','/api/v1/customers','/api/v1/accounts'))
              or getattr(route,'path','') == '/api/v1/upload/recharge-screenshot'
              for method in route.methods}
    expected = {(method, path.replace('/1','/{recharge_id}') if path.startswith('/recharge/') else
                 path.replace('/1','/{customer_id}').replace('/3','/{customer_id}') if path.startswith('/customers/') else
                 path.replace('/1','/{account_id}') if path.startswith('/accounts/') else path)
                for method,path,_,_ in CASES}
    assert actual == expected


def test_startup_runs_backfill_after_seed_returns(tmp_path, monkeypatch):
    import scripts.seed as startup
    from app.services.permission_migrations import ROUND3_PERMISSIONS, ROUND4_PERMISSIONS, ROUND5_PERMISSIONS, ROUND6_PERMISSIONS, ROUND9_SUPERVISOR_PERMISSIONS

    async def run():
        async with environment(tmp_path, monkeypatch) as (engine, factory, _):
            calls = []
            async def existing_database_seed():
                calls.append('seed-returned')
                return
            monkeypatch.setattr(startup, 'seed', existing_database_seed)
            monkeypatch.setattr(startup, '_get_engine', lambda: engine)
            await startup.initialize()
            await startup.initialize()
            assert calls == ['seed-returned', 'seed-returned']
            async with factory() as db:
                assert (await db.execute(select(User.extra_permissions).where(User.id == 3))).scalar_one() == [*ROUND2_PERMISSIONS, *ROUND3_PERMISSIONS, *ROUND4_PERMISSIONS, *ROUND5_PERMISSIONS, *ROUND6_PERMISSIONS, '垫款单']
                assert set((await db.get(User, 4)).extra_permissions) == set(ROUND9_SUPERVISOR_PERMISSIONS)
                assert (await db.execute(select(func.count(SystemSetting.id)).where(
                    SystemSetting.key == ROUND2_PERMISSION_MARKER))).scalar_one() == 1
    asyncio.run(run())

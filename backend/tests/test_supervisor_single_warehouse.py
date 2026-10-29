"""Real HTTP single-warehouse validation; only disposable synthetic databases."""
import asyncio
from contextlib import asynccontextmanager

import pytest
from sqlalchemy import func, select, text

from app.models import User, UserWarehouse, Warehouse
from tests.test_round2_permissions import auth
from tests.test_warehouse_cards import environment as cards_environment


MESSAGE = '主管只能分配一个仓库'


@asynccontextmanager
async def environment(tmp_path, monkeypatch):
    async with cards_environment(tmp_path, monkeypatch) as (engine, factory, client):
        async with factory() as db:
            db.add(Warehouse(id=3,name='未授权合成仓',code='FOREIGN'))
            if engine.dialect.name == 'postgresql':
                await db.execute(text("SELECT setval(pg_get_serial_sequence('users','id'),100)"))
            await db.commit()
        yield factory, client


async def state(factory, uid):
    async with factory() as db:
        user=await db.get(User,uid)
        ids=list((await db.execute(select(UserWarehouse.warehouse_id).where(
            UserWarehouse.user_id==uid).order_by(UserWarehouse.warehouse_id))).scalars())
        return {'name':user.display_name,'role':user.role,'active':user.is_active,
                'primary':user.warehouse_id,'warehouses':ids,'permissions':user.extra_permissions}


def create_body(role='supervisor', **values):
    return {'username':'synthetic-new','display_name':'合成新账号','password':'Synthetic-Only-2026',
            'role':role,'warehouse_ids':[1],**values}


def test_create_supervisor_one_warehouse(tmp_path,monkeypatch):
    async def run():
        async with environment(tmp_path,monkeypatch) as (factory,client):
            response=await client.post('/api/v1/users',headers=auth(2),json=create_body())
            assert response.status_code==200,response.text
            saved=await state(factory,response.json()['id'])
            assert saved['role']=='supervisor' and saved['warehouses']==[1] and saved['primary']==1
    asyncio.run(run())


def test_create_supervisor_two_warehouses_rejected_without_writes(tmp_path,monkeypatch):
    async def run():
        async with environment(tmp_path,monkeypatch) as (factory,client):
            async with factory() as db:
                before=(await db.execute(select(func.count(User.id)))).scalar_one()
            response=await client.post('/api/v1/users',headers=auth(2),json=create_body(warehouse_ids=[1,2]))
            assert response.status_code==400 and response.json()['detail']==MESSAGE
            async with factory() as db:
                assert (await db.execute(select(func.count(User.id)))).scalar_one()==before
    asyncio.run(run())


def test_create_finance_two_warehouses_unchanged(tmp_path,monkeypatch):
    async def run():
        async with environment(tmp_path,monkeypatch) as (factory,client):
            response=await client.post('/api/v1/users',headers=auth(2),json=create_body('staff',warehouse_ids=[1,2]))
            assert response.status_code==200,response.text
            assert (await state(factory,response.json()['id']))['warehouses']==[1,2]
    asyncio.run(run())


def test_multi_warehouse_finance_becoming_supervisor_rejected(tmp_path,monkeypatch):
    async def run():
        async with environment(tmp_path,monkeypatch) as (factory,client):
            before=await state(factory,3)
            response=await client.put('/api/v1/users/3',headers=auth(2),json={'role':'supervisor'})
            assert response.status_code==400 and response.json()['detail']==MESSAGE
            assert await state(factory,3)==before
    asyncio.run(run())


def test_legacy_multi_warehouse_supervisor_name_only_allowed(tmp_path,monkeypatch):
    async def run():
        async with environment(tmp_path,monkeypatch) as (factory,client):
            before=await state(factory,4)
            response=await client.put('/api/v1/users/4',headers=auth(1),json={'display_name':'合成改名'})
            assert response.status_code==200,response.text
            after=await state(factory,4)
            assert after=={**before,'name':'合成改名'}
    asyncio.run(run())


def test_legacy_supervisor_assign_one_warehouse(tmp_path,monkeypatch):
    async def run():
        async with environment(tmp_path,monkeypatch) as (factory,client):
            response=await client.put('/api/v1/users/4',headers=auth(1),json={'warehouse_ids':[2]})
            assert response.status_code==200,response.text
            saved=await state(factory,4)
            assert saved['warehouses']==[2] and saved['primary']==2
    asyncio.run(run())


def test_legacy_supervisor_explicitly_assign_two_rejected(tmp_path,monkeypatch):
    async def run():
        async with environment(tmp_path,monkeypatch) as (factory,client):
            before=await state(factory,4)
            response=await client.put('/api/v1/users/4',headers=auth(1),json={'warehouse_ids':[1,2]})
            assert response.status_code==400 and response.json()['detail']==MESSAGE
            assert await state(factory,4)==before
    asyncio.run(run())


def test_admin_can_only_assign_own_warehouses(tmp_path,monkeypatch):
    async def run():
        async with environment(tmp_path,monkeypatch) as (factory,client):
            good=await client.post('/api/v1/users',headers=auth(1),json=create_body())
            assert good.status_code==200,good.text
            bad=await client.post('/api/v1/users',headers=auth(1),json=create_body(
                username='synthetic-foreign',warehouse_ids=[3]))
            assert bad.status_code==403
            assert bad.json()['detail']=='无权限将用户分配到该仓库'
            bad_edit=await client.put('/api/v1/users/4',headers=auth(1),json={'warehouse_ids':[3]})
            assert bad_edit.status_code==403
            assert (await state(factory,4))['warehouses']==[1,2]
    asyncio.run(run())


@pytest.mark.parametrize('payload',[{'is_active':False},
    {'action_permissions':[],'permission_reason':'合成权限核对'},
    {'display_name':'合成改名','role':'supervisor'},
    {'display_name':'合成改名','warehouse_ids':None}])
def test_legacy_supervisor_unrelated_changes_keep_memberships(tmp_path,monkeypatch,payload):
    async def run():
        async with environment(tmp_path,monkeypatch) as (factory,client):
            response=await client.put('/api/v1/users/4',headers=auth(1),json=payload)
            assert response.status_code==200,response.text
            assert (await state(factory,4))['warehouses']==[1,2]
    asyncio.run(run())


def test_supervisor_cannot_clear_all_warehouses(tmp_path,monkeypatch):
    async def run():
        async with environment(tmp_path,monkeypatch) as (factory,client):
            before=await state(factory,4)
            response=await client.put('/api/v1/users/4',headers=auth(1),json={'warehouse_ids':[]})
            assert response.status_code==400 and response.json()['detail']==MESSAGE
            assert await state(factory,4)==before
    asyncio.run(run())


def test_single_warehouse_field_supported(tmp_path,monkeypatch):
    async def run():
        async with environment(tmp_path,monkeypatch) as (factory,client):
            created=await client.post('/api/v1/users',headers=auth(2),json=create_body(warehouse_ids=None,warehouse_id=2))
            assert created.status_code==200,created.text
            response=await client.put('/api/v1/users/4',headers=auth(1),json={'warehouse_id':2})
            assert response.status_code==200,response.text
            assert (await state(factory,4))['warehouses']==[2]
    asyncio.run(run())


def test_role_conversion_with_explicit_one_warehouse_allowed(tmp_path,monkeypatch):
    async def run():
        async with environment(tmp_path,monkeypatch) as (factory,client):
            response=await client.put('/api/v1/users/3',headers=auth(2),json={
                'role':'supervisor','warehouse_ids':[1],'action_permissions':[],'permission_reason':'合成岗位调整'})
            assert response.status_code==200,response.text
            saved=await state(factory,3)
            assert saved['role']=='supervisor' and saved['warehouses']==[1]
    asyncio.run(run())


@pytest.mark.parametrize('role',['warehouse_admin','staff','warehouse_labor'])
def test_other_roles_create_and_edit_multiple_warehouses_unchanged(tmp_path,monkeypatch,role):
    async def run():
        async with environment(tmp_path,monkeypatch) as (factory,client):
            created=await client.post('/api/v1/users',headers=auth(2),json=create_body(role,warehouse_ids=[1,2]))
            assert created.status_code==200,created.text
            uid=created.json()['id']
            response=await client.put(f'/api/v1/users/{uid}',headers=auth(2),json={'warehouse_ids':[1,2,3]})
            assert response.status_code==200,response.text
            assert (await state(factory,uid))['warehouses']==[1,2,3]
    asyncio.run(run())


def test_warehouse_ids_take_precedence_on_role_change(tmp_path,monkeypatch):
    async def run():
        async with environment(tmp_path,monkeypatch) as (factory,client):
            response=await client.put('/api/v1/users/3',headers=auth(2),json={
                'role':'supervisor','warehouse_ids':[1,2],'warehouse_id':1})
            assert response.status_code==400 and response.json()['detail']==MESSAGE
            assert (await state(factory,3))['role']=='staff'
    asyncio.run(run())

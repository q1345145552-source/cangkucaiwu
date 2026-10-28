"""第九轮：仅主管、清单派生、事务回滚与真实启动幂等。"""
import asyncio
import json
import pytest
from sqlalchemy import select, update
from app.core.menu_registry import MENU_PERMISSIONS
from app.models import User, UserWarehouse, SystemSetting
from app.services import permission_migrations as migrations
from tests.test_round3_permissions import hr_environment, snapshot
from tests.test_round2_permissions import auth


def test_registry_source():
    expected = tuple(p.label for p in MENU_PERMISSIONS if p.selectable)
    assert migrations.ROUND9_SUPERVISOR_PERMISSIONS == expected
    assert len(expected) == len(set(expected)) == len([p for p in MENU_PERMISSIONS if p.selectable])
    assert not set(expected) & {p.label for p in MENU_PERMISSIONS if not p.selectable}
    assert migrations.ROUND9_SUPERVISOR_PERMISSION_MARKER not in [getattr(migrations, f'ROUND{r}_PERMISSION_MARKER') for r in (2,3,4,5,6)]


@pytest.mark.parametrize('rollback', [False, True])
def test_supervisors_only_and_transaction(tmp_path, monkeypatch, rollback):
    async def run():
        async with hr_environment(tmp_path, monkeypatch) as (engine, factory, _):
            async with factory() as db:
                await db.execute(update(User).where(User.id == 4).values(extra_permissions=None))
                await db.execute(update(User).where(User.id == 3).values(extra_permissions=['自定义旧权限','充值申报']))
                for uid,wid,active,perms in ((7,2,True,['充值申报','充值申报']),(8,1,False,[]),(9,1,True,[*migrations.ROUND9_SUPERVISOR_PERMISSIONS,'旧权限保留'])):
                    db.add(User(id=uid,username=f'supervisor{uid}',display_name='测试主管',role='supervisor',warehouse_id=wid,is_active=active,password_hash='unused',extra_permissions=perms))
                    db.add(UserWarehouse(user_id=uid,warehouse_id=wid))
                await db.commit()
                before={u.id:u.extra_permissions for u in (await db.execute(select(User))).scalars()}
            payroll_before=await snapshot(factory)
            if rollback:
                with pytest.raises(RuntimeError):
                    async with engine.begin() as conn:
                        assert await migrations.backfill_round9_supervisor_permissions(conn)==1
                        raise RuntimeError('模拟迁移事务失败')
                async with factory() as db:
                    assert {u.id:u.extra_permissions for u in (await db.execute(select(User))).scalars()}==before
                    assert not (await db.execute(select(SystemSetting).where(SystemSetting.key==migrations.ROUND9_SUPERVISOR_PERMISSION_MARKER))).first()
            async with engine.begin() as conn:assert await migrations.backfill_round9_supervisor_permissions(conn)==1
            async with engine.begin() as conn:assert await migrations.backfill_round9_supervisor_permissions(conn)==0
            async with factory() as db:
                users={u.id:u for u in (await db.execute(select(User))).scalars()}
                assert set(users[7].extra_permissions)==set(migrations.ROUND9_SUPERVISOR_PERMISSIONS)
                assert len(users[7].extra_permissions)==len(migrations.ROUND9_SUPERVISOR_PERMISSIONS)
                for uid in (4,8):assert users[uid].extra_permissions==before[uid]  # null/empty never implies a grant
                assert users[9].extra_permissions==before[9]
                for uid,u in users.items():
                    if u.role!='supervisor':assert u.extra_permissions==before[uid],(uid,u.role)
                assert len((await db.execute(select(SystemSetting).where(SystemSetting.key==migrations.ROUND9_SUPERVISOR_PERMISSION_MARKER))).scalars().all())==1
            assert await snapshot(factory)==payroll_before
    asyncio.run(run())


def test_real_startup_and_revocation(tmp_path,monkeypatch):
    async def run():
        import scripts.seed as startup
        async with hr_environment(tmp_path,monkeypatch) as (engine,factory,client):
            async with factory() as db:
                db.add_all([SystemSetting(warehouse_id=1,key=getattr(migrations,f'ROUND{r}_PERMISSION_MARKER'),value='true') for r in (2,3,4,5,6)])
                await db.commit()
                finance_before=(await db.get(User,3)).extra_permissions
            calls=[]
            async def seeded():calls.append('seed-returned')
            monkeypatch.setattr(startup,'seed',seeded)
            monkeypatch.setattr(startup,'_get_engine',lambda:engine)
            before=await snapshot(factory)
            await startup.initialize()
            await startup.initialize()
            async with factory() as db:
                actual=(await db.get(User,4)).extra_permissions
                assert actual==[]
                assert (await db.get(User,3)).extra_permissions==finance_before
                print('\n测试库主管权限：'+json.dumps(actual,ensure_ascii=False))
                await db.execute(update(User).where(User.id==4).values(extra_permissions=[]))
                db.add(User(id=7,username='new-supervisor',display_name='标记后新主管',role='supervisor',warehouse_id=1,password_hash='unused',extra_permissions=[]))
                await db.commit()
            await startup.initialize()
            async with factory() as db:
                for uid in (4,7):assert (await db.get(User,uid)).extra_permissions==[]
                assert (await db.get(User,3)).extra_permissions==finance_before
                assert len((await db.execute(select(SystemSetting).where(SystemSetting.key==migrations.ROUND9_SUPERVISOR_PERMISSION_MARKER))).scalars().all())==1
            assert len(calls)==3
            assert await snapshot(factory)==before
            denied=await client.get('/api/v1/recharge',headers=auth(4))
            assert denied.status_code==403 and set(denied.json())=={'detail'}
    asyncio.run(run())


def test_migrated_supervisor_each_permission_read(tmp_path,monkeypatch):
    async def run():
        async with hr_environment(tmp_path,monkeypatch) as (engine,factory,client):
            async with factory() as db:
                await db.execute(update(User).where(User.id==4).values(extra_permissions=['员工档案']))
                await db.commit()
            before=await snapshot(factory)
            async with engine.begin() as conn:assert await migrations.backfill_round9_supervisor_permissions(conn)==1
            # Historical all-menu grants remain bounded by the confirmed onsite role.
            for path in ('/payroll','/reports/cost-funds-debt','/income-expense/ledger','/payable'):
                response=await client.get('/api/v1'+path,headers=auth(4))
                assert response.status_code==403 and set(response.json())=={'detail'},(path,response.text)
            accounts=await client.get('/api/v1/accounts',headers=auth(4))
            assert accounts.status_code==200 and accounts.json()['scope']=='account_selection_only'
            assert all(set(row)=={'id','warehouse_id','account_name','currency','status'} for row in accounts.json()['data'])
            for path in ('/employees','/attendance/leaves','/overtime','/suppliers/categories'):
                response=await client.get('/api/v1'+path,headers=auth(4))
                assert response.status_code==200,(path,response.text)
            assert await snapshot(factory)==before
    asyncio.run(run())

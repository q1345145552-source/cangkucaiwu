import asyncio,copy
import pytest
from fastapi import HTTPException
from sqlalchemy import text,select,func
from app.models import PurchaseOrder,User,InventoryAccount
from app.services.inventory_migration import MODELS,migrate_inventory,ensure_inventory
from tests.test_procurement_risk_round8 import fixture,scenario,counts
from tests.test_incoming_operations import environment,URL
pytestmark=pytest.mark.skipif(not URL,reason='Disposable localhost PostgreSQL only')

def test_empty_base_and_repeated_migration_new_tables_stay_empty(tmp_path,monkeypatch):
    async def run():
        async with environment(tmp_path,monkeypatch) as (engine,f,c):
            async with engine.begin() as conn:
                for m in reversed(MODELS):await conn.run_sync(lambda c,m=m:m.__table__.drop(c,checkfirst=True))
                await migrate_inventory(conn);await migrate_inventory(conn);await ensure_inventory(conn)
            async with f() as db:
                for m in MODELS:assert (await db.execute(select(func.count()).select_from(m))).scalar_one()==0
    asyncio.run(run())

def test_old_data_not_backfilled_and_missing_critical_constraints_fail_closed(tmp_path,monkeypatch):
    async def run():
        async with fixture(tmp_path,monkeypatch) as (engine,f,c,_):
            await scenario(c,f);before=await counts(f)
            async with f() as db:
                orders=[(p.id,copy.deepcopy(p.items),p.total_amount,p.status) for p in (await db.execute(select(PurchaseOrder))).scalars()]
                grants=[(u.id,copy.deepcopy(u.extra_permissions)) for u in (await db.execute(select(User))).scalars()]
            async with engine.begin() as conn:
                for m in reversed(MODELS):await conn.run_sync(lambda c,m=m:m.__table__.drop(c,checkfirst=True))
                await migrate_inventory(conn);await migrate_inventory(conn)
                try:
                    async with conn.begin_nested():await conn.execute(text('SELECT 1/0'))
                except Exception:pass
                assert (await conn.execute(text('SELECT 1'))).scalar_one()==1
            assert await counts(f)==before
            async with f() as db:
                assert [(p.id,p.items,p.total_amount,p.status) for p in (await db.execute(select(PurchaseOrder))).scalars()]==orders
                assert [(u.id,u.extra_permissions) for u in (await db.execute(select(User))).scalars()]==grants
                for m in MODELS:assert (await db.execute(select(func.count()).select_from(m))).scalar_one()==0
            for table,name in [('inventory_receipt_links','uq_inventory_receipt_line'),('inventory_accounts','ck_inventory_nonnegative')]:
                async with engine.begin() as conn:
                    async with conn.begin_nested() as savepoint:
                        await conn.execute(text(f'ALTER TABLE {table} DROP CONSTRAINT {name}'))
                        with pytest.raises(HTTPException) as e:await ensure_inventory(conn)
                        assert e.value.status_code==503 and name in e.value.detail['missing'];await savepoint.rollback()
    asyncio.run(run())

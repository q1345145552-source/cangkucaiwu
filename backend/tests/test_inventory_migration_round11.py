import asyncio,copy
import pytest
from fastapi import HTTPException
from sqlalchemy import select,func,text
from app.models import InventoryAccount,InventoryStocktake,InventoryControl,User
from app.services.inventory_migration import MODELS,migrate_inventory,ensure_inventory
from tests.test_inventory_round11 import fixture,setup,submit,review
from tests.test_incoming_operations import URL
pytestmark=pytest.mark.skipif(not URL,reason='Own disposable loopback database only')
NEW=MODELS[-2:]

def test_old_round10_stock_grants_and_journal_unchanged_new_empty_repeat_upgrade(tmp_path,monkeypatch):
 async def run():
  async with fixture(tmp_path,monkeypatch)as(engine,f,c,_):
   _,a=await setup(c)
   async with f()as db:
    before=(await db.execute(text('SELECT id,recorded_quantity,opening_at,revision FROM inventory_accounts ORDER BY id'))).all()
    grants=[(u.id,copy.deepcopy(u.extra_permissions))for u in(await db.execute(select(User))).scalars()]
   async with engine.begin()as conn:
    for m in reversed(NEW):await conn.run_sync(lambda c,m=m:m.__table__.drop(c,checkfirst=True))
    await migrate_inventory(conn);await migrate_inventory(conn);await ensure_inventory(conn)
   async with f()as db:
    assert(await db.execute(text('SELECT id,recorded_quantity,opening_at,revision FROM inventory_accounts ORDER BY id'))).all()==before
    assert[(u.id,u.extra_permissions)for u in(await db.execute(select(User))).scalars()]==grants
    for model in NEW:assert(await db.execute(select(func.count()).select_from(model))).scalar_one()==0
   entry,_=await submit(c,a);done,_=await review(c,entry['data'])
   async with engine.begin()as conn:await migrate_inventory(conn);await migrate_inventory(conn)
   async with f()as db:
    assert(await db.get(InventoryAccount,a['id'])).recorded_quantity==95
    assert(await db.get(InventoryStocktake,entry['data']['id'])).adjustment_id==done['movement_id']
    assert(await db.execute(select(func.count()).select_from(InventoryStocktake))).scalar_one()==1
 asyncio.run(run())

def test_new_safety_constraints_fail_closed_and_savepoint_does_not_abort_outer(tmp_path,monkeypatch):
 async def run():
  async with fixture(tmp_path,monkeypatch)as(engine,f,c,_):
   async with engine.begin()as conn:
    for table,name in [('inventory_stocktakes','ck_inventory_count_nonnegative'),('inventory_controls','ck_inventory_minimum'),('inventory_controls','ck_inventory_usage_ratio')]:
     async with conn.begin_nested()as sp:
      await conn.execute(text(f'ALTER TABLE {table} DROP CONSTRAINT {name}'))
      await conn.execute(text(f'ALTER TABLE {table} ADD CONSTRAINT {name} CHECK (1=1)'))
      with pytest.raises(HTTPException)as error:await ensure_inventory(conn)
      assert error.value.status_code==503 and name+'_definition'in error.value.detail['missing'];await sp.rollback()
    try:
     async with conn.begin_nested():await conn.execute(text('SELECT 1/0'))
    except Exception:pass
    assert(await conn.execute(text('SELECT 1'))).scalar_one()==1
    await ensure_inventory(conn)
 asyncio.run(run())

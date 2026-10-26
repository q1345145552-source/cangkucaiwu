"""R9 migrations: actual disposable schema DDL, no real connection or backfill."""
import asyncio
import pytest
from sqlalchemy import select,func,text
from fastapi import HTTPException
from app.models import PurchaseOrder,PayableBill,SystemSetting
from app.services.procurement_control_migration import MODELS,migrate_procurement_controls,ensure_procurement_controls
from tests.test_procurement_risk_round8 import fixture,scenario,counts
from tests.test_incoming_operations import URL
pytestmark=pytest.mark.skipif(not URL,reason='Disposable localhost only')

def test_upgrade_existing_rows_repeat_and_constraint_failure(tmp_path,monkeypatch):
 async def run():
  async with fixture(tmp_path,monkeypatch) as (engine,f,c,_):
   await scenario(c,f);before=await counts(f)
   async with f() as db:
    orders=[(p.id,p.items,p.total_amount,p.status) for p in (await db.execute(select(PurchaseOrder))).scalars()]
    settings=[(s.id,s.key,s.value) for s in (await db.execute(select(SystemSetting))).scalars()]
   async with engine.begin() as conn:
    for m in reversed(MODELS):await conn.run_sync(lambda c,m=m:m.__table__.drop(c,checkfirst=True))
    await migrate_procurement_controls(conn);await migrate_procurement_controls(conn);await ensure_procurement_controls(conn)
   assert await counts(f)==before
   async with f() as db:
    assert [(p.id,p.items,p.total_amount,p.status) for p in (await db.execute(select(PurchaseOrder))).scalars()]==orders
    assert [(s.id,s.key,s.value) for s in (await db.execute(select(SystemSetting))).scalars()]==settings
    for m in MODELS:assert (await db.execute(select(func.count()).select_from(m))).scalar_one()==0
   async with engine.begin() as conn:
    await conn.execute(text('ALTER TABLE procurement_duty_executions DROP CONSTRAINT uq_procurement_duty_execution'))
    with pytest.raises(HTTPException) as e:await ensure_procurement_controls(conn)
    assert e.value.status_code==503 and 'uq_procurement_duty_execution' in e.value.detail['missing']
 asyncio.run(run())

def test_new_database_schema_and_savepoint_failure_localized(tmp_path,monkeypatch):
 from tests.test_incoming_operations import environment
 async def run():
  async with environment(tmp_path,monkeypatch) as (engine,f,c):
   async with engine.begin() as conn:
    for m in reversed(MODELS):await conn.run_sync(lambda c,m=m:m.__table__.drop(c,checkfirst=True))
    # The app's ordinary empty base schema exists before startup migrations run.
    await migrate_procurement_controls(conn);await migrate_procurement_controls(conn)
    try:
     async with conn.begin_nested():await conn.execute(text('SELECT 1/0'))
    except Exception:pass
    assert (await conn.execute(text('SELECT 1'))).scalar_one()==1
    await ensure_procurement_controls(conn)
   async with f() as db:
    for m in MODELS:assert (await db.execute(select(func.count()).select_from(m))).scalar_one()==0
 asyncio.run(run())

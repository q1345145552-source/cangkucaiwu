"""真实 PostgreSQL + HTTP：到账并发防重、失败重试、私有附件与旧库升级。

INCOMING_TEST_DATABASE_URL 只能指向本机隔离服务；不读取项目或生产连接。
"""
import asyncio
import json
import os
import sys
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlparse

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

import app.database as database
from app.main import app
from app.models import Warehouse, User, UserWarehouse, Customer, PaymentAccount, IncomingFlow, RechargeDeclaration
from app.services.account_balances import current_account_balances
from scripts.seed import _migrate_incoming_operations
from tests.test_round2_permissions import auth, png

URL = os.environ.get("INCOMING_TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not URL, reason="Requires an explicitly configured isolated PostgreSQL server")
ACTUAL = {}


def actual(name, value):
    ACTUAL[name] = value
    if os.environ.get("INCOMING_TEST_REPORT"):
        Path(os.environ["INCOMING_TEST_REPORT"]).write_text(json.dumps(ACTUAL, ensure_ascii=False, indent=2))


@asynccontextmanager
async def environment(tmp_path, monkeypatch):
    assert urlparse(URL).hostname in ("127.0.0.1", "localhost"), "Only local isolated PostgreSQL is allowed"
    schema = "incoming_test_" + uuid.uuid4().hex
    admin = create_async_engine(URL)
    async with admin.begin() as conn:
        await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(URL, pool_size=30, max_overflow=10,
        connect_args={"server_settings": {"search_path": schema}})
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(database, "async_session_factory", lambda: factory)
    monkeypatch.setenv("INCOMING_ATTACHMENT_DIR", str(tmp_path / "private-incoming"))
    import app.services.account_balances as balances
    monkeypatch.setattr(balances, "thai_today", lambda: date(2026, 10, 20))
    try:
        async with engine.begin() as conn:
            await conn.run_sync(database.Base.metadata.create_all)
        async with factory() as db:
            db.add_all([Warehouse(id=n, name=f"测试仓{n}", code=f"TEST{n}") for n in (1, 2)])
            await db.flush()
            for uid, role, wid in [(1,"warehouse_admin",1),(2,"super_admin",1),(3,"staff",1),
                (4,"supervisor",1),(5,"warehouse_labor",1),(7,"warehouse_admin",2)]:
                db.add(User(id=uid,username=f"test-{uid}",display_name=f"测试账号{uid}",password_hash="unused",
                    role=role,warehouse_id=wid,extra_permissions=["到账流水"]))
            await db.flush()
            db.add_all([UserWarehouse(user_id=uid,warehouse_id=wid) for uid,wid in [(1,1),(2,1),(3,1),(4,1),(5,1),(7,2)]])
            db.add_all([PaymentAccount(id=n,warehouse_id=n,account_name=f"测试现金{n}",account_type="cash",
                account_number="-",opening_balance=0,opening_balance_date=date(2026,10,1),currency="THB") for n in (1,2)])
            db.add(Customer(id=1,warehouse_id=1,customer_code="TEST-CUSTOMER",company_name="测试客户"))
            await db.commit()
        async with AsyncClient(transport=ASGITransport(app=app),base_url="http://isolated-test") as client:
            yield engine, factory, client
    finally:
        await engine.dispose()
        async with admin.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.dispose()


def body(key=None, **values):
    return {"request_key": key or uuid.uuid4().hex,"received_date":"2026-10-20","amount":1000,
        "currency":"THB","account_id":1,"payer_name":"测试客户","payment_method":"银行转账",**values}


async def numbers(factory):
    async with factory() as db:
        account = await db.get(PaymentAccount,1)
        return {"count": (await db.execute(select(func.count(IncomingFlow.id)))).scalar_one(),
            "balance": float((await current_account_balances(db,[account]))[1])}


def test_real_postgres_concurrent_retry_and_independent_same_amount(tmp_path, monkeypatch):
    async def run():
        import app.services.incoming_receipts as service
        async with environment(tmp_path,monkeypatch) as (_,factory,client):
            original, barrier = service.lock_account, asyncio.Barrier(10)
            async def simultaneous(*args, **kwargs):
                await asyncio.wait_for(barrier.wait(),timeout=20)
                return await original(*args,**kwargs)
            monkeypatch.setattr(service,"lock_account",simultaneous)
            payload = body()
            responses = await asyncio.gather(*[client.post("/api/v1/incoming",headers=auth(1),json=payload) for _ in range(10)])
            assert all(r.status_code==200 for r in responses),[(r.status_code,r.text) for r in responses]
            assert len({r.json()["id"] for r in responses})==1
            assert sum(r.json()["created"] for r in responses)==1
            assert await numbers(factory)=={"count":1,"balance":1000}
            monkeypatch.setattr(service,"lock_account",original)
            for _ in range(3):
                response=await client.post("/api/v1/incoming",headers=auth(1),json=payload)
                assert response.status_code==200 and not response.json()["created"]
            once=await numbers(factory)
            other=await client.post("/api/v1/incoming",headers=auth(1),json=body())
            assert other.status_code==200 and other.json()["created"]
            assert await numbers(factory)=={"count":2,"balance":2000}
            actual("same_operation",{"concurrent_requests":10,"sequential_retries":3,"after_same_request":once,
                "after_independent_same_amount":await numbers(factory)})
    asyncio.run(run())


def test_payload_conflict_missing_key_batch_replay_and_atomic_failure(tmp_path,monkeypatch):
    async def run():
        async with environment(tmp_path,monkeypatch) as (_,factory,client):
            missing=body();missing.pop("request_key")
            assert (await client.post("/api/v1/incoming",headers=auth(1),json=missing)).status_code==422
            assert (await client.post("/api/v1/incoming",headers=auth(1),json=body(remark='x'*501))).status_code==422
            assert await numbers(factory)=={"count":0,"balance":0}
            payload=body()
            assert (await client.post("/api/v1/incoming",headers=auth(1),json=payload)).status_code==200
            changed=await client.post("/api/v1/incoming",headers=auth(1),json={**payload,"amount":2000})
            assert changed.status_code==409 and (await numbers(factory))["balance"]==1000
            batch={"request_key":uuid.uuid4().hex,"records":[{k:v for k,v in body().items() if k!='request_key'}]*2}
            for expected in [(2,0),(0,2)]:
                result=await client.post("/api/v1/incoming/batch-import",headers=auth(1),json=batch)
                assert result.status_code==200,result.text
                assert (result.json()["imported"],result.json()["existing"])==expected
            altered={**batch,"records":batch["records"]+[batch["records"][0]]}
            assert (await client.post("/api/v1/incoming/batch-import",headers=auth(1),json=altered)).status_code==409
            failed={"request_key":uuid.uuid4().hex,"records":[batch["records"][0],{**batch["records"][0],"account_id":2}]}
            assert (await client.post("/api/v1/incoming/batch-import",headers=auth(1),json=failed)).status_code==400
            assert await numbers(factory)=={"count":3,"balance":3000}
            actual("batch_and_conflict",{"missing_key":422,"same_key_changed_amount":409,"repeated_batch_new_records":0,
                "changed_batch":409,"failed_batch":400,"final":await numbers(factory)})
    asyncio.run(run())


def test_screenshot_failure_recovery_and_private_warehouse_access(tmp_path,monkeypatch):
    async def run():
        import app.services.image_utils as images
        async with environment(tmp_path,monkeypatch) as (_,factory,client):
            async with factory() as db:
                db.add(RechargeDeclaration(id=1,warehouse_id=1,customer_id=1,declare_date=datetime(2026,10,20),amount=1000,
                    currency="THB",declarer_id=1,screenshot="old-declaration.png"))
                await db.commit()
            payload=body()
            created=await client.post("/api/v1/incoming",headers=auth(1),json=payload)
            assert created.status_code==200,created.text
            rid=created.json()["id"]
            original=images.save_image
            def disk_failure(*args,**kwargs): raise OSError("simulated isolated disk failure")
            monkeypatch.setattr(images,"save_image",disk_failure)
            failed=await client.post(f"/api/v1/incoming/{rid}/screenshot",headers=auth(1),files={"file":("receipt.png",png(),"image/png")})
            assert failed.status_code==500 and "到账已入账" in failed.json()["detail"]
            assert await numbers(factory)=={"count":1,"balance":1000}
            lookup=await client.get(f'/api/v1/incoming/by-request/{payload["request_key"]}',headers=auth(1))
            assert lookup.status_code==200 and lookup.json()["id"]==rid and not lookup.json()["has_screenshot"]
            monkeypatch.setattr(images,"save_image",original)
            good=await client.post(f"/api/v1/incoming/{rid}/screenshot",headers=auth(1),files={"file":("receipt.png",png(),"image/png")})
            assert good.status_code==200,good.text
            image=await client.get(f"/api/v1/incoming/{rid}/screenshot",headers=auth(1))
            assert image.status_code==200 and image.headers['cache-control']=='private, no-store'
            assert image.content==png()
            assert await numbers(factory)=={"count":1,"balance":1000}
            async with factory() as db:
                assert (await db.get(RechargeDeclaration,1)).screenshot=="old-declaration.png"
                private=(await db.get(IncomingFlow,rid)).screenshot
                assert (tmp_path/"private-incoming"/private).is_file()
            assert (await client.get('/uploads/'+private)).status_code==404
            for uid in (2,5,7):
                for method in ('get','post'):
                    kwargs={} if method=='get' else {"files":{"file":("receipt.png",png(),"image/png")}}
                    response=await getattr(client,method)(f"/api/v1/incoming/{rid}/screenshot",headers=auth(uid),**kwargs)
                    assert response.status_code==403,(uid,method,response.text)
            assert (await client.get(f'/api/v1/incoming/by-request/{payload["request_key"]}',headers=auth(7))).status_code==404
            assert (await client.get('/api/v1/incoming',headers=auth(7))).json()['total']==0
            assert (await client.get(f'/api/v1/incoming/{rid}/screenshot')).status_code in (401,403)
            for uid in (3,4):
                assert (await client.get(f'/api/v1/incoming/{rid}/screenshot',headers=auth(uid))).status_code==200
            async with factory() as db:
                for uid in (3,4): (await db.get(User,uid)).extra_permissions=[]
                await db.commit()
            for uid in (3,4):
                assert (await client.get(f'/api/v1/incoming/{rid}/screenshot',headers=auth(uid))).status_code==403
                denied=await client.post(f'/api/v1/incoming/{rid}/screenshot',headers=auth(uid),files={'file':('receipt.png',png(),'image/png')})
                assert denied.status_code==403
                assert (await client.get(f'/api/v1/incoming/by-request/{payload["request_key"]}',headers=auth(uid))).status_code==403
            actual("screenshot",{"failure_status":500,"failure_message":failed.json()["detail"],"recovered_id":rid,
                "upload_success":200,"own_read":200,"foreign_read_write":403,"ungranted_staff_supervisor":403,
                "public_read":404,"after_retry":await numbers(factory)})
    asyncio.run(run())


@pytest.mark.parametrize("legacy",[False,True])
def test_postgres_migration_new_old_repeat_and_savepoint(tmp_path,monkeypatch,legacy):
    async def run():
        async with environment(tmp_path,monkeypatch) as (engine,factory,client):
            if legacy:
                async with engine.begin() as conn:
                    await conn.execute(text("DROP INDEX uq_incoming_operation"))
                    for field in ('request_key','request_fingerprint','screenshot'):
                        await conn.execute(text(f'ALTER TABLE incoming_flows DROP COLUMN {field}'))
                    await conn.execute(text("INSERT INTO incoming_flows(warehouse_id,account_id,received_date,amount,currency,entrant_id,match_status) VALUES(1,1,'2026-09-30',123,'THB',1,'unmatched')"))
                async with engine.begin() as conn:
                    class FailOnce:
                        def begin_nested(self): return conn.begin_nested()
                        async def execute(self,statement):
                            if 'ADD COLUMN IF NOT EXISTS request_fingerprint' in str(statement):
                                return await conn.execute(text('SELECT * FROM intentionally_missing_table'))
                            return await conn.execute(statement)
                    with pytest.raises(Exception): await _migrate_incoming_operations(FailOnce())
                    assert (await conn.execute(text('SELECT 1'))).scalar_one()==1
                    await _migrate_incoming_operations(conn)
            for _ in range(2):
                async with engine.begin() as conn: await _migrate_incoming_operations(conn)
            async with factory() as db:
                columns=(await db.execute(text("SELECT column_name FROM information_schema.columns WHERE table_schema=current_schema() AND table_name='incoming_flows'"))).scalars().all()
                assert {'request_key','request_fingerprint','screenshot'} <= set(columns)
                if legacy:
                    row=(await db.execute(select(IncomingFlow))).scalar_one()
                    assert row.amount==123 and row.request_key is row.request_fingerprint is row.screenshot is None
            response=await client.post('/api/v1/incoming',headers=auth(1),json=body())
            assert response.status_code==200,response.text
            actual('migration_old' if legacy else 'migration_new',{'repeat_runs':2,'fields':3,'legacy_amount_preserved':123 if legacy else None})
    asyncio.run(run())


def test_complete_startup_new_database_legacy_upgrade_and_restart(tmp_path):
    async def run():
        import asyncpg
        assert urlparse(URL).hostname in ('127.0.0.1','localhost')
        admin=await asyncpg.connect(URL.replace('postgresql+asyncpg://','postgresql://'))
        name='receipt_round1_startup_'+uuid.uuid4().hex
        await admin.execute('CREATE DATABASE '+name)
        test_url=URL.rsplit('/',1)[0]+'/'+name
        connection=None
        try:
            backend=Path(__file__).resolve().parents[1]
            env={**os.environ,'PYTHONPATH':str(backend),'DATABASE_URL':test_url,
                'SECRET_KEY':'isolated-round1-startup-test-key-no-production','SEED_ADMIN_PASSWORD':'isolated-round1-seed-password'}
            results={}
            for step in ('new_database','legacy_upgrade','restart'):
                if step=='legacy_upgrade':
                    connection=await asyncpg.connect(test_url.replace('postgresql+asyncpg://','postgresql://'))
                    before=[dict(r) for r in await connection.fetch('SELECT id,warehouse_id,received_date,amount,currency,entrant_id FROM incoming_flows ORDER BY id')]
                    await connection.execute('DROP INDEX uq_incoming_operation')
                    for column in ('request_key','request_fingerprint','screenshot'):
                        await connection.execute('ALTER TABLE incoming_flows DROP COLUMN '+column)
                process=await asyncio.create_subprocess_exec(sys.executable,'scripts/seed.py',cwd=backend,env=env,
                    stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.STDOUT)
                output,_=await process.communicate()
                (tmp_path/f'startup-{step}.txt').write_bytes(output)
                assert process.returncode==0,output.decode(errors='replace')[-4000:]
                results[step]={'exit_code':process.returncode}
                if connection is not None:
                    after=[dict(r) for r in await connection.fetch('SELECT id,warehouse_id,received_date,amount,currency,entrant_id FROM incoming_flows ORDER BY id')]
                    assert before==after
            results['legacy_receipts_preserved']=len(before)
            results['legacy_amount_preserved']=sum(r['amount'] for r in before)
            assert len(before)==1
            assert await connection.fetchval('SELECT count(*) FROM incoming_flows WHERE request_key IS NULL AND request_fingerprint IS NULL AND screenshot IS NULL')==1
            actual('full_startup',results)
        finally:
            if connection: await connection.close()
            await admin.execute('DROP DATABASE '+name)
            await admin.close()
    asyncio.run(run())

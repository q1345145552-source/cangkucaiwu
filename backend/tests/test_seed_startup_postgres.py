"""Run Compose's seed && server chain against disposable loopback databases.

SEED_STARTUP_TEST_DATABASE_URL must name a dedicated seed_startup_test_* control
database. Each case creates and drops its own database; production is never used.
"""
import asyncio
from datetime import date, datetime
import json
import os
from pathlib import Path
import shlex
import signal
import socket
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import Request, urlopen
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.database import Base
from app.models import Warehouse, User, Employee, ClockInRecord, PaymentAccount
from app.models.payroll import PayrollRecord
from app.core.security import hash_password

CONTROL = os.environ.get("SEED_STARTUP_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not CONTROL, reason="Explicit disposable startup database required")
BACKEND = Path(__file__).resolve().parents[1]
TABLES = ("warehouses", "users", "employees", "clock_in_records", "payroll_records",
          "payment_accounts", "incoming_flows", "expense_records", "employee_advances", "payable_bills")
PASSWORD = "Synthetic-Startup-Only-20261030"


async def database_command(name, create):
    control = make_url(CONTROL)
    assert control.host == "127.0.0.1" and control.port not in (None, 5432, 5434)
    assert control.database.startswith("seed_startup_test_")
    assert name.startswith("seed_startup_test_") and name.replace("_", "").isalnum()
    engine = create_async_engine(control, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as conn:
            await conn.execute(text(f'CREATE DATABASE "{name}"' if create else f'DROP DATABASE "{name}"'))
    finally:
        await engine.dispose()


async def prepare_legacy(url):
    engine = create_async_engine(url)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            session.add(Warehouse(id=1, name="隔离启动测试仓", code="STARTUP"))
            await session.flush()
            session.add_all([
                User(id=1, username="startup-admin", display_name="合成管理员", role="warehouse_admin",
                     warehouse_id=1, password_hash=hash_password(PASSWORD), is_active=True),
                User(id=2, username="startup-labor", display_name="合成员工", role="warehouse_labor",
                     warehouse_id=1, password_hash="synthetic-not-a-login", is_active=True),
            ])
            await session.flush()
            session.add(Employee(id=41, user_id=2, warehouse_id=1, name="合成员工", status="regular"))
            await session.flush()
            session.add(ClockInRecord(id=51, user_id=2, warehouse_id=1, clock_date=date(2026, 10, 4),
                                     session=1, clocked_in_at=datetime(2026, 10, 4, 8, 41, 54), status="normal"))
            session.add(PayrollRecord(id=101, employee_id=41, warehouse_id=1, period="2026-10",
                                     settle_start_date=date(2026, 10, 1), settle_end_date=date(2026, 10, 15),
                                     status="confirmed", gross_pay=6046, net_pay=6046, detail='{"sentinel":"keep"}'))
            session.add(PaymentAccount(id=1, warehouse_id=1, account_name="合成现金", account_type="cash",
                                       account_number="synthetic-cash", currency="THB", opening_balance=10000,
                                       opening_balance_date=date(2026, 10, 1)))
            await session.commit()
    finally:
        await engine.dispose()


async def snapshot(url):
    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            return {table: (await conn.execute(text(
                f"SELECT to_jsonb(t) - 'photo_fingerprint' FROM {table} t ORDER BY id"
            ))).scalars().all() for table in TABLES}
    finally:
        await engine.dispose()


async def verify_clock_schema(url):
    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            column = (await conn.execute(text("SELECT data_type, character_maximum_length FROM information_schema.columns "
                "WHERE table_schema=current_schema() AND table_name='clock_in_records' AND column_name='photo_fingerprint'"))).one()
            assert tuple(column) == ("character varying", 64)
            definition = (await conn.execute(text("SELECT indexdef FROM pg_indexes WHERE schemaname=current_schema() "
                "AND tablename='clock_in_records' AND indexname='uq_clock_photo_warehouse_fingerprint'"))).scalar_one()
            assert "UNIQUE INDEX" in definition and "photo_fingerprint IS NOT NULL" in definition
            return definition
    finally:
        await engine.dispose()


def start_and_verify(url, folder, iteration, username):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = {**os.environ, "DATABASE_URL": url, "SECRET_KEY": "isolated-startup-verification-only-20261030",
           "SEED_ADMIN_PASSWORD": PASSWORD, "PYTHONUNBUFFERED": "1", "PYTHONPATH": str(BACKEND),
           "TRUSTED_PROXY_HOSTS": "127.0.0.1", "FORWARDED_ALLOW_IPS": "",
           "UPLOAD_DIR": str(folder / "uploads"), "INCOMING_ATTACHMENT_DIR": str(folder / "incoming")}
    python = shlex.quote(sys.executable)
    command = f"{python} scripts/seed.py && exec {python} scripts/start_server.py --host 127.0.0.1 --port {port}"
    log_path = folder / f"startup-{iteration}.log"
    with log_path.open("w") as log:
        process = subprocess.Popen(["sh", "-c", command], cwd=BACKEND, env=env,
                                   stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            deadline = time.monotonic() + 60
            while True:
                assert process.poll() is None, log_path.read_text()
                try:
                    with urlopen(f"http://127.0.0.1:{port}/health", timeout=1) as response:
                        assert response.status == 200 and json.load(response) == {"status": "ok"}
                    break
                except (URLError, TimeoutError):
                    assert time.monotonic() < deadline, log_path.read_text()
                    time.sleep(0.1)
            payload = json.dumps({"username": username, "password": PASSWORD}).encode()
            request = Request(f"http://127.0.0.1:{port}/api/v1/auth/login", data=payload,
                              headers={"Content-Type": "application/json"})
            with urlopen(request, timeout=10) as response:
                identity = json.load(response)
                assert response.status == 200 and identity["access_token"] and identity["username"] == username
            output = log_path.read_text()
            assert "代理头已启用" in output
            assert "Traceback" not in output and "失败" not in output and "UnboundLocalError" not in output, output
            return {"iteration": iteration, "health": 200, "login": 200, "startup_log": str(log_path)}
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=5)


@pytest.mark.parametrize("legacy", [False, True], ids=["empty-database", "existing-data"])
def test_real_seed_then_server_twice_preserves_business_data(tmp_path, legacy):
    name = "seed_startup_test_" + uuid.uuid4().hex
    url = make_url(CONTROL).set(database=name).render_as_string(hide_password=False)
    report_root = Path(os.environ.get("SEED_STARTUP_TEST_REPORT_DIR", str(tmp_path)))
    folder = report_root / ("existing-data" if legacy else "empty-database")
    folder.mkdir(parents=True, exist_ok=True)
    asyncio.run(database_command(name, True))
    try:
        before = None
        if legacy:
            asyncio.run(prepare_legacy(url))
            before = asyncio.run(snapshot(url))
        first = start_and_verify(url, folder, 1, "startup-admin" if legacy else "admin")
        after = asyncio.run(snapshot(url))
        if before is not None:
            assert after == before, "Startup must preserve the existing synthetic business rows"
            assert after["payroll_records"][0]["net_pay"] == 6046
        assert after["warehouses"] and after["users"]
        definition = asyncio.run(verify_clock_schema(url))
        second = start_and_verify(url, folder, 2, "startup-admin" if legacy else "admin")
        assert asyncio.run(snapshot(url)) == after, "Repeated startup must preserve business data"
        assert asyncio.run(verify_clock_schema(url)) == definition
        result = {"synthetic_only": True, "existing_data_case": legacy, "runs": [first, second],
                  "row_counts": {table: len(rows) for table, rows in after.items()},
                  "existing_rows_unchanged": before is not None, "repeat_unchanged": True,
                  "fingerprint_index": definition}
        (folder / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
        print(json.dumps(result, ensure_ascii=False))
    finally:
        asyncio.run(database_command(name, False))

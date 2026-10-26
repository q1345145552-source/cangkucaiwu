"""Native PostgreSQL + actual HTTP application, synthetic identities only.

Started and stopped by run-legacy-regressions.py; no startup migrations or seed run.
"""
import asyncio
from contextlib import contextmanager
import signal
import json
import os
from datetime import date, datetime
from pathlib import Path
import sys
from urllib.parse import urlparse
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))
import uvicorn
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
import app.database as database
from app.main import app
from app.models import Warehouse, User, UserWarehouse, Employee, ClockInRecord
from app.models.payroll import PayrollRecord
from app.core.security import hash_password
from app.core.menu_registry import MENU_PERMISSIONS


async def main():
    url = os.environ['LEGACY12_DATABASE_URL']
    parsed = urlparse(url)
    assert parsed.hostname == '127.0.0.1' and parsed.port, 'Explicit isolated loopback database required'
    port = int(os.environ['LEGACY12_HTTP_PORT'])
    assert port not in (18080, 18082), 'Never reuse another task or user service'
    schema = 'legacy12_' + uuid.uuid4().hex
    admin = create_async_engine(url)
    async with admin.begin() as conn:
        await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(url, connect_args={'server_settings': {'search_path': schema}})
    factory = async_sessionmaker(engine, expire_on_commit=False)
    original = database.async_session_factory
    database.async_session_factory = lambda: factory
    try:
        async with engine.begin() as conn:
            await conn.run_sync(database.Base.metadata.create_all)
        all_permissions = [p.label for p in MENU_PERMISSIONS if p.selectable]
        specs = [(1, 'warehouse_admin', 'warehouse_admin', 1, True),
                 (2, 'super_admin', 'super_admin', 1, True),
                 (3, 'staff_all', 'staff', 1, True),
                 (4, 'supervisor_all', 'supervisor', 1, True),
                 (5, 'labor1', 'warehouse_labor', 1, False),
                 (6, 'labor2', 'warehouse_labor', 2, False),
                 (7, 'foreign_admin', 'warehouse_admin', 2, True),
                 (8, 'supervisor_none', 'supervisor', 1, False),
                 (9, 'staff_none', 'staff', 1, False),
                 (10, 'other_labor', 'warehouse_labor', 1, False),
                 (11, 'supervisor_attendance', 'supervisor', 1, False),
                 (12, 'staff_attendance', 'staff', 1, False)]
        password = hash_password('test-password')
        async with factory() as db:
            db.add_all([Warehouse(id=n, name=f'隔离测试仓{n}', code=f'LEGACY{n}') for n in (1, 2)])
            await db.flush()
            for uid, name, role, wid, granted in specs:
                db.add(User(id=uid, username=name, display_name=name, role=role, warehouse_id=wid,
                            password_hash=password, extra_permissions=all_permissions if granted else [next(p.label for p in MENU_PERMISSIONS if p.menu_key == 'attendance')] if uid in (11, 12) else [],
                            attendance_enabled=uid == 4))
            await db.flush()
            db.add_all([UserWarehouse(user_id=uid, warehouse_id=wid) for uid, _, _, wid, _ in specs])
            # Deliberately unrelated employee/user numbers: identity assertions must use the binding.
            for eid, uid, wid in [(41, 4, 1), (51, 5, 1), (52, 6, 2), (61, 10, 1)]:
                db.add(Employee(id=eid, user_id=uid, warehouse_id=wid, name=f'合成员工{eid}',
                                status='regular', position='仓库主管' if uid == 4 else '仓库劳工',
                                hire_date=datetime(2026, 10, 1)))
            await db.flush()
            supervisor = await db.get(User, 4)
            supervisor.attendance_employee_id = 41
            for rid, eid, uid, wid, amount in [(101, 41, 4, 1, 800), (102, 51, 5, 1, 800),
                                               (103, 61, 10, 1, 900), (104, 52, 6, 2, 700)]:
                db.add(PayrollRecord(id=rid, employee_id=eid, warehouse_id=wid, period='2026-10',
                                    settle_start_date=date(2026, 10, 1), settle_end_date=date(2026, 10, 15),
                                    status='confirmed', net_pay=amount, base_pay=amount, gross_pay=amount,
                                    attendance_days=2, detail='{}'))
                db.add(ClockInRecord(user_id=uid, warehouse_id=wid, clock_date=date(2026, 10, 10),
                                    session=1, clocked_in_at=datetime(2026, 10, 10, 9), status='normal'))
            await db.commit()
        metadata = {'schema': schema, 'base_url': f'http://127.0.0.1:{port}/api/v1',
                    'supervisor_employee_id': 41, 'labor_employee_id': 51,
                    'own_payroll': {'supervisor_all': 101, 'labor1': 102, 'other_labor': 103, 'labor2': 104},
                    'warehouse_payroll': {'1': [101, 102, 103], '2': [104]}}
        Path(os.environ['LEGACY12_FIXTURE_FILE']).write_text(json.dumps(metadata))
        print(json.dumps({'fixture_ready': metadata}), flush=True)
        class LocalServer(uvicorn.Server):
            @contextmanager
            def capture_signals(self):
                # Let the event loop stop the server, then finish schema cleanup before exit.
                yield
        server = LocalServer(uvicorn.Config(app, host='127.0.0.1', port=port,
                                           lifespan='off', log_level='warning'))
        asyncio.get_running_loop().add_signal_handler(signal.SIGINT, lambda: setattr(server, 'should_exit', True))
        await server.serve()
    finally:
        database.async_session_factory = original
        await engine.dispose()
        async with admin.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.dispose()
        print(json.dumps({'schema_removed': schema}), flush=True)


if __name__ == '__main__':
    asyncio.run(main())

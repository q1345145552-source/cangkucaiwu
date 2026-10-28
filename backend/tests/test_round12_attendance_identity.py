"""第十二轮：账号身份开关持久化、解除绑定、权限边界及启动保存点。"""
import asyncio
import ast
from datetime import datetime, timezone
from pathlib import Path
from contextlib import asynccontextmanager

import pytest
from sqlalchemy import select, func, inspect
from app.models import User, Employee
from app.schemas.user import UserResponse
from app.core.menu_registry import MENU_PERMISSIONS
from tests.test_round2_permissions import auth
from tests.test_round3_permissions import hr_environment, snapshot
from scripts.seed import _migrate_user_attendance_columns

FIELDS = ('attendance_enabled', 'attendance_employee_id', 'attendance_enabled_at')
ROOT = Path(__file__).resolve().parents[2]


def state(user):
    return {name: getattr(user, name) for name in FIELDS}


@pytest.mark.parametrize('uid', [3, 4], ids=['staff', 'supervisor'])
def test_toggle_roundtrip_and_auto_employee(tmp_path, monkeypatch, uid):
    async def run():
        async with hr_environment(tmp_path, monkeypatch) as (engine, factory, client):
            async with engine.connect() as conn:
                names = await conn.run_sync(lambda sync: {c['name'] for c in inspect(sync).get_columns('users')})
                assert set(FIELDS) <= names
            async with factory() as db:
                assert all(state(u) == dict(zip(FIELDS, (False, None, None))) for u in (await db.execute(select(User))).scalars())
                employees_before = (await db.execute(select(func.count(Employee.id)))).scalar()
            before = await snapshot(factory)
            async def read():
                response = await client.get('/api/v1/users', headers=auth(1))
                assert response.status_code == 200, response.text
                return next(u for u in response.json()['data'] if u['id'] == uid)
            assert not (await read())['attendance_enabled']
            r = await client.put(f'/api/v1/users/{uid}', headers=auth(1), json={'attendance_enabled': True})
            assert r.status_code == 200, r.text
            enabled = await read()
            assert enabled['attendance_enabled'] is True
            assert isinstance(enabled['attendance_employee_id'], int)
            assert datetime.fromisoformat(enabled['attendance_enabled_at']).date() == datetime.now(timezone.utc).date()
            r = await client.put(f'/api/v1/users/{uid}', headers=auth(1), json={'attendance_enabled': True})
            assert r.status_code == 200
            assert (await read())['attendance_enabled_at'] == enabled['attendance_enabled_at']
            # Other account edits must preserve the identity fields; explicit null is a no-op.
            r = await client.put(f'/api/v1/users/{uid}', headers=auth(1), json={'display_name': '身份测试', 'extra_permissions': ['工资'], 'attendance_enabled': None})
            assert r.status_code == 200, r.text
            assert (await read())['attendance_enabled_at'] == enabled['attendance_enabled_at']
            async with factory() as db:
                user = await db.get(User, uid)
                assert UserResponse.model_validate(user).attendance_enabled
                assert (await db.execute(select(func.count(Employee.id)))).scalar() == employees_before + 1
            r = await client.put(f'/api/v1/users/{uid}', headers=auth(1), json={'attendance_enabled': False})
            assert r.status_code == 200
            disabled = await read()
            assert {k: disabled[k] for k in FIELDS} == dict(zip(FIELDS, (False, None, None)))
            assert await snapshot(factory) == before
            print('\n实际账号开关值：', {k: enabled[k] for k in ('id', *FIELDS)}, {k: disabled[k] for k in ('id', *FIELDS)})
    asyncio.run(run())


@pytest.mark.parametrize('binding_matches', [True, False])
def test_disable_detaches_only_matching_profile_and_preserves_records(tmp_path, monkeypatch, binding_matches):
    async def run():
        async with hr_environment(tmp_path, monkeypatch) as (_, factory, client):
            async with factory() as db:
                # Seed an existing archive, never create one through the switch endpoint.
                employee = Employee(id=10, warehouse_id=1, name='已有主管档案', user_id=4 if binding_matches else None,
                                    phone='123', status='regular', daily_wage=400, salary_template_id=1, deduction_template_id=1)
                db.add(employee)
                await db.flush()
                user = await db.get(User, 4)
                user.attendance_enabled = True
                user.attendance_employee_id = 10
                user.attendance_enabled_at = datetime(2026, 10, 1, tzinfo=timezone.utc)
                await db.commit()
                original = {c.name: getattr(employee, c.name) for c in Employee.__table__.columns}
                count = (await db.execute(select(func.count(Employee.id)))).scalar()
            before = await snapshot(factory)
            for _ in range(2):
                r = await client.put('/api/v1/users/4', headers=auth(1), json={'attendance_enabled': False})
                assert r.status_code == 200, r.text
            async with factory() as db:
                employee = await db.get(Employee, 10)
                assert employee is not None
                for key, value in original.items():
                    assert getattr(employee, key) == (None if key == 'user_id' and binding_matches else value)
                assert (await db.execute(select(func.count(Employee.id)))).scalar() == count
                assert state(await db.get(User, 4)) == dict(zip(FIELDS, (False, None, None)))
                assert (await db.get(Employee, 1)).user_id == 5
            assert await snapshot(factory) == before
    asyncio.run(run())


@pytest.mark.parametrize('actor,target', [(1, 1), (2, 2), (2, 1), (1, 5)])
def test_inapplicable_roles_ignore_switch(tmp_path, monkeypatch, actor, target):
    async def run():
        async with hr_environment(tmp_path, monkeypatch) as (_, factory, client):
            for enabled in (True, False):
                r = await client.put(f'/api/v1/users/{target}', headers=auth(actor), json={'attendance_enabled': enabled})
                assert r.status_code == 200, r.text
            async with factory() as db:
                assert state(await db.get(User, target)) == dict(zip(FIELDS, (False, None, None)))
            # No broad self-edit permission was added.
            if actor == target:
                r = await client.put(f'/api/v1/users/{target}', headers=auth(actor), json={'attendance_enabled': True, 'role': 'super_admin'})
                assert r.status_code == 403, r.text
    asyncio.run(run())


@pytest.mark.parametrize('actor,target', [(3, 4), (4, 3), (5, 5), (1, 6)])
def test_original_role_and_warehouse_edit_guards(tmp_path, monkeypatch, actor, target):
    async def run():
        async with hr_environment(tmp_path, monkeypatch) as (_, factory, client):
            r = await client.put(f'/api/v1/users/{target}', headers=auth(actor), json={'attendance_enabled': True})
            assert r.status_code == 403, r.text
            async with factory() as db:
                assert not (await db.get(User, target)).attendance_enabled
    asyncio.run(run())


def test_link_and_timestamp_are_server_owned(tmp_path, monkeypatch):
    async def run():
        async with hr_environment(tmp_path, monkeypatch) as (_, factory, client):
            r = await client.put('/api/v1/users/4', headers=auth(1), json={
                'attendance_enabled': True, 'attendance_employee_id': 2,
                'attendance_enabled_at': '2000-01-01T00:00:00Z',
            })
            assert r.status_code == 422, r.text  # Explicit schema rejects client-owned identity fields.
            r = await client.put('/api/v1/users/4', headers=auth(1), json={'attendance_enabled': True})
            assert r.status_code == 200, r.text
            async with factory() as db:
                user = await db.get(User, 4)
                assert user.attendance_employee_id == r.json()["attendance_employee_id"] != 2
                assert (await db.get(Employee, user.attendance_employee_id)).user_id == user.id
                assert user.attendance_enabled_at.year != 2000
            r = await client.get('/api/v1/users/permissions', headers=auth(1))
            flag = next(item for item in r.json() if item['menu_key'] == 'attendance_enabled')
            assert flag['label'] == '纳入考勤' and flag['selectable'] is False and flag['path'] == ''
            assert len([p for p in MENU_PERMISSIONS if p.selectable]) == 34
    asyncio.run(run())


@pytest.mark.parametrize('fail_column', [None, *FIELDS])
def test_startup_ddl_savepoint_isolation(fail_column):
    class Connection:
        def __init__(self): self.committed, self.pending, self.sql, self.rolled_back = [], [], [], []
        @asynccontextmanager
        async def begin_nested(self):
            self.pending = []
            try:
                yield
            except Exception:
                self.rolled_back += self.pending
                raise
            else:
                self.committed += self.pending
        async def execute(self, statement):
            sql = str(statement)
            self.sql.append(sql)
            self.pending.append(sql)
            if fail_column and f' {fail_column} ' in sql:
                raise RuntimeError('模拟单列迁移失败')
    async def run():
        conn = Connection()
        await _migrate_user_attendance_columns(conn)
        assert len(conn.sql) == 3
        assert len(conn.committed) == (2 if fail_column else 3)
        assert len(conn.rolled_back) == (1 if fail_column else 0)
        assert all(s.startswith('ALTER TABLE users ADD COLUMN IF NOT EXISTS ') for s in conn.sql)
        assert not any(s.startswith(('UPDATE ', 'DELETE ')) for s in conn.sql)
    asyncio.run(run())


def test_startup_wires_migration_and_business_sources_unchanged():
    import subprocess
    source = (ROOT / 'backend/scripts/seed.py').read_text()
    seed = next(n for n in ast.parse(source).body if isinstance(n, ast.AsyncFunctionDef) and n.name == 'seed')
    calls = [ast.unparse(n.func) for n in ast.walk(seed) if isinstance(n, ast.Call)]
    assert '_migrate_user_attendance_columns' in calls
    unchanged = ['backend/app/api/v1/employees.py', 'backend/app/models/employee.py',
                 'backend/app/api/v1/payroll.py', 'backend/app/api/v1/attendance.py',
                 'frontend/src/components/layout/DashboardLayout.tsx']
    for filename in unchanged:
        old = subprocess.check_output(['git', 'show', 'cb3d709:' + filename], cwd=ROOT)
        assert subprocess.check_output(['git', 'show', 'deada28:' + filename], cwd=ROOT) == old, filename

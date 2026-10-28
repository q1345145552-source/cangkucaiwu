"""Employee limit repair: move static routes only, keep business functions unchanged."""
import ast
import asyncio
import json
import re
import subprocess
from pathlib import Path

from sqlalchemy import select
from app.main import app
from app.models import Warehouse
from tests.test_round2_permissions import auth, set_perms
from tests.test_round3_permissions import hr_environment, snapshot


def test_limit_route_role_ceiling_and_payroll_unchanged(tmp_path, monkeypatch):
    # Source equality predates action authorization; assert its intended data invariant.
    async def run():
        async with hr_environment(tmp_path, monkeypatch) as (_, f, c):
            before = await snapshot(f)
            for uid in (3, 4):
                await set_perms(f, uid, ['员工档案', '系统设置', '工资'])
                denied = await c.put('/api/v1/employees/max-limit?max_employees=999', headers=auth(uid))
                assert denied.status_code == 403, denied.text
            accepted = await c.put('/api/v1/employees/max-limit?max_employees=73', headers=auth(1))
            assert accepted.status_code == 200, accepted.text
            read = await c.get('/api/v1/employees/max-limit', headers=auth(1))
            assert read.status_code == 200 and read.json()['max_employees'] == 73
            assert await snapshot(f) == before
    asyncio.run(run())


def test_save_read_persistence_and_other_warehouse_unchanged(tmp_path, monkeypatch):
    async def run():
        async with hr_environment(tmp_path, monkeypatch) as (_, factory, client):
            old_payroll = await snapshot(factory)
            async with factory() as db:
                other_before = (await db.get(Warehouse, 2)).max_employees
            r = await client.put('/api/v1/employees/max-limit?max_employees=73', headers=auth(1), json={})
            assert r.status_code == 200, r.text
            assert r.json() == {'message': '人数上限已设为 73', 'max_employees': 73}
            read = await client.get('/api/v1/employees/max-limit', headers=auth(1))
            assert read.status_code == 200 and read.json() == {'max_employees': 73, 'current_count': 1}
            async with factory() as db:
                assert (await db.get(Warehouse, 1)).max_employees == 73
                assert (await db.get(Warehouse, 2)).max_employees == other_before
            assert await snapshot(factory) == old_payroll
            print('EMPLOYEE_LIMIT_PROOF', json.dumps({'write': r.json(), 'read': read.json()}, ensure_ascii=False))
    asyncio.run(run())


def test_employee_crud_and_summary(tmp_path, monkeypatch):
    async def run():
        async with hr_environment(tmp_path, monkeypatch) as (_, factory, c):
            created = await c.post('/api/v1/employees', headers=auth(1), json={'name': '人数上限回归员工', 'employee_no': 'LIMIT-REGRESSION', 'password': 'test-password', 'salary_template_id': 1, 'deduction_template_id': 1, 'hire_date': '2026-10-01'})
            assert created.status_code == 200, created.text
            eid = created.json()['id']
            r = await c.put(f'/api/v1/employees/{eid}', headers=auth(1), json={'name': '已编辑人数上限回归员工'})
            assert r.status_code == 200, r.text
            r = await c.get('/api/v1/employees', headers=auth(1))
            assert r.status_code == 200 and any(e['id'] == eid and e['name'] == '已编辑人数上限回归员工' for e in r.json()['data'])
            r = await c.get(f'/api/v1/employees/{eid}/summary', headers=auth(1))
            assert r.status_code == 200 and r.json()['employee_id'] == eid, r.text
            r = await c.post(f'/api/v1/employees/{eid}/resign', headers=auth(1), json={'reason': 'voluntary', 'resignation_date': '2026-10-15'})
            assert r.status_code == 200, r.text
            r = await c.delete(f'/api/v1/employees/{eid}', headers=auth(1))
            assert r.status_code == 200, r.text
            # Numeric edit still resolves to the employee handler; unknown ID stays 404.
            r = await c.put('/api/v1/employees/999999', headers=auth(1), json={'name': '不存在'})
            assert r.status_code == 404, r.text
    asyncio.run(run())


def test_permission_and_warehouse_checks_preserved(tmp_path, monkeypatch):
    async def run():
        async with hr_environment(tmp_path, monkeypatch) as (_, factory, c):
            for uid in (3, 4):
                await set_perms(factory, uid, [])
                for method in ('get', 'put'):
                    r = await c.request(method, '/api/v1/employees/max-limit?max_employees=61', headers=auth(uid))
                    assert r.status_code == 403 and ('无此操作权限' if method == 'get' else '规则及薪资扣款设置只能由仓库管理员修改') in r.json()['detail']
                await set_perms(factory, uid, ['员工档案'])
                r = await c.put('/api/v1/employees/max-limit?max_employees=61', headers=auth(uid))
                assert r.status_code == 403, r.text
            for method in ('get', 'put'):
                r = await c.request(method, '/api/v1/employees/max-limit?max_employees=61', headers=auth(5))
                assert r.status_code == 403
            r = await c.put('/api/v1/employees/max-limit?max_employees=62', headers={**auth(1), 'X-Warehouse-ID': '2'})
            assert r.status_code == 403
            legitimate = await c.put('/api/v1/employees/max-limit?max_employees=62', headers=auth(1))
            assert legitimate.status_code == 200, legitimate.text
            async with factory() as db:
                assert (await db.get(Warehouse, 1)).max_employees == 62
                assert (await db.get(Warehouse, 2)).max_employees != 62
    asyncio.run(run())


def test_registered_routes_no_static_word_shadowing():
    routes = [r for r in app.routes if hasattr(r, 'methods') and hasattr(r, 'path_regex')]
    collisions = []
    for i, route in enumerate(routes):
        sample = re.sub(r'\{[^}]+\}', '123', route.path)
        for earlier in routes[:i]:
            if '{' not in earlier.path or not (set(route.methods) & set(earlier.methods)):
                continue
            if not any(a.startswith('{') and b and not b.startswith('{') for a, b in zip(earlier.path.split('/'), route.path.split('/'))):
                continue
            if earlier.path_regex.fullmatch(sample):
                collisions.append((route.path, earlier.path))
    assert not collisions, collisions

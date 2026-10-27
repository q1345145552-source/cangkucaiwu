"""工资管理端拒绝劳工，本人专用接口与原管理角色保持原样；仅用隔离库。

统一守卫（e4a2bb7）把工资管理入口的拒绝文案改为「无权访问」，本文件按该已批准实现断言。
金额口径不在本文件用源码快照证明，改由 tests/test_dashboard_procurement_payments.py 的
test_money_basis_numbers_on_real_postgres 在真实 PostgreSQL 上以具体数字验证收入、支出、
余额、逐笔付款与防重。
"""
import asyncio
import json
import os
import re
from pathlib import Path

import pytest
from fastapi.routing import APIRoute
from sqlalchemy import select

from app.main import app
from app.models import User
from app.models.payroll import PayrollRecord
from app.core.security import hash_password
from app.core.permissions import require_non_labor
from app.api.v1 import payroll
from tests.test_round2_permissions import auth, set_perms
from tests.test_round4_permissions import attendance_environment
from tests.test_round15_employee_self import enable, SELF_READS
from tests.test_cash_advance_references import snapshot


MANAGEMENT_ROUTES = [r for r in app.routes if isinstance(r, APIRoute)
    and r.endpoint.__module__ == payroll.__name__ and r.endpoint is not payroll.my_payslip]


@pytest.mark.parametrize('route', MANAGEMENT_ROUTES, ids=lambda r: f'{next(iter(r.methods))} {r.path}')
def test_every_management_route_denies_labor_before_validation_or_business(tmp_path, monkeypatch, route):
    async def run():
        async with attendance_environment(tmp_path, monkeypatch) as (_, factory, client):
            before = await snapshot(factory)
            for uid in (5, 6):
                # Neither an unrelated warehouse nor "self" mode grants management access.
                for record_id in ('1', '10', '999999', 'not-an-id'):
                    path = re.sub(r'\{[^}]+\}', record_id, route.path)
                    response = await client.request(next(iter(route.methods)), path,
                        headers={**auth(uid), 'X-Warehouse-ID': '2'},
                        params={'view':'self', 'employee_id':2, 'user_id':6}, json={})
                    assert response.status_code == 403, response.text
                    assert response.json() == {'detail':'无权访问'}
            assert await snapshot(factory) == before
    asyncio.run(run())


def test_real_logins_self_only_four_employee_pages_and_management_roles(tmp_path, monkeypatch):
    async def run():
        async with attendance_environment(tmp_path, monkeypatch) as (_, factory, c):
            await enable(factory)
            for uid in (3, 4):
                await set_perms(factory, uid, ['工资'])
            async with factory() as db:
                for uid in range(1, 8):
                    user = await db.get(User, uid)
                    user.password_hash = hash_password('test-password')
                db.add(PayrollRecord(id=99, employee_id=4, warehouse_id=1, period='2026-10',
                    net_pay=55555, status='confirmed'))
                await db.commit()
            tokens = {}
            for uid, name in [(1,'warehouse_admin'), (2,'super_admin'), (3,'staff'),
                              (4,'supervisor'), (5,'labor1'), (6,'labor2')]:
                login = await c.post('/api/v1/auth/login', json={'username':name,'password':'test-password'})
                assert login.status_code == 200, login.text
                tokens[uid] = {'Authorization':'Bearer '+login.json()['access_token']}
            before = await snapshot(factory)
            denied = await c.get('/api/v1/payroll', headers=tokens[5])
            assert denied.status_code == 403 and denied.json() == {'detail':'无权访问'}
            spoof = await c.get('/api/v1/payroll/my-payslip?employee_id=4&user_id=7', headers=tokens[5])
            assert spoof.status_code == 403, spoof.text  # R04: reject spoofed identity, do not silently ignore.
            own = await c.get('/api/v1/payroll/my-payslip', headers=tokens[5])
            assert own.status_code == 200, own.text
            assert {x['id'] for x in own.json()['data']} == {1, 2, 3}
            other = await c.get('/api/v1/payroll/my-payslip', headers=tokens[6])
            assert other.status_code == 200 and [x['id'] for x in other.json()['data']] == [10]
            sup = await c.get('/api/v1/payroll/my-payslip', headers=tokens[4])
            assert sup.status_code == 200 and [x['id'] for x in sup.json()['data']] == [20]
            roles = []
            # 本轮 ManagementRouter 默认挂 require_business_user：超级管理员不再进业务页面，
            # 第三轮仅管理员/财务可见本仓管理工资；主管只保留本人入口。
            for uid in (1, 3):
                response = await c.get('/api/v1/payroll', headers=tokens[uid])
                assert response.status_code == 200, response.text
                assert {x['id'] for x in response.json()['data']} == {1, 2, 3, 20, 99}
                roles.append({'role':(await c.get('/api/v1/auth/me', headers=tokens[uid])).json()['role'],
                    'status':response.status_code, 'record_ids':[x['id'] for x in response.json()['data']]})
            supervisor = await c.get('/api/v1/payroll', headers=tokens[4])
            assert supervisor.status_code == 403 and supervisor.json() == {'detail':'无权查看工资数据'}
            super_admin = await c.get('/api/v1/payroll', headers=tokens[2])
            assert super_admin.status_code == 403
            assert super_admin.json() == {'detail':'超级管理员请使用各仓库管理员账号操作'}
            self_results = []
            for path in SELF_READS:
                response = await c.get('/api/v1'+path, headers=tokens[5])
                assert response.status_code == 200, (path, response.text)
                self_results.append({'method':'GET', 'path':path, 'status':response.status_code})
            calendar_response = await c.get('/api/v1/attendance/calendar?start_date=2026-10-01&end_date=2026-10-31', headers=tokens[5])
            calendar = calendar_response.json()
            assert [x['id'] for x in calendar['employees']] == [1]
            assert {x['employee_id'] for x in calendar['events']} == {1}
            # No salary/template/amount fields or other employees in the labor calendar response.
            def keys(value):
                if isinstance(value, dict):
                    return set(value) | set().union(*(keys(v) for v in value.values()))
                if isinstance(value, list):
                    return set().union(*(keys(v) for v in value))
                return set()
            assert not {'net_pay','base_pay','salary','salary_template_id','amount','hourly_rate'} & keys(calendar)
            assert await snapshot(factory) == before
            # Write requests are actual self-service routes, not management impersonation.
            clock = await c.post('/api/v1/clock-in', headers=tokens[5], data={'session':'1'})
            assert clock.status_code == 200, clock.text
            leave = await c.post('/api/v1/attendance/leaves', headers=tokens[5],
                data={'leave_date':'2026-10-17','duration_type':'hours','hours':'2','leave_type':'personal'})
            assert leave.status_code == 200, leave.text
            confirm = await c.post('/api/v1/overtime/1/confirm', headers=tokens[5])
            assert confirm.status_code == 200, confirm.text
            report = {'environment':'isolated SQLite; real HTTP and real login tokens; not production',
                'labor_management':{'status':denied.status_code,'body':denied.json()},
                'labor_own_payslip':{'status':own.status_code,'body':own.json()},
                'other_warehouse_own_ids':[x['id'] for x in other.json()['data']],
                'attendance_supervisor_own_ids':[x['id'] for x in sup.json()['data']],
                'management_roles':roles,'employee_reads':self_results,
                'employee_writes':{'clock':clock.json(),'leave':leave.json(),'overtime_confirm':confirm.json()},
                'labor_calendar_employee_ids':[x['id'] for x in calendar['employees']],
                'labor_calendar_salary_fields':[], 'all_tables_unchanged_after_reads':True,
                'management_routes':[{'method':next(iter(r.methods)), 'path':r.path,'labor_status':403,
                    'detail':'无权访问'} for r in MANAGEMENT_ROUTES]}
            if os.environ.get('PAYROLL_BOUNDARY_REPORT'):
                Path(os.environ['PAYROLL_BOUNDARY_REPORT']).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
            for uid in (3, 4):
                await set_perms(factory, uid, [])
                response = await c.get('/api/v1/payroll', headers=tokens[uid])
                assert response.status_code == 403 and ('无此操作权限' in response.text if uid == 3 else '无权查看工资数据' in response.text)
    asyncio.run(run())


def dependency_calls(route):
    return [dependency.call for dependency in route.dependant.dependencies]


def test_single_self_exception_and_guard_on_every_management_route():
    routes = [r for r in app.routes if isinstance(r, APIRoute) and r.endpoint.__module__ == payroll.__name__]
    assert len(routes) == 22 and len(MANAGEMENT_ROUTES) == 21
    self_routes = [r for r in routes if r.endpoint is payroll.my_payslip]
    assert len(self_routes) == 1
    # 本人工资单是唯一例外，且不挂非劳工守卫；可见范围仍由本人身份和仓库校验决定。
    assert require_non_labor not in dependency_calls(self_routes[0])
    for route in MANAGEMENT_ROUTES:
        assert dependency_calls(route)[0] is require_non_labor, route.path

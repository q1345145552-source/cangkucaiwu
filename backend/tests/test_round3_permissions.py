from app.services.permission_migrations import MODIFICATION_LOGS_PERMISSION_MARKER
"""第三轮真实 HTTP、独立数据库、工资快照与补权迁移测试。"""
import asyncio
import ast
from contextlib import asynccontextmanager
from datetime import date, datetime
from pathlib import Path

import pytest
from sqlalchemy import select, update, func

from app.main import app
from app.models import User, UserWarehouse, Employee, RestDay, SalaryTemplate, DeductionTemplate, SystemSetting
from app.models.payroll import PayrollRecord
from app.core.menu_registry import MENU_PERMISSIONS_BY_KEY
from app.services.permission_migrations import (
    ROUND2_PERMISSIONS, ROUND2_PERMISSION_MARKER, ROUND3_PERMISSIONS, ROUND3_PERMISSION_MARKER,
    ROUND4_PERMISSIONS, ROUND4_PERMISSION_MARKER, ROUND5_PERMISSION_MARKER, ROUND6_PERMISSION_MARKER, ROUND9_SUPERVISOR_PERMISSION_MARKER,
    backfill_round3_permissions, run_permission_migrations,
)
from tests.test_round2_permissions import environment, auth, set_perms, png

CALC = {'end_date': '2026-10-15', 'employee_ids': [1]}
CASES = [
    ('GET','/employees','employees',None),
    ('POST','/employees','employees',{'name':'新员工','employee_no':'NEW-LABOR','password':'test-password','salary_template_id':1,'deduction_template_id':1,'hire_date':'2026-10-01'}),
    ('PUT','/employees/1','employees',{'name':'已编辑'}),
    ('POST','/employees/1/resign','employees',{'reason':'voluntary','resignation_date':'2026-10-15'}),
    ('DELETE','/employees/1','employees',None),
    ('POST','/employees/bind-existing-accounts','employees',None),
    ('POST','/employees/batch-set-templates','employees',{'employee_ids':[1],'salary_template_id':1,'deduction_template_id':1}),
    ('POST','/employees/1/photo','employees','photo'),
    ('POST','/employees/1/passport-photo','employees','photo'),
    ('POST','/employees/1/work-permit-photo','employees','photo'),
    ('GET','/employees/1/summary','employees',None),
    ('GET','/employees/max-limit','employees',None),
    ('PUT','/employees/max-limit?max_employees=60','employees',{}),
    ('POST','/payroll/calculate','payroll',CALC),
    ('POST','/payroll/preview','payroll',CALC),
    ('POST','/payroll/single-settle','payroll',{'employee_id':1,'end_date':'2026-10-15'}),
    ('GET','/payroll','payroll',None),
    ('GET','/payroll/summary','payroll',None),
    ('GET','/payroll/export','payroll',None),
    ('POST','/payroll/1/confirm','payroll',None),
    ('POST','/payroll/confirm-all?period=2026-10','payroll',None),
    ('POST','/payroll/batch-confirm','payroll',{'record_ids':[1]}),
    ('POST','/payroll/batch-disburse','payroll',{'record_ids':[2],'account_id':1}),
    ('POST','/payroll/batch-delete','payroll',{'record_ids':[1]}),
    ('POST','/payroll/1/recalc','payroll',{'void_reason':'权限回归','mode':'recalc'}),
    ('POST','/payroll/batch-recalc','payroll',{'record_ids':[1],'void_reason':'权限回归','mode':'recalc'}),
    ('DELETE','/payroll/1','payroll',None),
    ('DELETE','/payroll/period/2026-10','payroll',None),
    ('POST','/payroll/2/disburse','payroll',{'account_id':1}),
    ('POST','/payroll/3/revoke-disbursement','payroll',None),
    ('GET','/payroll/my-payslip','payroll',None),
    ('GET','/payroll/settlement-progress','payroll',None),
    ('GET','/salary-templates','salary_templates',None),
    ('POST','/salary-templates','salary_templates',{'name':'新薪资模板','type':'daily','amount':500}),
    ('PUT','/salary-templates/1','salary_templates',{'amount':450}),
    ('DELETE','/salary-templates/3','salary_templates',None),
    ('GET','/deduction-templates','deduction_templates',None),
    ('POST','/deduction-templates','deduction_templates',{'name':'新扣款模板'}),
    ('PUT','/deduction-templates/1','deduction_templates',{'name':'已编辑模板'}),
    ('DELETE','/deduction-templates/3','deduction_templates',None),
]


@asynccontextmanager
async def hr_environment(tmp_path, monkeypatch):
    async with environment(tmp_path, monkeypatch) as (engine, factory, client):
        # 仅把测试上传的保存目录映射到临时目录；图片处理仍调用真实实现。
        import app.services.image_utils as images
        original_save = images.save_image
        def save_in_test(content, absolute, relative, filename):
            return original_save(content, str(tmp_path / 'hr-uploads' / absolute.lstrip('/')), relative, filename)
        monkeypatch.setattr(images, 'save_image', save_in_test)
        async with factory() as db:
            for wid in (1, 2):
                db.add(SalaryTemplate(id=wid, warehouse_id=wid, name=f'薪资{wid}', type='daily', amount=400))
                db.add(DeductionTemplate(id=wid, warehouse_id=wid, name=f'扣款{wid}'))
                uid = wid + 4
                db.add(User(id=uid, username=f'labor{wid}', display_name=f'员工{wid}', role='warehouse_labor',
                            password_hash='unused', warehouse_id=wid, extra_permissions=[]))
                db.add(UserWarehouse(user_id=uid, warehouse_id=wid))
                db.add(Employee(id=wid, warehouse_id=wid, name=f'员工{wid}', user_id=uid,
                                hire_date=datetime(2026,10,1), salary_template_id=wid, deduction_template_id=wid))
                for day in range(1,16):
                    db.add(RestDay(employee_id=wid, warehouse_id=wid, rest_date=date(2026,10,day)))
            db.add(SalaryTemplate(id=3, warehouse_id=1, name='未使用薪资模板', type='daily', amount=400))
            db.add(DeductionTemplate(id=3, warehouse_id=1, name='未使用扣款模板'))
            for rid, wid, eid, status, disbursed in [
                (1,1,1,'pending',False), (2,1,1,'confirmed',False), (3,1,1,'confirmed',True), (10,2,2,'pending',False),
            ]:
                db.add(PayrollRecord(id=rid, warehouse_id=wid, employee_id=eid, period='2026-10',
                                    settle_start_date=date(2026,10,1),settle_end_date=date(2026,10,15),
                                    status=status, disbursed=disbursed, net_pay=1234.56, base_pay=1500,
                                    gross_pay=1600, total_deductions=365.44, overtime_pay=100, detail='{}'))
            await db.commit()
        from app.services.payroll_expense import backfill_payroll_categories
        async with engine.begin() as conn:
            await backfill_payroll_categories(conn)
        yield engine, factory, client


async def snapshot(factory):
    async with factory() as db:
        return [tuple(row) for row in (await db.execute(select(PayrollRecord.__table__).order_by(PayrollRecord.id))).all()]


async def call(client, method, path, body, uid):
    kwargs = {'headers':auth(uid)}
    if body == 'photo':
        kwargs['files'] = {'file':('test.png',png(),'image/png')}
    elif body is not None:
        kwargs['json'] = body
    return await client.request(method, '/api/v1'+path, **kwargs)


def business_status(uid, path):
    if path.startswith(('/employees', '/salary-templates', '/deduction-templates')):
        return 200
    if path == '/payroll/my-payslip':
        return 403  # 原有劳工本人专用限制
    if uid in (2,3) and path not in ('/payroll','/payroll/summary'):
        return 403  # 原有业务角色限制
    return 200


@pytest.mark.parametrize('method,path,module,body',CASES,ids=[f'{m} {p}' for m,p,_,_ in CASES])
@pytest.mark.parametrize('uid,granted',[(3,False),(4,False),(3,True),(4,True),(1,False),(2,False)],
                         ids=['staff-deny','supervisor-deny','staff-allow','supervisor-allow','admin','super-admin'])
def test_all_hr_endpoints(tmp_path,monkeypatch,method,path,module,body,uid,granted):
    async def run():
        async with hr_environment(tmp_path,monkeypatch) as (_,factory,client):
            if granted:
                permissions=[MENU_PERMISSIONS_BY_KEY[module].label]
                if path.endswith('/resign'):
                    permissions.append(MENU_PERMISSIONS_BY_KEY['payroll'].label)
                await set_perms(factory,uid,permissions)
            before=await snapshot(factory)
            response=await call(client,method,path,body,uid)
            if uid in (3,4) and not granted:
                assert response.status_code==403,response.text
                assert response.json()['detail'].startswith('无此操作权限'),response.text
                assert await snapshot(factory)==before
            else:
                expected=business_status(uid,path)
                assert response.status_code==expected,response.text
                if expected==403:
                    assert not response.json()['detail'].startswith('无此操作权限'),response.text
                # 迁移之外：读取和模板变动不得自动重算已有工资。
                if method=='GET' or module.endswith('templates') or expected!=200:
                    assert await snapshot(factory)==before
                if path=='/payroll/batch-recalc' and expected==200:
                    assert response.json()['success_count']==1,response.text
    asyncio.run(run())


@pytest.mark.parametrize('uid',[3,4])
def test_shared_hr_reads(tmp_path,monkeypatch,uid):
    async def run():
        async with hr_environment(tmp_path,monkeypatch) as (_,factory,client):
            for key in ('employees','payroll','overtime','employee_deductions','employee_advances'):
                await set_perms(factory,uid,[MENU_PERMISSIONS_BY_KEY[key].label])
                result=await client.get('/api/v1/employees?active_only=true',headers=auth(uid))
                assert result.status_code==200,result.text
                if uid in (3,4):
                    assert {e['warehouse_id'] for e in result.json()['data']}=={1}
                if key!='employees':
                    result=await client.put('/api/v1/employees/1',headers=auth(uid),json={'remark':'越权'})
                    assert result.status_code==403 and result.json()['detail'].startswith('无此操作权限')
            await set_perms(factory,uid,['员工档案'])
            for path in ('/salary-templates','/deduction-templates'):
                result=await client.get('/api/v1'+path,headers=auth(uid))
                assert result.status_code==200,result.text
                result=await client.put('/api/v1'+path+'/1',headers=auth(uid),json={'name':'越权'})
                assert result.status_code==403 and result.json()['detail'].startswith('无此操作权限')
            # 即使有员工档案权限，缺工资权限也不能借离职入口算工资。
            before=await snapshot(factory)
            result=await client.post('/api/v1/employees/1/resign',headers=auth(uid),
                                     json={'reason':'voluntary','resignation_date':'2026-10-15'})
            assert result.status_code==403 and '需要: 工资' in result.json()['detail']
            assert await snapshot(factory)==before
            await set_perms(factory,uid,['报销管理'])
            assert (await client.get('/api/v1/employees',headers=auth(uid))).status_code==403
    asyncio.run(run())


@pytest.mark.parametrize('uid',[1,3,4])
@pytest.mark.parametrize('path,body',[
    ('/payroll/1/recalc',{'void_reason':'作废测试','mode':'void'}),
    ('/payroll/batch-recalc',{'record_ids':[1],'void_reason':'作废测试','mode':'void'}),
])
def test_void_actions(tmp_path,monkeypatch,uid,path,body):
    async def run():
        async with hr_environment(tmp_path,monkeypatch) as (_,factory,client):
            before=await snapshot(factory)
            if uid!=1:
                result=await client.post('/api/v1'+path,headers=auth(uid),json=body)
                assert result.status_code==403 and result.json()['detail'].startswith('无此操作权限')
                assert await snapshot(factory)==before
            await set_perms(factory,uid,['工资'])
            result=await client.post('/api/v1'+path,headers=auth(uid),json=body)
            assert result.status_code==(403 if uid==3 else 200),result.text
            if uid!=3:
                async with factory() as db:
                    r=await db.get(PayrollRecord,1)
                    assert r.voided is True and r.net_pay==1234.56
                    assert (await db.execute(select(func.count(PayrollRecord.id)))).scalar_one()==4
    asyncio.run(run())


def test_round3_migration_preserves_payroll_and_revocations(tmp_path,monkeypatch):
    async def run():
        async with hr_environment(tmp_path,monkeypatch) as (engine,factory,client):
            await set_perms(factory,3,None)
            await set_perms(factory,4,['到账流水','员工档案','员工档案'])
            async with factory() as db:
                db.add(User(id=7,username='inactive-staff',display_name='停用财务',role='staff',
                            is_active=False,password_hash='unused',extra_permissions=['自定义旧权限']))
                db.add(SystemSetting(warehouse_id=1,key=ROUND2_PERMISSION_MARKER,value='true'))
                db.add(SystemSetting(warehouse_id=1,key=ROUND4_PERMISSION_MARKER,value='true'))
                db.add(SystemSetting(warehouse_id=1,key=ROUND5_PERMISSION_MARKER,value='true'))
                db.add(SystemSetting(warehouse_id=1,key=ROUND6_PERMISSION_MARKER,value='true'))
                db.add(SystemSetting(warehouse_id=1,key=ROUND9_SUPERVISOR_PERMISSION_MARKER,value='true'))
                db.add(SystemSetting(warehouse_id=1,key=MODIFICATION_LOGS_PERMISSION_MARKER,value='true'))
                await db.commit()
            before=await snapshot(factory)
            async with engine.begin() as conn:
                counts=await run_permission_migrations(conn)
                assert counts=={'round2':0,'round3':3,'round4':0,'round5':0,'round6':0,'round9':0,'modification_logs':0}
            assert await snapshot(factory)==before
            async with factory() as db:
                values=dict((await db.execute(select(User.id,User.extra_permissions))).all())
                assert values[1]==values[2]==values[5]==values[6]==[]
                assert values[3]==list(ROUND3_PERMISSIONS)
                assert values[4]==['到账流水',*ROUND3_PERMISSIONS]
                assert values[7]==['自定义旧权限',*ROUND3_PERMISSIONS]
                assert (await db.execute(select(func.count(SystemSetting.id)).where(
                    SystemSetting.key==ROUND3_PERMISSION_MARKER))).scalar_one()==1
                print('\n第三轮补权后数据库：',values)
            # 只读列表和导出不得重算，所有已计算工资单全字段仍不变。
            for path in ('/payroll','/payroll/summary','/payroll/settlement-progress','/payroll/export'):
                result=await client.get('/api/v1'+path,headers=auth(4))
                assert result.status_code==200,result.text
            assert await snapshot(factory)==before
            await set_perms(factory,3,[])
            async with engine.begin() as conn:
                assert await run_permission_migrations(conn)=={'round2':0,'round3':0,'round4':0,'round5':0,'round6':0,'round9':0,'modification_logs':0}
            async with factory() as db:
                assert (await db.get(User,3)).extra_permissions==[]
            assert await snapshot(factory)==before
    asyncio.run(run())


def test_round3_migration_failure_rolls_back(tmp_path,monkeypatch):
    async def run():
        async with hr_environment(tmp_path,monkeypatch) as (engine,factory,_):
            before=await snapshot(factory)
            with pytest.raises(RuntimeError):
                async with engine.begin() as conn:
                    await backfill_round3_permissions(conn)
                    raise RuntimeError('模拟事务失败')
            async with factory() as db:
                assert (await db.get(User,4)).extra_permissions==[]
                assert (await db.execute(select(SystemSetting.id).where(SystemSetting.key==ROUND3_PERMISSION_MARKER))).first() is None
            assert await snapshot(factory)==before
    asyncio.run(run())


def test_hr_route_inventory():
    prefix_map={'employees':'employees','payroll':'payroll','salary_template':'salary-templates','deduction_template':'deduction-templates'}
    root=Path(__file__).resolve().parents[1]/'app/api/v1'
    seen=[]
    for filename,prefix in prefix_map.items():
        for node in ast.walk(ast.parse((root/(filename+'.py')).read_text())):
            if not isinstance(node,ast.AsyncFunctionDef):
                continue
            for decorator in node.decorator_list:
                if isinstance(decorator,ast.Call) and isinstance(decorator.func,ast.Attribute) and isinstance(decorator.func.value,ast.Name) and decorator.func.value.id=='router':
                    path='/'+prefix+decorator.args[0].value
                    seen.append((decorator.func.attr.upper(),path))
                    default=next(d for arg,d in zip(node.args.args[-len(node.args.defaults):],node.args.defaults) if arg.arg=='current_user')
                    assert any(dep in ast.unparse(default) for dep in ('check_staff_permission', 'employee_access')),node.name
    assert len(seen)==40
    # 请求清单使用实际参数值，标准化后与所有40条路由精确对应。
    def normalize(path):
        return __import__('re').sub(r'\{[^}]+\}', '{}', path.split('?')[0])
    expected={(method,normalize(path)) for method,path in seen}
    actual=set()
    for method,path,_,_ in CASES:
        path=path.split('?')[0]
        if '/period/' in path:
            path=path.rsplit('/',1)[0]+'/{}'
        path=__import__('re').sub(r'/[123](?=/|$)','/{}',path)
        actual.add((method,path))
    assert actual==expected


@pytest.mark.parametrize('uid',[1,4])
def test_hr_warehouse_isolation(tmp_path,monkeypatch,uid):
    async def run():
        async with hr_environment(tmp_path,monkeypatch) as (_,factory,client):
            await set_perms(factory,uid,list(ROUND3_PERMISSIONS))
            before=await snapshot(factory)
            for method,path,body in [
                ('PUT','/employees/2',{'name':'越权'}),
                ('POST','/employees/2/resign',{'reason':'voluntary','resignation_date':'2026-10-15'}),
                ('DELETE','/employees/2',None),
                ('POST','/employees/batch-set-templates',{'employee_ids':[1,2],'salary_template_id':1,'deduction_template_id':1}),
                ('GET','/employees/2/summary',None),
                ('POST','/employees/2/photo','photo'),
                ('POST','/employees/2/passport-photo','photo'),
                ('POST','/employees/2/work-permit-photo','photo'),
                ('PUT','/salary-templates/2',{'amount':1}), ('DELETE','/salary-templates/2',None),
                ('PUT','/deduction-templates/2',{'name':'越权'}), ('DELETE','/deduction-templates/2',None),
                ('POST','/payroll/single-settle',{'employee_id':2,'end_date':'2026-10-15'}),
                ('POST','/payroll/10/confirm',None),
                ('POST','/payroll/10/disburse',{}),
                ('POST','/payroll/10/revoke-disbursement',None),
                ('DELETE','/payroll/10',None),
                ('POST','/payroll/10/recalc',{'mode':'recalc','void_reason':'越权'}),
                ('POST','/payroll/10/recalc',{'mode':'void','void_reason':'越权'}),
                ('POST','/payroll/batch-confirm',{'record_ids':[1,10]}),
                ('POST','/payroll/batch-disburse',{'record_ids':[2,10]}),
                ('POST','/payroll/batch-delete',{'record_ids':[1,10]}),
                ('POST','/payroll/batch-recalc',{'record_ids':[1,10],'mode':'recalc','void_reason':'越权'}),
                ('POST','/payroll/batch-recalc',{'record_ids':[1,10],'mode':'void','void_reason':'越权'}),
            ]:
                response=await call(client,method,path,body,uid)
                assert response.status_code in (403,404),(method,path,response.text)
                assert await snapshot(factory)==before
            # 列表、汇总、导出及周期批量操作始终只取本仓；伪造header无效。
            response=await client.get('/api/v1/employees',headers={**auth(uid),'X-Warehouse-ID':'2'})
            assert {row['warehouse_id'] for row in response.json()['data']}=={1}
            response=await client.get('/api/v1/payroll',headers=auth(uid))
            assert {row['id'] for row in response.json()['data']}=={1,2,3}
            for prefix in ('salary-templates','deduction-templates'):
                response=await client.get('/api/v1/'+prefix,headers=auth(uid))
                assert {row['id'] for row in response.json()['data']}=={1,3}
            response=await client.get('/api/v1/payroll/summary',headers=auth(uid))
            assert response.json()['record_count']==3
            response=await client.get('/api/v1/payroll/export',headers=auth(uid))
            from openpyxl import load_workbook
            from io import BytesIO
            rows=list(load_workbook(BytesIO(response.content)).active.values)
            assert {row[0] for row in rows[1:]}=={'员工1'}
            for action in ('calculate','preview'):
                response=await client.post('/api/v1/payroll/'+action,headers=auth(uid),
                                           json={'end_date':'2026-10-15','employee_ids':[2]})
                assert response.status_code==200,response.text
                assert await snapshot(factory)==before  # 外仓员工不会被计算。
            foreign_before=next(row for row in before if row[0]==10)
            response=await client.delete('/api/v1/payroll/period/2026-10',headers=auth(uid))
            assert response.status_code==200,response.text
            assert next(row for row in await snapshot(factory) if row[0]==10)==foreign_before
    asyncio.run(run())


@pytest.mark.parametrize('uid',[1,4])
def test_explicit_calculate_creates_only_new_payroll(tmp_path,monkeypatch,uid):
    async def run():
        async with hr_environment(tmp_path,monkeypatch) as (_,factory,client):
            await set_perms(factory,uid,['工资'])
            # 单独增加一个未结算员工，旧工资单保留以检查没有隐式重算。
            async with factory() as db:
                db.add(Employee(id=3,warehouse_id=1,name='待结算员工',hire_date=datetime(2026,10,1),
                                salary_template_id=1,deduction_template_id=1))
                for day in range(1,16):
                    db.add(RestDay(employee_id=3,warehouse_id=1,rest_date=date(2026,10,day)))
                await db.commit()
            before=await snapshot(factory)
            response=await client.post('/api/v1/payroll/calculate',headers=auth(uid),
                                       json={'end_date':'2026-10-15','employee_ids':[3]})
            assert response.status_code==200,response.text
            assert response.json()['record_count']==1,response.text
            after=await snapshot(factory)
            assert len(after)==len(before)+1
            assert after[:len(before)]==before
    asyncio.run(run())


def test_labor_payslip_and_attendance_unchanged(tmp_path,monkeypatch):
    async def run():
        async with hr_environment(tmp_path,monkeypatch) as (_,factory,client):
            before=await snapshot(factory)
            # 劳工没有额外权限，仍按原有本人+本仓逻辑读取工资单。
            for uid,expected_ids in ((5,{1,2,3}),(6,{10})):
                response=await client.get('/api/v1/payroll/my-payslip',headers=auth(uid))
                assert response.status_code==200,response.text
                assert {r['id'] for r in response.json()['data']}==expected_ids
            # 考勤不依赖员工档案权限；第四轮后独立授予考勤/请假权限。
            await set_perms(factory,4,list(ROUND4_PERMISSIONS))
            for path in ('/attendance/leaves','/attendance/rest-days','/attendance/calendar?month=2026-10'):
                response=await client.get('/api/v1'+path,headers=auth(4))
                assert response.status_code==200,response.text
            for key,path in (('overtime','/overtime'),('employee_deductions','/employee-deductions'),('employee_advances','/employee-advances')):
                await set_perms(factory,4,[MENU_PERMISSIONS_BY_KEY[key].label])
                response=await client.get('/api/v1'+path,headers=auth(4))
                assert response.status_code==200,response.text
                response=await client.get('/api/v1/employees?active_only=true',headers=auth(4))
                assert response.status_code==200,response.text
            assert await snapshot(factory)==before
    asyncio.run(run())

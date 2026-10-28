import ast
import asyncio
import json
import subprocess
from datetime import date, datetime
from pathlib import Path
import pytest
from sqlalchemy import select, func
from app.models import User, UserWarehouse, Employee, ClockInRecord
from app.models.payroll import PayrollRecord
from app.models.employee_advance import EmployeeAdvance
from app.models.data_change_history import DataChangeHistory
import app.api.v1.payroll as payroll
import app.services.advance_recipients as recipients
from tests.test_round2_permissions import auth, set_perms
from tests.test_round3_permissions import snapshot
from tests.advance_funding_test_support import funded_hr_environment as hr_environment, funding_body
from tests.test_round15_employee_self import enable

async def options(c, uid=1):
    r = await c.get('/api/v1/employee-advances/recipients', headers=auth(uid))
    assert r.status_code == 200, r.text
    return r.json()['data']

async def create(c, *, uid=1, **target):
    return await c.post('/api/v1/employee-advances', headers=auth(uid), json={
        'amount': 100, 'advance_date': '2026-10-16', 'funding_source': 'company_account', 'payment_account_id': 1, **target,
    })

async def employee_count(factory):
    async with factory() as db:
        return (await db.execute(select(func.count(Employee.id)))).scalar_one()


def test_options_auto_archive_reuse_and_labor(tmp_path, monkeypatch):
    async def run():
        async with hr_environment(tmp_path, monkeypatch) as (_, f, c):
            monkeypatch.setattr(recipients, 'thai_today', lambda: date(2026,10,17))
            initial = await employee_count(f)
            choices = await options(c)
            assert {x['value'] for x in choices} == {'employee:1', 'user:1', 'user:4'}
            assert next(x for x in choices if x['user_id'] == 4)['role_label'] == '主管'
            assert await employee_count(f) == initial  # Opening options never writes.
            old = await snapshot(f)
            first = await create(c, user_id=4)
            assert first.status_code == 200 and first.json()['approval_status'] == 'pending', first.text
            async with f() as db:
                emp = (await db.execute(select(Employee).where(Employee.user_id == 4))).scalar_one()
                user = await db.get(User,4)
                advance = await db.get(EmployeeAdvance, first.json()['id'])
                actual = {'employee_id':emp.id, 'name':emp.name, 'employee_no':user.username,
                          'position':emp.position,'warehouse_id':emp.warehouse_id,'status':emp.status,
                          'user_id':emp.user_id,'hire_date':emp.hire_date.isoformat(),
                          'salary_template_id':emp.salary_template_id,'deduction_template_id':emp.deduction_template_id,
                          'attendance_enabled':user.attendance_enabled,'attendance_employee_id':user.attendance_employee_id,
                          'attendance_enabled_at':str(user.attendance_enabled_at)}
                assert actual['position']=='仓库主管' and actual['name']=='supervisor' and actual['employee_no']=='supervisor'
                assert actual['warehouse_id']==1 and actual['status']=='regular' and actual['hire_date']=='2026-10-17T00:00:00'
                assert emp.salary_template_id is emp.deduction_template_id is None
                assert not user.attendance_enabled and user.attendance_employee_id is None and user.attendance_enabled_at is None
                assert advance.employee_id==emp.id and advance.approval_status=='pending'
                eid=emp.id
                assert (await db.execute(select(DataChangeHistory).where(DataChangeHistory.module=='employee',DataChangeHistory.record_id==eid))).scalar_one().after_data['source']=='employee_advances'
            second=await create(c,user_id=4);assert second.status_code==200,second.text
            assert await employee_count(f)==initial+1
            choices_after=await options(c)
            assert sum(x['user_id']==4 for x in choices_after)==1
            assert next(x for x in choices_after if x['user_id']==4)['value']==f'employee:{eid}'
            third=await create(c,employee_id=eid);assert third.status_code==200
            labor=await create(c,employee_id=1);assert labor.status_code==200 and labor.json()['approval_status']=='pending'
            assert await snapshot(f)==old
            print('MANAGER_ADVANCE_PROOF',json.dumps({'choices':choices,'employee_and_account':actual,'advance':{'id':first.json()['id'],'employee_id':eid,'amount':100,'approval_status':first.json()['approval_status']},'employee_count_before':initial,'after_two_advances':await employee_count(f)},ensure_ascii=False))
    asyncio.run(run())


def test_existing_enabled_archive_and_self_approval_preserved(tmp_path,monkeypatch):
    async def run():
        async with hr_environment(tmp_path,monkeypatch) as (_,f,c):
            await enable(f);initial=await employee_count(f)
            opts=await options(c);assert sum(x['user_id']==4 for x in opts)==1
            assert next(x for x in opts if x['user_id']==4)['value']=='employee:5'
            assert (await create(c,user_id=4)).status_code==200
            await set_perms(f,4,['员工预支'])
            account_alias=await create(c,uid=4,user_id=4);assert account_alias.status_code==403
            own=await create(c,uid=4,employee_id=5);assert own.status_code==200 and own.json()['approval_status']=='pending'
            before_other=await employee_count(f)
            async with f() as db: advance_count=(await db.execute(select(func.count(EmployeeAdvance.id)))).scalar_one()
            other=await create(c,uid=4,employee_id=1);assert other.status_code==403 and set(other.json())=={'detail'}
            assert await employee_count(f)==before_other
            async with f() as db: assert (await db.execute(select(func.count(EmployeeAdvance.id)))).scalar_one()==advance_count
            assert await employee_count(f)==initial
            async with f() as db:
                u=await db.get(User,4);e=await db.get(Employee,5)
                assert u.attendance_enabled and u.attendance_employee_id==5 and e.salary_template_id==1 and e.deduction_template_id==1
    asyncio.run(run())


def test_disabled_attendance_history_reused_not_duplicated(tmp_path,monkeypatch):
    async def run():
        async with hr_environment(tmp_path,monkeypatch) as (_,f,c):
            await enable(f)
            r=await c.put('/api/v1/users/4',headers=auth(1),json={'attendance_enabled':False});assert r.status_code==200
            before=await employee_count(f)
            opts=await options(c);assert next(x for x in opts if x['user_id']==4)['value']=='employee:5'
            r=await create(c,user_id=4);assert r.status_code==200,r.text
            assert await employee_count(f)==before
            async with f() as db:
                assert (await db.get(Employee,5)).user_id==4
                assert not (await db.get(User,4)).attendance_enabled
                assert (await db.get(User,4)).attendance_employee_id is None
    asyncio.run(run())


@pytest.mark.parametrize('invalid',['outside','staff','labor','inactive','both','neither','deleted','resigned','conflict','bad_source','bad_fund'])
def test_rejected_targets_and_rollback(tmp_path,monkeypatch,invalid):
    async def run():
        async with hr_environment(tmp_path,monkeypatch) as (_,f,c):
            target={'user_id':4}
            if invalid in ('deleted','resigned','conflict'):
                await enable(f)
                async with f() as db:
                    emp=await db.get(Employee,5)
                    if invalid=='deleted':emp.is_deleted=True
                    if invalid=='resigned':emp.status='resigned'
                    if invalid=='conflict':emp.user_id=3
                    await db.commit()
            if invalid=='outside':
                async with f() as db:(await db.get(User,4)).warehouse_id=2;await db.commit()
            if invalid=='staff':target={'user_id':3}
            if invalid=='labor':target={'user_id':5}
            if invalid=='inactive':
                async with f() as db:(await db.get(User,4)).is_active=False;await db.commit()
            if invalid=='both':target={'user_id':4,'employee_id':1}
            if invalid=='neither':target={}
            if invalid=='bad_source':target['funding_source']='invalid'
            if invalid=='bad_fund':target.update(funding_source='expense_fund',fund_account_id=999)
            before=await employee_count(f)
            r=await create(c,**target);assert r.status_code in (400,404,409),r.text
            assert await employee_count(f)==before
            async with f() as db:
                assert (await db.execute(select(func.count(EmployeeAdvance.id)))).scalar_one()==0
                assert not (await db.execute(select(DataChangeHistory).where(DataChangeHistory.module=='employee',DataChangeHistory.operation_type=='create'))).scalars().all()
    asyncio.run(run())


def test_recipient_role_and_warehouse_scope(tmp_path,monkeypatch):
    async def run():
        async with hr_environment(tmp_path,monkeypatch) as (_,f,c):
            for uid in (3,4):
                await set_perms(f,uid,[])
                r=await c.get('/api/v1/employee-advances/recipients',headers=auth(uid));assert r.status_code==403
                await set_perms(f,uid,['员工预支'])
                assert await options(c,uid)==await options(c)
            r=await c.get('/api/v1/employee-advances/recipients',headers=auth(5));assert r.status_code==403
            r=await c.get('/api/v1/employee-advances/recipients',headers={**auth(1),'X-Warehouse-ID':'2'})
            assert r.status_code==403 and r.json()=={'detail':'无权访问所选仓库'}
            r=await create(c,user_id=1);assert r.status_code==200 and r.json()['approval_status']=='pending'
    asyncio.run(run())


def test_payroll_excludes_off_managers_not_enabled_or_staff_or_labor(tmp_path,monkeypatch):
    async def run():
        async with hr_environment(tmp_path,monkeypatch) as (_,f,c):
            monkeypatch.setattr(payroll,'thai_today',lambda:date(2026,10,20))
            monkeypatch.setattr(recipients,'thai_today',lambda:date(2026,10,16))
            assert (await create(c,user_id=4)).status_code==200
            assert (await create(c,user_id=1)).status_code==200
            async with f() as db:
                off=(await db.execute(select(Employee).where(Employee.user_id.in_([1,4])))).scalars().all()
                off_ids={e.id for e in off}
                db.add(User(id=7,username='enabled_supervisor',display_name='开启考勤主管',role='supervisor',warehouse_id=1,password_hash='unused',attendance_enabled=True))
                db.add(UserWarehouse(user_id=7,warehouse_id=1));await db.flush()
                for uid,name,position in [(7,'开启考勤主管','仓库主管'),(3,'财务','仓库主管')]:
                    e=Employee(user_id=uid,name=name,position=position,warehouse_id=1,status='regular',hire_date=datetime(2026,10,16),salary_template_id=1,deduction_template_id=1)
                    db.add(e);await db.flush()
                    if uid==7:(await db.get(User,7)).attendance_employee_id=e.id
                (await db.get(Employee,1)).hire_date=datetime(2026,10,16)
                for uid in (5,7,3):
                    for session,h in ((1,9),(2,12),(3,13),(4,18)):
                        db.add(ClockInRecord(user_id=uid,warehouse_id=1,clock_date=date(2026,10,16),session=session,clocked_in_at=datetime(2026,10,16,h),status='normal'))
                await db.commit()
            old=await snapshot(f)
            r=await c.post('/api/v1/payroll/preview',headers=auth(3),json={'end_date':'2026-10-16'});assert r.status_code==200,r.text
            r=await c.post('/api/v1/payroll/calculate',headers=auth(3),json={'end_date':'2026-10-16'});assert r.status_code==200,r.text
            async with f() as db:
                rows=(await db.execute(select(PayrollRecord).where(PayrollRecord.settle_start_date==date(2026,10,16)))).scalars().all()
                emps={e.id:e for e in (await db.execute(select(Employee))).scalars().all()}
                assert len(rows)==3 and not (off_ids & {r.employee_id for r in rows}),r.text
                assert {emps[r.employee_id].user_id for r in rows}=={3,5,7}
                actual=[{'employee_id':r.employee_id,'name':emps[r.employee_id].name,'net_pay':r.net_pay} for r in rows]
            after=await snapshot(f);assert [r for r in after if r[0] in {x[0] for x in old}]==old
            r=await c.post('/api/v1/payroll/calculate',headers=auth(3),json={'end_date':'2026-10-16','employee_ids':list(off_ids)})
            assert r.status_code==200 and r.json().get('record_count',0)==0,r.text
            print('MANAGER_ADVANCE_PAYROLL',json.dumps({'excluded_employee_ids':sorted(off_ids),'payroll':actual},ensure_ascii=False))
    asyncio.run(run())


def test_unchanged_review_and_payroll_math():
    root=Path(__file__).resolve().parents[2]
    path='backend/app/api/v1/payroll.py'
    def math(s):return {n.name:ast.dump(n,include_attributes=False) for n in ast.parse(s).body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name in {'_compute_employee_records','_rollback_advance_deductions'}}
    assert math((root/path).read_text())==math(subprocess.check_output(['git','show','e6cc888:'+path],cwd=root,text=True))


def test_later_enabling_attendance_reuses_auto_archive(tmp_path, monkeypatch):
    async def run():
        async with hr_environment(tmp_path, monkeypatch) as (_, f, c):
            assert (await create(c, user_id=4)).status_code == 200
            count = await employee_count(f)
            async with f() as db:
                eid = (await db.execute(select(Employee.id).where(Employee.user_id == 4))).scalar_one()
            r = await c.put('/api/v1/users/4', headers=auth(1), json={'attendance_enabled': True})
            assert r.status_code == 200, r.text
            assert await employee_count(f) == count
            async with f() as db:
                user = await db.get(User, 4)
                assert user.attendance_enabled and user.attendance_employee_id == eid
                assert (await db.get(Employee, eid)).salary_template_id is None
    asyncio.run(run())

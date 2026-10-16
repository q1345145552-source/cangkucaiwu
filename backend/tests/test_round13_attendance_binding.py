"""第十三轮：真实账号接口自动建档/复用/重开、冲突回滚、业务记录和审计。"""
import asyncio
import json
from datetime import datetime, date
from pathlib import Path
import subprocess
import pytest
from sqlalchemy import select, func
from app.core.timezone import thai_today
from app.models import User, Employee, UserWarehouse
from app.models.clock_in_records import ClockInRecord
from app.models.payroll import PayrollRecord
from app.models.data_change_history import DataChangeHistory
from tests.test_round2_permissions import auth
from tests.test_round3_permissions import hr_environment, snapshot


async def count(db, model):
    return (await db.execute(select(func.count()).select_from(model))).scalar_one()


async def toggle(client, uid, enabled, actor=1, **extra):
    return await client.put(f'/api/v1/users/{uid}', headers=auth(actor), json={'attendance_enabled': enabled, **extra})


@pytest.mark.parametrize('actor', [1, 2], ids=['admin', 'super-admin'])
@pytest.mark.parametrize('uid', [3, 4], ids=['staff', 'supervisor'])
def test_new_profile_fields_and_audit(tmp_path, monkeypatch, actor, uid):
    async def run():
        async with hr_environment(tmp_path, monkeypatch) as (_, factory, client):
            before = await snapshot(factory)
            async with factory() as db:
                user = await db.get(User, uid)
                expected = {k:getattr(user,k) for k in ('username','display_name','role','warehouse_id','password_hash','extra_permissions')}
                employee_count, user_count = await count(db,Employee), await count(db,User)
            r = await toggle(client,uid,True,actor)
            assert r.status_code == 200,r.text
            assert r.json()['attendance_employee_created'] is True
            assert '请到员工档案里设置薪资模板和扣款模板' in r.json()['message']
            async with factory() as db:
                user = await db.get(User,uid)
                employee = await db.get(Employee,user.attendance_employee_id)
                assert employee.name == expected['display_name']
                assert employee.position == '仓库主管' and employee.status == 'regular'
                assert employee.warehouse_id == user.warehouse_id == expected['warehouse_id']
                assert employee.user_id == user.id and employee.hire_date.date() == thai_today()
                assert employee.salary_template_id is None and employee.deduction_template_id is None
                assert employee.created_by == actor
                assert all(getattr(user,k)==v for k,v in expected.items())
                assert await count(db,Employee)==employee_count+1 and await count(db,User)==user_count
                history = (await db.execute(select(DataChangeHistory).where(DataChangeHistory.module=='employee',DataChangeHistory.record_id==employee.id))).scalar_one()
                assert history.operation_type=='create' and history.operator_id==actor and history.created_at
                assert history.after_data['employee_no']==user.username and history.after_data['source']=='attendance_enabled'
                eid=employee.id;enabled_at=user.attendance_enabled_at
                actual={'user':{'id':user.id,'username':user.username,'display_name':user.display_name,'role':user.role,'warehouse_id':user.warehouse_id,'attendance_enabled':user.attendance_enabled,'attendance_employee_id':eid,'attendance_enabled_at':enabled_at.isoformat()},'employee':{'id':eid,'name':employee.name,'employee_no':user.username,'position':employee.position,'warehouse_id':employee.warehouse_id,'status':employee.status,'user_id':employee.user_id,'hire_date':employee.hire_date.date().isoformat(),'salary_template_id':employee.salary_template_id,'deduction_template_id':employee.deduction_template_id},'history':{'id':history.id,'module':history.module,'record_id':history.record_id,'operation_type':history.operation_type,'operator_id':history.operator_id,'created_at':history.created_at.isoformat()}}
            listing=await client.get('/api/v1/employees',headers=auth(1))
            row=next(e for e in listing.json()['data'] if e['id']==eid)
            assert row['employee_no']==expected['username'] and row['status']=='regular'
            logs=await client.get(f'/api/v1/history?module=employee&record_id={eid}',headers=auth(1))
            assert logs.status_code==200 and logs.json()['total']==1
            for _ in range(2):
                repeat=await toggle(client,uid,True,actor)
                assert repeat.status_code==200 and repeat.json()['attendance_employee_created'] is False
                assert repeat.json()['attendance_employee_id']==eid
            async with factory() as db:
                assert await count(db,Employee)==employee_count+1
                assert (await db.get(User,uid)).attendance_enabled_at==enabled_at
                assert (await db.execute(select(func.count()).select_from(DataChangeHistory).where(DataChangeHistory.module=='employee',DataChangeHistory.operation_type=='create'))).scalar_one()==1
            assert await snapshot(factory)==before
            print('\n两边实际保存值：'+json.dumps(actual,ensure_ascii=False))
    asyncio.run(run())


@pytest.mark.parametrize('kind',['already-bound','account-pointer','history-after-close'])
def test_reuses_profile_without_overwriting_data(tmp_path,monkeypatch,kind):
    async def run():
        async with hr_environment(tmp_path,monkeypatch) as (_,factory,client):
            async with factory() as db:
                profile=Employee(id=10,warehouse_id=1,name='保留原姓名',position='原岗位',status='trial',user_id=4 if kind=='already-bound' else None,hire_date=datetime(2025,1,2),salary_template_id=1,deduction_template_id=1,daily_wage=777,base_salary=9000,phone='123')
                db.add(profile);await db.flush()
                if kind=='account-pointer':(await db.get(User,4)).attendance_employee_id=10
                if kind=='history-after-close':db.add(DataChangeHistory(module='user',record_id=4,operator_id=1,operation_type='edit',before_data={'attendance_employee_id':10},after_data={'attendance_employee_id':None},warehouse_id=1))
                await db.commit();before={c.name:getattr(profile,c.name) for c in Employee.__table__.columns};total=await count(db,Employee)
            r=await toggle(client,4,True)
            assert r.status_code==200,r.text
            assert r.json()['attendance_employee_id']==10 and not r.json()['attendance_employee_created']
            assert r.json()['attendance_notice'] is None
            async with factory() as db:
                profile=await db.get(Employee,10)
                assert await count(db,Employee)==total and profile.user_id==4
                for k,v in before.items():
                    if k not in ('user_id','updated_at'):assert getattr(profile,k)==v,k
                assert not (await db.execute(select(DataChangeHistory).where(DataChangeHistory.module=='employee',DataChangeHistory.operation_type=='create'))).first()
    asyncio.run(run())


def test_close_and_reopen_preserve_clock_payroll_and_archive(tmp_path,monkeypatch):
    async def run():
        async with hr_environment(tmp_path,monkeypatch) as (_,factory,client):
            opened=await toggle(client,4,True);assert opened.status_code==200
            eid=opened.json()['attendance_employee_id']
            async with factory() as db:
                employee=await db.get(Employee,eid);employee.salary_template_id=1;employee.deduction_template_id=1
                db.add(ClockInRecord(id=100,user_id=4,warehouse_id=1,clock_date=date(2026,10,15),session=1,status='normal',photo_path='old-clock.jpg'))
                db.add(PayrollRecord(id=100,warehouse_id=1,employee_id=eid,period='2026-10',settle_start_date=date(2026,10,1),settle_end_date=date(2026,10,15),net_pay=1234.56,base_pay=1500,status='confirmed',disbursed=True,detail='{"historical":true}'))
                await db.commit();total=await count(db,Employee)
                clock_before=tuple((await db.execute(select(ClockInRecord.__table__).where(ClockInRecord.id==100))).one())
            payroll_before=await snapshot(factory)
            for _ in range(2):assert (await toggle(client,4,False)).status_code==200
            async with factory() as db:
                user=await db.get(User,4);employee=await db.get(Employee,eid)
                assert user.attendance_employee_id is None and not user.attendance_enabled and user.attendance_enabled_at is None
                assert employee.user_id is None and not employee.is_deleted
            # A renamed account must still recover its original archive; names are not identity.
            edit=await client.put('/api/v1/users/4',headers=auth(1),json={'username':'renamed-supervisor','display_name':'改后的显示名','extra_permissions':['员工档案']})
            assert edit.status_code==200
            reopened=await toggle(client,4,True);assert reopened.status_code==200,reopened.text
            assert reopened.json()['attendance_employee_id']==eid and not reopened.json()['attendance_employee_created']
            async with factory() as db:
                employee=await db.get(Employee,eid)
                assert employee.user_id==4 and employee.salary_template_id==1 and employee.deduction_template_id==1
                assert await count(db,Employee)==total
                assert tuple((await db.execute(select(ClockInRecord.__table__).where(ClockInRecord.id==100))).one())==clock_before
            assert await snapshot(factory)==payroll_before
    asyncio.run(run())


@pytest.mark.parametrize('kind',['bound-other','history-bound-other','foreign-warehouse','deleted','missing','two-profiles','no-warehouse'])
def test_conflict_rolls_back_whole_account_update(tmp_path,monkeypatch,kind):
    async def run():
        async with hr_environment(tmp_path,monkeypatch) as (_,factory,client):
            async with factory() as db:
                user=await db.get(User,4)
                if kind=='no-warehouse':user.warehouse_id=None
                elif kind=='missing':user.attendance_employee_id=999
                else:
                    profile=Employee(id=10,warehouse_id=2 if kind=='foreign-warehouse' else 1,name='已有档案',user_id=3 if kind in ('bound-other','history-bound-other') else None,is_deleted=(kind=='deleted'))
                    db.add(profile);await db.flush()
                    if kind=='history-bound-other':db.add(DataChangeHistory(module='user',record_id=4,operator_id=1,operation_type='edit',before_data={'attendance_employee_id':10},after_data={'attendance_employee_id':None},warehouse_id=1))
                    else:user.attendance_employee_id=10
                    if kind=='two-profiles':db.add(Employee(id=11,warehouse_id=1,name='另一档案',user_id=4))
                await db.commit();username=user.username;total=await count(db,Employee);logs=await count(db,DataChangeHistory)
            # Super admin lets no-warehouse reach the explicit validation, without relaxing admin ownership.
            r=await toggle(client,4,True,2,username='must-rollback')
            assert r.status_code in (400,409),r.text
            if kind in ('bound-other','history-bound-other'):assert r.json()['detail']=='该员工档案已绑定其他账号'
            async with factory() as db:
                user=await db.get(User,4)
                assert user.username==username and not user.attendance_enabled
                assert await count(db,Employee)==total and await count(db,DataChangeHistory)==logs
    asyncio.run(run())


@pytest.mark.parametrize('stage',['employee-log','user-log'])
def test_audit_failure_rolls_back_archive_and_switch(tmp_path,monkeypatch,stage):
    async def run():
        import app.services.attendance_identity as service
        import app.api.v1.users as users_api
        async with hr_environment(tmp_path,monkeypatch) as (_,factory,client):
            async with factory() as db:total=await count(db,Employee)
            async def fail(*args,**kwargs):raise RuntimeError('模拟审计写入失败')
            monkeypatch.setattr(service if stage=='employee-log' else users_api,'record_history',fail)
            with pytest.raises(RuntimeError,match='模拟审计写入失败'):await toggle(client,4,True)
            async with factory() as db:
                user=await db.get(User,4)
                assert not user.attendance_enabled and user.attendance_employee_id is None and user.attendance_enabled_at is None
                assert await count(db,Employee)==total
                assert await count(db,DataChangeHistory)==0
    asyncio.run(run())


def test_thailand_hire_date_and_same_name_not_identity(tmp_path,monkeypatch):
    async def run():
        import app.services.attendance_identity as service
        async with hr_environment(tmp_path,monkeypatch) as (_,factory,client):
            monkeypatch.setattr(service,'thai_today',lambda:date(2026,10,17))
            async with factory() as db:
                user=await db.get(User,4);db.add(Employee(id=10,warehouse_id=1,name=user.display_name,user_id=3));await db.commit()
            r=await toggle(client,4,True);assert r.status_code==200,r.text
            async with factory() as db:
                user=await db.get(User,4);employee=await db.get(Employee,user.attendance_employee_id)
                assert employee.id!=10 and employee.hire_date.date()==date(2026,10,17)
                assert (await db.get(Employee,10)).user_id==3
    asyncio.run(run())


def test_business_and_frontend_sources_unchanged():
    root=Path(__file__).resolve().parents[2]
    for filename in ['backend/app/api/v1/payroll.py','backend/app/api/v1/attendance.py','backend/app/api/v1/clock_in.py','backend/app/api/v1/employees.py','backend/app/models/employee.py']:
        assert subprocess.check_output(['git','show','3603563:'+filename],cwd=root)==subprocess.check_output(['git','show','deada28:'+filename],cwd=root)
    assert not subprocess.check_output(['git','diff','deada28','3603563','--','frontend'],cwd=root)

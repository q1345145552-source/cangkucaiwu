"""第四轮：28接口、无额外权限劳工、隔离与工资口径回归。"""
import asyncio, ast, base64, json, re
from contextlib import asynccontextmanager
from datetime import date, datetime
from pathlib import Path
import pytest
from sqlalchemy import delete, select, update, func
from app.models import User, UserWarehouse, Employee, ClockInRecord, LeaveRequest, RestDay, Absence, SystemSetting
from app.models.overtime import OvertimeTask, OvertimeAssignment
from app.models.payroll import PayrollRecord
from app.core.timezone import THAI_TZ
from app.core.menu_registry import MENU_PERMISSIONS_BY_KEY
from app.services.permission_migrations import ROUND2_PERMISSION_MARKER, ROUND3_PERMISSION_MARKER, ROUND4_PERMISSION_MARKER, ROUND5_PERMISSION_MARKER, ROUND4_PERMISSIONS, backfill_round4_permissions, run_permission_migrations
from tests.test_round2_permissions import auth, set_perms, png
from tests.test_round3_permissions import hr_environment, snapshot
DATES='start_date=2026-10-10&end_date=2026-10-10'
CASES=[
    ('POST','/clock-in','attendance',{'form':{'session':'1','photo_base64':'PHOTO'}}),
    ('GET','/clock-in/today','attendance',None),
    ('GET','/clock-in/records?'+DATES,'attendance',None),
    ('POST','/clock-in/makeup','attendance',{'employee_id':1,'date':'2026-10-11','sessions':[1,2,3,4],'reason':'测试补卡'}),
    ('GET','/clock-in/makeup-count?employee_id=1&date=2026-10-11','attendance',None),
    ('GET','/clock-in/records/export?'+DATES,'attendance',None),
    ('GET','/clock-in/photos?employee_id=1&date=2026-10-10','attendance',None),
    ('GET','/attendance/calendar?'+DATES,'attendance',None),
    ('POST','/attendance/rest-days','attendance',{'employee_id':1,'rest_dates':['2026-10-12']}),
    ('GET','/attendance/rest-days','attendance',None),
    ('DELETE','/attendance/rest-days/1','attendance',None),
    ('POST','/attendance/absences','attendance',{'employee_id':1,'absence_date':'2026-10-12','reason':'未到'}),
    ('DELETE','/attendance/absences/1','attendance',None),
    ('POST','/attendance/leaves','leave',{'form':{'leave_date':'2026-10-12','leave_type':'personal','duration_type':'hours','hours':'2.3','reason':'测试请假'},'photo':True}),
    ('POST','/attendance/leaves/admin-record','leave',{'employee_id':1,'start_date':'2026-10-12','end_date':'2026-10-12','duration_type':'hours','hours':2.3}),
    ('GET','/attendance/leaves','leave',None),
    ('PUT','/attendance/leaves/1/approve','leave',None),
    ('PUT','/attendance/leaves/1/reject','leave',{'form':{'reason':'测试驳回'}}),
    ('POST','/overtime','overtime',{'employee_ids':[1],'date':'2026-10-12','start_time':'18:00','end_time':'19:00'}),
    ('POST','/overtime/3/verify','overtime',{'assignments':[{'assignment_id':3,'actual_hours':1}]}),
    ('POST','/overtime/1/confirm','overtime',None),
    ('POST','/overtime/2/dispute','overtime',{'form':{'reason':'实际工时不符'},'photo':True}),
    ('GET','/overtime','overtime',None),
    ('GET','/overtime/pending','overtime',None),
    ('GET','/overtime/monthly-hours?month=2026-10','overtime',None),
    ('GET','/overtime/limit','overtime',None),
    ('PUT','/overtime/limit','overtime',{'max_hours':60}),
    ('DELETE','/overtime/1','overtime',None),
]

@asynccontextmanager
async def attendance_environment(tmp_path,monkeypatch):
    async with hr_environment(tmp_path,monkeypatch) as (engine,factory,client):
        import app.api.v1.clock_in as clock
        import app.api.v1.attendance as attendance
        import app.api.v1.overtime as overtime
        fixed=datetime(2026,10,16,9,0,tzinfo=THAI_TZ)
        for module in (clock,attendance,overtime):
            monkeypatch.setattr(module,'thai_today',lambda:fixed.date())
            monkeypatch.setattr(module,'thai_now',lambda:fixed)
        async with factory() as db:
            await db.execute(delete(RestDay))
            db.add(Employee(id=3,warehouse_id=1,name='staff',phone='staff',user_id=3,hire_date=datetime(2026,10,1),salary_template_id=1,deduction_template_id=1))
            db.add(User(id=7,username='otherlabor',display_name='同仓其他员工',role='warehouse_labor',warehouse_id=1,password_hash='unused',extra_permissions=[]))
            db.add(UserWarehouse(user_id=7,warehouse_id=1))
            db.add(Employee(id=4,warehouse_id=1,name='同仓其他员工',user_id=7,hire_date=datetime(2026,10,1),salary_template_id=1,deduction_template_id=1))
            for eid,uid,wid in ((1,5,1),(2,6,2),(3,3,1),(4,7,1)):
                for session,h,m,s in ((1,9,0,0),(2,11,58,48),(3,13,0,0),(4,15,58,48)):
                    db.add(ClockInRecord(user_id=uid,warehouse_id=wid,clock_date=date(2026,10,10),session=session,clocked_in_at=datetime(2026,10,10,h,m,s),status='normal',photo_path=f'uploads/test-{uid}-{session}.jpg'))
            for rid,eid,wid in ((1,1,1),(2,2,2),(3,3,1),(4,4,1)):
                db.add(LeaveRequest(id=rid,employee_id=eid,warehouse_id=wid,leave_date=date(2026,10,10),leave_type='personal',duration_type='hours',hours=2.3,status='approved',notified_at=datetime(2026,10,9,9)))
                db.add(RestDay(id=rid,employee_id=eid,warehouse_id=wid,rest_date=date(2026,10,9)))
                db.add(Absence(id=rid,employee_id=eid,warehouse_id=wid,absence_date=date(2026,10,8)))
            for tid,eid,uid,wid,needs,actual in ((1,1,5,1,False,1),(2,1,5,1,True,1),(3,1,5,1,True,None),(4,4,7,1,False,1),(10,2,6,2,False,1)):
                db.add(OvertimeTask(id=tid,warehouse_id=wid,date=date(2026,10,10),start_time='18:00',end_time='19:00',hours=1,hourly_rate=0,status='已核实' if actual is not None else '待核实',needs_verification=needs,created_by=1))
                db.add(OvertimeAssignment(id=tid,overtime_id=tid,employee_id=eid,user_id=uid,actual_hours=actual,earned_amount=50,confirmed=False))
            await db.commit()
        yield engine,factory,client

async def call(client,method,path,body,uid):
    kwargs={'headers':auth(uid)}
    if isinstance(body,dict) and 'form' in body:
        form=body['form'].copy()
        if form.get('photo_base64')=='PHOTO':form['photo_base64']='data:image/png;base64,'+base64.b64encode(png()).decode()
        kwargs['data']=form
        if body.get('photo'):kwargs['files']={'file':('test.png',png(),'image/png')}
    elif body is not None:kwargs['json']=body
    return await client.request(method,'/api/v1'+path,**kwargs)

LABOR_PATHS={'/clock-in','/clock-in/today','/clock-in/records','/clock-in/photos','/attendance/calendar','/attendance/rest-days','/attendance/leaves','/overtime/1/confirm','/overtime/2/dispute','/overtime','/overtime/pending','/overtime/monthly-hours','/overtime/limit'}
def expected_status(uid,method,path):
    path=path.split('?')[0]
    labor_only=path in ('/clock-in','/clock-in/today','/overtime/1/confirm','/overtime/2/dispute','/overtime/pending')
    if uid==5:return 200 if path in LABOR_PATHS and (method=='GET' or path in ('/clock-in','/attendance/leaves','/overtime/1/confirm','/overtime/2/dispute')) else 403
    if labor_only:return 403
    if uid==2:return 200 if method=='GET' and path in ('/overtime','/overtime/monthly-hours','/overtime/limit') else 403
    if uid==3:return 200 if (method=='GET' and path in ('/attendance/calendar','/attendance/rest-days','/attendance/leaves','/overtime','/overtime/monthly-hours','/overtime/limit')) or (method=='POST' and path=='/attendance/leaves') else 403
    if method=='POST' and path=='/attendance/leaves':return 403
    return 200

@pytest.mark.parametrize('method,path,module,body',CASES,ids=[f'{m} {p}' for m,p,_,_ in CASES])
@pytest.mark.parametrize('uid,granted',[(3,False),(4,False),(3,True),(4,True),(1,False),(2,False),(5,False)],ids=['staff-deny','supervisor-deny','staff-allow','supervisor-allow','admin','super-admin','labor-no-extra-perms'])
def test_all_attendance_endpoints(tmp_path,monkeypatch,method,path,module,body,uid,granted):
    async def run():
        async with attendance_environment(tmp_path,monkeypatch) as (_,factory,client):
            if granted:await set_perms(factory,uid,[MENU_PERMISSIONS_BY_KEY[module].label])
            before=await snapshot(factory)
            response=await call(client,method,path,body,uid)
            if uid in (3,4) and not granted:
                assert response.status_code==403,response.text
                assert response.json()['detail'].startswith('无此操作权限'),response.text
            else:
                expected=expected_status(uid,method,path)
                assert response.status_code==expected,response.text
                if expected==403:assert not response.json()['detail'].startswith('无此操作权限'),response.text
                if expected==200 and method=='POST' and path=='/clock-in':
                    assert response.json()['photo_path']
                    today=await client.get('/api/v1/clock-in/today',headers=auth(uid))
                    assert today.status_code==200 and '1' in today.json()['completed']
                    again=await call(client,method,path,body,uid)
                    assert again.status_code==200 and again.json()['duplicate'] is True
                if expected==200 and path=='/overtime/1/confirm':
                    async with factory() as db:
                        assert (await db.get(OvertimeAssignment,1)).confirmed is True
                        assert (await db.get(OvertimeAssignment,4)).confirmed is False
                if expected==200 and body and isinstance(body,dict) and body.get('photo'):
                    async with factory() as db:
                        if path=='/attendance/leaves':assert (await db.get(LeaveRequest,response.json()['id'])).photo_path
                        if '/dispute' in path:
                            a=await db.get(OvertimeAssignment,2)
                            assert a.has_dispute and a.dispute_photo
            assert await snapshot(factory)==before
    asyncio.run(run())

def test_round4_inventory():
    root=Path(__file__).resolve().parents[1]/'app/api/v1'
    seen=[]
    for filename,prefix in {'clock_in':'clock-in','attendance':'attendance','overtime':'overtime'}.items():
        for node in ast.walk(ast.parse((root/(filename+'.py')).read_text())):
            if not isinstance(node,ast.AsyncFunctionDef):continue
            for d in node.decorator_list:
                if isinstance(d,ast.Call) and isinstance(d.func,ast.Attribute) and isinstance(d.func.value,ast.Name) and d.func.value.id=='router':
                    seen.append((d.func.attr.upper(),'/'+prefix+d.args[0].value))
                    default=next(v for a,v in zip(node.args.args[-len(node.args.defaults):],node.args.defaults) if a.arg=='current_user')
                    assert 'check_staff_permission' in ast.unparse(default),node.name
    assert len(seen)==28
    requested={(m,re.sub(r'/[123](?=/|$)','/{}',p.split('?')[0])) for m,p,_,_ in CASES}
    assert requested=={(m,re.sub(r'\{[^}]+\}','{}',p)) for m,p in seen}

async def business_snapshot(factory):
    async with factory() as db:
        return {model.__tablename__:[tuple(r) for r in (await db.execute(select(model.__table__).order_by(model.id))).all()]
                                        for model in (Employee,PayrollRecord,ClockInRecord,LeaveRequest,RestDay,Absence,OvertimeTask,OvertimeAssignment)}

@pytest.mark.parametrize('uid',[3,4])
def test_shared_attendance_reads(tmp_path,monkeypatch,uid):
    async def run():
        async with attendance_environment(tmp_path,monkeypatch) as (_,factory,client):
            for permission in ('考勤','请假'):
                await set_perms(factory,uid,[permission])
                for path in ('/attendance/calendar?'+DATES,'/attendance/rest-days','/attendance/leaves','/clock-in/records?'+DATES,'/clock-in/photos?employee_id=1&date=2026-10-10'):
                    response=await client.get('/api/v1'+path,headers=auth(uid))
                    expected=403 if uid==3 and path.startswith('/clock-in') else 200
                    assert response.status_code==expected,response.text
                before=await business_snapshot(factory)
                if permission=='请假':
                    for path,body in (('/clock-in/makeup',CASES[3][3]),('/attendance/rest-days',CASES[8][3]),('/attendance/absences',CASES[11][3])):
                        response=await call(client,'POST',path,body,uid)
                        assert response.status_code==403 and response.json()['detail'].startswith('无此操作权限')
                else:
                    response=await call(client,'PUT','/attendance/leaves/1/approve',None,uid)
                    assert response.status_code==403 and response.json()['detail'].startswith('无此操作权限')
                assert await business_snapshot(factory)==before
            await set_perms(factory,uid,['员工档案'])
            for path in ('/attendance/calendar','/attendance/leaves','/overtime'):
                response=await client.get('/api/v1'+path,headers=auth(uid))
                assert response.status_code==403 and response.json()['detail'].startswith('无此操作权限')
    asyncio.run(run())


def test_round4_migration_database_and_payroll_snapshot(tmp_path,monkeypatch):
    async def run():
        async with attendance_environment(tmp_path,monkeypatch) as (engine,factory,client):
            await set_perms(factory,3,None)
            await set_perms(factory,4,['到账流水','考勤','考勤'])
            async with factory() as db:
                db.add(User(id=8,username='inactive-staff',display_name='停用财务',role='staff',is_active=False,password_hash='unused',extra_permissions=['旧自定义权限']))
                db.add_all([SystemSetting(warehouse_id=1,key=marker,value='true') for marker in (ROUND2_PERMISSION_MARKER,ROUND3_PERMISSION_MARKER,ROUND5_PERMISSION_MARKER)])
                await db.commit()
            before=await business_snapshot(factory)
            async with engine.begin() as conn:
                assert await run_permission_migrations(conn)=={'round2':0,'round3':0,'round4':3,'round5':0}
            assert await business_snapshot(factory)==before
            async with factory() as db:
                values=dict((await db.execute(select(User.id,User.extra_permissions))).all())
                assert values[3]==list(ROUND4_PERMISSIONS)
                assert values[4]==['到账流水',*ROUND4_PERMISSIONS]
                assert values[8]==['旧自定义权限',*ROUND4_PERMISSIONS]
                for uid in (1,2,5,6,7):assert values[uid]==[]
                assert (await db.execute(select(func.count(SystemSetting.id)).where(SystemSetting.key==ROUND4_PERMISSION_MARKER))).scalar_one()==1
            await set_perms(factory,3,[])
            async with engine.begin() as conn:
                assert await run_permission_migrations(conn)=={'round2':0,'round3':0,'round4':0,'round5':0}
            async with factory() as db:assert (await db.get(User,3)).extra_permissions==[]
            assert await business_snapshot(factory)==before
    asyncio.run(run())


def test_round4_migration_failure_rolls_back(tmp_path,monkeypatch):
    async def run():
        async with attendance_environment(tmp_path,monkeypatch) as (engine,factory,_):
            before=await business_snapshot(factory)
            with pytest.raises(RuntimeError):
                async with engine.begin() as conn:
                    await backfill_round4_permissions(conn)
                    raise RuntimeError('模拟迁移事务失败')
            async with factory() as db:
                assert (await db.get(User,3)).extra_permissions==[]
                assert (await db.execute(select(SystemSetting.id).where(SystemSetting.key==ROUND4_PERMISSION_MARKER))).first() is None
            assert await business_snapshot(factory)==before
    asyncio.run(run())


@pytest.mark.parametrize('uid',[1,4])
def test_attendance_warehouse_isolation(tmp_path,monkeypatch,uid):
    async def run():
        async with attendance_environment(tmp_path,monkeypatch) as (_,factory,client):
            await set_perms(factory,uid,list(ROUND4_PERMISSIONS))
            before=await business_snapshot(factory)
            for method,path,body in [
                ('POST','/clock-in/makeup',{'employee_id':2,'date':'2026-10-11','sessions':[1],'reason':'越权'}),
                ('GET','/clock-in/makeup-count?employee_id=2&date=2026-10-11',None),
                ('GET','/clock-in/photos?employee_id=2&date=2026-10-10',None),
                ('POST','/attendance/leaves/admin-record',{'employee_id':2,'start_date':'2026-10-12','end_date':'2026-10-12'}),
                ('PUT','/attendance/leaves/2/approve',None),('PUT','/attendance/leaves/2/reject',None),
                ('POST','/attendance/rest-days',{'employee_id':2,'rest_dates':['2026-10-12']}),
                ('DELETE','/attendance/rest-days/2',None),
                ('POST','/attendance/absences',{'employee_id':2,'absence_date':'2026-10-12'}),
                ('DELETE','/attendance/absences/2',None),
                ('POST','/overtime',{'employee_ids':[1,2],'date':'2026-10-12','start_time':'18:00','end_time':'19:00'}),
                ('POST','/overtime/10/verify',{'assignments':[{'assignment_id':10,'actual_hours':1}]}),
                ('DELETE','/overtime/10',None),
            ]:
                response=await call(client,method,path,body,uid)
                assert response.status_code in (400,403,404),(path,response.text)
                assert await business_snapshot(factory)==before
            for path in ('/attendance/leaves','/attendance/rest-days','/attendance/calendar?'+DATES,'/clock-in/records?'+DATES,'/overtime'):
                response=await client.get('/api/v1'+path,headers={**auth(uid),'X-Warehouse-ID':'2'})
                assert response.status_code==200,response.text
                payload=response.json()
                if path.startswith('/attendance/calendar'):assert 2 not in {row['id'] for row in payload['employees']}
                elif path.startswith('/clock-in'):assert 6 not in {row['user_id'] for row in payload['records']}
                elif path=='/overtime':assert {row['warehouse_id'] for row in payload['data']}=={1}
                else:assert 2 not in {row['employee_id'] for row in payload['data']}
            from io import BytesIO
            from openpyxl import load_workbook
            response=await client.get('/api/v1/clock-in/records/export?'+DATES,headers=auth(uid))
            assert response.status_code==200,response.text
            rows=list(load_workbook(BytesIO(response.content)).active.values)
            assert not any('员工2' in str(row) for row in rows)
    asyncio.run(run())


def test_labor_only_self_and_assigned_tasks(tmp_path,monkeypatch):
    async def run():
        async with attendance_environment(tmp_path,monkeypatch) as (_,factory,client):
            before=await business_snapshot(factory)
            for eid in (2,4):
                response=await client.get(f'/api/v1/clock-in/photos?employee_id={eid}&date=2026-10-10',headers=auth(5))
                assert response.status_code==403,response.text
            for tid in (4,10):
                for action,body in (('confirm',None),('dispute',{'form':{'reason':'越权'},'photo':True})):
                    response=await call(client,'POST',f'/overtime/{tid}/{action}',body,5)
                    assert response.status_code in (400,404),response.text
            for method,path,module,body in CASES:
                if expected_status(5,method,path)==403:
                    response=await call(client,method,path,body,5)
                    assert response.status_code==403,response.text
            assert await business_snapshot(factory)==before
            for path in ('/attendance/leaves','/attendance/rest-days','/attendance/calendar?'+DATES,'/clock-in/records?'+DATES,'/overtime','/overtime/pending'):
                response=await client.get('/api/v1'+path,headers={**auth(5),'X-Warehouse-ID':'2'})
                assert response.status_code==200,response.text
                payload=response.json()
                if path.startswith('/attendance/calendar'):assert {row['id'] for row in payload['employees']}=={1}
                elif path.startswith('/clock-in'):assert {row['user_id'] for row in payload['records']}=={5}
                elif path.startswith('/overtime'):assert {row['id'] for row in payload['data']}<={1,2,3}
                else:assert {row['employee_id'] for row in payload['data']}=={1}
    asyncio.run(run())

@pytest.mark.parametrize('duration,hours,leave_type,status,work_hours,leave_days',[
    ('hours',2.3,'personal','hours_leave',3.66,.29),
    ('hours',2.3,'sick','hours_leave',3.66,.29),
    ('hours',8,'personal','leave',0,1),
    ('hours',None,'sick','leave',5.96,1),
    ('full',None,'sick','leave',5.96,1),
    ('full',None,'personal','leave',5.96,1),
    ('morning',None,'personal','half',5.96,.5),
    ('afternoon',None,'sick','half',5.96,.5),
    (None,None,None,'present',5.96,0),
])
def test_calendar_and_payroll_leave_rules_unchanged(tmp_path,monkeypatch,duration,hours,leave_type,status,work_hours,leave_days):
    async def run():
        async with attendance_environment(tmp_path,monkeypatch) as (_,factory,client):
            await set_perms(factory,4,['考勤','工资'])
            async with factory() as db:
                await db.execute(delete(PayrollRecord).where(PayrollRecord.employee_id==1))
                await db.execute(update(Employee).where(Employee.id==1).values(hire_date=datetime(2026,10,10)))
                if duration is None:await db.execute(delete(LeaveRequest).where(LeaveRequest.id==1))
                else:await db.execute(update(LeaveRequest).where(LeaveRequest.id==1).values(duration_type=duration,hours=hours,leave_type=leave_type))
                await db.commit()
            before=await snapshot(factory)
            response=await client.get('/api/v1/attendance/calendar?'+DATES,headers=auth(4))
            assert response.status_code==200,response.text
            event=next(e for e in response.json()['events'] if e['employee_id']==1)
            assert event['status']==status
            assert event['clock_hours']==5.96
            assert event['work_hours']==work_hours
            if duration=='hours' and hours==2.3:
                assert event['status_label']=='请假2.3小时'
                assert event['leave_hours']==2.3
            assert await snapshot(factory)==before
            # 显式算这一个测试员工；不是启动时或读取时触发计算。
            response=await client.post('/api/v1/payroll/calculate',headers=auth(4),json={'end_date':'2026-10-10','employee_ids':[1]})
            assert response.status_code==200,response.text
            assert response.json()['record_count']==1,response.text
            async with factory() as db:
                record=(await db.execute(select(PayrollRecord).where(PayrollRecord.employee_id==1))).scalar_one()
                detail=json.loads(record.detail)
                assert detail['work_hours']==work_hours,detail
                assert detail['leave_days']==leave_days,detail
                if duration=='hours' and hours==2.3:
                    assert detail['daily_hours'][0]['hours']==3.66
                    print('\n口径实测：',event['status_label'],'考勤工时=',event['work_hours'],'工资工时=',detail['work_hours'])
    asyncio.run(run())


def test_hourly_leave_multiple_entries_are_summed(tmp_path,monkeypatch):
    async def run():
        async with attendance_environment(tmp_path,monkeypatch) as (_,factory,client):
            await set_perms(factory,4,['考勤','工资'])
            async with factory() as db:
                await db.execute(delete(PayrollRecord).where(PayrollRecord.employee_id==1))
                await db.execute(update(Employee).where(Employee.id==1).values(hire_date=datetime(2026,10,10)))
                await db.execute(update(LeaveRequest).where(LeaveRequest.id==1).values(hours=1.1))
                db.add(LeaveRequest(employee_id=1,warehouse_id=1,leave_date=date(2026,10,10),duration_type='hours',hours=1.2,status='approved',notified_at=datetime(2026,10,9)))
                await db.commit()
            response=await client.get('/api/v1/attendance/calendar?'+DATES,headers=auth(4))
            event=next(e for e in response.json()['events'] if e['employee_id']==1)
            assert event['leave_hours']==2.3 and event['work_hours']==3.66
            response=await client.post('/api/v1/payroll/calculate',headers=auth(4),json={'end_date':'2026-10-10','employee_ids':[1]})
            assert response.status_code==200,response.text
            async with factory() as db:
                record=(await db.execute(select(PayrollRecord).where(PayrollRecord.employee_id==1))).scalar_one()
                assert json.loads(record.detail)['work_hours']==3.66
    asyncio.run(run())

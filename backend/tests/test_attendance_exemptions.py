"""Real HTTP/JWT and isolated PostgreSQL; no production records or permission mocks."""
import asyncio, json, os
from datetime import date, datetime
from pathlib import Path
import pytest
from sqlalchemy import select, text, delete
from app.models import User, UserWarehouse, Employee, SalaryTemplate, DeductionTemplate, ClockInRecord, ClockInMakeupBatch, LeaveRequest, AttendanceExemption, DataChangeHistory
from app.models.payroll import PayrollRecord
from tests.test_incoming_operations import environment, URL
from tests.test_round2_permissions import auth
from app.core.timezone import THAI_TZ

pytestmark=pytest.mark.skipif(not URL,reason='Requires explicitly isolated localhost PostgreSQL')
DAY=date(2026,10,28)
ROOT='/api/v1/attendance/exemptions'

async def seed(f):
 async with f() as db:
  db.add(SalaryTemplate(id=31,warehouse_id=1,name='合成日薪400',type='daily',amount=400))
  db.add(DeductionTemplate(id=31,warehouse_id=1,name='合成扣款模板'))
  await db.flush()
  for i in range(31,39):
   db.add(User(id=i,username=f'exempt-{i}',display_name=f'合成员工{i}',role='warehouse_labor',warehouse_id=1,password_hash='unused'))
   await db.flush();db.add(UserWarehouse(user_id=i,warehouse_id=1))
   db.add(Employee(id=i,warehouse_id=1,name=f'合成员工{i}',user_id=i,hire_date=datetime(2026,10,28),salary_template_id=31,deduction_template_id=31))
  await db.flush()
  for i,punches in [(31,[(3,13),(4,18)]),(34,[(1,9),(2,12)]),(36,[(1,10),(2,12),(3,13),(4,16)])]:
   for session,hour in punches:
    db.add(ClockInRecord(user_id=i,warehouse_id=1,clock_date=DAY,session=session,clocked_in_at=datetime(2026,10,28,hour,tzinfo=THAI_TZ),status='late_one' if i==36 and session==1 else 'normal'))
  for i,kind,hours in [(32,'full',None),(33,'morning',None),(35,'hours',2),(38,'afternoon',None)]:
   db.add(LeaveRequest(warehouse_id=1,employee_id=i,leave_date=DAY,duration_type=kind,hours=hours,status='approved',notified_at=datetime(2026,10,27,tzinfo=THAI_TZ)))
  batch=ClockInMakeupBatch(warehouse_id=1,clock_date=DAY,operator_id=1,operator_name='合成管理员',reason='旧批次',created_count=1)
  db.add(batch);await db.flush()
  db.add_all([ClockInRecord(user_id=37,warehouse_id=1,clock_date=DAY,session=1,is_makeup=True,makeup_counts_toward_limit=True,clocked_in_at=datetime(2026,10,28,9,tzinfo=THAI_TZ)),ClockInRecord(user_id=37,warehouse_id=1,clock_date=DAY,session=2,is_makeup=True,makeup_batch_id=batch.id,clocked_in_at=datetime(2026,10,28,12,tzinfo=THAI_TZ)),ClockInRecord(user_id=37,warehouse_id=1,clock_date=date(2026,10,27),session=1,is_makeup=True)])
  await db.commit()
  return batch.id

async def call(c,method,path,uid=1,code=200,**kwargs):
 r=await c.request(method,path,headers=auth(uid),**kwargs)
 assert r.status_code==code,(path,r.status_code,r.text)
 return r.json()

async def calendar(c):
 r=await call(c,'GET','/api/v1/attendance/calendar',params={'start_date':str(DAY),'end_date':str(DAY)})
 return {v['employee_id']:v for v in r['events']}

async def payrows(f):
 async with f() as db:return [tuple(r) for r in (await db.execute(select(PayrollRecord.__table__).order_by(PayrollRecord.id))).all()]

def test_28th_exemption_leave_payroll_and_revoke(tmp_path,monkeypatch):
 async def run():
  from app.api.v1 import payroll,clock_in
  monkeypatch.setattr(payroll,'thai_today',lambda:date(2026,10,29));monkeypatch.setattr(clock_in,'thai_today',lambda:date(2026,10,29))
  async with environment(tmp_path,monkeypatch) as (_,f,c):
   batch=await seed(f);result={}
   async with f() as db:
    physical=[tuple(r) for r in (await db.execute(select(ClockInRecord.__table__).where(ClockInRecord.is_makeup==False))).all()]
    leaves=[tuple(r) for r in (await db.execute(select(LeaveRequest.__table__))).all()]
   result['quota_before']=await call(c,'GET','/api/v1/clock-in/makeup-count',params={'employee_id':37,'date':str(DAY)})
   assert result['quota_before']['used_days']==2
   await call(c,'POST','/api/v1/payroll/calculate',json={'employee_ids':[31,32,33,34],'end_date':str(DAY)})
   before=await payrows(f)
   async with f() as db:
    old={r.employee_id:(r.id,r.net_pay) for r in (await db.execute(select(PayrollRecord))).scalars()}
   result['created']=await call(c,'POST',ROOT,json={'date':str(DAY),'reason':'警察查仓'})
   eid=result['created']['data']['id'];assert result['created']['voided_makeup_count']==2
   assert result['created']['detached_batch_ids']==[batch]
   assert result['created']['warning']=='该日期已有工资单，请手动重算才生效'
   assert await payrows(f)==before
   listing=await call(c,'GET',ROOT);assert listing['data'][0]['id']==eid
   after=await calendar(c);result['attendance']=after
   for i,h in {31:8,32:0,33:5,34:8,35:6,36:8,37:8,38:3}.items():
    assert after[i]['work_hours']==h and after[i]['status']=='exempt' and not after[i]['has_late'],after[i]
   result['quota_after']=await call(c,'GET','/api/v1/clock-in/makeup-count',params={'employee_id':37,'date':str(DAY)})
   assert result['quota_after']['used_days']==1
   result['payroll']={}
   for i,expected in {31:400,32:0,33:250,34:400}.items():
    changed=await call(c,'POST',f'/api/v1/payroll/{old[i][0]}/recalc',json={'void_reason':'豁免日人工重算','mode':'recalc'})
    async with f() as db:
     new=await db.get(PayrollRecord,changed['new_record_id']);detail=json.loads(new.detail)
     assert new.net_pay==expected and new.absence_fine==0 and new.late_penalty==0 and new.early_penalty==0
     result['payroll'][i]={'before':old[i][1],'after':new.net_pay,'hours':detail['work_hours'],'record_id':new.id}
   before_revoke=await payrows(f)
   result['revoked']=await call(c,'POST',f'{ROOT}/{eid}/revoke',json={'reason':'恢复正常上班'})
   assert result['revoked']['warning'] and await payrows(f)==before_revoke
   restored=await calendar(c);result['after_revoke']={i:restored[i] for i in (31,34,37)}
   assert restored[31]['work_hours']==5 and restored[34]['work_hours']==3 and restored[37]['work_hours']==0
   async with f() as db:
    assert [tuple(r) for r in (await db.execute(select(ClockInRecord.__table__).where(ClockInRecord.is_makeup==False))).all()]==physical
    assert [tuple(r) for r in (await db.execute(select(LeaveRequest.__table__))).all()]==leaves
    voids=(await db.execute(select(ClockInRecord).where(ClockInRecord.status=='voided'))).scalars().all()
    assert len(voids)==2 and all(not r.makeup_counts_toward_limit and r.makeup_batch_id is None for r in voids)
    assert (await db.get(ClockInMakeupBatch,batch)).created_count==1
    logs=(await db.execute(select(DataChangeHistory).where(DataChangeHistory.module=='attendance_exemptions'))).scalars().all()
    assert len(logs)==2 and all(r.operator_id==1 and r.warehouse_id==1 for r in logs)
   # Revoke of the old batch must not delete detached tombstones.
   await call(c,'POST',f'/api/v1/clock-in/makeup-batches/{batch}/revoke')
   async with f() as db:assert len((await db.execute(select(ClockInRecord).where(ClockInRecord.status=='voided'))).scalars().all())==2
   # Re-establishing an exemption never restores or invalidates the same row twice.
   again=await call(c,'POST',ROOT,json={'date':str(DAY),'reason':'重新豁免'})
   assert again['voided_makeup_count']==0
   result['permissions']={}
   for uid in (2,3,4,5):
    for method,path,body in [('GET',ROOT,None),('POST',ROOT,{'date':'2026-10-29','reason':'禁止'}),('POST',f"{ROOT}/{again['data']['id']}/revoke",{'reason':'禁止'})]:
     result['permissions'][f'{uid}:{method}:{path}']=await call(c,method,path,uid=uid,code=403,**({'json':body} if body else {}))
   await call(c,'POST','/api/v1/clock-in/makeup',code=400,json={'employee_id':37,'date':str(DAY),'sessions':[1],'reason':'豁免不补卡'})
   await call(c,'POST','/api/v1/clock-in/batch-makeup',code=400,json={'employee_ids':[37],'date':str(DAY),'sessions':[1],'reason':'豁免不补卡'})
   Path(os.environ['EXEMPTION_REPORT']).write_text(json.dumps(result,ensure_ascii=False,indent=2,default=str))
 asyncio.run(run())


def test_migration_uniqueness_future_cross_warehouse_and_rollback(tmp_path,monkeypatch):
 async def run():
  from app.services.attendance_exemption_migration import migrate_attendance_exemptions
  async with environment(tmp_path,monkeypatch) as (engine,f,c):
   await seed(f)
   async with f() as db:
    migration_clock_before=[tuple(r) for r in (await db.execute(select(ClockInRecord.__table__).order_by(ClockInRecord.id))).all()]
   async with engine.begin() as conn:
    await conn.execute(text('DROP TABLE attendance_exemptions'))
    await migrate_attendance_exemptions(conn);await migrate_attendance_exemptions(conn)
   async with f() as db:
    assert [tuple(r) for r in (await db.execute(select(ClockInRecord.__table__).order_by(ClockInRecord.id))).all()]==migration_clock_before
   before=await payrows(f)
   responses=await asyncio.gather(*[c.post(ROOT,headers=auth(1),json={'date':'2026-12-28','reason':'提前豁免'}) for _ in range(2)])
   assert sorted(r.status_code for r in responses)==[200,400]
   ident=next(r.json()['data']['id'] for r in responses if r.status_code==200)
   # uid7 is the other warehouse administrator in this fixture.
   await call(c,'POST',f'{ROOT}/{ident}/revoke',uid=7,code=404,json={'reason':'跨仓'})
   assert (await call(c,'GET',ROOT,uid=7))['data']==[]
   foreign=await c.post(ROOT,headers={**auth(1),'X-Warehouse-ID':'2'},json={'date':str(DAY),'reason':'伪造仓库'})
   assert foreign.status_code==403
   await call(c,'POST',ROOT,code=400,json={'date':str(DAY),'reason':'  '})
   import app.services.data_history as history
   original=history.record_history
   async def fail(*args,**kwargs):raise RuntimeError('synthetic rollback')
   monkeypatch.setattr(history,'record_history',fail)
   with pytest.raises(Exception):await c.post(ROOT,headers=auth(1),json={'date':str(DAY),'reason':'回滚样本'})
   monkeypatch.setattr(history,'record_history',original)
   async with f() as db:
    assert not (await db.execute(select(AttendanceExemption).where(AttendanceExemption.date==DAY))).first()
    assert not (await db.execute(select(ClockInRecord).where(ClockInRecord.status=='voided'))).first()
   assert await payrows(f)==before
 asyncio.run(run())


@pytest.mark.parametrize('template_type,amount', [('daily',400),('hourly',400),('monthly',12400)])
def test_all_salary_sources_leave_precedence_and_no_penalties(tmp_path,monkeypatch,template_type,amount):
 async def run():
  from app.api.v1 import payroll
  from app.models import RestDay,Absence
  monkeypatch.setattr(payroll,'thai_today',lambda:date(2026,10,29))
  async with environment(tmp_path,monkeypatch) as (_,f,c):
   await seed(f)
   async with f() as db:
    tpl=await db.get(SalaryTemplate,31);tpl.type=template_type;tpl.amount=amount
    db.add(RestDay(warehouse_id=1,employee_id=31,rest_date=DAY))
    db.add(Absence(warehouse_id=1,employee_id=36,absence_date=DAY,reason='旧标记'))
    # All approved leave kinds share the exemption source, with/without punches.
    await db.commit()
   await call(c,'POST',ROOT,json={'date':str(DAY),'reason':'全仓豁免'})
   await call(c,'POST','/api/v1/payroll/calculate',json={'employee_ids':list(range(31,39)),'end_date':str(DAY)})
   async with f() as db:
    rows=(await db.execute(select(PayrollRecord))).scalars().all()
    assert len(rows)==8
    for row in rows:
     hours={31:8,32:0,33:5,34:8,35:6,36:8,37:8,38:3}[row.employee_id]
     assert row.net_pay==hours*50 and row.absence_fine==row.late_penalty==row.early_penalty==0
     assert row.attendance_days==round(hours/8,2) and json.loads(row.detail)['work_hours']==hours
     assert json.loads(row.detail)['daily_hours'][0]['attendance']==hours/8
 asyncio.run(run())


def test_makeup_concurrency_and_full_legacy_permission_ceiling(tmp_path,monkeypatch):
 async def run():
  from app.api.v1 import clock_in
  from app.core.menu_registry import MENU_PERMISSIONS
  monkeypatch.setattr(clock_in,'thai_today',lambda:date(2026,10,29))
  async with environment(tmp_path,monkeypatch) as (_,f,c):
   await seed(f)
   async with f() as db:
    for uid in (2,3,4,5):(await db.get(User,uid)).extra_permissions=[p.label for p in MENU_PERMISSIONS]
    await db.commit()
   for uid in (2,3,4,5):await call(c,'POST',ROOT,uid=uid,code=403,json={'date':str(DAY),'reason':'旧全权限不能越权'})
   # Either makeup wins first and is voided, or exemption wins and makeup is denied.
   async def makeup():return await c.post('/api/v1/clock-in/batch-makeup',headers=auth(1),json={'date':str(DAY),'employee_ids':[38],'sessions':[1,2],'reason':'并发补卡'})
   creation,make=await asyncio.gather(c.post(ROOT,headers=auth(1),json={'date':str(DAY),'reason':'并发豁免'}),makeup())
   assert creation.status_code==200 and make.status_code in (200,400)
   async with f() as db:
    active=(await db.execute(select(ClockInRecord).where(ClockInRecord.clock_date==DAY,ClockInRecord.is_makeup==True,ClockInRecord.status!='voided'))).scalars().all()
    assert not active
 asyncio.run(run())

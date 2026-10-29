"""Real routes/auth, disposable localhost PostgreSQL, synthetic records only."""
import asyncio,json,os
from datetime import date,datetime
from pathlib import Path
import pytest
from sqlalchemy import select
from app.models import Warehouse,User,UserWarehouse,Employee
from app.models.clock_in_records import ClockInRecord
from app.core.timezone import thai_today
from tests.test_incoming_operations import environment,URL
from tests.test_round2_permissions import auth
pytestmark=pytest.mark.skipif(not URL,reason='Explicit local PostgreSQL required')

async def seed_clocks(f):
 async with f() as db:
  db.add(Warehouse(id=27,name='合成湘泰',code='SYN27'));await db.flush()
  db.add(UserWarehouse(user_id=1,warehouse_id=27))
  for uid in list(range(100,120))+[200]:
   wid=27 if uid==200 else 1
   db.add(User(id=uid,username=f'clock-{uid}',display_name=f'合成员工{uid}',role='warehouse_labor',warehouse_id=wid,password_hash='unused'))
  await db.flush()
  for uid in list(range(100,120))+[200]:
   wid=27 if uid==200 else 1
   db.add(UserWarehouse(user_id=uid,warehouse_id=wid))
   db.add(Employee(id=uid,warehouse_id=wid,user_id=uid,name=f'合成员工{uid}',status='regular',hire_date=datetime(2026,9,1)))
   days={date(2026,10,29),thai_today()} if uid!=200 else {date(2026,10,29)}
   if uid==100:days.update([date(2026,9,30),date(2026,10,27),date(2026,10,28)])
   for day in sorted(days):
    for session in range(1,5):db.add(ClockInRecord(user_id=uid,warehouse_id=wid,clock_date=day,session=session,status='normal',clocked_in_at=datetime.combine(day,datetime.min.time()),is_makeup=day==date(2026,10,28)))
  await db.commit()

def test_records_real_filters_pages_and_scope(tmp_path,monkeypatch):
 async def run():
  evidence=[]
  async with environment(tmp_path,monkeypatch) as (_,f,c):
   await seed_clocks(f)
   async with f() as db:before=[tuple(x) for x in (await db.execute(select(ClockInRecord.__table__).order_by(ClockInRecord.id))).all()]
   async def get(params,uid=1,code=200):
    r=await c.get('/api/v1/clock-in/records',headers=auth(uid),params=params);assert r.status_code==code,r.text
    b=r.json();ds=[x['clock_date'] for x in b.get('records',[])];evidence.append({'params':params,'actor':uid,'status':r.status_code,'total':b.get('total'),'page':b.get('page'),'count':len(ds),'earliest':min(ds) if ds else None,'latest':max(ds) if ds else None,'response':b});return b
   a=await get({'date':'2026-10-29'});b=await get({'date':'2026-10-29','page':2})
   assert a['total']==80 and len(a['records'])==50 and len(b['records'])==30
   assert not {x['id'] for x in a['records']} & {x['id'] for x in b['records']}
   assert {x['clock_date'] for x in a['records']+b['records']}=={'2026-10-29'}
   today=await get({});assert today['total']==80 and all(x['clock_date']==str(thai_today()) for x in today['records'])
   window=await get({'start_date':'2026-10-27','end_date':'2026-10-28'});assert window['total']==8 and {x['clock_date'] for x in window['records']}=={'2026-10-27','2026-10-28'}
   wh=await get({'date':'2026-10-29','warehouse_id':27});assert wh['total']==4 and {x['warehouse_id'] for x in wh['records']}=={27}
   await get({'warehouse_id':2},code=403)
   for key in ('employee_id','employee','user_id','user'):
    r=await get({'date':'2026-10-29',key:100});assert r['total']==4 and {x['user_id'] for x in r['records']}=={100}
   for key in ('employee_id','user_id'):assert (await get({'date':'2026-10-29',key:200}))['total']==0
   assert (await get({'date':'2026-10-29'},uid=100))['total']==4
   await get({'date':'2026-10-29','user_id':101},uid=100,code=403)
   await get({'warehouse_id':27},uid=100,code=403)
   for p in ({'page':0},{'page_size':101},{'date':'invalid'},{'employee_id':0},{'user':-1}):await get(p,code=422)
   for p in ({'date':'2026-10-29','start_date':'2026-10-28'},{'start_date':'2026-10-29','end_date':'2026-10-27'},{'month':'bad'},{'employee':101,'employee_id':100}):await get(p,code=400)
   r=await get({'month':'2026-10','page_size':100});assert all(x['clock_date'].startswith('2026-10-') for x in r['records'])
   a=await get({'month':'2026-10','employee_page':1,'page_size':100});b=await get({'month':'2026-10','employee_page':2,'page_size':100})
   assert len(a['employees'])==len(b['employees'])==5 and a['employees_total']==20
   assert not {e['id'] for e in a['employees']} & {e['id'] for e in b['employees']}
   assert all(x['employee_id'] in {e['id'] for e in a['employees']} for x in a['records'])
   r=await get({'start_date':'2026-10-27','end_date':'2026-10-29','is_makeup':True});assert r['total']==4 and all(x['is_makeup'] for x in r['records'])
   async with f() as db:assert before==[tuple(x) for x in (await db.execute(select(ClockInRecord.__table__).order_by(ClockInRecord.id))).all()]
  if os.environ.get('DATE_FILTER_EVIDENCE'):Path(os.environ['DATE_FILTER_EVIDENCE']).write_text(json.dumps(evidence,ensure_ascii=False,indent=2))
 asyncio.run(run())

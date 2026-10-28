"""真实PG：账户性质、未分类余额、权限及启动迁移；生产不动。"""
import asyncio,json,os,sys,uuid
from pathlib import Path
from datetime import datetime
import pytest
from sqlalchemy import select,text,func
from app.models import User,PaymentAccount,IncomeExpenseCategory,ExpenseRecord,AccountTransfer,IncomingFlow
from app.models.expense_fund import ExpenseFund
from scripts.seed import _migrate_account_nature
from tests.test_incoming_operations import environment,URL,body
from tests.test_round2_permissions import auth
from tests.test_cash_wallet import payment,balances
pytestmark=pytest.mark.skipif(not URL,reason='Requires explicit loopback PostgreSQL')
REPORT={}
def actual(key,value):
 REPORT[key]=value
 if os.environ.get('ACCOUNT_NATURE_TEST_REPORT'):Path(os.environ['ACCOUNT_NATURE_TEST_REPORT']).write_text(json.dumps(REPORT,ensure_ascii=False,indent=2,default=str))
def payload(**kw):return {'account_name':'性质测试','account_type':'cash','account_number':'','opening_balance':0,'opening_balance_date':'2026-10-01','currency':'THB',**kw}
async def accounts(c,uid=1):
 r=await c.get('/api/v1/accounts',headers=auth(uid));assert r.status_code==200,r.text;return r.json()
async def create(c,uid=1,**kw):
 r=await c.post('/api/v1/accounts',headers=auth(uid),json=payload(**kw));assert r.status_code==200,r.text;return r.json()['id']
async def setup(f):
 async with f() as db:
  await db.execute(text("SELECT setval(pg_get_serial_sequence('payment_accounts','id'),2,true)"))
  (await db.get(PaymentAccount,1)).opening_balance=100;(await db.get(PaymentAccount,1)).account_name='老现金企业户不按名字猜'
  for uid in (3,4):(await db.get(User,uid)).extra_permissions=['收款账户','到账流水','运营收支']
  db.add(IncomeExpenseCategory(id=1,warehouse_id=1,type='expense',name='运营支出',category_group='operating'));await db.commit()


def test_real_balances_currencies_unknown_and_fund_exclusion(tmp_path,monkeypatch):
 async def run():
  async with environment(tmp_path,monkeypatch) as (_,f,c):
   await setup(f)
   cash=await create(c,account_nature='cash',opening_balance=400)
   corp=await create(c,account_nature='corporate',account_type='bank',account_number='TEST',opening_balance=350)
   await create(c,account_nature='cash',currency='CNY',opening_balance=70);await create(c,account_nature='corporate',currency='CNY',opening_balance=30)
   r=await c.post('/api/v1/incoming',headers=auth(1),json=body(account_id=cash,amount=200));assert r.status_code==200,r.text
   for aid,value in [(cash,100),(corp,50)]:
    r=await c.post('/api/v1/income-expense/expense',headers=auth(1),data=payment(aid,amount=value));assert r.status_code==200,r.text
   async with f() as db:
    db.add(ExpenseFund(warehouse_id=1,employee_id=4,receive_date=datetime(2026,10,1),amount=10000,remaining_balance=10000,currency='THB',purpose='备用金另记台账'));await db.commit()
   result=await accounts(c);rows={a['id']:a for a in result['data']};groups=result['wallet_balances_by_currency'];thb=groups['THB']
   assert rows[cash]['current_balance']==500 and rows[corp]['current_balance']==300
   assert rows[1]['account_nature'] is rows[1]['belongs_to_owner_wallet'] is None
   assert rows[cash]['account_nature_label']=='现金户' and rows[corp]['account_nature_label']=='企业户'
   assert {a['warehouse_id'] for a in rows.values()}=={1}
   assert thb=={'cash_balance':500,'corporate_balance':300,'unclassified_balance':100,'unclassified_account_count':1,'account_count':3,'classified_wallet_balance':800,'wallet_total_complete':False,'wallet_actual_balance':None,'all_account_balance':900}
   assert groups['CNY']['wallet_actual_balance']==100 and groups['CNY']['wallet_total_complete']
   assert (groups['CNY']['cash_balance'],groups['CNY']['corporate_balance'])==(70,30)
   assert {x['value'] for x in result['nature_options']}=={'cash','corporate'}
   assert (await c.put(f'/api/v1/accounts/{cash}/toggle-status',headers=auth(1),json={})).status_code==200
   assert (await accounts(c))['wallet_balances_by_currency']==groups
   actual('real_balances',{'cash_id':cash,'corporate_id':corp,'by_currency':groups,'old_nature':None,'fund_10000_excluded':True,'inactive_money_retained':True})
 asyncio.run(run())


def test_metadata_changes_and_old_clients_do_not_change_money(tmp_path,monkeypatch):
 async def run():
  async with environment(tmp_path,monkeypatch) as (_,f,c):
   await setup(f);aid=await create(c,account_nature='cash',opening_balance=500)
   assert (await c.post('/api/v1/incoming',headers=auth(1),json=body(account_id=aid,amount=200))).status_code==200
   async def counts():
    async with f() as db:return [(await db.execute(select(func.count(m.id)))).scalar_one() for m in (IncomingFlow,ExpenseRecord,AccountTransfer)]
   before=await counts()
   for nature in ('corporate',None,'cash'):
    r=await c.put(f'/api/v1/accounts/{aid}',headers=auth(1),json=payload(account_nature=nature,opening_balance=500));assert r.status_code==200,r.text
    row=next(a for a in (await accounts(c))['data'] if a['id']==aid);assert row['account_nature']==nature and row['current_balance']==700
   assert (await c.put(f'/api/v1/accounts/{aid}',headers=auth(1),json=payload(account_name='老客户端编辑',opening_balance=500))).status_code==200
   assert next(a for a in (await accounts(c))['data'] if a['id']==aid)['account_nature']=='cash'
   assert await balances(f,aid)=={aid:700};assert await counts()==before
   old=await create(c,account_name='名字是企业现金，但未选性质',account_type='bank',account_number='N')
   assert next(a for a in (await accounts(c))['data'] if a['id']==old)['account_nature'] is None
   assert (await c.post('/api/v1/accounts',headers=auth(1),json=payload(account_nature='personal'))).status_code==422
   actual('metadata_only',{'before_balance':700,'after_balance':700,'before_counts':before,'after_counts':await counts(),'legacy_client_keeps_nature':True,'invalid_third_type':422})
 asyncio.run(run())


def test_permissions_warehouse_and_original_transfer(tmp_path,monkeypatch):
 async def run():
  async with environment(tmp_path,monkeypatch) as (_,f,c):
   await setup(f);a=await create(c,uid=1,account_nature='cash',opening_balance=500);b=await create(c,account_nature='corporate',opening_balance=300)
   assert (await accounts(c,3))['wallet_balances_by_currency']['THB']['classified_wallet_balance']==800
   restricted=await c.get('/api/v1/accounts',headers=auth(4))
   assert restricted.status_code==200 and restricted.json()['scope']=='account_selection_only'
   assert all(set(row)=={'id','warehouse_id','account_name','currency','status'} for row in restricted.json()['data'])
   assert 'wallet_balances_by_currency' not in restricted.json()
   assert (await c.post('/api/v1/accounts',headers=auth(4),json=payload(account_nature='cash'))).status_code==403
   denied={}
   for uid in (2,5):
    for method,path,data in [('GET','/accounts',None),('POST','/accounts',payload(account_nature='cash')),('PUT',f'/accounts/{a}',payload(account_nature='cash'))]:
     r=await c.request(method,'/api/v1'+path,headers=auth(uid),**({'json':data} if data else {}));assert r.status_code==403;denied[f'{uid}:{method}:{path}']=403
   assert (await c.post('/api/v1/accounts',headers=auth(3),json=payload(account_nature='cash'))).status_code==403
   for uid in (1,3,4):
    assert (await c.get('/api/v1/accounts',headers={**auth(uid),'X-Warehouse-ID':'2'})).status_code==403
    assert (await c.put('/api/v1/accounts/2',headers=auth(uid),json=payload(account_nature='cash'))).status_code==403
   async with f() as db:(await db.get(User,3)).extra_permissions=[];await db.commit()
   assert (await c.get('/api/v1/accounts',headers=auth(3))).status_code==403
   r=await c.post('/api/v1/accounts/transfers',headers=auth(1),json={'from_account_id':a,'to_account_id':b,'amount':100,'transfer_date':'2026-10-20','request_key':uuid.uuid4().hex});assert r.status_code==200,r.text
   group=(await accounts(c))['wallet_balances_by_currency']['THB'];assert (group['cash_balance'],group['corporate_balance'],group['classified_wallet_balance'])==(400,400,800)
   actual('access_transfer',{'denied':denied,'finance_create':403,'revoked':403,'foreign_header_and_id':403,'transfer':100,'after_transfer':group})
 asyncio.run(run())


def test_migration_null_old_data_savepoint_and_restart(tmp_path,monkeypatch):
 async def run():
  from sqlalchemy.ext.asyncio import create_async_engine
  async with environment(tmp_path,monkeypatch) as (engine,f,c):
   await setup(f)
   async with engine.begin() as conn:
    schema=(await conn.execute(text('SELECT current_schema()'))).scalar_one()
    await _migrate_account_nature(conn);await _migrate_account_nature(conn)
    before=(await conn.execute(text('SELECT id,account_name,account_type,opening_balance FROM payment_accounts ORDER BY id'))).all()
    await conn.execute(text('ALTER TABLE payment_accounts DROP COLUMN account_nature'));await conn.execute(text("UPDATE payment_accounts SET remark='先前步骤保留' WHERE id=1"))
    class Failing:
     def begin_nested(self):return conn.begin_nested()
     async def execute(self,statement):return await conn.execute(text('ALTER TABLE deliberately_missing_table ADD COLUMN account_nature TEXT'))
    with pytest.raises(Exception):await _migrate_account_nature(Failing())
    assert (await conn.execute(text('SELECT remark FROM payment_accounts WHERE id=1'))).scalar_one()=='先前步骤保留'
    await _migrate_account_nature(conn);await _migrate_account_nature(conn)
    assert (await conn.execute(text('SELECT id,account_name,account_type,opening_balance FROM payment_accounts ORDER BY id'))).all()==before
    assert (await conn.execute(text('SELECT count(*) FROM payment_accounts WHERE account_nature IS NOT NULL'))).scalar_one()==0
   restarted=create_async_engine(URL,connect_args={'server_settings':{'search_path':schema}})
   try:
    async with restarted.begin() as conn:await _migrate_account_nature(conn);await conn.execute(text("UPDATE payment_accounts SET account_nature='corporate' WHERE id=1"))
    async with restarted.begin() as conn:await _migrate_account_nature(conn);assert (await conn.execute(text('SELECT account_nature FROM payment_accounts WHERE id=1'))).scalar_one()=='corporate'
   finally:await restarted.dispose()
   actual('migration',{'new_repeat':2,'old_repeat':2,'restart_repeat':2,'old_null_rows':len(before),'old_amounts_unchanged':True,'savepoint_survives':True,'explicit_classification_kept':'corporate'})
 asyncio.run(run())


def test_complete_seed_new_old_and_two_restarts(tmp_path):
 async def run():
  import asyncpg
  admin=await asyncpg.connect(URL.replace('postgresql+asyncpg://','postgresql://'));name='nature_startup_'+uuid.uuid4().hex
  await admin.execute('CREATE DATABASE '+name);url=URL.rsplit('/',1)[0]+'/'+name;conn=None
  try:
   backend=Path(__file__).resolve().parents[1];env={**os.environ,'PYTHONPATH':str(backend),'DATABASE_URL':url,'SECRET_KEY':'isolated-account-nature-startup-secret','SEED_ADMIN_PASSWORD':'synthetic-nature-startup-password'};stages={}
   for stage in ('new_database','legacy_upgrade','restart','second_restart'):
    if stage=='legacy_upgrade':
     conn=await asyncpg.connect(url.replace('postgresql+asyncpg://','postgresql://'));wid=await conn.fetchval('SELECT id FROM warehouses ORDER BY id LIMIT 1')
     await conn.execute("INSERT INTO payment_accounts(warehouse_id,account_name,account_type,account_number,opening_balance,currency) VALUES($1,'老现金户不猜','cash','-',100,'THB')",wid);await conn.execute('ALTER TABLE payment_accounts DROP COLUMN account_nature')
    if stage=='restart':await conn.execute("UPDATE payment_accounts SET account_nature='cash'")
    process=await asyncio.create_subprocess_exec(sys.executable,'scripts/seed.py',cwd=backend,env=env,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.STDOUT)
    output,_=await process.communicate();(tmp_path/f'seed-{stage}.txt').write_bytes(output);assert process.returncode==0,output.decode(errors='replace')[-3000:]
    stages[stage]={'exit_code':process.returncode,'migration_message':'账户性质迁移完成'.encode() in output}
    if stage=='legacy_upgrade':assert await conn.fetchval('SELECT account_nature FROM payment_accounts') is None
   assert dict(await conn.fetchrow('SELECT account_type,opening_balance,account_nature FROM payment_accounts'))=={'account_type':'cash','opening_balance':100,'account_nature':'cash'}
   actual('full_startup',{'stages':stages,'old_null_on_upgrade':True,'balance_unchanged':100,'nature_after_restarts':'cash'})
  finally:
   if conn:await conn.close()
   await admin.execute('DROP DATABASE '+name);await admin.close()
 asyncio.run(run())


def test_current_warehouse_summary_not_all_memberships(tmp_path,monkeypatch):
 async def run():
  from app.models import UserWarehouse
  async with environment(tmp_path,monkeypatch) as (_,f,c):
   await setup(f);await create(c,account_nature='cash',opening_balance=500)
   async with f() as db:
    db.add(UserWarehouse(user_id=1,warehouse_id=2));foreign=await db.get(PaymentAccount,2);foreign.account_nature='corporate';foreign.opening_balance=9000;await db.commit()
   results={}
   for wh,expected in [('1',500),('2',9000),('all',9500)]:
    r=await c.get('/api/v1/accounts',headers={**auth(1),'X-Warehouse-ID':wh});assert r.status_code==200,r.text
    data=r.json();assert data['wallet_balances_by_currency']['THB']['classified_wallet_balance']==expected
    assert {a['warehouse_id'] for a in data['data']}==({1,2} if wh=='all' else {int(wh)})
    results[wh]={'warehouse_ids':data['warehouse_ids'],'classified_THB':expected}
   assert (await c.get('/api/v1/accounts',headers={**auth(3),'X-Warehouse-ID':'all'})).status_code==403
   actual('warehouse_scope',results)
 asyncio.run(run())

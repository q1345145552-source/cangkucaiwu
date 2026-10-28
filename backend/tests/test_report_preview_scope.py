"""Native PostgreSQL: all eight preview scopes agree with detail and existing Excel reads."""
import asyncio,json,os
from contextlib import asynccontextmanager
from datetime import date,datetime
from io import BytesIO
from pathlib import Path

import pytest
from openpyxl import load_workbook
from sqlalchemy import select,text,func,event
from app.models import (User,UserWarehouse,Customer,IncomingFlow,RechargeDeclaration,ReconciliationResult,
    ExpenseRecord,ExpenseFund,Reimbursement,PayableBill,PaymentAccount,Supplier)
from app.models.credit import CreditCustomer,CreditShipment
from tests.test_warehouse_summary import overview_environment
from tests.test_incoming_operations import URL
from tests.test_round2_permissions import auth

pytestmark=pytest.mark.skipif(not URL,reason='Requires explicit local isolated PostgreSQL')
ACTUAL={};MONTH={'month':'2026-10'}
KEYS=['recharge-summary','incoming-summary','income-expense','payable','expense-fund','reimbursement','credit','reconciliation-diff']
def actual(key,value):
 ACTUAL[key]=value
 if os.environ.get('REPORT_PREVIEW_JSON'):Path(os.environ['REPORT_PREVIEW_JSON']).write_text(json.dumps(ACTUAL,ensure_ascii=False,indent=2,default=str))

@asynccontextmanager
async def report_environment(tmp_path,mp):
 async with overview_environment(tmp_path,mp) as (engine,f,c):
  async with f() as db:
   db.add_all([Customer(id=6,warehouse_id=1,customer_code='CNY-A',company_name='人民币客户A',default_currency='CNY'),Customer(id=7,warehouse_id=2,customer_code='CNY-B',company_name='人民币客户B',default_currency='CNY')])
   db.add_all([Supplier(id=1,warehouse_id=1,name='供应商A'),Supplier(id=2,warehouse_id=2,name='供应商B')])
   await db.flush()
   for wid,decl,paid,cny_decl,cny_paid,fund,bill,reimb in [(1,103,100,51,50,60,500,120),(2,204,200,72,70,90,800,180)]:
    declaration=(await db.execute(select(RechargeDeclaration).where(RechargeDeclaration.warehouse_id==wid))).scalar_one()
    declaration.amount=decl
    db.add_all([RechargeDeclaration(id=10+wid,warehouse_id=wid,customer_id=5+wid,declare_date=datetime(2026,10,20),amount=cny_decl,currency='CNY',declarer_id=1),
     ExpenseFund(id=wid,warehouse_id=wid,employee_id=1 if wid==1 else 7,receive_date=datetime(2026,9,1),amount=fund,remaining_balance=fund,currency='THB',status='active',purpose='当前备用金'),
     ExpenseFund(id=10+wid,warehouse_id=wid,employee_id=1 if wid==1 else 7,receive_date=datetime(2026,9,1),amount=fund/10,remaining_balance=fund/10,currency='CNY',status='active',purpose='当前人民币备用金'),
     PayableBill(id=wid,warehouse_id=wid,supplier_id=wid,bill_number='BILL-'+str(wid),bill_date=datetime(2026,10,1),due_date=datetime(2026,10,25),amount=bill,paid_amount=0,currency='THB',status='pending'),
     PayableBill(id=10+wid,warehouse_id=wid,supplier_id=wid,bill_number='CNY-BILL-'+str(wid),bill_date=datetime(2026,10,1),due_date=datetime(2026,10,25),amount=bill/10,paid_amount=0,currency='CNY',status='pending'),
     Reimbursement(id=wid,warehouse_id=wid,employee_id=1 if wid==1 else 7,submit_date=datetime(2026,10,20),total_amount=reimb,currency='THB',status='pending'),
     Reimbursement(id=10+wid,warehouse_id=wid,employee_id=1 if wid==1 else 7,submit_date=datetime(2026,10,20),total_amount=reimb/10,currency='CNY',status='pending'),
     CreditCustomer(id=wid,warehouse_id=wid,customer_id=wid,currency='THB',credit_limit=1000,status='active'),
     CreditCustomer(id=10+wid,warehouse_id=wid,customer_id=5+wid,currency='CNY',credit_limit=1000,status='active')])
    await db.flush()
    for cur,did,customer_id,shipment,credit_id in [('THB',declaration.id,wid,150 if wid==1 else 280,wid),('CNY',10+wid,5+wid,61 if wid==1 else 92,10+wid)]:
     flow=(await db.execute(select(IncomingFlow).where(IncomingFlow.warehouse_id==wid,IncomingFlow.currency==cur))).scalar_one()
     db.add(ReconciliationResult(warehouse_id=wid,reconciliation_month='2026-10',declaration_id=did,flow_id=flow.id,match_status='matched',amount_diff=(decl-paid) if cur=='THB' else (cny_decl-cny_paid)))
     db.add(CreditShipment(credit_customer_id=credit_id,ship_date=datetime(2026,10,5),amount=shipment,order_count=1,currency=cur,status='active'))
   # Other month and inactive/unauthorised warehouses must never enter October's selected scope.
   db.add_all([IncomingFlow(warehouse_id=1,account_id=1,received_date=datetime(2026,9,20),amount=9000,currency='THB',entrant_id=1),
    ExpenseRecord(warehouse_id=1,category_id=1,account_id=1,expense_date=datetime(2026,9,20),amount=900,currency='THB'),
    IncomingFlow(warehouse_id=4,received_date=datetime(2026,10,20),amount=7777,currency='THB',entrant_id=1),
    IncomingFlow(warehouse_id=5,received_date=datetime(2026,10,20),amount=8888,currency='THB',entrant_id=1)])
   await db.commit()
  yield engine,f,c

async def get(c,path,warehouse='1',uid=1,**params):
 return await c.get('/api/v1/reports/'+path,headers={**auth(uid),'X-Warehouse-ID':str(warehouse)},params={**MONTH,**params})

def test_selected_all_currency_details_exports_and_no_writes(tmp_path,monkeypatch):
 async def run():
  async with report_environment(tmp_path,monkeypatch) as (engine,f,c):
   before=[]
   def trace(conn,cursor,statement,*args):
    if statement.lstrip().upper().startswith(('INSERT','UPDATE','DELETE')):before.append(statement)
   event.listen(engine.sync_engine,'before_cursor_execute',trace)
   responses={};exports={};sequence=[]
   try:
    for warehouse,income,expense in [('1',100,20),('2',200,40),('1',100,20),('all',300,60)]:
     r=await get(c,'previews',warehouse);assert r.status_code==200,r.text
     preview=r.json();p=preview['previews'];sequence.append({"warehouse":warehouse,"wallet":p["income-expense"]});assert p['income-expense']['income_by_currency']['THB']==income;assert p['income-expense']['expense_by_currency']['THB']==expense
     assert p['income-expense']['income_by_currency']['CNY']==({'1':50,'2':70,'all':120}[warehouse])
     assert preview['warehouse_ids']==([1,2,3] if warehouse=='all' else [int(warehouse)])
     for key in KEYS:
      detail=await get(c,key,warehouse);assert detail.status_code==200,(key,detail.text);data=detail.json()
      if key in ('recharge-summary','incoming-summary','reimbursement'):assert p[key]['preview_by_currency']==data['total_amount_by_currency']
      elif key=='income-expense':
       assert p[key]['income_by_currency']==data['income_by_currency'];assert p[key]['expense_by_currency']==data['expense_by_currency']
      elif key=='payable':assert p[key]['preview_by_currency']==data['total_pending_by_currency']
      elif key=='expense-fund':assert p[key]['preview_by_currency']==data['in_transit_total_by_currency']
      elif key=='credit':assert p[key]['preview_by_currency']==data['total_debt_by_currency']
      else:assert p[key]['preview_by_currency']==data['total_diff_by_currency'];assert p[key]['count']==data['total_count']
      excel=await get(c,key,warehouse,format='excel');assert excel.status_code==200,(key,excel.text)
      if os.environ.get('REPORT_PREVIEW_EXPORT_DIR'):
       folder=Path(os.environ['REPORT_PREVIEW_EXPORT_DIR']);folder.mkdir(parents=True,exist_ok=True);(folder/(warehouse+'_'+key+'.xlsx')).write_bytes(excel.content)
      rows=list(load_workbook(BytesIO(excel.content),data_only=True).active.values)
      assert len(rows)==len(data['data'])+1,(key,rows,data)
      expected=[[item.get(h) if item.get(h)!='' else None for h in rows[0]] for item in data['data']]
      assert [list(row) for row in rows[1:]]==expected,(key,rows,expected)
      exports[warehouse+':'+key]=[list(row) for row in rows]
     responses[warehouse]=preview
    assert not before,before
   finally:event.remove(engine.sync_engine,'before_cursor_execute',trace)
   actual('switching',{'responses':responses,'sequence':sequence,'exports':exports,'write_queries':len(before)})
 asyncio.run(run())

def test_roles_membership_revoke_forged_scope_and_month(tmp_path,monkeypatch):
 async def run():
  async with report_environment(tmp_path,monkeypatch) as (_,f,c):
   results=[]
   for uid in (1,3,4):
    for wh in (1,2):
     for path in ['previews',*KEYS]:
      r=await get(c,path,wh,uid);assert r.status_code==(403 if uid==4 else 200),(uid,wh,path,r.text);results.append({'user':uid,'warehouse':wh,'path':path,'status':r.status_code})
    for wh in ('5','4','999','garbage'):
     for path in ['previews',*KEYS]:
      r=await get(c,path,wh,uid);assert r.status_code==403,(uid,wh,path,r.text);results.append({'user':uid,'warehouse':wh,'path':path,'status':r.status_code,'body':r.json()})
    for path in ['previews',*KEYS]:
     r=await get(c,path,'1',uid,warehouse_id=2);assert r.status_code==403,(uid,path,r.text);results.append({'user':uid,'warehouse':1,'query_warehouse':2,'path':path,'status':r.status_code,'body':r.json()})
    if uid in (3,4):assert (await get(c,'previews','all',uid)).status_code==403
   for uid in (2,5):
    for path in ['previews',*KEYS]:assert (await get(c,path,1,uid)).status_code==403
   september=await get(c,'previews',1,month='2026-09');assert september.status_code==200,september.text
   assert september.json()['previews']['income-expense']['income_by_currency']=={'THB':9000}
   assert september.json()['previews']['income-expense']['expense_by_currency']['THB']==960  # Sept expense900 plus original fund disbursement60.
   assert september.json()['previews']['recharge-summary']['preview_by_currency']=={}
   assert september.json()['previews']['expense-fund']['preview_by_currency']=={'CNY':6,'THB':60}
   for params in [{'month':'2026-13'},{'start_date':'2026-11-01','end_date':'2026-10-01'},{'year':'2026'}]:
    assert (await get(c,'previews',1,**params)).status_code==400
   async with f() as db:
    (await db.get(User,3)).extra_permissions=[];await db.commit()
   for path in ['previews',*KEYS]:
    r=await get(c,path,1,3);assert r.status_code==403 and '无此操作权限' in r.text
   async with f() as db:
    (await db.get(User,4)).extra_permissions=['报表中心']
    for membership in (await db.execute(select(UserWarehouse).where(UserWarehouse.user_id==4,UserWarehouse.warehouse_id==2))).scalars():await db.delete(membership)
    await db.commit()
   for path in ['previews',*KEYS]:
    r=await get(c,path,2,4);assert r.status_code==403;results.append({'user':4,'warehouse':2,'path':path,'status':r.status_code,'body':r.json(),'membership_revoked':True})
   actual('permissions_and_month',{'office_single_warehouse':200,'invalid_warehouse_and_query_mismatch':403,'office_all':403,'labor_and_business_super':403,'old_token_permission_revoke':403,'old_token_membership_revoke':403,'september':september.json(),'requests':results})
 asyncio.run(run())

def test_business_filters_and_unknown_difference_currency_keep_existing_wallet(tmp_path,monkeypatch):
 async def run():
  from app.models.supplier import PurchaseOrder
  async with report_environment(tmp_path,monkeypatch) as (_,f,c):
   before=(await get(c,'income-expense')).json()
   async with f() as db:
    db.add(PurchaseOrder(id=99,warehouse_id=1,supplier_id=1,order_number='NOT-CONFIRMED',total_amount=999,items=[],currency='THB',status='pending'))
    await db.flush()
    db.add_all([PayableBill(id=99,warehouse_id=1,supplier_id=1,purchase_order_id=99,bill_number='UNCONFIRMED',bill_date=datetime(2026,10,1),due_date=datetime(2026,10,20),amount=999,currency='THB',status='pending'),
     PayableBill(id=100,warehouse_id=1,supplier_id=1,bill_number='VOIDED',bill_date=datetime(2026,10,1),due_date=datetime(2026,10,20),amount=888,currency='THB',status='voided'),
     ExpenseFund(id=99,warehouse_id=1,employee_id=1,receive_date=datetime(2026,9,1),amount=999,remaining_balance=999,currency='THB',status='closed',purpose='非有效余额不混入'),
     ReconciliationResult(warehouse_id=1,reconciliation_month='2026-10',amount_diff=9,match_status='unmatched')])
    await db.commit()
   preview=(await get(c,'previews')).json()['previews']
   payable=(await get(c,'payable')).json();fund=(await get(c,'expense-fund')).json();diff=(await get(c,'reconciliation-diff')).json()
   assert preview['payable']['preview_by_currency']==payable['total_pending_by_currency']=={'CNY':50,'THB':500}
   assert preview['expense-fund']['preview_by_currency']==fund['in_transit_total_by_currency']=={'CNY':6,'THB':60}
   assert preview['reconciliation-diff']['preview_by_currency']==diff['total_diff_by_currency']=={'THB':3,'CNY':1,'UNKNOWN':9}
   assert diff['total_diff'] is None and any(row['币种']=='UNKNOWN' for row in diff['data'])
   assert (await get(c,'income-expense')).json()==before
   actual('special_business_filters',{'payable':payable,'fund':fund,'differences':diff,'wallet_unchanged':True})
 asyncio.run(run())

def test_record_original_preview_before_and_after_without_reopening_routes(tmp_path,monkeypatch):
 async def run():
  import ast,subprocess
  from fastapi import Request
  from fastapi.security import HTTPAuthorizationCredentials
  from app.core.permissions import get_current_user
  import app.api.v1.reports as current
  root=Path(__file__).resolve().parents[2]
  source=subprocess.check_output(['git','show','1fa823c:backend/app/api/v1/reports.py'],cwd=root,text=True)
  parsed=ast.parse(source)
  nodes=[n for n in parsed.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name in ('_date_cond','_apply_date','report_previews')]
  for node in nodes:node.decorator_list=[]
  namespace=dict(vars(current));exec(compile(ast.Module(body=nodes,type_ignores=[]),'original_report_previews_1fa823c','exec'),namespace)
  # Read the exact old handler in an isolated namespace; never register it or replace the live protected route.
  old=namespace['report_previews'];result=[]
  async with report_environment(tmp_path,monkeypatch) as (_,f,c):
   for uid in (3,1):
    for wh in (1,2):
     async with f() as db:
      from app.main import app
      registered=next(r for r in app.routes if getattr(r,'path',None)=='/api/v1/reports/previews')
      request=Request({'type':'http','route':registered,'method':'GET','path':'/api/v1/reports/previews','headers':[(b'x-warehouse-id',str(wh).encode())]})
      credentials=HTTPAuthorizationCredentials(scheme='Bearer',credentials=auth(uid)['Authorization'].split()[1])
      user=await get_current_user(request,credentials,db)
      before=await old(start_date='2026-10-01',end_date='2026-10-31',current_user=user,db=db)
     after=(await get(c,'previews',wh,uid)).json()
     expected_before=300 if uid==3 else 8077  # Old admin scope also included its inactive warehouse's7777.
     assert before['previews']['income-expense']['income_by_currency']['THB']==expected_before
     assert before['previews']['income-expense']['expense_by_currency']['THB']==60
     assert after['previews']['income-expense']['income_by_currency']['THB']==(100 if wh==1 else 200)
     assert after['previews']['income-expense']['expense_by_currency']['THB']==(20 if wh==1 else 40)
     result.append({'user':uid,'selected_warehouse':wh,'before':before,'after':after})
   assert (await c.get('/api/v1/reports/operations',headers=auth(1))).status_code==403
   actual('exact_original_handler_before_after',result)
 asyncio.run(run())

"""Inventory of registered date-query GET routes and real local requests.
Response evidence distinguishes successful data checks from disabled/empty routes.
"""
import asyncio,inspect,json,os
from pathlib import Path
from datetime import date,datetime
import pytest
from app.main import app
from app.models import Employee, Supplier, PayableBill
from app.models.attendance import LeaveRequest,RestDay
from app.models.clock_in_records import ClockInMakeupBatch
from app.models.attendance_exemption import AttendanceExemption
from app.models.expense_fund import ExpenseFund,ExpenseFundItem
from app.models.recharge import RechargeDeclaration,IncomingFlow,ReconciliationResult
from app.models.reimbursement import Reimbursement
from app.models.audit_log import AuditLog
from app.models.data_change_history import DataChangeHistory
from app.models.cash_advance import CashAdvance
from app.models.income_expense import IncomeExpenseCategory,IncomeRecord,ExpenseRecord
from app.models.credit import CreditCustomer,CreditShipment
from tests.test_incoming_operations import environment,URL
from tests.test_round2_permissions import auth
pytestmark=pytest.mark.skipif(not URL,reason='Explicit isolated local PostgreSQL required')

async def seed_dates(f):
 async with f() as db:
  db.add(Supplier(id=1,warehouse_id=1,name='合成供应商'))
  db.add(Employee(id=1,warehouse_id=1,user_id=5,name='合成员工',status='regular',hire_date=datetime(2026,9,1)))
  db.add(ExpenseFund(id=1,warehouse_id=1,employee_id=5,receive_date=datetime(2026,9,1),amount=1000,remaining_balance=1000,purpose='合成'))
  db.add(IncomeExpenseCategory(id=1,warehouse_id=1,type='income',name='合成收入'))
  db.add(IncomeExpenseCategory(id=2,warehouse_id=1,type='expense',name='合成支出'))
  db.add(CreditCustomer(id=1,warehouse_id=1,customer_id=1,credit_limit=1000))
  await db.flush()
  for i,day in enumerate([date(2026,10,28),date(2026,10,29),date(2026,10,30)],1):
   when=datetime.combine(day,datetime.min.time()).replace(hour=15,minute=30)
   db.add(PayableBill(id=i,warehouse_id=1,supplier_id=1,bill_number=f'SYN{i}',bill_date=when,due_date=when,amount=i))
   db.add(LeaveRequest(id=i,warehouse_id=1,employee_id=1,leave_date=day,status='pending'))
   db.add(RestDay(id=i,warehouse_id=1,employee_id=1,rest_date=day))
   db.add(ClockInMakeupBatch(id=i,warehouse_id=1,clock_date=day,operator_id=1,operator_name='合成管理员',reason='合成'))
   db.add(AttendanceExemption(id=i,warehouse_id=1,date=day,reason='合成',created_by=1,created_by_name='合成管理员'))
   db.add(ExpenseFundItem(id=i,fund_id=1,expense_date=when,category='合成',amount=i,description='合成'))
   db.add(RechargeDeclaration(id=i,warehouse_id=1,customer_id=1,declare_date=when,amount=i,declarer_id=1,screenshot='synthetic.jpg'))
   db.add(IncomingFlow(id=i,warehouse_id=1,received_date=when,amount=i,entrant_id=1,account_id=1,customer_id=1))
   db.add(Reimbursement(id=i,warehouse_id=1,employee_id=5,submit_date=when,total_amount=i))
   db.add(AuditLog(id=i,warehouse_id=1,user_id=1,action_type='create',module='employee',created_at=when))
   db.add(DataChangeHistory(id=i,warehouse_id=1,module='employee',record_id=1,operator_id=1,operation_type='create',created_at=when))
   db.add(CashAdvance(id=i,warehouse_id=1,payer_id=5,payer_name='合成',advance_date=day,amount=i,purpose='other',status='confirmed',created_by_id=1,created_by_name='合成'))
   db.add(IncomeRecord(id=i,warehouse_id=1,category_id=1,account_id=1,customer_id=1,amount=i,income_date=when))
   db.add(ExpenseRecord(id=i,warehouse_id=1,category_id=2,account_id=1,amount=i,expense_date=when))
   db.add(CreditShipment(id=i,credit_customer_id=1,ship_date=when,amount=i,entrant_id=1))
   db.add(ReconciliationResult(id=i,warehouse_id=1,reconciliation_month='2026-10',created_at=when))
  await db.commit()


def test_registered_date_routes_actual_requests(tmp_path,monkeypatch):
 async def run():
  evidence=[]
  async with environment(tmp_path,monkeypatch) as (_,f,c):
   await seed_dates(f)
   from tests.test_clock_record_date_filters import seed_clocks
   await seed_clocks(f)
   for route in app.routes:
    if 'GET' not in getattr(route,'methods',set()) or not hasattr(route,'dependant'):continue
    names={x.alias for x in route.dependant.query_params};dates=names & {'date','start_date','end_date','date_from','date_to'}
    if not dates:continue
    params={key:'2026-10-29' for key in ( {'date'} if 'date' in dates else dates)}
    if 'employee_id' in names and route.path.endswith(('/photos','/makeup-count')):params['employee_id']=100
    path=route.path.replace('{customer_id}','1').replace('{credit_id}','1')
    try:
     r=await c.get(path,headers=auth(1),params=params)
     data=r.json() if 'application/json' in r.headers.get('content-type','') else {'download_bytes':len(r.content), 'rows': spreadsheet_rows(r.content)}
     evidence.append({'path':route.path,'parameters':params,'status':r.status_code,'response':data})
    except Exception as e:evidence.append({'path':route.path,'parameters':params,'error':str(e)[:1000]})
  out=os.environ.get('DATE_SWEEP_EVIDENCE')
  if out:Path(out).write_text(json.dumps(evidence,ensure_ascii=False,indent=2,default=str))
  verify_responses(evidence)
  if out:Path(out).write_text(json.dumps(evidence,ensure_ascii=False,indent=2,default=str))
  assert not [e for e in evidence if 'error' in e or e['status']>=500],[(e['path'],e.get('error',e.get('status'))) for e in evidence if 'error' in e or e['status']>=500]
 asyncio.run(run())


def test_end_day_includes_afternoon(tmp_path,monkeypatch):
 async def run():
  async with environment(tmp_path,monkeypatch) as (_,f,c):
   await seed_dates(f)
   r=await c.get('/api/v1/expense-fund/review/pending',headers=auth(1),params={'start_date':'2026-10-29','end_date':'2026-10-29'})
   assert r.status_code==200,r.text
   assert r.json()['total']==1,r.text
   r=await c.get('/api/v1/reconciliation/unmatched',headers=auth(1),params={'start_date':'2026-10-29','end_date':'2026-10-29'})
   assert r.status_code==200,r.text
   assert [x['id'] for x in r.json()['declarations']]==[2],r.text
   assert [x['id'] for x in r.json()['incoming']]==[2],r.text
 asyncio.run(run())


def spreadsheet_rows(content):
 from io import BytesIO
 from openpyxl import load_workbook
 return [list(row) for row in load_workbook(BytesIO(content),read_only=True).active.values]


def verify_responses(evidence):
 by_path={e['path'].removeprefix('/api/v1'):e for e in evidence}
 # Each dated list must contain a real positive sample and exclude both neighbours.
 date_fields={
  '/reconciliation/results':'created_at','/income-expense/income':'date',
  '/income-expense/expense':'date','/income-expense/ledger':'date',
  '/expense-fund/review/pending':'expense_date','/reimbursement':'submit_date',
  '/payable':'bill_date','/payable/batch-export':'due_date','/reports/cost-funds-debt/costs':'date',
  '/reports/cost-funds-debt/flows':'date','/reports/cost-funds-debt/advances':'advance_date',
  '/reports/recharge-summary':'日期','/reports/incoming-summary':'日期',
  '/reports/income-expense':'日期','/reports/reimbursement':'日期',
  '/settings/logs':'created_at','/attendance/leaves':'leave_date',
  '/attendance/rest-days':'rest_date','/attendance/exemptions':'date',
  '/clock-in/makeup-batches':'date','/history':'created_at','/cash-advances':'advance_date',
 }
 for path,field in date_fields.items():
  r=by_path[path];assert r['status']==200,r
  rows=r['response']['data'];assert rows,(path,r)
  assert all(str(x[field]).startswith('2026-10-29') for x in rows),(path,rows)
  r['verification']='positive and adjacent-day exclusion'
 for key in ['declarations','incoming']:
  assert [x['id'] for x in by_path['/reconciliation/unmatched']['response'][key]]==[2]
 by_path['/reconciliation/unmatched']['verification']='afternoon included; adjacent days excluded'
 for path in ['/customers/{customer_id}/receivables','/credit/shipments','/reports/operations']:
  assert by_path[path]['status']==403
  by_path[path]['verification']='existing disabled feature; not bypassed'
 r=by_path['/clock-in/records']['response'];assert r['total']==80 and {x['clock_date'] for x in r['records']}=={'2026-10-29'}
 for path in ['/reconciliation/export','/clock-in/records/export','/income-expense/income/export','/income-expense/expense/export','/income-expense/ledger/export','/reimbursement/export','/history/export']:
  rows=by_path[path]['response']['rows'];text=str(rows)
  assert '2026-10-29' in text and '2026-10-28' not in text and '2026-10-30' not in text,(path,text)
  by_path[path]['verification']='parsed workbook dates checked'

 for path in ['/dashboard/warehouse-summary','/income-expense/monthly-summary','/income-expense/operating-dashboard']:
  body=by_path[path]['response'];totals=body.get('totals',body)
  assert totals['total_income']==4 and totals['total_expense']==2,(path,body)
  by_path[path]['verification']='single-day seeded totals checked'
 assert by_path['/payable/stats']['response']['month_total']==2
 assert by_path['/reports/payable']['response']['total_count']==1
 for key in ['recharge-summary','incoming-summary','reimbursement','payable']:
  assert by_path['/reports/previews']['response']['previews'][key]['count']==1
 ships=by_path['/credit/{credit_id}/detail']['response']['shipments'];assert len(ships)==1 and ships[0]['ship_date'].startswith('2026-10-29')
 by_path['/credit/{credit_id}/detail']['verification']='dated shipment list filtered; current balance remains cumulative'
 events=by_path['/attendance/calendar']['response']['events'];assert events and all(e['date']=='2026-10-29' for e in events)
 # Reconciliation reports explicitly report by month, and balance previews by current position.
 assert by_path['/reports/reconciliation-diff']['response']['total_count']==3
 by_path['/reports/reconciliation-diff']['verification']='existing month-based report, all three October rows retained'

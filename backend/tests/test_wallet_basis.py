import asyncio, base64, json, tempfile
from pathlib import Path
from contextlib import asynccontextmanager
from datetime import date, datetime
from pytest import MonkeyPatch
from sqlalchemy import delete, event
from app.core.timezone import THAI_TZ
from app.models import PaymentAccount, RechargeDeclaration, User
from app.models.recharge import IncomingFlow, ReconciliationResult
from app.models.income_expense import IncomeRecord, IncomeExpenseCategory
from app.models.payable import PayableBill
from app.models.supplier import Supplier
from app.models.credit import CreditCustomer, CreditShipment
from tests.test_round2_permissions import auth, set_perms, png
from tests.test_round3_permissions import hr_environment
from tests.test_cash_advance_references import snapshot

OUT=Path('/tmp/wallet-policy-results')
OUT.mkdir(exist_ok=True)
RANGE={'start_date':'2026-10-01','end_date':'2026-10-31'}
report={'head':'wallet-policy-fix','environment':'isolated SQLite temporary databases and synthetic data; production untouched', 'cases':{}}

def fixed(y,m,d):return datetime(y,m,d,12,0,tzinfo=THAI_TZ)

async def get(c,path,**params):
 r=await c.get('/api/v1'+path,headers=auth(1),params=params)
 assert r.status_code==200,(path,r.status_code,r.text)
 return r.json()

async def post(c,path,**kwargs):
 r=await c.post('/api/v1'+path,headers=auth(1),**kwargs)
 assert r.status_code==200,(path,r.status_code,r.text)
 return r.json()

def amt(rows,cur='THB'):
 return next((r['amount'] for r in rows if r['currency']==cur),0)

async def views(c,**dates):
 dates=dates or RANGE
 ledger=await get(c,'/income-expense/ledger',**dates)
 company=await get(c,'/income-expense/ledger',**dates,flow_scope='company')
 old=await get(c,'/reports/income-expense',**dates)
 three=await get(c,'/reports/cost-funds-debt',**dates)
 thb=next(b for b in three['currencies'] if b['currency']=='THB')
 return {'ledger_income':ledger['income_by_currency'].get('THB',0),'ledger_expense':ledger['expense_by_currency'].get('THB',0),
  'company_income':company['income_by_currency'].get('THB',0),'company_expense':company['expense_by_currency'].get('THB',0),
  'old_report_income':old['total_income_by_currency'].get('THB',0),'old_report_expense':old['total_expense_by_currency'].get('THB',0),
  'unified_cost':thb['costs']['total'],'company_outflow':thb['reconciliation']['company_outflow'],
  'cash_report_close':next((a['closing_balance'] for a in thb['funds']['data'] if a['account_id']==1),None),
  'cash_current_api':next((a['current_balance'] for a in (await get(c,'/accounts'))['data'] if a['id']==1),None)}

@asynccontextmanager
async def clean(path,mp):
 path.mkdir(exist_ok=True)
 async with hr_environment(path,mp) as (engine,f,c):
  @event.listens_for(engine.sync_engine,'connect')
  def functions(conn,_):conn.create_function('to_char',2,lambda value,fmt:str(value)[:7] if value else None)
  await engine.dispose()
  import app.api.v1.dashboard as dashboard
  mp.setattr(dashboard,'thai_today',lambda:date(2026,10,20))
  async with f() as db:
   await db.execute(delete(RechargeDeclaration))
   (await db.get(PaymentAccount,1)).opening_balance=10000
   db.add_all([IncomeExpenseCategory(id=80,warehouse_id=1,type='income',name='业务收款',category_group='operating'),
    IncomeExpenseCategory(id=81,warehouse_id=1,type='expense',name='运营费用',category_group='operating'),
    IncomeExpenseCategory(id=82,warehouse_id=1,type='income',name='其他收入',category_group='other')])
   await db.commit()
  yield f,c

async def scenario_income(path,mp):
 async with clean(path,mp) as (f,c):
  async with f() as db:
   db.add(RechargeDeclaration(id=1,warehouse_id=1,customer_id=1,declare_date=datetime(2026,10,20),amount=1000, currency='THB',declarer_id=1))
   await db.commit()
  before=await snapshot(f)
  first=await views(c)
  cockpit=await get(c,'/dashboard/cockpit')
  operating=await get(c,'/income-expense/operating-dashboard',**RANGE)
  assert await snapshot(f)==before
  assert first['company_income']==first['ledger_income']==first['old_report_income']==0
  assert amt(cockpit['finance']['month']['income'])==0 and operating['income_by_currency'].get('THB',0)==0
  report['cases']['unreceived_declaration']={'views':first,'dashboard_income':0,'operating_income':0,'expected_wallet_income':0}
  async with f() as db:
   (await db.get(RechargeDeclaration,1)).match_status='matched'
   db.add(IncomingFlow(id=1,warehouse_id=1,received_date=datetime(2026,10,20),amount=1000,currency='THB',entrant_id=1,match_status='matched'))
   db.add(ReconciliationResult(warehouse_id=1,reconciliation_month='2026-10',declaration_id=1,flow_id=1,match_status='manual_matched'))
   await db.commit()
  matched=await views(c)
  assert matched['ledger_income']==matched['company_income']==matched['old_report_income']==1000
  report['cases']['matched_declaration_and_receipt_double_count']={'views':matched,'expected_wallet_income':1000}

async def scenario_manual(path,mp):
 async with clean(path,mp) as (f,c):
  await post(c,'/income-expense/income',json={'category_id':80,'account_id':1,'amount':500,'currency':'THB','income_date':'2026-10-20'})
  await post(c,'/income-expense/expense',data={'category_id':'81','account_id':'1','amount':'200','currency':'THB','expense_date':'2026-10-20'})
  v=await views(c)
  cockpit=await get(c,'/dashboard/cockpit')
  assert v['cash_current_api']==v['cash_report_close']==10300
  assert amt(cockpit['finance']['month']['income'])==500
  report['cases']['manual_receipt_payment_balance_and_dashboard']={'views':v,'dashboard_income':500,'expected_wallet_income':500,'expected_cash_balance':10300}

async def scenario_payable(path,mp):
 import app.services.payable_payment as api
 async with clean(path,mp) as (f,c):
  async with f() as db:
   db.add(Supplier(id=1,warehouse_id=1,name='测试供应商'))
   db.add(PayableBill(id=1,warehouse_id=1,supplier_id=1,bill_number='UNPAID-1000',bill_date=datetime(2026,10,1),due_date=datetime(2026,12,1),amount=1000))
   await db.commit()
  v=await views(c);cockpit=await get(c,'/dashboard/cockpit')
  assert amt(cockpit['finance']['month']['expense'])==0 and v['unified_cost']==v['company_expense']==0
  report['cases']['unpaid_bill_in_dashboard_headline']={'views':v,'dashboard_expense':amt(cockpit['finance']['month']['expense']),
   'dashboard_procurement_card':amt(cockpit['finance']['procurement']['expense']),'expected_wallet_expense':0}
  mp.setattr(api,'thai_now',lambda:fixed(2026,10,20))
  r=await c.put('/api/v1/payable/1/pay',headers=auth(1),params={'paid_amount':300,'account_id':1});assert r.status_code==200,r.text
  paid=await views(c)
  assert paid['old_report_expense']==paid['unified_cost']==paid['company_expense']==300 and paid['cash_current_api']==9700
  report['cases']['paid_procurement_missing_in_old_report_and_account']={'views':paid,'paid_amount':300,'expected_wallet_expense':300,'payment_account_recorded':True}
  r=await c.put('/api/v1/payable/1/void',headers=auth(1),params={'void_reason':'隔离测试作废部分付款账单'});assert r.status_code==200,r.text
  void=await views(c)
  assert void['unified_cost']==void['company_expense']==300
  report['cases']['partially_paid_void_loses_cost_but_not_cash']={'views':void,'already_paid':300,'expected_wallet_expense':300}

async def scenario_split_payable(path,mp):
 import app.services.payable_payment as api
 async with clean(path,mp) as (f,c):
  async with f() as db:
   db.add(Supplier(id=1,warehouse_id=1,name='测试供应商'))
   db.add(PayableBill(id=1,warehouse_id=1,supplier_id=1,bill_number='SPLIT-1000',bill_date=datetime(2026,9,1),due_date=datetime(2026,12,1),amount=1000))
   await db.commit()
  mp.setattr(api,'thai_now',lambda:fixed(2026,9,30))
  r=await c.put('/api/v1/payable/1/pay',headers=auth(1),params={'paid_amount':400,'account_id':1});assert r.status_code==200,r.text
  sep_before=await views(c,start_date='2026-09-01',end_date='2026-09-30')
  mp.setattr(api,'thai_now',lambda:fixed(2026,10,20))
  r=await c.put('/api/v1/payable/1/pay',headers=auth(1),params={'paid_amount':600,'account_id':1});assert r.status_code==200,r.text
  sep_after=await views(c,start_date='2026-09-01',end_date='2026-09-30');oct_after=await views(c)
  assert sep_before['company_expense']==sep_after['company_expense']==400 and oct_after['company_expense']==600
  report['cases']['split_payment_last_date_overwrites_prior_month']={'september_before_second_payment':sep_before,
   'september_after_second_payment':sep_after,'october_after_second_payment':oct_after,'expected_september':400,'expected_october':600}

async def scenario_cash_payroll(path,mp):
 from tests.test_payroll_cash_advance import environment,approved,disburse,voucher,repay
 async with environment(path,mp) as (f,c):
  aid=await approved(c,amount=10000)
  before=await views(c)
  r=await disburse(c,aid);assert r.status_code==200,r.text
  after=await views(c)
  assert after['old_report_expense']==before['old_report_expense'] and after['company_expense']==before['company_expense']
  r=await repay(c,aid,await voucher(c),amount='7000.00',repayment_date='2026-11-01');assert r.status_code==200,r.text
  nov=await views(c,start_date='2026-11-01',end_date='2026-11-30')
  assert nov['company_expense']==nov['old_report_expense']==nov['unified_cost']==7000
  report['cases']['cash_advance_payroll_before_and_after_repayment']={'before':before,'after_payroll':after,'november_repayment':nov,
   'expected_cost_at_payroll_under_wallet_rule':0,'expected_november_wallet_expense':7000}

async def scenario_cash_reimbursement(path,mp):
 from tests.test_reimbursement_payments import environment,loan,approved,upload,pay
 async with environment(path,mp) as (_,f,c):
  aid=await loan(c,amount=10000);rid=await approved(c,amount=2000)
  before=await views(c)
  r=await pay(c,rid,await upload(c,rid),funding_source='cash_advance',payment_account_id=None,cash_advance_id=aid)
  assert r.status_code==200,r.text
  after=await views(c)
  assert after['old_report_expense']==before['old_report_expense'] and after['company_expense']==before['company_expense']
  report['cases']['cash_advance_reimbursement_counts_before_company_pays']={'before':before,'after':after,'expected_new_company_expense':0}

async def scenario_fund(path,mp):
 from tests.test_fund_disbursement import environment,topup,spend,values
 async with environment(path,mp) as (_,f,c,fid):
  mp.setenv('UPLOAD_DIR',str(path/'approval-uploads'))
  r=await topup(c,fid);assert r.status_code==200,r.text
  after_topup=await values(c,fid)
  r=await spend(c,fid,amount=2000);assert r.status_code==200,r.text
  after_spend=await values(c,fid)
  assert after_topup['expense_amount']==after_spend['expense_amount']==10000
  assert after_topup['company_flow_amount']==after_spend['company_flow_amount']==10000
  report['cases']['new_fund_disbursement_and_spending_correct']={'after_topup':after_topup,'after_spend':after_spend,'expected_wallet_expense':10000}
  appr=await post(c,'/expense-approvals',json={'amount':2000,'currency':'THB','purpose':'备用金已拨付后的费用付款',
   'expense_date':'2026-10-20','payment_method':'cash','fund_source':'fund'})
  await post(c,f'/expense-approvals/{appr["id"]}/approve')
  paid=await post(c,f'/expense-approvals/{appr["id"]}/pay',json={'voucher_base64':'data:image/png;base64,'+base64.b64encode(png()).decode()})
  after_approval=await values(c,fid)
  assert after_approval['expense_amount']==after_approval['company_flow_amount']==10000
  assert after_approval['company_cash']==after_spend['company_cash']
  report['cases']['fund_expense_approval_double_counts_company_payment']={'approval':paid,'before':after_spend,'after':after_approval,'expected_wallet_expense':10000}

async def scenario_credit_and_currencies(path,mp):
 async with clean(path,mp) as (f,c):
  async with f() as db:
   db.add(CreditCustomer(id=1,warehouse_id=1,customer_id=1,credit_limit=10000,current_debt=1000))
   db.add(CreditShipment(credit_customer_id=1,ship_date=datetime(2026,10,1),amount=1000))
   await db.commit()
  paid=await post(c,'/credit/1/payment',json={'repayment_date':'2026-10-20','amount':300,'account_id':1})
  v=await views(c)
  assert paid['current_debt']==700 and v['company_income']==v['ledger_income']==300
  report['cases']['credit_repayment_not_in_cash_receipts']={'payment':paid,'views':v,'expected_receipt_if_payment_is_actual':300}
  async with f() as db:
   db.add(PaymentAccount(id=3,warehouse_id=1,account_name='人民币账户',account_type='bank',account_number='CNY',currency='CNY',opening_balance=0))
   await db.commit()
  for value,cur,account in ((100,'THB',1),(200,'CNY',3)):
   await post(c,'/income-expense/income',json={'category_id':80,'account_id':account,'amount':value,'currency':cur,'income_date':'2026-10-20'})
  preview=await get(c,'/reports/previews',**RANGE)
  raw=await get(c,'/income-expense/ledger',**RANGE)
  company=await get(c,'/income-expense/ledger',**RANGE,flow_scope='company')
  assert preview['previews']['income-expense']['preview'] is None and raw['total_income'] is None
  assert company['total_income'] is None and company['income_by_currency']=={'CNY':200.0,'THB':400.0}
  report['cases']['preview_mixes_currencies']={'preview':preview['previews']['income-expense'],
   'default_ledger_total_income':raw['total_income'],'by_currency':raw['income_by_currency'],'company_total_income':company['total_income']}

async def scenario_pending_date(path,mp):
 from tests.test_round15_employee_self import enable
 import app.api.v1.employee_advance as api
 async with clean(path,mp) as (f,c):
  await enable(f);await set_perms(f,4,['员工预支'])
  body={'employee_id':5,'amount':1000,'advance_date':'2026-09-30','funding_source':'company_account','payment_account_id':1}
  r=await c.post('/api/v1/employee-advances',headers=auth(4),json=body);assert r.status_code==200,r.text
  aid=r.json()['id'];before=await views(c,start_date='2026-09-01',end_date='2026-09-30')
  assert r.json()['approval_status']=='pending' and before['company_expense']==0
  mp.setattr(api,'thai_now',lambda:fixed(2026,10,20))
  approved=await post(c,f'/employee-advances/{aid}/approve')
  sep=await views(c,start_date='2026-09-01',end_date='2026-09-30');october=await views(c)
  assert sep['company_expense']==0 and october['company_expense']==1000
  report['cases']['pending_advance_executes_on_approval_but_posts_registration_date']={'approval':approved,'september':sep,'october':october,
   'expected_execution_date':'2026-10-20','stored_expense_date':'2026-10-20'}

async def main():
 scenarios=[scenario_income,scenario_manual,scenario_payable,scenario_split_payable,scenario_cash_payroll,
  scenario_cash_reimbursement,scenario_fund,scenario_credit_and_currencies,scenario_pending_date]
 with tempfile.TemporaryDirectory(prefix='wallet-basis-audit-') as temp:
  for index,fn in enumerate(scenarios):
   path=Path(temp)/str(index);path.mkdir()
   with MonkeyPatch.context() as mp:
    await fn(path,mp)
   print('PASS',fn.__name__,flush=True)
   (OUT/'实际复现数据.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,default=str)+'\n')
 print('DONE',len(report['cases']), 'verified cases',flush=True)



import pytest
@pytest.mark.parametrize("scenario", [scenario_income,scenario_manual,scenario_payable,scenario_split_payable,
    scenario_cash_payroll,scenario_cash_reimbursement,scenario_fund,scenario_credit_and_currencies,scenario_pending_date])
def test_wallet_policy_end_to_end(tmp_path, monkeypatch, scenario):
    asyncio.run(scenario(tmp_path, monkeypatch))
    (OUT/'实际修复数据.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str))

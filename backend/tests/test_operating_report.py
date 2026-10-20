"""独立经营报表：真实PG，未确认成本口径时利润必须为空，不能借钱包冒充。"""
import asyncio,json,os
from pathlib import Path
from datetime import date,datetime
import pytest
from sqlalchemy import select,func,event
from app.models import Customer,User,UserWarehouse,IncomeExpenseCategory,ExpenseRecord,Employee,Supplier
from app.models.credit import CreditShipment
from app.models.payroll import PayrollRecord
from app.models.reimbursement import Reimbursement
from app.models.payable import PayableBill
from app.models.expense_fund import ExpenseFund,ExpenseFundItem,ExpenseFundDisbursement
from app.models.expense_approval import ExpenseApproval
from app.models.employee_advance import EmployeeAdvance
from app.models.cash_advance import CashAdvance
from app.models.cash_advance_repayment import CashAdvanceRepayment
from tests.test_customer_receivables import ship,receive
from tests.test_credit_shipments import retained_entries, shipments_environment,payload,wallet
from tests.test_incoming_operations import URL,body
from tests.test_round2_permissions import auth
pytestmark=pytest.mark.skipif(not URL,reason='Requires explicit loopback PostgreSQL')
REPORT={}
def actual(key,value):
 REPORT[key]=value
 if os.environ.get('OPERATING_REPORT_TEST_REPORT'):Path(os.environ['OPERATING_REPORT_TEST_REPORT']).write_text(json.dumps(REPORT,ensure_ascii=False,indent=2,default=str))
async def get(c,uid=1,headers=None,**q):return await c.get('/api/v1/reports/operations',headers=headers or auth(uid),params=q)
def block(data,cur='THB'):return next(x for x in data['currencies'] if x['currency']==cur)


def test_cross_month_shipments_receipts_wallet_unchanged_and_no_fake_600_profit(tmp_path,monkeypatch):
 async def run():
  async with shipments_environment(tmp_path,monkeypatch) as (_,f,c):
   await ship(c,1000,ship_date='2026-09-01');await receive(c,1000,received_date='2026-10-01')
   async with f() as db:
    db.add(IncomeExpenseCategory(id=1,warehouse_id=1,type='expense',name='采购',category_group='operating'));await db.flush()
    db.add(ExpenseRecord(warehouse_id=1,category_id=1,account_id=1,amount=400,currency='THB',expense_date=datetime(2026,9,2),approved_by=1));await db.commit()
   before={m:(await c.get(f'/api/v1/reports/income-expense?start_date=2026-{m}-01&end_date=2026-{m}-30',headers=auth(1))).json() for m in ('09','10')}
   results={}
   for month,sh,received,win,wout,debt in [('2026-09',1000,0,0,400,1000),('2026-10',0,1000,1000,0,0)]:
    r=await get(c,month=month);assert r.status_code==200,r.text;data=r.json();b=block(data)
    assert (b['shipment_income'],b['actual_receipts'],b['receivable_asof'])==(sh,received,debt)
    assert b['operating_profit'] is None and b['attributed_cost_total'] is None and not b['profit_computable']
    assert data['wallet']['income_by_currency'].get('THB',0)==win and data['wallet']['expense_by_currency'].get('THB',0)==wout
    assert sum(d['shipment_income'] for d in b['daily'])==sh and sum(d['actual_receipts'] for d in b['daily'])==received
    results[month]={'amounts':b,'wallet':data['wallet'],'cost_reference_count':data['cost_references']['total']}
   assert results['2026-09']['cost_reference_count']==1 and results['2026-10']['cost_reference_count']==0
   after={m:(await c.get(f'/api/v1/reports/income-expense?start_date=2026-{m}-01&end_date=2026-{m}-30',headers=auth(1))).json() for m in ('09','10')}
   assert before==after
   actual('cross_month',{'periods':results,'wallet_reports_unchanged':before==after,'profit_600_not_claimed':'没有已确认成本归期及完整性依据，利润为空，不把400付款冒充对应经营成本'})
 asyncio.run(run())


def test_cost_source_review_deduplicates_linked_documents_and_excludes_funding_transfers(tmp_path,monkeypatch):
 async def run():
  async with shipments_environment(tmp_path,monkeypatch) as (_,f,c):
   async with f() as db:
    db.add(Employee(id=1,warehouse_id=1,user_id=5,name='测试员工',hire_date=datetime(2026,1,1),status='regular'))
    db.add(Supplier(id=1,warehouse_id=1,name='测试供应商'))
    db.add(IncomeExpenseCategory(id=1,warehouse_id=1,type='expense',name='运营支出',category_group='operating'))
    await db.flush()
    for eid,value in [(1,700),(2,200),(3,1000),(4,100),(5,60),(6,50)]:
     db.add(ExpenseRecord(id=eid,warehouse_id=1,category_id=1,account_id=1,amount=value,currency='THB',expense_date=datetime(2026,9,5)))
    db.add(CashAdvance(id=1,warehouse_id=1,payer_id=4,payer_name='主管',advance_date=date(2026,9,1),amount=2000,currency='THB',purpose='salary',status='confirmed',repaid_amount=500,created_by_id=1,created_by_name='管理员'))
    db.add(ExpenseFund(id=1,warehouse_id=1,employee_id=4,receive_date=datetime(2026,9,1),amount=1000,remaining_balance=800,purpose='备用金',currency='THB'))
    await db.flush()
    db.add(CashAdvanceRepayment(id=1,cash_advance_id=1,warehouse_id=1,repayment_date=date(2026,9,8),amount=500,currency='THB',account_id=1,account_name='现金',payment_method='cash',voucher_path='synthetic.png',created_by_id=1,created_by_name='管理员',status='active'))
    db.add(ExpenseFundDisbursement(id=1,warehouse_id=1,fund_id=1,amount=1000,currency='THB',disbursed_date=datetime(2026,9,1),payment_account_id=1,account_name='现金',expense_record_id=3,operator_id=1,operator_name='管理员'))
    for iid,status in [(1,'approved'),(2,'approved'),(3,'approved'),(4,'approved'),(5,'pending'),(6,'rejected'),(7,'voided')]:
     db.add(ExpenseFundItem(id=iid,fund_id=1,expense_date=datetime(2026,9,5),category='耗材',amount=20,currency='THB',description='虚构',review_status=status))
    db.add(PayrollRecord(id=1,warehouse_id=1,employee_id=1,period='2026-09',half='first_half',settle_start_date=date(2026,9,1),settle_end_date=date(2026,9,15),status='confirmed',gross_pay=800,total_deductions=0,net_pay=700,advance_deduction=100,expense_record_id=1,cash_advance_id=1,disbursed=True))
    db.add(PayrollRecord(id=2,warehouse_id=1,employee_id=1,period='2026-09',status='pending',net_pay=999))
    db.add(PayrollRecord(id=3,warehouse_id=1,employee_id=1,period='2026-09',status='confirmed',net_pay=999,voided=True))
    await db.flush()
    db.add(Reimbursement(id=1,warehouse_id=1,employee_id=4,submit_date=datetime(2026,9,5),total_amount=200,currency='THB',status='paid',expense_record_id=2,cash_advance_id=1,funding_source='cash_advance'))
    db.add(Reimbursement(id=2,warehouse_id=1,employee_id=4,submit_date=datetime(2026,9,5),total_amount=20,currency='THB',status='fund_linked',fund_item_id=2))
    db.add(Reimbursement(id=3,warehouse_id=1,employee_id=4,submit_date=datetime(2026,9,5),total_amount=999,currency='THB',status='rejected'))
    db.add(PayableBill(id=1,warehouse_id=1,supplier_id=1,bill_number='候选采购',bill_date=datetime(2026,9,5),due_date=datetime(2026,10,1),amount=400,currency='THB',status='pending'))
    db.add(PayableBill(id=2,warehouse_id=1,supplier_id=1,bill_number='作废采购',bill_date=datetime(2026,9,5),due_date=datetime(2026,10,1),amount=999,currency='THB',status='voided'))
    db.add(ExpenseApproval(id=1,warehouse_id=1,applicant_id=4,amount=60,currency='THB',purpose='费用',expense_date=date(2026,9,5),status='paid',fund_source='fund',fund_item_id=3,expense_record_id=5))
    db.add(ExpenseApproval(id=2,warehouse_id=1,applicant_id=4,amount=999,currency='THB',purpose='待批',expense_date=date(2026,9,5),status='pending'))
    db.add(EmployeeAdvance(id=1,warehouse_id=1,employee_id=1,period='2026-09',advance_date=date(2026,9,5),amount=100,source='fund',funding_source='expense_fund',fund_item_id=4,expense_record_id=4,approval_status='approved',status='unpaid'))
    await db.commit()
   before=await wallet(f);r=await get(c,month='2026-09',page_size=200);assert r.status_code==200,r.text
   data=r.json();refs=data['cost_references']['data'];keys={(r['source'],r['source_id']) for r in refs}
   assert keys=={('payroll',1),('reimbursement',1),('reimbursement',2),('payable',1),('expense_approval',1),('fund_item',1),('manual_expense',6)},keys
   assert all(r['cost_amount'] is None and not r['cost_period_confirmed'] for r in refs)
   assert block(data)['operating_profit'] is None and data['cost_completeness_confirmed'] is False
   assert await wallet(f)==before
   actual('cost_review',{'reference_count':len(refs),'sources':sorted(keys),'payroll_net_reference':700,'advance_100_not_extra_cost':True,'fund_disbursement_1000_not_extra_cost':True,'advance_repayment_500_not_extra_cost':True,'wallet_unchanged':True,'profit':None})
 asyncio.run(run())


def test_customer_currency_scope_paging_dates_voids_and_read_only(tmp_path,monkeypatch):
 async def run():
  async with shipments_environment(tmp_path,monkeypatch) as (engine,f,c):
   for i in range(23):await ship(c,10,ship_date='2026-09-30',order_count=1)
   await c.post('/api/v1/credit/4/shipment',headers=auth(1),json=payload(amount='200',currency='CNY',ship_date='2026-09-01'))
   void=await c.post('/api/v1/credit/3/shipment',headers=auth(1),json=payload(amount='999',ship_date='2026-09-02'))
   assert (await c.post(f'/api/v1/credit/3/shipment/{void.json()["id"]}/void',headers=auth(1),json={'reason':'虚构作废'})).status_code==200
   await c.post('/api/v1/credit/2/shipment',headers=auth(7),json=payload(amount='999',ship_date='2026-09-01'))
   queries=[]
   def trace(conn,cursor,stmt,*args):queries.append(stmt)
   event.listen(engine.sync_engine,'before_cursor_execute',trace)
   try:
    a=await get(c,month='2026-09',currency='THB',page_size=10);b=await get(c,month='2026-09',currency='THB',shipment_page=3,page_size=10)
    assert a.status_code==b.status_code==200
    assert a.json()['shipments']['total']==23 and len(b.json()['shipments']['data'])==3 and block(a.json())==block(b.json())
    assert block(a.json())['shipment_income']==230 and len(a.json()['currencies'])==1
    cny=(await get(c,month='2026-09',currency='CNY')).json();assert block(cny,'CNY')['shipment_income']==200
    selected=(await get(c,month='2026-09',customer_id=1)).json();assert block(selected)['shipment_income']==230 and selected['wallet'] is None and selected['cost_references']['total']==0
    for q in [{'month':'2026-13'},{'currency':'USD'},{'start_date':'bad'},{'start_date':'2026-10-01','end_date':'2026-09-01'}]:assert (await get(c,**q)).status_code==400
    for q in [{'customer_id':2},{'warehouse_id':2}]:assert (await get(c,month='2026-09',**q)).status_code==403
    assert (await get(c,headers={**auth(1),'X-Warehouse-ID':'2'},month='2026-09')).status_code==403
    assert all(not sql.lstrip().upper().startswith(('INSERT','UPDATE','DELETE')) for sql in queries)
   finally:event.remove(engine.sync_engine,'before_cursor_execute',trace)
   actual('filters_readonly',{'THB':230,'CNY':200,'shipments':23,'page3_rows':3,'foreign_999_excluded':True,'voided_999_excluded':True,'customer_cost_not_guessed':True,'mutation_queries':0})
 asyncio.run(run())


def test_report_permission_all_authorized_warehouses_legacy_and_year_boundaries(tmp_path,monkeypatch):
 async def run():
  async with shipments_environment(tmp_path,monkeypatch) as (_,f,c):
   for uid in (2,3,4,5):assert (await get(c,uid,month='2026-09')).status_code==403
   async with f() as db:
    for uid in (3,4):(await db.get(User,uid)).extra_permissions=['报表中心']
    db.add(UserWarehouse(user_id=1,warehouse_id=2));(await db.get(Customer,1)).debt_amount=777;await db.commit()
   for uid in (3,4):assert (await get(c,uid,month='2026-09')).status_code==200
   assert (await get(c,3,headers={**auth(3),'X-Warehouse-ID':'all'},month='2026-09')).status_code==403
   await ship(c,100,ship_date='2026-12-31');await receive(c,100,received_date='2027-01-01')
   r=await c.post('/api/v1/credit/2/shipment',headers=auth(7),json=payload(amount='200',ship_date='2026-12-31'));assert r.status_code==200
   allw=(await get(c,headers={**auth(1),'X-Warehouse-ID':'all'},month='2026-12')).json();assert block(allw)['shipment_income']==300
   dec=(await get(c,month='2026-12')).json();jan=(await get(c,month='2027-01')).json()
   assert block(dec)['shipment_income']==100 and block(dec)['actual_receipts']==0
   assert block(jan)['shipment_income']==0 and block(jan)['actual_receipts']==100
   assert dec['review_items'][0]['amount']==777 and block(dec)['receivable_asof']==100
   async with f() as db:assert (await db.get(Customer,1)).debt_amount==777
   actual('access_year_legacy',{'office_reports_only':200,'revoked_labor_superadmin':403,'all_warehouse_THB':300,'single_warehouse_THB':100,'dec_ship':100,'jan_received':100,'legacy_debt_kept':777,'profit':None})
 asyncio.run(run())

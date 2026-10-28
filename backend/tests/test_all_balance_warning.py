"""Real HTTP/transactions on synthetic SQLite and disposable localhost PG only."""
import asyncio,json
from datetime import datetime
from app.core.timezone import THAI_TZ
from pathlib import Path
from decimal import Decimal
import pytest
from sqlalchemy import select,func
from app.models import PaymentAccount,ExpenseFund,ExpenseFundItem
from app.models.payroll import PayrollRecord
from app.models.income_expense import ExpenseRecord
from app.models.data_change_history import DataChangeHistory
from app.services.account_balances import current_account_balances
from tests.test_round2_permissions import auth
from tests.test_round3_permissions import hr_environment
from tests.test_supplier_workflow_round1 import setup
from tests.test_expense_approval_payment import fee_environment,create as fee_create,pay as fee_pay,numbers
from tests.test_fund_disbursement import environment as fund_environment,topup,receipt
from tests.evidence_path import evidence_dir
OUT=evidence_dir('all-balance-warning-20261028')
def save(name,value):OUT.mkdir(exist_ok=True);(OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,default=str))
async def balance(f):
 async with f() as db:
  a=await db.get(PaymentAccount,1);return float((await current_account_balances(db,[a]))[1])
async def count(f):
 async with f() as db:return (await db.execute(select(func.count()).select_from(ExpenseRecord))).scalar_one()
async def logs(f,module=None):
 async with f() as db:
  q=select(DataChangeHistory).order_by(DataChangeHistory.id)
  if module:q=q.where(DataChangeHistory.module==module)
  rows=(await db.execute(q)).scalars().all()
  return [{'id':r.id,'module':r.module,'operator_id':r.operator_id,'operator_name':r.operator_name,'created_at':str(r.created_at),'data':r.after_data} for r in rows if r.after_data and r.after_data.get('remark')=='余额不足仍然执行']
@pytest.mark.parametrize('batch',[False,True])
def test_negative_salary_real_response_and_batch(tmp_path,monkeypatch,batch):
 async def run():
  async with hr_environment(tmp_path,monkeypatch) as (_,f,c):
   async with f() as db:
    (await db.get(PaymentAccount,1)).opening_balance=-1000
    if batch:
     row=await db.get(PayrollRecord,1);row.status='confirmed';row.net_pay=100.01
    await db.commit()
   before=await balance(f);old=await count(f);path='/api/v1/payroll/batch-disburse' if batch else '/api/v1/payroll/2/disburse'
   from tests.round3_flow_support import prepare_payroll
   await prepare_payroll(f,c,*([1,2] if batch else [2]))
   if batch:
    invalid=await c.post(path,headers=auth(3),json={'account_id':1,'record_ids':[1,2,2,3]})
    assert invalid.status_code==400 and await balance(f)==before
   payload={'account_id':1,**({'record_ids':[1,2]} if batch else {})}
   result=await c.post(path,headers=auth(3),json=payload);assert result.status_code==200,result.text
   data=result.json();amount=1334.57 if batch else 1234.56
   assert data['warning']['balance_before']==before and data['warning']['amount']==amount
   assert data['warning']['balance_after']==pytest.approx(before-amount) and await balance(f)==pytest.approx(before-amount)
   assert await count(f)==old+(2 if batch else 1) and len(await logs(f,'payroll'))==1
   replay=await c.post(path,headers=auth(3),json=payload)
   assert replay.status_code==(409 if batch else 400)
   assert len(await logs(f,'payroll'))==1
   save('step1-batch.json' if batch else 'step1-salary.json',{'status':result.status_code,'response':data,'before':before,'after':await balance(f),'expenses_before':old,'expenses_after':await count(f),'logs':await logs(f,'payroll')})
 asyncio.run(run())
def test_negative_payable_concurrency_and_original_retry(tmp_path,monkeypatch):
 async def run():
  import app.services.payable_payment as payment
  monkeypatch.setattr(payment,'thai_now',lambda:datetime(2026,10,20,12,tzinfo=THAI_TZ))
  async with setup(tmp_path,monkeypatch) as (_,f,c):
   async with f() as db:(await db.get(PaymentAccount,1)).opening_balance=-1000;await db.commit()
   params={'paid_amount':500,'account_id':1,'payment_method':'现金','request_key':'all-balance-payable-original'}
   from tests.test_supplier_workflow_round1 import request
   await request(c,'POST','/payable/1/verify-payment',uid=97)
   await request(c,'POST','/payable/1/approve-payment',uid=96)
   async def pay():return await c.put('/api/v1/payable/1/pay',headers=auth(97),params=params)
   responses=await asyncio.gather(*(pay() for _ in range(5)));assert all(r.status_code==200 for r in responses),[r.text for r in responses]
   data=responses[0].json();assert len({r.json()['payment_id'] for r in responses})==1
   assert data['warning']['balance_before']==-1000 and await balance(f)==-1500 and len(await logs(f,'payable'))==1
   replay=await pay();assert replay.json()['warning']==data['warning'] and await balance(f)==-1500
   save('step2-payable.json',{'statuses':[r.status_code for r in responses],'response':data,'retry':replay.json(),'balance':await balance(f),'logs':await logs(f,'payable')})
 asyncio.run(run())
@pytest.mark.parametrize('fund',[False,True])
def test_negative_fee_both_sources_preview_and_retry(tmp_path,monkeypatch,fund):
 async def run():
  async with fee_environment(tmp_path,monkeypatch,fund=fund) as (_,f,c):
   async with f() as db:
    (await db.get(PaymentAccount,1)).opening_balance=-1000
    if fund:(await db.get(ExpenseFund,1)).remaining_balance=50
    await db.commit()
   fee=await fee_create(c,fund_source='fund' if fund else 'company');before=await numbers(f)
   preview=await c.get(f"/api/v1/expense-approvals/{fee['id']}/payment-preview",headers=auth(1),params={} if fund else {'payment_account_id':1})
   assert preview.status_code==200 and preview.json()['warning'],preview.text
   assert await numbers(f)==before
   async def pay():return await fee_pay(c,fee['id'],payment_account_id=None if fund else 1)
   responses=await asyncio.gather(*(pay() for _ in range(4)));assert all(r.status_code==200 for r in responses),[r.text for r in responses]
   data=responses[0].json();after=await numbers(f)
   assert data['warning']['balance_before']==(50 if fund else -1000) and data['warning']['amount']==200
   assert after['company_balance']==(-1000 if fund else -1200) and after['fund_items']==(1 if fund else 0) and after['expense_rows']==(0 if fund else 1)
   assert len(await logs(f,'expense_approval'))==1 and (await pay()).json()['warning']==data['warning']
   save('step3-fund-fee.json' if fund else 'step3-company-fee.json',{'preview':preview.json(),'response':data,'before':before,'after':after,'logs':await logs(f,'expense_approval')})
 asyncio.run(run())
def test_default_5000_fund_cap_still_blocks(tmp_path,monkeypatch):
 async def run():
  async with fund_environment(tmp_path,monkeypatch) as (_,f,c,fid):
   async with f() as db:(await db.get(ExpenseFund,fid)).fund_limit=5000;(await db.get(PaymentAccount,1)).opening_balance=-1000;await db.commit()
   before=await balance(f);result=await topup(c,fid,amount=5001)
   assert result.status_code==400 and '超出既有备用金上限' in result.text,result.text
   assert await balance(f)==before and await count(f)==0 and await logs(f)==[]
   save('step5-fund-cap.json',{'status':result.status_code,'response':result.json(),'before':before,'after':await balance(f)})
 asyncio.run(run())
def test_warning_log_failure_rolls_back_salary(tmp_path,monkeypatch):
 async def run():
  from fastapi import HTTPException
  import app.services.balance_warning as service
  async with hr_environment(tmp_path,monkeypatch) as (_,f,c):
   async with f() as db:(await db.get(PaymentAccount,1)).opening_balance=-1000;await db.commit()
   before=await balance(f);old=await count(f)
   async def fail(*a,**k):raise HTTPException(500,'isolated warning log failure')
   monkeypatch.setattr(service,'record_history',fail)
   from tests.round3_flow_support import prepare_payroll
   await prepare_payroll(f,c,2)
   result=await c.post('/api/v1/payroll/2/disburse',headers=auth(3),json={'account_id':1})
   assert result.status_code==500 and await balance(f)==before and await count(f)==old
   async with f() as db:assert not (await db.get(PayrollRecord,2)).disbursed
 asyncio.run(run())
def test_other_manual_expense_transfer_and_replay(tmp_path,monkeypatch):
 async def run():
  from tests.test_cash_wallet import cash_environment,payment,balances
  async with cash_environment(tmp_path,monkeypatch) as (_,f,c,cash,bank):
   async with f() as db:(await db.get(PaymentAccount,cash)).opening_balance=-1000;await db.commit()
   body=payment(cash,key='negative-manual-expense');result=await c.post('/api/v1/income-expense/expense',headers=auth(1),data=body)
   assert result.status_code==200 and result.json()['warning']['balance_before']==-1000,result.text
   assert (await balances(f,cash))[cash]==-1200
   replay=await c.post('/api/v1/income-expense/expense',headers=auth(1),data=body);assert replay.json()['warning']==result.json()['warning']
   transfer={'from_account_id':cash,'to_account_id':bank,'amount':300,'transfer_date':'2026-10-20','request_key':'negative-transfer'}
   result=await c.post('/api/v1/accounts/transfers',headers=auth(1),json=transfer);assert result.status_code==200,result.text
   assert result.json()['warning']['balance_before']==-1200 and await balances(f,cash,bank)=={cash:-1500,bank:300}
   replay=await c.post('/api/v1/accounts/transfers',headers=auth(1),json=transfer);assert replay.json()['warning']==result.json()['warning']
   assert len(await logs(f,'expense'))==1 and len(await logs(f,'accounts'))==1
 asyncio.run(run())
def test_other_fund_item_create_and_edit(tmp_path,monkeypatch):
 async def run():
  async with fund_environment(tmp_path,monkeypatch) as (_,f,c,fid):
   proof=await receipt(c,fid);path=f'/api/v1/expense-fund/accounts/{fid}/items'
   body={'request_key':'negative-fund-item','expense_date':'2026-10-20','category':'耗材','amount':200,'currency':'THB','description':'合成超支','receipt':proof}
   result=await c.post(path,headers=auth(4),json=body);assert result.status_code==200,result.text
   assert result.json()['warning']['balance_before']==0
   rid=result.json()['id'];edited=await c.put(path+f'/{rid}',headers=auth(1),json={'amount':300});assert edited.status_code==200 and edited.json()['warning'],edited.text
   async with f() as db:
    assert (await db.get(ExpenseFundItem,rid)).amount==300 and (await db.get(ExpenseFund,fid)).remaining_balance==0
   replay=await c.post(path,headers=auth(4),json=body)
   assert replay.status_code==200 and replay.json()['warning']==result.json()['warning'],replay.text
   assert await count(f)==0 and len(await logs(f,'expense_fund_item'))==2
 asyncio.run(run())
@pytest.mark.parametrize('source',['cash_advance','expense_fund'])
def test_other_employee_advance_sources(tmp_path,monkeypatch,source):
 async def run():
  from tests.test_employee_advance_funding import environment,create
  from app.models.cash_advance import CashAdvance
  async with environment(tmp_path,monkeypatch) as (_,f,c):
   async with f() as db:
    if source=='cash_advance':(await db.get(CashAdvance,1)).amount=Decimal('100')
    else:(await db.get(ExpenseFund,1)).remaining_balance=100
    await db.commit()
   from tests.round3_flow_support import verify_approve_cash,execute_advance
   if source=='cash_advance':
    async with f() as db:(await db.get(CashAdvance,1)).status='pending';await db.commit()
    await verify_approve_cash(f,c,1)
   result=await create(c,funding_source=source,cash_advance_id=1,fund_account_id=1,amount=500)
   assert result.status_code==200 and result.json()['approval_status']=='pending',result.text
   result=await execute_advance(f,c,result.json()['id'])
   assert result.status_code==200 and result.json()['warning'],result.text
   assert result.json()['warning']['balance_before']==100 and len(await logs(f,'employee_advances'))==1
 asyncio.run(run())

@pytest.mark.parametrize('kind',['payroll','reimbursement'])
def test_cash_advance_overspending_warns_without_deducting_company(tmp_path,monkeypatch,kind):
 async def run():
  from tests.test_reimbursement_payments import environment,approved,upload,pay,loan,balances
  from tests.test_payroll_cash_advance import disburse
  async with environment(tmp_path,monkeypatch) as (_,f,c):
   aid=await loan(c,amount=100)
   before=await balances(c)
   if kind=='payroll':
    from tests.round3_flow_support import prepare_payroll
    await prepare_payroll(f,c,2)
    r=await disburse(c,aid)
   else:
    rid=await approved(c);path=await upload(c,rid)
    r=await pay(c,rid,path,funding_source='cash_advance',payment_account_id=None,cash_advance_id=aid)
   assert r.status_code==200,r.text
   assert r.json()['warning']['balance_before']==100 and r.json()['warning']['balance_after']<0
   assert await balances(c)==before
   assert len(await logs(f,'payroll' if kind=='payroll' else 'reimbursement'))==1
 asyncio.run(run())

def test_negative_plan_warns_and_creates_one_payment(tmp_path,monkeypatch):
 async def run():
  from app.models import PayablePlan,PayablePayment
  import app.services.payable_payment as payment
  monkeypatch.setattr(payment,'thai_now',lambda:datetime(2026,10,20,12,tzinfo=THAI_TZ))
  async with setup(tmp_path,monkeypatch) as (_,f,c):
   async with f() as db:
    (await db.get(PaymentAccount,1)).opening_balance=-1000
    await db.commit()
   from tests.test_supplier_workflow_round1 import request
   await request(c,'POST','/payable/1/verify-payment',uid=97)
   await request(c,'POST','/payable/1/approve-payment',uid=96)
   plan=await request(c,'POST','/payable/plans',uid=97,json={'plan_name':'合成负余额计划','planned_date':'2026-10-20','bill_ids':[1]})
   assert plan['id']==1
   r=await c.put('/api/v1/payable/plans/1/execute?account_id=1',headers=auth(97),json={})
   assert r.status_code==200,r.text
   assert r.json()['warning']['balance_after']==-2000 and await balance(f)==-2000
   retry=await c.put('/api/v1/payable/plans/1/execute?account_id=1',headers=auth(97),json={})
   assert retry.status_code==400 and await balance(f)==-2000
   async with f() as db:assert (await db.execute(select(func.count()).select_from(PayablePayment))).scalar_one()==1
 asyncio.run(run())

def test_financial_formulas_and_fund_limit_implementation_unchanged():
 import ast,subprocess
 root=Path(__file__).resolve().parents[2]
 def original(path):return subprocess.check_output(['git','show',f'6ec3d62:{path}'],cwd=root,text=True)
 for path in ['backend/app/services/account_balances.py','backend/app/services/flow_rules.py','backend/app/services/fund_disbursement.py','backend/app/services/payroll_expense.py']:
  assert (root/path).read_text()==original(path)
 for path,names in [('backend/app/api/v1/payroll.py',['_compute_employee_records','_calc_payroll']),('backend/app/services/employee_advance_funding.py',['fund_available_amount']),('backend/app/services/cash_advance_payroll.py',['usage_amounts'])]:
  def formulas(source):return {n.name:ast.dump(n,include_attributes=False) for n in ast.parse(source).body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name in names}
  assert formulas((root/path).read_text())==formulas(original(path))

 # The orchestration wrapper gained permission checks, not a new wage formula.
 path='backend/app/api/v1/payroll.py'
 def wrapper(source):return {n.name:ast.dump(n,include_attributes=False) for n in ast.parse(source).body if isinstance(n,ast.AsyncFunctionDef) and n.name in ('calculate_payroll','_prepare_payroll')}
 assert wrapper((root/path).read_text())==wrapper(subprocess.check_output(['git','show','87a461b:'+path],cwd=root,text=True))

"""Advisory balances: real HTTP, synthetic funds/accounts and unchanged money arithmetic."""
import asyncio,json
from pathlib import Path
import pytest
from sqlalchemy import select,func
from app.models import PaymentAccount,ExpenseFund
from app.models.data_change_history import DataChangeHistory
from app.services.account_balances import current_account_balances
from tests.test_round2_permissions import auth
from tests.test_fund_disbursement import environment as fund_env,topup,values
from tests.test_employee_advance_funding import environment as advance_env,create,state
from tests.test_reimbursement_payments import environment as reimb_env,approved,upload,pay,balances,costs,BASE
OUT=Path(__file__).resolve().parents[2]/'docs/balance-warning-20261028'

async def warning_logs(f):
 async with f() as db:
  rows=(await db.execute(select(DataChangeHistory).order_by(DataChangeHistory.id))).scalars().all()
  return [{'id':r.id,'module':r.module,'record_id':r.record_id,'operator_id':r.operator_id,'operator_name':r.operator_name,'created_at':str(r.created_at),'before':r.before_data,'after':r.after_data} for r in rows if r.after_data and r.after_data.get('remark')=='余额不足仍然执行']


def check_warning(w,before,amount,after,source):
 assert w['balance_before']==before and w['amount']==amount and w['balance_after']==after and w['source']==source
 assert w['message']==f'当前账户余额不足（可用 {before:,.2f}，本次 {amount:,.2f}），确认继续吗'


def test_negative_company_fund_5000_actual_response_and_history(tmp_path,monkeypatch):
 async def run():
  async with fund_env(tmp_path,monkeypatch) as (_,f,c,fid):
   async with f() as db:(await db.get(PaymentAccount,1)).opening_balance=-1000;await db.commit()
   before=await values(c,fid)
   result=await topup(c,fid,amount=5000,receive_date="2026-10-28");assert result.status_code==200,result.text
   actual=result.json();after=await values(c,fid)
   check_warning(actual['warning'],-1000,5000,-6000,'company_account')
   assert actual['account_balance']==after['company_cash']==-6000
   assert after['expense_count']==before['expense_count']+1 and after['flow_count']==before['flow_count']+1
   assert after['expense_amount']==before['expense_amount']+5000 and after['fund']['current_balance']==5000
   logs=await warning_logs(f);assert len(logs)==1 and logs[0]['operator_id']==1 and logs[0]['created_at']
   history=await c.get('/api/v1/history',headers=auth(1),params={'module':'expense_fund','record_id':fid})
   assert history.status_code==200 and '余额不足仍然执行' in history.text
   OUT.mkdir(exist_ok=True);(OUT/'step1-actual.json').write_text(json.dumps({'synthetic_only':True,'http_status':result.status_code,'response':actual,'before':before,'after':after,'warning_history':logs,'history_response':history.json()},ensure_ascii=False,indent=2,default=str))
 asyncio.run(run())


def test_negative_company_advance_executes_cost_and_logs_once(tmp_path,monkeypatch):
 async def run():
  async with advance_env(tmp_path,monkeypatch) as (_,f,c):
   async with f() as db:(await db.get(PaymentAccount,1)).opening_balance=-1000;await db.commit()
   result=await create(c,amount=500);assert result.status_code==200,result.text
   check_warning(result.json()['warning'],-1000,500,-1500,'company_account')
   after=await state(f);assert after['balance']==-1500 and after['expenses']==1 and after['expense_amount']==500
   logs=await warning_logs(f);assert len(logs)==1 and logs[0]['module']=='employee_advances'
   OUT.mkdir(exist_ok=True);(OUT/'step2-actual.json').write_text(json.dumps({'response':result.json(),'state':after,'logs':logs},ensure_ascii=False,indent=2))
 asyncio.run(run())


def test_low_fund_reimbursement_create_and_repayment_no_double_debit(tmp_path,monkeypatch):
 async def run():
  async with reimb_env(tmp_path,monkeypatch) as (_,f,c):
   async with f() as db:(await db.get(ExpenseFund,1)).remaining_balance=100;await db.commit()
   preview=await c.get(BASE+'/fund-balance',headers=auth(4));assert preview.status_code==200 and preview.json()['fund']['current_balance']==100
   result=await c.post(BASE,headers=auth(4),json={'submit_date':'2026-10-18','currency':'THB','is_fund_linked':'1','items':[{'category':'交通费','amount':500,'description':'合成余额提示验证'}]})
   assert result.status_code==200,result.text;rid=result.json()['id'];check_warning(result.json()['warning'],100,500,-400,'expense_fund')
   async with f() as db:assert (await db.get(ExpenseFund,1)).remaining_balance==-400
   assert len(await warning_logs(f))==1
   # Existing initial payment/approval must not debit the fund a second time.
   reviewed=await c.post('/api/v1/expense-fund/review/batch',headers=auth(1),json={'item_ids':[(await c.get(f'{BASE}/{rid}',headers=auth(1))).json()['fund_item_id']],'action':'approve'})
   assert reviewed.status_code==200,reviewed.text
   async with f() as db:assert (await db.get(ExpenseFund,1)).remaining_balance==-400
   # Synthetic historical setup only; the disabled revoke API stays disabled.
   from app.services import reimbursement_payment as service
   from app.models.reimbursement import Reimbursement
   from app.models import User
   async with f() as db:
    await service.revoke(db,await db.get(Reimbursement,rid),await db.get(User,1),'合成历史状态验证')
    await db.commit()
   async with f() as db:(await db.get(ExpenseFund,1)).remaining_balance=50;await db.commit()
   sources=(await c.get(BASE+'/payment-sources',headers=auth(1),params={'reimbursement_id':rid})).json()
   assert sources['fund']['current_balance']==50 and sources['fund']['debit_amount']==500
   paid=await c.post(f'{BASE}/{rid}/pay',headers=auth(1),json={'funding_source':'expense_fund'})
   assert paid.status_code==200,paid.text;check_warning(paid.json()['warning'],50,500,-450,'expense_fund')
   async with f() as db:assert (await db.get(ExpenseFund,1)).remaining_balance==-450
   assert len(await warning_logs(f))==2
   OUT.mkdir(exist_ok=True);(OUT/'step3-actual.json').write_text(json.dumps({'initial':result.json(),'repayment':paid.json(),'logs':await warning_logs(f)},ensure_ascii=False,indent=2))
 asyncio.run(run())


def test_reimbursement_company_account_is_advisory_too(tmp_path,monkeypatch):
 async def run():
  async with reimb_env(tmp_path,monkeypatch) as (_,f,c):
   rid=await approved(c,amount=500);path=await upload(c,rid)
   async with f() as db:(await db.get(PaymentAccount,1)).opening_balance=-1000;await db.commit()
   before=(await balances(c))[1]
   result=await pay(c,rid,path);assert result.status_code==200,result.text
   check_warning(result.json()['warning'],before,500,before-500,'company_account')
   assert (await balances(c))[1]==before-500 and len(await warning_logs(f))==1
 asyncio.run(run())


def test_warning_history_failure_rolls_back_all_disbursement_writes(tmp_path,monkeypatch):
 async def run():
  from fastapi import HTTPException
  import app.services.balance_warning as service
  async with fund_env(tmp_path,monkeypatch) as (_,f,c,fid):
   async with f() as db:(await db.get(PaymentAccount,1)).opening_balance=-1000;await db.commit()
   before=await values(c,fid)
   async def fail(*args,**kwargs):raise HTTPException(500,'isolated warning history failure')
   monkeypatch.setattr(service,'record_history',fail)
   result=await topup(c,fid,amount=5000);assert result.status_code==500
   assert await values(c,fid)==before and await warning_logs(f)==[]
 asyncio.run(run())


async def actual_account_balance(f):
 async with f() as db:
  account=await db.get(PaymentAccount,1)
  return float((await current_account_balances(db,[account]))[1])


def test_protected_payroll_existing_negative_balance_guard_is_unchanged(tmp_path,monkeypatch):
 async def run():
  from tests.test_round3_permissions import hr_environment
  async with hr_environment(tmp_path,monkeypatch) as (_,f,c):
   async with f() as db:(await db.get(PaymentAccount,1)).opening_balance=-1000;await db.commit()
   before=await actual_account_balance(f)
   result=await c.post('/api/v1/payroll/2/disburse',headers=auth(1),json={'account_id':1})
   # User explicitly excluded this module; current main still hard-blocks here.
   assert result.status_code==400 and '公司账户余额不足' in result.text,result.text
   assert await actual_account_balance(f)==before
   (OUT/'step4-payroll-unchanged.json').write_text(json.dumps({'http_status':result.status_code,'response':result.json(),'balance_before':before,'balance_after':await actual_account_balance(f),'source_unchanged':True},ensure_ascii=False,indent=2))
 asyncio.run(run())


def test_protected_payable_existing_negative_balance_guard_is_unchanged(tmp_path,monkeypatch):
 async def run():
  from tests.test_supplier_workflow_round1 import setup
  async with setup(tmp_path,monkeypatch) as (_,f,c):
   async with f() as db:(await db.get(PaymentAccount,1)).opening_balance=-1000;await db.commit()
   before=await actual_account_balance(f)
   result=await c.put('/api/v1/payable/1/pay',headers=auth(1),params={'paid_amount':500,'account_id':1,'payment_method':'现金','request_key':'negative-balance-unchanged-payable'})
   assert result.status_code==400 and '公司账户余额不足' in result.text,result.text
   assert await actual_account_balance(f)==before
   (OUT/'step4-payable-unchanged.json').write_text(json.dumps({'http_status':result.status_code,'response':result.json(),'balance_before':before,'balance_after':await actual_account_balance(f),'source_unchanged':True},ensure_ascii=False,indent=2))
 asyncio.run(run())


def test_protected_fee_existing_negative_balance_guard_is_unchanged(tmp_path,monkeypatch):
 async def run():
  from tests.test_expense_approval_payment import fee_environment,create,pay
  async with fee_environment(tmp_path,monkeypatch) as (_,f,c):
   async with f() as db:(await db.get(PaymentAccount,1)).opening_balance=-1000;await db.commit()
   before=await actual_account_balance(f)
   fee=await create(c);result=await pay(c,fee['id'])
   assert result.status_code==400 and '公司账户余额不足' in result.text,result.text
   assert await actual_account_balance(f)==before
   (OUT/'step4-fee-unchanged.json').write_text(json.dumps({'http_status':result.status_code,'response':result.json(),'balance_before':before,'balance_after':await actual_account_balance(f),'source_unchanged':True},ensure_ascii=False,indent=2))
 asyncio.run(run())

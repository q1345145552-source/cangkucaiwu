"""Real API money integration: same-transaction expenses, revocation and history."""
import asyncio, ast, json, subprocess
from datetime import date
from pathlib import Path
from decimal import Decimal
import pytest
from fastapi import HTTPException
from sqlalchemy import select, func
from app.models import PaymentAccount, Warehouse
from app.models.income_expense import ExpenseRecord, IncomeExpenseCategory
from app.models.payroll import PayrollRecord
from app.models.data_change_history import DataChangeHistory
from app.services.payroll_expense import backfill_payroll_categories
import app.services.payroll_expense as service
import app.api.v1.payroll as payroll
from tests.test_round2_permissions import auth, set_perms
from tests.test_round3_permissions import hr_environment as original_hr_environment, snapshot
from tests.round3_flow_support import prepare_payroll, historical_payroll, assert_disabled, grants
from contextlib import asynccontextmanager

@asynccontextmanager
async def hr_environment(tmp_path,monkeypatch):
 async with original_hr_environment(tmp_path,monkeypatch) as (engine,factory,c):
  await grants(factory)
  async with factory() as db:
   (await db.get(PaymentAccount,1)).opening_balance=100000
   await db.commit()
  yield engine,factory,c


async def cash(factory):
 async with factory() as db:
  db.add(PaymentAccount(id=3,warehouse_id=1,account_name='现金',account_type='cash',account_number='cash',currency='THB',status='active',opening_balance=100000))
  await db.commit()

async def rows(factory,model):
 async with factory() as db:return [tuple(r) for r in (await db.execute(select(model.__table__).order_by(model.id))).all()]


@pytest.mark.parametrize('uid',[3])
def test_disburse_reverse_reissue_and_reports(tmp_path,monkeypatch,uid):
 async def run():
  async with hr_environment(tmp_path,monkeypatch) as (engine,factory,c):
   from sqlalchemy import event
   @event.listens_for(engine.sync_engine, "connect")
   def sqlite_functions(conn, _):conn.create_function("to_char", 2, lambda value, fmt: str(value)[:7] if value else None)
   await engine.dispose()
   await cash(factory);await set_perms(factory,4,['工资'])
   await prepare_payroll(factory,c,2)
   before_old=(await snapshot(factory))[2]
   # A supervisor with only payroll permission can obtain the shared account list.
   accounts=await c.get('/api/v1/accounts',headers=auth(uid));assert accounts.status_code==200,accounts.text
   assert any(a['id']==3 and a['account_type']=='cash' for a in accounts.json()['data'])
   r=await c.post('/api/v1/payroll/2/disburse',headers=auth(uid),json={'account_id':3});assert r.status_code==200,r.text
   expense_id=r.json()['expense_record_id']
   assert r.json()['net_pay']==1234.56 and r.json()['account_id']==3
   async with factory() as db:
    rec=await db.get(PayrollRecord,2);expense=await db.get(ExpenseRecord,expense_id)
    assert rec.disbursed and rec.expense_record_id==expense.id
    assert Decimal(str(rec.net_pay))==Decimal(str(expense.amount))==Decimal('1234.56')
    assert expense.account_id==3 and expense.currency=='THB'
    assert expense.remark=='仓1 10-01到10-15 1人'
    assert expense.expense_date.date()==rec.disbursed_at.date()
    cat=await db.get(IncomeExpenseCategory,expense.category_id)
    assert (cat.name,cat.type,cat.category_group,cat.warehouse_id)==('员工工资','expense','operating',1)
   paylist=(await c.get('/api/v1/payroll',headers=auth(1))).json()['data']
   assert next(x for x in paylist if x['id']==2)['expense_record_id']==expense_id
   exp=await c.get('/api/v1/income-expense/expense?category_group=operating',headers=auth(1));assert exp.status_code==200,exp.text
   linked=next(x for x in exp.json()['data'] if x['id']==expense_id)
   assert linked['payroll_record_id']==2 and linked['amount']==1234.56
   ledger=await c.get('/api/v1/income-expense/ledger?source=manual&flow_type=expense',headers=auth(1));assert ledger.status_code==200,ledger.text
   assert ledger.json()['total_expense']==1234.56
   legacy_ledger_label=any(x['category_name']=='员工工资' and x['remark']=='仓1 10-01到10-15 1人' for x in ledger.json()['data'])
   summary=await c.get('/api/v1/income-expense/monthly-summary?category_group=operating',headers=auth(1))
   assert summary.status_code==200 and summary.json()["total_expense"]==1234.56,summary.text
   report=await c.get("/api/v1/reports/income-expense",headers=auth(1));assert report.status_code==200,report.text
   # A repeated payment cannot create another expense.
   again=await c.post('/api/v1/payroll/2/disburse',headers=auth(uid),json={'account_id':3});assert again.status_code==400
   assert len(await rows(factory,ExpenseRecord))==1
   update=await c.put(f'/api/v1/income-expense/expense/{expense_id}',headers=auth(1),data={'category_id':linked['category_id'],'account_id':3,'amount':999,'expense_date':'2026-10-16'})
   assert update.status_code==400 and '工资联动支出' in update.text
   delete=await c.delete(f'/api/v1/income-expense/expense/{expense_id}',headers=auth(1));assert delete.status_code==400
   revoke=await historical_payroll(factory,c,2)
   assert revoke['reversed_expense_id']==expense_id
   async with factory() as db:
    rec=await db.get(PayrollRecord,2)
    assert rec.status=='confirmed' and not rec.disbursed and rec.expense_record_id is None
    assert await db.get(ExpenseRecord,expense_id) is None
    history=(await db.execute(select(DataChangeHistory).where(DataChangeHistory.module=='expense',DataChangeHistory.operation_type=='delete'))).scalar_one()
    assert history.before_data['amount']==1234.56 and history.before_data['payroll_record_id']==2
    assert '因为撤销发放而冲销' in history.after_data['remark']
   ledger2=await c.get('/api/v1/income-expense/ledger?source=manual&flow_type=expense',headers=auth(1));assert ledger2.json()['total_expense']==0
   assert (await snapshot(factory))[2]==before_old
   # Explicit new confirmation after a synthetic historical reversal.
   await prepare_payroll(factory,c,2)
   # Reissue through a different account creates precisely one live expense.
   reissue=await c.post('/api/v1/payroll/2/disburse',headers=auth(uid),json={'account_id':1});assert reissue.status_code==200,reissue.text
   assert len(await rows(factory,ExpenseRecord))==1
   assert legacy_ledger_label,ledger.json()
   print('PAYROLL_EXPENSE',{'paid':r.json(),'expense':linked,'historical_fixture':revoke,'ledger_after':ledger2.json()['total_expense']})
 asyncio.run(run())


@pytest.mark.parametrize('kind',['missing','foreign','inactive','foreign_currency'])
def test_account_guards_no_writes(tmp_path,monkeypatch,kind):
 async def run():
  async with hr_environment(tmp_path,monkeypatch) as (_,factory,c):
   if kind in ('inactive','foreign_currency'):
    async with factory() as db:
     a=await db.get(PaymentAccount,1)
     if kind=='inactive':a.status='inactive'
     else:a.currency='USD'
     await db.commit()
   payload={} if kind=='missing' else {'account_id':2 if kind=='foreign' else 1}
   await prepare_payroll(factory,c,2)
   before=await snapshot(factory)
   for path,body in [('/payroll/2/disburse',payload),('/payroll/batch-disburse',{'record_ids':[2],**payload})]:
    r=await c.post('/api/v1'+path,headers=auth(3),json=body);assert r.status_code==400,r.text
   assert await snapshot(factory)==before and not await rows(factory,ExpenseRecord)
 asyncio.run(run())


def test_batch_one_expense_per_payroll_one_account_and_idempotence(tmp_path,monkeypatch):
 async def run():
  async with hr_environment(tmp_path,monkeypatch) as (_,factory,c):
   await cash(factory)
   async with factory() as db:
    (await db.get(PayrollRecord,1)).status='confirmed';(await db.get(PayrollRecord,1)).net_pay=100.01;await db.commit()
   await prepare_payroll(factory,c,1,2)
   invalid={'record_ids':[1,2,2,3],'account_id':3}
   denied=await c.post('/api/v1/payroll/batch-disburse',headers=auth(3),json=invalid)
   assert denied.status_code==400 and not await rows(factory,ExpenseRecord)
   body={'record_ids':[1,2],'account_id':3}
   r=await c.post('/api/v1/payroll/batch-disburse',headers=auth(3),json=body);assert r.status_code==200,r.text
   assert r.json()['count']==2 and r.json()['total_net']==1334.57
   async with factory() as db:
    expenses=(await db.execute(select(ExpenseRecord))).scalars().all()
    assert len(expenses)==2 and all(e.account_id==3 for e in expenses)
    assert Decimal(str(sum(e.amount for e in expenses)))==Decimal('1334.57')
    assert (await db.get(PayrollRecord,3)).expense_record_id is None
   again=await c.post('/api/v1/payroll/batch-disburse',headers=auth(3),json=body)
   assert again.status_code==409 and len(await rows(factory,ExpenseRecord))==2
   cross=await c.post('/api/v1/payroll/batch-disburse',headers=auth(1),json={'record_ids':[1,10],'account_id':3});assert cross.status_code==403
   print('PAYROLL_BATCH',r.json())
 asyncio.run(run())


@pytest.mark.parametrize('batch',[False,True])
def test_failed_expense_rolls_back_whole_payment(tmp_path,monkeypatch,batch):
 async def run():
  async with hr_environment(tmp_path,monkeypatch) as (_,factory,c):
   async with factory() as db:(await db.get(PayrollRecord,1)).status='confirmed';await db.commit()
   await prepare_payroll(factory,c,2)
   await prepare_payroll(factory,c,1)
   before=await snapshot(factory);history_before=await rows(factory,DataChangeHistory);calls=0
   original=service.record_history
   async def fail_after_flush(db,**kwargs):
    nonlocal calls
    calls+=1
    await original(db,**kwargs)
    await db.flush()
    if calls==(2 if batch else 1):raise HTTPException(500,'模拟记账失败')
   monkeypatch.setattr(service,'record_history',fail_after_flush)
   path='/api/v1/payroll/batch-disburse' if batch else '/api/v1/payroll/2/disburse'
   body={'account_id':1,**({'record_ids':[1,2]} if batch else {})}
   r=await c.post(path,headers=auth(3),json=body);assert r.status_code==500,r.text
   assert await snapshot(factory)==before
   assert not await rows(factory,ExpenseRecord)
   assert await rows(factory,DataChangeHistory)==history_before
 asyncio.run(run())


def test_failed_revocation_rolls_back_expense_and_payroll(tmp_path,monkeypatch):
 async def run():
  async with hr_environment(tmp_path,monkeypatch) as (_,factory,c):
   await prepare_payroll(factory,c,2)
   r=await c.post('/api/v1/payroll/2/disburse',headers=auth(3),json={'account_id':1});assert r.status_code==200,r.text
   before=await snapshot(factory);expenses=await rows(factory,ExpenseRecord);history=await rows(factory,DataChangeHistory)
   async def fail(db,**kwargs):
    await db.flush()
    raise HTTPException(500,'模拟撤销日志失败')
   monkeypatch.setattr(payroll,'record_history',fail)
   r=await c.post('/api/v1/payroll/2/revoke-disbursement',headers=auth(1));assert r.status_code==400 and '撤销功能已停用' in r.text
   assert await snapshot(factory)==before and await rows(factory,ExpenseRecord)==expenses and await rows(factory,DataChangeHistory)==history
 asyncio.run(run())


def test_categories_all_warehouses_idempotent_and_new_warehouse(tmp_path,monkeypatch):
 async def run():
  from app.services.default_categories import ensure_default_categories
  async with hr_environment(tmp_path,monkeypatch) as (engine,factory,c):
   original=await snapshot(factory)
   async with engine.begin() as conn:
    assert await backfill_payroll_categories(conn)==0
    assert await backfill_payroll_categories(conn)==0
   async with factory() as db:
    w=Warehouse(name='新仓',code='WH3');db.add(w);await db.flush()
    await ensure_default_categories(db,w.id);await db.flush()
    await ensure_default_categories(db,w.id);await db.flush()
    cats=(await db.execute(select(IncomeExpenseCategory).where(IncomeExpenseCategory.name=='员工工资').order_by(IncomeExpenseCategory.warehouse_id))).scalars().all()
    assert [(x.warehouse_id,x.type,x.category_group) for x in cats]==[(1,'expense','operating'),(2,'expense','operating'),(3,'expense','operating')]
    await db.commit()
    print('PAYROLL_CATEGORIES',[(x.id,x.warehouse_id,x.name,x.category_group) for x in cats])
   assert await snapshot(factory)==original and not await rows(factory,ExpenseRecord)
 asyncio.run(run())


def test_calculation_and_other_modules_unchanged():
 root=Path(__file__).resolve().parents[2];name='backend/app/api/v1/payroll.py'
 def functions(source):return {n.name:ast.dump(n,include_attributes=False) for n in ast.parse(source).body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name not in {'_batch_fetch','batch_disburse_payroll','disburse_payroll','revoke_disbursement','list_payroll','my_payslip'}}
 assert functions(subprocess.check_output(['git','show','2102711:'+name],cwd=root,text=True))==functions(subprocess.check_output(['git','show','15d53fa:'+name],cwd=root,text=True))
 assert not subprocess.check_output(['git','diff','15d53fa','2102711','--','frontend','backend/app/api/v1/expense_fund.py','backend/app/api/v1/reimbursement.py'],cwd=root)


@pytest.mark.parametrize('amount,expected',[(0,200),(-1,400),(1234.567,400)])
def test_exact_cent_amount_or_reject(tmp_path,monkeypatch,amount,expected):
 async def run():
  async with hr_environment(tmp_path,monkeypatch) as (_,factory,c):
   async with factory() as db:(await db.get(PayrollRecord,2)).net_pay=amount;await db.commit()
   await prepare_payroll(factory,c,2)
   before=await snapshot(factory)
   r=await c.post('/api/v1/payroll/2/disburse',headers=auth(3),json={'account_id':1});assert r.status_code==expected,r.text
   if expected==400:
    assert await snapshot(factory)==before and not await rows(factory,ExpenseRecord)
   else:
    async with factory() as db:assert (await db.get(ExpenseRecord,r.json()['expense_record_id'])).amount==0
 asyncio.run(run())


def test_missing_category_rejects_without_changing_payroll(tmp_path,monkeypatch):
 async def run():
  from sqlalchemy import delete
  async with hr_environment(tmp_path,monkeypatch) as (_,factory,c):
   async with factory() as db:
    await db.execute(delete(IncomeExpenseCategory).where(IncomeExpenseCategory.name=='员工工资'));await db.commit()
   await prepare_payroll(factory,c,2)
   before=await snapshot(factory)
   r=await c.post('/api/v1/payroll/2/disburse',headers=auth(3),json={'account_id':1})
   assert r.status_code==400 and '启动迁移' in r.text
   assert await snapshot(factory)==before and not await rows(factory,ExpenseRecord)
 asyncio.run(run())

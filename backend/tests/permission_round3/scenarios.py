from fixtures import *
from app.models.cash_advance import CashAdvance
from app.models.reimbursement_payment import ReimbursementPayment
from app.models.wallet import PayablePayment
from app.models.data_change_history import DataChangeHistory
from app.models.clock_in_records import ClockInRecord
from app.services import reimbursement_payment as rp
import app.api.v1.payroll as payroll_api

async def scenarios(factory,client,call,log,fail):
 def unchanged(a,b,r):
  for t in ('expense_records','payable_payments','reimbursement_payments','cash_advance_repayments','expense_funds'):
   assert a[t]==b[t],t
 async def payroll(rid,employee=1,warehouse=1):
  async with factory() as db:
   db.add(PayrollRecord(id=rid,employee_id=employee,warehouse_id=warehouse,period='2026-10',settle_start_date=date(2026,10,1),settle_end_date=date(2026,10,15),status='pending',net_pay=100,base_pay=100,gross_pay=100,total_deductions=0,overtime_pay=0,detail='{}'));await db.commit()
 async def approve_salary(rid):await call(f'A-confirm-{rid}',1,'POST',f'/payroll/{rid}/confirm',check=unchanged)
 async def bill(bid,creator=2,warehouse=1,amount=100):
  async with factory() as db:
   db.add(PayableBill(id=bid,warehouse_id=warehouse,supplier_id=warehouse,bill_number=f'SYNTHETIC-R3-{bid}',bill_date=datetime(2026,10,20),due_date=datetime(2026,10,30),amount=amount,currency='THB',matching_kind='non_goods',status='pending',created_by=creator));await db.commit()
 async def approve_bill(bid):
  await call(f'D-verify-{bid}',3,'POST',f'/payable/{bid}/verify-payment',check=unchanged)
  await call(f'D-approve-{bid}',1,'POST',f'/payable/{bid}/approve-payment',check=unchanged)
 async def reimb(uid=2):
  made=await call('B-create-extra-'+str(len(log)),uid,'POST','/reimbursement',{'submit_date':'2026-10-20','items':[{'category':'其他','amount':30},{'category':'其他','amount':10}]})
  rid=made['id'];detail=await call('B-read-extra-'+str(rid),uid,'GET',f'/reimbursement/{rid}')
  return rid,[{'item_id':d['id'],'status':'approved' if i==0 else 'rejected'} for i,d in enumerate(detail['items'])]
 async def approve_reimb(rid,items,verifier=3):
  await call('B-verify-extra-'+str(rid),verifier,'POST',f'/reimbursement/{rid}/verify',check=unchanged)
  await call('B-approve-extra-'+str(rid),1,'POST',f'/reimbursement/{rid}/review',{'items':items},check=unchanged)
 paybody={'payment_account_id':1,'payment_voucher_path':'uploads/1/2026-10/reimbursement-payments/proof.png'}
 async def concurrent(name,requests,table,identity,amount):
  before=await snapshot(factory)
  async def send(uid,method,path,body):
   r=await client.request(method,'/api/v1'+path,json=body,headers={'Authorization':'Bearer '+create_access_token({'sub':str(uid)})})
   return {'status':r.status_code,'response':r.json()}
  result=await asyncio.gather(*(send(*r) for r in requests));after=await snapshot(factory);errors=[]
  added=[r for r in after[table] if r not in before[table]]
  try:
   assert sum(r['status']==200 for r in result)==1,result
   assert all(r['status'] in (200,400,409) for r in result),result
   assert len(added)==1 and float(added[0]['amount'])==amount,added
  except Exception as e:errors.append(repr(e));fail.append(name+str(e))
  log.append({'id':name,'requests':requests,'responses':result,'expected':'one successful financial effect only','database_diff':{t:{'before':before[t],'after':after[t]} for t in before if before[t]!=after[t]},'errors':errors});print(name,result,errors or 'PASS',flush=True)
 # Additional identity samples: historical all-grants alias and finance without grants.
 async with factory() as db:
  db.add_all([User(id=90,username='r3-alias',display_name='SYNTHETIC alias',role='staff',warehouse_id=1,password_hash='synthetic',attendance_employee_id=3,extra_permissions=ALL,is_active=True),User(id=91,username='r3-no-grants',display_name='SYNTHETIC no grants',role='staff',warehouse_id=1,password_hash='synthetic',extra_permissions=[],is_active=True)])
  await db.commit()
 # Every management payroll action is capped for a historical-all-grants supervisor.
 for method,path,body in [('POST','/payroll/preview',{'end_date':'2026-10-16'}),('POST','/payroll/single-settle',{'employee_id':1,'end_date':'2026-10-16'}),('POST','/payroll/confirm-all?period=2026-10',None),('POST','/payroll/batch-confirm',{'record_ids':[1]}),('POST','/payroll/batch-disburse',{'record_ids':[1],'account_id':1}),('POST','/payroll/batch-delete',{'record_ids':[1]}),('POST','/payroll/1/recalc',{'void_reason':'SYNTHETIC'}),('POST','/payroll/batch-recalc',{'record_ids':[1],'void_reason':'SYNTHETIC'}),('DELETE','/payroll/1',None),('DELETE','/payroll/period/2026-10',None),('GET','/payroll',None),('GET','/payroll/export',None)]:
  await call('A-supervisor-cap-'+path,2,method,path,body,403)
 await call('A-no-grants',91,'POST','/payroll/calculate',{'end_date':'2026-10-16'},403)
 await call('A-foreign-employee-mixed',3,'POST','/payroll/calculate',{'employee_ids':[1,8],'end_date':'2026-10-16'},403)
 await call('A-internal-params',3,'POST','/payroll/calculate',{'recalc_employee_id':1,'end_date':'2026-10-16'},400)
 await call('A-forged-resignation-mode',3,'POST','/payroll/calculate',{'employee_ids':[1],'end_date':'2026-10-16','is_resignation':True},400)
 await call('A-legacy-confirmed-denied',3,'POST','/payroll/2/disburse',{'account_id':1},409)
 await payroll(100);await payroll(101,warehouse=2,employee=8)
 await call('A-mixed-confirm-atomic',1,'POST','/payroll/batch-confirm',{'record_ids':[100,101]},403)
 await approve_salary(100)
 async with factory() as db:(await db.get(PayrollRecord,100)).net_pay=101;await db.commit()
 await call('A-changed-money',3,'POST','/payroll/100/disburse',{'account_id':1},409)
 await payroll(102);await approve_salary(102)
 async with factory() as db:
  db.add(RestDay(employee_id=1,warehouse_id=1,rest_date=date(2026,10,3)));await db.commit()
 await call('A-changed-facts',3,'POST','/payroll/102/disburse',{'account_id':1},409)
 await payroll(103,employee=3);await approve_salary(103)
 await call('A-finance-self-pay',3,'POST','/payroll/103/disburse',{'account_id':1},403)
 await call('A-alias-self-pay',90,'POST','/payroll/103/disburse',{'account_id':1},403)
 await call('A-admin-pay-finance',1,'POST','/payroll/103/disburse',{'account_id':1})
 await call('A-paid-delete-denied',1,'DELETE','/payroll/103',status=409)
 await payroll(104);await payroll(105);await approve_salary(104)
 await call('A-mixed-unconfirmed-pay-atomic',3,'POST','/payroll/batch-disburse',{'record_ids':[104,105],'account_id':1},409)
 await call('A-mixed-paid-delete-atomic',1,'POST','/payroll/batch-delete',{'record_ids':[105,103]},409)
 await call('A-finance-delete-confirmed',3,'DELETE','/payroll/104',status=403)
 await call('A-finance-delete-draft',3,'DELETE','/payroll/105')
 await concurrent('A-concurrent-pay',[(3,'POST','/payroll/104/disburse',{'account_id':1}),(4,'POST','/payroll/104/disburse',{'account_id':1})],'expense_records','id',100)
 await payroll(106);await approve_salary(106)
 original=payroll_api.create_payroll_expense
 async def broken_payroll(*args,**kwargs):
  await original(*args,**kwargs);raise RuntimeError('SYNTHETIC failure after wage expense')
 payroll_api.create_payroll_expense=broken_payroll
 try:await call('A-execution-rollback',3,'POST','/payroll/106/disburse',{'account_id':1},500)
 finally:payroll_api.create_payroll_expense=original
 await call('A-retry-after-rollback',4,'POST','/payroll/106/disburse',{'account_id':1})
 await call('A-forged-header',1,'POST','/payroll/1/confirm',status=403,headers={'X-Warehouse-ID':'2'})
 def no_payroll_effect(a,b,r):assert a['payroll_records']==b['payroll_records'] and a['expense_records']==b['expense_records']
 await call('A-resignation-fact-only',2,'POST','/employees/4/resign',{'reason':'voluntary','resignation_date':'2026-10-15'},check=no_payroll_effect)
 await call('A-finance-resignation-pending',3,'GET','/payroll/pending-resignations')
 await payroll(110);await payroll(111,employee=3)
 await call('A-valid-batch-confirm',1,'POST','/payroll/batch-confirm',{'record_ids':[110,111]},check=unchanged)
 def two_wages(a,b,r):
  rows=[x for x in b['expense_records'] if x['id'] not in {y['id'] for y in a['expense_records']}]
  assert len(rows)==2 and sum(float(x['amount']) for x in rows)==200,rows
 await call('A-valid-batch-pay',4,'POST','/payroll/batch-disburse',{'record_ids':[110,111],'account_id':1},check=two_wages)
 await payroll(112)
 async with factory() as db:(await db.get(PayrollRecord,112)).settle_end_date=date(2026,10,16);await db.commit()
 await approve_salary(112)
 await call('A-finance-confirmed-recalc-denied',3,'POST','/payroll/112/recalc',{'void_reason':'SYNTHETIC'},403)
 made=await call('A-admin-confirmed-recalc',1,'POST','/payroll/112/recalc',{'void_reason':'SYNTHETIC'})
 await call('A-recalc-needs-new-confirmation',3,'POST',f"/payroll/{made.get('new_record_id',99999)}/disburse",{'account_id':1},400,check=lambda a,b,r: r['detail']=='请先确认工资单再发放' or (_ for _ in ()).throw(AssertionError(r)))
 # Ordinary reimbursement: self/alias, batch ownership, stale contents, explicit return, repeat/concurrency/rollback.
 rid,items=await reimb(3)
 await call('B-self-verify',3,'POST',f'/reimbursement/{rid}/verify',status=403)
 await approve_reimb(rid,items,4)
 await call('B-self-pay',3,'POST',f'/reimbursement/{rid}/pay',paybody,403)
 await call('B-alias-pay',90,'POST',f'/reimbursement/{rid}/pay',paybody,403)
 await call('B-independent-pay',4,'POST',f'/reimbursement/{rid}/pay',paybody)
 await call('B-paid-submit',3,'POST',f'/reimbursement/{rid}/submit',status=400)
 await call('B-paid-review',1,'POST',f'/reimbursement/{rid}/review',{'items':items},400)
 await call('B-supervisor-delete-other',2,'DELETE',f'/reimbursement/{rid}',status=403)
 rid,items=await reimb()
 await call('B-missing-verify',3,'POST',f'/reimbursement/{rid}/verify')
 await call('B-missing-line-decision',1,'POST',f'/reimbursement/{rid}/review',{'items':items[:1]},400)
 await call('B-finance-approve-denied',3,'POST',f'/reimbursement/{rid}/review',{'items':items},403)
 await call('B-mixed-parent',1,'POST',f'/reimbursement/{rid}/review',{'items':[items[0],{'item_id':8,'status':'approved'}]},400)
 await call('B-approve-current',1,'POST',f'/reimbursement/{rid}/review',{'items':items})
 await call('B-edit-approved',2,'PUT',f'/reimbursement/{rid}',{'submit_date':'2026-10-20','items':[{'category':'其他','amount':40}]},400)
 await call('B-return',1,'POST',f'/reimbursement/{rid}/return-to-draft')
 await call('B-old-verify-invalid',1,'POST',f'/reimbursement/{rid}/review',{'items':items},409)
 await approve_reimb(rid,items)
 async with factory() as db:(await db.get(ReimbursementItem,items[0]['item_id'])).description='SYNTHETIC changed';await db.commit()
 await call('B-stale-line-pay',3,'POST',f'/reimbursement/{rid}/pay',paybody,409)
 rid,items=await reimb();await approve_reimb(rid,items)
 await concurrent('B-concurrent-pay',[(3,'POST',f'/reimbursement/{rid}/pay',paybody),(4,'POST',f'/reimbursement/{rid}/pay',paybody)],'reimbursement_payments','reimbursement_id',30)
 rid,items=await reimb();await approve_reimb(rid,items)
 original_history=rp.record_history
 async def fail_history(*args,**kwargs):raise RuntimeError('SYNTHETIC failure after ordinary payment flush')
 rp.record_history=fail_history
 try:await call('B-pay-rollback',3,'POST',f'/reimbursement/{rid}/pay',paybody,500)
 finally:rp.record_history=original_history
 await call('B-pay-after-rollback',3,'POST',f'/reimbursement/{rid}/pay',paybody)
 rid,items=await reimb();items=[{**i,'status':'approved'} for i in items];await approve_reimb(rid,items)
 await call('B-full-approved-pay',3,'POST',f'/reimbursement/{rid}/pay',paybody)
 rid,items=await reimb();items=[{**i,'status':'rejected'} for i in items];await approve_reimb(rid,items)
 await call('B-rejected-pay-denied',3,'POST',f'/reimbursement/{rid}/pay',paybody,400)
 # Employee advance: on-behalf beneficiary is financial A; request registration never pays.
 async def request_advance(employee=3,source='company_account',**extra):
  body={'employee_id':employee,'amount':10,'advance_date':'2026-10-20','funding_source':source,**extra}
  if source=='company_account':body['payment_account_id']=1
  return await call('C-request-extra-'+str(len(log)),2,'POST','/employee-advances',body,check=unchanged)
 adv=await request_advance();aid=adv.get('id',99999)
 await call('C-on-behalf-self-verify',3,'POST',f'/employee-advances/{aid}/verify',status=403)
 await call('C-independent-verify',4,'POST',f'/employee-advances/{aid}/verify',check=unchanged)
 await call('C-self-approve-role',3,'POST',f'/employee-advances/{aid}/approve',status=403)
 await call('C-admin-approve-finance',1,'POST',f'/employee-advances/{aid}/approve',check=unchanged)
 await call('C-on-behalf-self-execute',3,'POST',f'/employee-advances/{aid}/execute',status=403)
 await call('C-alias-self-execute',90,'POST',f'/employee-advances/{aid}/execute',status=403)
 await call('C-admin-execute-finance',1,'POST',f'/employee-advances/{aid}/execute')
 adv=await request_advance(1);aid=adv.get('id',99999)
 await call('C-verify-stale',3,'POST',f'/employee-advances/{aid}/verify')
 await call('C-approve-stale',1,'POST',f'/employee-advances/{aid}/approve')
 async with factory() as db:
  row=await db.get(EmployeeAdvance,aid)
  if row:row.amount=11;await db.commit()
 await call('C-stale-execute',3,'POST',f'/employee-advances/{aid}/execute',status=409)
 await call('C-legacy-auto-approved',3,'POST','/employee-advances/1/execute',status=409)
 # Funds/loans: approved source may be used, without duplicate costs.
 adv=await request_advance(1,'expense_fund',fund_account_id=1);aid=adv.get('id',99999)
 await call('C-fund-verify',3,'POST',f'/employee-advances/{aid}/verify')
 await call('C-fund-approve',1,'POST',f'/employee-advances/{aid}/approve',check=unchanged)
 await call('C-fund-execute',4,'POST',f'/employee-advances/{aid}/execute')
 # Cash debts: verify, independent approval, independent execution, aliases, stale proof and rollback.
 import app.api.v1.cash_advance as cash_api
 import app.api.v1.employee_advance as advance_api
 async def cash(payer=2,creator=2):
  data=await call('C-cash-extra-'+str(len(log)),creator,'POST','/cash-advances',{'advance_date':'2026-10-20','amount':25,'purpose':'expense','payer_id':payer},check=unchanged)
  return data['id']
 async def approve_cash(cid,verifier=3):
  await call('C-cash-verify-'+str(cid),verifier,'POST',f'/cash-advances/{cid}/verify',check=unchanged)
  await call('C-cash-approve-'+str(cid),1,'POST',f'/cash-advances/{cid}/confirm',check=unchanged)
 cashpay={'amount':25,'account_id':1,'payment_method':'cash','voucher_path':'uploads/1/2026-10/cash-advances/proof.png'}
 cid=await cash(3)
 await call('C-cash-unapproved',4,'POST',f'/cash-advances/{cid}/repayments',cashpay,409)
 await call('C-cash-beneficiary-verify',3,'POST',f'/cash-advances/{cid}/verify',status=403)
 await approve_cash(cid,4)
 await call('C-cash-self-pay',3,'POST',f'/cash-advances/{cid}/repayments',cashpay,403)
 await call('C-cash-alias-pay',90,'POST',f'/cash-advances/{cid}/repayments',cashpay,403)
 await call('C-cash-admin-finance-pay',1,'POST',f'/cash-advances/{cid}/repayments',cashpay)
 await call('C-cash-paid-repeat',4,'POST',f'/cash-advances/{cid}/repayments',cashpay,400)
 cid=await cash();await approve_cash(cid)
 await concurrent('C-cash-concurrent',[(3,'POST',f'/cash-advances/{cid}/repayments',cashpay),(4,'POST',f'/cash-advances/{cid}/repayments',cashpay)],'cash_advance_repayments','cash_advance_id',25)
 cid=await cash();await approve_cash(cid)
 old=cash_api.record_history
 async def cash_failure(*a,**kw):raise RuntimeError('SYNTHETIC failure after repayment flush')
 cash_api.record_history=cash_failure
 try:await call('C-cash-rollback',3,'POST',f'/cash-advances/{cid}/repayments',cashpay,500)
 finally:cash_api.record_history=old
 await call('C-cash-after-rollback',4,'POST',f'/cash-advances/{cid}/repayments',cashpay)
 cid=await cash();await approve_cash(cid)
 async with factory() as db:(await db.get(CashAdvance,cid)).amount=26;await db.commit()
 await call('C-cash-stale',3,'POST',f'/cash-advances/{cid}/repayments',cashpay,409)
 cid=await cash();await approve_cash(cid)
 await call('C-cash-foreign-account',3,'POST',f'/cash-advances/{cid}/repayments',{**cashpay,'account_id':2},400)
 await call('C-cash-foreign-user',8,'POST',f'/cash-advances/{cid}/repayments',cashpay,404)
 async with factory() as db:
  account=await db.get(PaymentAccount,1);opening=account.opening_balance;account.opening_balance=0;await db.commit()
 await call('C-cash-insufficient-balance',3,'POST',f'/cash-advances/{cid}/repayments',cashpay,400)
 async with factory() as db:(await db.get(PaymentAccount,1)).opening_balance=opening;await db.commit()

 adv=await request_advance(1);cid=adv['id']
 await call('C-concurrent-verify',3,'POST',f'/employee-advances/{cid}/verify')
 await call('C-concurrent-approve',1,'POST',f'/employee-advances/{cid}/approve')
 await concurrent('C-advance-concurrent',[(3,'POST',f'/employee-advances/{cid}/execute',None),(4,'POST',f'/employee-advances/{cid}/execute',None)],'expense_records','id',10)
 adv=await request_advance(1);cid=adv['id']
 await call('C-rollback-verify',3,'POST',f'/employee-advances/{cid}/verify')
 await call('C-rollback-approve',1,'POST',f'/employee-advances/{cid}/approve')
 old=advance_api.apply_advance_funding
 async def advance_failure(*a,**kw):
  await old(*a,**kw);raise RuntimeError('SYNTHETIC after advance funding')
 advance_api.apply_advance_funding=advance_failure
 try:await call('C-advance-rollback',3,'POST',f'/employee-advances/{cid}/execute',status=500)
 finally:advance_api.apply_advance_funding=old
 await call('C-advance-after-rollback',4,'POST',f'/employee-advances/{cid}/execute')
 cid=await cash();await approve_cash(cid)
 adv=await request_advance(1,'cash_advance',cash_advance_id=cid);cash_aid=adv['id']
 await call('C-cash-source-verify',3,'POST',f'/employee-advances/{cash_aid}/verify')
 await call('C-cash-source-approve',1,'POST',f'/employee-advances/{cash_aid}/approve',check=unchanged)
 await call('C-cash-source-execute',4,'POST',f'/employee-advances/{cash_aid}/execute')
 adv=await request_advance(1);rejected_id=adv['id']
 await call('C-explicit-reject',1,'POST',f'/employee-advances/{rejected_id}/reject',{'reject_reason':'SYNTHETIC refused'},check=unchanged)
 await call('C-rejected-execute',3,'POST',f'/employee-advances/{rejected_id}/execute',status=409)
 adv=await request_advance(1);void_id=adv['id']
 await call('C-void-pending',1,'DELETE',f'/employee-advances/{void_id}',{'void_reason':'SYNTHETIC cancelled'})
 await call('C-void-execute',3,'POST',f'/employee-advances/{void_id}/execute',status=409)
 cid=await cash()
 await call('C-cash-reject',1,'POST',f'/cash-advances/{cid}/reject',{'reject_reason':'SYNTHETIC refused'},check=unchanged)
 await call('C-cash-rejected-pay',3,'POST',f'/cash-advances/{cid}/repayments',cashpay,409)
 # Every financial module denies disabled/no-grants/cross-warehouse operators.
 for uid in (5,6,7,8,91):
  expected=401 if uid==7 else 403
  await call(f'B-pay-role-{uid}',uid,'POST',f'/reimbursement/{rid}/pay',paybody,expected)
  await call(f'C-execute-role-{uid}',uid,'POST',f'/employee-advances/{aid}/execute',status=expected)
 # Supplier payments: partial budgets, direct/plan parity, mixed invalid parents, stale plan and bill.
 await bill(200);await approve_bill(200)
 await call('D-partial-pay',3,'PUT','/payable/200/pay?paid_amount=20&account_id=1')
 await call('D-remaining-pay',4,'PUT','/payable/200/pay?paid_amount=80&account_id=1')
 await call('D-no-repeat',3,'PUT','/payable/200/pay?account_id=1',status=400)
 await bill(201);await approve_bill(201)
 await call('D-sup-plan-create',2,'POST','/payable/plans',{'plan_name':'SYNTHETIC','planned_date':'2026-10-28','bill_ids':[201]},403)
 plan=await call('D-plan-create',3,'POST','/payable/plans',{'plan_name':'SYNTHETIC','planned_date':'2026-10-28','bill_ids':[201]},check=unchanged);pid=plan.get('id',99999)
 await call('D-sup-plan-execute',2,'PUT',f'/payable/plans/{pid}/execute?account_id=1',status=403)
 await call('D-plan-execute',3,'PUT',f'/payable/plans/{pid}/execute?account_id=1')
 await call('D-plan-repeat',4,'PUT',f'/payable/plans/{pid}/execute?account_id=1',status=400)
 await bill(202);await approve_bill(202);await bill(203,warehouse=2)
 await call('D-cross-plan-create',3,'POST','/payable/plans',{'plan_name':'SYNTHETIC invalid','planned_date':'2026-10-28','bill_ids':[202,203]},403)
 plan=await call('D-plan-stale-create',3,'POST','/payable/plans',{'plan_name':'SYNTHETIC','planned_date':'2026-10-28','bill_ids':[202]});pid=plan.get('id',99999)
 async with factory() as db:(await db.get(PayablePlan,pid)).total_amount=99;await db.commit()
 await call('D-plan-stale-execute',3,'PUT',f'/payable/plans/{pid}/execute?account_id=1',status=409)
 async with factory() as db:(await db.get(PayableBill,202)).amount=101;await db.commit()
 await call('D-stale-bill-pay',3,'PUT','/payable/202/pay?account_id=1',status=409)
 await bill(204);await approve_bill(204)
 await concurrent('D-concurrent-pay',[(3,'PUT','/payable/204/pay?account_id=1',None),(4,'PUT','/payable/204/pay?account_id=1',None)],'payable_payments','bill_id',100)
 await bill(205);await approve_bill(205);await bill(206)
 plan=await call('D-mixed-plan-create',3,'POST','/payable/plans',{'plan_name':'SYNTHETIC mixed','planned_date':'2026-10-28','bill_ids':[205,206]})
 await call('D-mixed-unapproved-plan-atomic',3,'PUT',f"/payable/plans/{plan['id']}/execute?account_id=1",status=409)
 await approve_bill(206)
 import app.services.payable_payment as pp
 old=pp.record_history
 async def bill_failure(*a,**kw):raise RuntimeError('SYNTHETIC after payment flush')
 pp.record_history=bill_failure
 try:await call('D-plan-rollback',3,'PUT',f"/payable/plans/{plan['id']}/execute?account_id=1",status=500)
 finally:pp.record_history=old
 await call('D-plan-after-rollback',4,'PUT',f"/payable/plans/{plan['id']}/execute?account_id=1")
 # Direct payment scope and self/alias restrictions also apply to legitimate approved objects.
 await bill(207,creator=3)
 await call('D-finance-self-verify',3,'POST','/payable/207/verify-payment',status=403)
 await call('D-other-finance-verify',4,'POST','/payable/207/verify-payment')
 await call('D-admin-approve-finance',1,'POST','/payable/207/approve-payment')
 await call('D-finance-self-pay',3,'PUT','/payable/207/pay?account_id=1',status=403)
 await call('D-finance-alias-pay',90,'PUT','/payable/207/pay?account_id=1',status=403)
 await call('D-foreign-operator',8,'PUT','/payable/207/pay?account_id=1',status=403)
 await call('D-foreign-account',4,'PUT','/payable/207/pay?account_id=2',status=400)
 for uid in (5,6,7,91):
  await call(f'D-role-deny-{uid}',uid,'PUT','/payable/207/pay?account_id=1',status=401 if uid==7 else 403)
 await call('D-admin-independent-finance-payment',1,'PUT','/payable/207/pay?account_id=1')
 await payroll(120);await approve_salary(120)
 await call('A-foreign-payment-account',3,'POST','/payroll/120/disburse',{'account_id':2},400)
 rid,items=await reimb();await approve_reimb(rid,items)
 await call('B-foreign-payment-account',3,'POST',f'/reimbursement/{rid}/pay',{**paybody,'payment_account_id':2},400)
 await call('B-foreign-parent-verify',3,'POST','/reimbursement/8/verify',status=403)
 async with factory() as db:(await db.get(PaymentAccount,1)).status='inactive';await db.commit()
 await call('B-disabled-payment-account',3,'POST',f'/reimbursement/{rid}/pay',paybody,400)
 async with factory() as db:(await db.get(PaymentAccount,1)).status='active';(await db.get(PaymentAccount,1)).currency='CNY';await db.commit()
 await call('B-wrong-currency-account',3,'POST',f'/reimbursement/{rid}/pay',paybody,400)
 async with factory() as db:(await db.get(PaymentAccount,1)).currency='THB';await db.commit()
 for uid in (2,3,4):
  await call(f'T13-payroll-reversal-{uid}',uid,'POST','/payroll/3/revoke-disbursement',{},400 if uid!=2 else 403)
  await call(f'T13-reimb-reversal-{uid}',uid,'POST','/reimbursement/1/revoke-payment',{},400)
  await call(f'T13-cash-reversal-{uid}',uid,'POST','/cash-advances/repayments/1/revoke',{},400)

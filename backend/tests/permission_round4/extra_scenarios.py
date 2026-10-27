from fixtures import *
async def scenarios(factory,client,call,LOG,FAIL):
 from app.models.income_expense import IncomeRecord,ExpenseRecord
 from app.models.customer import Customer
 def unchanged_money(a,b,r):
  for table in ('expense_records','income_records','incoming_flows','clock_in_records'):
   assert a[table]==b[table],table
 def one_new(table,amount):
  def check(a,b,r):
   new=[x for x in b[table] if x['id'] not in {x['id'] for x in a[table]}]
   assert len(new)==1 and new[0]['amount']==amount,new
  return check
 body={'category_id':50,'account_id':1,'amount':20,'currency':'THB','income_date':'2026-10-22','request_key':'r04-income'}
 income=await call('A-finance-income',3,'POST','/income-expense/income',body,check=one_new('income_records',20))
 await call('A-finance-income-repeat',3,'POST','/income-expense/income',body,check=unchanged_money)
 await call('A-finance-income-update',3,'PUT',f"/income-expense/income/{income['id']}",{**body,'amount':25})
 await call('A-finance-income-delete',3,'DELETE',f"/income-expense/income/{income['id']}")
 expense={'category_id':'4','account_id':'1','amount':'12','currency':'THB','expense_date':'2026-10-22','request_key':'r04-expense','remark':'SYNTHETIC'}
 exp=await call('A-finance-expense',3,'POST','/income-expense/expense',data=expense,check=one_new('expense_records',12))
 await call('A-finance-expense-repeat',3,'POST','/income-expense/expense',data=expense,check=unchanged_money)
 for uid in (2,6):
  await call(f'A-supervisor-expense-{uid}',uid,'POST','/income-expense/expense',data=expense,status=403)
  await call(f'A-supervisor-edit-expense-{uid}',uid,'PUT',f"/income-expense/expense/{exp['id']}",data=expense,status=403)
  await call(f'A-supervisor-delete-expense-{uid}',uid,'DELETE',f"/income-expense/expense/{exp['id']}",status=403)
 async with factory() as db:
  generated=ExpenseRecord(warehouse_id=1,category_id=4,account_id=1,amount=10,currency='THB',expense_date=datetime(2026,10,22))
  db.add(generated);await db.flush();gid=generated.id
  approval=await db.get(ExpenseApproval,1);approval.expense_record_id=gid;approval.status='paid';await db.commit()
 await call('A-approved-source-edit',3,'PUT',f'/income-expense/expense/{gid}',data={k:v for k,v in expense.items() if k!='request_key'},status=400)
 await call('A-approved-source-delete',1,'DELETE',f'/income-expense/expense/{gid}',status=400)
 await call('A-finance-cross-account',3,'POST','/income-expense/income',{**body,'account_id':2,'request_key':'r04-foreign'},400)
 incoming={'account_id':1,'amount':30,'currency':'THB','received_date':'2026-10-22','request_key':'r04-incoming'}
 flow=await call('A-finance-incoming',3,'POST','/incoming',incoming,check=one_new('incoming_flows',30))
 await call('A-finance-incoming-repeat',3,'POST','/incoming',incoming,check=unchanged_money)
 await call('A-mixed-import',3,'POST','/incoming/batch-import',{'request_key':'r04-mixed','records':[{k:v for k,v in incoming.items() if k!='request_key'},{'warehouse_id':2,**incoming}]},403)
 # Fault after an actual INSERT proves transaction rollback; no auth or money function is faked.
 import app.services.manual_wallet as wallet
 original=wallet.insert_once
 async def fail_after_insert(*args,**kwargs):
  await original(*args,**kwargs);raise RuntimeError('SYNTHETIC failure after actual insert')
 wallet.insert_once=fail_after_insert
 try:await call('A-insert-rollback',3,'POST','/income-expense/income',{**body,'request_key':'r04-fault'},500)
 finally:wallet.insert_once=original
 await call('A-after-rollback-retry',3,'POST','/income-expense/income',{**body,'request_key':'r04-fault'},check=one_new('income_records',20))
 # Concurrent same-key operations must commit one receipt only.
 before=await snapshot(factory)
 responses=await asyncio.gather(*[client.post('/api/v1/incoming',json={**incoming,'request_key':'r04-concurrent'},headers={'Authorization':'Bearer '+create_access_token({'sub':'3'})}) for _ in range(2)])
 after=await snapshot(factory);errors=[]
 try:
  assert [r.status_code for r in responses]==[200,200]
  new=[x for x in after['incoming_flows'] if x['id'] not in {x['id'] for x in before['incoming_flows']}]
  assert len(new)==1 and new[0]['amount']==30
 except Exception as e:errors.append(repr(e));FAIL.append('A-concurrency: '+repr(e))
 LOG.append({'id':'A-concurrent-incoming','requests':[{'actual':r.status_code,'response':r.json()} for r in responses], 'database_diff':{t:{'before':before[t],'after':after[t]} for t in before if before[t]!=after[t]},'errors':errors})
 async with factory() as db:
  db.add(Customer(id=1,warehouse_id=1,customer_code='SYNTHETIC',company_name='SYNTHETIC'))
  await db.flush();db.add(RechargeDeclaration(id=1,warehouse_id=1,customer_id=1,declare_date=datetime(2026,10,22),amount=30,currency='THB',declarer_id=2,screenshot='synthetic.png'))
  await db.commit()
 await call('A-finance-match',3,'POST',f"/reconciliation/manual-match?declaration_id=1&flow_id={flow['id']}")
 await call('A-repeated-match',3,'POST',f"/reconciliation/manual-match?declaration_id=1&flow_id={flow['id']}",status=400)
 await call('B-rule-unknown',1,'PUT','/salary-templates/1',{'warehouse_id':2},422)
 await call('B-template-batch-mixed',1,'POST','/employees/batch-set-templates',{'employee_ids':[1,8],'salary_template_id':1,'deduction_template_id':1},403)
 for uid in (2,3,6):
  for key in ('purchase_approval_threshold','overtime_monthly_limit','unknown','procurement_duty_policy'):
   await call(f'B-legacy-key-{uid}-{key}',uid,'POST','/expense-fund/settings',{'key':key,'value':'0'},403)
 await call('B-admin-unknown-key',1,'POST','/expense-fund/settings',{'key':'unknown','value':'0'},403)
 # New self requests have no attendance effect until independent approval.
 req=await call('D-self-makeup-request',3,'POST','/clock-in/makeup-requests',{'date':'2026-10-24','sessions':[1],'reason':'SYNTHETIC'},check=unchanged_money)
 await call('C-finance-cannot-approve-makeup',3,'POST',f"/clock-in/makeup-requests/{req['id']}/approve",status=403)
 await call('C-independent-makeup',2,'POST',f"/clock-in/makeup-requests/{req['id']}/approve")
 await call('C-repeat-makeup',2,'POST',f"/clock-in/makeup-requests/{req['id']}/approve",status=409)
 sup=await call('D-supervisor-makeup-request',2,'POST','/clock-in/makeup-requests',{'date':'2026-10-24','sessions':[1],'reason':'SYNTHETIC'},check=unchanged_money)
 await call('C-supervisor-self-makeup-approval',2,'POST',f"/clock-in/makeup-requests/{sup['id']}/approve",status=403)
 async with factory() as db:
  alias=await db.get(User,10);alias.is_active=True;await db.commit()
 await call('C-alias-self-makeup-approval',10,'POST',f"/clock-in/makeup-requests/{sup['id']}/approve",status=403)
 async with factory() as db:
  alias=await db.get(User,10);alias.is_active=False;await db.commit()
 await call('C-admin-makeup-approval',1,'POST',f"/clock-in/makeup-requests/{sup['id']}/approve")
 # Active formal binding but attendance switched off: payslip remains readable, clock does not.
 async with factory() as db:
  u=await db.get(User,4);u.attendance_enabled=False;await db.commit()
 await call('D-attendance-disabled-clock',4,'POST','/clock-in',data={'session':'1'},status=403)
 await call('D-attendance-disabled-payslip',4,'GET','/payroll/my-payslip')
 async with factory() as db:
  emp=await db.get(Employee,4);emp.status='resigned';await db.commit()
 await call('D-resigned-payslip',4,'GET','/payroll/my-payslip',status=403)
 await call('D-disabled-account',7,'GET','/payroll/my-payslip',status=401)
 await call('D-missing-binding',1,'GET','/payroll/my-payslip',status=403)
 await call('D-finance-self-fund-recharge',3,'POST','/expense-fund/recharge/request?view=self',{'amount':20,'reason':'SYNTHETIC'})
 await call('D-self-fund-other',6,'GET','/expense-fund/accounts/1/items?view=self',status=403)
 # Audit fields identify the exact object and warehouse, without the bank account plaintext.
 async with factory() as db:
  from app.models.data_change_history import DataChangeHistory
  histories=(await db.execute(select(DataChangeHistory).where(DataChangeHistory.module=='employees',DataChangeHistory.record_id==1))).scalars().all()
  assert any(r.operator_id==1 and r.warehouse_id==1 and 'bank_account_number' in r.after_data.get('changed_fields',[]) for r in histories)
  assert 'SYNTHETIC-123' not in json.dumps([r.after_data for r in histories])

 # Personal advance request retains explicit source selection without disclosing balances.
 choices=await call('D-finance-no-menu-funding-options',11,'GET','/employee-advances/funding-options?view=self')
 assert choices['accounts'] and not any('balance' in k or 'number' in k for a in choices['accounts'] for k in a)
 await call('D-finance-no-menu-advance',11,'POST','/employee-advances?view=self',{'employee_id':11,'amount':10,'advance_date':'2026-10-24','funding_source':'company_account','payment_account_id':1},check=unchanged_money)
 await call('D-finance-no-menu-other-advance',11,'POST','/employee-advances?view=self',{'employee_id':1,'amount':10,'advance_date':'2026-10-24','funding_source':'company_account','payment_account_id':1},403)
 await call('D-finance-no-menu-payment-fields',11,'POST','/employee-advances?view=self',{'employee_id':11,'amount':10,'advance_date':'2026-10-24','funding_source':'company_account','payment_account_id':1,'approval_status':'approved'},422)
 await call('D-own-request-other-fund',11,'POST','/employee-advances?view=self',{'employee_id':11,'amount':10,'advance_date':'2026-10-24','funding_source':'expense_fund','fund_account_id':1},403)
 receipt=await call('D-own-fund-upload',3,'POST','/expense-fund/accounts/1/upload-receipt?view=self',files={'file':('synthetic.png',PNG,'image/png')})
 await call('D-own-fund-record',3,'POST','/expense-fund/accounts/1/items?view=self',{'expense_date':'2026-10-24','category':'其他','amount':1,'description':'SYNTHETIC','receipt':receipt['receipt'],'request_key':'r04-personal-expense'})
 await call('D-own-fund-control-fields',3,'POST','/expense-fund/accounts/1/items?view=self',{'expense_date':'2026-10-24','category':'其他','amount':1,'description':'SYNTHETIC','receipt':receipt['receipt'],'request_key':'r04-personal-invalid','review_status':'approved'},422)
 async with factory() as db:
  (await db.get(User,3)).extra_permissions=[];await db.commit()
 await call('D-own-fund-receipt-read',3,'GET',receipt['receipt'])
 await call('D-other-fund-receipt-read',11,'GET',receipt['receipt'],status=403)
 # Approved/rejected leave path remains reversible by independent onsite staff, without self approval.
 await call('C-independent-reject-approved',1,'PUT','/attendance/leaves/2/reject',data={'reason':'SYNTHETIC correction'})
 await call('C-repeat-reject',1,'PUT','/attendance/leaves/2/reject',data={'reason':'SYNTHETIC'},status=409)
 # Missing/unknown fields do not mutate configuration. Approved-source amounts stay unchanged.
 await call('B-resign-extra-financial',2,'POST','/employees/1/resign',{'reason':'voluntary','resignation_date':'2026-10-24','daily_wage':1000},403)
 await call('B-resign-unknown',1,'POST','/employees/1/resign',{'reason':'voluntary','resignation_date':'2026-10-24','permissions':[]},422)

 await call('D-nested-control-field',11,'POST','/reimbursement?view=self',{'submit_date':'2026-10-24','items':[{'category':'其他','amount':1,'review_status':'approved'}]},422)
 await call('D-foreign-receipt-association',11,'POST','/reimbursement?view=self',{'submit_date':'2026-10-24','items':[{'category':'其他','amount':1,'receipt':'uploads/2/foreign.png'}]},403)
 # Administrator status also cannot bypass independence for the administrator's own employee.
 async with factory() as db:
  db.add(Employee(id=12,user_id=1,warehouse_id=1,name='SYNTHETIC ADMIN EMP',hire_date=datetime(2026,10,1)))
  await db.flush()
  u=await db.get(User,1);u.attendance_enabled=True;u.attendance_employee_id=12
  db.add(LeaveRequest(id=120,employee_id=12,warehouse_id=1,leave_date=date(2026,10,26),leave_type='personal',duration_type='hours',hours=1,status='pending',notified_at=datetime(2026,10,25)))
  await db.commit()
 await call('C-admin-self-leave',1,'PUT','/attendance/leaves/120/approve',status=403)
 await call('C-admin-self-delegated',1,'POST','/attendance/leaves/admin-record',{'employee_id':12,'start_date':'2026-10-27','end_date':'2026-10-27','leave_type':'personal'},403)
 await call('C-admin-self-makeup',1,'POST','/clock-in/makeup',{'employee_id':12,'date':'2026-10-27','sessions':[1],'reason':'SELF'},403)
 await call('C-independent-admin-employee-leave',2,'PUT','/attendance/leaves/120/approve')

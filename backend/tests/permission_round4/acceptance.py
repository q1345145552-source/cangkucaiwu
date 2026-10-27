"""Round-four real route/JWT/PG targets. No authorization overrides."""
from fixtures import *
LOG=[];FAIL=[]
async def main():
 engine=create_async_engine(URL);factory=async_sessionmaker(engine,expire_on_commit=False)
 database._engine=engine;database._session_maker=factory
 async with engine.begin() as c:
  await c.execute(text('DROP SCHEMA public CASCADE'));await c.execute(text('CREATE SCHEMA public'));await c.run_sync(database.Base.metadata.create_all)
 async with factory() as db:await seed(db)
 async with factory() as db:
  # An attendance alias is intentionally not a valid self binding but must still deny self approval.
  db.add(User(id=10,username='synthetic-alias',display_name='ALIAS',role='supervisor',password_hash='synthetic',warehouse_id=1,extra_permissions=ALL,attendance_enabled=True,attendance_employee_id=2))
  db.add(UserWarehouse(user_id=10,warehouse_id=1))
  db.add(User(id=11,username='synthetic-finance-no-menu',display_name='NO MENU FINANCE',role='staff',password_hash='synthetic',warehouse_id=1,extra_permissions=[],attendance_enabled=True))
  await db.flush()
  db.add(UserWarehouse(user_id=11,warehouse_id=1))
  db.add(Employee(id=11,user_id=11,warehouse_id=1,name='NO MENU FINANCE',hire_date=datetime(2026,10,1)))
  await db.flush()
  (await db.get(User,11)).attendance_employee_id=11
  db.add(Employee(id=6,user_id=6,warehouse_id=1,name='NO MENU SELF',hire_date=datetime(2026,10,1)))
  await db.flush()
  u=await db.get(User,6);u.attendance_enabled=True;u.attendance_employee_id=6
  db.add(IncomeExpenseCategory(id=50,warehouse_id=1,type='income',name='SYNTHETIC INCOME',category_group='other'))
  await db.commit()
 async with AsyncClient(transport=ASGITransport(app=app,raise_app_exceptions=False),base_url='http://round4.local') as client:
  async def call(name,uid,method,path,body=None,status=200,check=None,headers=None,data=None,files=None):
   before=await snapshot(factory)
   kwargs={'json':body} if data is None else {'data':data}
   if files is not None:kwargs={'files':files, 'data':data or {}}
   r=await client.request(method,path if path.startswith('/uploads/') else '/api/v1'+path,headers={'Authorization':'Bearer '+create_access_token({'sub':str(uid)}),**(headers or {})},**kwargs)
   try:response=r.json()
   except Exception:response={'text':r.text}
   after=await snapshot(factory);diff={t:{'before':before[t],'after':after[t]} for t in before if before[t]!=after[t]};errors=[]
   if r.status_code!=status:errors.append(f'expected {status}, actual {r.status_code}')
   if r.status_code>=400 and any(t not in ('audit_logs','data_change_history') for t in diff):errors.append('rejected request changed business tables')
   if r.status_code>=400 and [x for x in before.get('data_change_history',[]) if x.get('module')=='makeup_request'] != [x for x in after.get('data_change_history',[]) if x.get('module')=='makeup_request']:errors.append('rejected request changed makeup business requests')
   if check:
    try:check(before,after,response)
    except Exception as exc:errors.append(repr(exc))
   LOG.append({'id':name,'user':uid,'method':method,'path':path,'request':body if data is None else data,'expected':status,'actual':r.status_code,'response':response,'database_diff':diff,'errors':errors});FAIL.extend(name+': '+e for e in errors)
   print(name,r.status_code,errors or 'PASS',str(response)[:120],flush=True)
   (OUT/'requests.json').write_text(json.dumps(LOG,ensure_ascii=False,indent=2));return response
  money={'category_id':50,'account_id':1,'amount':20,'currency':'THB','income_date':'2026-10-22','request_key':'r04-income'}
  for uid in (2,6,5,7):
   expected=401 if uid==7 else 403
   for method,path,body in [('POST','/income-expense/income',money),('PUT','/income-expense/income/1',money),('DELETE','/income-expense/income/1',None),('POST','/income-expense/categories',{'name':'NO','type':'expense'}),('POST','/incoming',{}),('POST','/incoming/batch-import',{}),('POST','/reconciliation/manual-match?declaration_id=1&flow_id=1',None),('POST','/reconciliation/unmatch?record_id=1',None)]:
    await call(f'A-deny-{uid}-{method}-{path}',uid,method,path,body,expected)
  for uid in (2,3,4,6,5,7):
   expected=401 if uid==7 else 403
   for method,path,body in [('POST','/salary-templates',{'name':'NO','type':'daily','amount':600}),('PUT','/salary-templates/1',{'amount':600}),('DELETE','/salary-templates/1',None),('POST','/deduction-templates',{'name':'NO'}),('POST','/employee-deductions',{'employee_id':1,'amount':10,'deduction_date':'2026-10-22','reason':'NO'}),('POST','/employees/batch-set-templates',{'employee_ids':[1],'salary_template_id':1,'deduction_template_id':1}),('PUT','/employees/max-limit?max_employees=99',None)]:
    await call(f'B-rule-{uid}-{method}-{path}',uid,method,path,body,expected)
   for field in ('daily_wage','base_salary','salary_template_id','deduction_template_id','bank_account_number','bank_name','bank_account_holder','user_id'):
    await call(f'B-field-{uid}-{field}',uid,'PUT','/employees/1',{field:None},expected)
  await call('B-onsite-edit',2,'PUT','/employees/1',{'remark':'现场事实'})
  await call('B-unknown',1,'PUT','/employees/1',{'permissions':['all']},422)
  await call('B-admin-rule',1,'PUT','/salary-templates/1',{'amount':400})
  await call('B-cross-admin-rule',1,'PUT','/salary-templates/2',{'amount':900},404)
  await call('B-spoof-header',1,'PUT','/salary-templates/1',{'amount':900},403,headers={'X-Warehouse-ID':'2'})
  await call('B-admin-sensitive',1,'PUT','/employees/1',{'bank_account_number':'SYNTHETIC-123'})
  await call('C-self-leave',2,'PUT','/attendance/leaves/2/approve',status=403)
  await call('C-alias-leave',10,'PUT','/attendance/leaves/2/approve',status=403)
  await call('C-finance-leave',3,'PUT','/attendance/leaves/1/approve',status=403)
  await call('C-independent-leave',2,'PUT','/attendance/leaves/1/approve')
  await call('C-repeated-leave',2,'PUT','/attendance/leaves/1/approve',status=409)
  await call('C-other-admin-leave',1,'PUT','/attendance/leaves/2/approve')
  await call('C-delegated-self',2,'POST','/attendance/leaves/admin-record',{'employee_id':2,'start_date':'2026-10-23','end_date':'2026-10-24','leave_type':'personal'},403)
  await call('C-self-makeup',2,'POST','/clock-in/makeup',{'employee_id':2,'date':'2026-10-23','sessions':[1],'reason':'SELF'},403)
  await call('C-other-makeup',2,'POST','/clock-in/makeup',{'employee_id':1,'date':'2026-10-23','sessions':[1],'reason':'FACT'})
  await call('C-self-overtime',2,'POST','/overtime/2/verify',{'assignments':[{'assignment_id':2,'actual_hours':1}]},403)
  await call('C-alias-overtime',10,'POST','/overtime/2/verify',{'assignments':[{'assignment_id':2,'actual_hours':1}]},403)
  await call('C-other-overtime',1,'POST','/overtime/2/verify',{'assignments':[{'assignment_id':2,'actual_hours':1}]})
  await call('D-conflicting-binding-denied',2,'GET','/clock-in/today',status=403)
  async with factory() as db:
   alias=await db.get(User,10);alias.is_active=False;await db.commit()
  await call('C-self-confirm-fact',2,'POST','/overtime/2/confirm')
  for uid in (2,3,4,6,11):
   await call(f'D-clock-{uid}',uid,'POST','/clock-in',data={'session':'2'})
   await call(f'D-leave-{uid}',uid,'POST','/attendance/leaves?view=self',data={'leave_date':'2026-10-25','leave_type':'personal','reason':'SYNTHETIC'})
   for path in ('/clock-in/today','/attendance/leaves?view=self','/payroll/my-payslip','/employee-advances/my-debt','/reimbursement?view=self','/expense-fund/accounts?view=self'):
    await call(f'D-self-{uid}-{path}',uid,'GET',path)
   await call(f'D-foreign-query-{uid}',uid,'GET','/payroll/my-payslip?employee_id=8',status=403)
   await call(f'D-foreign-head-{uid}',uid,'GET','/clock-in/today',status=403,headers={'X-Warehouse-ID':'2'})
   await call(f'D-control-field-{uid}',uid,'POST','/attendance/leaves',data={'leave_date':'2026-10-26','status':'approved'},status=400)
  await call('D-alias-self-denied',10,'GET','/clock-in/today',status=401)
  await call('D-self-reimbursement',6,'POST','/reimbursement?view=self',{'submit_date':'2026-10-24','items':[{'category':'其他','amount':10}]})
  await call('D-other-reimbursement',6,'GET','/reimbursement/1?view=self',status=403)
  await call('D-self-management-bypass',6,'POST','/reimbursement/1/verify?view=self',status=403)
  await call('D-self-control-json',6,'POST','/reimbursement?view=self',{'submit_date':'2026-10-24','status':'paid','items':[{'category':'其他','amount':10}]},422)
  from extra_scenarios import scenarios
  await scenarios(factory,client,call,LOG,FAIL)
 (OUT/'requests.json').write_text(json.dumps(LOG,ensure_ascii=False,indent=2))
 (OUT/'status.json').write_text(json.dumps({'requests':len(LOG),'failures':FAIL},ensure_ascii=False,indent=2))
 await engine.dispose()
 if FAIL:raise AssertionError(FAIL)
if __name__=='__main__':asyncio.run(main())

"""Actual history/list/write/XLSX role and revocation regression with untouched raw logs."""
from fixtures import *
from app.models.data_change_history import DataChangeHistory
from app.core.menu_registry import MENU_PERMISSIONS_BY_KEY
from openpyxl import load_workbook
from io import BytesIO
from zipfile import ZipFile

async def main():
 assert not (OUT/'requests.json').exists(), 'Never overwrite evidence'
 engine=create_async_engine(URL);factory=async_sessionmaker(engine,expire_on_commit=False)
 database._engine=engine;database._session_maker=factory
 async with engine.begin() as c:
  await c.execute(text('DROP SCHEMA public CASCADE'));await c.execute(text('CREATE SCHEMA public'));await c.run_sync(database.Base.metadata.create_all)
 pay_values=['919191','929292','373737','454545','565656','676767']
 private_values=['BANK-HISTORY-SENTINEL','BANK-NAME-HISTORY','BANK-HOLDER-HISTORY','SSO-HISTORY-SENTINEL','1234567890123','PASSPORT-HISTORY-SENTINEL','VOUCHER-HISTORY-SENTINEL']
 logs=[];fail=[];transitions=[]
 tokens={uid:create_access_token({'sub':str(uid)}) for uid in range(1,9)}
 def perms(*keys):return [MENU_PERMISSIONS_BY_KEY[k].label for k in keys]
 base=perms('employees','modification_logs')
 async with factory() as db:
  await seed(db);u=await db.get(User,4);u.extra_permissions=base
  (await db.get(User,3)).extra_permissions=perms('employees','payroll')
  e=await db.get(Employee,1);e.base_salary=919191;e.daily_wage=929292;e.bank_account_number=private_values[0];e.thai_id_number=private_values[4]
  for index,module in enumerate(('employee','employees','salary_templates','deduction_templates'),101):
   data={'name':'ONSITE-HISTORY-FACT','base_salary':919191,'daily_wage':929292,'bank_account_number':private_values[0],'bank_name':private_values[1],'bank_account_holder':private_values[2],'thai_id_number':private_values[4],'sso_number':private_values[3],'passport_number':private_values[5],'voucher_path':private_values[6],
    'nested':[{'base_salary':919191,'bank_name':private_values[1]}],
    'salary_template':{'amount':454545,'overtime_half_hour_fee':565656},
    'rule_values':{'base_salary':919191,'salary_template_amount':373737,'bank_account_holder':private_values[2]},
    'encoded':json.dumps({'base_salary':676767,'bank_name':private_values[1]}),
    'changes':[{'field':'base_salary','old':919191,'new':929292},{'key':'bank_account_number','value':private_values[0]}]}
   if module in ('salary_templates','deduction_templates'):data['rule_values'].update(amount=373737,overtime_half_hour_fee=565656)
   db.add(DataChangeHistory(id=index,module=module,record_id=1,warehouse_id=1,operator_id=1,operation_type='r04_change',before_data=data,after_data={**data,'base_salary':929292}))
  db.add(DataChangeHistory(id=108,module='employee',record_id=8,warehouse_id=2,operator_id=8,operation_type='update',before_data={'name':'FOREIGN-HISTORY-SENTINEL','base_salary':919191},after_data={'name':'FOREIGN-HISTORY-SENTINEL'}))
  db.add(DataChangeHistory(id=109,module='makeup_request',record_id=1,warehouse_id=1,operator_id=5,operation_type='request',after_data={'status':'pending','date':'2026-10-20','note':'MAKEUP-BUSINESS-SENTINEL'}))
  db.add(DataChangeHistory(id=110,module='reimbursement',record_id=1,warehouse_id=1,operator_id=1,operation_type='edit',before_data={'amount':888888,'bank_name':private_values[1]},after_data={'amount':888889}))
  db.add(AuditLog(user_id=1,warehouse_id=1,module='employee',action_type='edit',detail={'base_salary':919191,'bank_name':private_values[1]}))
  await db.commit()
 initial=await snapshot(factory);original_history=initial['data_change_history']
 async with AsyncClient(transport=ASGITransport(app=app,raise_app_exceptions=False),base_url='http://round5.local') as client:
  async def call(name,uid,path='/history?page_size=100',status=200,can_pay=False,body=None,headers=None,expected_fact=False,expected_value=None):
   before=await snapshot(factory);r=await client.request('PUT' if body is not None else 'GET','/api/v1'+path,headers={'Authorization':'Bearer '+tokens[uid],**(headers or {})},**({'json':body} if body is not None else {}));after=await snapshot(factory)
   diff={k:{'before':before[k],'after':after[k]} for k in before if before[k]!=after[k]};errors=[];is_export='spreadsheetml' in r.headers.get('content-type','');parsed=None
   if is_export:
    (OUT/(name+'.xlsx')).write_bytes(r.content);wb=load_workbook(BytesIO(r.content),data_only=False)
    parsed={s.title:[[c.value for c in row] for row in s] for s in wb.worksheets};assert sum(len(v) for v in parsed.values())>1
    with ZipFile(BytesIO(r.content)) as z:payload='\n'.join(z.read(n).decode('utf-8',errors='replace') for n in z.namelist())
    payload+=json.dumps(parsed,ensure_ascii=False)
    response={'bytes':len(r.content),'sha256':hashlib.sha256(r.content).hexdigest(),'sheets':parsed}
   else:response=r.json();payload=r.text
   if r.status_code!=status:errors.append(f'expected {status}, got {r.status_code}')
   if r.status_code==200:
    if expected_value is not None and str(expected_value) not in payload:errors.append('legitimate non-payroll amount unavailable')
    if not can_pay:
     for sentinel in pay_values:
      if sentinel in payload:errors.append('unauthorized payroll value: '+sentinel)
    elif path.startswith('/history') and '919191' not in payload:errors.append('authorized salary unavailable')
    if path.startswith(('/history','/settings/logs')):
     for sentinel in private_values:
      if sentinel in payload:errors.append('private history value: '+sentinel)
     if 'FOREIGN-HISTORY-SENTINEL' in payload and uid!=8:errors.append('foreign history leaked')
     if 'MAKEUP-BUSINESS-SENTINEL' in payload:errors.append('makeup business leaked')
     if expected_fact and 'ONSITE-HISTORY-FACT' not in payload:errors.append('legitimate fact unavailable')
   if 'no-store' not in r.headers.get('cache-control',''):errors.append('cacheable response')
   if body is None or status>=400:
    if any(k!='audit_logs' for k in diff):errors.append('read/denial changed business')
   else:
    old=next(e for e in before['employees'] if e['id']==1);new=next(e for e in after['employees'] if e['id']==1)
    if new['remark']!=body['remark']:errors.append('fact not saved')
    if any(old[k]!=new[k] for k in ('base_salary','daily_wage','bank_account_number','thai_id_number')):errors.append('sensitive DB values changed')
   preserved=[h for h in after['data_change_history'] if h['id'] in {x['id'] for x in original_history}]
   if preserved!=original_history:errors.append('raw history/makeup changed')
   logs.append({'id':name,'user':uid,'token_sha256':hashlib.sha256(tokens[uid].encode()).hexdigest(),'method':'PUT' if body else 'GET','path':path,'expected':status,'actual':r.status_code,'response':response,'database_diff':diff,'original_history_sha256':hashlib.sha256(json.dumps(preserved,sort_keys=True).encode()).hexdigest(),'errors':errors});fail.extend(name+': '+e for e in errors)
   (OUT/'requests.json').write_text(json.dumps(logs,ensure_ascii=False,indent=2));print(name,r.status_code,errors or 'PASS',flush=True)
  async def set_permissions(label,values):
   async with factory() as db:
    u=await db.get(User,4);previous=u.extra_permissions;u.extra_permissions=values;await db.commit()
   transitions.append({'phase':label,'user':4,'before':previous,'after':values})
  for phase,permissions,allow in [('no-payroll',base,False),('template-menu-only',base+perms('salary_templates','deduction_templates'),False),('granted',base+perms('salary_templates','deduction_templates','payroll'),True),('revoked',base,False)]:
   await set_permissions(phase,permissions)
   await call(phase+'-employees',4,'/employees',can_pay=allow)
   await call(phase+'-edit',4,'/employees/1',body={'remark':'SYNTHETIC '+phase},can_pay=allow)
   for module in ('employee','employees'):
    await call(phase+'-'+module,4,'/history?module='+module,can_pay=allow,expected_fact=True)
    await call(phase+'-'+module+'-export',4,'/history/export?module='+module,can_pay=allow,expected_fact=True)
   if phase in ('template-menu-only','granted'):
    for module in ('salary_templates','deduction_templates'):
     await call(phase+'-'+module,4,'/history?module='+module,can_pay=allow,expected_fact=True)
     await call(phase+'-'+module+'-export',4,'/history/export?module='+module,can_pay=allow,expected_fact=True)
  await set_permissions('independent-finance-log',base+perms('reimbursement','audit_logs'))
  await call('non-payroll-amount',4,'/history?module=reimbursement',expected_value=888888)
  await call('non-payroll-amount-export',4,'/history/export?module=reimbursement',expected_value=888888)
  await call('audit-metadata-only',4,'/settings/logs')
  await call('history-operators',4,'/history/operators')
  for uid in (1,2):
   await call('role-'+str(uid),uid,can_pay=uid==1,expected_fact=True)
   await call('role-export-'+str(uid),uid,'/history/export',can_pay=uid==1,expected_fact=True)
  for uid in (1,2,4):
   await call('foreign-header-'+str(uid),uid,headers={'X-Warehouse-ID':'2'},status=403)
   await call('foreign-export-'+str(uid),uid,'/history/export?warehouse_id=2',status=403)
  for uid in (3,5,6,7):
   await call('no-log-'+str(uid),uid,status=401 if uid==7 else 403)
   await call('no-log-export-'+str(uid),uid,'/history/export',status=401 if uid==7 else 403)
 (OUT/'role-transitions.json').write_text(json.dumps(transitions,ensure_ascii=False,indent=2));(OUT/'raw-history-before.json').write_text(json.dumps(original_history,ensure_ascii=False,indent=2));(OUT/'status.json').write_text(json.dumps({'requests':len(logs),'failures':fail},ensure_ascii=False,indent=2));await engine.dispose()
 if fail:raise SystemExit(1)
if __name__=='__main__':asyncio.run(main())

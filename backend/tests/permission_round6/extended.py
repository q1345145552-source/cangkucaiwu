"""Migration, independent lanes, unknown routes and stale credentials on real local PG."""
from fixtures import *
from types import SimpleNamespace
from app.core.action_access import VERSION,role_grants,permission_state,convert_legacy
from app.models.data_change_history import DataChangeHistory
from fastapi import Depends
from app.core.permissions import get_current_user

async def main():
 engine=create_async_engine(URL);factory=async_sessionmaker(engine,expire_on_commit=False);database._engine=engine;database._session_maker=factory
 async with engine.begin() as c:
  await c.execute(text('DROP SCHEMA public CASCADE'));await c.execute(text('CREATE SCHEMA public'));await c.run_sync(database.Base.metadata.create_all)
 async with factory() as db:
  await seed(db)
  cases={13:None,14:[],15:['员工档案'],16:['UNKNOWN','employees','全部权限'],17:[VERSION],18:[VERSION,'employees:view'],19:['@wf-actions:999','employees:view'],20:[VERSION,'员工档案'],21:['员工档案'],22:['员工档案'],23:ALL,24:['员工档案'],25:['员工档案'],26:['员工档案'],27:{'all':True},28:None,29:[]}
  for uid,raw in cases.items():
   db.add(User(id=uid,username='SYNTHETIC-'+str(uid),display_name='SYNTHETIC '+str(uid),role='supervisor' if uid==23 else 'staff',warehouse_id=1,password_hash='synthetic-not-password',extra_permissions=raw,is_active=uid!=22));await db.flush();db.add(UserWarehouse(user_id=uid,warehouse_id=1))
  db.add(UserWarehouse(user_id=21,warehouse_id=2));await db.flush();await db.execute(text("SELECT setval(pg_get_serial_sequence('users','id'), 30, false)"));await db.commit()
 logs=[];fail=[];tokens={uid:create_access_token({'sub':str(uid)}) for uid in range(1,25)}
 def require(value,message='assertion failed'):
  if not value:raise AssertionError(message)
 async with AsyncClient(transport=ASGITransport(app=app,raise_app_exceptions=False),base_url='http://round6.local') as client:
  async def call(name,uid,method,path,body=None,status=200,check=None,headers=None):
   before=await snapshot(factory);files_before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(os.environ['UPLOAD_DIR']).rglob('*') if p.is_file()}
   r=await client.request(method,'/api/v1'+path,headers={'Authorization':'Bearer '+tokens[uid],**(headers or {})},**({'json':body} if body is not None else {}));after=await snapshot(factory)
   diff={t:{'before':before[t],'after':after[t]} for t in before if before[t]!=after[t]};errors=[]
   try:v=r.json()
   except ValueError:v={'bytes':len(r.content),'sha256':hashlib.sha256(r.content).hexdigest()}
   if r.status_code!=status:errors.append(f'expected {status}, actual {r.status_code}')
   if status>=400 or method=='GET':
    if any(t!='audit_logs' for t in diff):errors.append('rejected/read business mutation')
    files_after={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(os.environ['UPLOAD_DIR']).rglob('*') if p.is_file()}
    if files_before!=files_after:errors.append('rejected/read file mutation')
   if check and r.status_code==status:
    try:check(v,diff)
    except Exception as e:errors.append(str(e))
   logs.append({'id':name,'user':uid,'method':method,'path':path,'request':body,'expected':status,'actual':r.status_code,'response':v,'database_diff':diff,'errors':errors});fail.extend(name+': '+e for e in errors)
   print(name,r.status_code,errors or 'PASS',flush=True);(OUT/'requests.json').write_text(json.dumps(logs,ensure_ascii=False,indent=2));return v
  async def grant(uid,grants,name):return await call(name,1,'PUT',f'/users/{uid}',{'action_permissions':grants,'permission_reason':'SYNTHETIC '+name})
  import app.services.action_permission_migration as migration_service
  real_history=migration_service.record_history
  async def fail_history(*args,**kwargs):
   await real_history(*args,**kwargs)
   raise RuntimeError('SYNTHETIC migration failure before commit')
  migration_service.record_history=fail_history
  try:
   await call('migration-mid-transaction-rollback',1,'POST','/access/migrate',{'user_ids':[25,26],'reason':'SYNTHETIC rollback'},500)
  finally:migration_service.record_history=real_history
  await call('migration-scope-atomic' ,1,'POST','/access/migrate',{'user_ids':[13,21],'reason':'SYNTHETIC scope'},403)
  await call('migration-version-conflict-atomic',1,'POST','/access/migrate',{'user_ids':[13,19],'reason':'SYNTHETIC conflict'},409)
  await call('migration-mixed-old-new-atomic',1,'POST','/access/migrate',{'user_ids':[13,20],'reason':'SYNTHETIC mixed'},409)
  await call('migration-duplicate-targets',1,'POST','/access/migrate',{'user_ids':[13,13],'reason':'SYNTHETIC duplicate'},400)
  await call('migration-missing-target-atomic',1,'POST','/access/migrate',{'user_ids':[13,999],'reason':'SYNTHETIC missing'},404)
  await call('migration-staff-denied',3,'POST','/access/migrate',{'user_ids':[13],'reason':'SYNTHETIC'},403)
  await call('migration-normal-null-empty-unknown-disabled-full',1,'POST','/access/migrate',{'user_ids':[13,14,15,16,17,18,22,23,24],'reason':'SYNTHETIC explicit conversion'},check=lambda v,d:require(v['converted']==7 and v['already_versioned']==2,'conversion count'))
  for uid,status in [(13,403),(14,403),(15,200),(16,403),(17,403),(18,200),(22,401),(23,200)]:await call(f'migrated-read-{uid}',uid,'GET','/employees',status=status)
  for uid in (19,20):await call(f'invalid-config-{uid}',uid,'GET','/employees',status=403)
  await grant(15,[],'revoke-migrated')
  await call('replay-no-regrant',1,'POST','/access/migrate',{'user_ids':[13,14,15,16,17,18,22,23,24],'reason':'SYNTHETIC replay'},check=lambda v,d:require(v['converted']==0 and not any(t!='audit_logs' for t in d),'replay writes/regrants'))
  await call('old-jwt-revoked-migrated',15,'GET','/employees',status=403)
  # Actual old backfill runs in this synthetic DB. Versioned grants and revocations are immutable to it.
  async with engine.begin() as conn:
   from app.services.permission_migrations import _backfill_permissions
   before=(await conn.execute(select(User.id,User.extra_permissions).where(User.id.between(13,29)))).all()
   await _backfill_permissions(conn,'SYNTHETIC-round6-backfill-check',('工资','员工档案'))
   after=(await conn.execute(select(User.id,User.extra_permissions).where(User.id.between(13,29)))).all()
  for (uid,raw),(uid2,new) in zip(before,after):
   if uid in (27,28,29) or (isinstance(raw,list) and any(x.startswith('@wf-actions:') for x in raw)):
    require(raw==new,f'backfill regranted {uid}')
  (OUT/'backfill.json').write_text(json.dumps({'before':[(a,b) for a,b in before],'after':[(a,b) for a,b in after],'assertion':'all versioned/invalid-version values preserved'},ensure_ascii=False,indent=2))
  async with factory() as db:
   rows=(await db.execute(select(DataChangeHistory).where(DataChangeHistory.module=='permissions'))).scalars().all()
   require(len(rows)==7,'audit count');require(all(r.operator_id==1 and r.warehouse_id==1 and r.before_data is not None and r.after_data.get('reason') for r in rows),'audit source/scope/reason')
   unknown=next(r for r in rows if r.record_id==16);require(unknown.before_data['raw_permissions']==['UNKNOWN','employees','全部权限'],'lost source values')
   require(unknown.after_data['grants']==[],'unknown values grant rights')
   require((await db.get(User,22)).is_active is False,'migration enabled account')
  await call('create-default-minimal',1,'POST','/users',{'username':'new-minimal','display_name':'SYNTHETIC NEW','password':'synthetic-only-password','role':'staff','warehouse_id':1})
  async with factory() as db:
   new=(await db.execute(select(User).where(User.username=='new-minimal'))).scalar_one();require(new.extra_permissions==[VERSION],'new default not minimal');tokens[new.id]=create_access_token({'sub':str(new.id)});new_id=new.id
  await call('default-user-denied',new_id,'GET','/employees',status=403)
  await call('grant-missing-reason',1,'PUT','/users/3',{'action_permissions':['payroll:operate']},400)
  await call('grant-duplicate',1,'PUT','/users/3',{'action_permissions':['payroll:view','payroll:view'],'permission_reason':'SYNTHETIC'},403)
  await call('grant-mixed-input',1,'PUT','/users/3',{'action_permissions':[],'extra_permissions':[],'permission_reason':'SYNTHETIC'},400)
  await call('grant-client-role-claim',1,'PUT','/users/3',{'action_permissions':[],'permission_reason':'SYNTHETIC','is_super_admin':True},422)
  # Real configuration, real actions. POST preview is view, calculate is operate.
  for grants,label in [([], 'none'),(['payroll:view'],'view'),(['payroll:operate'],'operate'),(['payroll:view','payroll:operate'],'both')]:
   await grant(3,grants,'finance-grant-'+label)
   await call('finance-list-'+label,3,'GET','/payroll?settle_month=2026-10',status=200 if 'payroll:view' in grants else 403,check=lambda v,d:require(not any(row.get('capabilities',{}).get('can_pay') for row in v.get('data',[])),'pending payment hint'))
   await call('finance-post-preview-'+label,3,'POST','/payroll/preview',{'end_date':'2026-10-27'},status=200 if 'payroll:view' in grants else 403)
   await call('finance-confirm-denied-'+label,3,'POST','/payroll/1/confirm',status=403)
   await call('finance-selector-'+label,3,'GET','/access/choices/payroll',status=200 if 'payroll:operate' in grants else 403,check=lambda v,d:require('net_pay' not in json.dumps(v) and 'bank' not in json.dumps(v),'selector fields'))
   await call('finance-calculate-'+label,3,'POST','/payroll/calculate',{'end_date':'2026-10-27'},status=200 if 'payroll:operate' in grants else 403)
  await grant(3,['payroll:view'],'shared-account-selector-view')
  await call('payroll-view-account-selection-only',3,'GET','/accounts',check=lambda v,d:require(v.get('scope')=='account_selection_only' and all(set(x)<= {'id','warehouse_id','account_name','currency','status'} for x in v['data']),'shared selector exposes balances/bank fields'))
  await grant(3,['accounts:view'],'full-account-read-explicit')
  await call('explicit-account-balance-visible',3,'GET','/accounts',check=lambda v,d:require('current_balance' in v['data'][0],'explicit account view lost'))
  await call('client-owned-attendance-fields',1,'PUT','/users/3',{'attendance_enabled':True,'attendance_employee_id':2,'attendance_enabled_at':'2000-01-01T00:00:00Z'},422)
  await grant(2,['employees:operate'],'site-operations-only')
  await call('site-minimum-employees',2,'GET','/access/choices/employees')
  await call('site-no-leave-selector',2,'GET','/access/choices/leave',status=403)
  await call('site-fact-write-only',2,'PUT','/employees/1',{'remark':'SYNTHETIC MINIMUM FACT'})
  await call('site-fact-list-denied',2,'GET','/employees',status=403)
  await grant(2,['leave:approve'],'site-approval-only')
  await call('site-minimum-leave',2,'GET','/access/choices/leave')
  await call('site-no-fact-selector',2,'GET','/access/choices/employees',status=403)
  await call('site-approved-other',2,'PUT','/attendance/leaves/1/approve')
  await call('site-no-self-approve',2,'PUT','/attendance/leaves/2/approve',status=403)
  await call('site-approval-no-fact-write',2,'PUT','/employees/1',{'remark':'ATTACK'},403)
  await call('site-approval-no-full-list',2,'GET','/attendance/leaves',status=403)
  await call('minimal-foreign-object-scope',2,'GET','/access/choices/leave',headers={'X-Warehouse-ID':'2'},status=403)
  await call('client-claim-no-bypass',2,'POST','/payroll/1/disburse',{'funding_source':'company_account','payment_account_id':1},403,headers={'X-Permissions':'payroll:operate','X-Role':'warehouse_admin'})
  async with factory() as db:
   (await db.get(User,24)).extra_permissions=['员工档案'];await db.commit()
  race=await asyncio.gather(
   call('concurrent-migration',1,'POST','/access/migrate',{'user_ids':[24],'reason':'SYNTHETIC race'}),
   grant(24,[],'concurrent-revocation'))
  async with factory() as db:require((await db.get(User,24)).extra_permissions==[VERSION],'migration race restored revoked grants')
  # Register an intentionally omitted real route; middleware must reject before executing it.
  hits=[]
  async def unregistered_probe(user=Depends(get_current_user)):
   hits.append(user.id);return {'unsafe':True}
  app.add_api_route('/api/v1/synthetic-unregistered',unregistered_probe,methods=['POST'])
  await call('unknown-business-default-deny',1,'POST','/synthetic-unregistered',{},403)
  require(not hits,'unknown endpoint executed')
  await call('catalog-current-role',2,'GET','/access/catalog?role=supervisor',check=lambda v,d:require(any(m['key']=='leave' and m['tiers']['approve']['allowed'] and not m['tiers']['operate']['allowed'] for m in v['modules']),'leave ceiling/category'))
 (OUT/'status.json').write_text(json.dumps({'requests':len(logs),'failures':fail},indent=2));await engine.dispose()
 if fail:raise SystemExit(1)
if __name__=='__main__':asyncio.run(main())

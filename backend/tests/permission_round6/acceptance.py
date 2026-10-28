"""Versioned three-tier grants through real routes/JWT/PostgreSQL; no permissive auth."""
from fixtures import *
from app.core.action_access import VERSION,role_grants

async def main():
 engine=create_async_engine(URL);factory=async_sessionmaker(engine,expire_on_commit=False);database._engine=engine;database._session_maker=factory
 async with engine.begin() as c:
  await c.execute(text('DROP SCHEMA public CASCADE'));await c.execute(text('CREATE SCHEMA public'));await c.run_sync(database.Base.metadata.create_all)
 async with factory() as db:await seed(db)
 records=[];fail=[]
 async with AsyncClient(transport=ASGITransport(app=app,raise_app_exceptions=False),base_url='http://round6.local') as client:
  token={uid:create_access_token({'sub':str(uid)}) for uid in range(1,9)}
  async def call(name,uid,method,path,body=None,status=200,check=None,headers=None):
   before=await snapshot(factory);r=await client.request(method,'/api/v1'+path,headers={'Authorization':'Bearer '+token[uid],**(headers or {})},**({'json':body} if body is not None else {}));after=await snapshot(factory)
   diff={t:{'before':before[t],'after':after[t]} for t in before if before[t]!=after[t]};errors=[]
   try:value=r.json()
   except ValueError:value={'text':r.text[:500]}
   if r.status_code!=status:errors.append(f'expected {status}, got {r.status_code}')
   if method=='GET' or status>=400:
    if any(t!='audit_logs' for t in diff):errors.append('read/denial has business effect')
   if check and r.status_code==status:
    try:check(value,diff)
    except Exception as e:errors.append(str(e))
   records.append({'id':name,'user':uid,'token_sha256':hashlib.sha256(token[uid].encode()).hexdigest(),'method':method,'path':path,'body':body,'expected':status,'actual':r.status_code,'response':value,'database_diff':diff,'errors':errors});fail.extend(name+': '+x for x in errors)
   (OUT/'requests.json').write_text(json.dumps(records,ensure_ascii=False,indent=2));print(name,r.status_code,errors or 'PASS',flush=True);return value
  def require(value,message):
   if not value:raise AssertionError(message)
  for mask in range(8):
   tiers=[tier for bit,tier in enumerate(('view','operate','approve')) if mask & (1<<bit)]
   grants=[f'{m}:{t}' for m in ('employees','leave','attendance') for t in tiers if f'{m}:{t}' in role_grants('supervisor')]
   await call(f'config-{mask}',1,'PUT','/users/2',{'action_permissions':grants,'permission_reason':f'SYNTHETIC matrix {mask}'})
   await call(f'view-{mask}',2,'GET','/employees',status=200 if 'view' in tiers else 403)
   await call(f'operate-{mask}',2,'PUT','/employees/1',{'remark':f'SYNTHETIC FACT {mask}'},status=200 if 'operate' in tiers else 403)
   async with factory() as db:
    leave=await db.get(LeaveRequest,1);leave.status='pending';leave.reviewed_by=None;leave.reviewed_at=None;await db.commit()
   await call(f'approve-{mask}',2,'PUT','/attendance/leaves/1/approve',status=200 if 'approve' in tiers else 403)
   await call(f'self-approve-{mask}',2,'PUT','/attendance/leaves/2/approve',status=403)
   await call(f'choices-{mask}',2,'GET','/access/choices/'+('employees' if 'operate' in tiers else 'leave'),status=200 if any(t in tiers for t in ('operate','approve')) else 403,
              check=lambda v,d:require('bank_account_number' not in json.dumps(v),'selector bank leak'))
  await call('forged-role-ceiling',1,'PUT','/users/2',{'action_permissions':['payroll:operate'],'permission_reason':'SYNTHETIC invalid'},403)
  await call('forged-action',1,'PUT','/users/2',{'action_permissions':['unknown:approve'],'permission_reason':'SYNTHETIC invalid'},403)
  await call('self-grant',1,'PUT','/users/1',{'action_permissions':['employees:operate'],'permission_reason':'SYNTHETIC invalid'},403)
  await call('staff-edit-other-permissions',3,'PUT','/users/4',{'action_permissions':['employees:view'],'permission_reason':'SYNTHETIC invalid'},403)
  await call('supervisor-edit-other-permissions',2,'PUT','/users/4',{'action_permissions':['employees:view'],'permission_reason':'SYNTHETIC invalid'},403)
  await call('cross-warehouse-permissions',1,'PUT','/users/8',{'action_permissions':[],'permission_reason':'SYNTHETIC invalid'},403)
  await call('no-implicit-bank',2,'PUT','/employees/1',{'bank_account_number':'SYNTHETIC ATTACK'},403)
  await call('no-role-accounts',2,'PUT','/accounts/1',{'account_name':'ATTACK'},403)
  await call('revoke',1,'PUT','/users/2',{'action_permissions':[],'permission_reason':'SYNTHETIC revoke'})
  await call('old-jwt-after-revoke',2,'GET','/employees',status=403)
  await call('old-popup-after-revoke',2,'PUT','/employees/1',{'remark':'STALE'},403)
  await call('legacy-cannot-downgrade',1,'PUT','/users/2',{'extra_permissions':ALL},409)
  await call('migrate-legacy',1,'POST','/access/migrate',{'user_ids':[3,4,6,7],'reason':'SYNTHETIC migration'})
  await call('migrate-idempotent',1,'POST','/access/migrate',{'user_ids':[2,3,4,6,7],'reason':'SYNTHETIC replay'},check=lambda v,d:require(v['converted']==0,'migration regranted'))
  await call('migrated-staff-view',3,'GET','/employees')
  await call('migrated-disabled',7,'GET','/employees',status=401)
  await call('migrated-empty',6,'GET','/employees',status=403)
  await call('scoped-choice',3,'GET','/access/choices/payroll',headers={'X-Warehouse-ID':'2'},status=403)
 (OUT/'status.json').write_text(json.dumps({'requests':len(records),'failures':fail},indent=2));await engine.dispose()
 if fail:raise SystemExit(1)
if __name__=='__main__':asyncio.run(main())

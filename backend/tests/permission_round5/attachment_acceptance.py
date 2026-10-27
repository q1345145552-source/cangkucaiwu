"""Additional actual-upload attachment object, role, binding and revocation checks."""
from fixtures import *
from app.models.reimbursement_payment import ReimbursementPayment
from app.models.clock_in_records import ClockInRecord
OUT=ROOT/'docs/permissions-round5-20261028'/os.environ.get('ROUND5_ATTACH_RUN',os.environ.get('ROUND5_RUN','attachments-final'));OUT.mkdir(parents=True,exist_ok=True)
assert not (OUT/'requests.json').exists(), 'Use a fresh evidence directory; never overwrite previous requests'
async def main():
 engine=create_async_engine(URL);factory=async_sessionmaker(engine,expire_on_commit=False);database._engine=engine;database._session_maker=factory;records=[];fail=[]
 async with AsyncClient(transport=ASGITransport(app=app,raise_app_exceptions=False),base_url='http://round5.local') as client:
  async def call(name,uid,path,status=200,files=None,headers=None):
   before=await snapshot(factory)
   response=await client.request('POST' if files else 'GET',path if path.startswith('/uploads/') else '/api/v1'+path,headers={'Authorization':'Bearer '+create_access_token({'sub':str(uid)}),**(headers or {})},**({'files':files} if files else {}))
   after=await snapshot(factory);diff={k:{'before':before[k],'after':after[k]} for k in before if before[k]!=after[k]};errors=[]
   if response.status_code!=status:errors.append(f'expected {status}, actual {response.status_code}')
   if any(k not in ('audit_logs',) for k in diff):errors.append('read/upload modified business tables')
   if status==200 and not files and not response.content.startswith(b'\x89PNG'):errors.append('not actual PNG bytes')
   if status!=200 and (b'/private/tmp/' in response.content or response.content.startswith(b'\x89PNG')):errors.append('denial leaked file/path')
   if 'no-store' not in response.headers.get('cache-control',''):errors.append('cacheable file')
   records.append({'id':name,'user':uid,'method':'POST' if files else 'GET','path':path,'expected':status,'actual':response.status_code,'response':response.json() if 'json' in response.headers.get('content-type','') else {'bytes':len(response.content),'sha256':hashlib.sha256(response.content).hexdigest()},'database_diff':diff,'errors':errors});fail.extend(name+': '+e for e in errors);print(name,response.status_code,errors or 'PASS',flush=True);return response
  for kind in ('payroll','leave','clock','overtime','payment'):
   uploaded=await call('upload-'+kind,3,'/upload',files={'file':(kind+'.png',PNG,'image/png')});path=uploaded.json()['path']
   async with factory() as db:
    if kind=='payroll':(await db.get(PayrollRecord,1)).signature_path=path
    elif kind=='leave':(await db.get(LeaveRequest,1)).photo_path=path
    elif kind=='clock':db.add(ClockInRecord(user_id=5,warehouse_id=1,clock_date=date(2026,10,28),session=1,photo_path=path))
    elif kind=='overtime':(await db.get(OvertimeAssignment,1)).dispute_photo=path
    else:
     (await db.get(Reimbursement,1)).status='paid'
     existing=(await db.execute(select(ReimbursementPayment).where(ReimbursementPayment.reimbursement_id==1))).scalar_one_or_none()
     if existing:await db.delete(existing);await db.flush()
     db.add(ReimbursementPayment(reimbursement_id=1,warehouse_id=1,amount=100,currency='THB',funding_source='company_account',payment_account_id=1,voucher_path=path,previous_status='approved',paid_by_id=4,paid_by_name='SYNTHETIC FINANCE',paid_at=datetime(2026,10,28),status='active'))
    await db.commit()
   statuses={1:200,2:200 if kind in ('leave','clock','overtime') else 403,3:200 if kind in ('payroll','payment') else 403,4:200 if kind in ('payroll','payment') else 403,5:403 if kind=='payment' else 200,6:403,7:401,8:403,11:403}
   for uid,status in statuses.items():await call(kind+'-'+str(uid),uid,'/'+path,status)
   await call(kind+'-foreign-header',1,'/'+path,403,headers={'X-Warehouse-ID':'2'})
   if kind=='leave':
    async with factory() as db:
     e=await db.get(Employee,1);previous=e.status;e.status='resigned';await db.commit()
    await call('invalid-binding-old-leave-link',5,'/'+path,403)
    async with factory() as db:(await db.get(Employee,1)).status=previous;await db.commit()
    async with factory() as db:
     u=await db.get(User,2);perms=u.extra_permissions;u.extra_permissions=[];await db.commit()
    await call('revoked-supervisor-old-leave-link',2,'/'+path,403)
    async with factory() as db:(await db.get(User,2)).extra_permissions=perms;await db.commit()
   if kind=='payment':
    async with factory() as db:
     u=await db.get(User,4);perms=u.extra_permissions;u.extra_permissions=[];await db.commit()
    await call('revoked-finance-payment-link',4,'/'+path,403)
    async with factory() as db:(await db.get(User,4)).extra_permissions=perms;await db.commit()
  await call('encoded-parent-foreign-file',2,'/uploads/1/%2e%2e/2/audit/passport-8.png',403)
  await call('double-slash-private-file',2,'/uploads/1//audit/passport-1.png',403)
 (OUT/'requests.json').write_text(json.dumps(records,ensure_ascii=False,indent=2));(OUT/'status.json').write_text(json.dumps({'requests':len(records),'failures':fail},ensure_ascii=False,indent=2));await engine.dispose()
 if fail:raise AssertionError(fail)
if __name__=='__main__':asyncio.run(main())

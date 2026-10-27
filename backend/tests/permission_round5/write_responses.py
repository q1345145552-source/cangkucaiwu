"""Real JWT/PG write-response regression; preserves failure evidence in unique runs."""
from fixtures import *
from app.core.round5_access import PAY_FIELDS, DOCUMENT_FIELDS
from app.core.menu_registry import MENU_PERMISSIONS_BY_KEY

async def main():
 engine=create_async_engine(URL); factory=async_sessionmaker(engine,expire_on_commit=False)
 database._engine=engine;database._session_maker=factory
 async with engine.begin() as c:
  await c.execute(text('DROP SCHEMA public CASCADE'));await c.execute(text('CREATE SCHEMA public'));await c.run_sync(database.Base.metadata.create_all)
 sensitive={'bank_account_number':'BANK-SENTINEL-1','bank_name':'BANK-NAME-SENTINEL','bank_account_holder':'HOLDER-SENTINEL','thai_id_number':'1234567890123','sso_number':'SSO-SENTINEL','passport_number':'PASSPORT-SENTINEL','daily_wage':7124.0,'base_salary':91235.0}
 async with factory() as db:
  await seed(db); e=await db.get(Employee,1)
  for key,value in sensitive.items():setattr(e,key,value)
  u=await db.get(User,4);u.extra_permissions=[MENU_PERMISSIONS_BY_KEY['employees'].label];await db.commit()
 log=[]; failures=[]
 def keys(v):
  if isinstance(v,dict):return set(v).union(*(keys(x) for x in v.values()))
  if isinstance(v,list):return set().union(*(keys(x) for x in v))
  return set()
 async with AsyncClient(transport=ASGITransport(app=app,raise_app_exceptions=False),base_url='http://round5.local') as client:
  async def call(name,uid,body,status=200,content_type='application/json',path='/employees/1',method='PUT',upload=False):
   before=await snapshot(factory)
   headers={'Authorization':'Bearer '+create_access_token({'sub':str(uid)}),'X-Warehouse-ID':'1'}
   kwargs={'files':{'file':('synthetic.png',PNG,'image/png')}} if upload else {'content':json.dumps(body),'headers':{**headers,'Content-Type':content_type}}
   if upload:kwargs['headers']=headers
   r=await client.request(method,'/api/v1'+path,**kwargs)
   after=await snapshot(factory);diff={t:{'before':before[t],'after':after[t]} for t in before if before[t]!=after[t]}
   value=r.json();errors=[]
   if r.status_code!=status:errors.append(f'expected {status}, actual {r.status_code}')
   forbidden=(DOCUMENT_FIELDS if uid==3 else DOCUMENT_FIELDS|PAY_FIELDS|{'warnings'}) if uid!=1 else set()
   if r.status_code==200 and keys(value)&forbidden:errors.append('forbidden response keys: '+str(sorted(keys(value)&forbidden)))
   if uid!=1:
    for k,v in sensitive.items():
     if k in forbidden and str(v) in r.text:errors.append('sensitive sentinel returned: '+k)
   old=next(x for x in before['employees'] if x['id']==1);new=next(x for x in after['employees'] if x['id']==1)
   if not (uid==1 and status==200 and method=='PUT'):
    for k in sensitive:
     if old[k]!=new[k]:errors.append('sensitive DB value changed: '+k)
   if upload and status==200:
    field={'photo':'photo_path','passport-photo':'passport_photo_path','work-permit-photo':'work_permit_photo_path'}[path.rsplit('/',1)[-1]]
    if old[field]==new[field] or not new[field]:errors.append('uploaded reference not saved')
    if not (Path(os.environ['UPLOAD_DIR'])/'fix01-upload'/Path(new[field]).name).is_file():errors.append('real uploaded file missing')
    if uid==1 and value.get(field)!=new[field]:errors.append('admin upload path missing')
    for key in old:
     if key not in (field,'updated_at') and old[key]!=new[key]:errors.append('upload changed unrelated employee field: '+key)
    if any(t not in ('employees','audit_logs','data_change_history') for t in diff):errors.append('upload changed unrelated business table')
   if status>=400 and any(t!='audit_logs' for t in diff):errors.append('rejection changed business tables')
   if status==200 and method=='PUT':
    if 'remark' in body and new['remark']!=body['remark']:errors.append('fact not saved')
    if any(t not in ('employees','audit_logs','data_change_history') for t in diff):errors.append('unexpected business effect')
    if uid in (1,3) and value.get('bank_account_number')!=new['bank_account_number']:errors.append('authorized bank missing')
    if uid==1 and value.get('thai_id_number')!=new['thai_id_number']:errors.append('admin identity missing')
   log.append({'id':name,'user':uid,'method':method,'path':path,'content_type':content_type,'body':body,'expected':status,'actual':r.status_code,'response':value,'database_diff':diff,'errors':errors});failures.extend(name+': '+e for e in errors)
   (OUT/'requests.json').write_text(json.dumps(log,ensure_ascii=False,indent=2));print(name,r.status_code,errors or 'PASS',flush=True)
  for uid in (2,4,3,1):
   for variant,ct in [('normal','application/json'),('vendor','application/vnd.audit+json'),('charset','application/json; charset=utf-8')]:
    await call(f'fact-{uid}-{variant}',uid,{'remark':f'SYNTHETIC FACT {uid} {variant}'},content_type=ct)
   await call(f'empty-{uid}',uid,{})
  for uid in (2,4,3):
   for field in ('bank_account_number','bank_name','bank_account_holder','daily_wage','base_salary','salary_template_id','deduction_template_id'):
    await call(f'protected-{uid}-{field}',uid,{field:'ATTACK' if field.startswith('bank') else 999},403)
   await call(f'invalid-{uid}',uid,{'nationality':'invalid'},400)
   await call(f'malformed-{uid}',uid,{'remark':{'nested':'not a string'}},422)
   await call(f'foreign-{uid}',uid,{'remark':'FOREIGN'},403,path='/employees/8')
   await call(f'batch-{uid}',uid,{'employee_ids':[1],'salary_template_id':1,'deduction_template_id':1},403,path='/employees/batch-set-templates',method='POST')
   await call(f'create-deny-{uid}',uid,{'name':'SYNTHETIC NEW','employee_no':'fix01-'+str(uid),'password':'synthetic123'},403,path='/employees',method='POST')
  # Only redirect hard-coded upload storage into the isolated test directory; real image codec,
  # routing, authorization, ORM writes and response projection remain unchanged.
  import app.services.image_utils as image_utils
  original_save=image_utils.save_image
  def isolated_save(content,absolute,relative,filename):
   return original_save(content,str(Path(os.environ['UPLOAD_DIR'])/'fix01-upload'),relative,filename)
  image_utils.save_image=isolated_save
  try:
   for uid in (2,4,3,1):
    for kind in ('photo','passport-photo','work-permit-photo'):
     await call(f'upload-{uid}-{kind}',uid,{},path='/employees/1/'+kind,method='POST',upload=True)
  finally:image_utils.save_image=original_save
  await call('admin-bank-update',1,{'bank_name':'BANK-NAME-UPDATED'})
  await call('admin-create',1,{'name':'SYNTHETIC NEW','employee_no':'fix01-admin','password':'synthetic123','bank_account_number':'NEW-BANK','nationality':'泰国','thai_id_number':'9876543210123','salary_template_id':1,'deduction_template_id':1},path='/employees',method='POST')
 (OUT/'status.json').write_text(json.dumps({'requests':len(log),'failures':failures},indent=2));await engine.dispose()
 if failures:raise SystemExit(1)
if __name__=='__main__':asyncio.run(main())

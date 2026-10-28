"""Synthetic real-route evidence with DB and file before/after state; no auth substitutes."""
from fixtures import *
import gzip
from sqlalchemy import inspect as sql_inspect

def file_state():
 root=Path('/private/tmp/permissions-round7-env/uploads')
 return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()} if root.exists() else {}

class Evidence:
 def __init__(self,factory,client):self.factory=factory;self.client=client;self.records=[];self.failures=[]
 async def call(self,ident,uid,method,path,body=None,expected=200,check=None,warehouse='1',**kwargs):
  before=await snapshot(self.factory);files_before=file_state()
  headers={'Authorization':'Bearer '+create_access_token({'sub':str(uid)})} if uid is not None else {}
  if warehouse is not None:headers['X-Warehouse-ID']=warehouse
  headers.update(kwargs.pop('headers',{}))
  if body is not None:kwargs['json']=body
  response=await self.client.request(method,path if path.startswith(('/api/','/uploads/')) or path in ('/','/health') else '/api/v1'+path,headers=headers,**kwargs)
  after=await snapshot(self.factory);files_after=file_state();diff={t:{'before':before[t],'after':after[t]} for t in before if before[t]!=after[t]}
  errors=[]
  if response.status_code!=expected:errors.append(f'expected {expected}, actual {response.status_code}')
  business={t:v for t,v in diff.items() if t not in ('audit_logs','data_change_history')}
  if response.status_code>=400:
   if business:errors.append('rejected request changed business tables')
   if files_before!=files_after:errors.append('rejected request changed files')
   a=[x for x in before.get('data_change_history',[]) if x.get('module')=='makeup_request'];b=[x for x in after.get('data_change_history',[]) if x.get('module')=='makeup_request']
   if a!=b:errors.append('rejected request changed makeup business records')
  try:result=response.json()
  except ValueError:result={'bytes':len(response.content),'sha256':hashlib.sha256(response.content).hexdigest(),'content_type':response.headers.get('content-type')}
  if check:
   try:check(before,after,result,response)
   except Exception as exc:errors.append(repr(exc))
  actor=next((r for r in before['users'] if r['id']==uid),{})
  record={'id':ident,'actor':{k:actor.get(k) for k in ('id','role','warehouse_id','extra_permissions','attendance_enabled','attendance_employee_id','is_active')},'method':method,'path':path,'warehouse_header':warehouse,'request':body,'expected':expected,'actual':response.status_code,'response':result,'database_diff':diff,'file_before':files_before,'file_after':files_after,'errors':errors}
  def safe(v):
   if isinstance(v,dict):return {k:'[omitted]' if any(x in k.lower() for x in ('password','token','secret')) else safe(x) for k,x in v.items()}
   if isinstance(v,list):return [safe(x) for x in v]
   return v
  self.records.append(safe(record));self.failures.extend([ident+': '+x for x in errors])
  with gzip.open(OUT/'requests.jsonl.gz','at',encoding='utf-8') as f:f.write(json.dumps(safe(record),ensure_ascii=False,default=str)+'\n')
  (OUT/'status.json').write_text(json.dumps({'requests':len(self.records),'failures':self.failures},ensure_ascii=False,indent=2))
  print(ident,response.status_code,errors or 'PASS',flush=True)
  return result
 def finish(self):assert not self.failures,self.failures

async def environment():
 engine=create_async_engine(URL);factory=async_sessionmaker(engine,expire_on_commit=False)
 database._engine=engine;database._session_maker=factory
 async with engine.begin() as c:
  await c.execute(text('DROP SCHEMA public CASCADE'));await c.execute(text('CREATE SCHEMA public'));await c.run_sync(database.Base.metadata.create_all)
 async with factory() as db:await seed(db)
 return engine,factory

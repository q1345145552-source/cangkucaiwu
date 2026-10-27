"""Real route, JWT, PG, upload and exported workbook evidence for round five."""
from fixtures import *
from io import BytesIO
from openpyxl import load_workbook
from app.models.customer import Customer
from app.models.supplier import PurchaseOrder
from app.models.data_change_history import DataChangeHistory
from app.models.recharge import RechargeDeclaration
from app.core.round5_access import PAY_FIELDS,DOCUMENT_FIELDS
LOG=[];FAIL=[]
def require(condition,message='assertion failed'):
 if not condition:raise AssertionError(message)
def all_keys(value):
 if isinstance(value,dict):return set(value)|set().union(*(all_keys(v) for v in value.values()))
 if isinstance(value,list):return set().union(*(all_keys(v) for v in value))
 return set()
async def main():
 engine=create_async_engine(URL);factory=async_sessionmaker(engine,expire_on_commit=False)
 database._engine=engine;database._session_maker=factory
 async with engine.begin() as c:
  await c.execute(text('DROP SCHEMA public CASCADE'));await c.execute(text('CREATE SCHEMA public'));await c.run_sync(database.Base.metadata.create_all)
 async with factory() as db:
  await seed(db)
  for eid in (1,2,3,4,8):
   e=await db.get(Employee,eid);e.bank_account_number=f'BANK-SENTINEL-{eid}';e.passport_number=f'PASSPORT-SENTINEL-{eid}';e.daily_wage=7123+eid;e.base_salary=91234+eid
   path=Path(os.environ['UPLOAD_DIR'])/str(e.warehouse_id)/'audit'/f'passport-{eid}.png';path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(PNG)
  db.add(User(id=11,username='nomenu-finance',display_name='NO MENU',role='staff',warehouse_id=1,password_hash='synthetic',extra_permissions=[],attendance_enabled=True));await db.flush()
  db.add(UserWarehouse(user_id=11,warehouse_id=1));db.add(Employee(id=11,user_id=11,warehouse_id=1,name='SELF NO MENU',hire_date=datetime(2026,10,1)))
  db.add(Employee(id=6,user_id=6,warehouse_id=1,name='SELF SUP NO MENU',hire_date=datetime(2026,10,1)))
  await db.flush()
  for uid in (6,11):
   u=await db.get(User,uid);u.attendance_enabled=True;u.attendance_employee_id=uid
  for cid,wid in ((1,1),(2,1),(8,2)):
   db.add(Customer(id=cid,warehouse_id=wid,customer_code=f'R5-{cid}',company_name=f'CUSTOMER-{cid}',contact_person=f'CONTACT-SENTINEL-{cid}',contact_info=f'PHONE-SENTINEL-{cid}',credit_limit=99881+cid))
  await db.flush()
  for rid,uid in ((1,2),(2,3),(8,8)):
   db.add(RechargeDeclaration(id=rid,warehouse_id=2 if rid==8 else 1,customer_id=8 if rid==8 else 1,declare_date=datetime(2026,10,20),amount=100+rid,declarer_id=uid,currency='THB'))
  db.add(User(id=12,username='multi-admin',display_name='MULTI ADMIN',role='warehouse_admin',warehouse_id=1,password_hash='synthetic',extra_permissions=[]));await db.flush()
  db.add_all([UserWarehouse(user_id=12,warehouse_id=w) for w in (1,2)])
  for wid in (1,2):db.add(PurchaseOrder(id=wid,warehouse_id=wid,supplier_id=wid,order_number=f'PO-SENTINEL-{wid}',total_amount=123.45,items=[{'product_name':f'ONSITE-PRODUCT-{wid}','quantity':2,'unit_price':61.725}],status='confirmed'))
  for module,wid in (('payroll',1),('employee',1),('makeup_request',1),('employee',2)):
   db.add(DataChangeHistory(module=module,record_id=1,warehouse_id=wid,operation_type='update',operator_id=1,before_data={'bank_account_number':'LOG-BANK-SENTINEL','base_salary':919191,'name':'ONSITE-OLD'},after_data={'bank_account_number':'LOG-BANK-SENTINEL','base_salary':929292,'name':'ONSITE-NEW'}))
  await db.commit()
 async with AsyncClient(transport=ASGITransport(app=app,raise_app_exceptions=False),base_url='http://round5.local') as client:
  async def call(name,uid,path,status=200,check=None,method='GET',body=None,headers=None,files=None):
   before=await snapshot(factory)
   kwargs={'json':body} if body is not None else {}
   if files:kwargs={'files':files}
   r=await client.request(method,path if path.startswith('/uploads/') else '/api/v1'+path,headers={'Authorization':'Bearer '+create_access_token({'sub':str(uid)}),**(headers or {})},**kwargs)
   after=await snapshot(factory);diff={t:{'before':before[t],'after':after[t]} for t in before if before[t]!=after[t]};errors=[]
   try:value=r.json()
   except Exception:value={'length':len(r.content),'sha256':hashlib.sha256(r.content).hexdigest(),'text':r.text[:200] if not r.headers.get('content-type','').startswith(('image/','application/vnd')) else None}
   if r.status_code!=status:errors.append(f'expected {status}, actual {r.status_code}')
   if method=='GET' or r.status_code>=400:
    if any(t not in ('audit_logs','data_change_history') for t in diff):errors.append('read/rejection changed business data')
   if method=='GET' and before.get('data_change_history') != after.get('data_change_history'):errors.append('read changed history including makeup business rows')
   if 'no-store' not in r.headers.get('cache-control',''):errors.append('missing private no-store')
   if check and r.status_code==status:
    try:check(value,r)
    except Exception as exc:errors.append(repr(exc))
   if path.startswith('/api/v1'):raise AssertionError('relative API paths only')
   LOG.append({'id':name,'user':uid,'method':method,'path':path,'expected':status,'actual':r.status_code,'response':value,'headers':dict(r.headers),'database_diff':diff,'errors':errors});FAIL.extend(name+': '+e for e in errors)
   print(name,r.status_code,errors or 'PASS',flush=True)
   (OUT/'target-requests.json').write_text(json.dumps(LOG,ensure_ascii=False,indent=2));return r
  for uid in (1,2,3,4):
   await call(f'A-employees-{uid}',uid,'/employees',check=lambda v,r,uid=uid:(require(not (DOCUMENT_FIELDS & all_keys(v)) if uid!=1 else 'PASSPORT-SENTINEL-1' in r.text),require(not(PAY_FIELDS & all_keys(v)) if uid==2 else 'BANK-SENTINEL-1' in r.text),require('BANK-SENTINEL-8' not in r.text)))
  for uid in (6,11,5,7):await call(f'A-no-access-{uid}',uid,'/employees',401 if uid==7 else 403)
  for uid in (1,2,3):
   await call(f'A-summary-{uid}',uid,'/employees/1/summary?month=2026-10',check=lambda v,r,uid=uid:require(not(PAY_FIELDS & all_keys(v))) if uid==2 else None)
   await call(f'A-cross-head-{uid}',uid,'/employees',403,headers={'X-Warehouse-ID':'2'})
   await call(f'A-cross-id-{uid}',uid,'/employees/8/summary',404)
  for path in ('/payroll','/payroll/summary','/payroll/1','/payroll/export','/salary-templates','/deduction-templates','/reports/previews','/reports/income-expense','/reports/credit','/dashboard/cockpit','/dashboard/trends','/income-expense/expense','/incoming','/reconciliation/results','/payable','/cash-advances'):
   await call('B-supervisor-deny-'+path,2,path,403)
  for uid in (2,3,4,6,11,5):
   for path in ('/payroll/my-payslip','/employee-advances/my-debt'):
    await call(f'A-self-{uid}-{path}',uid,path)
    await call(f'A-self-spoof-{uid}-{path}',uid,path+'?employee_id=8',403)
  for header in ('2','all','999','bad',''):
   await call('A-invalid-scope-'+header,2,'/employees',403,headers={'X-Warehouse-ID':header})
  await call('A-multi-selected',12,'/employees',headers={'X-Warehouse-ID':'2'},check=lambda v,r:require('BANK-SENTINEL-8' in r.text and 'BANK-SENTINEL-1' not in r.text))
  await call('A-multi-all',12,'/employees',headers={'X-Warehouse-ID':'all'},check=lambda v,r:require('BANK-SENTINEL-8' in r.text and 'BANK-SENTINEL-1' in r.text))
  await call('A-multi-unauthorized',12,'/employees',403,headers={'X-Warehouse-ID':'999'})
  for uid in (1,2,3):
   def pdf_check(v,r):
    sys.path.append('/Users/xiongliu/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/lib/python3.12/site-packages')
    from pypdf import PdfReader
    doc=PdfReader(BytesIO(r.content));content=''.join(page.extract_text() for page in doc.pages)
    require('PO-SENTINEL-1' in content and 'PO-SENTINEL-2' not in content,content[:100])
    (OUT/f'purchase-{uid}.pdf').write_bytes(r.content)
   await call(f'C-purchase-pdf-{uid}',uid,'/suppliers/purchase-orders/1/pdf',check=pdf_check)
   await call(f'C-purchase-pdf-cross-{uid}',uid,'/suppliers/purchase-orders/2/pdf',403)
  for uid in (6,11,7):await call(f'C-pdf-no-access-{uid}',uid,'/suppliers/purchase-orders/1/pdf',401 if uid==7 else 403)
  await call('A-onsite-edit',2,'/employees/1',method='PUT',body={'remark':'ONSITE FACT'})
  for uid in (1,3):
   await call(f'B-finance-report-{uid}',uid,'/reports/recharge-summary',check=lambda v,r:require('CUSTOMER-8' not in r.text))
   await call(f'B-finance-payroll-{uid}',uid,'/payroll',check=lambda v,r:require('SYNTHETIC EMP 8' not in r.text))
   await call(f'B-finance-cross-query-{uid}',uid,'/reports/recharge-summary?warehouse_id=2',403)
  await call('B-no-menu-report',11,'/reports/recharge-summary',403)
  await call('B-onsite-home',2,'/dashboard/stats',check=lambda v,r:require(set(v)<= {'scope','employee_count'}))
  await call('B-onsite-efficiency',2,'/efficiency/summary?month=2026-10&view=month',check=lambda v,r:require(not({'labor_cost','cost_per_order','cross_check'}&all_keys(v))))
  await call('C-customer-list-denied',2,'/customers',403)
  await call('C-customer-search',2,'/customers?search=CUSTOMER-1',check=lambda v,r:(require(len(v['data'])==1),require('CONTACT-SENTINEL' not in r.text)))
  await call('C-customer-wildcard',2,'/customers?search=%25',403)
  await call('C-customer-second-page',2,'/customers?search=CUSTOMER&page=2',403)
  await call('C-customer-unbounded',2,'/customers?search=CUSTOMER&page_size=99999',403)
  await call('C-customer-detail',2,'/customers/1',check=lambda v,r:require('CONTACT-SENTINEL' not in r.text))
  for uid in (1,3):
   for path in ('/payroll/export','/history/export','/reports/recharge-summary?format=excel'):
    def workbook(v,r):
     wb=load_workbook(BytesIO(r.content),data_only=False);cells=[str(c.value) for sheet in wb for row in sheet for c in row if c.value is not None]
     require(bool(cells),'empty workbook');require(not any('SENTINEL-8' in c or 'SYNTHETIC EMP 8' in c or 'LOG-BANK-SENTINEL' in c for c in cells),'foreign/private data exported')
     (OUT/f'export-{uid}-{path.split("?")[0].replace("/","_")}.xlsx').write_bytes(r.content)
    await call(f'C-export-{uid}-{path}',uid,path,check=workbook)
  await call('A-preview-supervisor',2,'/payroll/preview',403,method='POST',body={'employee_ids':[1],'period':'2026-10'})
  await call('A-preview-no-menu',11,'/payroll/preview',403,method='POST',body={'employee_ids':[1],'period':'2026-10'})
  await call('B-account-selection',2,'/accounts',check=lambda v,r:require(not ({'current_balance','opening_balance','account_number','account_holder'} & all_keys(v))))
  await call('B-supplier-ai-cache',2,'/suppliers',check=lambda v,r:require('ai_evaluation' not in all_keys(v)))
  for uid in (2,6,11):
   await call(f'A-valid-self-funding-{uid}',uid,'/employee-advances/funding-options?view=self',check=lambda v,r:require('available_amount' not in all_keys(v)))
  async with factory() as db:
   user=await db.get(User,3);user.extra_permissions=[p for p in ALL if p not in ('工资','payroll')];await db.commit()
  await call('A-live-field-revocation',3,'/employees',check=lambda v,r:require(not (PAY_FIELDS & all_keys(v))))
  await call('A-live-payroll-revocation',3,'/payroll',403)
  async with factory() as db:
   (await db.get(User,3)).extra_permissions=ALL;await db.commit()
  await call('B-own-advances',2,'/employee-advances',check=lambda v,r:require(all(x['employee_id']==2 for x in v['data'])))
  await call('B-other-advance',2,'/employee-advances/2',404)
  await call('B-other-advance-filter',2,'/employee-advances?employee_id=3',403)
  await call('B-own-expense',2,'/expense-approvals',check=lambda v,r:require(all(x['applicant_id']==2 for x in v['data'])))
  await call('B-own-recharge',2,'/recharge',check=lambda v,r:require([x['id'] for x in v['data']]==[1]))
  await call('B-other-recharge',2,'/recharge/2',403)
  await call('B-history',2,'/history',check=lambda v,r:(require('LOG-BANK-SENTINEL' not in r.text),require('makeup_request' not in r.text),require('929292' not in r.text)))
  for uid,status in ((1,200),(2,403),(3,403),(5,200),(6,403),(7,401),(8,403)):
   await call(f'D-employee-document-{uid}',uid,'/uploads/1/audit/passport-1.png',status,check=lambda v,r,status=status:require(r.content==PNG if status==200 else r.content!=PNG))
  # Actual upload, temporary-owner scope, then actual reimbursement reference and revocation.
  upload=await call('D-real-upload',3,'/upload',method='POST',files={'file':('receipt.png',PNG,'image/png')})
  path=upload.json().get('path')
  if path:
   for uid,status in ((3,200),(2,403),(4,403),(8,403)):
    await call(f'D-temporary-{uid}',uid,'/'+path,status)
   async with factory() as db:
    (await db.get(ReimbursementItem,1)).receipt=path;await db.commit()
   for uid,status in ((3,200),(4,200),(2,403),(1,200)):
    await call(f'D-associated-{uid}',uid,'/'+path,status)
   async with factory() as db:
    (await db.get(User,4)).extra_permissions=[];await db.commit()
   await call('D-revoked-old-url',4,'/'+path,403)
   async with factory() as db:
    (await db.get(Employee,3)).status='resigned';await db.commit()
   await call('D-invalid-self-old-url',3,'/'+path) # Still independent management permission; not a personal entitlement.
   await call('A-invalid-self',3,'/payroll/my-payslip',403)
  (OUT/'target-status.json').write_text(json.dumps({'records':len(LOG),'failures':FAIL},ensure_ascii=False,indent=2))
 await engine.dispose()
 if FAIL:raise AssertionError(FAIL)
if __name__=='__main__':asyncio.run(main())

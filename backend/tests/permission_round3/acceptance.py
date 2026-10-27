"""Round-three target checks: real app, authentication, transactions and synthetic DB only."""
from fixtures import *
LOG=[];FAIL=[]
async def main():
 engine=create_async_engine(URL);factory=async_sessionmaker(engine,expire_on_commit=False)
 database._engine=engine;database._session_maker=factory
 async with engine.begin() as c:
  await c.execute(text('DROP SCHEMA public CASCADE'));await c.execute(text('CREATE SCHEMA public'));await c.run_sync(database.Base.metadata.create_all)
 async with factory() as db:await seed(db)
 for relative in ['1/2026-10/reimbursement-payments/proof.png','1/2026-10/cash-advances/proof.png']:
  p=Path(os.environ['UPLOAD_DIR'])/relative;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(PNG)
 async with AsyncClient(transport=ASGITransport(app=app,raise_app_exceptions=False),base_url='http://round3.local') as client:
  async def call(name,uid,method,path,body=None,status=200,check=None,headers=None):
   before=await snapshot(factory);h={'Authorization':'Bearer '+create_access_token({'sub':str(uid)}),**(headers or {})}
   r=await client.request(method,'/api/v1'+path,json=body,headers=h)
   try:response=r.json()
   except Exception:response={'text':r.text}
   after=await snapshot(factory);diff={t:{'before':before[t],'after':after[t]} for t in before if before[t]!=after[t]};errors=[]
   if r.status_code!=status:errors.append(f'expected {status} actual {r.status_code}')
   if r.status_code>=400 and any(t not in ('audit_logs','data_change_history') for t in diff):errors.append('rejection mutated business data')
   if check:
    try:check(before,after,response)
    except Exception as exc:errors.append(repr(exc))
   LOG.append({'id':name,'user':uid,'method':method,'path':path,'request':body,'expected':status,'actual':r.status_code,'response':response,'database_diff':diff,'errors':errors});FAIL.extend(name+': '+e for e in errors)
   print(name,r.status_code,errors or 'PASS',str(response)[:250],flush=True)
   (OUT/'requests.json').write_text(json.dumps(LOG,ensure_ascii=False,indent=2));return response
  def paid_once(table,amount):
   def check(a,b,r):
    rows=[x for x in b[table] if x['id'] not in {y['id'] for y in a[table]}]
    assert len(rows)==1 and float(rows[0]['amount'])==amount, rows
   return check
  def no_money(a,b,r):
   for t in ('expense_records','payable_payments','reimbursement_payments','expense_fund_items','cash_advance_repayments'):
    assert a[t]==b[t],t
  for uid in (2,5,6,7):
   expected=401 if uid==7 else 403
   await call(f'A-calc-deny-{uid}',uid,'POST','/payroll/calculate',{'employee_ids':[1],'end_date':'2026-10-16'},expected)
   await call(f'A-confirm-deny-{uid}',uid,'POST','/payroll/1/confirm',status=expected)
   await call(f'A-pay-deny-{uid}',uid,'POST','/payroll/2/disburse',{'account_id':1},expected)
  await call('A-supervisor-fact',2,'POST','/clock-in/makeup',{'employee_id':1,'date':'2026-10-16','sessions':[1,2,3,4],'reason':'SYNTHETIC onsite fact'})
  await call('A-finance-preview',3,'POST','/payroll/preview',{'employee_ids':[1],'end_date':'2026-10-16'})
  await call('A-finance-calculate',3,'POST','/payroll/calculate',{'employee_ids':[1],'end_date':'2026-10-16'})
  async with factory() as db:
   rid=(await db.execute(select(PayrollRecord.id).where(PayrollRecord.employee_id==1).order_by(PayrollRecord.id.desc()))).scalars().first()
  await call('A-finance-confirm-deny',3,'POST',f'/payroll/{rid}/confirm',status=403)
  await call('A-admin-confirm',1,'POST',f'/payroll/{rid}/confirm',check=no_money)
  await call('A-finance-pay',3,'POST',f'/payroll/{rid}/disburse',{'account_id':1},check=paid_once('expense_records',400))
  await call('A-finance-self-payslip',3,'GET','/payroll/my-payslip')
  await call('A-supervisor-self-payslip',2,'GET','/payroll/my-payslip')
  # Ordinary reimbursement: finance verification, administrator approval, independent execution.
  created=await call('B-create',2,'POST','/reimbursement',{'submit_date':'2026-10-20','items':[{'category':'其他','amount':30},{'category':'其他','amount':10}]})
  rid=created.get('id',9999);detail=await call('B-detail',3,'GET',f'/reimbursement/{rid}')
  items=[{'item_id':d['id'],'status':'approved' if i==0 else 'rejected'} for i,d in enumerate(detail.get('items',[]))]
  await call('B-supervisor-review',2,'POST',f'/reimbursement/{rid}/review',{'items':items},403)
  await call('B-unverified-approve',1,'POST',f'/reimbursement/{rid}/review',{'items':items},409)
  await call('B-verify',3,'POST',f'/reimbursement/{rid}/verify',check=no_money)
  await call('B-approve-partial',1,'POST',f'/reimbursement/{rid}/review',{'items':items},check=no_money)
  await call('B-pay',3,'POST',f'/reimbursement/{rid}/pay',{'payment_account_id':1,'payment_voucher_path':'uploads/1/2026-10/reimbursement-payments/proof.png'},check=paid_once('reimbursement_payments',30))
  # Employee advance is a request, not an automatic outflow.
  adv=await call('C-advance-request',2,'POST','/employee-advances',{'employee_id':1,'amount':50,'advance_date':'2026-10-20','funding_source':'company_account','payment_account_id':1},check=no_money)
  aid=adv.get('id',9999)
  await call('C-advance-unapproved',3,'POST',f'/employee-advances/{aid}/execute',status=409)
  await call('C-advance-verify',3,'POST',f'/employee-advances/{aid}/verify',check=no_money)
  await call('C-advance-approve',1,'POST',f'/employee-advances/{aid}/approve',check=no_money)
  await call('C-advance-execute',3,'POST',f'/employee-advances/{aid}/execute',check=paid_once('expense_records',50))
  await call('C-advance-repeat',4,'POST',f'/employee-advances/{aid}/execute',status=409)
  loan=await call('C-cash-request',2,'POST','/cash-advances',{'advance_date':'2026-10-20','amount':100,'purpose':'expense'},check=no_money)
  lid=loan.get('id',9999)
  await call('C-cash-verify',3,'POST',f'/cash-advances/{lid}/verify',check=no_money)
  await call('C-cash-approve',1,'POST',f'/cash-advances/{lid}/confirm',check=no_money)
  await call('C-cash-repay',3,'POST',f'/cash-advances/{lid}/repayments',{'amount':50,'account_id':1,'payment_method':'cash','voucher_path':'uploads/1/2026-10/cash-advances/proof.png','request_key':'synthetic-round3-cash'},check=paid_once('cash_advance_repayments',50))
  await call('D-supervisor-pay',2,'PUT','/payable/2/pay?account_id=1',status=403)
  await call('D-unapproved-pay',3,'PUT','/payable/2/pay?account_id=1',status=409)
  await call('D-verify',3,'POST','/payable/2/verify-payment',check=no_money)
  await call('D-approve',1,'POST','/payable/2/approve-payment',check=no_money)
  await call('D-pay',3,'PUT','/payable/2/pay?account_id=1',check=paid_once('payable_payments',100))
  from scenarios import scenarios
  await scenarios(factory,client,call,LOG,FAIL)
 (OUT/'requests.json').write_text(json.dumps(LOG,ensure_ascii=False,indent=2))
 (OUT/'status.json').write_text(json.dumps({'marker':'permissions7-r03-20261028','test_records':len(LOG),'http_requests':sum(len(x['requests']) if 'requests' in x else 1 for x in LOG),'failures':FAIL},ensure_ascii=False,indent=2))
 await engine.dispose()
 assert not FAIL,FAIL
if __name__=='__main__':asyncio.run(main())

"""Missing route branches with synthetic data, actual guards, whole-DB denial checks."""
from harness import *
from app.core.security import hash_password,verify_password
READS=['/supplier-controls/exceptions','/sku-catalog/reference','/sku-catalog/tags','/expense-identities/suppliers','/suppliers/categories','/suppliers/price-threshold','/suppliers/price-stats','/suppliers/price-trend?product_name=SYNTHETIC','/suppliers/price-anomalies','/suppliers/non-lowest-records','/suppliers/non-lowest-summary','/suppliers/1/logistics-prices','/suppliers/1','/income-expense/categories','/expense-fund/employees','/expense-fund/payment-accounts','/expense-fund/accounts/1/disbursements','/expense-fund/review/pending','/expense-fund/recharge/requests','/expense-fund/settings','/expense-fund/balance','/expense-fund/alert','/reimbursement/export','/rates/query','/clock-in/makeup-requests','/employee-advances/1','/credit/1/detail','/credit/dashboard','/credit/assessment','/credit/assessment/export','/credit/alerts']
async def main():
 engine,factory=await environment()
 async with factory() as db:
  for wid in (1,2):db.add(Customer(id=wid,warehouse_id=wid,customer_code=f'SYN-{wid}',company_name=f'SYNTHETIC CUSTOMER {wid}'))
  await db.flush()
  db.add(CreditCustomer(id=1,warehouse_id=1,customer_id=1,credit_limit=1000,status='active',current_debt=0))
  (await db.get(User,3)).password_hash=hash_password('SYNTHETIC-old-password')
  await db.commit()
 async with AsyncClient(transport=ASGITransport(app=app),base_url='http://local') as client:
  ev=Evidence(factory,client)
  await ev.call('seed-current-rate',1,'POST','/rates',{'rate':5,'from_currency':'CNY','to_currency':'THB','effective_from':'2026-10-01T00:00:00'})
  for n,path in enumerate(READS):
   await ev.call(f'read-{n}-authorized',1,'GET',path)
   await ev.call(f'read-{n}-forged-warehouse',1,'GET',path,warehouse='2',expected=403)
   await ev.call(f'read-{n}-labor',5,'GET',path,expected=200 if path=='/clock-in/makeup-requests' else 403)
  for path in ('/','/health'):await ev.call('public-'+path,None,'GET',path,warehouse=None)
  await ev.call('own-access-description',3,'GET','/access/me')
  await ev.call('warehouse-list',1,'GET','/warehouses')
  await ev.call('warehouse-create-supervisor-deny',2,'POST','/warehouses',{'name':'SYNTHETIC THIRD','code':'SYN3'},expected=403)
  made=await ev.call('warehouse-create-admin',1,'POST','/warehouses',{'name':'SYNTHETIC THIRD','code':'SYN3'})
  await ev.call('warehouse-update-admin',1,'PUT',f'/warehouses/{made["id"]}',{'name':'SYNTHETIC THIRD UPDATED'},warehouse=str(made['id']))
  await ev.call('warehouse-update-foreign',1,'PUT','/warehouses/2',{'name':'DENIED'},expected=403)
  await ev.call('fund-setting-admin',1,'POST','/expense-fund/settings',{'key':'fund_limit','value':'5000'})
  price=await ev.call('logistics-create',1,'POST','/suppliers/1/logistics-prices',{'transport_method':'land','cargo_type':'general','origin_warehouse':'SYNTHETIC','price_per_cbm':100,'estimated_days':'3','currency':'THB'})
  await ev.call('logistics-cross-parent',1,'DELETE',f'/suppliers/2/logistics-prices/{price["id"]}',expected=403)
  await ev.call('logistics-delete',1,'DELETE',f'/suppliers/1/logistics-prices/{price["id"]}')
  await ev.call('change-own-password',3,'POST','/auth/change-password',{'old_password':'SYNTHETIC-old-password','new_password':'SYNTHETIC-new-password'})
  async with factory() as db:assert verify_password('SYNTHETIC-new-password',(await db.get(User,3)).password_hash)
  await ev.call('attachment-cookie-set',3,'POST','/auth/attachment-session',{},check=lambda b,a,r,res:assert_cookie(res))
  await ev.call('attachment-cookie-clear',3,'POST','/auth/attachment-session',{'clear':True})
  ev.finish()
 await engine.dispose()
def assert_cookie(response):
 cookie=response.headers['set-cookie'];assert 'HttpOnly' in cookie and 'Path=/uploads' in cookie and 'SameSite=lax' in cookie
if __name__=='__main__':asyncio.run(main())

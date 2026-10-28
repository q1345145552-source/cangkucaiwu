"""Remaining constructible routes. Synthetic historical evidence; no external provider calls."""
from harness import *
from datetime import timedelta
from app.core.timezone import thai_now
from app.models import Customer, SupplierProduct, SupplierQuote, SupplierQuoteRevision, ProcurementActionException, PurchaseOrder
from app.services.payable_creation import fingerprint
from app.services import procurement_controls as duty
async def main():
 engine,factory=await environment()
 async with factory() as db:
  for wid in (1,2):
   db.add(Customer(id=20+wid,warehouse_id=wid,customer_code=f'SYN-GAP-{wid}',company_name=f'SYN CUSTOMER {wid}'))
   db.add(PurchaseOrder(id=20+wid,warehouse_id=wid,supplier_id=wid,created_by=2 if wid==1 else 8,order_number=f'SYN-GAP-{wid}',total_amount=100,currency='THB',status='pending',items=[]))
   db.add(SupplierProduct(id=20+wid,supplier_id=wid,product_name=f'SYN PRODUCT {wid}',unit='件',unit_price=10,currency='THB'))
  await db.flush()
  for wid in (1,2):
   db.add(SupplierQuote(id=20+wid,warehouse_id=wid,product_id=20+wid,code=f'SYN-Q-{wid}',current_revision=1))
   db.add(ProcurementActionException(id=20+wid,warehouse_id=wid,purchase_order_id=20+wid,action='reject',operator_id=1 if wid==1 else 8,policy_version='synthetic-historical',business_version='synthetic-historical',request_key=f'syn-{wid}',request_fingerprint='synthetic',granted_by=1 if wid==1 else 8,reason='SYN historical revoked authorization',expires_at=thai_now()+timedelta(days=1),status='revoked'))
  await db.flush()
  for wid in (1,2):
   terms={'tiers':[],'currency':'THB','unit':'件'};binding={}
   db.add(SupplierQuoteRevision(id=20+wid,warehouse_id=wid,quote_id=20+wid,revision=1,request_key=f'syn-revision-{wid}',request_fingerprint='synthetic',content_fingerprint=fingerprint({'terms':terms,'binding':binding}),terms=terms,product_binding=binding,operator_id=1 if wid==1 else 8,operator_name='SYN administrator'))
  db.add(User(id=9,username='synthetic-superadmin',display_name='SYN platform',role='super_admin',password_hash='not-login',warehouse_id=1,extra_permissions=ALL,is_active=True));await db.flush();db.add(UserWarehouse(user_id=9,warehouse_id=1))
  await db.commit()
 async with AsyncClient(transport=ASGITransport(app=app),base_url='http://local') as client:
  ev=Evidence(factory,client)
  for name,path in [('quote-history','/supplier-quotes/21/revisions'),('exception-detail','/supplier-controls/exceptions/21'),('attendance-times','/config/attendance-times')]:
   await ev.call(name+'-labor',5,'GET',path,expected=403)
   await ev.call(name+'-foreign-header',1,'GET',path,warehouse='2',expected=403)
   await ev.call(name,1,'GET',path)
  await ev.call('quote-history-foreign-object',1,'GET','/supplier-quotes/22/revisions',expected=404)
  await ev.call('exception-foreign-object',1,'GET','/supplier-controls/exceptions/22',expected=404)
  body={'customer_id':21,'credit_limit':1000,'repayment_day':15}
  await ev.call('credit-create-labor',5,'POST','/credit',body,expected=403)
  await ev.call('credit-create-supervisor',2,'POST','/credit',body,expected=403)
  await ev.call('credit-create-foreign',1,'POST','/credit',{**body,'customer_id':22},expected=403)
  credit=await ev.call('credit-create-admin',1,'POST','/credit',body)
  if 'id' in credit:
   path=f"/credit/{credit['id']}"
   await ev.call('credit-update-supervisor',2,'PUT',path,{'credit_limit':1200},expected=403)
   await ev.call('credit-update-foreign-header',1,'PUT',path,{'credit_limit':1200},warehouse='2',expected=403)
   await ev.call('credit-update-admin',1,'PUT',path,{'credit_limit':1200})
  context=await ev.call('purchase-reject-context',1,'GET','/supplier-controls/orders/21/context?action=reject')
  body={'reason':'SYN rejected after review','request_key':'syn-reject-21','expected_policy_version':context.get('policy_version'),'expected_business_version':context.get('business_version')}
  await ev.call('purchase-reject-labor',5,'PUT','/suppliers/purchase-approvals/21/reject',body,expected=403)
  await ev.call('purchase-reject-cross-header',1,'PUT','/suppliers/purchase-approvals/21/reject',body,warehouse='2',expected=403)
  await ev.call('purchase-reject',1,'PUT','/suppliers/purchase-approvals/21/reject',body)
  await ev.call('fund-void-supervisor',2,'DELETE','/expense-fund/accounts/1/items/1',{'reason':'SYN void'},expected=403)
  await ev.call('fund-void',1,'DELETE','/expense-fund/accounts/1/items/1',{'reason':'SYN void'})
  await ev.call('ai-compare-no-input',1,'POST','/suppliers/ai-compare',{})
  await ev.call('ai-evaluation-admin-denied',1,'GET','/suppliers/1/ai-evaluation',expected=403)
  await ev.call('ai-evaluation-platform-denied',9,'GET','/suppliers/1/ai-evaluation',expected=403)
  await ev.call('ai-evaluation-cross-object',9,'GET','/suppliers/2/ai-evaluation',expected=403)
  ev.finish()
 await engine.dispose()
if __name__=='__main__':asyncio.run(main())

"""Real PostgreSQL routes: supervisor implicit personal mode and linked financial projection."""
from harness import *
from app.core.action_access import encode_permissions

def require(ok,message):
 assert ok,message

async def main():
 engine,f=await environment()
 async with f() as db:
  db.add(PurchaseOrder(id=21,warehouse_id=1,supplier_id=1,order_number='SYN-21',total_amount=100,currency='THB',items=[],status='confirmed',payable_bill_id=1))
  await db.flush();bill=await db.get(PayableBill,1);bill.purchase_order_id=21;bill.remark='FINANCIAL-SECRET-R7-ONLY';await db.commit()
 async with AsyncClient(transport=ASGITransport(app=app),base_url='http://local') as c:
  ev=Evidence(f,c)
  for mode in ('legacy-all','v1-onsite','no-extra'):
   async with f() as db:
    u=await db.get(User,2);u.extra_permissions=ALL if mode=='legacy-all' else encode_permissions(u.role,['employee_advances:operate','suppliers:view']) if mode=='v1-onsite' else []
    await db.commit()
   body={'employee_id':2,'amount':10,'advance_date':'2026-10-28','funding_source':'company_account','payment_account_id':1}
   await ev.call(mode+'-own-request',2,'POST','/employee-advances',body,check=lambda b,a,d,r:require(d['approval_status']=='pending' and d['expense_record_id'] is None,'must not execute'))
   for eid in (1,8):await ev.call(mode+'-other-'+str(eid),2,'POST','/employee-advances',{**body,'employee_id':eid},expected=403)
   await ev.call(mode+'-account-substitution',2,'POST','/employee-advances',{**body,'employee_id':None,'user_id':3},expected=403)
   if mode!='no-extra':
    await ev.call(mode+'-purchase-read-redacted',2,'GET','/suppliers/purchase-orders/21',check=lambda b,a,d,r:require(d['bill'] is None and not d['can_read_payable'] and 'FINANCIAL-SECRET-R7-ONLY' not in json.dumps(d),'linked bill leak'))
  for uid in (1,3):await ev.call('authorized-financial-read-'+str(uid),uid,'GET','/suppliers/purchase-orders/21',check=lambda b,a,d,r:require(d['bill']['remark']=='FINANCIAL-SECRET-R7-ONLY','authorized detail lost'))
  async with f() as db:
   (await db.get(User,2)).attendance_enabled=False;await db.commit()
  await ev.call('disabled-self-binding',2,'POST','/employee-advances',body,expected=403)
  ev.finish()
 await engine.dispose()
if __name__=='__main__':asyncio.run(main())

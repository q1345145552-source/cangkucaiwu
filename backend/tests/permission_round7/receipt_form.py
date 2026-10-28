"""Structured multipart receipt lines use actual parent and existing version/receipt services."""
from harness import *
from app.core.action_forms import contract
from app.core.action_access import CATALOG
async def main():
 engine,factory=await environment()
 async with factory() as db:
  for pid,wid in ((21,1),(22,1),(28,2)):
   db.add(PurchaseOrder(id=pid,warehouse_id=wid,supplier_id=wid,created_by=1 if wid==1 else 8,order_number=f'SYN-{pid}',total_amount=100,currency='THB',status='confirmed',items=[{'line_id':f'line-{pid}','product_name':f'SYNTHETIC {pid}','quantity':10,'received_quantity':0,'unit':'个','unit_price':10,'subtotal':100}]))
  await db.commit()
 async with AsyncClient(transport=ASGITransport(app=app),base_url='http://local') as client:
  ev=Evidence(factory,client)
  row=next(r for r in CATALOG['routes'] if r['id']=='suppliers.receive_purchase')
  form=contract(app,row,'staff');assert form['body']['properties']['items']['encoding']=='json-string'
  def url(field,extra=''):return '/access/choices/suppliers?action=suppliers.receive_purchase&field='+field+extra
  parent=await ev.call('receipt-parent-context',4,'GET',url('path:po_id','&selected_id=21'))
  await ev.call('receipt-lines-only-parent',4,'GET',url('body:items.[].line_id','&parent_id=21'),check=lambda b,a,r,res:assert_ids(r,['line-21']))
  await ev.call('receipt-line-context',4,'GET',url('body:items.[].line_id','&parent_id=21&selected_id=line-21'),check=lambda b,a,r,res:assert_quantity(r))
  await ev.call('receipt-other-parent-line',4,'GET',url('body:items.[].line_id','&parent_id=21&selected_id=line-22'),expected=403)
  await ev.call('receipt-foreign-parent',4,'GET',url('body:items.[].line_id','&parent_id=28'),expected=403)
  await ev.call('receipt-labor-denied',5,'GET',url('body:items.[].line_id','&parent_id=21'),expected=403)
  await ev.call('receipt-numeric-object-invalid',4,'GET',url('path:po_id','&selected_id=line-21'),expected=400)
  data={'items':json.dumps([{'line_id':'line-21','received_quantity':3}]),'request_key':'SYNTHETIC-receipt-form','remark':'SYNTHETIC','expected_policy_version':parent['versions']['expected_policy_version'],'expected_business_version':parent['versions']['expected_business_version']}
  await ev.call('receipt-form-submit',4,'POST','/suppliers/purchase-orders/21/receive',data=data,files={'file':('receipt.png',PNG,'image/png')},check=lambda b,a,r,res:check_received(a,3))
  await ev.call('receipt-form-replay',4,'POST','/suppliers/purchase-orders/21/receive',data=data,files={'file':('receipt.png',PNG,'image/png')},check=lambda b,a,r,res:check_received(a,3))
  await ev.call('receipt-form-stale-reject',4,'POST','/suppliers/purchase-orders/21/receive',data={**data,'request_key':'SYNTHETIC-receipt-form-stale'},files={'file':('receipt.png',PNG,'image/png')},expected=409)
  ev.finish()
 await engine.dispose()
def assert_ids(r,ids):assert [x['id'] for x in r['data']]==ids
def assert_quantity(r):assert r['context']['quantity']==10 and r['context']['received_quantity']==0 and 'unit_price' not in r['context']
def check_received(after,quantity):
 rows=[r for r in after['purchase_receipt_events'] if r['purchase_order_id']==21]
 assert len(rows)==1 and rows[0]['items'][0]['quantity']==quantity
 assert not after['payable_payments'] and not after['expense_records']
if __name__=='__main__':asyncio.run(main())

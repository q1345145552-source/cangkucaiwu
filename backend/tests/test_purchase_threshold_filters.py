"""Real routes/auth/PostgreSQL; synthetic data only, explicit threshold policies."""
import asyncio, json, os
from pathlib import Path
from datetime import datetime
from sqlalchemy import select
from app.models import PurchaseOrder, PayableBill, Customer, RechargeDeclaration
from app.models.supplier import SupplierProduct
from tests.test_supplier_workflow_round1 import setup, request
from tests.test_incoming_operations import URL
import pytest
pytestmark = pytest.mark.skipif(not URL, reason='Requires isolated local PostgreSQL')


def test_threshold_and_filters(tmp_path, monkeypatch):
 async def run():
  evidence={}
  async with setup(tmp_path,monkeypatch,approval_threshold=None) as (_,f,c):
   async with f() as db:
    (await db.get(SupplierProduct,1)).unit_price=5
    db.add(PurchaseOrder(warehouse_id=1,supplier_id=1,order_number='OLD-2',total_amount=10,items=[],status='confirmed'))
    await db.commit()
    old={p.id:p.status for p in (await db.execute(select(PurchaseOrder))).scalars()}
   evidence['zero_saved']=await request(c,'PUT','/suppliers/purchase-approval-threshold',json={'threshold':0})
   evidence['negative']=await request(c,'PUT','/suppliers/purchase-approval-threshold',json={'threshold':-1},code=400)
   assert (await request(c,'GET','/suppliers/purchase-approval-threshold'))['threshold']==0
   async def order(q):
    return await request(c,'POST','/suppliers/1/purchase-order',json={'items':[{'product_id':1,'quantity':q}]})
   small=await order(1);evidence['five']=small
   assert small['pending'] and not small.get('payable_bill_id')
   pid=small['order']['id']
   async with f() as db:
    assert (await db.get(PurchaseOrder,pid)).status=='pending'
    assert not (await db.execute(select(PayableBill).where(PayableBill.purchase_order_id==pid))).first()
   pending=await request(c,'GET','/suppliers/purchase-approvals',uid=96)
   assert pid in [r['id'] for r in pending['pending']]
   evidence['approval']=await request(c,'PUT',f'/suppliers/purchase-approvals/{pid}/approve',uid=96,json={'request_key':'independent-approval'})
   async with f() as db:
    po=await db.get(PurchaseOrder,pid);bill=await db.get(PayableBill,po.payable_bill_id)
    assert po.status=='confirmed' and bill.amount==5 and bill.purchase_order_id==pid
    evidence['approved_state']={'status':po.status,'bill_id':bill.id,'bill_amount':bill.amount}
   await order(1)
   for status in ('pending','confirmed',''):
    r=await request(c,'GET','/suppliers/purchase-orders',params={'status':status} if status else {})
    assert r['total']==len(r['data'])
    if status:assert r['data'] and all(x['status']==status for x in r['data'])
    else:assert {x['status'] for x in r['data']}=={'pending','confirmed'}
    evidence['filter_'+(status or 'all')]={'total':r['total'],'orders':[{'id':x['id'],'status':x['status']} for x in r['data']]}
   page=await request(c,'GET','/suppliers/purchase-orders',params={'status':'confirmed','page_size':1})
   assert len(page['data'])==1 and page['total']==3
   assert (await request(c,'GET','/suppliers/purchase-orders',params={'status':'not-a-state'}))['total']==0
   await request(c,'PUT','/suppliers/purchase-approval-threshold',json={'threshold':1000})
   for qty,total,pending in ((100,500,False),(200,1000,False),(400,2000,True)):
    r=await order(qty);assert r['pending'] is pending
    async with f() as db:
     po=await db.get(PurchaseOrder,r['order']['id']);assert po.total_amount==total
     assert po.status==('pending' if pending else 'confirmed')
    evidence[str(total)]=r
   async with f() as db:
    assert {i:(await db.get(PurchaseOrder,i)).status for i in old}==old
   evidence['old_orders_unchanged']=old
  out=os.environ.get('PURCHASE_FILTER_REPORT')
  if out:Path(out).write_text(json.dumps(evidence,ensure_ascii=False,indent=2,default=str))
 asyncio.run(run())


def test_recharge_search_and_combined_filters(tmp_path,monkeypatch):
 async def run():
  async with setup(tmp_path,monkeypatch,approval_threshold=None) as (_,f,c):
   async with f() as db:
    db.add_all([Customer(id=31,warehouse_id=1,company_name='目标客户',customer_code='SYN31'),Customer(id=32,warehouse_id=2,company_name='目标外仓',customer_code='SYN32')]);await db.flush()
    for i,wid,customer,day,status,tx,remark in [(31,1,31,'2026-10-01','unmatched','TX-A','特殊%备注'),(32,1,31,'2026-09-01','matched','TX-B','其他'),(33,2,32,'2026-10-01','unmatched','TX-A','特殊%备注')]:
     db.add(RechargeDeclaration(id=i,warehouse_id=wid,customer_id=customer,declare_date=datetime.fromisoformat(day),amount=10,currency='THB',match_status=status,transaction_no=tx,remark=remark,declarer_id=1))
    await db.commit()
   for params,expected in [({'search':'TX-A'},[31]),({'search':'目标客户'},[31,32]),({'search':'特殊%'},[31]),({'search':'不存在'},[]),({'search':'目标','month':'2026-10','status':'unmatched'},[31]),({'search':'目标','month':'2026-09','status':'matched'},[32])]:
    r=await request(c,'GET','/recharge',params=params);assert sorted(x['id'] for x in r['data'])==expected,r
    assert r['total']==len(expected)
 asyncio.run(run())


def test_missing_threshold_defaults_to_approval_and_status_stays_scoped(tmp_path,monkeypatch):
 async def run():
  async with setup(tmp_path,monkeypatch,approval_threshold=None) as (_,f,c):
   assert (await request(c,'GET','/suppliers/purchase-approval-threshold'))['threshold']==0
   r=await request(c,'POST','/suppliers/1/purchase-order',json={'items':[{'product_id':1,'quantity':1}]})
   assert r['pending'] and r['payable_bill_id'] is None
   async with f() as db:
    foreign=PurchaseOrder(warehouse_id=2,supplier_id=2,order_number='FOREIGN-PENDING',total_amount=100,items=[],status='pending')
    db.add(foreign);await db.commit();foreign_id=foreign.id
   local=await request(c,'GET','/suppliers/purchase-orders',params={'status':'pending'})
   assert local['total']==1 and local['data'][0]['id']==r['order']['id']
   other=await request(c,'GET','/suppliers/purchase-orders',warehouse='2',params={'status':'pending'})
   assert other['total']==1 and other['data'][0]['id']==foreign_id
 asyncio.run(run())

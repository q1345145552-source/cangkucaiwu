"""Real PostgreSQL/JWT/HTTP, synthetic supplier20, no production access."""
import asyncio, json
from datetime import datetime
import pytest
from sqlalchemy import select, text
from app.database import Base
from app.models import Supplier, SupplierProduct, PurchaseOrder, PayableBill, User, SupplierQuote, SupplierQuoteRevision, SupplierQuoteTier, InventoryReceiptLink
from app.models.supplier import SupplierLogisticsPrice, SupplierCrossBorderPrice
from app.models.purchase_receipt import PurchaseReceiptEvent
from app.models.procurement_control import ProcurementRiskReview
from app.models.data_change_history import DataChangeHistory
from tests.test_supplier_workflow_round1 import setup
from tests.test_round2_permissions import auth
from tests.evidence_path import evidence_dir
from tests.test_incoming_operations import URL
pytestmark=pytest.mark.skipif(not URL,reason='Requires isolated local PostgreSQL')
OUT=evidence_dir('supplier-lifecycle-20261028')
async def state(f):
 async with f() as db:
  return {t.name:[dict(x) for x in (await db.execute(select(t).order_by(*t.primary_key.columns))).mappings()] for t in Base.metadata.tables.values()}
async def seed(f,records=True):
 async with f() as db:
  db.add(Supplier(id=20,warehouse_id=1,name='合成供应商20',is_active='true'))
  for uid in (3,4):(await db.get(User,uid)).extra_permissions=['供应商管理']
  await db.flush()
  if records:
   db.add(SupplierProduct(id=20,supplier_id=20,product_name='合成产品',unit_price=10,currency='THB'))
   for i in (20,21,22):db.add(PurchaseOrder(id=i,warehouse_id=1,supplier_id=20,order_number=f'SYN-{i}',total_amount=100,items=[],status='confirmed'))
   db.add(SupplierLogisticsPrice(supplier_id=20,route_name='合成路线',cargo_type='普货',starting_price=0,price_per_kg=2))
   db.add(SupplierCrossBorderPrice(supplier_id=20,transport_method='海运',cargo_type='普货',origin_warehouse='深圳仓',price_per_cbm=10))
   await db.flush()
   db.add(PayableBill(id=20,warehouse_id=1,supplier_id=20,bill_number='SYN-BILL-20',bill_date=datetime(2026,10,20),due_date=datetime(2026,10,30),amount=100,status='pending',purchase_order_id=20,source='purchase_order'))
   await db.flush()
   (await db.get(PurchaseOrder,20)).payable_bill_id=20
   db.add(SupplierQuote(id=20,warehouse_id=1,product_id=20,code='SYN-Q20',current_revision=1))
   await db.flush()
   db.add(SupplierQuoteRevision(id=20,warehouse_id=1,quote_id=20,revision=1,request_key='q20',request_fingerprint='x',content_fingerprint='x',terms={},product_binding={},operator_id=1,operator_name='合成人员'))
   db.add(PurchaseReceiptEvent(id=20,warehouse_id=1,purchase_order_id=20,request_key='receipt20',request_fingerprint='x',items=[],photo_path='synthetic.png',operator_id=1,operator_name='合成人员'))
   db.add(ProcurementRiskReview(warehouse_id=1,month='2026-10',rule='new_supplier',subject_key='x',signal_id='x',rule_version='x',scope={},evidence_version='x',snapshot={'supplier_id':20},conclusion='reviewed',reason='合成风险',reviewer_id=1,request_key='r20',request_fingerprint='x'))
   await db.flush()
   db.add(SupplierQuoteTier(revision_id=20,min_quantity=1,unit_price=10))
   db.add(InventoryReceiptLink(warehouse_id=1,receipt_event_id=20,purchase_order_id=20,line_id='l20',original_quantity=1,source_fingerprint='x',source_snapshot={},status='pending'))
  await db.execute(text("SELECT setval(pg_get_serial_sequence('suppliers','id'),(SELECT max(id) FROM suppliers))"))
  await db.commit()

def test_supplier20_delete_status_history_and_choices(tmp_path,monkeypatch):
 async def run():
  async with setup(tmp_path,monkeypatch) as (_,f,c):
   await seed(f);before=await state(f)
   r=await c.delete('/api/v1/suppliers/20',headers=auth(1));assert r.status_code==400,r.text
   for phrase in ('已有业务记录','请改用停用','3 张采购单','1 条产品报价','1 条物流报价','1 条阶梯报价','1 张应付账单','1 条库存记录','1 条收货记录','1 条风险看板记录'):assert phrase in r.text
   assert await state(f)==before
   results={'delete20':{'status':r.status_code,'response':r.json()}}
   for uid in (3,4):
    denied=await c.delete('/api/v1/suppliers/20',headers=auth(uid));assert denied.status_code==403 and denied.json()['detail']=='供应商删除只能由仓库管理员操作';assert await state(f)==before
    results['delete-role-'+str(uid)]={'status':denied.status_code,'response':denied.json()}
   disabled=await c.put('/api/v1/suppliers/20',headers=auth(1),json={'is_active':'false'});assert disabled.status_code==200,disabled.text
   after=await state(f)
   for table in before:
    if table not in ('suppliers','data_change_history','audit_logs'):assert after[table]==before[table],table
   path='/api/v1/access/choices/suppliers?action=suppliers.create_purchase_order&field=path:supplier_id'
   choices=await c.get(path,headers=auth(1));assert choices.status_code==200,choices.text
   assert 20 not in [x['id'] for x in choices.json()['data']]
   listing=await c.get('/api/v1/suppliers',headers=auth(1));assert next(x for x in listing.json()['data'] if x['id']==20)['is_active']=='false'
   po=await c.get('/api/v1/suppliers/purchase-orders/20',headers=auth(1));assert po.status_code==200 and '合成供应商20' in po.text,po.text
   bill=await c.get('/api/v1/payable/20/detail',headers=auth(1));assert bill.status_code==200 and '合成供应商20' in bill.text,bill.text
   products=await c.get('/api/v1/suppliers/20/products',headers=auth(1));assert products.status_code==200 and '合成产品' in products.text
   rejected_order=await c.post('/api/v1/suppliers/20/purchase-order',headers=auth(1),json={'request_key':'disabled-order','items':[{'product_id':20,'quantity':1}]});assert rejected_order.status_code==400,rejected_order.text
   results['disable20']={'status':disabled.status_code,'response':disabled.json(),'choices':choices.json(),'purchase_order':po.json(),'payable':bill.json(),'products':products.json(),'direct_order_status':rejected_order.status_code}
   enabled=await c.put('/api/v1/suppliers/20',headers=auth(1),json={'is_active':'true'});assert enabled.status_code==200,enabled.text
   choices=await c.get(path,headers=auth(1));assert 20 in [x['id'] for x in choices.json()['data']]
   async with f() as db:
    logs=(await db.execute(select(DataChangeHistory).where(DataChangeHistory.module=='suppliers',DataChangeHistory.record_id==20).order_by(DataChangeHistory.id))).scalars().all()
    assert [x.after_data['is_active'] for x in logs]==['false','true'];assert all(x.operator_id==1 and x.created_at and x.warehouse_id==1 for x in logs)
   empty=await c.post('/api/v1/suppliers',headers=auth(1),json={'name':'合成空供应商'});assert empty.status_code==200,empty.text
   deleted=await c.delete('/api/v1/suppliers/'+str(empty.json()['id']),headers=auth(1));assert deleted.status_code==200,deleted.text
   results['empty_delete']={'created':empty.json(),'status':deleted.status_code,'response':deleted.json()};results['enable20']={'status':enabled.status_code,'response':enabled.json()}
   (OUT/'actual.json').write_text(json.dumps(results,ensure_ascii=False,indent=2,default=str))
 asyncio.run(run())

@pytest.mark.parametrize('deferred',[False,True])
def test_real_fk_failure_flush_and_commit_roll_back(tmp_path,monkeypatch,deferred):
 async def run():
  async with setup(tmp_path,monkeypatch) as (_,f,c):
   await seed(f,False)
   async with f() as db:
    await db.execute(text('CREATE TABLE synthetic_supplier_reference (supplier_id integer REFERENCES suppliers(id) '+('DEFERRABLE INITIALLY DEFERRED' if deferred else '')+')'))
    await db.execute(text('INSERT INTO synthetic_supplier_reference VALUES (20)'));await db.commit()
   before=await state(f);r=await c.delete('/api/v1/suppliers/20',headers=auth(1));assert r.status_code==400 and '已有业务记录' in r.text,r.text
   assert await state(f)==before
 asyncio.run(run())

@pytest.mark.parametrize('action',['delete','disable','enable'])
@pytest.mark.parametrize('failure',['history','flush','commit'])
def test_injected_failures_are_chinese_and_atomic(tmp_path,monkeypatch,action,failure):
 async def run():
  from sqlalchemy.ext.asyncio import AsyncSession
  from app.services import supplier_lifecycle as life
  async with setup(tmp_path,monkeypatch) as (_,f,c):
   await seed(f,False)
   if action=='enable':
    async with f() as db:(await db.get(Supplier,20)).is_active='false';await db.commit()
   before=await state(f)
   async def broken(*a,**k):raise RuntimeError('synthetic private database error')
   with monkeypatch.context() as patch:
    patch.setattr(life if failure=='history' else AsyncSession,'record_history' if failure=='history' else failure,broken)
    r=await c.delete('/api/v1/suppliers/20',headers=auth(1)) if action=='delete' else await c.put('/api/v1/suppliers/20',headers=auth(1),json={'is_active':'true' if action=='enable' else 'false'})
   assert r.status_code==400 and '失败' in r.text and 'synthetic' not in r.text,r.text
   assert await state(f)==before
 asyncio.run(run())

@pytest.mark.parametrize('kind',['product','logistics','cross_border','purchase','payable','risk'])
def test_each_reference_alone_blocks_deletion(tmp_path,monkeypatch,kind):
 async def run():
  async with setup(tmp_path,monkeypatch) as (_,f,c):
   await seed(f,False)
   async with f() as db:
    if kind=='product':db.add(SupplierProduct(id=20,supplier_id=20,product_name='合成产品',unit_price=1))
    if kind=='logistics':db.add(SupplierLogisticsPrice(supplier_id=20,route_name='合成',cargo_type='普货',price_per_kg=1))
    if kind=='cross_border':db.add(SupplierCrossBorderPrice(supplier_id=20,transport_method='海运',cargo_type='普货',origin_warehouse='深圳',price_per_cbm=1))
    if kind=='purchase':db.add(PurchaseOrder(warehouse_id=1,supplier_id=20,order_number='SYN-ONLY',total_amount=1,items=[]))
    if kind=='payable':db.add(PayableBill(warehouse_id=1,supplier_id=20,bill_number='SYN-ONLY',bill_date=datetime(2026,10,20),due_date=datetime(2026,10,30),amount=1))
    if kind=='risk':db.add(ProcurementRiskReview(warehouse_id=1,month='2026-10',rule='new_supplier',subject_key='x',signal_id='x',rule_version='x',scope={},evidence_version='x',snapshot={'evidence':[{'supplier_id':20}]},conclusion='reviewed',reason='合成',reviewer_id=1,request_key='only',request_fingerprint='x'))
    await db.commit()
   before=await state(f);r=await c.delete('/api/v1/suppliers/20',headers=auth(1));assert r.status_code==400 and '已有业务记录' in r.text,r.text;assert await state(f)==before
 asyncio.run(run())

def test_scope_invalid_status_missing_and_double_delete(tmp_path,monkeypatch):
 async def run():
  async with setup(tmp_path,monkeypatch) as (_,f,c):
   await seed(f,False);before=await state(f)
   for method,path,body,code in [('DELETE','/suppliers/2',None,403),('PUT','/suppliers/2',{'is_active':'false'},403),('PUT','/suppliers/20',{'is_active':'invalid','name':'不能保存'},400),('DELETE','/suppliers/99999',None,400),('PUT','/suppliers/99999',{'is_active':'false'},400)]:
    r=await c.request(method,'/api/v1'+path,headers=auth(1),json=body);assert r.status_code==code,r.text;assert await state(f)==before
   rs=await asyncio.gather(*(c.delete('/api/v1/suppliers/20',headers=auth(1)) for _ in range(2)))
   assert sorted(r.status_code for r in rs)==[200,400]
   async with f() as db:
    assert await db.get(Supplier,20) is None
    assert len((await db.execute(select(DataChangeHistory).where(DataChangeHistory.module=='suppliers',DataChangeHistory.record_id==20))).scalars().all())==1
 asyncio.run(run())

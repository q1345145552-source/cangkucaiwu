"""Constructible uncovered actions: actual routes and complete denial snapshots."""
from harness import *
from app.models.supplier import PurchaseOrder,SupplierProduct
from app.models.income_expense import ExpenseRecord
async def main():
 engine,factory=await environment()
 async with factory() as db:
  db.add(PurchaseOrder(id=21,warehouse_id=1,supplier_id=1,created_by=2,order_number='SYNTHETIC-GAP-21',total_amount=100,currency='THB',status='confirmed',items=[]))
  db.add(SupplierProduct(id=21,supplier_id=1,product_name='SYNTHETIC PRODUCT',unit='件',unit_price=10,currency='THB'))
  category=(await db.execute(select(IncomeExpenseCategory).where(IncomeExpenseCategory.warehouse_id==1))).scalars().first()
  cid=category.id
  db.add(ExpenseRecord(id=21,warehouse_id=1,account_id=1,category_id=cid,amount=10,currency='THB',expense_date=datetime(2026,10,20),remark='SYNTHETIC manual'))
  db.add(PayrollRecord(id=21,warehouse_id=1,employee_id=1,period='2025-01',status='pending',disbursed=False,net_pay=10,detail='{}'))
  await db.commit()
 async with AsyncClient(transport=ASGITransport(app=app),base_url='http://local') as client:
  ev=Evidence(factory,client)
  calls=[('supplier-create',1,'POST','/suppliers',{'name':'SYNTHETIC NEW'}),
   ('category-create',1,'POST','/income-expense/categories',{'type':'expense','name':'SYNTHETIC NEW CATEGORY'}),
   ('reimb-category',1,'POST','/reimbursement/categories',{'name':'SYNTHETIC REIMB CATEGORY'}),
   ('reimb-delete',3,'DELETE','/reimbursement/1',None),
   ('purchase-shipped',2,'POST','/suppliers/purchase-orders/21/mark-shipped',None),
   ('expense-update',3,'PUT','/expense-approvals/1',{'purpose':'SYNTHETIC UPDATED'}),
   ('payroll-delete-period',3,'DELETE','/payroll/period/2025-01',None),
   ('mapping-history',1,'GET','/sku-catalog/products/21/mapping-history',None),
   ('report-advances',1,'GET','/reports/cost-funds-debt/advances',None)]
  for ident,uid,method,path,body in calls:
   await ev.call(ident+'-labor',5,method,path,body,expected=403)
   await ev.call(ident+'-cross-header',uid,method,path,body,warehouse='2',expected=403)
   await ev.call(ident,uid,method,path,body)
  form={'category_id':str(cid),'account_id':'1','amount':'11','currency':'THB','expense_date':'2026-10-20','remark':'SYNTHETIC updated'}
  await ev.call('manual-expense-supervisor',2,'PUT','/income-expense/expense/21',data=form,expected=403)
  await ev.call('manual-expense-foreign',3,'PUT','/income-expense/expense/21',data=form,warehouse='2',expected=403)
  await ev.call('manual-expense-finance',3,'PUT','/income-expense/expense/21',data=form)
  ev.finish()
 await engine.dispose()
if __name__=='__main__':asyncio.run(main())

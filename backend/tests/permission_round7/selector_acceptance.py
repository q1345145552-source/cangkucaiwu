from harness import *
from decimal import Decimal
from app.core.action_access import VERSION, CATALOG
from app.core.action_forms import contract

def equal(value,expected):assert value==expected,(value,expected)
def ids(result):return [r['id'] for r in result['data']]
async def main():
 engine,factory=await environment()
 async with factory() as db:
  u=await db.get(User,3);u.extra_permissions=[VERSION,'payroll:operate','expense_fund:operate','reimbursement:operate','suppliers:operate']
  u=await db.get(User,2);u.extra_permissions=[VERSION,'leave:approve','expense_fund:operate','inventory:operate']
  for i in range(20,131):db.add(Employee(id=i,warehouse_id=1,name=f'候选员工{i}',hire_date=datetime(2026,10,1)))
  db.add(ExpenseFund(id=2,warehouse_id=1,employee_id=2,receive_date=datetime(2026,10,1),amount=500,purpose='SYNTHETIC',remaining_balance=500,currency='THB',status='active'))
  db.add(ExpenseFundItem(id=2,fund_id=1,expense_date=datetime(2026,10,20),category='其他',amount=20,currency='THB',description='SYNTHETIC',review_status='pending'))
  db.add(StandardSKU(id=1,warehouse_id=1,code='SYN-CARTON',name='合成纸箱',attributes={},base_unit='个',created_by=1));await db.flush()
  db.add(InventoryAccount(id=7,warehouse_id=1,sku_id=1,base_unit='个',sku_snapshot={'name':'合成纸箱'},recorded_quantity=10,opening_confirmed=True))
  db.add_all([SupplierProduct(id=1,supplier_id=1,product_name='本仓纸箱',unit_price=12),SupplierProduct(id=2,supplier_id=2,product_name='外仓禁止哨兵',unit_price=999)])
  db.add(Customer(id=1,warehouse_id=1,customer_code='SYNTHETIC-SELECT',company_name='合成对账客户'));await db.flush()
  db.add(RechargeDeclaration(id=17,warehouse_id=1,customer_id=1,declare_date=datetime(2026,10,20),amount=100,declarer_id=1,match_status='matched'))
  db.add(IncomingFlow(id=19,warehouse_id=1,received_date=datetime(2026,10,20),amount=100,entrant_id=1,match_status='matched'));await db.flush()
  db.add(ReconciliationResult(id=23,warehouse_id=1,reconciliation_month='2026-10',declaration_id=17,flow_id=19,match_status='manual_matched'))
  await db.commit()
 async with AsyncClient(transport=ASGITransport(app=app),base_url='http://local') as client:
  ev=Evidence(factory,client)
  def url(module,action,field,extra=''):return f'/access/choices/{module}?action={action}&field={field}'+extra
  await ev.call('catalog-contracts',3,'GET','/access/catalog?role=staff',check=lambda b,a,r,res:equal(next(x for x in r['routes'] if x['id']=='payroll.calculate_payroll')['form']['body']['properties']['employee_ids']['anyOf'][0]['items']['selector']['entity'],'Employee'))
  await ev.call('payroll-employee-page1',3,'GET',url('payroll','payroll.calculate_payroll','body:employee_ids.[]'),check=lambda b,a,r,res:equal((len(r['data']),r['has_more']),(30,True)))
  await ev.call('payroll-employee-page5',3,'GET',url('payroll','payroll.calculate_payroll','body:employee_ids.[]','&page=4'),check=lambda b,a,r,res:equal(130 in ids(r),True))
  await ev.call('payroll-employee-search',3,'GET',url('payroll','payroll.calculate_payroll','body:employee_ids.[]','&search=候选员工130'),check=lambda b,a,r,res:equal(ids(r),[130]))
  await ev.call('payroll-employee-foreign-search',3,'GET',url('payroll','payroll.calculate_payroll','body:employee_ids.[]','&search=8'),check=lambda b,a,r,res:equal(8 in ids(r),False))
  await ev.call('payroll-no-grants',6,'GET',url('payroll','payroll.calculate_payroll','body:employee_ids.[]'),expected=403)
  await ev.call('payroll-role-ceiling',2,'GET',url('payroll','payroll.calculate_payroll','body:employee_ids.[]'),expected=403)
  await ev.call('payroll-wrong-field',3,'GET',url('payroll','payroll.calculate_payroll','body:user_id'),expected=400)
  await ev.call('payroll-wrong-module',3,'GET',url('accounts','payroll.calculate_payroll','body:employee_ids.[]'),expected=403)
  await ev.call('payroll-foreign-header',3,'GET',url('payroll','payroll.calculate_payroll','body:employee_ids.[]'),warehouse='2',expected=403)
  await ev.call('payroll-invalid-header',3,'GET',url('payroll','payroll.calculate_payroll','body:employee_ids.[]'),warehouse='abc',expected=403)
  await ev.call('fund-not-payment-account',2,'GET',url('expense_fund','expense_fund.add_item','path:account_id'),check=lambda b,a,r,res:equal([(x['id'],x['entity']) for x in r['data']],[(2,'ExpenseFund')]))
  await ev.call('fund-child-parent',1,'GET',url('expense_fund','expense_fund.edit_item','path:item_id','&parent_id=1'),check=lambda b,a,r,res:equal(ids(r),[1,2]))
  await ev.call('fund-child-no-parent',1,'GET',url('expense_fund','expense_fund.edit_item','path:item_id'),check=lambda b,a,r,res:equal(ids(r),[]))
  await ev.call('fund-child-other-owner',2,'GET',url('expense_fund','expense_fund.edit_item','path:item_id','&parent_id=1'),expected=403)
  await ev.call('reimb-child-parent',1,'GET',url('reimbursement','reimbursement.review_reimb','body:items.[].item_id','&parent_id=1'),check=lambda b,a,r,res:equal(ids(r),[1]))
  await ev.call('reimb-child-foreign-parent',1,'GET',url('reimbursement','reimbursement.review_reimb','body:items.[].item_id','&parent_id=8'),expected=403)
  await ev.call('disabled-user',7,'GET',url('payroll','payroll.calculate_payroll','body:employee_ids.[]'),expected=401)
  await ev.call('selected-payroll-context',3,'GET',url('payroll','payroll.disburse_payroll','path:record_id','&selected_id=2'),check=lambda b,a,r,res:equal(r['context']['net_pay'],100))
  await ev.call('selected-payroll-foreign',3,'GET',url('payroll','payroll.disburse_payroll','path:record_id','&selected_id=8'),expected=403)
  await ev.call('selected-context-no-bank',3,'GET',url('payroll','payroll.disburse_payroll','path:record_id','&selected_id=2'),check=lambda b,a,r,res:equal(any(k in json.dumps(r) for k in ('account_number','passport','base_pay','gross_pay')),False))
  await ev.call('supplier-nested-product',3,'GET',url('suppliers','suppliers.create_purchase_order','body:items.[].product_id','&parent_id=1'),check=lambda b,a,r,res:equal(ids(r),[1]))
  await ev.call('supplier-nested-foreign',3,'GET',url('suppliers','suppliers.create_purchase_order','body:items.[].product_id','&parent_id=2'),expected=403)
  stock=await ev.call('inventory-real-entity-and-version',2,'GET',url('inventory','inventory.issue','path:account_id','&selected_id=7'),check=lambda b,a,r,res:equal((r['data'][0]['entity'],r['context']['recorded_quantity']),('InventoryAccount',10)))
  def inventory_effect(before,after,result,response):
   equal(Decimal(next(r['recorded_quantity'] for r in after['inventory_accounts'] if r['id']==7)),Decimal('8'))
   equal(len(after['inventory_movements']),len(before['inventory_movements'])+1)
   for table in ('payment_accounts','expense_records','payable_payments','income_records'):equal(before[table],after[table])
  payload={'issued_quantity':'2','expected_version':stock['versions']['expected_version'],'purpose':'SYNTHETIC onsite consumption','request_key':'SYNTHETIC-round7-selector-issue'}
  await ev.call('inventory-operation-only-real-issue',2,'POST','/inventory/accounts/7/issues',payload,check=inventory_effect)
  await ev.call('inventory-operation-no-list',2,'GET','/inventory',expected=403)
  await ev.call('inventory-stale-version-no-mutation',2,'POST','/inventory/accounts/7/issues',{**payload,'request_key':'SYNTHETIC-stale-version'},expected=409)
  await ev.call('fund-employee-is-login-user',1,'GET',url('expense_fund','expense_fund.create_account','body:employee_id'),check=lambda b,a,r,res:equal((6 in ids(r),r['data'][0]['entity']),(True,'User')))
  async with factory() as db:
   u=await db.get(User,3);u.extra_permissions=[VERSION,'reconciliation:operate'];await db.commit()
  await ev.call('reconciliation-record-not-payroll',3,'GET',url('reconciliation','reconciliation.unmatch_record','query:record_id','&selected_id=23&page=4'),check=lambda b,a,r,res:equal((r['data'][0]['entity'],r['context']['declaration_id'],r['context']['flow_id']),('ReconciliationResult',17,19)))
  await ev.call('reconciliation-declaration-not-incoming',3,'GET',url('reconciliation','reconciliation.manual_match','query:declaration_id'),check=lambda b,a,r,res:equal(ids(r),[17]))
  await ev.call('reconciliation-incoming-not-declaration',3,'GET',url('reconciliation','reconciliation.manual_match','query:flow_id'),check=lambda b,a,r,res:equal(ids(r),[19]))
  def unmatched(before,after,result,response):
   equal(next(r['match_status'] for r in after['recharge_declarations'] if r['id']==17),'unmatched')
   equal(next(r['match_status'] for r in after['incoming_flows'] if r['id']==19),'unmatched')
   for table in ('payment_accounts','income_records','expense_records','payroll_records'):equal(before[table],after[table])
  await ev.call('reconciliation-operation-real-unmatch',3,'POST','/reconciliation/unmatch?record_id=23',check=unmatched)
  async with factory() as db:
   u=await db.get(User,2);u.extra_permissions=ALL;await db.commit()
  await ev.call('legacy-all-supervisor-payroll-selector-denied',2,'GET','/access/choices/payroll',expected=403)
  await ev.call('legacy-all-supervisor-payroll-field-denied',2,'GET',url('payroll','payroll.disburse_payroll','path:record_id'),expected=403)
  async with factory() as db:
   u=await db.get(User,3);u.extra_permissions=[VERSION,'cash_advances:operate'];await db.commit()
  for kind,entity,selected in [('payroll','PayrollRecord',2),('payable','PayableBill',1),('reimbursement','Reimbursement',1),('employee_advance','EmployeeAdvance',1)]:
   await ev.call('linked-document-'+kind,3,'GET',url('cash_advances','cash_advance.create_advance','body:linked_documents.[].document_id',f'&document_type={kind}&selected_id={selected}'),check=lambda b,a,r,res,entity=entity:equal(r['data'][0]['entity'],entity))
   await ev.call('linked-document-foreign-'+kind,3,'GET',url('cash_advances','cash_advance.create_advance','body:linked_documents.[].document_id',f'&document_type={kind}&selected_id=8'),expected=403)
  await ev.call('linked-document-missing-type',3,'GET',url('cash_advances','cash_advance.create_advance','body:linked_documents.[].document_id'),expected=400)
  await ev.call('linked-document-invalid-type',3,'GET',url('cash_advances','cash_advance.create_advance','body:linked_documents.[].document_id','&document_type=users'),expected=400)
  for mask in range(8):
   async with factory() as db:
    u=await db.get(User,3);u.extra_permissions=[VERSION]+['expense_fund:'+tier for i,tier in enumerate(('view','operate','approve')) if mask & (1<<i)];await db.commit()
   # Finance approval bits exceed the role ceiling: a stale/forged stored config is invalid.
   expected=200 if mask in (2,3) else 403
   await ev.call('finance-tier-combination-'+str(mask),3,'GET',url('expense_fund','expense_fund.add_item','path:account_id'),expected=expected)
  ev.finish()
 await engine.dispose()
if __name__=='__main__':asyncio.run(main())

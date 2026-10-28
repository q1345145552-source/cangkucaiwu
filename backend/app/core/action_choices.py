"""Server-owned action/field bindings. A caller cannot select an arbitrary table."""
from dataclasses import dataclass
from fastapi import HTTPException
from sqlalchemy import select, or_, cast, String
from app import models as m
from app.models.overtime import OvertimeTask, OvertimeAssignment
from app.models.payroll import PayrollRecord
from app.models.payable import PlanTemplate
from app.models.credit import CreditShipment
from app.models.supplier import SupplierCrossBorderPrice
from app.core.action_access import CATALOG, variants, has_module, permission_state

@dataclass(frozen=True)
class Binding:
    entity: str
    parent: str | None = None
    parent_column: str | None = None
    discriminator: str | None = None

# This map is keyed by the actual route namespace, not the navigation module.
PRIMARY = {
 'employees': 'Employee', 'attendance':'LeaveRequest', 'clock_in':'DataChangeHistory',
 'payroll':'PayrollRecord', 'overtime':'OvertimeTask', 'expense_fund':'ExpenseFund',
 'reimbursement':'Reimbursement', 'payable':'PayableBill', 'payment_accounts':'PaymentAccount',
 'suppliers':'Supplier', 'supplier_quotes':'SupplierQuote', 'sku_catalog':'StandardSKU',
 'inventory':'InventoryAccount', 'employee_advance':'EmployeeAdvance', 'cash_advance':'CashAdvance',
 'expense_approval':'ExpenseApproval','salary_template':'SalaryTemplate','deduction_template':'DeductionTemplate',
 'employee_deduction':'EmployeeDeduction','customers':'Customer','credit':'CreditCustomer',
 'recharge':'RechargeDeclaration','incoming':'IncomingFlow','users':'User','warehouses':'Warehouse',
 'market':'MarketItem','group_order':'GroupOrder',
}
ENTITIES = {name:getattr(m,name) for name in set(PRIMARY.values()) | {
 'ExpenseFundItem','FundRechargeRequest','ReimbursementItem','PayablePlan','SupplierProduct',
 'PurchaseOrder','SupplierCategory','SupplierWarehouseTag','InventoryMovement','InventoryStocktake',
 'InventoryReceiptLink','ProcurementActionException','EmployeeFixedDeduction','RestDay','Absence',
 'ClockInMakeupBatch','IncomeRecord','ExpenseRecord','IncomeExpenseCategory','GroupOrderParticipant',
 'SalaryTemplate','DeductionTemplate','ReconciliationResult'} if hasattr(m,name)}
ENTITIES.update(OvertimeTask=OvertimeTask,OvertimeAssignment=OvertimeAssignment,PayrollRecord=PayrollRecord,
                PlanTemplate=PlanTemplate,CreditShipment=CreditShipment,SupplierCrossBorderPrice=SupplierCrossBorderPrice)
# Children always inherit warehouse and any personal scope through this parent, even when
# the client did not supply a parent filter (e.g. approved batch fund items).
PARENTS = {
 'ExpenseFundItem':('ExpenseFund','fund_id'), 'ReimbursementItem':('Reimbursement','reimbursement_id'),
 'SupplierProduct':('Supplier','supplier_id'), 'SupplierCrossBorderPrice':('Supplier','supplier_id'),
 'GroupOrderParticipant':('GroupOrder','group_order_id'),
 'OvertimeAssignment':('OvertimeTask','overtime_id'), 'CreditShipment':('CreditCustomer','credit_customer_id'),
}
COMMON = {'employee_id':'Employee','employee_ids':'Employee','recalc_employee_id':'Employee',
 'supplier_id':'Supplier','customer_id':'Customer','payment_account_id':'PaymentAccount',
 'from_account_id':'PaymentAccount','to_account_id':'PaymentAccount','cash_advance_id':'CashAdvance',
 'fund_account_id':'ExpenseFund','salary_template_id':'SalaryTemplate','deduction_template_id':'DeductionTemplate',
 'warehouse_id':'Warehouse','warehouse_ids':'Warehouse','user_id':'User','user_ids':'User','payer_id':'User',
 'operator_id':'User','declaration_id':'RechargeDeclaration','flow_id':'IncomingFlow','incoming_flow_id':'IncomingFlow','sku_id':'StandardSKU','tag_ids':'SupplierWarehouseTag'}

def binding(action, field):
    """Exact structured field path; [] denotes one array element, never plural guessing."""
    if action['id']=='suppliers.receive_purchase' and field=='body:items.[].line_id':return Binding('PurchaseOrderLine','path:po_id')
    namespace,handler=action['id'].split('.',1)
    field=field.removesuffix('.[]')
    name=field.rsplit('.',1)[-1].removeprefix('path:').removeprefix('query:').removeprefix('body:')
    parent=None; column=None
    entity=COMMON.get(name)
    if name in ('account_id','fund_id'):
        entity='ExpenseFund' if namespace=='expense_fund' else 'InventoryAccount' if namespace=='inventory' else 'PaymentAccount'
    if name in ('record_id','record_ids','payroll_id'): entity='ReconciliationResult' if namespace=='reconciliation' else 'PayrollRecord'
    if namespace=='expense_fund' and name=='employee_id':entity='User'
    if name in ('reimb_id','reimbursement_id'):entity='Reimbursement'
    if name in ('bill_id','bill_ids'):entity='PayableBill'
    if name=='plan_id':entity='PayablePlan'
    if name=='template_id':entity={'salary_template':'SalaryTemplate','deduction_template':'DeductionTemplate','payable':'PlanTemplate'}.get(namespace)
    if name=='advance_id':entity='EmployeeAdvance' if namespace=='employee_advance' else 'CashAdvance'
    if name=='approval_id':entity='ExpenseApproval'
    if name=='leave_id':entity='LeaveRequest'
    if name in ('task_id','overtime_id'):entity='OvertimeTask'
    if name=='assignment_id':entity='OvertimeAssignment';parent='path:task_id';column='overtime_id'
    if name=='request_id':
        entity='FundRechargeRequest' if namespace=='expense_fund' else 'DataChangeHistory' if namespace=='clock_in' else None
    if name in ('item_id','item_ids'):
        if namespace=='expense_fund':entity='ExpenseFundItem';parent='path:account_id' if name=='item_id' else None;column='fund_id'
        elif namespace=='reimbursement':entity='ReimbursementItem';parent='path:reimb_id';column='reimbursement_id'
        elif namespace=='market':entity='MarketItem'
    if name=='product_id':
        entity='SupplierProduct';parent='path:supplier_id' if namespace=='suppliers' else None;column='supplier_id'
    if name=='quote_id':
        entity='SupplierQuote';parent='body:items.[].product_id' if namespace=='suppliers' else None;column='product_id'
    if name=='po_id':entity='PurchaseOrder'
    if name=='price_id':entity='SupplierCrossBorderPrice';parent='path:supplier_id';column='supplier_id'
    if name=='exception_id':entity='ProcurementActionException';parent='path:po_id';column='purchase_order_id'
    if name=='ident':entity={'inventory':'InventoryReceiptLink','procurement_controls':'ProcurementActionException'}.get(namespace)
    if name=='movement_id':entity='InventoryMovement'
    if name=='count_id':entity='InventoryStocktake'
    if name=='tag_id':entity='SupplierWarehouseTag'
    if name=='rest_day_id':entity='RestDay'
    if name=='absence_id':entity='Absence'
    if name=='batch_id':entity='ClockInMakeupBatch'
    if name=='deduction_id':entity='EmployeeFixedDeduction' if 'fixed' in handler else 'EmployeeDeduction'
    if name=='credit_id':entity='CreditCustomer'
    if name=='shipment_id':entity='CreditShipment';parent='path:credit_id';column='credit_customer_id'
    if name=='recharge_id':entity='RechargeDeclaration'
    if name=='incoming_id':entity='IncomingFlow'
    if name=='income_id':entity='IncomeRecord'
    if name=='expense_id':entity='ExpenseRecord'
    if name=='go_id':entity='GroupOrder'
    if name=='participant_id':entity='GroupOrderParticipant'
    if name=='category_id':entity='SupplierCategory' if namespace in ('suppliers','sku_catalog') else 'IncomeExpenseCategory' if namespace=='income_expense' else None
    if namespace=='cash_advance' and field=='body:linked_documents.[].document_id':return Binding('LinkedDocument',discriminator='document_type')
    return Binding(entity,parent,column) if entity in ENTITIES else None


def authorize(user,row):
    if row is None or row['mode']!='business' or permission_state(user)['version']=='invalid':
        raise HTTPException(403,'该动作不提供对象选择')
    if not any(user.role in v['roles'] and v['tier']!='view' and any(has_module(user,module,v['tier']) for module in row.get('grant_modules',[row['module_key']])) for v in variants(row)):
        raise HTTPException(403,'缺少该动作授权或超出角色职责')

async def scoped(db,user,wh_ids,entity):
    model=ENTITIES[entity];q=select(model)
    scope_model=model
    if entity in PARENTS:
        parent,fk=PARENTS[entity];scope_model=ENTITIES[parent]
        q=q.join(scope_model,getattr(model,fk)==scope_model.id)
    if entity=='Warehouse':q=q.where(model.id.in_(wh_ids))
    elif entity=='SupplierCategory':pass  # Existing shared reference taxonomy, no financial fields.
    elif hasattr(scope_model,'warehouse_id'):q=q.where(scope_model.warehouse_id.in_(wh_ids))
    else:raise HTTPException(403,'该对象尚未配置安全的仓库范围')
    if entity=='Employee':q=q.where(model.is_deleted==False)
    if entity=='User':
        # A multi-warehouse identity is manageable only if *all* memberships are authorized.
        q=q.where(~select(m.UserWarehouse.user_id).where(m.UserWarehouse.user_id==model.id,m.UserWarehouse.warehouse_id.not_in(wh_ids)).exists())
        if user.role!='warehouse_admin':q=q.where(model.is_active==True)
    if user.role=='supervisor' and scope_model in (m.ExpenseFund,m.Reimbursement):
        from app.core.round5_access import own_read_ids
        q=q.where(scope_model.employee_id.in_(await own_read_ids(db,user)))
    if entity=='DataChangeHistory':q=q.where(model.module=='makeup_request')
    return q

LABEL_FIELDS=('name','account_name','bill_number','order_no','order_number','code','plan_name','display_name','product_name','transport_method','cargo_type','item_name','period','leave_date','date','expense_date','advance_date','title','customer_code','received_date','declare_date','reconciliation_month')
LABELS={'ExpenseFund':'备用金','ExpenseFundItem':'开销','FundRechargeRequest':'补充申请','PayrollRecord':'工资','Reimbursement':'报销','ReimbursementItem':'报销明细','InventoryAccount':'库存','InventoryMovement':'库存流水','InventoryStocktake':'盘点','InventoryReceiptLink':'待入库收货','PayableBill':'应付单','PayablePlan':'付款计划','SupplierQuote':'报价','OvertimeTask':'加班','OvertimeAssignment':'加班人员','LeaveRequest':'请假','DataChangeHistory':'补卡申请'}

LABELS.update(ReconciliationResult='对账记录',Employee='员工',User='账号',Warehouse='仓库',Supplier='供应商',SupplierProduct='商品',SupplierCategory='供应商分类',SupplierCrossBorderPrice='物流报价',PaymentAccount='付款账户',StandardSKU='SKU',SupplierWarehouseTag='供应商标签',Customer='客户',EmployeeAdvance='预支',CashAdvance='垫款',ExpenseApproval='费用申请',SalaryTemplate='薪资模板',DeductionTemplate='扣款模板',EmployeeDeduction='员工扣款',EmployeeFixedDeduction='固定扣款',RestDay='休息日',Absence='缺勤',ClockInMakeupBatch='补卡批次',IncomeRecord='收入',ExpenseRecord='支出',IncomeExpenseCategory='收支分类',GroupOrder='团购',GroupOrderParticipant='参与人',CreditCustomer='账期客户',CreditShipment='发货',PlanTemplate='付款计划模板',RechargeDeclaration='充值申报',IncomingFlow='到账',ProcurementActionException='采购例外授权',PurchaseOrder='采购单',MarketItem='商品')

async def select_choices(db,user,wh_ids,row,field,parent_id=None,search='',page=1,page_size=30,selected_id=None,document_type=None):
    authorize(user,row)
    b=binding(row,field)
    if b is None:raise HTTPException(400,'该字段没有已登记的对象选择器')
    if b.entity=='LinkedDocument':
        entity={'payroll':'PayrollRecord','payable':'PayableBill','reimbursement':'Reimbursement','employee_advance':'EmployeeAdvance'}.get(document_type)
        if not entity:raise HTTPException(400,'请先选择合法的关联单据类型')
        b=Binding(entity)
    if b.entity=='PurchaseOrderLine':
        if parent_id is None:return {'data':[],'page':page,'has_more':False,'requires_parent':b.parent}
        pq=await scoped(db,user,wh_ids,'PurchaseOrder')
        parent=(await db.execute(pq.where(m.PurchaseOrder.id==parent_id))).scalar_one_or_none()
        if parent is None:raise HTTPException(403,'父对象不存在或无权使用')
        from app.services.purchase_matching import receipt_state
        state=await receipt_state(db,parent)
        if state['issues']:raise HTTPException(409,'历史收货依据异常，请从采购单核对')
        records=[]
        for item in state['items']:
            label=' · '.join(str(item.get(k) or '') for k in ('product_name','spec','unit'))
            if search and search.casefold() not in (label+' '+item['line_id']).casefold():continue
            if selected_id is not None and item['line_id']!=selected_id:continue
            records.append({'id':item['line_id'],'label':label,'entity':'PurchaseOrderLine','facts':{k:item.get(k) for k in ('product_name','spec','unit','quantity','received_quantity')}})
        if selected_id is not None and not records:raise HTTPException(403,'明细不存在或不属于当前采购单')
        offset=0 if selected_id is not None else (page-1)*page_size
        result={'data':[{k:v for k,v in item.items() if k!='facts'} for item in records[offset:offset+page_size]],'page':page,'has_more':len(records)>offset+page_size,'scope':'minimal-action-dependency'}
        if selected_id is not None:result.update(context=records[0]['facts'],versions={})
        return result
    if selected_id is not None:
        try:
            selected_id=int(selected_id)
            if selected_id<=0:raise ValueError
        except (TypeError,ValueError):raise HTTPException(400,'对象编号格式不正确')
    model=ENTITIES[b.entity]
    q=await scoped(db,user,wh_ids,b.entity)
    if b.entity == "Supplier" and row["id"] == "suppliers.create_purchase_order":
        q=q.where(model.is_active == "true")
    if b.parent:
        if parent_id is None:return {'data':[],'page':page,'has_more':False,'requires_parent':b.parent}
        parent_binding=binding(row,b.parent)
        if parent_binding is None:raise HTTPException(400,'父对象选择尚未登记')
        pq=await scoped(db,user,wh_ids,parent_binding.entity)
        if not (await db.execute(pq.where(ENTITIES[parent_binding.entity].id==parent_id))).scalars().first():
            raise HTTPException(403,'父对象不存在或无权使用')
        q=q.where(getattr(model,b.parent_column)==parent_id)
    fields=[getattr(model,key) for key in LABEL_FIELDS if hasattr(model,key)]
    if search:
        term='%'+search.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%'
        q=q.where(or_(cast(model.id,String)==search,*[cast(c,String).ilike(term,escape='\\') for c in fields]))
    if selected_id is not None:q=q.where(model.id==selected_id)
    rows=(await db.execute(q.order_by(model.id).offset(0 if selected_id is not None else (page-1)*page_size).limit(page_size+1))).scalars().all()
    employee_ids={getattr(r,'employee_id',None) for r in rows}-{None}
    if b.entity=='DataChangeHistory':employee_ids.update(r.record_id for r in rows)
    employee_names=dict((await db.execute(select(m.Employee.id,m.Employee.name).where(m.Employee.id.in_(employee_ids),m.Employee.warehouse_id.in_(wh_ids)))).all()) if employee_ids else {}
    owner_names=dict((await db.execute(select(m.User.id,m.User.display_name).where(m.User.id.in_(employee_ids),m.User.warehouse_id.in_(wh_ids)))).all()) if employee_ids and b.entity in ('ExpenseFund','Reimbursement') else employee_names
    data=[]
    for r in rows[:page_size]:
        parts=[str(getattr(r,k)) for k in LABEL_FIELDS if getattr(r,k,None) is not None]
        employee=owner_names.get(getattr(r,'employee_id',None))
        if employee:parts.insert(0,employee)
        if b.entity=='DataChangeHistory':
            details=r.after_data or {};parts=[employee_names.get(r.record_id,'员工'),str(details.get('date','')),str(details.get('sessions',[]))]
        if b.entity=='InventoryAccount':
            snapshot=r.sku_snapshot or {};parts.insert(0,str(snapshot.get('name') or snapshot.get('sku_name') or 'SKU'))
        data.append({'id':r.id,'label':' · '.join([LABELS.get(b.entity,b.entity),*parts,f'#{r.id}']),
                     'status':(r.after_data or {}).get('status') if b.entity=='DataChangeHistory' else getattr(r,'status',None),'entity':b.entity})
    result={'data':data,'page':page,'page_size':page_size,'has_more':len(rows)>page_size,'scope':'minimal-action-dependency'}
    if selected_id is not None:
        if not rows:raise HTTPException(403,'对象不存在或不在允许范围')
        # A selected action needs its own transaction facts, not a warehouse-wide ledger.
        # Never serialize whole models, bank details, identity documents or salary templates.
        context_fields={
            'PayrollRecord':('period','status','net_pay','disbursed','settle_start_date','settle_end_date'),
            'Reimbursement':('submit_date','status','total_amount','currency'),
            'ReimbursementItem':('category','amount','description','review_status'),
            'ExpenseFund':('purpose','currency','status'),
            'ExpenseFundItem':('expense_date','category','amount','currency','description','review_status'),
            'FundRechargeRequest':('amount','reason','status'),
            'PayableBill':('bill_number','amount','paid_amount','currency','status','due_date'),
            'PayablePlan':('plan_name','planned_date','total_amount','status'),
            'LeaveRequest':('leave_date','leave_type','hours','reason','status'),
            'OvertimeTask':('date','start_time','end_time','hours','status'),
            'OvertimeAssignment':('actual_hours','confirmed'),
            'PurchaseOrder':('order_number','status','currency','total_amount'),
            'InventoryStocktake':('book_quantity','counted_quantity','counted_at','status','reason'),
            'InventoryAccount':('base_unit','recorded_quantity','revision'),
            'ReconciliationResult':('reconciliation_month','declaration_id','flow_id','match_status','amount_diff','handling_note'),
        }
        result['context']={key:getattr(rows[0],key) for key in context_fields.get(b.entity,()) if hasattr(rows[0],key)}
        r=rows[0]; versions={}
        if b.entity=='PurchaseOrder' and row['id'] in ('suppliers.receive_purchase','suppliers.approve_purchase','suppliers.reject_purchase'):
            from app.services.procurement_controls import context
            action='receive' if row['id']=='suppliers.receive_purchase' else 'approve' if row['id']=='suppliers.approve_purchase' else 'reject'
            state=await context(db,r.warehouse_id,user,r.id,action)
            versions.update(expected_policy_version=state['policy_version'],expected_business_version=state['business_version'])
        if b.entity=='DataChangeHistory':result['context']={k:(r.after_data or {}).get(k) for k in ('date','sessions','reason','status')}
        if b.entity in ('InventoryAccount','InventoryMovement'):
            from app.services.inventory import account_version
            account=r if b.entity=='InventoryAccount' else await db.get(m.InventoryAccount,r.account_id)
            if account is None or account.warehouse_id not in wh_ids:raise HTTPException(403,'库存关联账户不在允许范围')
            versions['expected_version']=account_version(account.warehouse_id,account.sku_id,account.base_unit,account)
            if row['id']=='inventory.set_controls':
                from app.services.inventory_controls import controls
                versions['expected_version']=(await controls(db,account.warehouse_id,account.id))['version']
        elif b.entity=='InventoryStocktake':
            from app.services.inventory_controls import count_data
            versions['expected_count_version']=count_data(r)['version']
        elif b.entity=='InventoryReceiptLink':versions['expected_source_fingerprint']=r.source_fingerprint
        elif b.entity=='StandardSKU':
            from app.services.sku_catalog import sku_data
            versions['expected_sku_version']=sku_data(r)['version']
            result['context'].update(name=r.name,base_unit=r.base_unit)
            if row['id']=='sku_catalog.update':versions['expected_version']=sku_data(r)['version']
            if row['id']=='inventory.confirm_opening':
                from app.services.inventory import account_version
                account=(await db.execute(select(m.InventoryAccount).where(m.InventoryAccount.warehouse_id==r.warehouse_id,m.InventoryAccount.sku_id==r.id,m.InventoryAccount.base_unit==r.base_unit))).scalar_one_or_none()
                versions['expected_version']=account_version(r.warehouse_id,r.id,r.base_unit,account)
        elif b.entity=='SupplierWarehouseTag' and row['id']=='sku_catalog.update_tag':
            from app.services.payable_creation import fingerprint
            versions['expected_version']=fingerprint({k:getattr(r,k) for k in ('id','warehouse_id','name','active','revision')})
        elif b.entity=='Supplier' and row['id']=='sku_catalog.assign_tags':
            from app.services.payable_creation import fingerprint
            tag_ids=list((await db.execute(select(m.SupplierTagLink.tag_id).where(m.SupplierTagLink.supplier_id==r.id,m.SupplierTagLink.warehouse_id.in_(wh_ids)).order_by(m.SupplierTagLink.tag_id))).scalars())
            versions['expected_version']=fingerprint(tag_ids)
        elif b.entity=='SupplierProduct':
            from app.services import sku_catalog, supplier_quotes
            supplier,mapping,sku=await supplier_quotes.source_context(db,(await db.get(m.Supplier,r.supplier_id)).warehouse_id,r)
            versions['expected_product_version']=sku_catalog.product_version(r)
            if sku:versions['expected_sku_version']=sku['version']
            result['context'].update(product_name=r.product_name,spec=r.spec,unit=r.unit,currency=r.currency)
        elif b.entity=='SupplierQuote':
            from app.services.supplier_quotes import revision_data, source_context
            from app.services.sku_catalog import product_version
            quote=await revision_data(db,r)
            versions['expected_quote_version']=quote['version']
            product=await db.get(m.SupplierProduct,r.product_id)
            if product is None:raise HTTPException(409,'报价产品关系异常')
            supplier,mapping,sku=await source_context(db,r.warehouse_id,product)
            versions['expected_product_version']=product_version(product)
            if sku:versions['expected_sku_version']=sku['version']
            result['context'].update({k:quote['terms'].get(k) for k in ('currency','unit','valid_from','valid_to','tiers','fees')})
        result['versions']=versions

    return result


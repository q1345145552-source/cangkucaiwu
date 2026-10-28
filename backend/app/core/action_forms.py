"""Existing API contracts for the minimal action workspace, never a generic write endpoint."""
import inspect

VERBS={'create':'新建','add':'添加','update':'修改','edit':'修改','delete':'删除','remove':'移除','set':'设置','save':'保存','submit':'提交','approve':'批准','reject':'驳回','verify':'核验','confirm':'确认','execute':'执行','pay':'付款','disburse':'发放','recalc':'重算','calculate':'核算','void':'作废','reverse':'冲销','revoke':'撤回','upload':'上传','import':'导入','batch':'批量办理','receive':'收货','return':'退回','mark':'登记','toggle':'启停','bind':'绑定','grant':'授权','request':'申请','join':'参加','complete':'完成','cancel':'取消','send':'发送','repay':'还款','issue':'领用','single':'单人结算','admin':'代录'}
NOUNS={'account':'账户','transfer':'内部调拨','employee':'员工','leave':'请假','rest_days':'休息日','absence':'缺勤','payroll':'工资','reimb':'报销','reimbursement':'报销','advance':'预支','approval':'费用申请','bill':'应付单','plan':'付款计划','supplier':'供应商','category':'分类','purchase':'采购','product':'商品','item':'明细','recharge':'补充申请','overtime':'加班','makeup':'补卡','count':'盘点','policy':'规则','receipt':'凭证','expense':'支出','income':'收入','shipment':'发货','template':'模板','threshold':'门槛'}

def action_label(row, endpoint=None):
    doc=inspect.getdoc(endpoint) if endpoint else None
    if doc and any('\u4e00'<=c<='\u9fff' for c in doc.splitlines()[0]):
        return doc.splitlines()[0].strip().rstrip('。')[:90]
    name=row['handler'];parts=name.split('_')
    return VERBS.get(parts[0],'办理')+next((v for k,v in NOUNS.items() if k in name),'事项')


def contract(app, row, role):
    route=next((r for r in app.routes if getattr(r,'path',None)==row['path'] and set(row['methods']) & set(getattr(r,'methods',()))),None)
    if not route:return None
    operation=app.openapi()['paths'].get(row['path'],{}).get(row['methods'][0].lower(),{})
    definitions=app.openapi().get('components',{}).get('schemas',{})
    def resolve(value,depth=0):
        if depth>12:return {}
        if isinstance(value,dict):
            if '$ref' in value:return resolve(definitions.get(value['$ref'].rsplit('/',1)[-1],{}),depth+1)
            return {k:resolve(v,depth+1) for k,v in value.items()}
        if isinstance(value,list):return [resolve(v,depth+1) for v in value]
        return value
    content=operation.get('requestBody',{}).get('content',{})
    media='application/json' if 'application/json' in content else next(iter(content),'application/json')
    body = resolve(content.get(media,{}).get('schema',{}))
    if row['id'] == 'suppliers.add_logistics_price':
        # Existing dict endpoint: expose only its existing editable price fields,
        # never supplier_id/id/created_at owned by the route and database.
        body = {'type':'object','required':['transport_method','cargo_type','origin_warehouse','price_per_cbm'],
            'properties':{key:{'type':kind,'title':title} for key,kind,title in [
                ('transport_method','string','运输方式'),('cargo_type','string','货物类型'),
                ('origin_warehouse','string','发货仓库'),('price_per_cbm','number','每立方米价格'),
                ('estimated_days','string','预计时效'),('currency','string','币种'),('remark','string','备注')]}}
    if row['id']=='suppliers.receive_purchase':
        body['properties']['items']={'type':'array','title':'本次收货明细','encoding':'json-string','items':{'type':'object','required':['line_id','received_quantity'],'properties':{'line_id':{'type':'string','title':'采购明细'},'received_quantity':{'type':'integer','title':'本次收货数量','minimum':0}}}}
    if row['id']=='payable.confirm_bill':
        body={'type':'object','required':['reason'],'properties':{'reason':{'type':'string','title':'匹配复核原因','maxLength':1000}}}
    if row['id']=='suppliers.approve_purchase':
        body={'type':'object','properties':{'request_key':{'type':'string','title':'本次操作标识'},'exception_id':{'type':'integer','title':'例外授权'}}}
    if row['id']=='reimbursement.review_reimb':
        body['properties']['items']['items']={'type':'object','required':['item_id','status'],'properties':{'item_id':{'type':'integer','title':'报销明细'},'status':{'type':'string','enum':['approved','rejected'],'title':'审核结论'}}}
    if row['module'].rsplit('.',1)[-1] == 'employees' and role != 'warehouse_admin':
        from app.core.round5_access import PAY_FIELDS, DOCUMENT_FIELDS
        protected = PAY_FIELDS | DOCUMENT_FIELDS | {'user_id','employee_no','password'}
        body['properties'] = {k:v for k,v in body.get('properties',{}).items() if k not in protected}
        body['required'] = [k for k in body.get('required',[]) if k not in protected]
    from app.core.action_choices import binding
    def annotate(schema, field):
        if not isinstance(schema,dict):return
        b=binding(row,field)
        if b and schema.get('type') not in ('object','array'):
            schema['selector']={'field':field,'entity':b.entity,'parent':b.parent,'discriminator':b.discriminator}
        for key,value in schema.get('properties',{}).items():annotate(value,field+'.'+key if field!='body:' else field+key)
        if 'items' in schema:annotate(schema['items'],field+'.[]')
        for variant in schema.get('anyOf',[])+schema.get('allOf',[]):annotate(variant,field)
    annotate(body,'body:')
    parameters=[resolve(p) for p in operation.get('parameters',[]) if p.get('in') in ('path','query')]
    for p in parameters:annotate(p['schema'],p['in']+':'+p['name'])
    return {'label':action_label(row,route.endpoint),'method':row['methods'][0], 'path':row['path'].removeprefix('/api/v1'),
        'parameters':parameters,
        'body':body, 'media':media}

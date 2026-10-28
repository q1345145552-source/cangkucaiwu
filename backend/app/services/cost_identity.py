"""Cross-channel expense identity, deliberately separate from cash and cost calculations."""
from app.core.action_access import has_module
import json
from datetime import datetime,timedelta
from sqlalchemy import select,func
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException
from app.models import CostIdentity,PayableBill,ExpenseApproval,ExpenseFundItem,ExpenseFund,ExpenseRecord,Supplier
from app.core.permissions import Role
from app.core.menu_registry import MENU_PERMISSIONS_BY_KEY
from app.core.timezone import thai_now
from app.config import get_settings
from app.services.payable_creation import fingerprint,normalized,invoice_identity,number
from app.services.purchase_matching import scope_lock
from app.services.cost_identity_migration import ensure_cost_guards
from app.services.wallet import money
from app.services.data_history import record_history

UNSET=object()
def audit_json(value):return json.loads(json.dumps(value,ensure_ascii=False,default=str)) if value is not None else None
MODELS={'payable':PayableBill,'approval':ExpenseApproval,'fund_item':ExpenseFundItem,'expense':ExpenseRecord}
PERMISSIONS={'payable':('payable','payment_plans'),'approval':('expense_approval',),'fund_item':('expense_fund',),'expense':('operating',)}
LABELS={'payable':'应付账款','approval':'费用审批','fund_item':'备用金开销','expense':'运营支出'}
MODULES={'payable':'payable','approval':'expense_approval','fund_item':'expense_fund_item','expense':'expense'}

def readable(user,source):
    if user.role==Role.WAREHOUSE_ADMIN:return True
    if user.role not in (Role.SUPERVISOR,Role.STAFF):return False
    return any(has_module(user,k,'view') for k in PERMISSIONS[source])

async def lock(db,wid):
    if not isinstance(wid,int) or wid<=0:raise HTTPException(400,'请先选择单个仓库')
    await scope_lock(db,wid)
    await ensure_cost_guards(await db.connection())

def parse_identity(value,user):return invoice_identity(value,user)

def metadata(root):
    return {'cost_identity_id':root.id,'supplier_id':root.supplier_id,'invoice_identity':root.invoice_identity,
        'cost_source':root.source_type,'cost_source_id':root.source_id,'cost_active':root.active,
        'cost_paid_locked':root.paid_locked,'cost_payment_unknown':root.payment_unknown} if root else {'cost_identity_id':None,'invoice_identity':None}

async def metadata_for(db,record,user=None):
    root=await db.get(CostIdentity,record.cost_identity_id) if record.cost_identity_id else None
    if root:
        wid=getattr(record,'warehouse_id',None)
        if isinstance(record,ExpenseFundItem):wid=(await db.execute(select(ExpenseFund.warehouse_id).where(ExpenseFund.id==record.fund_id))).scalar_one_or_none()
        if root.warehouse_id!=wid:raise HTTPException(409,'费用身份仓库关系异常，未展示其他仓库资料')
        source=next((k for k,model in MODELS.items() if isinstance(record,model)),None)
        if root.source_type!=source and (user is None or not readable(user,root.source_type)):
            return {'cost_identity_id':None,'cost_origin_restricted':True,'invoice_identity':None}
    return metadata(root) if root else {'cost_identity_id':None,'invoice_identity':getattr(record,'invoice_identity',None)}

async def source_data(db,source,record):
    unknown=False
    if source=='fund_item':
        fund=await db.get(ExpenseFund,record.fund_id)
        if not fund:raise HTTPException(409,'备用金归属缺失，未猜配费用身份')
        wid=fund.warehouse_id;when=record.expense_date;state=record.review_status
        active=not record.is_voided and state!='rejected';paid=state=='approved'
    else:
        wid=record.warehouse_id
        when=record.bill_date if source=='payable' else record.expense_date
        state=record.status if source!='expense' else 'paid'
        unknown=(source=='payable' and record.paid_amount is None) or (source=='approval' and state in ('paid','completed') and not (record.payer_id and record.paid_at))
        paid=(unknown or money(record.paid_amount)>0) if source=='payable' else (state in ('paid','completed')) if source=='approval' else record.amount>0
        active=(state!='voided' or paid) if source=='payable' else paid if source=='approval' else record.amount>0
    return {'warehouse_id':wid,'expense_date':when.date() if isinstance(when,datetime) else when,
        'amount':money(record.amount),'currency':record.currency or 'THB','source_state':state,
        'active':active,'paid_locked':paid,'payment_unknown':unknown}

def values(root):
    return {k:getattr(root,k) for k in ('warehouse_id','source_type','source_id','supplier_id','invoice_key','issuer_key','amount','currency','expense_date','active','paid_locked','payment_unknown','source_state','source_deleted')}

async def replay(db,source,wid,key,signature):
    if not key:return None
    number(key,'登记请求编号',100)
    root=(await db.execute(select(CostIdentity).where(CostIdentity.warehouse_id==wid,
        CostIdentity.source_type==source,CostIdentity.request_key==key))).scalar_one_or_none()
    if not root:return None
    if root.request_fingerprint!=signature:raise HTTPException(409,'原费用登记已保存且内容不同，请核对原单；未重复登记')
    if root.source_deleted:raise HTTPException(409,'原登记已处理或删除，请核对费用身份历史；未重新登记')
    record=await db.get(MODELS[source],root.source_id)
    if not record or record.cost_identity_id!=root.id:raise HTTPException(409,'原登记来源关系异常，请管理员核对')
    return record

async def is_derived_expense(db,eid):
    from app.models import PayrollRecord,Reimbursement,EmployeeAdvance,ExpenseFundDisbursement
    for model in (ExpenseApproval,PayrollRecord,Reimbursement,EmployeeAdvance,ExpenseFundDisbursement):
        if (await db.execute(select(model.id).where(model.expense_record_id==eid).limit(1))).first():return True
    return False

async def candidates(db,proposal,exclude_id=None):
    wid=proposal['warehouse_id'];result=[]
    for r in (await db.execute(select(CostIdentity).where(CostIdentity.warehouse_id==wid,CostIdentity.active.is_(True)).order_by(CostIdentity.id))).scalars():
        if r.id!=exclude_id:result.append({**values(r),'version':r.version,'root_id':r.id})
    # Legacy known identities and comparable rows remain read-only; never adopt them during scans.
    for b in (await db.execute(select(PayableBill).where(PayableBill.warehouse_id==wid,PayableBill.cost_identity_id.is_(None)))).scalars():
        if proposal['source_type']=='payable' and b.id==proposal['source_id']:continue
        d=await source_data(db,'payable',b)
        if not d['active']:continue
        issuer=(b.invoice_identity or {}).get('issuer_identifier') if isinstance(b.invoice_identity,dict) else None
        row={**d,'source_type':'payable','source_id':b.id,'supplier_id':b.supplier_id,'invoice_key':b.invoice_identity_key,
            'issuer_key':fingerprint(normalized(issuer)) if issuer else None,'source_deleted':False,'root_id':None}
        row['version']=fingerprint(row);result.append(row)
    for e in (await db.execute(select(ExpenseRecord).where(ExpenseRecord.warehouse_id==wid,
            ExpenseRecord.cost_identity_id.is_(None),ExpenseRecord.amount>0,ExpenseRecord.supplier_id.is_not(None)))).scalars():
        if proposal['source_type']=='expense' and e.id==proposal['source_id']:continue
        if await is_derived_expense(db,e.id):continue
        row={**await source_data(db,'expense',e),'source_type':'expense','source_id':e.id,'supplier_id':e.supplier_id,
             'invoice_key':None,'issuer_key':None,'source_deleted':False,'root_id':None}
        row['version']=fingerprint(row);result.append(row)
    window=get_settings().PAYABLE_DUPLICATE_WINDOW_DAYS
    if not isinstance(window,int) or not 0<=window<=3660:raise HTTPException(503,'费用疑似重复日期窗口无效')
    found=[]
    for r in result:
        if (r['source_type'],r['source_id'])==(proposal['source_type'],proposal['source_id']):continue
        hard=bool(proposal['invoice_key'] and proposal['invoice_key']==r['invoice_key'])
        same_supplier=(proposal['supplier_id'] is not None and proposal['supplier_id']==r['supplier_id']) or bool(proposal['issuer_key'] and proposal['issuer_key']==r['issuer_key'])
        same_channel_payable=proposal['source_type']==r['source_type']=='payable'
        suspected=(not same_channel_payable and same_supplier and proposal['currency']==r['currency']
            and proposal['amount']==r['amount'] and abs((proposal['expense_date']-r['expense_date']).days)<=window)
        if hard or suspected:found.append({**r,'hard':hard,'ref':f'{r["source_type"]}:{r["source_id"]}'})
    return sorted(found,key=lambda r:(r['source_type'],r['source_id'])),window

async def check(db,proposal,user,confirmation=None,exclude_id=None,*,skip_suspicion=False):
    rows,window=await candidates(db,proposal,exclude_id)
    if skip_suspicion:rows=[r for r in rows if r['hard']]
    if not rows:return None
    if any(not readable(user,r['source_type']) for r in rows):
        raise HTTPException(409,{'code':'cost_duplicate_restricted','permission_required':True,
            'message':'发现跨渠道重复风险，请具有相关原单权限的人员核查；未展示无权查看的数据'})
    version=fingerprint({'candidates':rows,'proposal':{k:proposal[k] for k in
        ('warehouse_id','source_type','supplier_id','invoice_key','issuer_key','amount','currency','expense_date')}})
    visible=[{'ref':r['ref'],'source':r['source_type'],'source_label':LABELS[r['source_type']],
        'id':r['source_id'],'date':str(r['expense_date']),'amount':float(r['amount']),'currency':r['currency'],
        'status':r['source_state'],'source_deleted':r['source_deleted'],
        'href':f'/expense-identities/{r["source_type"]}/{r["source_id"]}',
        'reason':'已核实的同一完整发票身份' if r['hard'] else f'同供应商、币种、金额且日期相距不超过{window}天'} for r in rows]
    hard=any(r['hard'] for r in rows)
    challenge={'code':'cost_invoice_duplicate' if hard else 'cost_duplicate_confirmation','hard_duplicate':hard,
        'message':'该完整发票已有有效费用根，不能跨渠道重复登记' if hard else '发现跨渠道疑似费用，请核对原单；独立业务可说明本次原因后继续',
        'candidates':visible,'version':version,'window_days':window,'target_ref':f'{proposal["source_type"]}:{proposal["source_id"]}'}
    if hard:raise HTTPException(409,challenge)
    try:data=json.loads(confirmation) if isinstance(confirmation,str) else confirmation or {}
    except (ValueError,TypeError):data={}
    refs=[r['ref'] for r in rows]
    if not isinstance(data,dict) or data.get('candidate_refs')!=refs or data.get('version')!=version or not isinstance(data.get('reason'),str) or not data['reason'].strip() or len(data['reason'])>1000:
        raise HTTPException(409,challenge)
    return {'candidate_refs':refs,'version':version,'candidates':visible,'reason':data['reason'],
        'operator_id':user.id,'operator_name':user.display_name or user.username,'confirmed_at':thai_now().isoformat()}

async def sync(db,source,record,user,*,supplier=UNSET,identity=UNSET,confirmation=None,key=None,signature=None,skip_suspicion=False):
    data=await source_data(db,source,record);wid=data['warehouse_id'];await lock(db,wid)
    root=(await db.execute(select(CostIdentity).where(CostIdentity.warehouse_id==wid,
        CostIdentity.source_type==source,CostIdentity.source_id==record.id).with_for_update())).scalar_one_or_none()
    if record.cost_identity_id and (root is None or record.cost_identity_id!=root.id):raise HTTPException(409,'此记录属于另一费用根，不能从派生记录独立修改')
    sid=(root.supplier_id if root else getattr(record,'supplier_id',None)) if supplier is UNSET else supplier
    if sid is not None:
        s=await db.get(Supplier,sid)
        if not s or s.warehouse_id!=wid:raise HTTPException(403,'供应商不存在或不属于当前仓库')
    if identity is UNSET:
        inv,ik=(root.invoice_identity,root.invoice_key) if root else (record.invoice_identity,record.invoice_identity_key) if source=='payable' else (None,None)
    else:inv,ik=identity
    if inv and sid is None:raise HTTPException(400,'核实发票前请先选择本仓供应商')
    if root and root.paid_locked and root.invoice_key and ik!=root.invoice_key:raise HTTPException(400,'已实际支付费用的发票身份不能修改或清空，请保留原单核查')
    if root and root.invoice_key==ik and ik:inv=root.invoice_identity
    proposal={**data,'source_type':source,'source_id':record.id,'supplier_id':sid,'invoice_key':ik,
        'issuer_key':fingerprint(normalized(inv['issuer_identifier'])) if inv else None,'source_deleted':False}
    if root and root.paid_locked:proposal['active']=True;proposal['paid_locked']=True
    before=values(root) if root else None
    # State-only releases need no new confirmation. Activation/changed evidence must be checked again.
    unchanged=bool(root and root.active and all(getattr(root,k)==proposal[k] for k in ('supplier_id','invoice_key','amount','currency','expense_date')))
    if confirmation is None and root:confirmation=root.confirmation
    confirmed=await check(db,proposal,user,confirmation,root.id if root else None,skip_suspicion=skip_suspicion or unchanged) if proposal['amount']>0 and (proposal['active'] or not root or root.invoice_key!=ik) else None
    if not root:
        root=CostIdentity(operator_id=user.id,operator_name=user.display_name or user.username,
            request_key=number(key,'登记请求编号',100) if key else None,request_fingerprint=signature)
        db.add(root)
    for k,v in proposal.items():setattr(root,k,v)
    root.invoice_identity=inv;root.confirmation=confirmed or root.confirmation;root.version=fingerprint(proposal)
    try:await db.flush()
    except IntegrityError:raise HTTPException(409,'并发费用身份冲突，未登记第二笔；请刷新核对原单')
    record.cost_identity_id=root.id
    await record_history(db,module=MODULES[source],record_id=record.id,operator=user,
        operation_type='cost_identity',before=audit_json(before),after=audit_json({**proposal,'cost_identity_id':root.id,'confirmation':confirmed}),warehouse_id=wid)
    await db.flush();return root

async def paid(db,source,record,user):
    # An installment is a change to the existing root, never a second expense.
    return await sync(db,source,record,user,skip_suspicion=True)

async def deleted(db,source,record,user):
    root=await sync(db,source,record,user,skip_suspicion=True)
    before=values(root);root.source_deleted=True
    if not root.paid_locked:root.active=False
    root.version=fingerprint(values(root))
    await record_history(db,module=MODULES[source],record_id=record.id,operator=user,operation_type='cost_source_deleted',
        before=audit_json(before),after=audit_json({**values(root),'note':'已付身份保留占用，删除原行不能再次报同票'}),warehouse_id=root.warehouse_id)
    await db.flush()

async def link_child(db,origin,child):
    root=await db.get(CostIdentity,origin.cost_identity_id) if origin.cost_identity_id else None
    if root is None:raise HTTPException(409,'原费用身份未就绪，未生成独立派生费用')
    child.cost_identity_id=root.id
    if isinstance(child,ExpenseRecord):child.supplier_id=root.supplier_id
    await db.flush()

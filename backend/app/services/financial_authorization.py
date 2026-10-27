"""Round-three financial duties and immutable approval evidence; existing history storage."""
import hashlib,json
from fastapi import HTTPException
from sqlalchemy import select
from app.core.permissions import Role
from app.core.round2_access import own_scope
from app.models.user import User
from app.models.employee import Employee
from app.models.data_change_history import DataChangeHistory
from app.services.data_history import record_history
from app.services.fund_authorization import independent,executor


def accountant(user):
    if user.role not in (Role.STAFF, Role.WAREHOUSE_ADMIN):
        raise HTTPException(403,'只有获授权财务或管理员可以处理核算')


def approver(user):
    if user.role != Role.WAREHOUSE_ADMIN:
        raise HTTPException(403,'只有仓库管理员可以批准资金')


def payload(obj,exclude=()):
    return {c.name:str(getattr(obj,c.name)) if getattr(obj,c.name) is not None else None
            for c in obj.__table__.columns if c.name not in set(exclude)}


def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,default=str).encode()).hexdigest()

async def evidence(db,user,obj,action,value):
    own_scope(user,obj.warehouse_id)
    await record_history(db,module='financial_authorization',record_id=obj.id,operator=user,
        operation_type=action,after={'sha256':digest(value)},warehouse_id=obj.warehouse_id)

async def proof(db,obj,action,value):
    row=(await db.execute(select(DataChangeHistory).where(DataChangeHistory.module=='financial_authorization',
        DataChangeHistory.record_id==obj.id,DataChangeHistory.warehouse_id==obj.warehouse_id,
        DataChangeHistory.operation_type==action).order_by(DataChangeHistory.id.desc()).limit(1))).scalar_one_or_none()
    if not row or row.after_data != {'sha256':digest(value)}:
        raise HTTPException(409,'缺少有效核验或管理员批准；内容已变更或历史记录需重新核对')
    return row

async def employee_users(db,employee_id):
    emp=await db.get(Employee,employee_id)
    if emp is None:raise HTTPException(409,'关联员工不存在')
    ids=set((await db.execute(select(User.id).where(User.attendance_employee_id==employee_id))).scalars())
    if emp.user_id:ids.add(emp.user_id)
    return ids

async def payroll_payload(db,r):
    # Store only a digest, never copy salary/account/identity data into audit JSON.
    from app.database import Base
    ignored={'updated_at','status','confirmed_by','confirmed_at','disbursed','disbursed_at','disbursed_by','signature_path','expense_record_id','payment_account_id','funding_source','cash_advance_id'}
    from app.api.v1.payroll import _compute_employee_records, _prepare_payroll
    import inspect
    result={'record':payload(r,ignored),'calculation_version':digest(inspect.getsource(_compute_employee_records)+inspect.getsource(_prepare_payroll)),'sources':{}}
    employee=await db.get(Employee,r.employee_id)
    names=('employees','salary_templates','deduction_templates','clock_in_records','leave_requests','rest_days','absences','overtime_assignments','overtime_tasks','employee_deductions','employee_fixed_deductions','employee_advances','system_settings')
    for name in names:
        table=Base.metadata.tables.get(name)
        if table is None:continue
        query=select(table)
        if name=='employees':query=query.where(table.c.id==r.employee_id)
        elif name in ('salary_templates','deduction_templates'):
            template_id=employee.salary_template_id if name=='salary_templates' else employee.deduction_template_id
            query=query.where(table.c.id==template_id)
        elif name in ('overtime_assignments','overtime_tasks'):
            assignments=Base.metadata.tables['overtime_assignments'];tasks=Base.metadata.tables['overtime_tasks']
            relevant=select(tasks.c.id).join(assignments,assignments.c.overtime_id==tasks.c.id).where(assignments.c.employee_id==r.employee_id)
            if r.settle_start_date and r.settle_end_date:relevant=relevant.where(tasks.c.date>=r.settle_start_date,tasks.c.date<=r.settle_end_date)
            query=query.where(table.c.id.in_(relevant)) if name=='overtime_tasks' else query.where(table.c.employee_id==r.employee_id,table.c.overtime_id.in_(relevant))
        elif 'employee_id' in table.c:query=query.where(table.c.employee_id==r.employee_id)
        elif name=='clock_in_records':query=query.where(table.c.user_id.in_(await employee_users(db,r.employee_id)),table.c.warehouse_id==r.warehouse_id)
        elif 'warehouse_id' in table.c:query=query.where(table.c.warehouse_id==r.warehouse_id)
        else:continue
        for date_column in ('clock_date','leave_date','rest_date','absence_date','deduction_date','date'):
            if date_column in table.c and r.settle_start_date and r.settle_end_date:
                query=query.where(table.c[date_column]>=r.settle_start_date,table.c[date_column]<=r.settle_end_date)
                break
        rows=[dict(x) for x in (await db.execute(query)).mappings()]
        result['sources'][name]=sorted(rows,key=lambda x:str(x.get('id','')))
    return result

async def confirm_payroll(db,user,r):
    approver(user);own_scope(user,r.warehouse_id)
    if r.voided or r.disbursed or r.status!='pending':raise HTTPException(409,'只能确认未发放的待确认工资单')
    await independent(db,user,*await employee_users(db,r.employee_id))
    await evidence(db,user,r,'payroll_approve',await payroll_payload(db,r))

async def execute_payroll(db,user,r):
    own_scope(user,r.warehouse_id)
    await executor(db,user,*await employee_users(db,r.employee_id))
    if r.voided or r.disbursed or r.status!='confirmed':raise HTTPException(409,'只能发放有效确认且未发放的工资单')
    await proof(db,r,'payroll_approve',await payroll_payload(db,r))

async def draft_payroll(db,user,r):
    accountant(user);own_scope(user,r.warehouse_id)
    if r.voided or r.disbursed:raise HTTPException(409,'已作废或已发放的工资单不能删除或重算')
    if r.status!='pending' and user.role!=Role.WAREHOUSE_ADMIN:
        raise HTTPException(403,'已确认工资只能由管理员撤回或作废后重算')

async def reimb_payload(db,r):
    from app.models.reimbursement import ReimbursementItem
    lines=(await db.execute(select(ReimbursementItem).where(ReimbursementItem.reimbursement_id==r.id).order_by(ReimbursementItem.id))).scalars().all()
    return {'parent':payload(r,{'status','reviewer_id','review_remark','paid_at','payment_method','payment_account_id','payment_voucher_path','funding_source','cash_advance_id','expense_record_id'}),'items':[payload(x) for x in lines]}

async def execute_reimbursement(db,user,r):
    own_scope(user,r.warehouse_id)
    await executor(db,user,r.employee_id)
    if r.status not in ('approved','partially_approved'):
        raise HTTPException(400,'该报销单已付款' if r.status=='paid' else '仅已审批状态可付款')
    if r.is_fund_linked=='1':return  # Round-two fund proof and money guard remain authoritative.
    await proof(db,r,'reimb_approve',await reimb_payload(db,r))

async def advance_payload(db,row):
    return payload(row,{'approval_status','reviewer_id','reviewed_at','reject_reason','expense_record_id','fund_item_id','status','deducted_amount','voided_by','voided_at','void_reason'})

async def advance_people(db,row):
    return {row.operator_id,*await employee_users(db,row.employee_id)}-{None}

async def cash_payload(db,row):
    from app.models.cash_advance import CashAdvanceDocument
    lines=(await db.execute(select(CashAdvanceDocument).where(CashAdvanceDocument.cash_advance_id==row.id).order_by(CashAdvanceDocument.id))).scalars().all()
    return {'parent':payload(row,{'status','repaid_amount','reviewed_by_id','reviewed_by_name','reviewed_at','reject_reason'}),'documents':[payload(x) for x in lines]}

async def bill_payload(db,row):
    from app.services.purchase_matching import matching
    match=await matching(db,row)
    return {'bill':payload(row,{'cost_identity_id','status','paid_amount','paid_at','payment_method','legacy_paid_amount','legacy_paid_at','match_review','need_boss_confirm'}),'matching_hash':match['snapshot_hash']}

async def execute_bill(db,user,row):
    own_scope(user,row.warehouse_id)
    await executor(db,user,getattr(row,'created_by',None))
    await proof(db,row,'bill_approve',await bill_payload(db,row))

async def permitted(operation):
    try:
        await operation
        return True
    except HTTPException:
        return False

async def payroll_capabilities(db,user,r):
    independent_user=await permitted(independent(db,user,*await employee_users(db,r.employee_id)))
    return {'can_confirm':user.role==Role.WAREHOUSE_ADMIN and independent_user and r.status=='pending' and not r.disbursed and not r.voided,
        'can_pay':await permitted(execute_payroll(db,user,r)),
        'can_rework':await permitted(draft_payroll(db,user,r))}

async def reimbursement_capabilities(db,user,r):
    own=not await permitted(independent(db,user,r.employee_id))
    verified=await permitted(proof(db,r,'reimb_verify',await reimb_payload(db,r))) if r.is_fund_linked!='1' and r.status=='pending' else False
    if r.is_fund_linked=='1' and r.fund_item_id and r.status=='fund_linked':
        from app.models.expense_fund import ExpenseFundItem, ExpenseFund
        from app.services import fund_authorization as fund_duties
        linked=(await db.execute(select(ExpenseFundItem,ExpenseFund).join(ExpenseFund,ExpenseFundItem.fund_id==ExpenseFund.id).where(ExpenseFundItem.id==r.fund_item_id))).first()
        if linked and linked[1].warehouse_id==r.warehouse_id and linked[1].employee_id==r.employee_id and linked[0].review_status=='verified':
            verified=await permitted(fund_duties.proof(db,linked[0],'item_verify',await fund_duties.item_review_payload(db,*linked),r.warehouse_id))
    can_pay=False
    if r.status in ('approved','partially_approved'):
        if r.is_fund_linked=='1':
            from app.services.fund_authorization import reimbursement_payment_capability
            can_pay=await reimbursement_payment_capability(db,user,r)
        else:can_pay=await permitted(execute_reimbursement(db,user,r))
    return {'can_verify':not own and user.role in (Role.STAFF,Role.WAREHOUSE_ADMIN) and r.status=='pending' and r.is_fund_linked!='1' and not verified,
        'can_approve':not own and user.role==Role.WAREHOUSE_ADMIN and verified,
        'can_pay':can_pay,'can_return':user.role==Role.WAREHOUSE_ADMIN and r.is_fund_linked!='1' and r.status in ('approved','partially_approved','rejected'),
        'workflow_stage':'待批准' if verified else {'pending':'待核验','fund_linked':'待核验','approved':'待执行','partially_approved':'部分批准，待执行','paid':'已付款','rejected':'已驳回'}.get(r.status,r.status)}

async def advance_capabilities(db,user,r):
    independent_user=await permitted(independent(db,user,*await advance_people(db,r)))
    verified=await permitted(proof(db,r,'advance_verify',await advance_payload(db,r))) if r.approval_status=='verified' else False
    approved=await permitted(proof(db,r,'advance_approve',await advance_payload(db,r))) if r.approval_status=='approved_ready' else False
    executor_allowed=await permitted(executor(db,user,*await advance_people(db,r)))
    return {'can_verify':not r.is_voided and independent_user and user.role in (Role.STAFF,Role.WAREHOUSE_ADMIN) and r.approval_status=='pending',
        'can_approve':not r.is_voided and independent_user and user.role==Role.WAREHOUSE_ADMIN and verified,
        'can_execute':not r.is_voided and approved and executor_allowed,
        'workflow_stage':{'pending':'待核验','verified':'待批准','approved_ready':'待出款','approved':'已出款','rejected':'已驳回'}.get(r.approval_status,r.approval_status)}

async def cash_capabilities(db,user,r):
    independent_user=r.payer_id is not None and await permitted(independent(db,user,r.payer_id,r.created_by_id))
    verified=await permitted(proof(db,r,'cash_verify',await cash_payload(db,r))) if r.status=='pending' else False
    approved=await permitted(proof(db,r,'cash_approve',await cash_payload(db,r))) if r.status=='confirmed' else False
    return {'can_verify':r.status=='pending' and not verified and independent_user and user.role in (Role.STAFF,Role.WAREHOUSE_ADMIN),
        'can_approve':verified and independent_user and user.role==Role.WAREHOUSE_ADMIN,
        'can_repay':approved and await permitted(executor(db,user,r.payer_id,r.created_by_id)),
        'workflow_stage':'待批准' if verified else {'pending':'待核验','confirmed':'待执行','repaid':'已还清','rejected':'已驳回'}.get(r.status,r.status)}

async def bill_capabilities(db,user,r):
    independent_user=await permitted(independent(db,user,r.created_by))
    active=r.status not in ('paid','voided')
    value=await bill_payload(db,r)
    verified=await permitted(proof(db,r,'bill_verify',value))
    approved=await permitted(proof(db,r,'bill_approve',value))
    return {'can_verify':active and not verified and independent_user and user.role in (Role.STAFF,Role.WAREHOUSE_ADMIN),
        'can_approve':active and verified and independent_user and user.role==Role.WAREHOUSE_ADMIN,
        'can_pay':active and approved and await permitted(executor(db,user,r.created_by)),
        'workflow_stage':{'paid':'已付清','voided':'已作废'}.get(r.status,'待执行' if approved else ('待批准' if verified else '待核验'))}


async def plan_capabilities(db,user,p):
    from app.models.payable import PayableBill
    from app.services.wallet import money
    if user.role not in (Role.STAFF,Role.WAREHOUSE_ADMIN) or p.status!='pending' or not p.bill_ids or len(set(p.bill_ids))!=len(p.bill_ids):return {'can_execute':False}
    if not await permitted(proof(db,p,'plan_prepare',payload(p,{'status'}))):return {'can_execute':False}
    rows=(await db.execute(select(PayableBill).where(PayableBill.id.in_(p.bill_ids)))).scalars().all()
    valid=len(rows)==len(p.bill_ids) and len({r.currency or 'THB' for r in rows})==1
    if not valid:return {'can_execute':False}
    for row in rows:
        if row.warehouse_id!=p.warehouse_id or row.status in ('paid','voided') or not await permitted(execute_bill(db,user,row)):
            return {'can_execute':False}
    return {'can_execute':sum(money(r.amount)-money(r.paid_amount) for r in rows)==money(p.total_amount)}

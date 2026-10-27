"""Petty-cash separation of duties; evidence lives in existing transactional history."""
from fastapi import HTTPException
from sqlalchemy import select
from app.core.permissions import Role
from app.core.round2_access import own_scope
from app.models.user import User
from app.models.employee import Employee
from app.models.data_change_history import DataChangeHistory
from app.services.data_history import record_history

async def identities(db, user):
    employee_ids = set((await db.execute(select(Employee.id).where(Employee.user_id == user.id))).scalars())
    if user.attendance_employee_id:
        employee_ids.add(user.attendance_employee_id)
    ids = {user.id}
    if employee_ids:
        ids.update((await db.execute(select(User.id).where(User.attendance_employee_id.in_(employee_ids)))).scalars())
        ids.update(v for v in (await db.execute(select(Employee.user_id).where(Employee.id.in_(employee_ids)))).scalars() if v)
    return ids

async def independent(db, user, *beneficiaries):
    if set(beneficiaries) & await identities(db, user):
        raise HTTPException(403, "不能核验、批准或支付本人的资金申请")

async def recorder(db, user, fund):
    own_scope(user, fund.warehouse_id)
    if fund.status != 'active':
        raise HTTPException(400, '备用金账户已停用')
    if user.role != Role.WAREHOUSE_ADMIN and fund.employee_id not in await identities(db, user):
        raise HTTPException(403, '只能登记本人的备用金开销')

async def evidence(db, user, obj, action, payload, warehouse_id):
    await record_history(db, module='fund_authorization', record_id=obj.id, operator=user,
        operation_type=action, after=payload, warehouse_id=warehouse_id)

async def proof(db, obj, action, payload, warehouse_id):
    row = (await db.execute(select(DataChangeHistory).where(
        DataChangeHistory.module == 'fund_authorization', DataChangeHistory.record_id == obj.id,
        DataChangeHistory.operation_type == action, DataChangeHistory.warehouse_id == warehouse_id
    ).order_by(DataChangeHistory.id.desc()).limit(1))).scalar_one_or_none()
    if not row or row.after_data != payload:
        raise HTTPException(409, '缺少可验证的核验或批准记录，请重新核验批准；历史记录不能直接执行')
    return row

async def executor(db, user, *beneficiaries):
    await independent(db, user, *beneficiaries)
    if user.role == Role.STAFF:
        return
    if user.role == Role.WAREHOUSE_ADMIN:
        finance = (await db.execute(select(User.id).where(User.id.in_(beneficiaries), User.role == Role.STAFF))).first()
        if finance:
            return
    raise HTTPException(403, '仅获授权财务可以执行；财务本人申请可由管理员独立办理')

def recharge_payload(rr, fund):
    return {'fund_id': fund.id, 'applicant_id': rr.applicant_id, 'beneficiary_id': fund.employee_id,
            'amount': str(rr.amount), 'currency': fund.currency or 'THB'}


def item_payload(item, fund):
    return {'fund_id': fund.id, 'beneficiary_id': fund.employee_id, 'amount': str(item.amount),
            'currency': item.currency, 'receipt': item.receipt, 'description': item.description,
            'expense_date': item.expense_date.isoformat()}

async def approved_item_execution(db, user, reimb, fund, item):
    own_scope(user, fund.warehouse_id)
    await executor(db, user, reimb.employee_id, fund.employee_id)
    if item.review_status != 'approved':
        raise HTTPException(409, '备用金开销尚未取得管理员批准')
    await proof(db, item, 'item_approve', item_payload(item, fund), fund.warehouse_id)

async def recharge_capabilities(db, user, rr, fund):
    own = bool({rr.applicant_id, fund.employee_id} & await identities(db, user))
    finance = (await db.execute(select(User.id).where(User.id.in_([rr.applicant_id, fund.employee_id]), User.role == Role.STAFF))).first()
    valid_verification = valid_approval = False
    if rr.status in ('verified', 'approved_ready'):
        try:
            await proof(db, rr, 'recharge_verify' if rr.status == 'verified' else 'recharge_approve', recharge_payload(rr, fund), rr.warehouse_id)
            valid_verification = rr.status == 'verified'
            valid_approval = rr.status == 'approved_ready'
        except HTTPException:
            pass
    return {
        'can_verify': not own and rr.status == 'pending' and user.role in (Role.STAFF, Role.WAREHOUSE_ADMIN),
        'can_approve': not own and valid_verification and user.role == Role.WAREHOUSE_ADMIN,
        'can_reject': not own and rr.status in ('pending', 'verified', 'approved_ready') and user.role == Role.WAREHOUSE_ADMIN,
        'can_execute': not own and valid_approval and (user.role == Role.STAFF or (user.role == Role.WAREHOUSE_ADMIN and bool(finance))),
    }

async def reimbursement_payment_capability(db, user, reimb):
    if reimb.is_fund_linked != '1' or reimb.status not in ('approved', 'partially_approved') or not reimb.fund_item_id:
        return False
    from app.models.expense_fund import ExpenseFund, ExpenseFundItem
    row = (await db.execute(select(ExpenseFundItem, ExpenseFund).join(ExpenseFund,
        ExpenseFundItem.fund_id == ExpenseFund.id).where(ExpenseFundItem.id == reimb.fund_item_id,
        ExpenseFund.warehouse_id == reimb.warehouse_id, ExpenseFund.employee_id == reimb.employee_id))).first()
    if row is None:
        return False
    try:
        await approved_item_execution(db, user, reimb, row[1], row[0])
        return True
    except HTTPException:
        return False

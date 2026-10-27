"""Explicit personal mode for existing requests; never grants management menus."""
from fastapi import Depends, HTTPException, Request
from app.core.permissions import get_current_user, check_staff_permission
from app.core.employee_access import employee_access
from app.database import get_db
from app.models.reimbursement import Reimbursement
from app.models.expense_fund import ExpenseFund
from app.services.fund_authorization import identities

ACTIONS = {
    'reimbursement': {'list_reimbursements', 'create_reimbursement', 'list_reimb_categories',
                      'get_reimb_detail', 'edit_reimb', 'delete_reimb', 'submit_reimb'},
    'expense_fund': {'list_accounts', 'list_items', 'add_item', 'upload_receipt',
                     'submit_recharge_request', 'list_recharge_requests', 'upload_new_item_receipt'},
    'employee_advance': {'create_advance', 'list_funding_options'},
}

def personal_finance_access(permissions):
    management = check_staff_permission(permissions)
    async def dependency(request: Request, user=Depends(get_current_user), db=Depends(get_db)):
        if request.query_params.get('view') != 'self':
            return await management(user)
        endpoint = request.scope['route'].endpoint
        module = endpoint.__module__.rsplit('.', 1)[-1]
        if endpoint.__name__ not in ACTIONS.get(module, set()):
            raise HTTPException(403, '本人入口不提供管理、审批或付款操作')
        user = await employee_access(self_only=True)(request, user, db)
        user._personal_finance = True
        user._personal_user_ids = await identities(db, user)
        for key, model in [('reimb_id', Reimbursement), ('account_id', ExpenseFund)]:
            if key not in request.path_params:
                continue
            obj = await db.get(model, int(request.path_params[key]))
            if obj is None or obj.warehouse_id != user._attendance_employee.warehouse_id or obj.employee_id not in user._personal_user_ids:
                raise HTTPException(403, '只能访问本人的申请或备用金账户')
        if module == 'reimbursement' and endpoint.__name__ in ('create_reimbursement', 'edit_reimb'):
            if request.headers.get('content-type') == '':
                raise HTTPException(415, 'Content-Type不能为空，请使用JSON媒体类型')
        if module == 'employee_advance' and request.method == 'POST':
            body = await request.json()
            if body.get('employee_id') != user._attendance_employee.id or body.get('user_id') is not None:
                raise HTTPException(403, '本人预支只能为本人正式员工档案申请')
            from app.models.cash_advance import CashAdvance
            for field, model, owner in [('fund_account_id', ExpenseFund, 'employee_id'), ('cash_advance_id', CashAdvance, 'payer_id')]:
                if body.get(field) is not None:
                    obj = await db.get(model, body[field])
                    if obj is None or obj.warehouse_id != user.warehouse_id or getattr(obj, owner) not in user._personal_user_ids:
                        raise HTTPException(403, '本人申请不能使用他人的备用金或垫款单')
        if request.query_params.get('applicant_id') not in (None, str(user.id)):
            raise HTTPException(403, '只能查询本人申请')
        return user
    return dependency

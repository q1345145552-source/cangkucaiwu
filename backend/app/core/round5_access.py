"""Read ceilings and server-side projections; existing action/menu guards remain."""
from functools import wraps
from inspect import signature
from fastapi import Depends, HTTPException, Request
from app.core.permissions import Role, get_current_user
from app.core.menu_registry import MENU_PERMISSIONS_BY_KEY
from app.database import get_db

FINANCIAL_MODULES = {'reports','cost_funds_debt','income_expense','incoming','reconciliation',
    'payable','credit','cash_advance','cost_identity','salary_template','deduction_template','employee_deduction'}
SELF_FIXED = {('payroll','my_payslip'),('employee_advance','my_debt'),('clock_in','get_today')}
SELF_ONSITE = {('clock_in',n) for n in ('list_records','get_photos','list_makeup_requests')} | {
    ('attendance',n) for n in ('list_leaves','list_rest_days','get_calendar')} | {
    ('overtime',n) for n in ('list_overtimes','pending_overtimes','monthly_hours','get_overtime_limit')}
PERSONAL_FINANCE_READ = {('reimbursement',n) for n in ('list_reimbursements','get_reimb_detail','list_reimb_categories')} | {
    ('expense_fund',n) for n in ('list_accounts','list_items','list_recharge_requests','list_disbursements')} | {('employee_advance','list_funding_options')}
PAY_FIELDS = {'daily_wage','base_salary','salary_template_id','salary_template_name','salary_template_type',
    'salary_template_amount','salary_template_overtime_fee','deduction_template_id','deduction_template_name',
    'bank_account_number','bank_name','bank_account_holder','payroll','payroll_total','payroll_details'}
DOCUMENT_FIELDS = {'myanmar_id','thai_id_number','sso_number','passport_number','work_permit_number',
    'passport_photo_path','passport_photo_thumb_path','work_permit_photo_path','work_permit_photo_thumb_path'}


def has_menu(user, key):
    return user.role == Role.WAREHOUSE_ADMIN or (
        user.role in (Role.SUPERVISOR,Role.STAFF) and key in MENU_PERMISSIONS_BY_KEY and MENU_PERMISSIONS_BY_KEY[key].label in (user.extra_permissions or []))


def financial_reader(user, key):
    return user.role == Role.WAREHOUSE_ADMIN or (user.role == Role.STAFF and has_menu(user,key))


def is_read_action(module, name, methods):
    return 'GET' in methods or (module,name) in {('payroll','preview_payroll'),('supplier_quotes','preview'),('settings_api','backup_all_data')}


def personal_read(module, name, user, request):
    key=(module,name)
    return key in SELF_FIXED or (key in SELF_ONSITE and (user.role == Role.WAREHOUSE_LABOR or request.query_params.get('view') == 'self')) or (
        key in PERSONAL_FINANCE_READ and (user.role == Role.SUPERVISOR or request.query_params.get('view') == 'self'))


async def read_scope(request: Request, user=Depends(get_current_user), db=Depends(get_db)):
    endpoint=request.scope['route'].endpoint
    module,name=endpoint.__module__.rsplit('.',1)[-1],endpoint.__name__
    if module in ('market','group_order'):
        return user  # Existing explicitly shared platform guards remain authoritative.
    if personal_read(module,name,user,request):
        return user  # Actual employee_access/personal_finance validates the binding and header.
    if (module,name) in {('auth','get_me'),('users','list_available_permissions'),('warehouses','list_warehouses'),('settings_api','get_boss_contact')}:
        return user
    from app.services.warehouse_summary import warehouse_scope
    raw=request.query_params.getlist('warehouse_id')+request.query_params.getlist('warehouse_ids')
    try: requested=[int(v) for v in raw]
    except ValueError: raise HTTPException(400,'仓库筛选格式无效')
    selected=await warehouse_scope(db,user,request.headers.get('X-Warehouse-ID'),warehouse_ids=requested)
    if not selected: raise HTTPException(403,'没有可访问的仓库')
    ids=[w.id for w in selected]
    user._warehouse_ids=ids;user._all_warehouse_ids=ids
    user._active_wh_id=ids[0] if len(ids)==1 else None
    user._all_warehouses=len(ids)>1
    if user.role == Role.SUPERVISOR:
        if module in FINANCIAL_MODULES and (module,name) != ('income_expense','list_categories'):
            raise HTTPException(403,'只有获授权财务或管理员可以处理核算' if module == 'cash_advance' else '该财务数据不属于主管现场职责')
        if (module,name) == ('customers','customer_receivables'):
            raise HTTPException(403,'客户财务对账不属于现场查询范围')
        if module == 'payroll':
            raise HTTPException(403,'无权查看工资数据')
        if module == 'dashboard' and name in ('dashboard_cockpit','dashboard_trends','warehouse_summary','pending_tasks'):
            raise HTTPException(403,'请使用现场待办和本人入口')
        if module == 'expense_fund' and name not in ('fund_settings',):
            raise HTTPException(403,'主管只能查看本人的备用金申请')
        if module == 'reimbursement':
            raise HTTPException(403,'主管只能查看本人的报销申请')
    if module == 'dashboard' and name in ('dashboard_cockpit','dashboard_trends','warehouse_summary','pending_tasks'):
        if not financial_reader(user,'reports'):raise HTTPException(403,'财务汇总需要财务职责及报表权限')
    return user


def remove_fields(value, fields):
    if isinstance(value,list):return [remove_fields(v,fields) for v in value]
    if isinstance(value,dict):return {k:remove_fields(v,fields) for k,v in value.items() if k not in fields}
    return value


def project(kind,user,data):
    if kind == 'employee':
        fields=set()
        if not financial_reader(user,'payroll'):fields |= PAY_FIELDS
        if user.role != Role.WAREHOUSE_ADMIN:fields |= DOCUMENT_FIELDS
        return remove_fields(data,fields)
    if kind == 'supplier' and user.role != Role.WAREHOUSE_ADMIN:
        return remove_fields(data,{'ai_evaluation','ai_evaluated_at'})
    if kind == 'efficiency' and not financial_reader(user,'reports'):
        return remove_fields(data,{'labor_cost','cost_per_order','cross_check','recharge_amount','prev_recharge_amount','recharge_pct'})
    return data


def read_projection(kind):
    """Applied on selected JSON handlers; projection occurs before serialization."""
    def decorate(fn):
        sig=signature(fn)
        @wraps(fn)
        async def wrapped(*args,**kwargs):
            bound=sig.bind(*args,**kwargs)
            user=bound.arguments.get('current_user') or bound.arguments.get('user')
            result=await fn(*args,**kwargs)
            return project(kind,user,result)
        return wrapped
    return decorate

HISTORY_MENUS = {
    'employee':'employees','employees':'employees','attendance':'attendance','clock_in':'attendance','clock-in':'attendance',
    'overtime':'overtime','inventory':'inventory','suppliers':'suppliers','purchase_order':'suppliers','sku_catalog':'suppliers',
    'supplier_quotes':'suppliers','payroll':'payroll','salary_templates':'salary_templates','deduction_templates':'deduction_templates',
    'employee_deductions':'employee_deductions','employee_fixed_deductions':'employee_deductions',
    'employee_advances':'employee_advances','employee-advances':'employee_advances','expense_fund':'expense_fund','expense-fund':'expense_fund',
    'reimbursement':'reimbursement','accounts':'accounts','payment_accounts':'accounts','payable':'payable',
    'cash_advance':'cash_advances','cash-advances':'cash_advances','expense_approval':'expense_approval','expense-approvals':'expense_approval',
    'incoming':'incoming','reconciliation':'reconciliation','income_expense':'operating','income-expense':'operating','customers':'customers',
}
ONSITE_HISTORY={'employee','employees','attendance','clock_in','clock-in','overtime','inventory','suppliers','purchase_order','sku_catalog','supplier_quotes'}

def history_modules(user):
    if user.role == Role.WAREHOUSE_ADMIN:return None
    return [m for m,key in HISTORY_MENUS.items() if has_menu(user,key) and (user.role != Role.SUPERVISOR or m in ONSITE_HISTORY)]


def history_values(user, value):
    if not isinstance(value,dict):return {'value':'[历史内容已隐藏]'} if value else value
    if user.role == Role.SUPERVISOR:
        allowed={'name','position','status','date','hours','actual_hours','confirmed','quantity','operation_type'}
        return {**{k:v for k,v in value.items() if k in allowed and isinstance(v,(str,int,float,bool,type(None)))},'changed_fields':sorted(value)}
    hidden=DOCUMENT_FIELDS|{'password','password_hash','bank_account_number','account_number','account_holder','token','access_token',
        'secret','secret_key','receipt','voucher','voucher_path','payment_voucher_path','photo_path','signature_path'}
    return remove_fields(value,hidden)


async def own_read_employee(db, user):
    from app.core.employee_access import own_employee
    from app.core.permissions import get_wh_ids
    emp = await own_employee(db, user)
    if emp is None or emp.warehouse_id not in get_wh_ids(user):
        raise HTTPException(403, '请先关联有效的本人员工档案')
    return emp


async def own_read_ids(db, user):
    await own_read_employee(db, user)
    from app.services.fund_authorization import identities
    return await identities(db, user)

"""Action metadata and explicitly minimal read dependencies; never returns financial amounts."""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from app.database import get_db
from app.core.permissions import get_current_user, get_wh_ids, Role
from app.core.action_access import CATALOG, role_grants, access_description, permission_state, has_module
from app.core.menu_registry import MENU_PERMISSIONS
from app.core.round2_access import mutation_scope
from app.services.action_permission_migration import migrate_permissions
from pydantic import BaseModel, Field
from app.models.payroll import PayrollRecord
from app.models import Employee, PaymentAccount, Reimbursement, ExpenseFund, PayableBill, PayablePlan, LeaveRequest
from app.models.overtime import OvertimeTask

router = APIRouter()


@router.get('/catalog')
async def catalog(request: Request, role: str = Query('staff'), user=Depends(get_current_user)):
    if role not in ('warehouse_admin','super_admin','supervisor','staff','warehouse_labor'):
        raise HTTPException(400, '未知角色')
    from app.core.action_forms import contract, action_label
    contracts = {r["id"]: contract(request.app, r, role) for r in CATALOG["routes"] if r["mode"] == "business" and r["tier"] != "view"}
    ceiling = role_grants(role)
    modules = []
    for item in MENU_PERMISSIONS:
        tiers = {}
        for tier in ('view','operate','approve'):
            actions = [r for r in CATALOG['routes'] if item.menu_key in r.get('grant_modules',[r['module_key']]) and
                (r['tier']==tier or any(v['tier']==tier for v in r.get('variants',{}).get('values',{}).values()))]
            tiers[tier] = {'grant':f'{item.menu_key}:{tier}','allowed':f'{item.menu_key}:{tier}' in ceiling,
                'reason':'仍受对象、仓库、状态及本人隔离限制' if f'{item.menu_key}:{tier}' in ceiling else '超出角色职责或本模块没有该类动作',
                'actions':[{'id':r['id'],'method':r['methods'],'path':r['path'],'roles':r['roles'],'label':r.get('label') or action_label(r)} for r in actions]}
        modules.append({'key':item.menu_key,'label':item.label,'tiers':tiers,
            'minimum_read':'操作/审批不授予全仓查看；按具体动作和字段校验对象选择。选中单据仅返回办理所需金额、状态及版本，不返回银行资料、证件或全仓汇总'})
    return {'version':1,'role':role,'modules':modules,'routes':[{**{k:r[k] for k in ('id','module_key','grant_modules','tier','mode','variants') if k in r},'form':contracts.get(r['id'])} for r in CATALOG['routes']]}


@router.get('/me')
async def my_actions(user=Depends(get_current_user)):
    return access_description(user)


@router.get('/choices/{module}')
async def choices(module: str, request: Request, kind: str = 'records',
                  action: str | None = None, field: str | None = None,
                  parent_id: int | None = Query(None,gt=0), selected_id: str | None = Query(None,min_length=1,max_length=100), document_type: str | None = None, search: str = Query('',max_length=100),
                  page: int = Query(1,ge=1,le=100000), page_size: int = Query(30,ge=1,le=100),
                  user=Depends(get_current_user), db=Depends(get_db)):
    if action is not None or field is not None:
        from app.core.action_choices import authorize, select_choices
        from app.core.action_forms import contract
        row=next((r for r in CATALOG['routes'] if r['id']==action),None)
        authorize(user,row)
        if module not in row.get('grant_modules',[row['module_key']]):
            raise HTTPException(403,'动作与模块不匹配')
        form=contract(request.app,row,user.role)
        def selectors(value):
            if isinstance(value,dict):
                if 'selector' in value:yield value['selector']['field']
                for child in value.values():yield from selectors(child)
            elif isinstance(value,list):
                for child in value:yield from selectors(child)
        if not form or field not in set(selectors(form)):
            raise HTTPException(400,'该动作没有此对象字段')
        from app.services.warehouse_summary import warehouse_scope
        wh_ids=[w.id for w in await warehouse_scope(db,user,request.headers.get('X-Warehouse-ID'))]
        return await select_choices(db,user,wh_ids,row,field,parent_id,search,page,page_size,selected_id,document_type)

    from app.core.action_access import variants
    eligible=any(r['mode']=='business' and module in r.get('grant_modules',[r['module_key']]) and any(user.role in v['roles'] and v['tier'] in ('operate','approve') and has_module(user,module,v['tier']) for v in variants(r)) for r in CATALOG['routes'])
    if permission_state(user)['version']=='invalid' or not eligible:
        raise HTTPException(403,'缺少该模块操作或审批授权，不能使用最小选择器')
    from app.services.warehouse_summary import warehouse_scope
    wh_ids=[w.id for w in await warehouse_scope(db,user,request.headers.get('X-Warehouse-ID'))]
    models={'employees':Employee,'attendance':Employee,'leave':LeaveRequest,'overtime':OvertimeTask,
            'payroll':PayrollRecord,'expense_fund':ExpenseFund,'reimbursement':Reimbursement,
            'payable':PayableBill,'payment_plans':PayablePlan,'accounts':PaymentAccount}
    model=models.get(module)
    if kind=='employees' and module in ('attendance','leave','overtime','payroll'):
        model=Employee
    elif kind=='accounts':
        if module not in ('payroll','expense_fund','reimbursement','payable','payment_plans','employee_advances','expense_approval') or user.role not in (Role.STAFF,Role.WAREHOUSE_ADMIN):
            raise HTTPException(403,'该操作不提供付款账户选择')
        model=PaymentAccount
    elif kind!='records':
        raise HTTPException(400,'未知选择器类型')
    if model is None:
        raise HTTPException(404,'该模块没有最小选择器')
    q=select(model).where(model.warehouse_id.in_(wh_ids))
    if model is Employee:q=q.where(Employee.is_deleted==False)
    if user.role==Role.SUPERVISOR and model in (ExpenseFund,Reimbursement):
        from app.core.round5_access import own_read_ids
        q=q.where(model.employee_id.in_(await own_read_ids(db,user)))
    rows=(await db.execute(q.order_by(model.id).limit(100))).scalars().all()
    return {'data':[{'id':r.id,'warehouse_id':r.warehouse_id,'label':getattr(r,'name',None) or getattr(r,'account_name',None) or f'记录 {r.id}',
                     'status':getattr(r,'status',None),
                     **({'employee_id':r.employee_id,'date':r.leave_date,'hours':r.hours,'leave_type':r.leave_type} if isinstance(r,LeaveRequest) else {}),
                     **({'date':r.date,'hours':r.hours} if isinstance(r,OvertimeTask) else {})} for r in rows],'scope':'minimal-action-dependency','limit':100}


class MigrateRequest(BaseModel):
    model_config={'extra':'forbid'}
    user_ids:list[int]=Field(min_length=1,max_length=100)
    reason:str=Field(min_length=1,max_length=200)


@router.post('/migrate',dependencies=[Depends(mutation_scope)])
async def migrate(req:MigrateRequest,user=Depends(get_current_user),db=Depends(get_db)):
    return await migrate_permissions(db,user,req.user_ids,req.reason)

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from app.database import get_db
from app.models.customer import Customer
from app.models.user import User
from app.core.permissions import check_staff_permission, check_staff_permission_any, get_wh_id, get_wh_ids, Role, get_current_user, require_non_labor
from app.schemas.business import CustomerCreate, CustomerUpdate

from app.core.menu_registry import MENU_PERMISSIONS_BY_KEY

_PERMISSION = MENU_PERMISSIONS_BY_KEY["customers"].label

from app.services.customer_receivables import positions, empty_position, legacy_review, bind_receipt
from app.services.warehouse_summary import warehouse_scope
from app.services.money_period import money_period
from app.models.recharge import IncomingFlow
from pydantic import BaseModel, Field
from datetime import date
from app.core.retired_entries import require_operating_entries_enabled

router = APIRouter()

class CustomerReceiptLink(BaseModel):
    incoming_flow_id: int = Field(gt=0)


async def _scoped_customer(db, user, header, customer_id):
    scope = [w.id for w in await warehouse_scope(db, user, header)]
    customer = await db.get(Customer, customer_id)
    if not customer: raise HTTPException(404, "客户不存在")
    if customer.warehouse_id not in scope: raise HTTPException(403, "只能访问当前仓库客户的对账")
    return customer


@router.get("/{customer_id}/receivables", dependencies=[Depends(require_operating_entries_enabled)])
async def customer_receivables(customer_id: int, request: Request, month: str = None,
    start_date: str = None, end_date: str = None,
    current_user: User = Depends(check_staff_permission_any(_PERMISSION, MENU_PERMISSIONS_BY_KEY["credit"].label)),
    db: AsyncSession = Depends(get_db)):
    customer = await _scoped_customer(db,current_user,request.headers.get('X-Warehouse-ID'),customer_id)
    start,end = money_period(month,start_date,end_date,default_start=date.min,default_end=date.max)
    result = (await positions(db,[customer.warehouse_id],[customer.id],start_date=start,end_date=end,sources=True)).get(customer.id,{})
    if not result: result[customer.default_currency or 'THB'] = {**empty_position(customer.id,customer.default_currency or 'THB'),'events':[]}
    for group in result.values():
        group['period_shipped'] = round(sum(r['amount'] for r in group['events'] if r['source']=='shipment'),2)
        group['period_received'] = round(sum(r['amount'] for r in group['events'] if r['source']=='incoming'),2)
    review = (await legacy_review(db,[customer.warehouse_id],[customer.id])).get(customer.id,[])
    return {'customer_id':customer.id,'warehouse_id':customer.warehouse_id,'customer_name':customer.company_name,
        'by_currency':result,'review_items':review,'needs_review':bool(review),'start_date':str(start),'end_date':str(end),
        'basis':'同客户同仓同币种，已登记发货减唯一实际到账；只按编号关联，不按名称或申报金额推断',
        'allocation_basis':'按客户同币种总额抵扣，不做逐票核销；已核销为应收与实收较小值，预收仅为实收超过应收的部分',
        'refund_workflow_supported':False}


@router.post("/{customer_id}/receipts/link", dependencies=[Depends(require_operating_entries_enabled)])
async def link_customer_receipt(customer_id: int, req: CustomerReceiptLink, request: Request,
    current_user: User = Depends(check_staff_permission(MENU_PERMISSIONS_BY_KEY["credit"].label)),
    db: AsyncSession = Depends(get_db)):
    customer = await _scoped_customer(db,current_user,request.headers.get('X-Warehouse-ID'),customer_id)
    flow = (await db.execute(select(IncomingFlow).where(IncomingFlow.id == req.incoming_flow_id)
        .with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
    if not flow: raise HTTPException(404,'到账流水不存在')
    linked = await bind_receipt(db,customer,flow,current_user)
    return {'incoming_flow_id':flow.id,'customer_id':customer.id,'linked':linked,
        'message':'客户到账已关联，钱包未重复入账' if linked else '该到账已关联此客户，未重复分配'}


@router.get("", dependencies=[Depends(require_non_labor)])
async def list_customers(
    request: Request,
    page: int = 1, page_size: int = 20, search: str = None,
    credit_status: str = None,
    current_user: User = Depends(check_staff_permission_any(
        _PERMISSION,
        MENU_PERMISSIONS_BY_KEY["recharge"].label,
        MENU_PERMISSIONS_BY_KEY["incoming"].label,
        MENU_PERMISSIONS_BY_KEY["credit"].label,
    )),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if current_user.role == Role.SUPERVISOR:
        if not search or len(search.strip()) < 2 or any(c in search for c in ("%", "_")):raise HTTPException(403,"请输入具体客户名称或编号查询，不提供客户名册批量读取")
        if page_size > 20 or page_size < 1 or page != 1:raise HTTPException(403,"现场客户查询最多20条，请缩小搜索范围")
    scope = [w.id for w in await warehouse_scope(db,current_user,request.headers.get('X-Warehouse-ID'))]
    query = select(Customer).where(Customer.warehouse_id.in_(scope))
    count_q = select(func.count(Customer.id)).where(Customer.warehouse_id.in_(scope))
    if current_user.role != Role.SUPER_ADMIN:
        query = query.where(Customer.warehouse_id.in_(get_wh_ids(current_user)))
        count_q = count_q.where(Customer.warehouse_id.in_(get_wh_ids(current_user)))
    if search:
        filt = or_(Customer.company_name.ilike(f"%{search}%"), Customer.customer_code.ilike(f"%{search}%"))
        query = query.where(filt); count_q = count_q.where(filt)
    if credit_status == "true":
        query = query.where(Customer.credit_status == True); count_q = count_q.where(Customer.credit_status == True)
    elif credit_status == "false":
        query = query.where(Customer.credit_status == False); count_q = count_q.where(Customer.credit_status == False)
    total = (await db.execute(count_q)).scalar()
    result = await db.execute(query.order_by(Customer.created_at.desc()).offset((page-1)*page_size).limit(page_size))
    customers = result.scalars().all()
    if current_user.role == Role.SUPERVISOR:
        return {"data":[{"id":c.id,"warehouse_id":c.warehouse_id,"customer_code":c.customer_code,
                         "company_name":c.company_name,"cargo_type":c.cargo_type,"logistics_channel":c.logistics_channel} for c in customers],
                "total":len(customers),"page":page,"page_size":page_size,"scope":"onsite_lookup"}
    can_read_finance = current_user.role == Role.WAREHOUSE_ADMIN or any(p in (current_user.extra_permissions or []) for p in (_PERMISSION,MENU_PERMISSIONS_BY_KEY['credit'].label))
    balances = await positions(db,scope,[c.id for c in customers]) if can_read_finance else {}
    reviews = await legacy_review(db,scope,[c.id for c in customers]) if can_read_finance else {}
    return {
        "data": [{"id": c.id, "warehouse_id": c.warehouse_id, "customer_code": c.customer_code,
                  "company_name": c.company_name, "contact_person": c.contact_person,
                  "contact_info": c.contact_info, "line_id": c.line_id,
                  "cargo_type": c.cargo_type, "logistics_channel": c.logistics_channel,
                  "total_shipments": c.total_shipments or 0, "total_shipping_cost": c.total_shipping_cost or 0,
                  "last_ship_date": c.last_ship_date.isoformat() if c.last_ship_date else None,
                  "default_currency": c.default_currency or "THB", "default_payment_method": c.default_payment_method,
                  "credit_status": c.credit_status, "credit_limit": c.credit_limit,
                  "debt_amount": c.debt_amount or 0, "legacy_debt_amount": c.debt_amount or 0,
                  **({'receivables': balances.get(c.id,{c.default_currency or 'THB':empty_position(c.id,c.default_currency or 'THB')}), 'review_items': reviews.get(c.id,[]), 'needs_review':bool(reviews.get(c.id))} if can_read_finance else {}),
                  "remark": c.remark, "tags": c.tags,
                  "created_at": c.created_at.isoformat() if c.created_at else None} for c in customers],
        "total": total, "page": page, "page_size": page_size,
    }

@router.post("")
async def create_customer(req: CustomerCreate, current_user: User = Depends(check_staff_permission(_PERMISSION)),
                          db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if current_user.role not in (Role.SUPER_ADMIN, Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
        raise HTTPException(403, "无权限")
    wh_id = get_wh_id(current_user)
    if current_user.role == Role.SUPER_ADMIN:
        wh_id = req.warehouse_id
    if wh_id is None:
        raise HTTPException(400, "无法确定所属仓库，请联系管理员分配仓库")
    c = Customer(warehouse_id=wh_id, **{k:v for k,v in req.model_dump().items() if k != "warehouse_id"})
    db.add(c); await db.flush(); return {"id": c.id, "message": "创建成功"}

@router.get("/{customer_id}", dependencies=[Depends(require_non_labor)])
async def get_customer(customer_id: int, current_user: User = Depends(check_staff_permission(_PERMISSION)), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Customer).where(Customer.id == customer_id))
    c = result.scalar_one_or_none()
    if not c: raise HTTPException(404, "客户不存在")
    if current_user.role != Role.SUPER_ADMIN and c.warehouse_id not in get_wh_ids(current_user):
        raise HTTPException(403, "无权查看其他仓库的客户")
    if current_user.role == Role.SUPERVISOR:
        return {"id":c.id,"warehouse_id":c.warehouse_id,"customer_code":c.customer_code,"company_name":c.company_name,
                "cargo_type":c.cargo_type,"logistics_channel":c.logistics_channel}
    return {"id": c.id, "warehouse_id": c.warehouse_id, "customer_code": c.customer_code,
            "company_name": c.company_name, "contact_person": c.contact_person,
            "contact_info": c.contact_info, "credit_status": c.credit_status,
            "credit_limit": c.credit_limit, "remark": c.remark, "tags": c.tags}

@router.put("/{customer_id}", dependencies=[Depends(require_non_labor)])
async def update_customer(customer_id: int, req: CustomerUpdate,
                          current_user: User = Depends(check_staff_permission(_PERMISSION)),
                          db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    result = await db.execute(select(Customer).where(Customer.id == customer_id))
    c = result.scalar_one_or_none()
    if not c: raise HTTPException(404, "客户不存在")
    if current_user.role != Role.SUPER_ADMIN and c.warehouse_id not in get_wh_ids(current_user):
        raise HTTPException(403, "无权限")
    for k, v in req.model_dump(exclude_unset=True).items():
        setattr(c, k, v)
    await db.flush(); return {"message": "更新成功"}

@router.delete("/{customer_id}")
async def delete_customer(customer_id: int, current_user: User = Depends(check_staff_permission(_PERMISSION)),
                          db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if current_user.role not in (Role.SUPER_ADMIN, Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
        raise HTTPException(403, "无权限")
    result = await db.execute(select(Customer).where(Customer.id == customer_id))
    c = result.scalar_one_or_none()
    if not c: raise HTTPException(404, "客户不存在")
    if current_user.role != Role.SUPER_ADMIN and c.warehouse_id not in get_wh_ids(current_user):
        raise HTTPException(403, "只能删除自己仓库的客户")
    await db.delete(c); await db.flush(); return {"message": "删除成功"}

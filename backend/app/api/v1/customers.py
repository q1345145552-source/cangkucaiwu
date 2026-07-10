from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from app.database import get_db
from app.models.customer import Customer
from app.models.user import User
from app.core.permissions import get_current_user, get_wh_id, get_wh_ids, Role
from app.schemas.business import CustomerCreate, CustomerUpdate

router = APIRouter()

@router.get("")
async def list_customers(
    page: int = 1, page_size: int = 20, search: str = None,
    credit_status: str = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    query = select(Customer); count_q = select(func.count(Customer.id))
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
    return {
        "data": [{"id": c.id, "warehouse_id": c.warehouse_id, "customer_code": c.customer_code,
                  "company_name": c.company_name, "contact_person": c.contact_person,
                  "contact_info": c.contact_info, "line_id": c.line_id,
                  "cargo_type": c.cargo_type, "logistics_channel": c.logistics_channel,
                  "total_shipments": c.total_shipments or 0, "total_shipping_cost": c.total_shipping_cost or 0,
                  "last_ship_date": c.last_ship_date.isoformat() if c.last_ship_date else None,
                  "default_currency": c.default_currency or "THB", "default_payment_method": c.default_payment_method,
                  "credit_status": c.credit_status, "credit_limit": c.credit_limit,
                  "debt_amount": c.debt_amount or 0, "remark": c.remark, "tags": c.tags,
                  "created_at": c.created_at.isoformat() if c.created_at else None} for c in customers],
        "total": total, "page": page, "page_size": page_size,
    }

@router.post("")
async def create_customer(req: CustomerCreate, current_user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if current_user.role not in (Role.SUPER_ADMIN, Role.WAREHOUSE_ADMIN):
        raise HTTPException(403, "无权限")
    wh_id = get_wh_id(current_user)
    if current_user.role == Role.SUPER_ADMIN:
        wh_id = req.warehouse_id
    if wh_id is None:
        raise HTTPException(400, "无法确定所属仓库，请联系管理员分配仓库")
    c = Customer(warehouse_id=wh_id, **{k:v for k,v in req.model_dump().items() if k != "warehouse_id"})
    db.add(c); await db.flush(); return {"id": c.id, "message": "创建成功"}

@router.get("/{customer_id}")
async def get_customer(customer_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Customer).where(Customer.id == customer_id))
    c = result.scalar_one_or_none()
    if not c: raise HTTPException(404, "客户不存在")
    return {"id": c.id, "warehouse_id": c.warehouse_id, "customer_code": c.customer_code,
            "company_name": c.company_name, "contact_person": c.contact_person,
            "contact_info": c.contact_info, "credit_status": c.credit_status,
            "credit_limit": c.credit_limit, "remark": c.remark, "tags": c.tags}

@router.put("/{customer_id}")
async def update_customer(customer_id: int, req: CustomerUpdate,
                          current_user: User = Depends(get_current_user),
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
async def delete_customer(customer_id: int, current_user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if current_user.role not in (Role.SUPER_ADMIN, Role.WAREHOUSE_ADMIN):
        raise HTTPException(403, "无权限")
    result = await db.execute(select(Customer).where(Customer.id == customer_id))
    c = result.scalar_one_or_none()
    if not c: raise HTTPException(404, "客户不存在")
    if current_user.role != Role.SUPER_ADMIN and c.warehouse_id not in get_wh_ids(current_user):
        raise HTTPException(403, "只能删除自己仓库的客户")
    await db.delete(c); await db.flush(); return {"message": "删除成功"}

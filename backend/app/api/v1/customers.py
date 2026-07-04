from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from app.database import get_db
from app.models.customer import Customer
from app.models.user import User
from app.core.permissions import get_current_user, Role
from app.schemas.business import CustomerCreate, CustomerUpdate

router = APIRouter()

@router.get("")
async def list_customers(
    page: int = 1, page_size: int = 20, search: str = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(Customer); count_q = select(func.count(Customer.id))
    if current_user.role != Role.SUPER_ADMIN:
        query = query.where(Customer.warehouse_id == current_user.warehouse_id)
        count_q = count_q.where(Customer.warehouse_id == current_user.warehouse_id)
    if search:
        filt = or_(Customer.company_name.ilike(f"%{search}%"), Customer.customer_code.ilike(f"%{search}%"))
        query = query.where(filt); count_q = count_q.where(filt)
    total = (await db.execute(count_q)).scalar()
    result = await db.execute(query.order_by(Customer.created_at.desc()).offset((page-1)*page_size).limit(page_size))
    customers = result.scalars().all()
    return {
        "data": [{"id": c.id, "warehouse_id": c.warehouse_id, "customer_code": c.customer_code,
                  "company_name": c.company_name, "contact_person": c.contact_person,
                  "contact_info": c.contact_info, "credit_status": c.credit_status,
                  "credit_limit": c.credit_limit, "remark": c.remark, "tags": c.tags,
                  "created_at": c.created_at.isoformat() if c.created_at else None} for c in customers],
        "total": total, "page": page, "page_size": page_size,
    }

@router.post("")
async def create_customer(req: CustomerCreate, current_user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    if current_user.role not in (Role.SUPER_ADMIN, Role.WAREHOUSE_ADMIN):
        raise HTTPException(403, "无权限")
    wh_id = current_user.warehouse_id
    if current_user.role == Role.SUPER_ADMIN:
        wh_id = req.warehouse_id or 1
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
    result = await db.execute(select(Customer).where(Customer.id == customer_id))
    c = result.scalar_one_or_none()
    if not c: raise HTTPException(404, "客户不存在")
    if current_user.role != Role.SUPER_ADMIN and c.warehouse_id != current_user.warehouse_id:
        raise HTTPException(403, "无权限")
    for k, v in req.model_dump(exclude_unset=True).items():
        setattr(c, k, v)
    await db.flush(); return {"message": "更新成功"}

@router.delete("/{customer_id}")
async def delete_customer(customer_id: int, current_user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    if current_user.role != Role.SUPER_ADMIN:
        raise HTTPException(403, "仅超级管理员可删除")
    result = await db.execute(select(Customer).where(Customer.id == customer_id))
    c = result.scalar_one_or_none()
    if not c: raise HTTPException(404, "客户不存在")
    await db.delete(c); await db.flush(); return {"message": "删除成功"}

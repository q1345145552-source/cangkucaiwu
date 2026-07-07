from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.warehouse import Warehouse
from app.models.user import User
from app.models.user_warehouse import UserWarehouse
from app.core.permissions import get_current_user, require_role, Role
from app.schemas.business import WarehouseCreate, WarehouseUpdate

router = APIRouter()

@router.get("")
async def list_warehouses(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        result = await db.execute(select(Warehouse).order_by(Warehouse.id))
        whs = result.scalars().all()
        return {"data": [{"id": w.id, "name": w.name, "name_th": w.name_th, "code": w.code,
                          "address": w.address, "is_active": w.is_active} for w in whs]}

    result = await db.execute(
        select(Warehouse).join(UserWarehouse, UserWarehouse.warehouse_id == Warehouse.id)
        .where(UserWarehouse.user_id == current_user.id)
        .order_by(Warehouse.id)
    )
    whs = result.scalars().all()
    return {"data": [{"id": w.id, "name": w.name, "name_th": w.name_th, "code": w.code,
                      "address": w.address, "is_active": w.is_active} for w in whs]}

@router.post("")
async def create_warehouse(req: WarehouseCreate,
                           current_user: User = Depends(get_current_user),
                           db: AsyncSession = Depends(get_db)):
    if current_user.role not in (Role.SUPER_ADMIN, Role.WAREHOUSE_ADMIN):
        raise HTTPException(403, "无权限创建仓库")

    w = Warehouse(**req.model_dump(), created_by=current_user.id)
    db.add(w)
    await db.flush()

    uw = UserWarehouse(user_id=current_user.id, warehouse_id=w.id)
    db.add(uw)
    await db.flush()

    return {"id": w.id, "message": "创建成功"}

@router.put("/{warehouse_id}")
async def update_warehouse(warehouse_id: int, req: WarehouseUpdate,
                           current_user: User = Depends(get_current_user),
                           db: AsyncSession = Depends(get_db)):
    if current_user.role not in (Role.SUPER_ADMIN, Role.WAREHOUSE_ADMIN):
        raise HTTPException(403, "无权限更新仓库")

    if current_user.role == Role.WAREHOUSE_ADMIN:
        result = await db.execute(
            select(UserWarehouse).where(
                UserWarehouse.user_id == current_user.id,
                UserWarehouse.warehouse_id == warehouse_id
            )
        )
        if not result.scalar_one_or_none():
            raise HTTPException(403, "无权限操作该仓库")

    result = await db.execute(select(Warehouse).where(Warehouse.id == warehouse_id))
    w = result.scalar_one_or_none()
    if not w:
        raise HTTPException(404, "仓库不存在")
    for k, v in req.model_dump(exclude_unset=True).items():
        setattr(w, k, v)
    await db.flush()
    return {"message": "更新成功"}

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.warehouse import Warehouse
from app.models.user import User, Role
from app.core.permissions import get_current_user, get_wh_id, require_role
from app.schemas.business import WarehouseCreate, WarehouseUpdate, WarehouseResponse

router = APIRouter()

@router.get("")
async def list_warehouses(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if current_user.role != Role.SUPER_ADMIN:
        wh = (await db.execute(select(Warehouse).where(Warehouse.id == get_wh_id(current_user)))).scalar_one_or_none()
        wh_name = wh.name if wh else ""
        return {"data": [{"id": get_wh_id(current_user), "name": wh_name, "code": ""}]}
    result = await db.execute(select(Warehouse).order_by(Warehouse.id))
    whs = result.scalars().all()
    return {"data": [{"id": w.id, "name": w.name, "name_th": w.name_th, "code": w.code, "address": w.address, "is_active": w.is_active} for w in whs]}

@router.post("")
async def create_warehouse(req: WarehouseCreate, current_user: User = Depends(require_role(Role.SUPER_ADMIN)),
                           db: AsyncSession = Depends(get_db)):
    w = Warehouse(**req.model_dump())
    db.add(w); await db.flush(); return {"id": w.id, "message": "创建成功"}

@router.put("/{warehouse_id}")
async def update_warehouse(warehouse_id: int, req: WarehouseUpdate,
                           _: User = Depends(require_role(Role.SUPER_ADMIN)),
                           db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Warehouse).where(Warehouse.id == warehouse_id))
    w = result.scalar_one_or_none()
    if not w: raise HTTPException(404, "仓库不存在")
    for k, v in req.model_dump(exclude_unset=True).items():
        setattr(w, k, v)
    await db.flush(); return {"message": "更新成功"}

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.database import get_db
from app.models.user import User
from app.models.user_warehouse import UserWarehouse
from app.models.warehouse import Warehouse
from app.core.security import hash_password, verify_password, create_access_token
from app.core.permissions import get_current_user
from app.schemas.auth import LoginRequest, TokenResponse, ChangePasswordRequest

router = APIRouter()

def _build_warehouses_list(db_result) -> list:
    warehouses = []
    seen = set()
    for uw, wh in db_result:
        if wh and wh.id not in seen:
            seen.add(wh.id)
            warehouses.append({"id": wh.id, "name": wh.name, "code": wh.code})
    return warehouses

@router.post("/login")
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(User).options(selectinload(User.warehouse)).where(User.username == req.username)
    )
    user = result.scalar_one_or_none()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已被禁用")

    token = create_access_token(data={"sub": str(user.id), "role": str(user.role)})
    warehouse_name = user.warehouse.name if user.warehouse else None

    uw_result = await db.execute(
        select(UserWarehouse, Warehouse)
        .join(Warehouse, UserWarehouse.warehouse_id == Warehouse.id)
        .where(UserWarehouse.user_id == user.id)
    )
    warehouses = _build_warehouses_list(uw_result.all())

    return {
        "access_token": token,
        "token_type": "bearer",
        "user_id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "role": str(user.role),
        "warehouse_id": user.warehouse_id,
        "warehouse_name": warehouse_name,
        "warehouses": warehouses,
        "extra_permissions": user.extra_permissions or [],
    }

@router.get("/me")
async def get_me(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    uw_result = await db.execute(
        select(UserWarehouse, Warehouse)
        .join(Warehouse, UserWarehouse.warehouse_id == Warehouse.id)
        .where(UserWarehouse.user_id == current_user.id)
    )
    warehouses = _build_warehouses_list(uw_result.all())

    return {
        "id": current_user.id,
        "username": current_user.username,
        "display_name": current_user.display_name,
        "role": str(current_user.role),
        "warehouse_id": current_user.warehouse_id,
        "warehouse_name": current_user.warehouse.name if current_user.warehouse else None,
        "warehouses": warehouses,
        "is_active": current_user.is_active,
        "extra_permissions": current_user.extra_permissions or [],
    }

@router.post("/change-password")
async def change_password(
    req: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not verify_password(req.old_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="原密码错误")
    current_user.password_hash = hash_password(req.new_password)
    await db.flush()
    return {"message": "密码修改成功"}

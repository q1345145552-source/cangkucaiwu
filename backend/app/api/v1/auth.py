from app.core.action_access import access_description, legacy_labels
from app.core.employee_access import own_employee
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from pydantic import BaseModel
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


class AttachmentSession(BaseModel):
    clear: bool = False


@router.post("/attachment-session")
async def attachment_session(req: AttachmentSession, request: Request, response: Response,
    user=Depends(get_current_user)):
    """Only existing image/file requests may use this HttpOnly cookie; API writes still require Bearer."""
    import time
    from app.api.secure_uploads import COOKIE
    from app.core.security import decode_token
    if req.clear:
        response.delete_cookie(COOKIE,path="/uploads")
    else:
        token = request.headers["Authorization"][7:]
        payload = decode_token(token)
        response.set_cookie(COOKIE,token,httponly=True,samesite="lax",path="/uploads",
            secure=request.url.scheme=="https",max_age=max(0,int(payload["exp"]-time.time())))
    return {"ok":True}

def _build_warehouses_list(db_result) -> list:
    warehouses = []
    seen = set()
    for uw, wh in db_result:
        if wh and wh.id not in seen:
            seen.add(wh.id)
            warehouses.append({"id": wh.id, "name": wh.name, "code": wh.code})
    return warehouses

@router.post("/login")
async def login(req: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
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

    employee = await own_employee(db, user)
    request.state.audit_login_user_id = user.id
    request.state.audit_login_warehouse_id = user.warehouse_id
    return {
        "access_token": token,
        "token_type": "bearer",
        "user_id": user.id,
        "self_employee_id": employee.id if employee else None,
        "username": user.username,
        "display_name": user.display_name,
        "role": str(user.role),
        "warehouse_id": user.warehouse_id,
        "warehouse_name": warehouse_name,
        "warehouses": warehouses,
        "extra_permissions": legacy_labels(user),
        "action_access": access_description(user),
        "attendance_enabled": bool(user.attendance_enabled),
        "attendance_employee_id": user.attendance_employee_id,
    }

@router.get("/me")
async def get_me(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    # Fetch warehouse list
    uw_result = await db.execute(
        select(UserWarehouse, Warehouse)
        .join(Warehouse, UserWarehouse.warehouse_id == Warehouse.id)
        .where(UserWarehouse.user_id == current_user.id)
    )
    warehouses = _build_warehouses_list(uw_result.all())

    # Get warehouse name from the first warehouse in list
    wh_name = warehouses[0]["name"] if warehouses else None
    employee = await own_employee(db, current_user)

    return {
        "id": current_user.id,
        "self_employee_id": employee.id if employee else None,
        "username": current_user.username,
        "display_name": current_user.display_name,
        "role": str(current_user.role),
        "warehouse_id": current_user.warehouse_id,
        "warehouse_name": wh_name,
        "warehouses": warehouses,
        "is_active": current_user.is_active,
        "extra_permissions": legacy_labels(current_user),
        "action_access": access_description(current_user),
        "attendance_enabled": bool(current_user.attendance_enabled),
        "attendance_employee_id": current_user.attendance_employee_id,
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

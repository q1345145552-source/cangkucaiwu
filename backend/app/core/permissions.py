from enum import Enum
from typing import List, Optional
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.core.security import decode_token

security_scheme = HTTPBearer()

class Role(str, Enum):
    SUPER_ADMIN = "super_admin"
    WAREHOUSE_ADMIN = "warehouse_admin"
    STAFF = "staff"

ROLE_HIERARCHY = {
    Role.SUPER_ADMIN: 3,
    Role.WAREHOUSE_ADMIN: 2,
    Role.STAFF: 1,
}

STAFF_PERMISSIONS = {
    "到账流水": "到账流水",
    "备用金管理": "备用金管理",
    "报销管理": "报销管理",
    "收付款管理": "收付款管理",
    "账期管理": "账期管理",
    "操作日志": "操作日志",
    "供应商管理": "供应商管理",
    "其他收支": "其他收支",
}

def check_staff_permission(perm_key: str):
    async def dependency(current_user = Depends(get_current_user)):
        if current_user.role == Role.STAFF:
            perms = current_user.extra_permissions or []
            if perm_key not in perms:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"无此操作权限，需要: {STAFF_PERMISSIONS.get(perm_key, perm_key)}"
                )
        return current_user
    return dependency

async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
    db: AsyncSession = Depends(get_db),
):
    from app.models.user import User
    from app.models.user_warehouse import UserWarehouse
    payload = decode_token(credentials.credentials)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    try:
        uid = int(user_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token: user_id must be numeric")
    result = await db.execute(select(User).where(User.id == uid))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")

    # Load user's accessible warehouse IDs
    uw_result = await db.execute(
        select(UserWarehouse.warehouse_id).where(UserWarehouse.user_id == uid)
    )
    wh_ids = [r for r in uw_result.scalars().all()]
    if not wh_ids and user.warehouse_id:
        wh_ids = [user.warehouse_id]
    user._warehouse_ids = wh_ids

    # Determine active warehouse from X-Warehouse-ID header
    if user.role != Role.SUPER_ADMIN:
        wh_header = request.headers.get("X-Warehouse-ID")
        active_wh = None
        if wh_header:
            if wh_header == "all" and user.role == Role.WAREHOUSE_ADMIN:
                user._all_warehouses = True
                user._all_warehouse_ids = wh_ids
                active_wh = None
            else:
                try:
                    wh_int = int(wh_header)
                    if wh_int in wh_ids:
                        active_wh = wh_int
                except ValueError:
                    pass
        if active_wh is None and wh_ids and not getattr(user, '_all_warehouses', False):
            active_wh = wh_ids[0]
        user._active_wh_id = active_wh
    else:
        user._active_wh_id = user.warehouse_id

    return user


def get_wh_id(user) -> int | None:
    """Returns a single warehouse_id for CREATE operations. Uses header-selected warehouse first."""
    wh = getattr(user, '_active_wh_id', None) or user.warehouse_id
    if wh is None:
        ids = get_wh_ids(user)
        if ids:
            return ids[0]
    return wh


def get_wh_ids(user) -> list:
    """Returns list of accessible warehouse IDs. In 'all' mode returns all user's warehouse IDs.
    Always returns a list, never None. Safe for .in_() queries."""
    _all = getattr(user, '_all_warehouse_ids', None)
    if _all:
        return _all
    wh = get_wh_id(user)
    return [wh] if wh else []

def require_role(*roles: Role):
    async def dependency(current_user = Depends(get_current_user)):
        if current_user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return current_user
    return dependency

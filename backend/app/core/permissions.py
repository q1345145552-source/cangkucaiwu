from enum import Enum
from typing import List
from fastapi import Depends, HTTPException, status
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

# Available extra permissions for staff
STAFF_PERMISSIONS = {
    "incoming_entry": "录入到账流水",
    "approve_expense_fund": "审批备用金",
    "approve_reimbursement": "审批报销",
    "confirm_income": "确认入账",
    "confirm_expense": "确认出账",
    "manage_credit": "管理账期",
    "operation_log": "查看操作日志",
}

def check_staff_permission(perm_key: str):
    """Returns a FastAPI dependency that checks if the current staff user has the given extra permission.
    Warehouse admins and super admins pass through automatically.
    """
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
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
    db: AsyncSession = Depends(get_db),
):
    from app.models.user import User
    payload = decode_token(credentials.credentials)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")
    return user

def require_role(*roles: Role):
    async def dependency(current_user = Depends(get_current_user)):
        if current_user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return current_user
    return dependency

def require_warehouse_access():
    """SuperAdmin sees all; others only see their own warehouse."""
    async def dependency(
        current_user = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
        warehouse_id: int = None,
    ):
        if current_user.role == Role.SUPER_ADMIN:
            return current_user
        if warehouse_id and current_user.warehouse_id != warehouse_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot access other warehouse data")
        return current_user
    return dependency

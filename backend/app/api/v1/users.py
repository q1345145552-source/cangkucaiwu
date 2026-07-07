from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from app.database import get_db
from app.models.user import User
from app.models.user_warehouse import UserWarehouse
from app.models.warehouse import Warehouse
from app.core.security import hash_password
from app.core.permissions import get_current_user, require_role, Role, STAFF_PERMISSIONS
from app.schemas.user import UserCreate, UserUpdate, UserResponse

router = APIRouter()

@router.get("", response_model=dict)
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    role: str | None = None,
    warehouse_id: int | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(User).options(selectinload(User.warehouse))
    count_query = select(func.count(User.id))

    # Non-superadmin can only see users in warehouses they manage
    if current_user.role != Role.SUPER_ADMIN:
        managed_wh_ids = (await db.execute(
            select(UserWarehouse.warehouse_id).where(UserWarehouse.user_id == current_user.id)
        )).scalars().all()
        managed_wh_ids = list(managed_wh_ids) if managed_wh_ids else []
        if managed_wh_ids:
            # Find all user_ids in managed warehouses via the association table
            user_ids_subq = select(UserWarehouse.user_id).where(UserWarehouse.warehouse_id.in_(managed_wh_ids))
            query = query.where(
                User.id.in_(user_ids_subq) | (User.id == current_user.id)
            )
            count_query = count_query.where(
                User.id.in_(user_ids_subq) | (User.id == current_user.id)
            )
        else:
            # New warehouse_admin with no warehouses yet - show only self
            query = query.where(User.id == current_user.id)
            count_query = count_query.where(User.id == current_user.id)

    if role:
        query = query.where(User.role == role)
        count_query = count_query.where(User.role == role)
    if warehouse_id and current_user.role == Role.SUPER_ADMIN:
        query = query.where(User.warehouse_id == warehouse_id)
        count_query = count_query.where(User.warehouse_id == warehouse_id)

    total = (await db.execute(count_query)).scalar()
    result = await db.execute(
        query.order_by(User.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    users = result.scalars().all()

    return {
        "data": [
            {
                "id": u.id, "username": u.username, "display_name": u.display_name,
                "role": u.role,
                "warehouse_id": u.warehouse_id,
                "warehouse_name": u.warehouse.name if u.warehouse else None,
                "extra_permissions": u.extra_permissions or [],
                "is_active": u.is_active,
                "created_at": u.created_at.isoformat() if u.created_at else None,
            }
            for u in users
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }

@router.get("/permissions")
async def list_available_permissions():
    """Return all available staff extra permissions."""
    return [{"key": k, "label": v} for k, v in STAFF_PERMISSIONS.items()]

@router.post("")
async def create_user(
    req: UserCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Role hierarchy check: can only create users with lower role
    from app.core.permissions import ROLE_HIERARCHY
    if ROLE_HIERARCHY.get(current_user.role, 0) <= ROLE_HIERARCHY.get(req.role, 0):
        raise HTTPException(status_code=403, detail="无法创建同级别或更高级别用户")

    # Check username uniqueness
    existing = (await db.execute(select(User).where(User.username == req.username))).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="用户名已存在")

    # warehouse_admin role: no warehouse needed (they create their own later)
    if req.role == Role.WAREHOUSE_ADMIN:
        req.warehouse_id = None
    else:
        # Non-superadmin: validate warehouse_id against managed warehouses
        if current_user.role != Role.SUPER_ADMIN:
            if req.warehouse_id is not None:
                uw_check = (await db.execute(
                    select(UserWarehouse).where(
                        UserWarehouse.user_id == current_user.id,
                        UserWarehouse.warehouse_id == req.warehouse_id,
                    )
                )).scalar_one_or_none()
                if not uw_check:
                    raise HTTPException(status_code=403, detail="无权限将用户分配到该仓库")
            else:
                req.warehouse_id = current_user.warehouse_id

        # staff MUST have a warehouse_id
        if req.role == Role.STAFF and req.warehouse_id is None:
            raise HTTPException(status_code=400, detail="创建员工时必须指定所属仓库")

    user = User(
        username=req.username,
        password_hash=hash_password(req.password),
        display_name=req.display_name,
        role=req.role,
        warehouse_id=req.warehouse_id,
        created_by=current_user.id,
    )
    db.add(user)
    await db.flush()

    if user.warehouse_id:
        uw = UserWarehouse(user_id=user.id, warehouse_id=user.warehouse_id)
        db.add(uw)
        await db.flush()

    return {"id": user.id, "message": "用户创建成功"}

@router.put("/{user_id}")
async def update_user(
    user_id: int,
    req: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    # Permission check: super_admin can edit anyone, warehouse_admin can only edit own managed warehouse users
    if current_user.role != Role.SUPER_ADMIN:
        if current_user.role != Role.WAREHOUSE_ADMIN:
            raise HTTPException(status_code=403, detail="无权限编辑用户")
        # Check if user is in a warehouse managed by current_user
        managed_wh_ids = (await db.execute(
            select(UserWarehouse.warehouse_id).where(UserWarehouse.user_id == current_user.id)
        )).scalars().all()
        managed_wh_ids = [w for w in managed_wh_ids] if managed_wh_ids else []
        if not managed_wh_ids or user.warehouse_id not in managed_wh_ids:
            raise HTTPException(status_code=403, detail="只能编辑自己仓库的用户")
        # warehouse_admin can only edit staff users
        if user.role != Role.STAFF.value:
            raise HTTPException(status_code=403, detail="只能编辑staff角色的用户")
        # warehouse_admin can only set extra_permissions, not change role
        if req.role is not None and req.role != user.role:
            raise HTTPException(status_code=403, detail="无权修改用户角色")

    if req.display_name is not None:
        user.display_name = req.display_name
    if req.role is not None:
        user.role = req.role
    if req.warehouse_id is not None:
        user.warehouse_id = req.warehouse_id
    if req.is_active is not None:
        user.is_active = req.is_active
    if req.line_user_id is not None:
        user.line_user_id = req.line_user_id
    if req.extra_permissions is not None:
        user.extra_permissions = req.extra_permissions

    await db.flush()
    return {"message": "用户更新成功"}

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.models.user import User
from app.models.warehouse import Warehouse
from app.core.security import hash_password
from app.core.permissions import get_current_user, require_role, Role
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
    query = select(User)
    count_query = select(func.count(User.id))

    # Non-superadmin can only see users in their warehouse or created by them
    if current_user.role != Role.SUPER_ADMIN:
        query = query.where(User.warehouse_id == current_user.warehouse_id)
        count_query = count_query.where(User.warehouse_id == current_user.warehouse_id)

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
                "is_active": u.is_active,
                "created_at": u.created_at.isoformat() if u.created_at else None,
            }
            for u in users
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }

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

    # Non-superadmin can only create users in their own warehouse
    if current_user.role != Role.SUPER_ADMIN:
        req.warehouse_id = current_user.warehouse_id

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

    if current_user.role != Role.SUPER_ADMIN and user.warehouse_id != current_user.warehouse_id:
        raise HTTPException(status_code=403, detail="无权限")

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

    await db.flush()
    return {"message": "用户更新成功"}

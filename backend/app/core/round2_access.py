"""Explicit role ceilings for account/rule writes; menu grants never override these."""
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from app.database import get_db
from app.core.permissions import get_current_user, Role, get_wh_ids
from app.models.warehouse import Warehouse
from app.services.warehouse_summary import warehouse_scope


def require_account_manager(user, *, platform=False):
    allowed = (Role.WAREHOUSE_ADMIN, Role.SUPER_ADMIN) if platform else (Role.WAREHOUSE_ADMIN,)
    if user.role not in allowed:
        raise HTTPException(403, "只有仓库管理员可以管理账号或账户配置")


async def mutation_scope(request: Request, user=Depends(get_current_user), db=Depends(get_db)):
    # Preserve platform-only user management; do not expand super-admin business access.
    if user.role == Role.SUPER_ADMIN:
        return user
    header = request.headers.get('X-Warehouse-ID')
    if header is not None:
        rows = await warehouse_scope(db, user, header)
        ids = [w.id for w in rows]
    else:
        ids = list((await db.execute(select(Warehouse.id).where(
            Warehouse.id.in_(get_wh_ids(user)), Warehouse.is_active.is_(True)))).scalars())
    if not ids:
        raise HTTPException(403, '无权操作所选仓库')
    user._mutation_warehouse_ids = ids
    return user


def mutation_ids(user):
    return getattr(user, '_mutation_warehouse_ids', get_wh_ids(user))


def own_scope(user, warehouse_id):
    if user.role != Role.SUPER_ADMIN and warehouse_id not in mutation_ids(user):
        raise HTTPException(403, '无权操作该仓库')

async def login_target_scope(db, user, target):
    """An account spanning unauthorized warehouses cannot be managed through its primary warehouse."""
    from app.models.user_warehouse import UserWarehouse
    from app.core.permissions import ROLE_HIERARCHY
    if user.role == Role.SUPER_ADMIN:
        return
    own_scope(user, target.warehouse_id)
    if ROLE_HIERARCHY.get(target.role, 0) >= ROLE_HIERARCHY.get(user.role, 0):
        raise HTTPException(403, '不能管理同级或更高角色登录账号')
    for wid in (await db.execute(select(UserWarehouse.warehouse_id).where(UserWarehouse.user_id == target.id))).scalars():
        own_scope(user, wid)

"""Owner-approved platform publication, separate from warehouse business management."""
from fastapi import HTTPException
from app.core.permissions import Role
from app.models.warehouse import Warehouse


async def publication_warehouse(db, user, warehouse_id=None):
    """Keep the existing source-warehouse field; shared visibility never depends on this ID."""
    if user.role != Role.SUPER_ADMIN:
        raise HTTPException(403, "只有超级管理员可以发布和管理跨仓内容")
    wid = warehouse_id or user.warehouse_id
    warehouse = await db.get(Warehouse, wid) if wid else None
    if not warehouse or not warehouse.is_active:
        raise HTTPException(400, "请选择有效的发布来源仓库")
    return warehouse.id

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime
from app.database import get_db
from app.models.data_change_history import DataChangeHistory
from app.core.permissions import get_current_user, get_wh_ids, Role

router = APIRouter()


@router.get("/operators")
async def list_operators(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """返回有历史记录的操作人列表（供筛选下拉使用）。"""
    if current_user.role not in (Role.SUPER_ADMIN, Role.WAREHOUSE_ADMIN):
        raise HTTPException(403, "无权限")
    query = select(DataChangeHistory.operator_id, DataChangeHistory.operator_name)
    if current_user.role != Role.SUPER_ADMIN:
        query = query.where(DataChangeHistory.warehouse_id.in_(get_wh_ids(current_user)))
    query = query.distinct()
    rows = (await db.execute(query)).all()
    return {"data": [{"operator_id": r[0], "operator_name": r[1] or "-"} for r in rows if r[0] is not None]}


@router.get("")
async def list_history(
    module: str = None,
    record_id: int = None,
    operation_type: str = None,
    operator_id: int = None,
    start_date: str = None,
    end_date: str = None,
    page: int = 1,
    page_size: int = 20,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """查询数据修改历史（管理员可见本仓库/名下仓库的历史）。"""
    if current_user.role not in (Role.SUPER_ADMIN, Role.WAREHOUSE_ADMIN):
        raise HTTPException(403, "无权限")

    query = select(DataChangeHistory)
    count_q = select(func.count(DataChangeHistory.id))
    if current_user.role != Role.SUPER_ADMIN:
        query = query.where(DataChangeHistory.warehouse_id.in_(get_wh_ids(current_user)))
        count_q = count_q.where(DataChangeHistory.warehouse_id.in_(get_wh_ids(current_user)))
    if module:
        query = query.where(DataChangeHistory.module == module)
        count_q = count_q.where(DataChangeHistory.module == module)
    if record_id:
        query = query.where(DataChangeHistory.record_id == record_id)
        count_q = count_q.where(DataChangeHistory.record_id == record_id)
    if operation_type:
        query = query.where(DataChangeHistory.operation_type == operation_type)
        count_q = count_q.where(DataChangeHistory.operation_type == operation_type)
    if operator_id:
        query = query.where(DataChangeHistory.operator_id == operator_id)
        count_q = count_q.where(DataChangeHistory.operator_id == operator_id)
    if start_date:
        start_d = datetime.strptime(start_date, "%Y-%m-%d").date()
        query = query.where(func.date(DataChangeHistory.created_at) >= start_d)
        count_q = count_q.where(func.date(DataChangeHistory.created_at) >= start_d)
    if end_date:
        end_d = datetime.strptime(end_date, "%Y-%m-%d").date()
        query = query.where(func.date(DataChangeHistory.created_at) <= end_d)
        count_q = count_q.where(func.date(DataChangeHistory.created_at) <= end_d)

    total = (await db.execute(count_q)).scalar()
    result = await db.execute(
        query.order_by(DataChangeHistory.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    rows = result.scalars().all()
    return {
        "data": [{
            "id": h.id, "module": h.module, "record_id": h.record_id,
            "operator_id": h.operator_id, "operator_name": h.operator_name,
            "operation_type": h.operation_type,
            "before_data": h.before_data, "after_data": h.after_data,
            "warehouse_id": h.warehouse_id,
            "created_at": h.created_at.isoformat() if h.created_at else None,
        } for h in rows],
        "total": total, "page": page, "page_size": page_size,
    }

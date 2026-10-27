from app.core.round5_access import history_modules, history_values
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime
from app.database import get_db
from app.models.data_change_history import DataChangeHistory
from app.core.permissions import check_staff_permission, get_wh_ids, Role
from app.core.menu_registry import MENU_PERMISSIONS_BY_KEY
from app.core.timezone import thai_now
from fastapi.responses import StreamingResponse
from io import BytesIO
import json

router = APIRouter()


async def history_reader(current_user=Depends(check_staff_permission(MENU_PERMISSIONS_BY_KEY["modification_logs"].label))):
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPER_ADMIN, Role.SUPERVISOR, Role.STAFF):
        raise HTTPException(403, "无此操作权限")
    return current_user


def _history_query(current_user, module=None, record_id=None, operation_type=None, operator_id=None, start_date=None, end_date=None):
    query = select(DataChangeHistory).where(DataChangeHistory.warehouse_id.in_(get_wh_ids(current_user)), DataChangeHistory.module != 'makeup_request')
    modules = history_modules(current_user)
    if modules is not None: query = query.where(DataChangeHistory.module.in_(modules))
    if module:
        query = query.where(DataChangeHistory.module == module)
    if record_id:
        query = query.where(DataChangeHistory.record_id == record_id)
    if operation_type:
        query = query.where(DataChangeHistory.operation_type == operation_type)
    if operator_id:
        query = query.where(DataChangeHistory.operator_id == operator_id)
    if start_date:
        start_d = datetime.strptime(start_date, "%Y-%m-%d").date()
        query = query.where(func.date(DataChangeHistory.created_at) >= start_d)
    if end_date:
        end_d = datetime.strptime(end_date, "%Y-%m-%d").date()
        query = query.where(func.date(DataChangeHistory.created_at) <= end_d)
    return query



@router.get("/operators")
async def list_operators(
    current_user=Depends(history_reader),
    db: AsyncSession = Depends(get_db),
):
    """返回有历史记录的操作人列表（供筛选下拉使用）。"""
    query = select(DataChangeHistory.operator_id, DataChangeHistory.operator_name)
    query = query.where(DataChangeHistory.warehouse_id.in_(get_wh_ids(current_user)))
    query = query.where(DataChangeHistory.module != "makeup_request")
    modules = history_modules(current_user)
    if modules is not None: query = query.where(DataChangeHistory.module.in_(modules))
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
    current_user=Depends(history_reader),
    db: AsyncSession = Depends(get_db),
):
    """查询有权仓库的修改历史；主管/财务须获授修改日志权限。"""

    query = _history_query(current_user, module, record_id, operation_type, operator_id, start_date, end_date)
    count_q = select(func.count()).select_from(query.subquery())
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
            "before_data": history_values(current_user,h.before_data), "after_data": history_values(current_user,h.after_data),
            "warehouse_id": h.warehouse_id,
            "created_at": h.created_at.isoformat() if h.created_at else None,
        } for h in rows],
        "total": total, "page": page, "page_size": page_size,
    }


@router.get("/export")
async def export_history(
    module: str = None, record_id: int = None, operation_type: str = None,
    operator_id: int = None, start_date: str = None, end_date: str = None,
    current_user=Depends(history_reader), db: AsyncSession = Depends(get_db),
):
    from openpyxl import Workbook
    query = _history_query(current_user, module, record_id, operation_type, operator_id, start_date, end_date)
    rows = (await db.execute(query.order_by(DataChangeHistory.created_at.desc()))).scalars().all()
    book = Workbook()
    sheet = book.active
    sheet.title = "修改日志"
    sheet.append(["编号", "模块", "记录编号", "操作人编号", "操作人", "操作类型", "操作时间", "仓库编号", "修改前", "修改后"])
    for row in rows:
        sheet.append([row.id, row.module, row.record_id, row.operator_id, row.operator_name,
                      row.operation_type, row.created_at.isoformat() if row.created_at else "",
                      row.warehouse_id, json.dumps(history_values(current_user,row.before_data), ensure_ascii=False),
                      json.dumps(history_values(current_user,row.after_data), ensure_ascii=False)])
        for cell in sheet[sheet.max_row]:
            if isinstance(cell.value, str):
                cell.data_type = "s"
    output = BytesIO()
    book.save(output)
    output.seek(0)
    return StreamingResponse(output, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="modification_logs_{thai_now():%Y%m%d_%H%M%S}.xlsx"'})

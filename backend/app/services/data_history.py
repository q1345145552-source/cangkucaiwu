"""通用数据修改历史记录。

供各业务模块在新建/编辑/删除后调用，把改动前后数据写入 data_change_history 表。
"""
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.data_change_history import DataChangeHistory


async def record_history(
    db: AsyncSession,
    *,
    module: str,
    record_id: int,
    operator=None,
    operation_type: str,
    before=None,
    after=None,
    warehouse_id=None,
):
    """记录一条修改历史。调用方需自行 flush/commit。

    - module: 模块标识（如 recharge / reimbursement / expense）
    - record_id: 被修改记录的编号
    - operator: 当前操作用户对象（取其 id 与 display_name）
    - operation_type: create / edit / delete
    - before / after: JSON 可序列化的 dict
    """
    db.add(DataChangeHistory(
        module=module,
        record_id=record_id,
        operator_id=operator.id if operator else None,
        operator_name=getattr(operator, "display_name", None) if operator else None,
        operation_type=operation_type,
        before_data=before,
        after_data=after,
        warehouse_id=warehouse_id,
    ))

"""启动时一次性补齐第二轮权限；必须与标记在同一事务中提交。"""
from sqlalchemy import func, insert, select, text, update
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.menu_registry import MENU_PERMISSIONS_BY_KEY
from app.core.permissions import Role
from app.models.expense_fund import SystemSetting
from app.models.user import User
from app.models.warehouse import Warehouse

ROUND2_PERMISSION_MARKER = "menu_perms_round2_recharge_customers_accounts_backfilled_v1"
ROUND2_PERMISSIONS = tuple(
    MENU_PERMISSIONS_BY_KEY[key].label for key in ("recharge", "customers", "accounts")
)


async def backfill_round2_permissions(conn: AsyncConnection) -> int:
    """由调用方管理事务；失败向上抛出，阻止未补权限就启动服务。

    PostgreSQL 事务锁防止多个启动进程同时执行。标记存在就完全跳过，
    因而日后手动撤销权限不会在下次重启时被覆盖。空库尚无仓库时不记标记。
    """
    if conn.dialect.name == "postgresql":
        await conn.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:marker))"),
            {"marker": ROUND2_PERMISSION_MARKER},
        )
    if (await conn.execute(select(SystemSetting.id).where(
        SystemSetting.key == ROUND2_PERMISSION_MARKER
    ))).first():
        return 0

    warehouse_id = (await conn.execute(select(func.min(Warehouse.id)))).scalar_one()
    if warehouse_id is None:
        return 0
    users = (await conn.execute(select(User.id, User.extra_permissions).where(
        User.role.in_((Role.SUPERVISOR.value, Role.STAFF.value))
    ).with_for_update())).all()
    changed = 0
    for user_id, permissions in users:
        existing = permissions or []
        merged = list(dict.fromkeys([*existing, *ROUND2_PERMISSIONS]))
        if merged != existing:
            await conn.execute(update(User).where(User.id == user_id).values(extra_permissions=merged))
            changed += 1
    await conn.execute(insert(SystemSetting).values(
        warehouse_id=warehouse_id, key=ROUND2_PERMISSION_MARKER, value="true",
    ))
    return changed

"""各轮启动补权迁移；每轮权限与标记必须在同一事务中提交。"""
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
ROUND3_PERMISSION_MARKER = "menu_perms_round3_employees_payroll_salary_deduction_backfilled_v1"
ROUND3_PERMISSIONS = tuple(
    MENU_PERMISSIONS_BY_KEY[key].label
    for key in ("employees", "payroll", "salary_templates", "deduction_templates")
)
ROUND4_PERMISSION_MARKER = "menu_perms_round4_attendance_leave_overtime_backfilled_v1"
ROUND4_PERMISSIONS = tuple(
    MENU_PERMISSIONS_BY_KEY[key].label for key in ("attendance", "leave", "overtime")
)
ROUND5_PERMISSION_MARKER = "menu_perms_round5_payable_plans_concentration_group_order_backfilled_v1"
ROUND5_PERMISSIONS = tuple(
    MENU_PERMISSIONS_BY_KEY[key].label
    for key in ("payable", "payment_plans", "concentration", "group_order")
)


async def _backfill_permissions(conn: AsyncConnection, marker: str, permissions_to_add: tuple[str, ...]) -> int:
    """由调用方管理事务；失败向上抛出，阻止未补权限就启动服务。

    PostgreSQL 事务锁防止多个启动进程同时执行。标记存在就完全跳过，
    因而日后手动撤销权限不会在下次重启时被覆盖。空库尚无仓库时不记标记。
    """
    if conn.dialect.name == "postgresql":
        await conn.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:marker))"),
            {"marker": marker},
        )
    if (await conn.execute(select(SystemSetting.id).where(
        SystemSetting.key == marker
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
        merged = list(dict.fromkeys([*existing, *permissions_to_add]))
        if merged != existing:
            await conn.execute(update(User).where(User.id == user_id).values(extra_permissions=merged))
            changed += 1
    await conn.execute(insert(SystemSetting).values(
        warehouse_id=warehouse_id, key=marker, value="true",
    ))
    return changed


async def backfill_round2_permissions(conn: AsyncConnection) -> int:
    return await _backfill_permissions(conn, ROUND2_PERMISSION_MARKER, ROUND2_PERMISSIONS)


async def backfill_round3_permissions(conn: AsyncConnection) -> int:
    return await _backfill_permissions(conn, ROUND3_PERMISSION_MARKER, ROUND3_PERMISSIONS)


async def backfill_round4_permissions(conn: AsyncConnection) -> int:
    return await _backfill_permissions(conn, ROUND4_PERMISSION_MARKER, ROUND4_PERMISSIONS)


async def backfill_round5_permissions(conn: AsyncConnection) -> int:
    return await _backfill_permissions(conn, ROUND5_PERMISSION_MARKER, ROUND5_PERMISSIONS)


async def run_permission_migrations(conn: AsyncConnection) -> dict[str, int]:
    """启动只调用此入口，后续轮次继续在本文件登记；不触碰工资业务数据。"""
    return {
        "round2": await backfill_round2_permissions(conn),
        "round3": await backfill_round3_permissions(conn),
        "round4": await backfill_round4_permissions(conn),
        "round5": await backfill_round5_permissions(conn),
    }

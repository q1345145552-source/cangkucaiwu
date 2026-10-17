"""Configuration writes: callers retain their menu-permission dependency."""
from fastapi import HTTPException
from app.core.permissions import Role


def ensure_config_editor(user):
    if user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if user.role == Role.STAFF:
        raise HTTPException(403, "财务只能查看配置中心")
    if user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
        raise HTTPException(403, "无权限")

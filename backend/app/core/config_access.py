"""Configuration writes: callers retain their menu-permission dependency."""
from fastapi import HTTPException
from app.core.permissions import Role


def ensure_config_editor(user):
    if user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if user.role != Role.WAREHOUSE_ADMIN:
        raise HTTPException(403, "只有仓库管理员可以修改规则设置")

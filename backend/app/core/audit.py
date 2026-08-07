"""审计日志中间件：自动记录所有成功的写操作(POST/PUT/DELETE/PATCH)到 audit_logs 表。

设计要点：
- 只记录改动类请求，且仅在响应成功(2xx)时记录。
- 从 Authorization 头解析出 user_id（尽力而为，失败不影响主流程）。
- module 取 /api/v1/<module>，target_id 取路径末段整数（如 /api/v1/payable/5 -> 5）。
- 全程 try/except 包裹，审计失败绝不影响正常请求。
- 显式跳过登录接口，避免把凭证写进日志。
"""
import logging
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("uvicorn.error")

_WRITE_METHODS = {"POST", "PUT", "DELETE", "PATCH"}
# 不审计的路径片段（登录/改密等敏感或高频无意义）
_SKIP = ("/auth/login", "/auth/change-password", "/clock-in")


def _extract_user_id(auth_header: str):
    if not auth_header or not auth_header.lower().startswith("bearer "):
        return None
    token = auth_header.split(" ", 1)[1].strip()
    try:
        from app.core.security import decode_token
        payload = decode_token(token)
        if not payload:
            return None
        sub = payload.get("sub")
        return int(sub) if sub is not None else None
    except Exception:
        return None


def _parse_path(path: str):
    """返回 (module, target_id)。path 形如 /api/v1/payable/5/pay"""
    parts = [p for p in path.split("/") if p]
    module = None
    target_id = None
    if "v1" in parts:
        i = parts.index("v1")
        if i + 1 < len(parts):
            module = parts[i + 1]
        # 找路径里最后一个纯数字段作为 target_id
        for seg in parts[i + 2:]:
            if seg.isdigit():
                target_id = int(seg)
    return module, target_id


class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        try:
            method = request.method.upper()
            path = request.url.path
            if (
                method in _WRITE_METHODS
                and 200 <= response.status_code < 300
                and not any(s in path for s in _SKIP)
            ):
                user_id = _extract_user_id(request.headers.get("Authorization", ""))
                module, target_id = _parse_path(path)
                action = {"POST": "create", "PUT": "edit", "PATCH": "edit", "DELETE": "delete"}.get(method, method.lower())
                client_ip = request.client.host if request.client else None

                # 用独立会话写入，避免与请求本身的事务耦合
                from app.database import async_session_factory
                from app.models.audit_log import AuditLog
                factory = async_session_factory()
                async with factory() as session:
                    session.add(AuditLog(
                        user_id=user_id,
                        action_type=action,
                        module=module or "unknown",
                        target_id=target_id,
                        ip_address=client_ip,
                        detail={"method": method, "path": path, "status": response.status_code},
                    ))
                    await session.commit()
        except Exception as e:  # 审计失败绝不影响主请求
            logger.warning(f"审计日志写入失败: {e}")
        return response

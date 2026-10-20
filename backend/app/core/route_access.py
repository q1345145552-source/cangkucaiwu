"""Management is the default; only named employee/self and account utilities opt out.

Use FastAPI's public include_router API to preserve every route's schema and handlers.
Existing module permissions, business role restrictions and warehouse checks still run.
"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.routing import APIRoute

from app.core.permissions import Role, get_current_user, require_non_labor, check_staff_permission_any
from app.core.menu_registry import MENU_PERMISSIONS_BY_KEY, MENU_PERMISSIONS


SELF_ROUTES = {
    ("clock_in", "clock_in"), ("clock_in", "get_today"),
    ("clock_in", "list_records"), ("clock_in", "get_photos"),
    ("attendance", "create_leave"), ("attendance", "list_leaves"),
    ("attendance", "list_rest_days"), ("attendance", "get_calendar"),
    ("overtime", "confirm_overtime"), ("overtime", "dispute_overtime"),
    ("overtime", "list_overtimes"), ("overtime", "pending_overtimes"),
    ("overtime", "monthly_hours"), ("overtime", "get_overtime_limit"),
    ("payroll", "my_payslip"), ("employee_advance", "my_debt"),
}
ACCOUNT_UTILITIES = {("auth", name) for name in ("login", "get_me", "change_password", "attachment_session")}
PLATFORM_MODULES = {"users", "warehouses", "settings_api", "history"}
# Owner-approved cross-warehouse board: platform publication/moderation, office participation.
# These are deliberate exceptions to the super-admin business ban, not exceptions for labor.
SHARED_PLATFORM_MODULES = {"market", "group_order"}
MODULE_KEYS = {
    "customers":"customers", "payment_accounts":"accounts", "suppliers":"suppliers",
    "recharge":"recharge", "incoming":"incoming", "reconciliation":"reconciliation",
    "income_expense":"operating", "expense_fund":"expense_fund", "reimbursement":"reimbursement",
    "payable":"payable", "credit":"credit", "market":"market", "group_order":"group_order",
    "cost_funds_debt":"reports", "reports":"reports", "settings_api":"settings", "config_api":"config_center",
    "exchange_rates":"settings", "employees":"employees", "clock_in":"attendance", "attendance":"attendance",
    "overtime":"overtime", "payroll":"payroll", "history":"modification_logs", "efficiency":"labor_efficiency",
    "employee_advance":"employee_advances", "salary_template":"salary_templates", "deduction_template":"deduction_templates",
    "employee_deduction":"employee_deductions", "expense_approval":"expense_approval", "cash_advance":"cash_advances",
    "users":"settings",
}


async def require_business_user(user=Depends(get_current_user)):
    if user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if user.role not in (Role.WAREHOUSE_ADMIN,Role.SUPERVISOR,Role.STAFF,Role.WAREHOUSE_LABOR):
        raise HTTPException(403,"无权访问")
    return user


async def require_office_user(user=Depends(get_current_user)):
    if user.role not in (Role.SUPER_ADMIN,Role.WAREHOUSE_ADMIN,Role.SUPERVISOR,Role.STAFF):
        raise HTTPException(403,"无权访问")
    return user


def _has_permission(dependant):
    freevars = getattr(getattr(dependant.call, "__code__", None), "co_freevars", ())
    return bool(set(freevars) & {"perm_key", "perm_keys", "permissions", "management"}) or any(
        _has_permission(item) for item in dependant.dependencies)


class ManagementRouter(APIRouter):
    def include_router(self, router, **kwargs):
        for route in router.routes:
            if not isinstance(route, APIRoute):
                raise RuntimeError("管理路由必须声明访问策略")
            module = route.endpoint.__module__.rsplit(".", 1)[-1]
            key = (module, route.endpoint.__name__)
            dependencies = []
            if key in ACCOUNT_UTILITIES:
                kind = "account_utility"
            elif key in SELF_ROUTES:
                kind = "employee_self_or_management"
                dependencies.append(Depends(require_business_user))
            else:
                kind = "shared_platform" if module in SHARED_PLATFORM_MODULES else "platform_management" if module in PLATFORM_MODULES else "business_management"
                dependencies.append(Depends(require_non_labor))
                if module not in PLATFORM_MODULES and module not in SHARED_PLATFORM_MODULES:
                    dependencies.append(Depends(require_business_user))
                else:
                    dependencies.append(Depends(require_office_user))
                if not _has_permission(route.dependant):
                    if key == ("suppliers", "list_suppliers"):
                        keys = ("suppliers", "payable", "payment_plans", "concentration", "group_order")
                    elif key == ("config_api", "get_attendance_times"):
                        keys = ("config_center", "attendance", "payroll", "leave")
                    elif module == "upload":
                        keys = tuple(p.menu_key for p in MENU_PERMISSIONS if p.selectable)
                    elif module in ("dashboard", "warehouses") or key == ("users", "list_available_permissions"):
                        keys = ()  # Office dashboard/warehouse selector/catalog, with no selectable permission.
                    elif module in MODULE_KEYS:
                        keys = (MODULE_KEYS[module],)
                    else:
                        raise RuntimeError(f"管理接口未配置权限：{module}.{route.endpoint.__name__}")
                    if keys:
                        dependencies.append(Depends(check_staff_permission_any(*(MENU_PERMISSIONS_BY_KEY[k].label for k in keys))))
            # include_router clones APIRoute and retains models, forms, files, responses and dependencies.
            single = APIRouter()
            single.routes.append(route)
            route.openapi_extra = {**(route.openapi_extra or {}), "x-access-kind": kind}
            super().include_router(single, dependencies=[*dependencies, *kwargs.get("dependencies", [])],
                **{k:v for k,v in kwargs.items() if k != "dependencies"})

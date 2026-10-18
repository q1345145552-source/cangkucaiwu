"""后端菜单/权限唯一清单，供接口及后续权限轮次引用。

menu_key 是稳定英文标识；key 保留老接口的中文授权值（仅原八项）。
roles 与现有菜单的角色范围一致；额外权限门槛仍由现有代码执行。
default_roles 是不勾选额外权限时默认可见的角色（按当前菜单行为计算）。
selectable 表示可作为授权项，不会在本轮改变前端的八个勾选项。
这里只收录有页面的菜单，分组容器不单列；请假共用考勤页面。
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class MenuPermission:
    menu_key: str
    label: str
    path: str
    roles: tuple[str, ...]
    selectable: bool = True
    legacy_permission: bool = False
    permission_menu_key: str | None = None

    @property
    def key(self) -> str:
        return self.label if self.legacy_permission else self.menu_key

    def as_dict(self) -> dict:
        # 财务/主管的旧额外权限需要勾选，不属于默认可见。
        gated = self.legacy_permission or self.permission_menu_key is not None
        return {
            "key": self.key,
            "label": self.label,
            "menu_key": self.menu_key,
            "path": self.path,
            "roles": list(self.roles),
            "default_roles": [
                role for role in self.roles
                if not gated or role not in ("staff", "supervisor")
            ],
            "selectable": self.selectable,
        }


_MANAGERS = ("warehouse_admin", "supervisor")
_OFFICE = ("warehouse_admin", "staff", "supervisor")
_ADMIN_OFFICE = ("super_admin", *_OFFICE)
_ATTENDANCE = (*_MANAGERS, "warehouse_labor")

MENU_PERMISSIONS: tuple[MenuPermission, ...] = (
    MenuPermission("recharge", "充值申报", "/recharge", _OFFICE, permission_menu_key="recharge"),
    MenuPermission("customers", "客户档案", "/customers", _OFFICE, permission_menu_key="customers"),
    MenuPermission("accounts", "收款账户", "/accounts", _MANAGERS, permission_menu_key="accounts"),
    MenuPermission("employees", "员工档案", "/employees", _MANAGERS, permission_menu_key="employees"),
    MenuPermission("payroll", "工资", "/payroll", _MANAGERS, permission_menu_key="payroll"),
    MenuPermission("salary_templates", "薪资模板", "/salary-templates", _MANAGERS, permission_menu_key="salary_templates"),
    MenuPermission("deduction_templates", "扣款模板", "/deduction-templates", _MANAGERS, permission_menu_key="deduction_templates"),
    MenuPermission("attendance", "考勤", "/attendance", _ATTENDANCE, permission_menu_key="attendance"),
    MenuPermission("leave", "请假", "/attendance", _ATTENDANCE, permission_menu_key="leave"),
    MenuPermission("overtime", "加班", "/overtime", _ATTENDANCE, permission_menu_key="overtime"),
    MenuPermission("payable", "应付账款", "/payable", _MANAGERS, permission_menu_key="payable"),
    MenuPermission("payment_plans", "付款计划", "/payment-plans", _MANAGERS, permission_menu_key="payment_plans"),
    MenuPermission("concentration", "采购分析", "/concentration", _MANAGERS, permission_menu_key="concentration"),
    MenuPermission("group_order", "拼单", "/group-order", ("super_admin", *_MANAGERS), permission_menu_key="group_order"),
    MenuPermission("config_center", "配置中心", "/config-center", _MANAGERS, permission_menu_key="config_center"),
    MenuPermission("settings", "系统设置", "/settings", _ADMIN_OFFICE, permission_menu_key="settings"),
    MenuPermission("labor_efficiency", "人效", "/labor-efficiency", _MANAGERS, permission_menu_key="labor_efficiency"),
    MenuPermission("reports", "报表中心", "/reports", _OFFICE, permission_menu_key="reports"),
    MenuPermission("ledger", "资金流水", "/ledger", _MANAGERS, permission_menu_key="ledger"),
    MenuPermission("reconciliation", "对账", "/reconciliation", _MANAGERS, permission_menu_key="reconciliation"),
    MenuPermission("expense_approval", "费用审批", "/expense-approvals", _OFFICE),
    MenuPermission("market", "市场", "/market", _ADMIN_OFFICE),
    # 以下八项中文名已存入 users.extra_permissions，禁止重命名。
    MenuPermission("incoming", "到账流水", "/incoming", _OFFICE, legacy_permission=True),
    MenuPermission("expense_fund", "备用金管理", "/expense-fund", _OFFICE, legacy_permission=True),
    MenuPermission("reimbursement", "报销管理", "/reimbursement", _OFFICE, legacy_permission=True),
    MenuPermission("operating", "运营收支", "/operating", _OFFICE, legacy_permission=True),
    MenuPermission("cash_advances", "垫款单", "/cash-advances", _OFFICE, permission_menu_key="cash_advances"),
    MenuPermission("credit", "账期管理", "/credit", _OFFICE, legacy_permission=True),
    MenuPermission("audit_logs", "操作日志", "/audit-logs", _ADMIN_OFFICE, legacy_permission=True),
    MenuPermission("suppliers", "供应商管理", "/suppliers", _OFFICE, legacy_permission=True),
    MenuPermission("other_income_expense", "其他收支", "/other-income-expense", _OFFICE, legacy_permission=True),
    MenuPermission("dashboard", "仪表盘", "/dashboard", _OFFICE, selectable=False),
    MenuPermission("warehouses", "仓库档案", "/warehouses", ("super_admin", "warehouse_admin"), selectable=False),
    MenuPermission("modification_logs", "修改日志", "/modification-logs", ("warehouse_admin", "super_admin", "supervisor", "staff"), permission_menu_key="modification_logs"),
    MenuPermission("employee_deductions", "员工扣款", "/employee-deductions", _MANAGERS, permission_menu_key="employee_deductions"),
    MenuPermission("employee_advances", "员工预支", "/employee-advances", _MANAGERS, permission_menu_key="employee_advances"),
    MenuPermission("clock_in", "打卡签到", "/clock-in", ("warehouse_labor",), selectable=False),
    MenuPermission("my_payslip", "我的工资单", "/my-payslip", ("warehouse_labor",), selectable=False),
    # 账号身份开关，没有菜单页面，也不是 extra_permissions 勾选项。
    MenuPermission("attendance_enabled", "纳入考勤", "", ("supervisor", "staff"), selectable=False),
)

MENU_PERMISSIONS_BY_KEY = {item.menu_key: item for item in MENU_PERMISSIONS}

# 兼容现有业务接口，只从唯一清单派生，不扩大原八项的授权范围。
STAFF_PERMISSIONS = {
    item.key: item.label for item in MENU_PERMISSIONS if item.legacy_permission
}

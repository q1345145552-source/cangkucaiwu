"use client";
import { useState, useEffect, ReactNode } from "react";
import { useRouter, usePathname } from "next/navigation";
import { useAuth } from "@/hooks/useAuth";
import { useI18n } from "@/hooks/useI18n";
import {
  LayoutDashboard, Users, Warehouse, CreditCard, Truck, ArrowDownUp,
  CheckCircle, TrendingUp, PiggyBank, Receipt, FileText, Clock,
  ShoppingBag, PackageOpen, BarChart3, Settings, Menu, X, ChevronLeft,
  Globe, LogOut, Key, UserCog, ClipboardCheck,
} from "lucide-react";
import Link from "next/link";
import BackToTop from "@/components/ui/BackToTop";

interface NavItem {
  key: string;
  label: string;
  icon: ReactNode;
  href?: string;
  children?: NavItem[];
  roles: string[];
}

const navItems: NavItem[] = [
  {
    key: "dashboard_group", label: "dashboard_group", icon: <LayoutDashboard size={20} />,
    roles: ["super_admin", "warehouse_admin", "staff"],
    children: [
      { key: "dashboard", label: "dashboard", icon: <LayoutDashboard size={18} />, href: "/dashboard", roles: ["super_admin", "warehouse_admin", "staff"] },
    ],
  },
  {
    key: "finance_ops_group", label: "财务(仓库运营)", icon: <CreditCard size={20} />,
    roles: ["super_admin", "warehouse_admin", "staff"],
    children: [
      { key: "customers", label: "客户档案", icon: <Users size={18} />, href: "/customers", roles: ["warehouse_admin", "staff"] },
      { key: "warehouses", label: "仓库管理", icon: <Warehouse size={18} />, href: "/warehouses", roles: ["super_admin"] },
      { key: "accounts", label: "收款账户", icon: <CreditCard size={18} />, href: "/accounts", roles: ["warehouse_admin"] },
      { key: "recharge", label: "充值申报", icon: <ArrowDownUp size={18} />, href: "/recharge", roles: ["warehouse_admin", "staff"] },
      { key: "incoming", label: "到账流水", icon: <TrendingUp size={18} />, href: "/incoming", roles: ["warehouse_admin"] },
      { key: "reconciliation", label: "对账中心", icon: <CheckCircle size={18} />, href: "/reconciliation", roles: ["warehouse_admin"] },
    ],
  },
  {
    key: "finance_daily_group", label: "财务(日常开支)", icon: <PiggyBank size={20} />,
    roles: ["super_admin", "warehouse_admin", "staff"],
    children: [
      { key: "operating", label: "运营收支", icon: <BarChart3 size={18} />, href: "/operating", roles: ["warehouse_admin", "staff"] },
      { key: "other_income_expense", label: "其他收入", icon: <FileText size={18} />, href: "/other-income-expense", roles: ["warehouse_admin"] },
      { key: "expense_fund", label: "备用金管理", icon: <PiggyBank size={18} />, href: "/expense-fund", roles: ["warehouse_admin", "staff"] },
      { key: "reimbursement", label: "报销管理", icon: <Receipt size={18} />, href: "/reimbursement", roles: ["warehouse_admin", "staff"] },
      { key: "credit", label: "账期管理", icon: <Clock size={18} />, href: "/credit", roles: ["warehouse_admin"] },
      { key: "reports", label: "报表中心", icon: <BarChart3 size={18} />, href: "/reports", roles: ["warehouse_admin", "staff"] },
      { key: "ledger", label: "资金流水总览", icon: <FileText size={18} />, href: "/ledger", roles: ["warehouse_admin"] },
    ],
  },
  {
    key: "supplier_group", label: "supplier_group", icon: <Truck size={20} />,
    roles: ["super_admin", "warehouse_admin", "staff"],
    children: [
      { key: "suppliers", label: "suppliers", icon: <Truck size={18} />, href: "/suppliers", roles: ["warehouse_admin"] },
      { key: "payable", label: "payable", icon: <FileText size={18} />, href: "/payable", roles: ["warehouse_admin"] },
      { key: "payment_plans", label: "payment_plans", icon: <BarChart3 size={18} />, href: "/payment-plans", roles: ["warehouse_admin"] },
    ],
  },
  {
    key: "group_order_group", label: "group_order_group", icon: <PackageOpen size={20} />,
    roles: ["super_admin", "warehouse_admin", "staff"],
    children: [
      { key: "market", label: "market", icon: <ShoppingBag size={18} />, href: "/market", roles: ["super_admin", "warehouse_admin", "staff"] },
      { key: "group_order", label: "group_order", icon: <PackageOpen size={18} />, href: "/group-order", roles: ["super_admin", "warehouse_admin"] },
    ],
  },
  {
    key: "settings_group", label: "settings_group", icon: <Settings size={20} />,
    roles: ["super_admin", "warehouse_admin", "staff"],
    children: [
      { key: "settings", label: "settings", icon: <Settings size={18} />, href: "/settings", roles: ["super_admin", "warehouse_admin", "staff"] },
      { key: "audit_logs", label: "audit_logs", icon: <FileText size={18} />, href: "/audit-logs", roles: ["super_admin"] },
    ],
  },
];


// Staff 扩展权限 → 菜单映射
const STAFF_EXTRA_MAP: Record<string, string | string[]> = {
  incoming: "到账流水",
  expense_fund: "备用金管理",
  reimbursement: "报销管理",
  income_expense: "收付款管理",
  credit: "账期管理",
  suppliers: "供应商管理",
  payable: "供应商管理",
  payment_plans: "供应商管理",
  audit_logs: "操作日志",
  other_income_expense: "其他收支",
};

function hasAccess(item: NavItem, user: any): boolean {
  if (!user || !user.role) return false;
  // 非 staff 角色走原有角色匹配
  if (user.role !== "staff") return item.roles.includes(user.role);
  // Staff 角色：roles 中包含 staff 的菜单直接可见
  if (item.roles.includes("staff")) return true;
  // roles 中不包含 staff 的菜单，需检查扩展权限
  const perms: string[] = user.extra_permissions || [];
  if (perms.length === 0) return false;
  const required = STAFF_EXTRA_MAP[item.key];
  if (!required) return false;
  if (Array.isArray(required)) return required.some((p: string) => perms.includes(p));
  return perms.includes(required);
}

export default function DashboardLayout({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const { t, toggleLocale } = useI18n();
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [showUserMenu, setShowUserMenu] = useState(false);
  const pathname = usePathname();

  // 根据当前路径计算父菜单 key，初始化时直接展开，避免 useEffect 导致的闪烁
  function getParentKey(path: string | null): string | null {
    if (!path) return null;
    for (const item of navItems) {
      if (!item.children) continue;
      for (const child of item.children) {
        if (child.href && path.startsWith(child.href)) {
          return item.key;
        }
      }
    }
    return null;
  }

  const [expandedMenu, setExpandedMenu] = useState<string | null>(getParentKey(pathname));

  // 页面切换时自动匹配父菜单，处理从非子菜单页面跳转到子页面的情况
  useEffect(() => {
    if (!pathname) return;
    const parent = getParentKey(pathname);
    if (parent) setExpandedMenu(parent);
  }, [pathname]);

  const filteredNav = navItems.filter((item) => {
    if (!item.children) return hasAccess(item, user);
    return item.children.some((c) => hasAccess(c, user));
  });

  return (
    <div className="flex min-h-screen">
      {/* Sidebar */}
      <aside className={`bg-slate-900 text-white flex flex-col transition-all duration-300 ${sidebarOpen ? "w-64" : "w-20"} flex-shrink-0`}>
        <div className="flex items-center justify-between p-4 border-b border-slate-700">
          {sidebarOpen && <span className="font-semibold text-sm truncate">{t("app_name")}</span>}
          <button onClick={() => setSidebarOpen(!sidebarOpen)} className="p-1 hover:bg-slate-700 rounded">
            {sidebarOpen ? <ChevronLeft size={18} /> : <Menu size={18} />}
          </button>
        </div>
        <nav className="flex-1 overflow-y-auto py-2">
          {filteredNav.map((item) => (
            <div key={item.key}>
              {item.children ? (
                <>
                  <button
                    onClick={() => setExpandedMenu(expandedMenu === item.key ? null : item.key)}
                    className={`w-full flex items-center gap-3 px-4 py-2.5 text-sm hover:bg-slate-700 transition-colors ${!sidebarOpen && "justify-center"}`}
                  >
                    {item.icon}
                    {sidebarOpen && <span className="flex-1 text-left">{t(item.label)}</span>}
                  </button>
                  {expandedMenu === item.key && sidebarOpen && (
                    <div className="bg-slate-800">
                      {item.children.filter((c) => hasAccess(c, user)).map((child) => (
                        <Link key={child.key} href={child.href || "#"} className="flex items-center gap-3 pl-10 pr-4 py-2 text-sm hover:bg-slate-700">
                          {child.icon}
                          <span>{t(child.label)}</span>
                        </Link>
                      ))}
                    </div>
                  )}
                </>
              ) : (
                <Link
                  href={item.href || "#"}
                  className={`w-full flex items-center gap-3 px-4 py-2.5 text-sm hover:bg-slate-700 transition-colors ${!sidebarOpen && "justify-center"}`}
                >
                  {item.icon}
                  {sidebarOpen && <span className="flex-1 text-left">{t(item.label)}</span>}
                </Link>
              )}
            </div>
          ))}
        </nav>
      </aside>

      {/* Main */}
      <div className="flex-1 flex flex-col min-w-0">
        <header className="bg-white border-b h-16 flex items-center justify-between px-6 shadow-sm">
          <button onClick={() => setSidebarOpen(!sidebarOpen)} className="lg:hidden p-2">
            {sidebarOpen ? <X size={20} /> : <Menu size={20} />}
          </button>
          <div className="flex items-center gap-3 ml-auto">
            <button onClick={toggleLocale} className="p-2 hover:bg-gray-100 rounded-lg">
              <Globe size={18} />
            </button>
            <div className="relative">
              <button
                onClick={() => setShowUserMenu(!showUserMenu)}
                className="flex items-center gap-2 p-2 hover:bg-gray-100 rounded-lg"
              >
                <div className="w-8 h-8 bg-primary text-white rounded-full flex items-center justify-center text-sm font-medium">
                  {user?.display_name?.[0] || "U"}
                </div>
                <span className="text-sm text-gray-700 hidden sm:block">{user?.display_name}</span>
              </button>
              {showUserMenu && (
                <div className="absolute right-0 top-12 bg-white rounded-lg shadow-lg border w-48 py-1 z-50">
                  <div className="px-3 py-2 text-xs text-gray-400 border-b">
                    {user?.display_name}<br/>
                    {t(`role_${user?.role}`)}
                  </div>
                  <button onClick={() => {}} className="w-full flex items-center gap-2 px-3 py-2 text-sm hover:bg-gray-50">
                    <Key size={16} /> {t("change_password")}
                  </button>
                  <button onClick={() => {}} className="w-full flex items-center gap-2 px-3 py-2 text-sm hover:bg-gray-50">
                    <UserCog size={16} /> {t("users_management")}
                  </button>
                  <button onClick={logout} className="w-full flex items-center gap-2 px-3 py-2 text-sm hover:bg-gray-50 text-red-500">
                    <LogOut size={16} /> {t("logout")}
                  </button>
                </div>
              )}
            </div>
          </div>
        </header>
        <main className="flex-1 p-6 bg-gray-50 overflow-auto">
          <div key={pathname} className="animate-fade-in">
            {children}
          </div>
          <BackToTop />
        </main>
      </div>
    </div>
  );
}

"use client";
import { useState, useEffect, ReactNode } from "react";
import { useRouter, usePathname } from "next/navigation";
import { useAuth } from "@/hooks/useAuth";
import { useI18n } from "@/hooks/useI18n";
import {
  LayoutDashboard, Users, Warehouse, CreditCard, Truck, ArrowDownUp,
  CheckCircle, TrendingUp, PiggyBank, Receipt, FileText, Clock,
  ShoppingBag, PackageOpen, BarChart3, Settings, Menu, X, ChevronLeft,
  Globe, LogOut, Key, UserCog,
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
  { key: "dashboard", label: "dashboard", icon: <LayoutDashboard size={20} />, href: "/dashboard", roles: ["super_admin", "warehouse_admin", "staff"] },
  {
    key: "basic_archive", label: "basic_archive", icon: <Warehouse size={20} />,
    roles: ["warehouse_admin", "staff"],
    children: [
      { key: "customers", label: "customers", icon: <Users size={18} />, href: "/customers", roles: ["warehouse_admin", "staff"] },
      { key: "warehouses", label: "warehouses", icon: <Warehouse size={18} />, href: "/warehouses", roles: ["super_admin"] },
      { key: "accounts", label: "accounts", icon: <CreditCard size={18} />, href: "/accounts", roles: ["warehouse_admin"] },
      { key: "suppliers", label: "suppliers", icon: <Truck size={18} />, href: "/suppliers", roles: ["warehouse_admin"] },
      
    ],
  },
  { key: "recharge", label: "recharge", href: "/recharge", icon: <ArrowDownUp size={20} />, roles: ["warehouse_admin", "staff"] },
  { key: "incoming", label: "incoming", href: "/incoming", icon: <TrendingUp size={20} />, roles: ["warehouse_admin"] },
  { key: "reconciliation", label: "reconciliation", href: "/reconciliation", icon: <CheckCircle size={20} />, roles: ["warehouse_admin"] },
  { key: "income_expense", label: "income_expense", href: "/income-expense", icon: <CreditCard size={20} />, roles: ["warehouse_admin"] },
  { key: "expense_fund", label: "expense_fund", href: "/expense-fund", icon: <PiggyBank size={20} />, roles: ["warehouse_admin", "staff"] },
  { key: "reimbursement", label: "reimbursement", href: "/reimbursement", icon: <Receipt size={20} />, roles: ["warehouse_admin", "staff"] },
  { key: "payable", label: "payable", href: "/payable", icon: <FileText size={20} />, roles: ["warehouse_admin"] },
  { key: "credit", label: "credit", href: "/credit", icon: <Clock size={20} />, roles: ["warehouse_admin"] },
  { key: "market", label: "market", href: "/market", icon: <ShoppingBag size={20} />, roles: ["super_admin", "warehouse_admin", "staff"] },
  { key: "group_order", label: "group_order", href: "/group-order", icon: <PackageOpen size={20} />, roles: ["super_admin", "warehouse_admin"] },
  { key: "reports", label: "reports", href: "/reports", icon: <BarChart3 size={20} />, roles: ["warehouse_admin", "staff"] },
  { key: "ledger", label: "ledger", href: "/ledger", icon: <FileText size={20} />, roles: ["super_admin", "warehouse_admin"] },
  { key: "audit_logs", label: "audit_logs", href: "/audit-logs", icon: <FileText size={20} />, roles: ["super_admin"] },
  { key: "settings", label: "settings", href: "/settings", icon: <Settings size={20} />, roles: ["super_admin", "warehouse_admin", "staff"] },
];

function hasAccess(roles: string[], userRole: string | undefined): boolean {
  if (!userRole) return false;
  return roles.includes(userRole);
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

  const filteredNav = navItems.filter((item) => hasAccess(item.roles, user?.role));

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
                      {item.children.filter((c) => hasAccess(c.roles, user?.role)).map((child) => (
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

"use client";
import { useState, useEffect, ReactNode } from "react";
import { useRouter, usePathname } from "next/navigation";
import { useI18n } from "@/hooks/useI18n";
import {
  LayoutDashboard, Users, Warehouse, CreditCard, Truck, ArrowDownUp,
  CheckCircle, TrendingUp, PiggyBank, Receipt, FileText, Clock,
  ShoppingBag, PackageOpen, BarChart3, Settings, Menu, X, ChevronLeft,
  Globe, LogOut, Key, UserCog, Building2, ClipboardCheck, CalendarDays,
} from "lucide-react";
import Link from "next/link";
import BackToTop from "@/components/ui/BackToTop";
import { api, getToken, setActiveWarehouseId, getActiveWarehouseId } from "@/lib/api";

interface NavItem {
  key: string;
  label: string;
  icon: ReactNode;
  href?: string;
  children?: NavItem[];
  roles: string[];
}

const navItems: NavItem[] = [
  { key: "dashboard", label: "仪表盘", icon: <LayoutDashboard size={20} />, href: "/dashboard", roles: ["warehouse_admin", "staff"] },
  {
    key: "finance_ops_group", label: "财务(仓库运营)", icon: <CreditCard size={20} />,
    roles: ["warehouse_admin", "staff"],
    children: [
      { key: "customers", label: "客户档案", icon: <Users size={18} />, href: "/customers", roles: ["warehouse_admin", "staff"] },
      { key: "warehouses", label: "仓库管理", icon: <Warehouse size={18} />, href: "/warehouses", roles: ["warehouse_admin"] },
      { key: "employees", label: "员工档案", icon: <Users size={18} />, href: "/employees", roles: ["warehouse_admin"] },
      { key: "accounts", label: "收款账户", icon: <CreditCard size={18} />, href: "/accounts", roles: ["warehouse_admin"] },
      { key: "recharge", label: "充值申报", icon: <ArrowDownUp size={18} />, href: "/recharge", roles: ["warehouse_admin", "staff"] },
      { key: "incoming", label: "到账流水", icon: <TrendingUp size={18} />, href: "/incoming", roles: ["warehouse_admin"] },
      { key: "reconciliation", label: "对账中心", icon: <CheckCircle size={18} />, href: "/reconciliation", roles: ["warehouse_admin"] },
    ],
  },
  {
    key: "finance_daily_group", label: "财务(日常开支)", icon: <PiggyBank size={20} />,
    roles: ["warehouse_admin", "staff"],
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
    roles: ["warehouse_admin", "staff"],
    children: [
      { key: "suppliers", label: "suppliers", icon: <Truck size={18} />, href: "/suppliers", roles: ["warehouse_admin"] },
      { key: "payable", label: "payable", icon: <FileText size={18} />, href: "/payable", roles: ["warehouse_admin"] },
      { key: "payment_plans", label: "payment_plans", icon: <BarChart3 size={18} />, href: "/payment-plans", roles: ["warehouse_admin"] },
    ],
  },
  { key: "warehouses", label: "仓库管理", icon: <Warehouse size={20} />, href: "/warehouses", roles: ["super_admin"] },
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
      { key: "attendance", label: "工作考勤", icon: <CalendarDays size={18} />, href: "/attendance", roles: ["warehouse_admin", "warehouse_labor"] },
      { key: "clock_in", label: "打卡签到", icon: <ClipboardCheck size={18} />, href: "/clock-in", roles: ["warehouse_labor"] },    ],
  },
];

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
  if (!user || !item.roles.includes(user.role)) return false;
  if (user.role === "staff") {
    const perms = user.extra_permissions || [];
    const required = STAFF_EXTRA_MAP[item.key];
    if (required) {
      if (Array.isArray(required)) return required.some(p => perms.includes(p));
      return perms.includes(required);
    }
    return true;
  }
  return true;
}

interface WarehouseInfo {
  id: number;
  name: string;
  code: string;
}

export default function DashboardLayout({ children }: { children: ReactNode }) {
  const { t, toggleLocale } = useI18n();
  const pathname = usePathname();
  const router = useRouter();
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [expandedMenu, setExpandedMenu] = useState<string | null>(null);
  const [showUserMenu, setShowUserMenu] = useState(false);
  const [showWhSwitcher, setShowWhSwitcher] = useState(false);
  const [whList, setWhList] = useState<WarehouseInfo[]>([]);
  const [selectedWhId, setSelectedWhId] = useState<number | null>(null);
  const [isAllWarehouses, setIsAllWarehouses] = useState(false);
  const [user, setUser] = useState<any>(null);
  const [isMobile, setIsMobile] = useState(false);

  useEffect(() => {
    setIsMobile(window.innerWidth < 768);
    const handleResize = () => setIsMobile(window.innerWidth < 768);
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  // Load user + warehouses
  useEffect(() => {
    const token = getToken();
    if (!token) { router.push("/login"); return; }
    
    // Try stored user first
    const stored = localStorage.getItem("user");
    if (stored) {
      try { setUser(JSON.parse(stored)); } catch {}
    }

    // Fetch /me for warehouse list
    api.get<any>("/auth/me").then(me => {
      setUser(me);
      localStorage.setItem("user", JSON.stringify(me));
      if (me.warehouses && me.warehouses.length > 0) {
        setWhList(me.warehouses);
        const activeId = getActiveWarehouseId();
        if (activeId === "all") {
          setIsAllWarehouses(true);
          if (me.warehouses.length > 0) setSelectedWhId(me.warehouses[0].id);
        } else if (activeId && me.warehouses.find((w: any) => w.id === +activeId)) {
          setSelectedWhId(+activeId);
        } else if (me.warehouses.length > 0) {
          setSelectedWhId(me.warehouses[0].id);
          setActiveWarehouseId(me.warehouses[0].id);
        }
      }
    }).catch(() => {});
  }, []);

  const switchWarehouse = (wh: WarehouseInfo) => {
    setIsAllWarehouses(false);
    setSelectedWhId(wh.id);
    setActiveWarehouseId(wh.id);
    setShowWhSwitcher(false);
    window.dispatchEvent(new CustomEvent("warehouse-changed", { detail: { warehouseId: wh.id } }));
  };

  const switchAllWarehouses = () => {
    setIsAllWarehouses(true);
    setActiveWarehouseId("all");
    setShowWhSwitcher(false);
    window.dispatchEvent(new CustomEvent("warehouse-changed", { detail: { warehouseId: "all" } }));
  };

  // Reset all-warehouses mode when leaving /reports page
  useEffect(() => {
    if (pathname !== "/reports" && isAllWarehouses) {
      setIsAllWarehouses(false);
      if (whList.length > 0) {
        setSelectedWhId(whList[0].id);
        setActiveWarehouseId(whList[0].id);
      }
    }
  }, [pathname]);

  const logout = () => {
    localStorage.clear();
    router.push("/login");
  };

  const filteredNav = navItems.filter(item => hasAccess(item, user));
  
  // Sidebar content
  const sidebarContent = (
    <aside className={`bg-slate-900 text-white flex flex-col transition-all duration-300 z-50 ${
      isMobile ? "fixed inset-y-0 left-0 w-64" : sidebarOpen ? "w-64" : "w-16"
    }`}>
      <div className="flex items-center justify-between p-4 border-b border-slate-700 min-h-[56px]">
        <span className={`font-semibold text-sm truncate ${!sidebarOpen && !isMobile && "hidden"}`}>
          海外仓财务管理系统
        </span>
        <button
          onClick={() => isMobile ? setMobileMenuOpen(false) : setSidebarOpen(!sidebarOpen)}
          className="p-2 hover:bg-slate-700 rounded min-w-[44px] min-h-[44px] flex items-center justify-center"
        >
          {isMobile ? <X size={20} /> : (sidebarOpen ? <ChevronLeft size={18} /> : <Menu size={18} />)}
        </button>
      </div>
      <nav className="flex-1 overflow-y-auto py-2">
        {filteredNav.map((item) => (
          <div key={item.key}>
            {item.children ? (
              <>
                <button onClick={() => setExpandedMenu(expandedMenu === item.key ? null : item.key)}
                  className={`w-full flex items-center gap-3 px-4 py-3 text-sm hover:bg-slate-700 transition-colors min-h-[44px] ${!sidebarOpen && !isMobile && "justify-center"}`}>
                  {item.icon}
                  {(sidebarOpen || isMobile) && <span className="flex-1 text-left">{t(item.label)}</span>}
                </button>
                {expandedMenu === item.key && (sidebarOpen || isMobile) && (
                  <div className="bg-slate-800">
                    {item.children.filter(c => hasAccess(c, user)).map(child => (
                      <Link key={child.key} href={child.href || "#"} className="flex items-center gap-3 pl-10 pr-4 py-3 text-sm hover:bg-slate-700 min-h-[44px]">
                        {child.icon}<span>{t(child.label)}</span>
                      </Link>
                    ))}
                  </div>
                )}
              </>
            ) : (
              <Link href={item.href || "#"} className={`w-full flex items-center gap-3 px-4 py-3 text-sm hover:bg-slate-700 transition-colors min-h-[44px] ${!sidebarOpen && !isMobile && "justify-center"}`}>
                {item.icon}
                {(sidebarOpen || isMobile) && <span className="flex-1 text-left">{t(item.label)}</span>}
              </Link>
            )}
          </div>
        ))}
      </nav>
    </aside>
  );

  return (
    <div className="flex min-h-screen">
      {/* Mobile overlay */}
      {isMobile && mobileMenuOpen && (
        <div className="fixed inset-0 bg-black/50 z-40" onClick={() => setMobileMenuOpen(false)} />
      )}

      {/* Sidebar */}
      {(!isMobile || mobileMenuOpen) && sidebarContent}

      {/* Main */}
      <div className="flex-1 flex flex-col min-w-0">
        <header className="bg-white border-b h-14 lg:h-16 flex items-center justify-between px-3 lg:px-6 shadow-sm">
          <div className="flex items-center gap-2">
            {isMobile && (
              <button onClick={() => setMobileMenuOpen(true)} className="p-2 hover:bg-gray-100 rounded-lg min-w-[44px] min-h-[44px] flex items-center justify-center">
                <Menu size={22} />
              </button>
            )}
            {!isMobile && (
              <button onClick={() => setSidebarOpen(!sidebarOpen)} className="p-2 hover:bg-gray-100 rounded-lg min-w-[44px] min-h-[44px] flex items-center justify-center">
                {sidebarOpen ? <ChevronLeft size={20} /> : <Menu size={20} />}
              </button>
            )}
            
            {/* Warehouse Switcher */}
            {whList.length > 0 && (
              <div className="relative">
                <button
                  onClick={() => setShowWhSwitcher(!showWhSwitcher)}
                  className="flex items-center gap-2 px-3 py-1.5 bg-blue-50 text-blue-700 rounded-lg hover:bg-blue-100 text-sm font-medium min-h-[36px]"
                >
                  <Building2 size={16} />
                  <span className="max-w-[120px] truncate">
                    {isAllWarehouses ? "总仓汇总" : (whList.find(w => w.id === selectedWhId)?.name || "选择仓库")}
                  </span>
                  <svg className="w-3 h-3" viewBox="0 0 12 12"><path d="M3 5l3 3 3-3" fill="none" stroke="currentColor" strokeWidth="1.5"/></svg>
                </button>
                {showWhSwitcher && (
                  <div className="absolute left-0 top-full mt-1 bg-white rounded-lg shadow-lg border w-56 py-1 z-50">
                    {user?.role === "warehouse_admin" && pathname === "/reports" && (
                      <button
                        onClick={switchAllWarehouses}
                        className={`w-full text-left px-3 py-2 text-sm hover:bg-gray-50 flex items-center gap-2 min-h-[40px] ${
                          isAllWarehouses ? "text-blue-600 font-medium bg-blue-50" : ""
                        }`}
                      >
                        <Building2 size={14} className="text-amber-500" />
                        <span>总仓汇总</span>
                        <span className="text-xs text-amber-400 ml-auto">全部</span>
                      </button>
                    )}
                    {user?.role === "warehouse_admin" && pathname === "/reports" && <div className="border-t border-gray-100" />}
                    {whList.map(wh => (
                      <button
                        key={wh.id}
                        onClick={() => switchWarehouse(wh)}
                        className={`w-full text-left px-3 py-2 text-sm hover:bg-gray-50 flex items-center gap-2 min-h-[40px] ${
                          wh.id === selectedWhId ? "text-blue-600 font-medium bg-blue-50" : ""
                        }`}
                      >
                        <Building2 size={14} />
                        <span>{wh.name}</span>
                        <span className="text-xs text-gray-400 ml-auto">{wh.code}</span>
                      </button>
                    ))}
                    {user?.role === "warehouse_admin" && (
                      <Link
                        href="/warehouses"
                        onClick={() => setShowWhSwitcher(false)}
                        className="w-full text-left px-3 py-2 text-sm text-blue-500 hover:bg-blue-50 flex items-center gap-2 min-h-[40px] border-t"
                      >
                        + 新建仓库
                      </Link>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
          
          <div className="flex items-center gap-2 ml-auto">
            <button onClick={toggleLocale} className="p-2 hover:bg-gray-100 rounded-lg min-w-[44px] min-h-[44px] flex items-center justify-center">
              <Globe size={18} />
            </button>
            <div className="relative">
              <button onClick={() => setShowUserMenu(!showUserMenu)}
                className="flex items-center gap-2 p-2 hover:bg-gray-100 rounded-lg min-h-[44px]">
                <div className="w-8 h-8 bg-primary text-white rounded-full flex items-center justify-center text-sm font-medium shrink-0">
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
                  <Link href="/settings" className="w-full flex items-center gap-2 px-3 py-2 text-sm hover:bg-gray-50 min-h-[44px]">
                    <Key size={16} /> {t("change_password")}
                  </Link>
                  <Link href="/settings" className="w-full flex items-center gap-2 px-3 py-2 text-sm hover:bg-gray-50 min-h-[44px]">
                    <UserCog size={16} /> {t("users_management")}
                  </Link>
                  <button onClick={logout} className="w-full flex items-center gap-2 px-3 py-2 text-sm hover:bg-gray-50 text-red-500 min-h-[44px]">
                    <LogOut size={16} /> {t("logout")}
                  </button>
                </div>
              )}
            </div>
          </div>
        </header>
        <main className="flex-1 p-3 lg:p-6 bg-gray-50 overflow-auto">
          <div key={pathname + '-' + selectedWhId} className="animate-fade-in">
            {children}
          </div>
          <BackToTop />
        </main>
      </div>
    </div>
  );
}

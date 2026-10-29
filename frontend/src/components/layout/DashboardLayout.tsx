"use client";
import { useState, useEffect, ReactNode } from "react";
import { useRouter, usePathname } from "next/navigation";
import { useI18n, type Locale } from "@/hooks/useI18n";
import {
  LayoutDashboard, Users, Warehouse, CreditCard, Truck, ArrowDownUp,
  CheckCircle, TrendingUp, PiggyBank, Receipt, FileText, Clock,
  ShoppingBag, PackageOpen, BarChart3, Settings, Menu, X, ChevronLeft,
  Globe, LogOut, ChevronDown, Key, UserCog, Building2, ClipboardCheck, CalendarDays, DollarSign, Camera, ClipboardList, History, Gauge, Scale, MinusCircle, SlidersHorizontal,
} from "lucide-react";
import Link from "next/link";
import MinimalActionWorkspace from "@/components/permissions/MinimalActionWorkspace";
import PageNavigation from "@/components/common/PageNavigation";
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
  { key: "dashboard", label: "dashboard", icon: <LayoutDashboard size={20} />, href: "/dashboard", roles: ["warehouse_admin", "staff", "supervisor"] },
  {
    key: "finance_ops_group", label: "finance_ops_group_label", icon: <CreditCard size={20} />,
    roles: ["warehouse_admin", "staff", "supervisor"],
    children: [
      { key: "customers", label: "customers", icon: <Users size={18} />, href: "/customers", roles: ["warehouse_admin", "staff", "supervisor"] },
      { key: "warehouses", label: "warehouses", icon: <Warehouse size={18} />, href: "/warehouses", roles: ["warehouse_admin"] },
      { key: "accounts", label: "accounts", icon: <CreditCard size={18} />, href: "/accounts", roles: ["warehouse_admin", "supervisor"] },
      { key: "recharge", label: "recharge", icon: <ArrowDownUp size={18} />, href: "/recharge", roles: ["warehouse_admin", "staff", "supervisor"] },
      { key: "incoming", label: "incoming", icon: <TrendingUp size={18} />, href: "/incoming", roles: ["warehouse_admin", "staff", "supervisor"] },
      { key: "reconciliation", label: "reconciliation", icon: <CheckCircle size={18} />, href: "/reconciliation", roles: ["warehouse_admin", "supervisor"] },
    ],
  },
  {
    key: "finance_daily_group", label: "finance_daily_group_label", icon: <PiggyBank size={20} />,
    roles: ["warehouse_admin", "staff", "supervisor"],
    children: [
      { key: "payable", label: "payable", icon: <FileText size={18} />, href: "/payable", roles: ["warehouse_admin", "supervisor"] },
      { key: "payment_plans", label: "payment_plans", icon: <BarChart3 size={18} />, href: "/payment-plans", roles: ["warehouse_admin", "supervisor"] },
      { key: "operating", label: "operating", icon: <BarChart3 size={18} />, href: "/operating", roles: ["warehouse_admin", "staff", "supervisor"] },
      { key: "expense_approval", label: "expense_approval", icon: <Receipt size={18} />, href: "/expense-approvals", roles: ["warehouse_admin", "staff", "supervisor"] },
      { key: "other_income_expense", label: "other_income_expense", icon: <FileText size={18} />, href: "/other-income-expense", roles: ["warehouse_admin", "staff", "supervisor"] },
      { key: "expense_fund", label: "expense_fund", icon: <PiggyBank size={18} />, href: "/expense-fund", roles: ["warehouse_admin", "staff", "supervisor"] },
      { key: "reimbursement", label: "reimbursement", icon: <Receipt size={18} />, href: "/reimbursement", roles: ["warehouse_admin", "staff", "supervisor"] },
      { key: "cash_advances", label: "cash_advances", icon: <Receipt size={18} />, href: "/cash-advances", roles: ["warehouse_admin", "staff", "supervisor"] },
      { key: "credit", label: "credit", icon: <Clock size={18} />, href: "/credit", roles: ["warehouse_admin", "staff", "supervisor"] },
      { key: "reports", label: "reports", icon: <BarChart3 size={18} />, href: "/reports", roles: ["warehouse_admin", "staff", "supervisor"] },
      { key: "ledger", label: "ledger", icon: <FileText size={18} />, href: "/ledger", roles: ["warehouse_admin", "supervisor"] },
    ],
  },
  {
    key: "supplier_group", label: "supplier_group", icon: <Truck size={20} />,
    roles: ["warehouse_admin", "staff", "supervisor"],
    children: [
      { key: "suppliers", label: "suppliers", icon: <Truck size={18} />, href: "/suppliers", roles: ["warehouse_admin", "staff", "supervisor"] },
      { key: "inventory", label: "耗材库存", icon: <PackageOpen size={18} />, href: "/inventory", roles: ["warehouse_admin", "staff", "supervisor"] },
      { key: "sku_catalog", label: "标准SKU目录", icon: <PackageOpen size={18} />, href: "/supplier-skus", roles: ["warehouse_admin", "staff", "supervisor"] },
      { key: "concentration", label: "supplier_purchase_analysis", icon: <BarChart3 size={18} />, href: "/concentration", roles: ["warehouse_admin", "supervisor"] },
    ],
  },
  { key: "warehouses", label: "warehouses", icon: <Warehouse size={20} />, href: "/warehouses", roles: ["super_admin"] },
  { key: "modification_logs", label: "modification_logs", icon: <History size={20} />, href: "/modification-logs", roles: ["warehouse_admin", "super_admin", "supervisor", "staff"] },
  {
    key: "group_order_group", label: "group_order_group", icon: <PackageOpen size={20} />,
    roles: ["super_admin", "warehouse_admin", "staff", "supervisor"],
    children: [
      { key: "market", label: "market", icon: <ShoppingBag size={18} />, href: "/market", roles: ["super_admin", "warehouse_admin", "staff", "supervisor"] },
      { key: "group_order", label: "group_order", icon: <PackageOpen size={18} />, href: "/group-order", roles: ["super_admin", "warehouse_admin", "supervisor"] },
    ],
  },
  {
    key: "hr_group", label: "employee_group", icon: <ClipboardList size={20} />,
    roles: ["warehouse_admin", "supervisor"],
    children: [
      { key: "employees", label: "employees", icon: <Users size={18} />, href: "/employees", roles: ["warehouse_admin", "supervisor"] },
      { key: "salary_templates", label: "salary_templates", icon: <DollarSign size={18} />, href: "/salary-templates", roles: ["warehouse_admin", "supervisor"] },
      { key: "deduction_templates", label: "deduction_templates", icon: <Scale size={18} />, href: "/deduction-templates", roles: ["warehouse_admin", "supervisor"] },
      { key: "employee_deductions", label: "employee_deductions", icon: <MinusCircle size={18} />, href: "/employee-deductions", roles: ["warehouse_admin", "supervisor"] },
      { key: "attendance", label: "attendance", icon: <CalendarDays size={18} />, href: "/attendance", roles: ["warehouse_admin", "supervisor"] },
      { key: "overtime", label: "overtime", icon: <Clock size={18} />, href: "/overtime", roles: ["warehouse_admin", "supervisor"] },
      { key: "payroll", label: "payroll", icon: <DollarSign size={18} />, href: "/payroll", roles: ["warehouse_admin", "supervisor"] },
      { key: "employee_advances", label: "employee_advances", icon: <DollarSign size={18} />, href: "/employee-advances", roles: ["warehouse_admin", "supervisor"] },
      { key: "labor_efficiency", label: "labor_efficiency", icon: <Gauge size={18} />, href: "/labor-efficiency", roles: ["warehouse_admin", "supervisor"] },
    ],
  },
  { key: "config_center", label: "config_center", icon: <SlidersHorizontal size={20} />, href: "/config-center", roles: ["warehouse_admin", "supervisor"] },
  {
    key: "settings_group", label: "settings_group", icon: <Settings size={20} />,
    roles: ["super_admin", "warehouse_admin", "staff", "warehouse_labor", "supervisor"],
    children: [
      { key: "settings", label: "settings", icon: <Settings size={18} />, href: "/settings", roles: ["super_admin", "warehouse_admin", "staff", "supervisor"] },
      { key: "audit_logs", label: "audit_logs", icon: <FileText size={18} />, href: "/audit-logs", roles: ["super_admin", "warehouse_admin", "staff", "supervisor"] },
      { key: "attendance", label: "attendance", icon: <CalendarDays size={18} />, href: "/attendance", roles: ["warehouse_labor"] },
      { key: "overtime", label: "overtime", icon: <Clock size={18} />, href: "/overtime", roles: ["warehouse_labor"] },
      { key: "clock_in", label: "clock_in", icon: <ClipboardCheck size={18} />, href: "/clock-in", roles: ["warehouse_labor"] },
      { key: "my_payslip", label: "my_payslip", icon: <DollarSign size={18} />, href: "/my-payslip", roles: ["warehouse_labor"] },    ],
  },
];

interface MenuPermission {
  menu_key: string;
  label: string;
  path: string;
  roles: string[];
  selectable: boolean;
}

function hasAccess(item: NavItem, user: any, permissions: MenuPermission[]): boolean {
  if (!user) return false;
  // 管理员、超管和劳工保留原菜单；勾选权限不扩大他们的角色范围。
  if (user.role !== "staff" && user.role !== "supervisor") {
    return item.roles.includes(user.role);
  }
  // 劳工自助入口仍只属于劳工，不混入管理端。
  if (item.roles.every(role => role === "warehouse_labor")) return false;
  if (user.role === "supervisor" && ["payroll", "salary_templates", "deduction_templates", "employee_deductions", "reports", "ledger", "incoming", "reconciliation", "payable", "payment_plans", "operating", "other_income_expense", "cash_advances", "credit"].includes(item.key)) return false;
  if (item.key === "sku_catalog" && user.action_access?.grants.includes("sku_catalog_manage:operate")) return true;
  const permission = permissions.find(p => p.menu_key === item.key);
  if (!permission) return false;
  if (!permission.selectable) return item.roles.includes(user.role);
  // 请假与考勤共用原有入口；不新增菜单、不改变地址。
  return permissions.some(p => p.selectable && p.path === permission.path
    && (user.extra_permissions || []).includes(p.label));
}

function filterNavItems(items: NavItem[], user: any, permissions: MenuPermission[]): NavItem[] {
  return items.flatMap(item => {
    if (item.children) {
      const children = filterNavItems(item.children, user, permissions);
      const permissionBased = user?.role === "staff" || user?.role === "supervisor";
      if (!children.length || (!permissionBased && !hasAccess(item, user, permissions))) return [];
      return [{ ...item, children }];
    }
    return hasAccess(item, user, permissions) ? [item] : [];
  });
}

interface WarehouseInfo {
  id: number;
  name: string;
  code: string;
}

export default function DashboardLayout({ children }: { children: ReactNode }) {
  const { t, locale, setLocale } = useI18n();
  const pathname = usePathname();
  const router = useRouter();
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [expandedMenu, setExpandedMenu] = useState<string | null>(null);
  const [showUserMenu, setShowUserMenu] = useState(false);
  const [showLangSwitcher, setShowLangSwitcher] = useState(false);
  const [showWhSwitcher, setShowWhSwitcher] = useState(false);
  const [whList, setWhList] = useState<WarehouseInfo[]>([]);
  const [selectedWhId, setSelectedWhId] = useState<number | null>(null);
  const [isAllWarehouses, setIsAllWarehouses] = useState(false);
  const [user, setUser] = useState<any>(null);
  const [isMobile, setIsMobile] = useState(false);
  const [menuPermissions, setMenuPermissions] = useState<MenuPermission[]>([]);
  useEffect(() => {
    let active = true;
    setMenuPermissions([]);
    if (user?.role === "staff" || user?.role === "supervisor") {
      api.get<MenuPermission[]>("/users/permissions").then(items => { if (active) setMenuPermissions(items); }).catch(() => {});
    }
    return () => { active = false; };
  }, [user?.id, user?.role]);
  useEffect(() => {
    if (user?.role === "warehouse_labor") document.title = t("app_name");
  }, [user?.role, locale, t, pathname]);
  const laborPageAllowed = user?.role !== "warehouse_labor" ||
    ["/clock-in", "/attendance", "/overtime", "/my-payslip", "/settings"].includes(pathname);
  useEffect(() => {
    if (user?.role === "warehouse_labor" && !laborPageAllowed) router.replace("/clock-in");
  }, [user?.role, laborPageAllowed]);

  useEffect(() => {
    setIsMobile(window.innerWidth < 768);
    const handleResize = () => setIsMobile(window.innerWidth < 768);
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  useEffect(() => {
    const changed = (event: Event) => {
      if (!(event instanceof CustomEvent)) return;
      setUser(event.detail);
      setWhList(event.detail?.warehouses || []);
    };
    window.addEventListener("auth-user-refreshed", changed);
    return () => window.removeEventListener("auth-user-refreshed", changed);
  }, []);

  // Load user + warehouses
  useEffect(() => {
    const token = getToken();
    if (!token) { router.push("/login"); return; }
    api.post("/auth/attachment-session", {}).catch(() => {});
    
    // Wait for this token's live identity; cached administrator menus are not capabilities.

    // Fetch /me for warehouse list
    api.get<any>("/auth/me").then(async me => {
      if (me.role === "staff" || me.role === "supervisor") {
        const permissions = await api.get<MenuPermission[]>("/users/permissions");
        setMenuPermissions(permissions);
      }
      if (getToken() !== token) return;
      setUser(me);
      localStorage.setItem("user", JSON.stringify(me));
      window.dispatchEvent(new CustomEvent("auth-user-refreshed", { detail: me }));
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

  // Only reports and the dashboard support authorized all-warehouses reads.
  useEffect(() => {
    if (!["/reports", "/dashboard"].includes(pathname) && isAllWarehouses) {
      setIsAllWarehouses(false);
      if (whList.length > 0) {
        setSelectedWhId(whList[0].id);
        setActiveWarehouseId(whList[0].id);
      }
    }
  }, [pathname]);

  const logout = async () => {
    await api.post("/auth/attachment-session", { clear: true }).catch(() => {});
    localStorage.clear();
    router.push("/login");
  };

  const currentModules = menuPermissions.filter(p => p.path === pathname).map(p => p.menu_key);
  if (pathname === "/supplier-skus") currentModules.push("sku_catalog_manage");
  if (pathname === "/fund-review") currentModules.push("expense_fund");
  if (pathname === "/income-expense") currentModules.push("operating");
  const minimumWorkspace = user?.action_access?.version === 1 && ["staff", "supervisor"].includes(user.role)
    && currentModules.length > 0 && !["/settings", "/dashboard"].includes(pathname)
    && !currentModules.some(m => user.action_access.grants.includes(`${m}:view`));
  const filteredNav = filterNavItems(navItems, user, menuPermissions);
  if ((user?.role === "supervisor" || user?.role === "staff") && user.attendance_enabled) {
    filteredNav.push({ key: "employee_self", label: "employee_self", icon: <Users size={20} />, roles: ["supervisor", "staff"], children: [
      { key: "self_clock", label: "clock_in", icon: <ClipboardCheck size={18} />, href: "/clock-in", roles: ["supervisor", "staff"] },
      { key: "self_attendance", label: "attendance", icon: <CalendarDays size={18} />, href: "/my-attendance", roles: ["supervisor", "staff"] },
      { key: "self_overtime", label: "overtime", icon: <Clock size={18} />, href: "/my-overtime", roles: ["supervisor", "staff"] },
      { key: "self_payslip", label: "my_payslip", icon: <DollarSign size={18} />, href: "/my-payslip", roles: ["supervisor", "staff"] },
      { key: "self_leave", label: "leave", icon: <CalendarDays size={18} />, href: "/my-leave", roles: ["supervisor", "staff"] },
    ] });
  }
  if ((user?.role === "supervisor" || user?.role === "staff") && user.self_employee_id) {
    filteredNav.push({ key: "my_requests", label: "我的申请与欠款", icon: <Users size={20} />, href: "/my-requests", roles: ["supervisor", "staff"] });
    if (!user.attendance_enabled) filteredNav.push({ key: "my_salary", label: "my_payslip", icon: <DollarSign size={18} />, href: "/my-payslip", roles: ["supervisor", "staff"] });
  }
  const settingsItem = navItems.find(item => item.key === "settings_group")?.children?.find(item => item.key === "settings");
  const showUsersManagement = user?.role !== "warehouse_labor" && settingsItem && hasAccess(settingsItem, user, menuPermissions);
  
  // Sidebar content
  const sidebarContent = (
    <aside className={`bg-slate-900 text-white flex flex-col transition-all duration-300 z-50 ${
      isMobile ? "fixed inset-y-0 left-0 w-64" : sidebarOpen ? "w-64" : "w-16"
    }`}>
      <div className="flex items-center justify-between p-4 border-b border-slate-700 min-h-[56px]">
        <span className={`font-semibold text-sm truncate ${!sidebarOpen && !isMobile && "hidden"}`}>
          {t("app_name")}
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
                    {item.children.map(child => (
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

  // Do not render a default Chinese/management shell before the saved role and locale are loaded.
  if (!user || !laborPageAllowed) return null;

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
        <header className="sticky top-0 z-20 shrink-0 lg:static lg:z-auto bg-white border-b h-14 lg:h-16 flex items-center justify-between px-3 lg:px-6 shadow-sm">
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
            
            {/* Warehouse Switcher（超管不显示，其余角色照旧） */}
            {whList.length > 0 && user?.role !== "super_admin" && (
              <div className="relative">
                <button
                  onClick={() => setShowWhSwitcher(!showWhSwitcher)}
                  className="flex items-center gap-2 px-3 py-1.5 bg-blue-50 text-blue-700 rounded-lg hover:bg-blue-100 text-sm font-medium min-h-[36px]"
                >
                  <Building2 size={16} />
                  <span className="max-w-[120px] truncate">
                    {isAllWarehouses ? t("all_warehouses") : (whList.find(w => w.id === selectedWhId)?.name || t("select_warehouse"))}
                  </span>
                  <svg className="w-3 h-3" viewBox="0 0 12 12"><path d="M3 5l3 3 3-3" fill="none" stroke="currentColor" strokeWidth="1.5"/></svg>
                </button>
                {showWhSwitcher && (
                  <div className="absolute left-0 top-full mt-1 bg-white rounded-lg shadow-lg border w-56 py-1 z-50">
                    {user?.role === "warehouse_admin" && ["/reports", "/dashboard"].includes(pathname) && (
                      <button
                        onClick={switchAllWarehouses}
                        className={`w-full text-left px-3 py-2 text-sm hover:bg-gray-50 flex items-center gap-2 min-h-[40px] ${
                          isAllWarehouses ? "text-blue-600 font-medium bg-blue-50" : ""
                        }`}
                      >
                        <Building2 size={14} className="text-amber-500" />
                        <span>{t("all_warehouses")}</span>
                        <span className="text-xs text-amber-400 ml-auto">{t("all")}</span>
                      </button>
                    )}
                    {user?.role === "warehouse_admin" && ["/reports", "/dashboard"].includes(pathname) && <div className="border-t border-gray-100" />}
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
                        + {t("new_warehouse")}
                      </Link>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
          
          <div className="flex items-center gap-2 ml-auto">
            {/* Language Switcher Dropdown */}
            <div className="relative">
              <button
                onClick={() => setShowLangSwitcher(!showLangSwitcher)}
                className="p-2 hover:bg-gray-100 rounded-lg min-w-[44px] min-h-[44px] flex items-center justify-center gap-1"
              >
                <Globe size={18} />
                <span className="text-xs font-medium text-gray-500 hidden sm:inline">{locale === "zh" ? "中文" : locale === "th" ? "ไทย" : "မြန်မာ"}</span>
                <ChevronDown size={12} className="text-gray-400" />
              </button>
              {showLangSwitcher && (
                <div className="absolute right-0 top-full mt-1 bg-white rounded-lg shadow-lg border w-36 py-1 z-50">
                  {((user?.role === "warehouse_labor"
                    ? [{ code: "th", label: "ไทย" }, { code: "my", label: "မြန်မာ" }]
                    : [{ code: "zh", label: "中文" }, { code: "th", label: "ไทย" }, { code: "my", label: "မြန်မာ" }]
                  ) satisfies { code: Locale; label: string }[]).map(lang => (
                    <button
                      key={lang.code}
                      onClick={() => { setLocale(lang.code); setShowLangSwitcher(false); }}
                      className={"w-full text-left px-3 py-2 text-sm hover:bg-gray-50 flex items-center gap-2 min-h-[40px] " + (locale === lang.code ? "text-blue-600 font-medium bg-blue-50" : "")}
                    >
                      <span>{lang.label}</span>
                      {locale === lang.code && <span className="ml-auto text-blue-500">✓</span>}
                    </button>
                  ))}
                </div>
              )}
            </div>

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
                  {showUsersManagement && (
                    <Link href="/settings" className="w-full flex items-center gap-2 px-3 py-2 text-sm hover:bg-gray-50 min-h-[44px]">
                      <UserCog size={16} /> {t("users_management")}
                    </Link>
                  )}
                  <button onClick={logout} className="w-full flex items-center gap-2 px-3 py-2 text-sm hover:bg-gray-50 text-red-500 min-h-[44px]">
                    <LogOut size={16} /> {t("logout")}
                  </button>
                </div>
              )}
            </div>
          </div>
        </header>
        {user && laborPageAllowed && pathname !== "/clock-in" && <PageNavigation />}
        <main className="flex-1 p-3 lg:p-6 bg-gray-50 overflow-auto">
          <div key={`${user?.id}-${user?.role}-${pathname}-${selectedWhId}-${isAllWarehouses}-${JSON.stringify([user?.extra_permissions || [], user?.action_access?.grants || []])}`} className="animate-fade-in">
            {user && laborPageAllowed && (!["staff", "supervisor"].includes(user.role) || menuPermissions.length > 0) ? (minimumWorkspace ? <MinimalActionWorkspace modules={currentModules} /> : children) : null}
          </div>
          <BackToTop />
        </main>
      </div>
    </div>
  );
}

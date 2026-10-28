export interface PageParent { href: string; label: string; labelKey?: string }
const dashboard: PageParent = { href: '/dashboard', label: '仪表盘', labelKey: 'dashboard' };
const supplier: PageParent = { href: '/suppliers', label: '供应商管理', labelKey: 'suppliers' };
const employee: PageParent = { href: '/clock-in', label: '员工首页', labelKey: 'page_back_employee_home' };
const warehouse: PageParent = { href: '/warehouses', label: '仓库档案', labelKey: 'warehouses' };
// Menu headings without an actual page use the dashboard; no routes are invented.
export const dashboardPages = [
 '/accounts','/audit-logs','/cash-advances','/config-center','/credit','/customers',
 '/deduction-templates','/employee-advances','/employee-deductions','/employees',
 '/expense-approvals','/expense-fund','/group-order','/incoming','/labor-efficiency',
 '/ledger','/market','/modification-logs','/operating','/other-income-expense',
 '/payable','/payment-plans','/payroll','/recharge','/reconciliation','/reimbursement',
 '/reports','/salary-templates','/suppliers','/warehouses',
 '/attendance','/overtime','/settings','/clock-in','/my-attendance','/my-leave',
 '/my-overtime','/my-payslip','/my-requests',
] as const;
const parents: Record<string, PageParent> = Object.fromEntries(dashboardPages.map(path => [path, dashboard]));
Object.assign(parents, {
 '/categories': {href:'/config-center',label:'配置中心',labelKey:'config_center'},
 '/clock-records': {href:'/attendance',label:'考勤管理',labelKey:'attendance'},
 '/income-expense': {href:'/operating',label:'运营支出',labelKey:'operating'},
 '/fund-review': {href:'/expense-fund',label:'备用金管理',labelKey:'expense_fund'},
 '/concentration':supplier, '/inventory':supplier, '/supplier-skus':supplier,
 '/reports/cost-funds-debt': {href:'/reports',label:'报表中心',labelKey:'reports'},
 '/suppliers/monthly-price-report':supplier, '/suppliers/risk':supplier,
 '/suppliers/controls': {href:'/suppliers/risk',label:'采购风险看板'},
 '/suppliers/risk/reviews': {href:'/suppliers/risk',label:'采购风险看板'},
});
export function pageParent(path: string, role: string): PageParent | null {
 path=path.replace(/\/$/,'')||'/';
 if(['/', '/login', '/dashboard'].includes(path)) return null;
 if(role==='super_admin' && path==='/warehouses') return null;
 if(role==='warehouse_labor' && path==='/clock-in') return null;
 let result=parents[path];
 if(/^\/cash-advances\/[^/]+$/.test(path)) result={href:'/cash-advances',label:'垫款单列表',labelKey:'cash_advances'};
 if(/^\/suppliers\/purchase-orders\/[^/]+$/.test(path)) result={href:'/payable',label:'应付账款',labelKey:'payable'};
 const source=path.match(/^\/expense-identities\/(payable|approval|fund_item|expense)\/[^/]+$/)?.[1];
 if(source){
  const origins:Record<string,PageParent>={payable:{href:'/payable',label:'应付账款',labelKey:'payable'},approval:{href:'/expense-approvals',label:'费用审批',labelKey:'expense_approval'},fund_item:{href:'/expense-fund',label:'备用金管理',labelKey:'expense_fund'},expense:{href:'/operating',label:'运营支出',labelKey:'operating'}};
  result=origins[source];
 }
 if(!result) return null;
 if(role==='warehouse_labor') return employee;
 if(role==='super_admin' && result.href==='/dashboard') return warehouse;
 return result;
}

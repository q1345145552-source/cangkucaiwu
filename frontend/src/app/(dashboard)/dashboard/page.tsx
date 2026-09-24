"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/hooks/useAuth";
import { getToken, api } from "@/lib/api";
import { TrendingUp, TrendingDown, Wallet, ShoppingCart, Users, Gauge, ListTodo, FileText, Receipt, Bed, Clock, ClipboardCheck, AlertTriangle, Tag, Package, LineChart as LineChartIcon } from "lucide-react";
import { LineChart, BarChart, DonutChart } from "@/components/TrendCharts";

interface Amount { currency: string; amount: number; }

interface CockpitData {
  finance: {
    month: { income: Amount[]; operating_expense: Amount[]; procurement_expense: Amount[]; expense: Amount[]; profit: Amount[] };
    receivable_payable: { receivable: Amount[]; payable: Amount[]; overdue_payable: Amount[] };
    balances: { payment_accounts: Amount[]; expense_funds: Amount[] };
    procurement: { expense: Amount[]; price_anomaly_count: number; non_lowest_count: number };
    recharge_reconciliation: { recharge: Amount[]; incoming: Amount[]; unmatched_count: number };
  };
  people: {
    attendance: { expected: number; present: number; absent: number };
    efficiency: { person_times: number; order_count: number; efficiency: number; standard: number; below_standard: boolean } | null;
    todos: { leave_pending: number; overtime_pending: number; expense_fund_pending: number; reimbursement_pending: number; market_pending: number; group_order_pending: number; expense_approval_pending?: number };
  };
  todos: { type: string; description: string; link: string; id: number }[];
}

interface TrendPoint { date?: string; month?: string; week_start?: string; recharge?: number; incoming?: number; income?: number; expense?: number; count?: number; }
interface DonutItem { name: string; amount: number; }
interface TrendsData {
  funds: Record<string, TrendPoint[]>;
  income_expense: Record<string, TrendPoint[]>;
  orders: Record<string, TrendPoint[]>;
  expense_categories: Record<string, DonutItem[]>;
  procurement_suppliers: Record<string, DonutItem[]>;
}

function curSymbol(c: string) {
  if (!c) return "";
  const cc = c.toUpperCase();
  if (cc === "CNY" || c === "人民币") return "¥";
  if (cc === "THB" || c === "泰铢") return "฿";
  return cc + " ";
}

function fmtAmt(a: Amount) {
  return `${curSymbol(a.currency)}${(a.amount ?? 0).toLocaleString()}`;
}

function AmountList({ items, empty = "—" }: { items: Amount[]; empty?: string }) {
  if (!items || items.length === 0) return <span className="text-gray-400">{empty}</span>;
  return (
    <div className="flex flex-wrap gap-x-3 gap-y-0.5">
      {items.map((a) => (
        <span key={a.currency} className="whitespace-nowrap">{fmtAmt(a)}</span>
      ))}
    </div>
  );
}

function CurrencyToggle({ value, onChange }: { value: "THB" | "CNY"; onChange: (v: "THB" | "CNY") => void }) {
  return (
    <div className="flex bg-gray-100 rounded-lg p-0.5 text-xs">
      <button onClick={() => onChange("THB")} className={`px-2 py-0.5 rounded-md transition ${value === "THB" ? "bg-white shadow-sm text-gray-800" : "text-gray-500"}`}>泰铢</button>
      <button onClick={() => onChange("CNY")} className={`px-2 py-0.5 rounded-md transition ${value === "CNY" ? "bg-white shadow-sm text-gray-800" : "text-gray-500"}`}>人民币</button>
    </div>
  );
}

function hasFundData(points: TrendPoint[] | undefined) {
  return !!(points && points.some(p => (p.recharge || 0) > 0 || (p.incoming || 0) > 0));
}
function hasIEData(points: TrendPoint[] | undefined) {
  return !!(points && points.some(p => (p.income || 0) > 0 || (p.expense || 0) > 0));
}
function hasOrderData(points: TrendPoint[] | undefined) {
  return !!(points && points.some(p => (p.count || 0) > 0));
}

const TODO_CONFIG: Record<string, { icon: React.ReactNode; color: string; badge: string }> = {
  purchase_approval: { icon: <ClipboardCheck className="h-4 w-4" />, color: "text-purple-600 bg-purple-50", badge: "采购审批" },
  bill_confirm: { icon: <AlertTriangle className="h-4 w-4" />, color: "text-amber-600 bg-amber-50", badge: "账单确认" },
  leave: { icon: <Bed className="h-4 w-4" />, color: "text-pink-600 bg-pink-50", badge: "请假审批" },
  overtime: { icon: <Clock className="h-4 w-4" />, color: "text-indigo-600 bg-indigo-50", badge: "加班确认" },
  expense_fund: { icon: <FileText className="h-4 w-4" />, color: "text-red-600 bg-red-50", badge: "备用金审核" },
  reimbursement: { icon: <Receipt className="h-4 w-4" />, color: "text-orange-600 bg-orange-50", badge: "报销审批" },
  market: { icon: <Tag className="h-4 w-4" />, color: "text-blue-600 bg-blue-50", badge: "商品审核" },
  group_order: { icon: <Package className="h-4 w-4" />, color: "text-teal-600 bg-teal-50", badge: "待拼单" },
  expense_approval: { icon: <Receipt className="h-4 w-4" />, color: "text-emerald-600 bg-emerald-50", badge: "费用审批" },
};

export default function DashboardPage() {
  const { user } = useAuth();
  const router = useRouter();
  const [data, setData] = useState<CockpitData | null>(null);
  const [trends, setTrends] = useState<TrendsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [fundCur, setFundCur] = useState<"THB" | "CNY">("THB");
  const [ieCur, setIeCur] = useState<"THB" | "CNY">("THB");
  const [orderCur, setOrderCur] = useState<"THB" | "CNY">("THB");
  const [expCur, setExpCur] = useState<"THB" | "CNY">("THB");
  const [supCur, setSupCur] = useState<"THB" | "CNY">("THB");

  useEffect(() => {
    if (!getToken()) { router.push("/login"); return; }
    loadData();
  }, [router]);

  async function loadData() {
    setError("");
    try {
      const [d, t] = await Promise.all([
        api.get<CockpitData>("/dashboard/cockpit"),
        api.get<TrendsData>("/dashboard/trends"),
      ]);
      setData(d);
      setTrends(t);
    } catch (e: any) {
      setError(e?.message || "加载失败");
    }
    setLoading(false);
  }

  if (loading) {
    return <div className="flex items-center justify-center h-64 text-gray-400">加载中...</div>;
  }
  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-64 text-gray-500 gap-2">
        <AlertTriangle className="h-8 w-8 text-orange-400" />
        <p>{error}</p>
      </div>
    );
  }
  if (!data) return null;

  const { finance, people } = data;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-800">老板驾驶舱</h1>
        <p className="text-sm text-gray-500 mt-1">{user?.display_name} · {user?.warehouse_name || "概览"}</p>
      </div>

      {/* 钱的部分 */}
      <section>
        <h2 className="text-base font-semibold text-gray-700 mb-3 flex items-center gap-2"><Wallet className="h-5 w-5 text-green-600" /> 钱</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {/* 本月收支盈亏 */}
          <div className="bg-white rounded-xl p-5 shadow-sm border">
            <div className="flex items-center gap-2 mb-3 text-gray-500 text-sm"><TrendingUp className="h-4 w-4 text-green-600" />本月收支盈亏</div>
            <div className="space-y-2 text-sm">
              <div className="flex justify-between"><span className="text-gray-500">本月收入</span><AmountList items={finance.month.income} /></div>
              <div className="flex justify-between"><span className="text-gray-500">本月支出</span><AmountList items={finance.month.expense} /></div>
              <div className="flex justify-between border-t pt-2"><span className="text-gray-700 font-medium">盈亏</span><span className={finance.month.profit.some(p => p.amount < 0) ? "text-red-600 font-semibold" : "text-green-600 font-semibold"}><AmountList items={finance.month.profit} /></span></div>
            </div>
          </div>

          {/* 待收待付 */}
          <div className="bg-white rounded-xl p-5 shadow-sm border">
            <div className="flex items-center gap-2 mb-3 text-gray-500 text-sm"><TrendingDown className="h-4 w-4 text-blue-600" />待收待付</div>
            <div className="space-y-2 text-sm">
              <div className="flex justify-between"><span className="text-gray-500">待收</span><AmountList items={finance.receivable_payable.receivable} /></div>
              <div className="flex justify-between"><span className="text-gray-500">待付</span><AmountList items={finance.receivable_payable.payable} /></div>
              <div className="flex justify-between border-t pt-2"><span className="text-red-500">逾期未付</span><span className="text-red-600 font-semibold"><AmountList items={finance.receivable_payable.overdue_payable} /></span></div>
            </div>
          </div>

          {/* 账户余额 */}
          <div className="bg-white rounded-xl p-5 shadow-sm border">
            <div className="flex items-center gap-2 mb-3 text-gray-500 text-sm"><Wallet className="h-4 w-4 text-teal-600" />账户余额</div>
            <div className="space-y-2 text-sm">
              <div className="flex justify-between"><span className="text-gray-500">收款账户</span><AmountList items={finance.balances.payment_accounts} /></div>
              <div className="flex justify-between"><span className="text-gray-500">备用金</span><AmountList items={finance.balances.expense_funds} /></div>
            </div>
          </div>

          {/* 本月采购 */}
          <div className="bg-white rounded-xl p-5 shadow-sm border">
            <div className="flex items-center gap-2 mb-3 text-gray-500 text-sm"><ShoppingCart className="h-4 w-4 text-purple-600" />本月采购</div>
            <div className="space-y-2 text-sm">
              <div className="flex justify-between"><span className="text-gray-500">采购支出</span><AmountList items={finance.procurement.expense} /></div>
              <div className="flex justify-between"><span className="text-gray-500">价格异常</span><span className={finance.procurement.price_anomaly_count > 0 ? "text-red-600 font-semibold" : "text-gray-700"}>{finance.procurement.price_anomaly_count} 笔</span></div>
              <div className="flex justify-between"><span className="text-gray-500">非最低价</span><span className={finance.procurement.non_lowest_count > 0 ? "text-red-600 font-semibold" : "text-gray-700"}>{finance.procurement.non_lowest_count} 笔</span></div>
            </div>
          </div>

          {/* 充值对账 */}
          <div className="bg-white rounded-xl p-5 shadow-sm border">
            <div className="flex items-center gap-2 mb-3 text-gray-500 text-sm"><TrendingUp className="h-4 w-4 text-sky-600" />充值对账</div>
            <div className="space-y-2 text-sm">
              <div className="flex justify-between"><span className="text-gray-500">本月充值</span><AmountList items={finance.recharge_reconciliation.recharge} /></div>
              <div className="flex justify-between"><span className="text-gray-500">本月到账</span><AmountList items={finance.recharge_reconciliation.incoming} /></div>
              <div className="flex justify-between border-t pt-2"><span className="text-gray-500">未对账</span><span className="text-red-600 font-semibold">{finance.recharge_reconciliation.unmatched_count} 笔</span></div>
            </div>
          </div>
        </div>
      </section>

      {/* 人的部分 */}
      <section>
        <h2 className="text-base font-semibold text-gray-700 mb-3 flex items-center gap-2"><Users className="h-5 w-5 text-blue-600" /> 人</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {/* 今日出勤 */}
          <div className="bg-white rounded-xl p-5 shadow-sm border">
            <div className="flex items-center gap-2 mb-3 text-gray-500 text-sm"><Users className="h-4 w-4 text-blue-600" />今日出勤</div>
            <div className="flex items-end gap-2">
              <span className="text-3xl font-bold text-gray-800">{people.attendance.present}</span>
              <span className="text-gray-400 text-lg">/ {people.attendance.expected}</span>
            </div>
            <div className="text-sm text-gray-500 mt-2">实到 / 应到 · 缺勤 {people.attendance.absent} 人</div>
          </div>

          {/* 本月人效 */}
          <div className="bg-white rounded-xl p-5 shadow-sm border">
            <div className="flex items-center gap-2 mb-3 text-gray-500 text-sm"><Gauge className="h-4 w-4 text-orange-600" />本月人效</div>
            {people.efficiency ? (
              <div className="space-y-2 text-sm">
                <div className="flex justify-between"><span className="text-gray-500">人次</span><span className="font-semibold">{people.efficiency.person_times}</span></div>
                <div className="flex justify-between"><span className="text-gray-500">人效</span><span className="font-semibold">{people.efficiency.efficiency} 单/人次</span></div>
                <div className="flex justify-between"><span className="text-gray-500">达标</span>
                  <span className={people.efficiency.below_standard ? "text-red-600 font-semibold" : "text-green-600 font-semibold"}>
                    {people.efficiency.below_standard ? "不达标" : "达标"}（标准 {people.efficiency.standard}）
                  </span>
                </div>
              </div>
            ) : <span className="text-gray-400">—</span>}
          </div>

          {/* 待办数量 */}
          <div className="bg-white rounded-xl p-5 shadow-sm border">
            <div className="flex items-center gap-2 mb-3 text-gray-500 text-sm"><ListTodo className="h-4 w-4 text-red-600" />待办数量</div>
            <div className="space-y-2 text-sm">
              <div className="flex justify-between"><span className="text-gray-500">请假待审批</span><span className="font-semibold">{people.todos.leave_pending}</span></div>
              <div className="flex justify-between"><span className="text-gray-500">加班待确认</span><span className="font-semibold">{people.todos.overtime_pending}</span></div>
              <div className="flex justify-between"><span className="text-gray-500">备用金审核</span><span className="font-semibold">{people.todos.expense_fund_pending}</span></div>
              <div className="flex justify-between"><span className="text-gray-500">报销审批</span><span className="font-semibold">{people.todos.reimbursement_pending}</span></div>
              <div className="flex justify-between"><span className="text-gray-500">商品审核</span><span className="font-semibold">{people.todos.market_pending}</span></div>
              {user?.role === "warehouse_admin" && (
                <div className="flex justify-between"><span className="text-gray-500">费用待审批</span><span className="font-semibold">{people.todos.expense_approval_pending ?? 0}</span></div>
              )}
            </div>
          </div>
        </div>
      </section>

      {/* 趋势图 */}
      {trends && (
        <section>
          <h2 className="text-base font-semibold text-gray-700 mb-3 flex items-center gap-2"><LineChartIcon className="h-5 w-5 text-indigo-600" /> 趋势</h2>
          <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
            {/* 资金趋势 */}
            <div className="bg-white rounded-xl p-5 shadow-sm border">
              <div className="flex items-center justify-between mb-3">
                <span className="text-sm font-medium text-gray-600">资金趋势（30天）</span>
                <CurrencyToggle value={fundCur} onChange={setFundCur} />
              </div>
              {hasFundData(trends.funds[fundCur]) ? (
                <LineChart
                  labels={trends.funds[fundCur].map(p => p.date || "")}
                  datasets={[
                    { name: "充值", color: "#2563eb", values: trends.funds[fundCur].map(p => p.recharge || 0) },
                    { name: "到账", color: "#16a34a", values: trends.funds[fundCur].map(p => p.incoming || 0) },
                  ]}
                  valuePrefix={fundCur === "CNY" ? "¥" : "฿"}
                />
              ) : <div className="h-40 flex items-center justify-center text-gray-400 text-sm">暂无数据</div>}
            </div>

            {/* 收支趋势 */}
            <div className="bg-white rounded-xl p-5 shadow-sm border">
              <div className="flex items-center justify-between mb-3">
                <span className="text-sm font-medium text-gray-600">收支趋势（6个月）</span>
                <CurrencyToggle value={ieCur} onChange={setIeCur} />
              </div>
              {hasIEData(trends.income_expense[ieCur]) ? (
                <LineChart
                  labels={trends.income_expense[ieCur].map(p => p.month || "")}
                  datasets={[
                    { name: "收入", color: "#2563eb", values: trends.income_expense[ieCur].map(p => p.income || 0) },
                    { name: "支出", color: "#dc2626", values: trends.income_expense[ieCur].map(p => p.expense || 0) },
                  ]}
                  valuePrefix={ieCur === "CNY" ? "¥" : "฿"}
                />
              ) : <div className="h-40 flex items-center justify-center text-gray-400 text-sm">暂无数据</div>}
            </div>

            {/* 订单趋势 */}
            <div className="bg-white rounded-xl p-5 shadow-sm border">
              <div className="flex items-center justify-between mb-3">
                <span className="text-sm font-medium text-gray-600">订单趋势（8周）</span>
                <CurrencyToggle value={orderCur} onChange={setOrderCur} />
              </div>
              {hasOrderData(trends.orders[orderCur]) ? (
                <BarChart
                  labels={trends.orders[orderCur].map(p => p.week_start || "")}
                  datasets={[
                    { name: "订单数", color: "#8b5cf6", values: trends.orders[orderCur].map(p => p.count || 0) },
                  ]}
                  valuePrefix=""
                />
              ) : <div className="h-40 flex items-center justify-center text-gray-400 text-sm">暂无数据</div>}
            </div>
          </div>
        </section>
      )}

      {/* 占比环形图 */}
      {trends && (
        <section>
          <h2 className="text-base font-semibold text-gray-700 mb-3">占比</h2>
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
            {/* 支出构成 */}
            <div className="bg-white rounded-xl p-5 shadow-sm border">
              <div className="flex items-center justify-between mb-3">
                <span className="text-sm font-medium text-gray-600">支出构成（本月运营支出）</span>
                <CurrencyToggle value={expCur} onChange={setExpCur} />
              </div>
              {(trends.expense_categories[expCur] || []).length > 0 ? (
                <DonutChart items={trends.expense_categories[expCur] || []} valuePrefix={expCur === "CNY" ? "¥" : "฿"} />
              ) : <div className="h-40 flex items-center justify-center text-gray-400 text-sm">暂无数据</div>}
            </div>

            {/* 供应商采购占比 */}
            <div className="bg-white rounded-xl p-5 shadow-sm border">
              <div className="flex items-center justify-between mb-3">
                <span className="text-sm font-medium text-gray-600">供应商采购占比（本月采购支出）</span>
                <CurrencyToggle value={supCur} onChange={setSupCur} />
              </div>
              {(trends.procurement_suppliers[supCur] || []).length > 0 ? (
                <DonutChart items={trends.procurement_suppliers[supCur] || []} valuePrefix={supCur === "CNY" ? "¥" : "฿"} redAbovePercent={70} />
              ) : <div className="h-40 flex items-center justify-center text-gray-400 text-sm">暂无数据</div>}
            </div>
          </div>
        </section>
      )}

      {/* 待办列表 */}
      <section className="bg-white rounded-xl p-6 shadow-sm border">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-gray-700">待办提醒</h2>
          <span className="text-sm text-gray-400">{data.todos.length} 项待处理</span>
        </div>

        {data.todos.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-10 text-gray-400">
            <svg className="w-12 h-12 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <span>暂无待办事项</span>
          </div>
        ) : (
          <div className="space-y-2">
            {(["purchase_approval", "bill_confirm", "leave", "overtime", "expense_fund", "reimbursement", "market", "group_order", "expense_approval"] as const).map((type) => {
              const typeTasks = data.todos.filter((t) => t.type === type);
              if (typeTasks.length === 0) return null;
              const cfg = TODO_CONFIG[type];
              return (
                <div key={type} className="mb-3">
                  <div className="flex items-center gap-2 mb-2">
                    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${cfg.color}`}>
                      {cfg.icon}{cfg.badge}
                    </span>
                    <span className="text-xs text-gray-400">{typeTasks.length} 项</span>
                  </div>
                  {typeTasks.map((task) => (
                    <div key={task.id} onClick={() => router.push(task.link)}
                      className="flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-gray-50 cursor-pointer transition-colors text-sm text-gray-700">
                      <span className="w-1.5 h-1.5 rounded-full bg-current opacity-50 shrink-0" />
                      <span>{task.description}</span>
                      <svg className="w-3 h-3 text-gray-300 ml-auto shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                      </svg>
                    </div>
                  ))}
                </div>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}

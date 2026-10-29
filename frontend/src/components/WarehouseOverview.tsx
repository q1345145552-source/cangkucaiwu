"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import { getToken, setActiveWarehouseId } from "@/lib/api";

const todoColumns = [
  ["employee_advances", "待预支"],
  ["overtime_employee_confirmation", "待员工确认加班"],
  ["overtime_admin_verification", "待管理员核实加班"],
  ["expense_fund_review", "待审备用金"],
  ["purchase_approval", "待审批采购"],
  ["receipt_review", "待审收货"],
] as const;
type TodoKey = typeof todoColumns[number][0] | "total";
type Amount = string | number;
type Amounts = Record<string, Amount>;
interface TodayRow {
  warehouse_id: number;
  warehouse_name: string;
  income_by_currency: { currency: string; amount: Amount }[];
  expense_by_currency: { currency: string; amount: Amount }[];
  todos: Record<TodoKey, number>;
  attendance: { actual: number; expected: number };
  has_data: boolean;
}
interface MonthRow {
  warehouse_id: number;
  warehouse_name: string;
  income_by_currency: Amounts;
  expense_by_currency: Amounts;
  income_count_by_currency: Record<string, number>;
  expense_count_by_currency: Record<string, number>;
}
interface ViewData { today: TodayRow[]; month: MonthRow[]; start: string; end: string }
type LoadState = { kind: "loading" } | { kind: "error"; message: string } | { kind: "ready"; data: ViewData };

export function WarehouseOverviewEntry() {
  const { user } = useAuth();
  if (user?.role !== "warehouse_admin" || user.warehouses.length < 2) return null;
  return <Link href="/warehouse-overview" prefetch={false}
    className="absolute -top-1 right-0 inline-flex min-h-[44px] items-center rounded-lg border border-blue-200 bg-white px-4 text-blue-700 hover:bg-blue-50">全部仓汇总</Link>;
}

function record(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}
function count(value: unknown): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0;
}
function cents(value: unknown): bigint {
  if (typeof value !== "string" && typeof value !== "number") throw new Error("金额数据格式不正确");
  const match = /^(-?)(\d+)(?:\.(\d{1,2}))?$/.exec(String(value));
  if (!match) throw new Error("金额数据格式不正确");
  return (BigInt(match[2]) * BigInt(100) + BigInt((match[3] || "").padEnd(2, "0"))) * BigInt(match[1] ? -1 : 1);
}
function money(value: bigint): string {
  const text = (value < BigInt(0) ? -value : value).toString().padStart(3, "0");
  return `${value < BigInt(0) ? "-" : ""}${text.slice(0, -2).replace(/\B(?=(\d{3})+(?!\d))/g, ",")}.${text.slice(-2)}`;
}
function amountMap(value: unknown): value is Amounts {
  if (!record(value)) return false;
  return Object.entries(value).every(([currency, amount]) => { cents(amount); return currency.length > 0; });
}
function amountList(value: unknown): value is TodayRow["income_by_currency"] {
  return Array.isArray(value) && value.every(item => record(item) && typeof item.currency === "string" && item.currency.length > 0
    && (cents(item.amount), true)) && new Set(value.map(item => item.currency)).size === value.length;
}
function validToday(value: unknown): value is TodayRow {
  if (!record(value) || !count(value.warehouse_id) || value.warehouse_id === 0 || typeof value.warehouse_name !== "string"
      || typeof value.has_data !== "boolean" || !record(value.todos) || !record(value.attendance)) return false;
  return amountList(value.income_by_currency) && amountList(value.expense_by_currency)
    && [...todoColumns.map(([key]) => key), "total"].every(key => count((value.todos as Record<string, unknown>)[key]))
    && count(value.attendance.actual) && count(value.attendance.expected);
}
function validMonth(value: unknown): value is MonthRow {
  if (!record(value) || !count(value.warehouse_id) || value.warehouse_id === 0 || typeof value.warehouse_name !== "string"
      || !amountMap(value.income_by_currency) || !amountMap(value.expense_by_currency)
      || !record(value.income_count_by_currency) || !record(value.expense_count_by_currency)) return false;
  return ["income", "expense"].every(kind => {
    const amounts = value[`${kind}_by_currency`] as Amounts;
    const counts = value[`${kind}_count_by_currency`] as Record<string, unknown>;
    return Object.keys(amounts).length === Object.keys(counts).length
      && Object.keys(amounts).every(currency => count(counts[currency]));
  });
}
function thaiPeriod() {
  const parts = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Bangkok", year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(new Date());
  const part = (kind: string) => parts.find(item => item.type === kind)!.value;
  return { start: `${part("year")}-${part("month")}-01`, end: `${part("year")}-${part("month")}-${part("day")}` };
}
function reason(value: unknown): string {
  if (typeof value === "string" && value.trim()) return value;
  if (Array.isArray(value)) return value.map(reason).join("；");
  if (record(value)) return reason(value.message || value.msg || value.detail);
  return "服务返回了无法读取的错误，请重试";
}
async function read(path: string, token: string, signal: AbortSignal): Promise<unknown> {
  const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "/api/v1"}${path}`, {
    method: "GET", headers: { Authorization: `Bearer ${token}`, "X-Warehouse-ID": "all", "X-Language": "zh" },
    signal, cache: "no-store",
  });
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) throw new Error(`请求失败（${response.status}）：${reason(record(body) ? body.detail : body)}`);
  if (!body) throw new Error("服务返回内容无法读取，请重试");
  return body;
}
function combine(groups: [string, bigint][][]) {
  const result = new Map<string, bigint>();
  groups.flat().forEach(([currency, amount]) => result.set(currency, (result.get(currency) || BigInt(0)) + amount));
  return [...result.entries()].sort(([a], [b]) => a.localeCompare(b));
}
function TodayMoney({ values }: { values: [string, bigint][] }) {
  return values.length ? <>{values.map(([currency, value]) => <span key={currency} className="block whitespace-nowrap">{({ THB: "฿", CNY: "¥" } as Record<string, string>)[currency] || currency} {money(value)}</span>)}</> : <>0</>;
}
function MonthlyMoney({ values, counts }: { values: [string, bigint][]; counts: Record<string, number> }) {
  return values.length ? <>{values.map(([currency, value]) => <span key={currency} className="block whitespace-nowrap">{({ THB: "฿", CNY: "¥" } as Record<string, string>)[currency] || currency} {money(value)}（{counts[currency]}笔）</span>)}</> : <>0（0笔）</>;
}
const cell = "border-b border-gray-200 px-4 py-3 text-left align-top";

function OverviewTables({ data, enter }: { data: ViewData; enter: (id: number) => void }) {
  const populated = data.today.filter(row => row.has_data);
  const ids = new Set(populated.map(row => row.warehouse_id));
  const monthly = data.month.filter(row => ids.has(row.warehouse_id));
  const dailyAmounts = (row: TodayRow, kind: "income" | "expense"): [string, bigint][] => row[`${kind}_by_currency`].map(item => [item.currency, cents(item.amount)]);
  const monthAmounts = (row: MonthRow, kind: "income" | "expense"): [string, bigint][] => Object.entries(row[`${kind}_by_currency`]).sort(([a], [b]) => a.localeCompare(b)).map(([currency, amount]) => [currency, cents(amount)]);
  const monthlyCounts = (kind: "income" | "expense") => {
    const result: Record<string, number> = {};
    monthly.forEach(row => Object.entries(row[`${kind}_count_by_currency`]).forEach(([currency, n]) => { result[currency] = (result[currency] || 0) + n; }));
    return result;
  };
  const enterLink = (row: TodayRow | MonthRow) => <a href="/dashboard" className="whitespace-nowrap text-blue-700 underline" onClick={event => { event.preventDefault(); enter(row.warehouse_id); }}>进入这个仓</a>;
  return <>
    <section>
      <h2 className="mb-3 text-lg font-semibold text-gray-900">今日对比</h2>
      <div role="region" aria-label="今日对比表格，可横向滚动" tabIndex={0} className="overflow-x-auto rounded-lg border border-gray-200 bg-white">
        <table className="w-full min-w-[1550px] text-sm tabular-nums">
          <thead className="bg-gray-100 text-gray-700"><tr>{["仓库", "今日收入", "今日支出", ...todoColumns.map(([, name]) => name), "待办合计", "出勤（实到 / 应到）", "操作"].map(name => <th scope="col" className={`${cell} whitespace-nowrap`} key={name}>{name}</th>)}</tr></thead>
          <tbody>{data.today.map(row => <tr key={row.warehouse_id}><th scope="row" className={`${cell} whitespace-nowrap font-medium`}>{row.warehouse_name}</th>
            {row.has_data ? <><td className={cell}><TodayMoney values={dailyAmounts(row, "income")} /></td><td className={cell}><TodayMoney values={dailyAmounts(row, "expense")} /></td>{todoColumns.map(([key]) => <td key={key} className={cell}>{row.todos[key]}</td>)}<td className={`${cell} font-semibold`}>{row.todos.total}</td><td className={`${cell} whitespace-nowrap`}>{row.attendance.actual} / {row.attendance.expected}</td></> : <td className={`${cell} text-gray-500`} colSpan={10}>暂无数据</td>}
            <td className={cell}>{enterLink(row)}</td></tr>)}</tbody>
          <tfoot className="bg-gray-50 font-semibold"><tr><th scope="row" className={cell}>合计</th><td className={cell}><TodayMoney values={combine(populated.map(row => dailyAmounts(row, "income")))} /></td><td className={cell}><TodayMoney values={combine(populated.map(row => dailyAmounts(row, "expense")))} /></td>{todoColumns.map(([key]) => <td key={key} className={cell}>{populated.reduce((sum, row) => sum + row.todos[key], 0)}</td>)}<td className={cell}>{populated.reduce((sum, row) => sum + row.todos.total, 0)}</td><td className={`${cell} whitespace-nowrap`}>{populated.reduce((sum, row) => sum + row.attendance.actual, 0)} / {populated.reduce((sum, row) => sum + row.attendance.expected, 0)}</td><td className={cell}>—</td></tr></tfoot>
        </table>
      </div>
    </section>
    <section className="mt-8">
      <h2 className="mb-1 text-lg font-semibold text-gray-900">本月对比</h2>
      <p className="mb-3 text-sm text-gray-500">{data.start} 至 {data.end}（泰国时间）</p>
      <div role="region" aria-label="本月对比表格，可横向滚动" tabIndex={0} className="overflow-x-auto rounded-lg border border-gray-200 bg-white">
        <table className="w-full min-w-[850px] text-sm tabular-nums"><thead className="bg-gray-100 text-gray-700"><tr>{["仓库", "本月收入（分币种、笔数）", "本月支出（分币种、笔数）", "操作"].map(name => <th scope="col" className={`${cell} whitespace-nowrap`} key={name}>{name}</th>)}</tr></thead>
          <tbody>{data.month.map(row => <tr key={row.warehouse_id}><th scope="row" className={`${cell} whitespace-nowrap font-medium`}>{row.warehouse_name}</th>{ids.has(row.warehouse_id) ? <><td className={cell}><MonthlyMoney values={monthAmounts(row, "income")} counts={row.income_count_by_currency} /></td><td className={cell}><MonthlyMoney values={monthAmounts(row, "expense")} counts={row.expense_count_by_currency} /></td></> : <td className={`${cell} text-gray-500`} colSpan={2}>暂无数据</td>}<td className={cell}>{enterLink(row)}</td></tr>)}</tbody>
          <tfoot className="bg-gray-50 font-semibold"><tr><th scope="row" className={cell}>合计</th><td className={cell}><MonthlyMoney values={combine(monthly.map(row => monthAmounts(row, "income")))} counts={monthlyCounts("income")} /></td><td className={cell}><MonthlyMoney values={combine(monthly.map(row => monthAmounts(row, "expense")))} counts={monthlyCounts("expense")} /></td><td className={cell}>—</td></tr></tfoot>
        </table>
      </div>
    </section>
  </>;
}

export default function WarehouseOverview() {
  const { user, loading } = useAuth();
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [owner, setOwner] = useState<number | null>(null);
  const [attempt, setAttempt] = useState(0);
  const entering = useRef(false);
  useEffect(() => {
    const controller = new AbortController();
    const token = getToken();
    setOwner(user?.id ?? null);
    setState({ kind: "loading" });
    if (loading || user?.role !== "warehouse_admin" || !token) return () => controller.abort();
    const period = thaiPeriod();
    Promise.all([read("/dashboard/warehouse-cards", token, controller.signal), read(`/dashboard/warehouse-summary?start_date=${period.start}&end_date=${period.end}`, token, controller.signal)]).then(([today, month]) => {
      if (controller.signal.aborted || token !== getToken()) return;
      if (!record(today) || !Array.isArray(today.data) || !today.data.every(validToday)
          || !record(month) || !Array.isArray(month.data) || !month.data.every(validMonth)
          || month.start_date !== period.start || month.end_date !== period.end) throw new Error("汇总数据格式不正确，请重试");
      const monthly = new Map(month.data.map(row => [row.warehouse_id, row]));
      if (monthly.size !== month.data.length || new Set(today.data.map(row => row.warehouse_id)).size !== today.data.length
          || today.data.length !== monthly.size || today.data.some(row => !monthly.has(row.warehouse_id))) throw new Error("两张表的仓库范围不一致，请重试");
      setState({ kind: "ready", data: { today: today.data, month: today.data.map(row => monthly.get(row.warehouse_id)!), ...period } });
    }).catch((error: unknown) => {
      if (controller.signal.aborted || token !== getToken()) return;
      setState({ kind: "error", message: error instanceof TypeError ? "无法连接服务，请稍后重试" : error instanceof Error ? error.message : "加载失败，请重试" });
    });
    return () => controller.abort();
  }, [user?.id, user?.role, loading, attempt]);
  function enter(id: number) {
    if (entering.current) return;
    entering.current = true;
    setActiveWarehouseId(id);
    window.dispatchEvent(new CustomEvent("warehouse-changed", { detail: { warehouseId: id } }));
    window.location.assign("/dashboard");
  }
  if (!loading && user && user.role !== "warehouse_admin") return <p role="status" className="text-gray-700">仅仓库管理员可查看全部仓汇总</p>;
  return <section className="min-w-0 text-gray-900">
    <div className="mb-6 flex flex-wrap items-center justify-between gap-3"><h1 className="text-2xl font-bold">全部仓汇总 只读</h1><Link href="/select-warehouse" prefetch={false} className="inline-flex min-h-[44px] items-center rounded-lg border border-gray-300 bg-white px-4 text-blue-700">返回仓选择页</Link></div>
    {loading || !user || owner !== user.id || state.kind === "loading" ? <p role="status">加载中…</p> : state.kind === "error" ? <div role="alert"><p className="break-words text-red-700">{state.message}</p><button type="button" onClick={() => setAttempt(value => value + 1)} className="mt-3 min-h-[44px] rounded-lg border border-gray-300 bg-white px-4">重试</button></div> : state.data.today.length === 0 ? <p role="status">你名下还没有仓库 请联系平台管理员分配</p> : <OverviewTables data={state.data} enter={enter} />}
  </section>;
}

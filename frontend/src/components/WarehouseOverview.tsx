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
const todoDotColors: Record<string, string> = {
  employee_advances: "bg-blue-600",
  overtime_employee_confirmation: "bg-rose-500",
  overtime_admin_verification: "bg-violet-600",
  expense_fund_review: "bg-amber-500",
  purchase_approval: "bg-indigo-600",
  receipt_review: "bg-teal-600",
};
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
interface ChartMonth {
  month: string;
  income_by_currency: Amounts;
  expense_by_currency: Amounts;
  expense_by_warehouse: { warehouse_id: number; warehouse_name: string; currency: string; amount: Amount }[];
}
interface OverviewCharts {
  as_of: string;
  months: ChartMonth[];
  yesterday_expense_by_warehouse: { warehouse_id: number; expense_by_currency: Amounts }[];
}
interface ViewData { today: TodayRow[]; month: MonthRow[]; start: string; end: string; charts: OverviewCharts }
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
function validCharts(value: unknown): value is OverviewCharts {
  if (!record(value) || typeof value.as_of !== "string" || !Number.isFinite(Date.parse(value.as_of))
      || !Array.isArray(value.months) || value.months.length !== 6
      || !Array.isArray(value.yesterday_expense_by_warehouse)) return false;
  const chartMonths = value.months;
  const yesterdayRows = value.yesterday_expense_by_warehouse;
  const monthsValid = chartMonths.every((item, index) => record(item)
    && typeof item.month === "string" && /^\d{4}-\d{2}$/.test(item.month)
    && (index === 0 || item.month > String((chartMonths[index - 1] as Record<string, unknown>).month))
    && amountMap(item.income_by_currency) && amountMap(item.expense_by_currency)
    && Array.isArray(item.expense_by_warehouse)
    && item.expense_by_warehouse.every(row => record(row) && count(row.warehouse_id) && row.warehouse_id > 0
      && typeof row.warehouse_name === "string" && typeof row.currency === "string" && !!row.currency
      && (cents(row.amount), true)));
  const yesterdayValid = yesterdayRows.every(row => record(row)
    && count(row.warehouse_id) && row.warehouse_id > 0 && amountMap(row.expense_by_currency));
  return monthsValid && yesterdayValid;
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

const currencySymbols: Record<string, string> = { THB: "฿", CNY: "¥" };
const chartColors = ["#2563eb", "#0f766e", "#7c3aed", "#d97706", "#db2777", "#64748b"];
function currencyLabel(currency: string) { return currencySymbols[currency] || currency; }
function numberMoney(value: number) { return value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }); }
function SignedMoney({ value, currency }: { value: bigint; currency: string }) {
  const color = value > BigInt(0) ? "text-red-600" : value < BigInt(0) ? "text-green-700" : "text-gray-500";
  const sign = value > BigInt(0) ? "+" : value < BigInt(0) ? "−" : "";
  return <span className={`whitespace-nowrap ${color}`}>{currencyLabel(currency)} {sign}{money(value < BigInt(0) ? -value : value)}</span>;
}

function TrendChart({ currency, months }: { currency: string; months: ChartMonth[] }) {
  const [hovered, setHovered] = useState<number | null>(null);
  const income = months.map(row => cents(row.income_by_currency[currency] ?? 0));
  const expense = months.map(row => cents(row.expense_by_currency[currency] ?? 0));
  const width = 720, height = 230, left = 46, right = 16, top = 16, bottom = 35;
  const chartWidth = width - left - right, chartHeight = height - top - bottom;
  const maxValue = [...income, ...expense].reduce((value, item) => item > value ? item : value, BigInt(0));
  const max = maxValue > BigInt(0) ? maxValue : BigInt(100);
  const x = (index: number) => left + (months.length < 2 ? chartWidth / 2 : (index * chartWidth) / (months.length - 1));
  const y = (amount: bigint) => top + chartHeight - (Number(amount) / Number(max)) * chartHeight;
  const incomePoints = income.map((amount, index) => `${x(index)},${y(amount)}`).join(" ");
  const expensePoints = expense.map((amount, index) => `${x(index)},${y(amount)}`).join(" ");
  const symbol = currencyLabel(currency);
  return <section className="min-w-0 rounded-xl border border-gray-100 bg-white p-4 shadow-sm">
    <h3 className="mb-2 font-semibold text-gray-900">近六个月 · {symbol}</h3>
    <div className="relative h-[200px] w-full sm:h-[230px]" onMouseLeave={() => setHovered(null)}>
      <svg className="h-full w-full overflow-visible" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${currency}近六个月收入和支出折线图`}>
        {[0, 0.5, 1].map((ratio, index) => {
          const gy = top + chartHeight * ratio;
          return <g key={index}><line x1={left} x2={width - right} y1={gy} y2={gy} stroke="#e5e7eb" strokeDasharray="3 4" />
            <text x={left - 7} y={gy + 4} textAnchor="end" fontSize="10" fill="#6b7280">{numberMoney((Number(max) / 100) * (1 - ratio))}</text></g>;
        })}
        <polyline points={incomePoints} fill="none" stroke="#2563eb" strokeWidth="3" strokeLinejoin="round" strokeLinecap="round" />
        <polyline points={expensePoints} fill="none" stroke="#d97706" strokeWidth="3" strokeLinejoin="round" strokeLinecap="round" />
        {months.map((row, index) => {
          const inc = income[index], exp = expense[index], net = inc - exp;
          const tip = `${row.month}\n收入 ${symbol} ${money(inc)}\n支出 ${symbol} ${money(exp)}\n净额 ${symbol} ${money(net)}`;
          return <g key={row.month}>
            <circle cx={x(index)} cy={y(inc)} r="5" fill="#2563eb" stroke="white" strokeWidth="2" tabIndex={0} role="button" aria-label={tip}
              onMouseEnter={() => setHovered(index)} onFocus={() => setHovered(index)} onBlur={() => setHovered(null)}><title>{tip}</title></circle>
            <circle cx={x(index)} cy={y(exp)} r="5" fill="#d97706" stroke="white" strokeWidth="2" tabIndex={0} role="button" aria-label={tip}
              onMouseEnter={() => setHovered(index)} onFocus={() => setHovered(index)} onBlur={() => setHovered(null)}><title>{tip}</title></circle>
            <text x={x(index)} y={height - 9} textAnchor="middle" fontSize="10" fill="#4b5563">{row.month.slice(5)}月</text>
          </g>;
        })}
      </svg>
      {hovered !== null && <div role="tooltip" className="pointer-events-none absolute left-1/2 top-2 z-10 -translate-x-1/2 rounded-lg border border-gray-200 bg-white px-3 py-2 text-xs leading-5 text-gray-800 shadow-lg">
        <div className="font-semibold">{months[hovered].month}</div>
        <div>收入 {symbol} {money(income[hovered])}</div>
        <div>支出 {symbol} {money(expense[hovered])}</div>
        <div>净额 {symbol} {money(income[hovered] - expense[hovered])}</div>
      </div>}
    </div>
    <div className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-sm text-gray-700">
      <span className="inline-flex items-center gap-2"><i className="h-2.5 w-2.5 rounded-full bg-blue-600" />收入</span>
      <span className="inline-flex items-center gap-2"><i className="h-2.5 w-2.5 rounded-full bg-amber-600" />支出</span>
      <span className="text-xs text-gray-500">悬停数据点可查看收入、支出和净额</span>
    </div>
  </section>;
}

function DonutChart({ currency, rows: warehouseRows }: { currency: string; rows: ChartMonth["expense_by_warehouse"] }) {
  const rows = warehouseRows.filter(row => row.currency === currency)
    .map(row => ({ name: row.warehouse_name, amount: cents(row.amount) }))
    .filter(row => row.amount > BigInt(0)).sort((a, b) => a.amount === b.amount ? a.name.localeCompare(b.name) : a.amount > b.amount ? -1 : 1);
  const visible = rows.slice(0, 5);
  const remainder = rows.slice(5).reduce((sum, row) => sum + row.amount, BigInt(0));
  if (remainder > BigInt(0)) visible.push({ name: "其他", amount: remainder });
  const total = visible.reduce((sum, row) => sum + row.amount, BigInt(0));
  let rounded = 0;
  const shares = visible.map((row, index) => {
    const hundredths = index === visible.length - 1 ? 10000 - rounded : Number((row.amount * BigInt(10000)) / total);
    const pct = hundredths / 100;
    rounded += hundredths;
    return { ...row, pct };
  });
  const circumference = 2 * Math.PI * 54;
  let offset = 0;
  const arcs = shares.map((row, index) => {
    const length = (row.pct / 100) * circumference;
    const current = { ...row, color: chartColors[index % chartColors.length], length, offset };
    offset += length;
    return current;
  });
  return <section className="min-w-0 rounded-xl border border-gray-100 bg-white p-4 shadow-sm">
    <h3 className="font-semibold text-gray-900">本月支出占比 · {currencyLabel(currency)}</h3>
    {!total ? <p className="flex h-[200px] items-center justify-center text-sm text-gray-500">本月暂无支出</p> : <div className="flex min-h-[200px] flex-col items-center justify-center gap-3 sm:min-h-[230px]">
      <svg className="h-[170px] w-[170px] shrink-0" viewBox="0 0 140 140" role="img" aria-label={`${currency}各仓本月支出占比`}>
        <circle cx="70" cy="70" r="54" fill="none" stroke="#e5e7eb" strokeWidth="24" />
        {arcs.map(row => <circle key={row.name} cx="70" cy="70" r="54" fill="none" stroke={row.color} strokeWidth="24"
          strokeDasharray={`${row.length} ${circumference - row.length}`} strokeDashoffset={-row.offset} transform="rotate(-90 70 70)">
          <title>{`${row.name}：${currencyLabel(currency)} ${money(row.amount)}，${row.pct.toFixed(2)}%`}</title>
        </circle>)}
        <text x="70" y="66" textAnchor="middle" fontSize="11" fill="#6b7280">合计</text>
        <text x="70" y="83" textAnchor="middle" fontSize="13" fontWeight="600" fill="#111827">{currencyLabel(currency)} {money(total)}</text>
      </svg>
      <ul className="grid w-full grid-cols-1 gap-1 text-sm sm:grid-cols-2">{arcs.map(row => <li key={row.name} className="flex min-w-0 items-center gap-2">
        <i className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ backgroundColor: row.color }} />
        <span className="min-w-0 flex-1 truncate" title={row.name}>{row.name}</span>
        <span className="whitespace-nowrap tabular-nums text-gray-600">{money(row.amount)} · {row.pct.toFixed(2)}%</span>
      </li>)}</ul>
    </div>}
  </section>;
}

function ChartPanels({ data }: { data: ViewData }) {
  const currencies = [...new Set(["THB", "CNY", ...data.charts.months.flatMap(row => [...Object.keys(row.income_by_currency), ...Object.keys(row.expense_by_currency)])])];
  const asOf = new Intl.DateTimeFormat("zh-CN", { timeZone: "Asia/Bangkok", hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date(data.charts.as_of));
  return <>
    <p className="mb-4 text-sm text-gray-500">数据截至今天 {asOf}（泰国时间）</p>
    <section className="mb-8"><h2 className="mb-3 text-lg font-semibold text-gray-900">近六个月收支趋势</h2>
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">{currencies.map(currency => <TrendChart key={currency} currency={currency} months={data.charts.months} />)}</div>
    </section>
    <section className="mb-8"><h2 className="mb-3 text-lg font-semibold text-gray-900">本月至今各仓支出占比（按币种分开）</h2>
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">{currencies.map(currency => <DonutChart key={currency} currency={currency} rows={data.charts.months[data.charts.months.length - 1].expense_by_warehouse} />)}</div>
    </section>
  </>;
}

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
          <tbody>{data.today.map(row => {
            const yesterday = data.charts.yesterday_expense_by_warehouse.find(item => item.warehouse_id === row.warehouse_id)?.expense_by_currency || {};
            const todayExpense = Object.fromEntries(dailyAmounts(row, "expense"));
            const compareCurrencies = [...new Set([...Object.keys(todayExpense), ...Object.keys(yesterday)])].sort();
            return <tr key={row.warehouse_id}><th scope="row" className={`${cell} whitespace-nowrap font-medium`}>{row.warehouse_name}</th>
            {row.has_data ? <><td className={cell}><TodayMoney values={dailyAmounts(row, "income")} /></td><td className={cell}><TodayMoney values={dailyAmounts(row, "expense")} />
              <span className="mt-1 block space-y-0.5 text-xs">{compareCurrencies.length ? compareCurrencies.map(currency => <span key={currency} className="block">较昨日 <SignedMoney value={(todayExpense[currency] ?? BigInt(0)) - cents(yesterday[currency] ?? 0)} currency={currency} /></span>) : <span className="text-gray-500">较昨日持平</span>}</span>
            </td>{todoColumns.map(([key]) => <td key={key} className={cell}><span className={`mr-2 inline-block h-2 w-2 rounded-full ${todoDotColors[key]}`} aria-hidden="true" />{row.todos[key]}</td>)}<td className={`${cell} font-semibold`}>{row.todos.total}</td><td className={`${cell} whitespace-nowrap`}>{row.attendance.actual} / {row.attendance.expected}</td></> : <td className={`${cell} text-gray-500`} colSpan={10}>暂无数据</td>}
            <td className={cell}>{enterLink(row)}</td></tr>;
          })}</tbody>
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
    Promise.all([read("/dashboard/warehouse-cards", token, controller.signal), read(`/dashboard/warehouse-summary?start_date=${period.start}&end_date=${period.end}&include_charts=true`, token, controller.signal)]).then(([today, month]) => {
      if (controller.signal.aborted || token !== getToken()) return;
      if (!record(today) || !Array.isArray(today.data) || !today.data.every(validToday)
          || !record(month) || !Array.isArray(month.data) || !month.data.every(validMonth)
          || month.start_date !== period.start || month.end_date !== period.end) throw new Error("汇总数据格式不正确，请重试");
      const monthly = new Map(month.data.map(row => [row.warehouse_id, row]));
      if (monthly.size !== month.data.length || new Set(today.data.map(row => row.warehouse_id)).size !== today.data.length
          || today.data.length !== monthly.size || today.data.some(row => !monthly.has(row.warehouse_id))) throw new Error("两张表的仓库范围不一致，请重试");
      if (!validCharts(month.overview_charts)) throw new Error("图表数据格式不正确，请重试");
      setState({ kind: "ready", data: { today: today.data, month: today.data.map(row => monthly.get(row.warehouse_id)!), charts: month.overview_charts, ...period } });
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
    <div className="mb-2 flex flex-wrap items-center justify-between gap-3"><h1 className="text-2xl font-bold">全部仓总览</h1><Link href="/select-warehouse" prefetch={false} className="inline-flex min-h-[44px] items-center rounded-lg border border-gray-300 bg-white px-4 text-blue-700">返回仓选择页</Link></div>
    <p className="mb-4 text-sm text-gray-500">只读 这里不能改任何数据</p>
    {loading || !user || owner !== user.id || state.kind === "loading" ? <p role="status">加载中…</p> : state.kind === "error" ? <div role="alert"><p className="break-words text-red-700">{state.message}</p><button type="button" onClick={() => setAttempt(value => value + 1)} className="mt-3 min-h-[44px] rounded-lg border border-gray-300 bg-white px-4">重试</button></div> : state.data.today.length === 0 ? <p role="status">你名下还没有仓库 请联系平台管理员分配</p> : <><ChartPanels data={state.data} /><OverviewTables data={state.data} enter={enter} /></>}
  </section>;
}

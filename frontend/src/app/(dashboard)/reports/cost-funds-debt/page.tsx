"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { FileText, ChevronDown, ChevronUp } from "lucide-react";

type Totals = { amount: number; repaid_amount: number; outstanding_amount: number };
interface Cost { name: string; count: number; amount: number }
interface Account { account_id: number; account_name: string; opening_balance: number; inflow: number; outflow: number; closing_balance: number }
interface Detail { id: number; source: string; source_id: number; date: string; category_name: string; amount: number; funding_source: string; cash_advance_id: number | null; reimbursement_id: number | null; payroll_record_id: number | null; remark: string | null }
interface Block {
  currency: string; symbol: string;
  costs: { data: Cost[]; count: number; total: number };
  funds: { data: Account[]; total: Omit<Account, "account_id" | "account_name">; unassigned: { inflow: number; outflow: number } };
  debt: { data: (Totals & { key: string; payer_id: number | null; payer_name: string; count: number })[]; total: Totals };
  reconciliation: { cost_total: number; company_outflow: number; difference: number; cash_advance_cost: number; expense_fund_cost: number; non_company_cost: number; unreconciled_difference: number; balanced: boolean; non_cost_outflows: { name: string; count: number; amount: number }[]; details: Detail[]; detail_count: number };
}
interface Report { start_date: string; end_date: string; currencies: Block[]; notes: string[]; balance_anchor_date: string; undated_flows: { currency: string; source: string; count: number; amount: number }[] }
function today() { return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Bangkok", year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date()); }
function thisMonth() { const end_date = today(); return { start_date: `${end_date.slice(0, 7)}-01`, end_date }; }
function lastWeek() { const now = new Date(`${today()}T12:00:00+07:00`); const monday = new Date(now); monday.setUTCDate(now.getUTCDate() - (now.getUTCDay() + 6) % 7); const end = new Date(monday); end.setUTCDate(monday.getUTCDate() - 1); const start = new Date(monday); start.setUTCDate(monday.getUTCDate() - 7); return { start_date: start.toISOString().slice(0, 10), end_date: end.toISOString().slice(0, 10) }; }
const amount = (v: number, symbol: string) => `${symbol}${Number(v || 0).toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

export default function CostFundsDebtPage() {
  const [range, setRange] = useState(thisMonth), [ready, setReady] = useState(false);
  const [data, setData] = useState<Report | null>(null), [loading, setLoading] = useState(true), [error, setError] = useState("");
  const [open, setOpen] = useState<string | null>(null), [retry, setRetry] = useState(0);
  useEffect(() => { const q = new URLSearchParams(window.location.search); if (q.get("start_date") && q.get("end_date")) setRange({ start_date: q.get("start_date")!, end_date: q.get("end_date")! }); setReady(true); }, []);
  useEffect(() => {
    if (!ready) return;
    if (!range.start_date || !range.end_date) { setData(null); setError("请选择完整日期范围"); setLoading(false); return; }
    let active = true;
    setLoading(true); setError(""); setData(null); setOpen(null);
    api.get<Report>(`/reports/cost-funds-debt?${new URLSearchParams(range)}`).then(r => { if (active) setData(r); })
      .catch((e: any) => { if (active) setError(e.message || "报表加载失败"); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [ready, range, retry]);
  function href(path: string, cur: string, filters: Record<string, string> = {}) { return `${path}?${new URLSearchParams({ ...range, currency: cur, report_view: "1", ...filters })}`; }
  return <div className="space-y-5">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <h1 className="page-title flex items-center gap-2"><FileText size={24} />成本资金欠款</h1><Link href="/reports" className="text-sm text-blue-600">返回报表中心</Link>
    </div>
    <div className="bg-white rounded-xl border p-4 flex items-end flex-wrap gap-3">
      <label className="text-sm">开始日期<input aria-label="开始日期" type="date" className="form-input mt-1 w-36" value={range.start_date} onChange={e => setRange({ ...range, start_date: e.target.value })} /></label>
      <label className="text-sm">结束日期<input aria-label="结束日期" type="date" className="form-input mt-1 w-36" value={range.end_date} onChange={e => setRange({ ...range, end_date: e.target.value })} /></label>
      <button className="btn-secondary" onClick={() => setRange(thisMonth())}>本月</button><button className="btn-secondary" onClick={() => setRange(lastWeek())}>上周</button>
    </div>
    {loading && <p className="text-gray-500 py-8 text-center" role="status">正在核对三张账…</p>}
    {error && <div role="alert" className="bg-red-50 border border-red-200 text-red-700 rounded-xl p-4">{error}<button className="ml-3 underline" onClick={() => setRetry(n => n + 1)}>重试</button></div>}
    {data && data.currencies.map(block => {
      const { currency: cur, symbol: sym, costs, funds, debt, reconciliation: r } = block;
      const expanded = open === cur;
      return <section key={cur} className="space-y-4" aria-label={`${sym}三张账`}>
        <h2 className="text-xl font-semibold">{sym}</h2>
        <div className="bg-white border rounded-xl overflow-hidden">
          <h3 className="px-4 py-3 font-semibold border-b">成本线</h3>
          <div className="overflow-x-auto"><table className="w-full text-sm whitespace-nowrap"><thead className="bg-gray-50 text-gray-500"><tr><th className="text-left p-3">分类</th><th className="text-right p-3">笔数</th><th className="text-right p-3">金额</th></tr></thead><tbody>
            {costs.data.map(row => <tr key={row.name} className="border-t"><td className="p-3"><Link className="text-blue-600 hover:underline" href={href("/operating", cur, { cost_category: row.name })}>{row.name}</Link></td><td className="text-right p-3">{row.count}</td><td className="text-right p-3">{amount(row.amount, sym)}</td></tr>)}
            <tr className="border-t bg-gray-50 font-semibold"><td className="p-3"><Link href={href("/operating", cur)}>合计</Link></td><td className="text-right p-3">{costs.count}</td><td className="text-right p-3">{amount(costs.total, sym)}</td></tr>
          </tbody></table></div>
        </div>
        <div className="bg-white border rounded-xl overflow-hidden">
          <h3 className="px-4 py-3 font-semibold border-b">资金线</h3><p className="px-4 pt-3 text-xs text-gray-500">期初按 {data.balance_anchor_date} 月初登记余额与现存有效流水推算。</p>
          <div className="overflow-x-auto"><table className="w-full text-sm whitespace-nowrap"><thead className="bg-gray-50 text-gray-500"><tr>{["账户", "期初余额", "本期流入", "本期流出", "期末余额"].map(h => <th key={h} className={`p-3 ${h === "账户" ? "text-left" : "text-right"}`}>{h}</th>)}</tr></thead><tbody>
            {funds.data.map(row => <tr key={row.account_id} className="border-t"><td className="p-3"><Link className="text-blue-600 hover:underline" href={href("/ledger", cur, { account_id: String(row.account_id), flow_scope: "company" })}>{row.account_name}</Link></td>{(["opening_balance", "inflow", "outflow", "closing_balance"] as const).map(k => <td key={k} className="text-right p-3">{amount(row[k], sym)}</td>)}</tr>)}
            {!funds.data.length && <tr><td colSpan={5} className="p-4 text-gray-500">暂无账户</td></tr>}
            <tr className="border-t bg-gray-50 font-semibold"><td className="p-3">账户合计</td>{(["opening_balance", "inflow", "outflow", "closing_balance"] as const).map(k => <td key={k} className="text-right p-3">{amount(funds.total[k], sym)}</td>)}</tr>
          </tbody></table></div>
          {!!(funds.unassigned.inflow || funds.unassigned.outflow) && <p className="p-4 text-sm text-amber-700 bg-amber-50"><Link className="underline" href={href("/ledger", cur, { flow_scope: "company", unassigned: "true" })}>未指定账户</Link>：流入 {amount(funds.unassigned.inflow, sym)}，流出 {amount(funds.unassigned.outflow, sym)}。单列待核对，不计入任何账户余额；计入下方公司资金收付。</p>}
        </div>
        <div className="bg-white border rounded-xl overflow-hidden">
          <h3 className="px-4 py-3 font-semibold border-b">欠款</h3><p className="px-4 pt-3 text-xs text-gray-500">所选日期内已确认垫款的当前已还、未还金额，含已归还单。</p>
          <div className="overflow-x-auto"><table className="w-full text-sm whitespace-nowrap"><thead className="bg-gray-50 text-gray-500"><tr>{["垫款人", "垫了多少", "已经还了多少", "还欠多少"].map(h => <th key={h} className={`p-3 ${h === "垫款人" ? "text-left" : "text-right"}`}>{h}</th>)}</tr></thead><tbody>
            {debt.data.map(row => <tr key={row.key} className="border-t"><td className="p-3"><Link className="text-blue-600 hover:underline" href={href("/cash-advances", cur, row.payer_id !== null ? { payer_id: String(row.payer_id) } : { payer_name_exact: row.payer_name })}>{row.payer_name}</Link></td>{(["amount", "repaid_amount", "outstanding_amount"] as const).map(k => <td key={k} className="text-right p-3">{amount(row[k], sym)}</td>)}</tr>)}
            {!debt.data.length && <tr><td colSpan={4} className="p-4 text-gray-500">暂无已确认垫款</td></tr>}
            <tr className="border-t bg-gray-50 font-semibold"><td className="p-3">合计</td>{(["amount", "repaid_amount", "outstanding_amount"] as const).map(k => <td key={k} className="text-right p-3">{amount(debt.total[k], sym)}</td>)}</tr>
          </tbody></table></div>
        </div>
        <div className={`border rounded-xl p-4 space-y-3 ${r.balanced ? "bg-green-50 border-green-200" : "bg-red-50 border-red-200"}`} aria-label={`${sym}差异说明`}>
          <h3 className="font-semibold">差异说明</h3>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-sm">
            <p>成本合计<strong className="block text-xl mt-1">{amount(r.cost_total, sym)}</strong></p>
            <p>减：公司实际资金流出<strong className="block text-xl mt-1">{amount(r.company_outflow, sym)}</strong></p>
            <p>等于：差额<strong className="block text-xl mt-1">{amount(r.difference, sym)}</strong></p>
          </div>
          <p className="text-sm">垫款付掉的成本 {amount(r.cash_advance_cost, sym)} ＋ 备用金扣的成本 {amount(r.expense_fund_cost, sym)} ＝ {amount(r.non_company_cost, sym)}</p>
          <p className={`text-sm font-semibold ${r.balanced ? "text-green-800" : "text-red-700"}`}>{r.balanced ? "公式核对一致" : `未对平：差额与垫款、备用金成本相差 ${amount(r.unreconciled_difference, sym)}`}</p>
          {r.non_cost_outflows.map((row, i) => <p key={i} className="text-sm">另有 {row.name} {row.count} 笔，共 {amount(row.amount, sym)}，属于资金流出，不属于本期成本，会影响原公式。</p>)}
          {!r.balanced && <p className="text-xs text-red-700">保留原公式，不把非成本流出藏掉。除上述项目外，请核对非运营支出、历史无账户/无成本关联记录及跨期付款。</p>}
          <p className="text-xs text-gray-600">例：成本 {sym}10,000，公司账户流出 {sym}7,000，差额 {sym}3,000；若垫款和备用金成本合计也是 {sym}3,000，就能对上。</p>
          <button className="text-blue-700 flex items-center gap-1 text-sm font-medium" aria-expanded={expanded} onClick={() => setOpen(expanded ? null : cur)}>{expanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}查看垫款及备用金成本明细（{r.detail_count} 笔）</button>
          {expanded && <div className="overflow-x-auto bg-white rounded-lg"><table className="w-full text-sm whitespace-nowrap"><thead><tr>{["日期", "来源", "分类 / 关联单", "金额"].map(h => <th key={h} className="p-3 text-left">{h}</th>)}</tr></thead><tbody>
            {r.details.map(row => <tr key={`${row.source}-${row.source_id}`} className="border-t"><td className="p-3">{row.date}</td><td className="p-3">{row.funding_source === "cash_advance" ? `垫款单 #${row.cash_advance_id}` : row.source === "expense" ? row.remark || "备用金支付" : `备用金开销 #${row.source_id}`}</td><td className="p-3">{row.category_name}{row.reimbursement_id ? ` / 报销单 #${row.reimbursement_id}` : row.payroll_record_id ? ` / 工资单 #${row.payroll_record_id}` : ""}</td><td className="p-3 text-right">{amount(row.amount, sym)}</td></tr>)}
            {!r.details.length && <tr><td colSpan={4} className="p-4 text-gray-500">暂无垫款或备用金成本</td></tr>}
            <tr className="border-t font-semibold"><td colSpan={3} className="p-3">合计 {r.detail_count} 笔</td><td className="p-3 text-right">{amount(r.non_company_cost, sym)}</td></tr>
          </tbody></table></div>}
        </div>
      </section>;
    })}
    {data && <aside className="bg-white border rounded-xl p-4 text-xs text-gray-500 space-y-2">{data.notes.map((note, i) => <p key={i}>{note}</p>)}{data.undated_flows.map((row, i) => <p key={`undated-${i}`} className="text-amber-700">另有 {row.source} {row.count} 笔没有付款日期，金额 {amount(row.amount, row.currency === "CNY" ? "¥" : "฿")}，无法分配到日期范围，未混入本期数字。</p>)}</aside>}
  </div>;
}

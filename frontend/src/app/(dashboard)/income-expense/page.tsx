"use client";
import { confirmAccountBalance } from "@/lib/balanceWarning";
import InternalTransferSummary from "@/components/InternalTransferSummary";
import { useEffect, useRef, useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import { useI18n } from "@/hooks/useI18n";
import { useToast } from "@/components/ui/Toast";
import { api, getToken, getActiveWarehouseId } from "@/lib/api";
import { fmtMoney, fmtMoneyByCurrency } from "@/lib/currency";
import { useRouter } from "next/navigation";
import DataTable from "@/components/common/DataTable";
import { pendingWalletOperation, submitWalletOperation } from "@/lib/manualWallet";
import { useCostIdentity, emptyCost, type CostConfirmation } from "@/components/CostIdentity";

export default function IncomeExpensePage() {
  const cost = useCostIdentity();
  const { t } = useI18n();
  const { toast } = useToast(); const { user } = useAuth(); const router = useRouter();
  const [tab, setTab] = useState("income");
  const [data, setData] = useState<any[]>([]); const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const loadVersion = useRef(0);
  const now = new Date();
  const curMonth = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
  const todayStr = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
  const [dateRange, setDateRange] = useState({ start_date: `${curMonth}-01`, end_date: todayStr });
  const [totals, setTotals] = useState<any>({ total_income: 0, total_expense: 0, net: 0, income_by_currency: {}, expense_by_currency: {} });
  const [showForm, setShowForm] = useState(false);
  const [categories, setCategories] = useState<any[]>([]);
  const [accounts, setAccounts] = useState<any[]>([]);
  const [form, setForm] = useState({ category_id: 0, account_id: 0, amount: "" as string | number, currency: "THB", date: "", remark: "" });

  useEffect(() => { if (!getToken()) router.push("/login"); load(); loadRefs(); return () => { loadVersion.current += 1; }; }, [page, tab, dateRange]);

  async function load() {
    const version = ++loadVersion.current;
    const ep = tab === "income" ? "/income-expense/income" : "/income-expense/expense";
    const [res, s] = await Promise.all([
      api.get<any>(`${ep}?page=${page}&page_size=25&start_date=${dateRange.start_date}&end_date=${dateRange.end_date}`),
      api.get<any>(`/income-expense/monthly-summary?start_date=${dateRange.start_date}&end_date=${dateRange.end_date}`),
    ]);
    if (version !== loadVersion.current) return;
    setData(res.data); setTotal(res.total);
    setTotals(s);
  }

  async function loadRefs() {
    try {
      const cats = await api.get<any>(`/income-expense/categories?type=${tab}`);
      setCategories(cats.data);
      const accs = await api.get<any>("/accounts");
      setAccounts(accs.data);
    } catch {}
  }

  async function handleCreate(costConfirmation?: CostConfirmation) {
    try {
      if(tab==='expense'&&Number(form.amount)>0&&!await confirmAccountBalance(api,form.account_id,form.amount))return;
      const result = await submitWalletOperation(tab === "income" ? "income" : "expense", { ...form, ...(tab === "expense" ? cost.payload() : {}), amount: form.amount || 0, [tab === "income" ? "income_date" : "expense_date"]: form.date }, [], costConfirmation);
      toast("success", result.message || "创建成功");
      setShowForm(false); load();
    } catch (err: any) { if (tab !== "expense" || !cost.capture(err, data => handleCreate(data))) toast("error", err.message || "创建失败"); }
  }

  function openCreate() {
    try {
      const kind = tab === "income" ? "income" : "expense";
      const pending = pendingWalletOperation(kind)?.payload;
      cost.reset();
      if (pending) {
        setForm({ category_id: pending.category_id, account_id: pending.account_id, amount: String(pending.amount), currency: pending.currency, date: pending[`${kind}_date`], remark: pending.remark || "" });
        if (kind === "expense") cost.reset({ supplier_id: pending.supplier_id || 0, invoice: pending.invoice_identity ? JSON.parse(pending.invoice_identity) : emptyCost().invoice });
        toast("error", "已恢复上一笔结果待确认的收付，请重试，不要另建");
      }
      loadRefs(); setShowForm(true);
    } catch (err: any) { toast("error", err.message); }
  }

  async function handleExport() {
    try {
      const headers: Record<string,string> = { Authorization: `Bearer ${getToken()}` };
      const warehouse = getActiveWarehouseId();
      if (warehouse !== null) headers["X-Warehouse-ID"] = warehouse;
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "/api/v1"}/income-expense/${tab}/export?start_date=${dateRange.start_date}&end_date=${dateRange.end_date}`, { headers });
      if (!res.ok) throw new Error((await res.json()).detail || "导出失败");
      const url = URL.createObjectURL(await res.blob());
      const a = document.createElement("a"); a.href = url; a.download = `wallet_${tab}_${dateRange.start_date}_${dateRange.end_date}.xlsx`; a.click(); URL.revokeObjectURL(url);
      toast("success", "导出成功");
    } catch (err: any) { toast("error", err.message || "导出失败"); }
  }

  const columns = [
    { key: tab === "income" ? "income_date" : "expense_date", label: "日期", render: (v: string) => v?.slice(0,10) },
    { key: "category_name", label: "类别" },
    { key: "account_name", label: "账户" },
    { key: tab === "income" ? "customer_name" : "supplier_name", label: "对象" },
    { key: "amount", label: "金额", render: (v: number, row: any) => fmtMoney(v, row.currency) },
    { key: "currency", label: "币种" },
    { key: "remark", label: "备注" },
    { key: "ref_no", label: "来源", render: (_: string, row: any) => <div className="text-xs whitespace-nowrap">{row.source_link ? <a href={row.source_link} className="text-primary hover:underline">{row.source_label} {row.ref_no}</a> : <span>{row.source_label} {row.ref_no}</span>}{row.is_read_only && <div className="text-gray-400">业务联动，只读</div>}</div> },
  ];

  return (
    <>
      {cost.dialog}
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="page-title">{t("income_expense")}</h1>
          <p className="text-xs text-gray-500 mt-1">公司钱包实际收付款，内部转账不计收支</p>
          <div className="flex gap-6 mt-2 text-sm flex-wrap">
            <span className="text-green-600">收入: {fmtMoneyByCurrency(totals.income_by_currency)}</span>
            <span className="text-red-600">支出: {fmtMoneyByCurrency(totals.expense_by_currency)}</span>
            <span className={totals.net >= 0 ? "text-blue-600" : "text-red-600"}>净额: {(() => { const all = new Set([...Object.keys(totals.income_by_currency || {}), ...Object.keys(totals.expense_by_currency || {})]); const m: any = {}; all.forEach((c: string) => m[c] = (totals.income_by_currency?.[c] || 0) - (totals.expense_by_currency?.[c] || 0)); return fmtMoneyByCurrency(m); })()}</span>
          </div>
        </div>
        <div className="flex gap-2 shrink-0"><button onClick={handleExport} className="btn-secondary whitespace-nowrap">导出</button><button onClick={openCreate} className="btn-primary whitespace-nowrap">新建记录</button></div>
      </div>
      <InternalTransferSummary data={totals.internal_transfers} />
      <div className="flex items-center gap-3 mb-4 flex-wrap">
        <div className="bg-white rounded-lg p-1 flex"><button onClick={() => { setTab("income"); setPage(1); }} className={`px-4 py-1.5 rounded text-sm ${tab === "income" ? "bg-primary text-white" : ""}`}>收款</button><button onClick={() => { setTab("expense"); setPage(1); }} className={`px-4 py-1.5 rounded text-sm ${tab === "expense" ? "bg-primary text-white" : ""}`}>付款</button></div>
        <input type="date" value={dateRange.start_date} onChange={e => { setDateRange({ ...dateRange, start_date: e.target.value }); setPage(1); }} className="border border-gray-300 rounded-lg px-3 py-2 text-sm" />
        <span className="text-gray-400 text-xs">至</span>
        <input type="date" value={dateRange.end_date} onChange={e => { setDateRange({ ...dateRange, end_date: e.target.value }); setPage(1); }} className="border border-gray-300 rounded-lg px-3 py-2 text-sm" />
      </div>
      <DataTable columns={columns} data={data} total={total} page={page} pageSize={25} onPageChange={setPage} />
      {showForm && (
        <div className="modal-overlay">
          <div className="bg-white rounded-xl w-full max-w-md p-6 max-h-[90vh] overflow-y-auto">
            <h2 className="text-lg font-semibold mb-4">{tab === "income" ? "新建收款" : "新建付款"}</h2>
            <div className="space-y-3">
              {tab === "expense" && cost.fields}
              <div><label className="block text-sm mb-1">类别</label><select className="form-input" value={form.category_id} onChange={e => setForm({...form, category_id: +e.target.value})}><option>选择类别</option>{categories.map((c: any) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></div>
              <div><label className="block text-sm mb-1">收款账户</label><select className="form-input" value={form.account_id} onChange={e => setForm({...form, account_id: +e.target.value})}><option>选择账户</option>{accounts.map((a: any) => <option key={a.id} value={a.id}>{a.account_name} ({a.account_type})</option>)}</select></div>
              <div><label className="block text-sm mb-1">日期</label><input type="date" className="form-input" value={form.date} onChange={e => setForm({...form, date: e.target.value})} /></div>
              <div><label className="block text-sm mb-1">金额</label><input type="number" step="0.01" className="form-input" value={form.amount} onChange={e => setForm({...form, amount: e.target.value===""?"":+e.target.value})} /></div>
              <div><label className="block text-sm mb-1">币种</label><select className="form-input" value={form.currency} onChange={e => setForm({...form, currency: e.target.value})}><option value="THB">THB</option><option value="CNY">CNY</option></select></div>
              <div><label className="block text-sm mb-1">备注</label><input className="form-input" value={form.remark} onChange={e => setForm({...form, remark: e.target.value})} /></div>
            </div>
            <div className="flex justify-end gap-3 mt-6">
              <button onClick={() => setShowForm(false)} className="btn-secondary">取消</button>
              <button onClick={() => handleCreate()} className="px-4 py-2 bg-primary text-white rounded-lg text-sm">保存</button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

"use client";
import { useEffect, useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import { useI18n } from "@/hooks/useI18n";
import { api, getToken } from "@/lib/api";
import { useRouter } from "next/navigation";
import DashboardLayout from "@/components/layout/DashboardLayout";
import DataTable from "@/components/common/DataTable";

export default function IncomeExpensePage() {
  const { t } = useI18n(); const { user } = useAuth(); const router = useRouter();
  const [tab, setTab] = useState("income");
  const [data, setData] = useState<any[]>([]); const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1); const [month, setMonth] = useState("");
  const [totals, setTotals] = useState({ total_income: 0, total_expense: 0, net: 0 });
  const [showForm, setShowForm] = useState(false);
  const [categories, setCategories] = useState<any[]>([]);
  const [accounts, setAccounts] = useState<any[]>([]);
  const [form, setForm] = useState({ category_id: 0, account_id: 0, amount: 0, currency: "THB", date: "", remark: "" });

  useEffect(() => { if (!getToken()) router.push("/login"); load(); loadRefs(); }, [page, tab, month]);

  async function load() {
    const ep = tab === "income" ? "/income-expense/income" : "/income-expense/expense";
    const res = await api.get<any>(`${ep}?page=${page}&page_size=25${month ? "&month="+month : ""}`);
    setData(res.data); setTotal(res.total);
    const s = await api.get<any>(`/income-expense/monthly-summary?month=${month || "2026-07"}`);
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

  async function handleCreate() {
    const ep = tab === "income" ? "/income-expense/income" : "/income-expense/expense";
    await api.post(ep, { ...form, [tab === "income" ? "income_date" : "expense_date"]: form.date });
    setShowForm(false); load();
  }

  const columns = [
    { key: tab === "income" ? "income_date" : "expense_date", label: "日期", render: (v: string) => v?.slice(0,10) },
    { key: "category_name", label: "类别" },
    { key: "account_name", label: "账户" },
    { key: tab === "income" ? "customer_name" : "supplier_name", label: "对象" },
    { key: "amount", label: "金额" },
    { key: "currency", label: "币种" },
    { key: "remark", label: "备注" },
  ];

  return (
    <DashboardLayout>
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-xl font-bold">{t("income_expense")}</h1>
          <div className="flex gap-6 mt-2 text-sm">
            <span className="text-green-600">收入: ¥{totals.total_income.toLocaleString()}</span>
            <span className="text-red-600">支出: ¥{totals.total_expense.toLocaleString()}</span>
            <span className={totals.net >= 0 ? "text-blue-600" : "text-red-600"}>净额: ¥{totals.net.toLocaleString()}</span>
          </div>
        </div>
        <button onClick={() => { loadRefs(); setShowForm(true); }} className="bg-primary text-white px-4 py-2 rounded-lg text-sm">新建记录</button>
      </div>
      <div className="flex items-center gap-3 mb-4">
        <div className="bg-white rounded-lg p-1 flex"><button onClick={() => { setTab("income"); setPage(1); }} className={`px-4 py-1.5 rounded text-sm ${tab === "income" ? "bg-primary text-white" : ""}`}>收款</button><button onClick={() => { setTab("expense"); setPage(1); }} className={`px-4 py-1.5 rounded text-sm ${tab === "expense" ? "bg-primary text-white" : ""}`}>付款</button></div>
        <input type="month" value={month} onChange={e => { setMonth(e.target.value); setPage(1); }} className="border rounded px-3 py-2 text-sm" />
      </div>
      <DataTable columns={columns} data={data} total={total} page={page} pageSize={25} onPageChange={setPage} />
      {showForm && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center">
          <div className="bg-white rounded-xl w-full max-w-md p-6">
            <h2 className="text-lg font-semibold mb-4">{tab === "income" ? "新建收款" : "新建付款"}</h2>
            <div className="space-y-3">
              <div><label className="block text-sm mb-1">类别</label><select className="border rounded px-3 py-2 w-full" value={form.category_id} onChange={e => setForm({...form, category_id: +e.target.value})}><option>选择类别</option>{categories.map((c: any) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></div>
              <div><label className="block text-sm mb-1">收款账户</label><select className="border rounded px-3 py-2 w-full" value={form.account_id} onChange={e => setForm({...form, account_id: +e.target.value})}><option>选择账户</option>{accounts.map((a: any) => <option key={a.id} value={a.id}>{a.account_name} ({a.account_type})</option>)}</select></div>
              <div><label className="block text-sm mb-1">日期</label><input type="date" className="border rounded px-3 py-2 w-full" value={form.date} onChange={e => setForm({...form, date: e.target.value})} /></div>
              <div><label className="block text-sm mb-1">金额</label><input type="number" step="0.01" className="border rounded px-3 py-2 w-full" value={form.amount} onChange={e => setForm({...form, amount: +e.target.value})} /></div>
              <div><label className="block text-sm mb-1">币种</label><select className="border rounded px-3 py-2 w-full" value={form.currency} onChange={e => setForm({...form, currency: e.target.value})}><option value="THB">THB</option><option value="CNY">CNY</option></select></div>
              <div><label className="block text-sm mb-1">备注</label><input className="border rounded px-3 py-2 w-full" value={form.remark} onChange={e => setForm({...form, remark: e.target.value})} /></div>
            </div>
            <div className="flex justify-end gap-3 mt-6">
              <button onClick={() => setShowForm(false)} className="px-4 py-2 border rounded-lg text-sm">取消</button>
              <button onClick={handleCreate} className="px-4 py-2 bg-primary text-white rounded-lg text-sm">保存</button>
            </div>
          </div>
        </div>
      )}
    </DashboardLayout>
  );
}

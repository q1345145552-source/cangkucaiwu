"use client";
import { useEffect, useState } from "react";
import { useToast } from "@/components/ui/Toast";
import { api, getToken } from "@/lib/api";
import { useRouter } from "next/navigation";
import { Plus, DollarSign, Pencil, Trash2, TrendingUp, RefreshCw, Download, Search } from "lucide-react";

const CATEGORY_GROUP = "other";
const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

export default function OtherIncomePage() {
  const { toast } = useToast(); const router = useRouter();
  const [data, setData] = useState<any[]>([]); const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [month, setMonth] = useState(new Date().toISOString().slice(0, 7));
  const [monthTotal, setMonthTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<any>(null);
  const [categories, setCategories] = useState<any[]>([]);
  const [accounts, setAccounts] = useState<any[]>([]);
  const [form, setForm] = useState({ category_id: 0, account_id: 0, amount: "", currency: "THB", date: new Date().toISOString().slice(0, 10), remark: "" });
  // 展示货币（只有两种）
  const [displayCurrency, setDisplayCurrency] = useState<"THB" | "CNY">("THB");
  const [rateCNYtoTHB, setRateCNYtoTHB] = useState(5.0);
  // 筛选
  const [currencyFilter, setCurrencyFilter] = useState("");
  const [searchText, setSearchText] = useState("");
  const [catFilter, setCatFilter] = useState(0);
  const [dateStart, setDateStart] = useState("");
  const [dateEnd, setDateEnd] = useState("");

  useEffect(() => { if (!getToken()) router.push("/login"); load(); loadRefs(); loadSummary(); loadRate(); }, [page, month, currencyFilter, searchText, catFilter, dateStart, dateEnd]);

  async function load() {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      params.set("page", String(page)); params.set("page_size", "25");
      params.set("category_group", CATEGORY_GROUP);
      if (month) params.set("month", month);
      if (currencyFilter) params.set("currency", currencyFilter);
      if (searchText) params.set("search", searchText);
      if (catFilter) params.set("category_id", String(catFilter));
      if (dateStart) params.set("start_date", dateStart);
      if (dateEnd) params.set("end_date", dateEnd);
      const res = await api.get<any>(`/income-expense/income?${params.toString()}`);
      setData(res.data); setTotal(res.total);
    } catch (err) { console.error("加载失败:", err); }
    setLoading(false);
  }

  async function loadSummary() {
    try {
      const s = await api.get<any>(`/income-expense/monthly-summary?month=${month || new Date().toISOString().slice(0,7)}&category_group=${CATEGORY_GROUP}`);
      setMonthTotal(s.total_income || 0);
    } catch {}
  }

  async function loadRefs() {
    try {
      const cats = await api.get<any>(`/income-expense/categories?type=income&category_group=${CATEGORY_GROUP}`);
      setCategories(cats.data);
      const accs = await api.get<any>("/accounts");
      setAccounts(accs.data || []);
    } catch {}
  }

  async function loadRate() {
    try {
      const r = await api.get<any>("/rates/query?from_currency=CNY&to_currency=THB");
      setRateCNYtoTHB(r.rate || 5.0);
    } catch { setRateCNYtoTHB(5.0); }
  }

  // 换算：始终按展示货币显示
  function displayAmount(row: any): number {
    const amt = row.amount || 0;
    const cur = row.currency || "THB";
    if (displayCurrency === "THB") return cur === "THB" ? amt : +(amt * rateCNYtoTHB).toFixed(2);
    else return cur === "CNY" ? amt : +(amt / rateCNYtoTHB).toFixed(2);
  }

  function displayMonthTotal(): number {
    // monthTotal is always in THB (sum of all amounts), convert if needed
    if (displayCurrency === "THB") return monthTotal;
    return +(monthTotal / rateCNYtoTHB).toFixed(2);
  }

  function symbol() { return displayCurrency === "THB" ? "฿" : "¥"; }

  async function handleCreate() {
    try {
      await api.post("/income-expense/income", { ...form, amount: form.amount || 0, income_date: form.date, currency: form.currency });
      toast("success", "创建成功");
      resetForm(); load(); loadSummary();
    } catch (err: any) { toast("error", err.message || "创建失败"); }
  }

  async function handleEdit() {
    if (!editing) return;
    try {
      await api.put(`/income-expense/income/${editing.id}`, { ...form, amount: form.amount || 0, income_date: form.date, currency: form.currency, category_id: form.category_id, account_id: form.account_id });
      toast("success", "更新成功");
      resetForm(); load(); loadSummary();
    } catch (err: any) { toast("error", err.message || "更新失败"); }
  }

  async function handleDelete(id: number) {
    if (!confirm("确定要删除这条记录吗？")) return;
    try {
      await api.delete(`/income-expense/income/${id}`);
      toast("success", "删除成功");
      load(); loadSummary();
    } catch (err: any) { toast("error", err.message || "删除失败"); }
  }

  async function handleExport() {
    try {
      const params = new URLSearchParams();
      params.set("category_group", CATEGORY_GROUP);
      if (month) params.set("month", month);
      if (currencyFilter) params.set("currency", currencyFilter);
      if (searchText) params.set("search", searchText);
      if (catFilter) params.set("category_id", String(catFilter));
      if (dateStart) params.set("start_date", dateStart);
      if (dateEnd) params.set("end_date", dateEnd);
      const token = getToken();
      const res = await fetch(`${API_URL}/income-expense/income/export?${params.toString()}`, {
        headers: { "Authorization": `Bearer ${token}` },
      });
      const blob = await res.blob();
      const a = document.createElement("a"); a.href = window.URL.createObjectURL(blob);
      a.download = `other_income_${displayCurrency}.xlsx`; a.click();
      toast("success", "导出成功");
    } catch { toast("error", "导出失败"); }
  }

  function resetForm() {
    setShowForm(false); setEditing(null);
    setForm({ category_id: 0, account_id: 0, amount: "", currency: "THB", date: new Date().toISOString().slice(0, 10), remark: "" });
  }

  function openCreate() {
    loadRefs();
    setEditing(null);
    setForm({ category_id: 0, account_id: 0, amount: "", currency: "THB", date: new Date().toISOString().slice(0, 10), remark: "" });
    setShowForm(true);
  }

  function openEdit(row: any) {
    loadRefs();
    setEditing(row);
    setForm({
      category_id: row.category_id || 0,
      account_id: row.account_id || 0,
      amount: String(row.amount || ""),
      currency: row.currency || "THB",
      date: row.income_date?.slice(0, 10) || "",
      remark: row.remark || "",
    });
    setShowForm(true);
  }

  function resetFilters() { setCurrencyFilter(""); setSearchText(""); setCatFilter(0); setDateStart(""); setDateEnd(""); setPage(1); }

  return (
    <>
      <div className="flex items-center justify-between mb-5">
        <h1 className="page-title">其他收入</h1>
        <div className="flex items-center gap-2">
          {/* 展示切换 */}
          <div className="flex bg-white rounded-lg border p-0.5 mr-2">
            <button onClick={() => { setDisplayCurrency("THB"); loadRate(); }} className={`px-3 py-1.5 rounded text-xs font-medium transition-colors ${displayCurrency === "THB" ? "bg-blue-600 text-white shadow-sm" : "text-gray-400 hover:text-gray-600"}`}>显示为泰铢</button>
            <button onClick={() => { setDisplayCurrency("CNY"); loadRate(); }} className={`px-3 py-1.5 rounded text-xs font-medium transition-colors ${displayCurrency === "CNY" ? "bg-blue-600 text-white shadow-sm" : "text-gray-400 hover:text-gray-600"}`}>显示为人民币</button>
          </div>
          <button onClick={openCreate} className="btn-primary flex items-center gap-1.5 text-sm">
            <Plus size={16} />新建收入
          </button>
        </div>
      </div>

      {/* 当月合计卡片 */}
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6 mb-5">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-green-50 flex items-center justify-center">
            <TrendingUp size={22} className="text-green-600" />
          </div>
          <div>
            <div className="text-sm text-gray-400">当月其他收入合计<span className="text-blue-500 ml-1">（{displayCurrency === "THB" ? "泰铢" : "人民币"}）</span></div>
            <div className="text-2xl font-bold text-green-700">{symbol()}{displayMonthTotal().toLocaleString()}</div>
          </div>
          <div className="ml-auto text-xs text-gray-400 flex items-center gap-1">
            <RefreshCw size={12} /> CNY→THB 汇率: {rateCNYtoTHB}
          </div>
        </div>
      </div>

      {/* 筛选 + 列表 */}
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
        <div className="flex items-end gap-3 mb-4 flex-wrap">
          <div className="w-[140px]">
            <label className="form-label text-xs">月份</label>
            <input type="month" value={month} onChange={e => { setMonth(e.target.value); setPage(1); }} className="form-input text-sm" />
          </div>
          <div className="w-[130px]">
            <label className="form-label text-xs">开始日期</label>
            <input type="date" value={dateStart} onChange={e => { setDateStart(e.target.value); setPage(1); }} className="form-input text-sm" />
          </div>
          <div className="w-[130px]">
            <label className="form-label text-xs">结束日期</label>
            <input type="date" value={dateEnd} onChange={e => { setDateEnd(e.target.value); setPage(1); }} className="form-input text-sm" />
          </div>
          <div className="w-[110px]">
            <label className="form-label text-xs">币种</label>
            <select className="form-input text-sm" value={currencyFilter} onChange={e => { setCurrencyFilter(e.target.value); setPage(1); }}>
              <option value="">全部</option>
              <option value="THB">THB</option>
              <option value="CNY">CNY</option>
            </select>
          </div>
          <div className="w-[130px]">
            <label className="form-label text-xs">分类</label>
            <select className="form-input text-sm" value={catFilter} onChange={e => { setCatFilter(+e.target.value); setPage(1); }}>
              <option value={0}>全部分类</option>
              {categories.map((c: any) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </div>
          <div className="flex-1 min-w-[150px]">
            <label className="form-label text-xs">搜索</label>
            <input type="text" className="form-input text-sm" placeholder="物品说明关键词" value={searchText} onChange={e => setSearchText(e.target.value)} onKeyDown={e => { if (e.key === "Enter") { setPage(1); load(); } }} />
          </div>
          <button onClick={() => { setPage(1); load(); }} className="btn-primary flex items-center gap-1.5 text-sm h-[38px]">
            <Search size={15} />查询
          </button>
          <button onClick={resetFilters} className="btn-secondary flex items-center gap-1.5 text-sm h-[38px]">重置</button>
          <button onClick={handleExport} className="btn-secondary flex items-center gap-1.5 text-sm h-[38px] ml-auto">
            <Download size={15} />导出Excel
          </button>
          <span className="text-xs text-gray-400 self-center ml-1">{total} 条记录</span>
        </div>

        {loading ? (
          <div className="flex items-center justify-center h-40 text-gray-400">
            <div className="animate-spin w-5 h-5 border-2 border-blue-600 border-t-transparent rounded-full mr-2" />加载中...
          </div>
        ) : data.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-gray-400 bg-gray-50/50 rounded-xl">
            <DollarSign size={40} className="text-gray-200 mb-3" /><span className="text-sm">暂无收入记录</span>
          </div>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-gray-50">
                    <th className="text-left px-4 py-3 font-medium text-gray-500">日期</th>
                    <th className="text-left px-4 py-3 font-medium text-gray-500">分类</th>
                    <th className="text-left px-4 py-3 font-medium text-gray-500">物品说明</th>
                    <th className="text-right px-4 py-3 font-medium text-gray-500">金额</th>
                    <th className="text-center px-4 py-3 font-medium text-gray-500 w-16">币种</th>
                    <th className="text-left px-4 py-3 font-medium text-gray-500">备注</th>
                    <th className="text-center px-4 py-3 font-medium text-gray-500">操作</th>
                  </tr>
                </thead>
                <tbody>
                  {data.map((row: any) => (
                    <tr key={row.id} className="border-b hover:bg-gray-50/50 transition-colors">
                      <td className="px-4 py-3">{row.income_date?.slice(0, 10)}</td>
                      <td className="px-4 py-3"><span className="px-2 py-0.5 rounded text-xs font-medium bg-green-50 text-green-700">{row.category_name}</span></td>
                      <td className="px-4 py-3 text-gray-600 max-w-[200px] truncate">{row.remark || "-"}</td>
                      <td className="px-4 py-3 text-right font-medium text-green-600">{symbol()}{displayAmount(row).toLocaleString()}</td>
                      <td className="px-4 py-3 text-center">
                        <span className={`px-1.5 py-0.5 rounded text-xs font-medium ${row.currency === "CNY" ? "bg-red-50 text-red-600" : "bg-blue-50 text-blue-600"}`}>
                          {row.currency || "THB"}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-gray-500 max-w-[120px] truncate">{row.remark || "-"}</td>
                      <td className="px-4 py-3 text-center">
                        <div className="flex items-center justify-center gap-1">
                          <button onClick={() => openEdit(row)} className="p-1.5 rounded-lg hover:bg-blue-50 text-blue-500 transition-colors" title="编辑"><Pencil size={15} /></button>
                          <button onClick={() => handleDelete(row.id)} className="p-1.5 rounded-lg hover:bg-red-50 text-red-500 transition-colors" title="删除"><Trash2 size={15} /></button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {total > 25 && (
              <div className="flex items-center justify-between mt-4 pt-3 border-t">
                <span className="text-xs text-gray-400">共 {total} 条，第 {page}/{Math.ceil(total/25)} 页</span>
                <div className="flex gap-2">
                  <button onClick={() => setPage(p => Math.max(1, p-1))} disabled={page <= 1} className="px-3 py-1.5 text-xs rounded border disabled:opacity-30">上一页</button>
                  <button onClick={() => setPage(p => p+1)} disabled={page * 25 >= total} className="px-3 py-1.5 text-xs rounded border disabled:opacity-30">下一页</button>
                </div>
              </div>
            )}
          </>
        )}
      </div>

      {/* 新建/编辑弹窗 */}
      {showForm && (
        <div className="modal-overlay" onClick={() => resetForm()}>
          <div className="bg-white rounded-2xl w-full max-w-md shadow-2xl" onClick={e => e.stopPropagation()}>
            <div className="bg-green-600 text-white px-6 py-4 rounded-t-2xl flex items-center gap-3">
              <DollarSign size={20} />
              <h2 className="text-lg font-semibold">{editing ? "编辑收入" : "新建其他收入"}</h2>
              <button onClick={() => resetForm()} className="ml-auto text-green-200 hover:text-white text-xl leading-none">&times;</button>
            </div>
            <div className="p-6 space-y-4">
              <div><label className="form-label">日期</label><input type="date" className="form-input" value={form.date} onChange={e => setForm({...form, date: e.target.value})} /></div>
              <div><label className="form-label">分类</label><select className="form-input" value={form.category_id} onChange={e => setForm({...form, category_id: +e.target.value})}><option value={0}>选择分类</option>{categories.map((c: any) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></div>
              <div><label className="form-label">物品说明</label><input className="form-input" value={form.remark} onChange={e => setForm({...form, remark: e.target.value})} placeholder="例如：纸壳500kg、旧货架2个" /></div>
              <div className="grid grid-cols-2 gap-3">
                <div><label className="form-label">金额</label><input type="number" step="0.01" className="form-input" value={form.amount} onChange={e => setForm({...form, amount: e.target.value === "" ? "" : +e.target.value})} /></div>
                <div><label className="form-label">币种</label><select className="form-input" value={form.currency} onChange={e => setForm({...form, currency: e.target.value})}><option value="THB">THB 泰铢</option><option value="CNY">CNY 人民币</option></select></div>
              </div>
              <div><label className="form-label">收款账户</label><select className="form-input" value={form.account_id} onChange={e => setForm({...form, account_id: +e.target.value})}><option value={0}>选择账户</option>{accounts.map((a: any) => <option key={a.id} value={a.id}>{a.account_name}</option>)}</select></div>
            </div>
            <div className="border-t px-6 py-4 bg-gray-50 rounded-b-2xl flex justify-end gap-3">
              <button onClick={() => resetForm()} className="btn-secondary">取消</button>
              <button onClick={editing ? handleEdit : handleCreate} className="btn-primary">{editing ? "保存修改" : "保存"}</button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

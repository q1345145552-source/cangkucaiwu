"use client";
import ActionGate from "@/components/permissions/ActionGate";
import { useBusinessAction } from "@/hooks/useMenuPermission";
import { useEffect, useRef, useState } from "react";
import { useToast } from "@/components/ui/Toast";
import { api, getToken, getActiveWarehouseId } from "@/lib/api";
import { fmtMoney } from "@/lib/currency";
import { pendingWalletOperation, submitWalletOperation } from "@/lib/manualWallet";
import { useRouter } from "next/navigation";
import { Plus, DollarSign, Pencil, Trash2, TrendingUp, Download, Search } from "lucide-react";

const CATEGORY_GROUP = "other";
const API_URL = process.env.NEXT_PUBLIC_API_URL || "/api/v1";

export default function OtherIncomePage() {
  const canWrite = useBusinessAction("other_income_expense", "bookkeeping");
  const { toast } = useToast(); const router = useRouter();
  const [data, setData] = useState<any[]>([]); const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const now = new Date();
  const curMonth = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
  const todayStr = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
  const [totalsByCurrency, setTotalsByCurrency] = useState<Record<string, number>>({});
  const loadVersion = useRef(0);
  const [loading, setLoading] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<any>(null);
  const [categories, setCategories] = useState<any[]>([]);
  const [accounts, setAccounts] = useState<any[]>([]);
  const [form, setForm] = useState({ category_id: 0, account_id: 0, amount: "", currency: "THB", date: new Date().toISOString().slice(0, 10), remark: "" });
  // 筛选
  const [currencyFilter, setCurrencyFilter] = useState("");
  const [searchText, setSearchText] = useState("");
  const [catFilter, setCatFilter] = useState(0);
  const [dateStart, setDateStart] = useState(`${curMonth}-01`);
  const [dateEnd, setDateEnd] = useState(todayStr);

  useEffect(() => { if (!getToken()) { router.push("/login"); return; } loadRefs(); }, []);
  useEffect(() => { load(); return () => { loadVersion.current += 1; }; }, [page, currencyFilter, searchText, catFilter, dateStart, dateEnd]);

  function filterParams() {
    const params = new URLSearchParams({ category_group: CATEGORY_GROUP, start_date: dateStart, end_date: dateEnd });
    if (currencyFilter) params.set("currency", currencyFilter);
    if (searchText) params.set("search", searchText);
    if (catFilter) params.set("category_id", String(catFilter));
    return params;
  }

  async function load() {
    const version = ++loadVersion.current;
    setLoading(true);
    try {
      const params = filterParams();
      params.set("page", String(page)); params.set("page_size", "25");
      const res = await api.get<any>(`/income-expense/income?${params.toString()}`);
      if (version !== loadVersion.current) return;
      setData(res.data); setTotal(res.total); setTotalsByCurrency(res.totals_by_currency || {});
    } catch (err: any) {
      if (version === loadVersion.current) {
        setData([]); setTotal(0); setTotalsByCurrency({});
        toast("error", err.message || "加载失败");
      }
    } finally { if (version === loadVersion.current) setLoading(false); }
  }

  async function loadRefs() {
    try {
      const cats = await api.get<any>(`/income-expense/categories?type=income&category_group=${CATEGORY_GROUP}`);
      setCategories(cats.data);
      const accs = await api.get<any>("/accounts");
      setAccounts(accs.data || []);
    } catch {}
  }

  function validAccount() {
    const account = accounts.find((a: any) => a.id === form.account_id);
    if (!account) { toast("error", "请选择收款账户"); return false; }
    if (account.status && account.status !== "active") { toast("error", "收款账户已停用"); return false; }
    if ((account.currency || "THB") !== form.currency) { toast("error", "收款账户币种必须与收入币种一致"); return false; }
    return true;
  }

  async function handleCreate() {
    if (!validAccount()) return;
    try {
      const result = await submitWalletOperation("income", { ...form, amount: form.amount || 0, income_date: form.date, currency: form.currency });
      toast("success", result.message || "创建成功");
      resetForm(); load();
    } catch (err: any) { toast("error", err.message || "创建失败"); }
  }

  async function handleEdit() {
    if (!editing) return;
    if (!validAccount()) return;
    try {
      await api.put(`/income-expense/income/${editing.id}`, { ...form, amount: form.amount || 0, income_date: form.date, currency: form.currency, category_id: form.category_id, account_id: form.account_id });
      toast("success", "更新成功");
      resetForm(); load();
    } catch (err: any) { toast("error", err.message || "更新失败"); }
  }

  async function handleDelete(id: number) {
    if (!confirm("确定要删除这条记录吗？")) return;
    try {
      await api.delete(`/income-expense/income/${id}`);
      toast("success", "删除成功");
      load();
    } catch (err: any) { toast("error", err.message || "删除失败"); }
  }

  async function handleExport() {
    try {
      const params = filterParams();
      const token = getToken();
      const headers: Record<string, string> = { Authorization: `Bearer ${token}` };
      const warehouse = getActiveWarehouseId();
      if (warehouse !== null) headers["X-Warehouse-ID"] = warehouse;
      const res = await fetch(`${API_URL}/income-expense/income/export?${params.toString()}`, {
        headers,
      });
      if (!res.ok) throw new Error((await res.json()).detail || "导出失败");
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a"); a.href = url;
      a.download = `other_income_${currencyFilter || "all"}_${dateStart}_${dateEnd}.xlsx`; a.click(); window.URL.revokeObjectURL(url);
      toast("success", "导出成功");
    } catch (err: any) { toast("error", err.message || "导出失败"); }
  }

  function resetForm() {
    setShowForm(false); setEditing(null);
    setForm({ category_id: 0, account_id: 0, amount: "", currency: "THB", date: new Date().toISOString().slice(0, 10), remark: "" });
  }

  function openCreate() {
    loadRefs();
    let pending: any;
    try { pending = pendingWalletOperation("income")?.payload; } catch (err: any) { toast("error", err.message); return; }
    setEditing(null);
    setForm(pending ? { category_id: pending.category_id, account_id: pending.account_id, amount: String(pending.amount), currency: pending.currency, date: pending.income_date, remark: pending.remark || "" } : { category_id: 0, account_id: 0, amount: "", currency: "THB", date: new Date().toISOString().slice(0, 10), remark: "" });
    if (pending) toast("error", "已恢复上一笔结果待确认的收款，请重试，不要另建");
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

  function resetFilters() { setCurrencyFilter(""); setSearchText(""); setCatFilter(0); setDateStart(`${curMonth}-01`); setDateEnd(todayStr); setPage(1); }

  return (
    <>
      <div className="flex items-center justify-between mb-5">
        <h1 className="page-title">其他收入</h1>
        <div className="flex items-center gap-2">
          <ActionGate anyOf={["income_expense.create_income"]}><button aria-disabled={!canWrite} disabled={!canWrite} onClick={openCreate} className="btn-primary flex items-center gap-1.5 text-sm">
            <Plus size={16} />新建收入
          </button></ActionGate>
        </div>
      </div>

      {/* 当月合计卡片 */}
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6 mb-5">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-green-50 flex items-center justify-center">
            <TrendingUp size={22} className="text-green-600" />
          </div>
          <div>
            <div className="text-sm text-gray-400">筛选范围其他收入合计</div>
            <div className="flex flex-wrap gap-x-6 gap-y-2 mt-1">{(currencyFilter ? [currencyFilter] : ["THB", "CNY"]).map(c => <div key={c}><span className="text-xs text-gray-400">{c === "THB" ? "泰铢 THB" : "人民币 CNY"}</span><div className="text-2xl font-bold text-green-700">{fmtMoney(totalsByCurrency[c] || 0, c)}</div></div>)}</div>
          </div>
          <div className="ml-auto text-xs text-gray-400 flex items-center gap-1">
            按币种分别统计，不换算
          </div>
        </div>
      </div>

      {/* 筛选 + 列表 */}
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
        <div className="flex items-end gap-3 mb-4 flex-wrap">
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
            <input type="text" className="form-input text-sm" placeholder="物品说明关键词" value={searchText} onChange={e => { setSearchText(e.target.value); setPage(1); }} onKeyDown={e => { if (e.key === "Enter") { if (page === 1) load(); else setPage(1); } }} />
          </div>
          <button onClick={() => { if (page === 1) load(); else setPage(1); }} className="btn-primary flex items-center gap-1.5 text-sm h-[38px]">
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
                      <td className="px-4 py-3 text-right font-medium text-green-600">{fmtMoney(row.amount, row.currency || "THB")}</td>
                      <td className="px-4 py-3 text-center">
                        <span className={`px-1.5 py-0.5 rounded text-xs font-medium ${row.currency === "CNY" ? "bg-red-50 text-red-600" : "bg-blue-50 text-blue-600"}`}>
                          {row.currency || "THB"}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-gray-500 max-w-[120px] truncate">{row.remark || "-"}</td>
                      <td className="px-4 py-3 text-center">
                        <div className="flex items-center justify-center gap-1">
                          <ActionGate anyOf={["income_expense.update_income"]}><button disabled={!(canWrite)} onClick={() => openEdit(row)} className="p-1.5 rounded-lg hover:bg-blue-50 text-blue-500 transition-colors" title="编辑"><Pencil size={15} /></button></ActionGate>
                          <ActionGate anyOf={["income_expense.delete_income#operate"]}><button disabled={!(canWrite)} onClick={() => handleDelete(row.id)} className="p-1.5 rounded-lg hover:bg-red-50 text-red-500 transition-colors" title="删除"><Trash2 size={15} /></button></ActionGate>
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
      {canWrite && showForm && (
        <div className="modal-overlay" >
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
                <div><label className="form-label">金额</label><input type="number" step="0.01" className="form-input" value={form.amount} onChange={e => setForm({...form, amount: e.target.value})} /></div>
                <div><label className="form-label">币种</label><select className="form-input" value={form.currency} onChange={e => { const currency = e.target.value; setForm({...form, currency, account_id: accounts.find((a: any) => a.id === form.account_id && (a.currency || "THB") === currency) ? form.account_id : 0}); }}><option value="THB">THB 泰铢</option><option value="CNY">CNY 人民币</option></select></div>
              </div>
              <div><label className="form-label">收款账户</label><select className="form-input" value={form.account_id} onChange={e => setForm({...form, account_id: +e.target.value})}><option value={0}>选择账户</option>{accounts.filter((a: any) => (a.currency || "THB") === form.currency && (!a.status || a.status === "active")).map((a: any) => <option key={a.id} value={a.id}>{a.account_name}（{a.currency || "THB"}）</option>)}</select></div>
            </div>
            <div className="border-t px-6 py-4 bg-gray-50 rounded-b-2xl flex justify-end gap-3">
              <button onClick={() => resetForm()} className="btn-secondary">取消</button>
              <ActionGate anyOf={["income_expense.update_income#operate"]}><button aria-disabled={!canWrite} disabled={!canWrite} onClick={editing ? handleEdit : handleCreate} className="btn-primary">{editing ? "保存修改" : "保存"}</button></ActionGate>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

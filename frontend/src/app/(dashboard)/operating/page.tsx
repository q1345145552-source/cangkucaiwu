"use client";
import { useEffect, useState } from "react";
import { useToast } from "@/components/ui/Toast";
import { api, getToken, getActiveWarehouseId } from "@/lib/api";
import { useRouter } from "next/navigation";
import DataTable from "@/components/common/DataTable";
import { TrendingUp, TrendingDown, Plus, DollarSign, Minus, ArrowUp, ArrowDown, Search } from "lucide-react";

export default function OperatingPage() {
  const { toast } = useToast(); const router = useRouter();
  const [dashboard, setDashboard] = useState<any>(null);
  const [expenses, setExpenses] = useState<any[]>([]); const [expTotal, setExpTotal] = useState(0);
  const [expPage, setExpPage] = useState(1);
  const [month, setMonth] = useState(new Date().toISOString().slice(0, 7));
  const [loading, setLoading] = useState(false);
  const [expLoading, setExpLoading] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [categories, setCategories] = useState<any[]>([]);
  const [accounts, setAccounts] = useState<any[]>([]);
  const [form, setForm] = useState({ category_id: 0, account_id: 0, amount: "", currency: "THB", date: new Date().toISOString().slice(0, 10), remark: "" });
  const [expFilters, setExpFilters] = useState({ category_id: 0, account_id: 0, currency: "", start_date: "", end_date: "" });
  const [viewMode, setViewMode] = useState<"month" | "week">("month");
  const [voucherFiles, setVoucherFiles] = useState<File[]>([]);
  const [voucherPreviews, setVoucherPreviews] = useState<string[]>([]);
  const [zoomVouchers, setZoomVouchers] = useState<string[]>([]);
  const [zoomIndex, setZoomIndex] = useState(0);

  useEffect(() => { if (!getToken()) router.push("/login"); loadDashboard(); loadRefs(); }, []);
  useEffect(() => { loadExpenses(); }, [expPage, month, expFilters, viewMode]);

  // 按周：用本月第几周；按月：用月份。切换时 dashboard 重新拉
  useEffect(() => { loadDashboard(); loadExpenses(); }, [viewMode]);

  function getWeekRange(): { start: string; end: string } | null {
    if (viewMode !== "week") return null;
    const now = new Date();
    const day = now.getDay() || 7; // Monday=1, Sunday=7
    const monday = new Date(now); monday.setDate(now.getDate() - day + 1);
    const sunday = new Date(now); sunday.setDate(now.getDate() + (7 - day));
    return {
      start: monday.toISOString().slice(0, 10),
      end: sunday.toISOString().slice(0, 10),
    };
  }

  async function loadDashboard() {
    setLoading(true);
    try {
      const r = await api.get<any>("/income-expense/operating-dashboard");
      setDashboard(r);
    } catch (err) { console.error("加载看板失败:", err); }
    setLoading(false);
  }

  async function loadExpenses() {
    setExpLoading(true);
    try {
      const params = new URLSearchParams();
      params.set("page", String(expPage)); params.set("page_size", "25");
      params.set("category_group", "operating");
      if (viewMode === "month" && month) {
        params.set("month", month);
      } else if (viewMode === "week") {
        const wr = getWeekRange();
        if (wr) { params.set("start_date", wr.start); params.set("end_date", wr.end); }
      }
      if (expFilters.category_id) params.set("category_id", String(expFilters.category_id));
      if (expFilters.account_id) params.set("account_id", String(expFilters.account_id));
      if (expFilters.currency) params.set("currency", expFilters.currency);
      if (expFilters.start_date) params.set("start_date", expFilters.start_date);
      if (expFilters.end_date) params.set("end_date", expFilters.end_date);
      const res = await api.get<any>(`/income-expense/expense?${params.toString()}`);
      setExpenses(res.data); setExpTotal(res.total);
    } catch (err) { console.error("加载支出失败:", err); }
    setExpLoading(false);
  }

  async function loadRefs() {
    try {
      const cats = await api.get<any>("/income-expense/categories?type=expense&category_group=operating");
      setCategories(cats.data);
      const accs = await api.get<any>("/accounts");
      setAccounts(accs.data || []);
    } catch {}
  }

  // 兼容旧单路径字符串 + 新 JSON 数组字符串
  function parseVouchers(v: any): string[] {
    if (!v) return [];
    if (Array.isArray(v)) return v.filter(Boolean);
    if (typeof v === "string") {
      const s = v.trim();
      if (!s) return [];
      if (s.startsWith("[")) {
        try { const a = JSON.parse(s); return Array.isArray(a) ? a.filter(Boolean) : [s]; } catch { return [s]; }
      }
      return [s];
    }
    return [];
  }

  function handleVoucherSelect(e: any) {
    const fileList: FileList | null = e.target.files;
    if (!fileList || !fileList.length) return;
    const files: File[] = Array.from(fileList);
    const newPreviews = files.map((f: File) => URL.createObjectURL(f));
    setVoucherFiles(prev => [...prev, ...files]);
    setVoucherPreviews(prev => [...prev, ...newPreviews]);
    e.target.value = "";
  }

  function removeVoucher(i: number) {
    if (voucherPreviews[i]) URL.revokeObjectURL(voucherPreviews[i]);
    setVoucherFiles(prev => prev.filter((_, idx) => idx !== i));
    setVoucherPreviews(prev => prev.filter((_, idx) => idx !== i));
  }

  function clearVoucher() {
    voucherPreviews.forEach(p => URL.revokeObjectURL(p));
    setVoucherFiles([]);
    setVoucherPreviews([]);
  }

  function closeForm() {
    setShowForm(false);
    clearVoucher();
  }

  async function handleCreate() {
    if (!form.category_id) { toast("error", "请选择类别"); return; }
    if (!form.account_id) { toast("error", "请选择账户"); return; }
    try {
      const fd = new FormData();
      fd.append("category_id", String(form.category_id));
      fd.append("account_id", String(form.account_id));
      fd.append("amount", String(form.amount || 0));
      fd.append("currency", form.currency || "THB");
      fd.append("expense_date", form.date);
      if (form.remark) fd.append("remark", form.remark);
      if (voucherFiles.length) voucherFiles.forEach(f => fd.append("files", f));

      const headers: Record<string, string> = {};
      const token = getToken();
      if (token) headers["Authorization"] = `Bearer ${token}`;
      const whId = getActiveWarehouseId();
      if (whId !== null) headers["X-Warehouse-ID"] = whId;

      const res = await fetch("/api/v1/income-expense/expense", {
        method: "POST", headers, body: fd,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        let msg = err.detail || "录入失败";
        if (Array.isArray(err.detail)) msg = err.detail.map((e: any) => e.msg).join("; ");
        throw new Error(msg);
      }
      toast("success", "支出录入成功");
      setShowForm(false);
      setForm({ category_id: 0, account_id: 0, amount: "", currency: "THB", date: new Date().toISOString().slice(0, 10), remark: "" });
      clearVoucher();
      loadExpenses(); loadDashboard();
    } catch (err: any) { toast("error", err.message || "录入失败"); }
  }

  function handleSearch() { setExpPage(1); loadExpenses(); }

  // === SVG Chart ===
  function renderChart() {
    if (!dashboard?.data || dashboard.data.length === 0) return null;
    const d = dashboard.data;
    const w = 860; const h = 280; const px = 65; const py = 35;
    const gw = w - px - 30; const gh = h - py * 2;
    const maxVal = Math.max(...d.map((x: any) => Math.max(x.recharge_income || 0, 1)), 1);
    const scale = Math.ceil(maxVal * 1.2);
    const step = gw / Math.max(d.length - 1, 1);

    let linePath = ""; let areaPath = "";
    const dots: any[] = [];
    for (let i = 0; i < d.length; i++) {
      const x = px + i * step;
      const y = py + gh - ((d[i].recharge_income || 0) / scale * gh);
      linePath += (i === 0 ? "M" : "L") + x + "," + y + " ";
      areaPath += (i === 0 ? "M" : "L") + x + "," + y + " ";
      const isCurrent = d[i].month === dashboard.current_month;
      dots.push(<circle key={"d"+i} cx={x} cy={y} r={isCurrent ? 5.5 : 3.5} fill={isCurrent ? "#EF4444" : "#2563EB"} stroke="white" strokeWidth={2}><title>{d[i].month}: ¥{Math.round(d[i].recharge_income || 0).toLocaleString()}</title></circle>);
    }
    areaPath += "L" + (px + (d.length - 1) * step) + "," + (py + gh) + " L" + px + "," + (py + gh) + " Z";

    const gridLines: any[] = [];
    for (let j = 0; j <= 4; j++) {
      const y = py + j * gh / 4;
      gridLines.push(<line key={"g"+j} x1={px} y1={y} x2={w-30} y2={y} stroke="#e5e7eb" strokeWidth={1} strokeDasharray="4,3" />);
      gridLines.push(<text key={"gt"+j} x={px-10} y={y+4} textAnchor="end" fill="#9ca3af" fontSize={11}>{Math.round(scale*(4-j)/4).toLocaleString()}</text>);
    }

    return (
      <svg viewBox={`0 0 ${w} ${h}`} className="w-full">
        <defs>
          <linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#2563EB" stopOpacity={0.35} />
            <stop offset="100%" stopColor="#2563EB" stopOpacity={0.02} />
          </linearGradient>
        </defs>
        {gridLines}
        <path d={areaPath} fill="url(#areaGrad)" />
        <path d={linePath.trim()} fill="none" stroke="#2563EB" strokeWidth={2.8} strokeLinejoin="round" strokeLinecap="round" />
        {dots}
        {d.map((x: any, i: number) => (
          <text key={"l"+i} x={px + i * step} y={h - 10} textAnchor="middle" fill="#6b7280" fontSize={12}>{x.month.substring(5)}月</text>
        ))}
      </svg>
    );
  }

  const curMonthExpense = expenses.reduce((sum: number, e: any) => sum + (e.amount || 0), 0);

  return (
    <>
      <div className="flex items-center justify-between mb-5">
        <h1 className="page-title">运营收支</h1>
        <div className="flex items-center gap-2">
          <div className="flex bg-white rounded-lg border p-0.5">
            <button onClick={() => setViewMode("week")} className={`px-3 py-1.5 rounded text-xs font-medium transition-colors ${viewMode === "week" ? "bg-blue-600 text-white shadow-sm" : "text-gray-500 hover:text-gray-700"}`}>按周</button>
            <button onClick={() => setViewMode("month")} className={`px-3 py-1.5 rounded text-xs font-medium transition-colors ${viewMode === "month" ? "bg-blue-600 text-white shadow-sm" : "text-gray-500 hover:text-gray-700"}`}>按月</button>
          </div>
          <button onClick={() => { loadRefs(); setShowForm(true); }} className="btn-primary flex items-center gap-1.5 text-sm">
            <Plus size={16} />录入支出
          </button>
        </div>
      </div>

      {/* 收入趋势图 */}
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6 mb-5">
        <div className="flex items-center gap-2.5 mb-4">
          <div className="w-9 h-9 rounded-lg bg-blue-50 flex items-center justify-center"><TrendingUp size={20} className="text-blue-600" /></div>
          <div><h2 className="text-base font-semibold text-gray-800">充值收入趋势</h2><span className="text-xs text-gray-400">近12个月</span></div>
          <div className="ml-auto flex items-center gap-2">
            <div className="flex items-center gap-1.5"><div className="w-2.5 h-2.5 rounded-full bg-blue-600" /><span className="text-xs text-gray-400">充值收入</span></div>
            <div className="flex items-center gap-1.5"><div className="w-2.5 h-2.5 rounded-full bg-red-500" /><span className="text-xs text-gray-400">当月</span></div>
          </div>
        </div>
        {loading ? (
          <div className="flex items-center justify-center h-64 text-gray-400"><div className="animate-spin w-6 h-6 border-2 border-blue-600 border-t-transparent rounded-full mr-2" />加载中...</div>
        ) : dashboard?.data?.length > 0 ? (
          <div className="bg-gradient-to-b from-blue-50/40 to-white rounded-xl p-3">{renderChart()}</div>
        ) : (
          <div className="flex flex-col items-center justify-center h-64 text-gray-400 bg-gray-50/50 rounded-xl"><TrendingUp size={44} className="text-gray-200 mb-3" /><span className="text-sm">暂无充值收入数据</span></div>
        )}
      </div>

      {/* 支出管理 */}
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6 mb-5">
        <div className="flex items-center gap-2.5 mb-4">
          <div className="w-9 h-9 rounded-lg bg-red-50 flex items-center justify-center"><Minus size={20} className="text-red-500" /></div>
          <div><h2 className="text-base font-semibold text-gray-800">运营支出</h2><span className="text-xs text-gray-400">{expTotal} 条记录</span></div>
        </div>
        <div className="bg-gray-50/70 rounded-xl p-4 mb-4">
          <div className="flex items-end gap-3 flex-wrap">
            {viewMode === "month" ? (
              <div className="w-[140px]"><label className="form-label text-xs">月份</label><input type="month" value={month} onChange={e => { setMonth(e.target.value); setExpPage(1); }} className="form-input text-sm" /></div>
            ) : (
              <div className="flex gap-2 items-end">
                <div className="w-[140px]"><label className="form-label text-xs">开始日期</label><input type="date" value={expFilters.start_date || getWeekRange()?.start || ""} onChange={e => setExpFilters({ ...expFilters, start_date: e.target.value })} className="form-input text-sm" /></div>
                <div className="w-[140px]"><label className="form-label text-xs">结束日期</label><input type="date" value={expFilters.end_date || getWeekRange()?.end || ""} onChange={e => setExpFilters({ ...expFilters, end_date: e.target.value })} className="form-input text-sm" /></div>
              </div>
            )}
            <div className="w-[140px]"><label className="form-label text-xs">类别</label><select className="form-input text-sm" value={expFilters.category_id} onChange={e => setExpFilters({ ...expFilters, category_id: +e.target.value })}><option value={0}>全部类别</option>{categories.map((c: any) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></div>
            <div className="w-[110px]"><label className="form-label text-xs">币种</label><select className="form-input text-sm" value={expFilters.currency} onChange={e => setExpFilters({ ...expFilters, currency: e.target.value })}><option value="">全部</option><option value="THB">THB</option><option value="CNY">CNY</option></select></div>
            <div className="w-[150px]"><label className="form-label text-xs">账户</label><select className="form-input text-sm" value={expFilters.account_id} onChange={e => setExpFilters({ ...expFilters, account_id: +e.target.value })}><option value={0}>全部账户</option>{accounts.map((a: any) => <option key={a.id} value={a.id}>{a.account_name}</option>)}</select></div>
            <button onClick={handleSearch} className="btn-primary flex items-center gap-1.5 text-sm h-[38px]"><Search size={15} />查询</button>
            <button onClick={() => { setExpFilters({ category_id: 0, account_id: 0, currency: "", start_date: "", end_date: "" }); setMonth(new Date().toISOString().slice(0, 7)); setExpPage(1); }} className="btn-secondary flex items-center gap-1.5 text-sm h-[38px]">重置</button>
          </div>
        </div>

        {expLoading ? (
          <div className="flex items-center justify-center h-40 text-gray-400"><div className="animate-spin w-5 h-5 border-2 border-blue-600 border-t-transparent rounded-full mr-2" />加载中...</div>
        ) : expenses.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-gray-400 bg-gray-50/50 rounded-xl"><Minus size={40} className="text-gray-200 mb-3" /><span className="text-sm">暂无支出记录</span></div>
        ) : (
          <DataTable
            columns={[
              { key: "expense_date", label: "日期", render: (v: string) => v?.slice(0, 10) },
              { key: "category_name", label: "类别" },
              { key: "account_name", label: "账户" },
              { key: "amount", label: "金额", render: (v: number) => <span className="font-medium">¥{v?.toLocaleString()}</span> },
              { key: "currency", label: "币种" },
              { key: "remark", label: "备注" },
              { key: "voucher", label: "凭证", render: (v: any) => {
                  const list = parseVouchers(v);
                  return list.length ? (
                    <button onClick={(e) => { e.stopPropagation(); setZoomVouchers(list); setZoomIndex(0); }} className="text-blue-600 hover:underline text-xs font-medium">凭证({list.length})</button>
                  ) : <span className="text-gray-300">无</span>;
                } },
            ]}
            data={expenses} total={expTotal} page={expPage} pageSize={25} onPageChange={setExpPage}
          />
        )}

        <div className="mt-4 pt-4 border-t border-gray-100 flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-red-50 flex items-center justify-center"><DollarSign size={18} className="text-red-500" /></div>
          <span className="text-sm text-gray-500">当前筛选结果支出合计</span>
          <span className="text-xl font-bold text-red-600">¥{curMonthExpense.toLocaleString()}</span>
        </div>
      </div>

      {/* 收支对比 */}
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
        <div className="flex items-center gap-2.5 mb-4">
          <div className="w-9 h-9 rounded-lg bg-indigo-50 flex items-center justify-center"><DollarSign size={20} className="text-indigo-600" /></div>
          <div><h2 className="text-base font-semibold text-gray-800">收支对比</h2><span className="text-xs text-gray-400">{viewMode === "month" ? "本月" : "本周"}</span></div>
          <div className="ml-auto flex bg-white rounded-lg border p-0.5">
            <button onClick={() => setViewMode("week")} className={`px-3 py-1.5 rounded text-xs font-medium transition-colors ${viewMode === "week" ? "bg-blue-600 text-white shadow-sm" : "text-gray-400 hover:text-gray-600"}`}>按周</button>
            <button onClick={() => setViewMode("month")} className={`px-3 py-1.5 rounded text-xs font-medium transition-colors ${viewMode === "month" ? "bg-blue-600 text-white shadow-sm" : "text-gray-400 hover:text-gray-600"}`}>按月</button>
          </div>
        </div>
        {dashboard ? (
          <div className="grid grid-cols-3 gap-5">
            <div className="bg-gradient-to-br from-green-50 to-emerald-50 rounded-2xl p-6 border border-green-100 shadow-sm">
              <div className="flex items-center gap-2 mb-3"><div className="w-8 h-8 rounded-lg bg-green-100 flex items-center justify-center"><ArrowUp size={16} className="text-green-600" /></div><span className="text-sm font-medium text-green-700">充值收入</span></div>
              <div className="text-2xl font-bold text-green-700">¥{dashboard.current_income.toLocaleString()}</div>
            </div>
            <div className="bg-gradient-to-br from-red-50 to-rose-50 rounded-2xl p-6 border border-red-100 shadow-sm">
              <div className="flex items-center gap-2 mb-3"><div className="w-8 h-8 rounded-lg bg-red-100 flex items-center justify-center"><ArrowDown size={16} className="text-red-600" /></div><span className="text-sm font-medium text-red-700">运营支出</span></div>
              <div className="text-2xl font-bold text-red-700">¥{dashboard.current_expense.toLocaleString()}</div>
            </div>
            <div className={`bg-gradient-to-br rounded-2xl p-6 border shadow-sm ${dashboard.current_net >= 0 ? "from-blue-50 to-sky-50 border-blue-100" : "from-orange-50 to-amber-50 border-orange-100"}`}>
              <div className="flex items-center gap-2 mb-3"><div className={`w-8 h-8 rounded-lg flex items-center justify-center ${dashboard.current_net >= 0 ? "bg-blue-100" : "bg-orange-100"}`}>{dashboard.current_net >= 0 ? <TrendingUp size={16} className="text-blue-600" /> : <TrendingDown size={16} className="text-orange-600" />}</div><span className={`text-sm font-medium ${dashboard.current_net >= 0 ? "text-blue-700" : "text-orange-700"}`}>盈亏</span></div>
              <div className={`text-2xl font-bold ${dashboard.current_net >= 0 ? "text-blue-700" : "text-orange-700"}`}>{dashboard.current_net >= 0 ? "+" : ""}¥{dashboard.current_net.toLocaleString()}</div>
            </div>
          </div>
        ) : (
          <div className="flex items-center justify-center h-24 text-gray-400"><div className="animate-spin w-5 h-5 border-2 border-blue-600 border-t-transparent rounded-full mr-2" />加载中...</div>
        )}
      </div>

      {/* 录入弹窗 */}
      {showForm && (
        <div className="modal-overlay" onClick={closeForm}>
          <div className="bg-white rounded-2xl w-full max-w-md shadow-2xl" onClick={e => e.stopPropagation()}>
            <div className="bg-red-500 text-white px-6 py-4 rounded-t-2xl flex items-center gap-3">
              <Minus size={20} /><h2 className="text-lg font-semibold">录入运营支出</h2>
              <button onClick={closeForm} className="ml-auto text-red-200 hover:text-white text-xl leading-none">&times;</button>
            </div>
            <div className="p-6 space-y-4">
              <div><label className="form-label">日期</label><input type="date" className="form-input" value={form.date} onChange={e => setForm({...form, date: e.target.value})} /></div>
              <div><label className="form-label">类别</label><select className="form-input" value={form.category_id} onChange={e => setForm({...form, category_id: +e.target.value})}><option value={0}>选择类别</option>{categories.map((c: any) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></div>
              <div><label className="form-label">账户</label><select className="form-input" value={form.account_id} onChange={e => setForm({...form, account_id: +e.target.value})}><option value={0}>选择账户</option>{accounts.map((a: any) => <option key={a.id} value={a.id}>{a.account_name}</option>)}</select></div>
              <div className="grid grid-cols-2 gap-3">
                <div><label className="form-label">金额</label><input type="number" step="0.01" className="form-input" value={form.amount} onChange={e => setForm({...form, amount: e.target.value === "" ? "" : +e.target.value})} /></div>
                <div><label className="form-label">币种</label><select className="form-input" value={form.currency} onChange={e => setForm({...form, currency: e.target.value})}><option value="THB">THB 泰铢</option><option value="CNY">CNY 人民币</option></select></div>
              </div>
              <div><label className="form-label">备注</label><input className="form-input" value={form.remark} onChange={e => setForm({...form, remark: e.target.value})} /></div>
              <div>
                <label className="form-label">凭证图片（可选，可多张）</label>
                <input type="file" accept="image/*" multiple className="form-input" onChange={handleVoucherSelect} />
                {voucherPreviews.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-2">
                    {voucherPreviews.map((p, i) => (
                      <div key={i} className="relative inline-block">
                        <img src={p} alt={`凭证${i + 1}`} className="h-20 w-20 rounded-lg border object-cover" />
                        <button onClick={() => removeVoucher(i)} className="absolute -top-2 -right-2 bg-red-500 text-white rounded-full w-5 h-5 text-xs leading-none">×</button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
            <div className="border-t px-6 py-4 bg-gray-50 rounded-b-2xl flex justify-end gap-3">
              <button onClick={closeForm} className="btn-secondary">取消</button>
              <button onClick={handleCreate} className="btn-primary">保存</button>
            </div>
          </div>
        </div>
      )}

      {/* 凭证大图预览（多图可切换） */}
      {zoomVouchers.length > 0 && (
        <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-[60] p-4" onClick={() => setZoomVouchers([])}>
          <div className="relative w-full max-w-4xl" onClick={e => e.stopPropagation()}>
            <button onClick={() => setZoomVouchers([])} className="absolute -top-3 -right-3 bg-white rounded-full w-8 h-8 shadow z-10 text-gray-600 hover:text-black text-xl leading-none">&times;</button>
            <img src={`/${zoomVouchers[zoomIndex]}`} alt={`凭证${zoomIndex + 1}`} className="mx-auto max-h-[68vh] max-w-full rounded-lg shadow-2xl object-contain" />
            {zoomVouchers.length > 1 && (
              <>
                <button onClick={() => setZoomIndex(i => (i - 1 + zoomVouchers.length) % zoomVouchers.length)} className="absolute left-2 top-1/2 -translate-y-1/2 bg-white/80 hover:bg-white rounded-full w-9 h-9 shadow text-xl leading-none text-gray-700">‹</button>
                <button onClick={() => setZoomIndex(i => (i + 1) % zoomVouchers.length)} className="absolute right-2 top-1/2 -translate-y-1/2 bg-white/80 hover:bg-white rounded-full w-9 h-9 shadow text-xl leading-none text-gray-700">›</button>
              </>
            )}
            <div className="flex justify-center gap-2 mt-3 flex-wrap">
              {zoomVouchers.map((p, i) => (
                <img key={i} src={`/${p}`} onClick={() => setZoomIndex(i)} className={`h-14 w-14 object-cover rounded cursor-pointer border-2 ${i === zoomIndex ? "border-blue-500" : "border-transparent"}`} />
              ))}
            </div>
            <div className="text-center text-white text-xs mt-2">{zoomIndex + 1} / {zoomVouchers.length}</div>
          </div>
        </div>
      )}
    </>
  );
}

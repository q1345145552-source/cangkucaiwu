"use client";
import { useEffect, useState } from "react";
import { useToast } from "@/components/ui/Toast";
import { api, getToken, getActiveWarehouseId } from "@/lib/api";
import { useRouter } from "next/navigation";
import DataTable from "@/components/common/DataTable";
import { TrendingUp, TrendingDown, Plus, DollarSign, Minus, ArrowUp, ArrowDown } from "lucide-react";

function todayStr(): string {
  const n = new Date();
  return `${n.getFullYear()}-${String(n.getMonth() + 1).padStart(2, "0")}-${String(n.getDate()).padStart(2, "0")}`;
}
function monthStartStr(): string {
  const n = new Date();
  return `${n.getFullYear()}-${String(n.getMonth() + 1).padStart(2, "0")}-01`;
}

export default function OperatingPage() {
  const { toast } = useToast(); const router = useRouter();
  const [dashboard, setDashboard] = useState<any>(null);
  const [expenses, setExpenses] = useState<any[]>([]); const [expTotal, setExpTotal] = useState(0);
  const [expPage, setExpPage] = useState(1);
  const [dateRange, setDateRange] = useState({ start_date: monthStartStr(), end_date: todayStr() });
  const [loading, setLoading] = useState(false);
  const [expLoading, setExpLoading] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [categories, setCategories] = useState<any[]>([]);
  const [accounts, setAccounts] = useState<any[]>([]);
  const [form, setForm] = useState({ category_id: 0, account_id: 0, amount: "", currency: "THB", date: todayStr(), remark: "" });
  const [expFilters, setExpFilters] = useState({ category_id: 0, account_id: 0, currency: "" });
  const [voucherFiles, setVoucherFiles] = useState<File[]>([]);
  const [voucherPreviews, setVoucherPreviews] = useState<string[]>([]);
  const [zoomVouchers, setZoomVouchers] = useState<string[]>([]);
  const [zoomIndex, setZoomIndex] = useState(0);
  // 编辑
  const [editingExpense, setEditingExpense] = useState<any>(null);
  const [editForm, setEditForm] = useState({ category_id: 0, account_id: 0, amount: "", currency: "THB", date: "", remark: "" });
  const [editExistingVouchers, setEditExistingVouchers] = useState<string[]>([]);
  const [editDeleteVouchers, setEditDeleteVouchers] = useState<string[]>([]);
  const [editVoucherFiles, setEditVoucherFiles] = useState<File[]>([]);
  const [editVoucherPreviews, setEditVoucherPreviews] = useState<string[]>([]);
  const [confirmDeleteVoucher, setConfirmDeleteVoucher] = useState<string | null>(null);
  // 删除记录 / 历史
  const [deletingExpense, setDeletingExpense] = useState<any>(null);
  const [historyRow, setHistoryRow] = useState<any>(null);
  const [historyData, setHistoryData] = useState<any[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);

  useEffect(() => { if (!getToken()) { router.push("/login"); return; } loadRefs(); }, []);
  useEffect(() => { loadDashboard(); }, [dateRange]);
  useEffect(() => { loadExpenses(); }, [expPage, expFilters, dateRange]);

  async function loadDashboard() {
    setLoading(true);
    try {
      const r = await api.get<any>(`/income-expense/operating-dashboard?start_date=${dateRange.start_date}&end_date=${dateRange.end_date}`);
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
      params.set("start_date", dateRange.start_date);
      params.set("end_date", dateRange.end_date);
      if (expFilters.category_id) params.set("category_id", String(expFilters.category_id));
      if (expFilters.account_id) params.set("account_id", String(expFilters.account_id));
      if (expFilters.currency) params.set("currency", expFilters.currency);
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
      setForm({ category_id: 0, account_id: 0, amount: "", currency: "THB", date: todayStr(), remark: "" });
      clearVoucher();
      loadExpenses(); loadDashboard();
    } catch (err: any) { toast("error", err.message || "录入失败"); }
  }

  // ===== 编辑 =====
  function openEdit(row: any) {
    loadRefs();
    setEditingExpense(row);
    setEditForm({
      category_id: row.category_id || 0,
      account_id: row.account_id || 0,
      amount: String(row.amount || ""),
      currency: row.currency || "THB",
      date: row.expense_date?.slice(0, 10) || "",
      remark: row.remark || "",
    });
    setEditExistingVouchers(parseVouchers(row.voucher));
    setEditDeleteVouchers([]);
    setEditVoucherFiles([]);
    setEditVoucherPreviews([]);
  }

  function handleEditVoucherSelect(e: any) {
    const fileList: FileList | null = e.target.files;
    if (!fileList || !fileList.length) return;
    const files: File[] = Array.from(fileList);
    const newPreviews = files.map((f: File) => URL.createObjectURL(f));
    setEditVoucherFiles(prev => [...prev, ...files]);
    setEditVoucherPreviews(prev => [...prev, ...newPreviews]);
    e.target.value = "";
  }

  function removeEditVoucherFile(i: number) {
    if (editVoucherPreviews[i]) URL.revokeObjectURL(editVoucherPreviews[i]);
    setEditVoucherFiles(prev => prev.filter((_, idx) => idx !== i));
    setEditVoucherPreviews(prev => prev.filter((_, idx) => idx !== i));
  }

  function closeEdit() {
    setEditingExpense(null);
    setEditDeleteVouchers([]);
    setEditVoucherFiles([]);
    editVoucherPreviews.forEach(p => URL.revokeObjectURL(p));
    setEditVoucherPreviews([]);
    setConfirmDeleteVoucher(null);
  }

  function doConfirmDeleteVoucher() {
    if (!confirmDeleteVoucher) return;
    setEditExistingVouchers(prev => prev.filter(p => p !== confirmDeleteVoucher));
    setEditDeleteVouchers(prev => [...prev, confirmDeleteVoucher]);
    setConfirmDeleteVoucher(null);
  }

  async function handleEditSave() {
    if (!editForm.category_id) { toast("error", "请选择类别"); return; }
    if (!editForm.account_id) { toast("error", "请选择账户"); return; }
    try {
      const fd = new FormData();
      fd.append("category_id", String(editForm.category_id));
      fd.append("account_id", String(editForm.account_id));
      fd.append("amount", String(editForm.amount || 0));
      fd.append("currency", editForm.currency || "THB");
      fd.append("expense_date", editForm.date);
      if (editForm.remark) fd.append("remark", editForm.remark);
      if (editDeleteVouchers.length) fd.append("delete_vouchers", JSON.stringify(editDeleteVouchers));
      if (editVoucherFiles.length) editVoucherFiles.forEach(f => fd.append("files", f));

      const headers: Record<string, string> = {};
      const token = getToken();
      if (token) headers["Authorization"] = `Bearer ${token}`;
      const whId = getActiveWarehouseId();
      if (whId !== null) headers["X-Warehouse-ID"] = whId;

      const res = await fetch(`/api/v1/income-expense/expense/${editingExpense.id}`, {
        method: "PUT", headers, body: fd,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        let msg = err.detail || "更新失败";
        if (Array.isArray(err.detail)) msg = err.detail.map((e: any) => e.msg).join("; ");
        throw new Error(msg);
      }
      toast("success", "更新成功");
      closeEdit();
      loadExpenses(); loadDashboard();
    } catch (err: any) { toast("error", err.message || "更新失败"); }
  }

  async function handleDeleteExpense() {
    try {
      await api.delete(`/income-expense/expense/${deletingExpense.id}`);
      toast("success", "删除成功");
      setDeletingExpense(null);
      loadExpenses(); loadDashboard();
    } catch (err: any) { toast("error", err.message || "删除失败"); }
  }

  async function openHistory(row: any) {
    setHistoryRow(row);
    setHistoryLoading(true);
    setHistoryData([]);
    try {
      const r = await api.get<any>(`/history?module=expense&record_id=${row.id}&page_size=100`);
      setHistoryData(r.data || []);
    } catch {}
    setHistoryLoading(false);
  }

  const opTypeLabel = (op: string) => op === "create" ? "新建" : op === "edit" ? "编辑" : op === "delete" ? "删除" : op;
  const opTypeColor = (op: string) => op === "create" ? "bg-green-100 text-green-700" : op === "edit" ? "bg-blue-100 text-blue-700" : "bg-red-100 text-red-700";
  function renderData(obj: any): string {
    if (!obj) return "-";
    if (typeof obj === "object") return Object.entries(obj).map(([k, v]) => `${k}: ${typeof v === "object" ? JSON.stringify(v) : v}`).join("，");
    return String(obj);
  }

  function resetFilters() {
    setExpFilters({ category_id: 0, account_id: 0, currency: "" });
    setDateRange({ start_date: monthStartStr(), end_date: todayStr() });
    setExpPage(1);
  }

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
      dots.push(<circle key={"d" + i} cx={x} cy={y} r={3.5} fill="#2563EB" stroke="white" strokeWidth={2}><title>{d[i].label}: ¥{Math.round(d[i].recharge_income || 0).toLocaleString()}</title></circle>);
    }
    areaPath += "L" + (px + (d.length - 1) * step) + "," + (py + gh) + " L" + px + "," + (py + gh) + " Z";

    const gridLines: any[] = [];
    for (let j = 0; j <= 4; j++) {
      const y = py + j * gh / 4;
      gridLines.push(<line key={"g" + j} x1={px} y1={y} x2={w - 30} y2={y} stroke="#e5e7eb" strokeWidth={1} strokeDasharray="4,3" />);
      gridLines.push(<text key={"gt" + j} x={px - 10} y={y + 4} textAnchor="end" fill="#9ca3af" fontSize={11}>{Math.round(scale * (4 - j) / 4).toLocaleString()}</text>);
    }

    const labelStep = d.length > 15 ? Math.ceil(d.length / 8) : 1;

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
        {d.map((x: any, i: number) => {
          if (i % labelStep !== 0 && i !== d.length - 1) return null;
          const lab = dashboard.granularity === "day" ? x.label.slice(5) : x.label;
          return <text key={"l" + i} x={px + i * step} y={h - 10} textAnchor="middle" fill="#6b7280" fontSize={12}>{lab}</text>;
        })}
      </svg>
    );
  }

  return (
    <>
      <div className="flex items-center justify-between mb-5 flex-wrap gap-3">
        <h1 className="page-title">运营收支</h1>
        <div className="flex items-center gap-2 flex-wrap">
          <div className="flex items-center gap-2 bg-white rounded-lg border p-1.5">
            <input type="date" value={dateRange.start_date} onChange={e => { setDateRange({ ...dateRange, start_date: e.target.value }); setExpPage(1); }} className="form-input text-sm w-[140px]" />
            <span className="text-gray-400 text-xs">至</span>
            <input type="date" value={dateRange.end_date} onChange={e => { setDateRange({ ...dateRange, end_date: e.target.value }); setExpPage(1); }} className="form-input text-sm w-[140px]" />
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
          <div><h2 className="text-base font-semibold text-gray-800">充值收入趋势</h2><span className="text-xs text-gray-400">{dashboard?.granularity === "day" ? "按日" : "按月"} · {dateRange.start_date} ~ {dateRange.end_date}</span></div>
          <div className="ml-auto flex items-center gap-1.5"><div className="w-2.5 h-2.5 rounded-full bg-blue-600" /><span className="text-xs text-gray-400">充值收入</span></div>
        </div>
        {loading ? (
          <div className="flex items-center justify-center h-64 text-gray-400"><div className="animate-spin w-6 h-6 border-2 border-blue-600 border-t-transparent rounded-full mr-2" />加载中...</div>
        ) : dashboard?.data?.length > 0 ? (
          <div className="bg-gradient-to-b from-blue-50/40 to-white rounded-xl p-3">{renderChart()}</div>
        ) : (
          <div className="flex flex-col items-center justify-center h-64 text-gray-400 bg-gray-50/50 rounded-xl"><TrendingUp size={44} className="text-gray-200 mb-3" /><span className="text-sm">该时间范围内暂无充值收入数据</span></div>
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
            <div className="w-[140px]"><label className="form-label text-xs">类别</label><select className="form-input text-sm" value={expFilters.category_id} onChange={e => setExpFilters({ ...expFilters, category_id: +e.target.value })}><option value={0}>全部类别</option>{categories.map((c: any) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></div>
            <div className="w-[110px]"><label className="form-label text-xs">币种</label><select className="form-input text-sm" value={expFilters.currency} onChange={e => setExpFilters({ ...expFilters, currency: e.target.value })}><option value="">全部</option><option value="THB">THB</option><option value="CNY">CNY</option></select></div>
            <div className="w-[150px]"><label className="form-label text-xs">账户</label><select className="form-input text-sm" value={expFilters.account_id} onChange={e => setExpFilters({ ...expFilters, account_id: +e.target.value })}><option value={0}>全部账户</option>{accounts.map((a: any) => <option key={a.id} value={a.id}>{a.account_name}</option>)}</select></div>
            <button onClick={resetFilters} className="btn-secondary flex items-center gap-1.5 text-sm h-[38px]">重置</button>
          </div>
        </div>

        {expLoading ? (
          <div className="flex items-center justify-center h-40 text-gray-400"><div className="animate-spin w-5 h-5 border-2 border-blue-600 border-t-transparent rounded-full mr-2" />加载中...</div>
        ) : expenses.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-gray-400 bg-gray-50/50 rounded-xl"><Minus size={40} className="text-gray-200 mb-3" /><span className="text-sm">该时间范围内暂无支出记录</span></div>
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
              { key: "id", label: "操作", render: (_: any, row: any) => (
                  <div className="flex items-center gap-2">
                    <button onClick={(e) => { e.stopPropagation(); openEdit(row); }} className="text-blue-600 hover:underline text-xs font-medium">编辑</button>
                    <button onClick={(e) => { e.stopPropagation(); setDeletingExpense(row); }} className="text-red-500 hover:underline text-xs font-medium">删除</button>
                    <button onClick={(e) => { e.stopPropagation(); openHistory(row); }} className="text-gray-500 hover:underline text-xs font-medium">历史</button>
                  </div>
                ) },
            ]}
            data={expenses} total={expTotal} page={expPage} pageSize={25} onPageChange={setExpPage}
          />
        )}

        <div className="mt-4 pt-4 border-t border-gray-100 flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-red-50 flex items-center justify-center"><DollarSign size={18} className="text-red-500" /></div>
          <span className="text-sm text-gray-500">运营支出合计（范围内）</span>
          <span className="text-xl font-bold text-red-600">¥{(dashboard?.total_expense || 0).toLocaleString()}</span>
        </div>
      </div>

      {/* 收支对比 */}
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
        <div className="flex items-center gap-2.5 mb-4">
          <div className="w-9 h-9 rounded-lg bg-indigo-50 flex items-center justify-center"><DollarSign size={20} className="text-indigo-600" /></div>
          <div><h2 className="text-base font-semibold text-gray-800">收支对比</h2><span className="text-xs text-gray-400">{dateRange.start_date} ~ {dateRange.end_date}</span></div>
        </div>
        {dashboard ? (
          <div className="grid grid-cols-3 gap-5">
            <div className="bg-gradient-to-br from-green-50 to-emerald-50 rounded-2xl p-6 border border-green-100 shadow-sm">
              <div className="flex items-center gap-2 mb-3"><div className="w-8 h-8 rounded-lg bg-green-100 flex items-center justify-center"><ArrowUp size={16} className="text-green-600" /></div><span className="text-sm font-medium text-green-700">充值收入</span></div>
              <div className="text-2xl font-bold text-green-700">¥{(dashboard.total_income || 0).toLocaleString()}</div>
            </div>
            <div className="bg-gradient-to-br from-red-50 to-rose-50 rounded-2xl p-6 border border-red-100 shadow-sm">
              <div className="flex items-center gap-2 mb-3"><div className="w-8 h-8 rounded-lg bg-red-100 flex items-center justify-center"><ArrowDown size={16} className="text-red-600" /></div><span className="text-sm font-medium text-red-700">运营支出</span></div>
              <div className="text-2xl font-bold text-red-700">¥{(dashboard.total_expense || 0).toLocaleString()}</div>
            </div>
            <div className={`bg-gradient-to-br rounded-2xl p-6 border shadow-sm ${(dashboard.total_net || 0) >= 0 ? "from-blue-50 to-sky-50 border-blue-100" : "from-orange-50 to-amber-50 border-orange-100"}`}>
              <div className="flex items-center gap-2 mb-3"><div className={`w-8 h-8 rounded-lg flex items-center justify-center ${(dashboard.total_net || 0) >= 0 ? "bg-blue-100" : "bg-orange-100"}`}>{(dashboard.total_net || 0) >= 0 ? <TrendingUp size={16} className="text-blue-600" /> : <TrendingDown size={16} className="text-orange-600" />}</div><span className={`text-sm font-medium ${(dashboard.total_net || 0) >= 0 ? "text-blue-700" : "text-orange-700"}`}>盈亏</span></div>
              <div className={`text-2xl font-bold ${(dashboard.total_net || 0) >= 0 ? "text-blue-700" : "text-orange-700"}`}>{(dashboard.total_net || 0) >= 0 ? "+" : ""}¥{(dashboard.total_net || 0).toLocaleString()}</div>
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

      {/* 编辑弹窗 */}
      {editingExpense && (
        <div className="modal-overlay" onClick={closeEdit}>
          <div className="bg-white rounded-2xl w-full max-w-md shadow-2xl max-h-[90vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
            <div className="bg-blue-600 text-white px-6 py-4 rounded-t-2xl flex items-center gap-3">
              <Minus size={20} /><h2 className="text-lg font-semibold">编辑运营支出</h2>
              <button onClick={closeEdit} className="ml-auto text-blue-200 hover:text-white text-xl leading-none">&times;</button>
            </div>
            <div className="p-6 space-y-4">
              <div><label className="form-label">日期</label><input type="date" className="form-input" value={editForm.date} onChange={e => setEditForm({...editForm, date: e.target.value})} /></div>
              <div><label className="form-label">类别</label><select className="form-input" value={editForm.category_id} onChange={e => setEditForm({...editForm, category_id: +e.target.value})}><option value={0}>选择类别</option>{categories.map((c: any) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></div>
              <div><label className="form-label">账户</label><select className="form-input" value={editForm.account_id} onChange={e => setEditForm({...editForm, account_id: +e.target.value})}><option value={0}>选择账户</option>{accounts.map((a: any) => <option key={a.id} value={a.id}>{a.account_name}</option>)}</select></div>
              <div className="grid grid-cols-2 gap-3">
                <div><label className="form-label">金额</label><input type="number" step="0.01" className="form-input" value={editForm.amount} onChange={e => setEditForm({...editForm, amount: e.target.value === "" ? "" : +e.target.value})} /></div>
                <div><label className="form-label">币种</label><select className="form-input" value={editForm.currency} onChange={e => setEditForm({...editForm, currency: e.target.value})}><option value="THB">THB 泰铢</option><option value="CNY">CNY 人民币</option></select></div>
              </div>
              <div><label className="form-label">备注</label><input className="form-input" value={editForm.remark} onChange={e => setEditForm({...editForm, remark: e.target.value})} /></div>
              <div>
                <label className="form-label">已有凭证（点击放大，可删除）</label>
                {editExistingVouchers.length > 0 ? (
                  <div className="mt-2 flex flex-wrap gap-2">
                    {editExistingVouchers.map((p, i) => (
                      <div key={p} className="relative inline-block">
                        <img src={`/${p}`} alt={`凭证${i + 1}`} className="h-20 w-20 rounded-lg border object-cover cursor-pointer" onClick={() => { setZoomVouchers([p]); setZoomIndex(0); }} />
                        <button onClick={() => setConfirmDeleteVoucher(p)} className="absolute -top-2 -right-2 bg-red-500 text-white rounded-full w-5 h-5 text-xs leading-none">×</button>
                      </div>
                    ))}
                  </div>
                ) : <div className="text-xs text-gray-400 mt-1">暂无凭证</div>}
              </div>
              <div>
                <label className="form-label">新增凭证（可选，可多张）</label>
                <input type="file" accept="image/*" multiple className="form-input" onChange={handleEditVoucherSelect} />
                {editVoucherPreviews.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-2">
                    {editVoucherPreviews.map((p, i) => (
                      <div key={i} className="relative inline-block">
                        <img src={p} alt={`新凭证${i + 1}`} className="h-20 w-20 rounded-lg border object-cover" />
                        <button onClick={() => removeEditVoucherFile(i)} className="absolute -top-2 -right-2 bg-red-500 text-white rounded-full w-5 h-5 text-xs leading-none">×</button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
            <div className="border-t px-6 py-4 bg-gray-50 rounded-b-2xl flex justify-end gap-3">
              <button onClick={closeEdit} className="btn-secondary">取消</button>
              <button onClick={handleEditSave} className="btn-primary">保存</button>
            </div>
          </div>
        </div>
      )}

      {/* 删除凭证确认 */}
      {confirmDeleteVoucher && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-[70] p-4" onClick={() => setConfirmDeleteVoucher(null)}>
          <div className="bg-white rounded-2xl p-6 w-full max-w-sm shadow-2xl" onClick={e => e.stopPropagation()}>
            <h3 className="font-semibold text-lg mb-2">删除凭证</h3>
            <p className="text-sm text-gray-500 mb-5">确定要删除这张凭证图片吗？删除后不可恢复。</p>
            <div className="flex justify-end gap-3">
              <button onClick={() => setConfirmDeleteVoucher(null)} className="btn-secondary">取消</button>
              <button onClick={doConfirmDeleteVoucher} className="bg-red-500 text-white px-4 py-2 rounded-lg text-sm">删除</button>
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

      {/* 删除记录确认 */}
      {deletingExpense && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-[70] p-4" onClick={() => setDeletingExpense(null)}>
          <div className="bg-white rounded-2xl p-6 w-full max-w-sm shadow-2xl" onClick={e => e.stopPropagation()}>
            <h3 className="font-semibold text-lg mb-2">删除支出</h3>
            <p className="text-sm text-gray-500 mb-5">确定要彻底删除这笔支出吗？删除后变更历史仍会保留。</p>
            <div className="flex justify-end gap-3">
              <button onClick={() => setDeletingExpense(null)} className="btn-secondary">取消</button>
              <button onClick={handleDeleteExpense} className="bg-red-500 text-white px-4 py-2 rounded-lg text-sm">删除</button>
            </div>
          </div>
        </div>
      )}

      {/* 历史弹窗 */}
      {historyRow && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-[70] p-4" onClick={() => setHistoryRow(null)}>
          <div className="bg-white rounded-2xl w-full max-w-lg max-h-[80vh] overflow-y-auto shadow-2xl" onClick={e => e.stopPropagation()}>
            <div className="bg-gray-800 text-white px-6 py-4 rounded-t-2xl flex items-center gap-3 sticky top-0">
              <h2 className="text-lg font-semibold">变更历史</h2>
              <button onClick={() => setHistoryRow(null)} className="ml-auto text-gray-300 hover:text-white text-xl leading-none">&times;</button>
            </div>
            <div className="p-5 space-y-3">
              {historyLoading ? <div className="text-center py-8 text-gray-400">加载中...</div>
                : historyData.length === 0 ? <div className="text-center py-8 text-gray-400 text-sm">暂无变更记录</div>
                : historyData.map((h: any) => (
                  <div key={h.id} className="border rounded-lg p-3">
                    <div className="flex items-center gap-2 mb-1.5">
                      <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${opTypeColor(h.operation_type)}`}>{opTypeLabel(h.operation_type)}</span>
                      <span className="text-xs text-gray-500">{h.operator_name || "-"} · {h.created_at ? new Date(h.created_at).toLocaleString("zh-CN", { timeZone: "Asia/Bangkok" }) : "-"}</span>
                    </div>
                    {h.before_data && <div className="text-xs text-gray-500 mb-1"><span className="text-gray-400">修改前：</span>{renderData(h.before_data)}</div>}
                    {h.after_data && <div className="text-xs text-gray-600"><span className="text-gray-400">修改后：</span>{renderData(h.after_data)}</div>}
                  </div>
                ))}
            </div>
          </div>
        </div>
      )}
    </>
  );
}

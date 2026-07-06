"use client";
import { useEffect, useState } from "react";
import DataTable from "@/components/common/DataTable";
import { api, getToken } from "@/lib/api";
import { useI18n } from "@/hooks/useI18n";
import { useToast } from "@/components/ui/Toast";
import { useRouter } from "next/navigation";
import { Upload, AlertTriangle, DollarSign, Clock, CheckCircle, AlertCircle, FileText, Receipt, Download, Edit, TrendingUp, Package } from "lucide-react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

export default function PayablePage() {
  const { t } = useI18n();
  const { toast } = useToast(); const router = useRouter();
  const [data, setData] = useState<any[]>([]); const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1); const [showForm, setShowForm] = useState(false);
  const [suppliers, setSuppliers] = useState<any[]>([]);
  const [stats, setStats] = useState<any>(null);
  const [form, setForm] = useState({ supplier_id: 0, bill_number: "", bill_date: "", due_date: "", amount: "", confirmed_amount: "", payment_commitment_days: "", currency: "THB", detail: "", remark: "", is_fund_linked: "" });
  const [billFile, setBillFile] = useState<File | null>(null);
  const [payAmounts, setPayAmounts] = useState<Record<number, string | number>>({});
  const [voucherFile, setVoucherFile] = useState<File | null>(null);
  const [payingBillId, setPayingBillId] = useState(0);
  const [payingRow, setPayingRow] = useState<any>(null);
  const [payMethod, setPayMethod] = useState("银行转账");
  const [showPayModal, setShowPayModal] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [editingBill, setEditingBill] = useState<any>(null);
  const [editForm, setEditForm] = useState({ confirmed_amount: "", detail: "", remark: "", diff_note: "" });
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewLabel, setPreviewLabel] = useState("");
  const [listFilters, setListFilters] = useState({ supplier_id: 0, start_date: "", end_date: "", status: "" });

  useEffect(() => { if (!getToken()) router.push("/login"); load(); loadSuppliers(); loadStats(); }, [page, listFilters]);

  async function load() {
    setLoading(true);
    try {
      const params = new URLSearchParams(); params.set("page", String(page)); params.set("page_size", "25");
      if (listFilters.supplier_id) params.set("supplier_id", String(listFilters.supplier_id));
      if (listFilters.start_date) params.set("start_date", listFilters.start_date);
      if (listFilters.end_date) params.set("end_date", listFilters.end_date);
      if (listFilters.status) params.set("status", listFilters.status);
      const r = await api.get<any>(`/payable?${params.toString()}`); setData(r.data); setTotal(r.total);
    }
    catch (err) { console.error("加载失败:", err); }
    setLoading(false);
  }
  async function loadSuppliers() { try { const r = await api.get<any>("/suppliers?page_size=100"); setSuppliers(r.data); } catch {} }
  async function loadStats() { try { const r = await api.get<any>("/payable/stats"); setStats(r); } catch {} }

  // === 月度订单量 ===
  const today = new Date(); const yyyy = today.getFullYear(); const mm = String(today.getMonth()+1).padStart(2,"0");
  const [orderCount, setOrderCount] = useState("");
  const [orderMonth, setOrderMonth] = useState(`${yyyy}-${mm}`);
  const [orderSaved, setOrderSaved] = useState("");
  async function loadOrderVolume() {
    try {
      const r = await api.get<any>(`/payable/monthly-order?start_month=${yyyy}-01&end_month=${yyyy}-12`);
      const found = r.data.find((x: any) => x.month === `${yyyy}-${mm}`);
      if (found) { setOrderCount(String(found.order_count)); setOrderSaved(String(found.order_count)); }
    } catch {}
  }
  async function saveOrderVolume() {
    try {
      await api.post("/payable/monthly-order", { month: orderMonth, order_count: +orderCount });
      toast("success", "订单量已保存"); setOrderSaved(orderCount);
    } catch { toast("error", "保存失败"); }
  }
  useEffect(() => { loadOrderVolume(); }, []);

  // === 趋势图 ===
  const [showTrend, setShowTrend] = useState(false);
  const [trendData, setTrendData] = useState<any[]>([]);
  const [trendWarnings, setTrendWarnings] = useState<string[]>([]);
  async function loadTrend() {
    try {
      const r = await api.get<any>("/payable/trend?months=6");
      setTrendData(r.data || []);
      setTrendWarnings(r.warnings || []);
      setShowTrend(true);
    } catch { toast("error", "加载趋势失败"); }
  }

  async function handleCreate() {
    try {
      const res = await api.post<any>("/payable", { ...form, amount: form.amount || 0, confirmed_amount: form.confirmed_amount || 0, payment_commitment_days: form.payment_commitment_days || 0 });
      if (billFile && res.id) {
        const fd = new FormData(); fd.append("file", billFile);
        await fetch(`${API_URL}/payable/${res.id}/upload-attachment`, {
          method: "POST", headers: { "Authorization": `Bearer ${getToken()}` }, body: fd,
        });
      }
      toast("success", res.has_diff ? "账单创建成功，已标记对账差异" : "创建成功");
      setShowForm(false); setBillFile(null); setForm({ supplier_id: 0, bill_number: "", bill_date: "", due_date: "", amount: "", confirmed_amount: "", payment_commitment_days: "", currency: "THB", detail: "", remark: "", is_fund_linked: "" });
      load(); loadStats();
    } catch (err: any) { toast("error", err.message || "创建失败"); }
  }

  function openPayModal(row: any) {
    setPayAmounts(prev => ({ ...prev, [row.id]: "" }));
    setPayingBillId(row.id);
    setPayingRow(row);
    setVoucherFile(null);
    setShowPayModal(true);
  }

  async function handlePay() {
    const payAmount = payAmounts[payingBillId] || (payingRow.amount - payingRow.paid_amount);
    try {
      await fetch(`${API_URL}/payable/${payingBillId}/pay?paid_amount=${payAmount}&payment_method=${payMethod}`, {
        method: "PUT", headers: { "Authorization": `Bearer ${getToken()}` },
      });
      if (voucherFile) {
        const fd = new FormData(); fd.append("file", voucherFile);
        await fetch(`${API_URL}/payable/${payingBillId}/upload-voucher`, {
          method: "POST", headers: { "Authorization": `Bearer ${getToken()}` }, body: fd,
        });
      }
      toast("success", "付款成功");
      setShowPayModal(false); load(); loadStats();
    } catch { toast("error", "付款失败"); }
  }

  function openEditModal(row: any) {
    setEditingBill(row);
    setEditForm({
      confirmed_amount: row.confirmed_amount != null ? String(row.confirmed_amount) : "",
      detail: row.detail || "",
      remark: row.remark || "",
      diff_note: row.diff_note || "",
    });
    setShowEditModal(true);
  }

  async function handleEdit() {
    try {
      await api.put<any>(`/payable/${editingBill.id}`, {
        confirmed_amount: editForm.confirmed_amount === "" ? null : +editForm.confirmed_amount,
        detail: editForm.detail,
        remark: editForm.remark,
        diff_note: editForm.diff_note,
      });
      toast("success", "账单更新成功");
      setShowEditModal(false); load(); loadStats();
    } catch (err: any) { toast("error", err.message || "更新失败"); }
  }

  function toggleSelectAll() {
    if (selectedIds.size === data.length) { setSelectedIds(new Set()); }
    else { setSelectedIds(new Set(data.map(r => r.id))); }
  }
  function toggleSelect(id: number) {
    setSelectedIds(prev => { const next = new Set(prev); if (next.has(id)) next.delete(id); else next.add(id); return next; });
  }

  async function handleExport() {
    if (selectedIds.size === 0) { toast("error", "请先在列表中勾选要导出的账单"); return; }
    try {
      const billIds = Array.from(selectedIds).join(",");
      const res = await fetch(`${API_URL}/payable/batch-export?bill_ids=${billIds}`, {
        headers: { "Authorization": `Bearer ${getToken()}` },
      });
      const blob = await res.blob();
      const a = document.createElement("a"); a.href = window.URL.createObjectURL(blob);
      a.download = "payable_export.xlsx"; a.click();
      toast("success", `已导出 ${selectedIds.size} 条账单`);
    } catch { toast("error", "导出失败"); }
  }

  function handleQuery() { setPage(1); setSelectedIds(new Set()); load(); }

  function getFileUrl(path: string) {
    if (!path) return "";
    if (path.startsWith("http")) return path;
    return `${API_URL.replace("/api/v1", "")}${path}`;
  }

  function openPreview(url: string, label: string) {
    setPreviewUrl(url); setPreviewLabel(label);
  }

  const statusColors: Record<string, string> = {
    pending: "px-2 py-1 rounded text-xs font-medium bg-yellow-100 text-yellow-700",
    paid: "px-2 py-1 rounded text-xs font-medium bg-green-100 text-green-700",
    partially_paid: "px-2 py-1 rounded text-xs font-medium bg-blue-100 text-blue-700",
    overdue: "px-2 py-1 rounded text-xs font-medium bg-red-100 text-red-700",
  };
  const statusLabels: Record<string, string> = {
    pending: "待付", paid: "已付", partially_paid: "部分付款", overdue: "逾期",
  };

  return (
    <>
      <h1 className="page-title mb-5">{t("payable")}</h1>

      {/* 总览看板 */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-5">
        <div className="card bg-gradient-to-br from-blue-500 to-blue-600 text-white border-0">
          <div className="flex items-center gap-2 mb-1"><DollarSign size={18} /><span className="text-sm opacity-80">本月应付</span></div>
          <div className="text-2xl font-bold">¥{(stats?.month_total || 0).toLocaleString()}</div>
        </div>
        <div className="card bg-gradient-to-br from-red-500 to-red-600 text-white border-0">
          <div className="flex items-center gap-2 mb-1"><AlertCircle size={18} /><span className="text-sm opacity-80">逾期未付</span></div>
          <div className="text-2xl font-bold">¥{(stats?.overdue_total || 0).toLocaleString()}</div>
        </div>
        <div className="card bg-gradient-to-br from-green-500 to-green-600 text-white border-0">
          <div className="flex items-center gap-2 mb-1"><CheckCircle size={18} /><span className="text-sm opacity-80">本月已付</span></div>
          <div className="text-2xl font-bold">¥{(stats?.month_paid || 0).toLocaleString()}</div>
        </div>
        <div className="card bg-gradient-to-br from-orange-500 to-orange-600 text-white border-0">
          <div className="flex items-center gap-2 mb-1"><Clock size={18} /><span className="text-sm opacity-80">本月未付</span></div>
          <div className="text-2xl font-bold">¥{(stats?.month_unpaid || 0).toLocaleString()}</div>
        </div>
      </div>

      {/* 本月订单量录入 */}
      <div className="card mb-5 p-4">
        <div className="flex items-end gap-3">
          <div className="flex items-center gap-2">
            <Package size={20} className="text-blue-600" />
            <span className="text-sm font-semibold text-gray-600">本月订单量</span>
          </div>
          <div className="w-[100px]"><label className="form-label">月份</label>
            <input type="month" className="form-input text-sm" value={orderMonth} onChange={e => setOrderMonth(e.target.value)} />
          </div>
          <div className="w-[120px]"><label className="form-label">订单数（笔）</label>
            <input type="number" className="form-input" value={orderCount} onChange={e => setOrderCount(e.target.value)} placeholder="输入数量" />
          </div>
          <button onClick={saveOrderVolume} className="btn-primary h-[42px]">保存</button>
          {orderSaved && orderCount === orderSaved && <span className="text-xs text-green-600 self-center pb-1">已保存</span>}
          <div className="flex-1" />
          <button onClick={loadTrend} className="btn-secondary h-[42px] flex items-center gap-1.5"><TrendingUp size={16} />查看趋势</button>
        </div>
      </div>

      {/* 按供应商汇总 */}
      {(stats?.supplier_summary || []).length > 0 && (
        <div className="card mb-5">
          <h3 className="card-title">按供应商汇总（本月）</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {stats.supplier_summary.map((s: any) => (
              <div key={s.supplier_id} className="p-3 bg-gray-50 rounded-lg flex items-center justify-between cursor-pointer hover:bg-blue-50 transition-colors"
                onClick={() => setListFilters(prev => ({ ...prev, supplier_id: s.supplier_id }))}>
                <div>
                  <div className="font-medium text-sm">{s.supplier_name}</div>
                  <div className="text-xs text-gray-400">{s.bill_count}笔账单</div>
                </div>
                <div className="text-right text-xs">
                  <div>应付 <span className="font-medium">¥{s.total_amount.toLocaleString()}</span></div>
                  <div>已付 <span className="text-green-600">¥{s.paid_amount.toLocaleString()}</span></div>
                  <div>未付 <span className="text-red-500">¥{s.unpaid_amount.toLocaleString()}</span></div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 列表筛选 + 操作栏 */}
      <div className="card mb-4 p-4">
        <div className="flex items-end gap-3 flex-wrap">
          <div className="flex-1 min-w-[120px]"><label className="form-label">供应商</label>
            <select className="form-input" value={listFilters.supplier_id} onChange={e => setListFilters({ ...listFilters, supplier_id: +e.target.value })}>
              <option value={0}>全部供应商</option>
              {suppliers.map((s: any) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </div>
          <div className="w-[130px]"><label className="form-label">开始日期</label>
            <input type="date" className="form-input" value={listFilters.start_date} onChange={e => setListFilters({ ...listFilters, start_date: e.target.value })} />
          </div>
          <div className="w-[130px]"><label className="form-label">结束日期</label>
            <input type="date" className="form-input" value={listFilters.end_date} onChange={e => setListFilters({ ...listFilters, end_date: e.target.value })} />
          </div>
          <div className="w-[130px]"><label className="form-label">状态</label>
            <select className="form-input" value={listFilters.status} onChange={e => setListFilters({ ...listFilters, status: e.target.value })}>
              <option value="">全部</option>
              <option value="pending">待付</option>
              <option value="paid">已付</option>
              <option value="partially_paid">部分付款</option>
              <option value="overdue">逾期</option>
            </select>
          </div>
          <button onClick={handleQuery} className="btn-primary h-[42px]">查询</button>
          <div className="flex-1" />
          <button onClick={handleExport} className="btn-secondary flex items-center gap-1 h-[42px]" disabled={selectedIds.size === 0}>
            <Download size={16} />导出选中{selectedIds.size > 0 ? ` (${selectedIds.size})` : ""}
          </button>
          {selectedIds.size > 0 && (
            <button onClick={() => { setSelectedIds(new Set()); }} className="text-xs text-gray-400 hover:text-gray-600 self-center">
              清除选择
            </button>
          )}
          <button onClick={() => setShowForm(true)} className="btn-primary h-[42px]">新建账单</button>
        </div>
      </div>

      {loading ? <div className="text-center py-8 text-gray-400">加载中...</div> : <DataTable columns={[
        {
          key: "_select", label: "",
          headerRender: () => <input type="checkbox" checked={data.length > 0 && selectedIds.size === data.length} onChange={toggleSelectAll} className="w-4 h-4" />,
          render: (_: any, row: any) => <input type="checkbox" checked={selectedIds.has(row.id)} onChange={() => toggleSelect(row.id)} className="w-4 h-4" />
        },
        { key: "supplier_name", label: "供应商" },
        { key: "bill_number", label: "账单编号" },
        { key: "bill_date", label: "账单日期", render: (v: any) => v?.slice(0, 10) },
        { key: "due_date", label: "到期日", render: (v: any) => v?.slice(0, 10) },
        {
          key: "amount", label: "金额", align: "right", render: (v: any, row: any) => {
            const diff = row.confirmed_amount && row.confirmed_amount !== row.amount;
            return <span>{v?.toLocaleString()} {diff && <AlertTriangle size={12} className="inline text-orange-500 ml-1" title={`供应商确认: ${row.confirmed_amount}`} />}</span>
          }
        },
        { key: "paid_amount", label: "已付", align: "right", render: (v: any) => v?.toLocaleString() },
        { key: "status", label: "状态", render: (v: any) => <span className={statusColors[v] || ""}>{statusLabels[v] || v}</span> },
        { key: "detail", label: "明细", render: (v: any) => v ? <span className="text-xs text-gray-500 max-w-32 truncate block" title={v}>{v.length > 12 ? v.slice(0, 12) + "..." : v}</span> : "-" },
        { key: "bill_attachment", label: "附件", render: (v: any) => v ? <button onClick={() => openPreview(getFileUrl(v), "账单附件")} className="text-blue-600 text-xs hover:underline cursor-pointer">查看</button> : <span className="text-gray-300 text-xs">-</span> },
        { key: "payment_voucher", label: "凭证", render: (v: any) => v ? <button onClick={() => openPreview(getFileUrl(v), "付款凭证")} className="text-blue-600 text-xs hover:underline cursor-pointer">查看</button> : <span className="text-gray-300 text-xs">-</span> },
        { key: "id", label: "操作", render: (_: any, row: any) => <div className="flex items-center gap-1">{row.status !== "paid" && <button onClick={() => openPayModal(row)} className="btn-primary btn-xs">付款</button>}<button onClick={() => openEditModal(row)} className="btn-secondary btn-xs flex items-center gap-0.5"><Edit size={12} />编辑</button></div> },
      ]} data={data} total={total} page={page} pageSize={25} onPageChange={setPage} />}

      {/* 新建账单弹窗 */}
      {showForm && (
        <div className="modal-overlay" onClick={() => setShowForm(false)}>
          <div className="bg-white rounded-xl w-full max-w-lg max-h-[90vh] overflow-auto shadow-2xl" onClick={e => e.stopPropagation()}>
            <div className="bg-blue-600 text-white px-6 py-4 rounded-t-xl flex items-center gap-3">
              <FileText size={22} />
              <div className="flex-1"><h2 className="text-lg font-semibold">新建应付账单</h2></div>
              <button onClick={() => setShowForm(false)} className="text-blue-200 hover:text-white"><span className="text-xl leading-none">&times;</span></button>
            </div>

            <div className="p-6 space-y-4">
              {/* 基本信息 */}
              <div className="text-sm font-semibold text-gray-400 pb-1 border-b">基本信息</div>
              <div className="form-group"><label className="form-label">供应商</label>
                <select className="form-input" value={form.supplier_id} onChange={e => setForm({ ...form, supplier_id: +e.target.value })}>
                  <option value={0}>选择供应商</option>
                  {suppliers.map((s: any) => <option key={s.id} value={s.id}>{s.name}</option>)}
                </select>
              </div>
              <div className="form-grid">
                <div className="form-group"><label className="form-label">账单编号</label><input className="form-input" value={form.bill_number} onChange={e => setForm({ ...form, bill_number: e.target.value })} /></div>
                <div className="form-group"><label className="form-label">币种</label><select className="form-input" value={form.currency} onChange={e => setForm({ ...form, currency: e.target.value })}><option>THB</option><option>CNY</option><option>USD</option></select></div>
              </div>
              <div className="form-grid">
                <div className="form-group"><label className="form-label">账单日期</label><input type="date" className="form-input" value={form.bill_date} onChange={e => setForm({ ...form, bill_date: e.target.value })} /></div>
                <div className="form-group"><label className="form-label">到期日期</label><input type="date" className="form-input" value={form.due_date} onChange={e => setForm({ ...form, due_date: e.target.value })} /></div>
              </div>

              <div className="text-sm font-semibold text-gray-400 pb-1 border-b">金额信息</div>
              <div className="form-grid">
                <div className="form-group"><label className="form-label">金额</label><input type="number" className="form-input" value={form.amount || ""} onChange={e => setForm({ ...form, amount: e.target.value===""?"":+e.target.value })} /></div>
                <div className="form-group"><label className="form-label">供应商确认金额</label><input type="number" className="form-input" value={form.confirmed_amount || ""} onChange={e => setForm({ ...form, confirmed_amount: e.target.value===""?"":+e.target.value })} /></div>
              </div>
              <div className="form-group"><label className="form-label">付款承诺天数</label><input type="number" className="form-input" value={form.payment_commitment_days || ""} onChange={e => setForm({ ...form, payment_commitment_days: e.target.value===""?"":+e.target.value })} /></div>

              <div className="text-sm font-semibold text-gray-400 pb-1 border-b">补充信息</div>
              <div className="form-group"><label className="form-label">费用明细</label><textarea className="form-input" rows={3} value={form.detail} onChange={e => setForm({ ...form, detail: e.target.value })} placeholder="费用明细描述" /></div>
              <div className="form-group">
                <label className="form-label">账单附件（非必填，支持图片和PDF）</label>
                <div className="border-2 border-dashed border-gray-200 rounded-lg p-4 text-center hover:border-blue-400 transition-colors">
                  <Upload size={24} className="mx-auto text-gray-300 mb-2" />
                  <input type="file" accept="image/*,.pdf" onChange={e => setBillFile(e.target.files?.[0] || null)} className="text-sm text-gray-500" />
                  <div className="text-xs text-gray-400 mt-2">上传供应商发来的账单文件</div>
                </div>
              </div>
            </div>

            <div className="border-t px-6 py-4 bg-gray-50 rounded-b-xl flex justify-end gap-3">
              <button onClick={() => setShowForm(false)} className="btn-secondary min-w-[80px]">取消</button>
              <button onClick={handleCreate} className="btn-primary min-w-[80px]">保存</button>
            </div>
          </div></div>
      )}

      {/* 编辑弹窗 */}
      {showEditModal && editingBill && (
        <div className="modal-overlay" onClick={() => setShowEditModal(false)}>
          <div className="bg-white rounded-xl w-full max-w-lg max-h-[90vh] overflow-auto shadow-2xl" onClick={e => e.stopPropagation()}>
            <div className="bg-orange-500 text-white px-6 py-4 rounded-t-xl flex items-center gap-3">
              <Edit size={22} />
              <div className="flex-1">
                <h2 className="text-lg font-semibold">编辑账单</h2>
                <div className="text-xs text-orange-100 mt-0.5">账单编号：{editingBill.bill_number} · 供应商：{editingBill.supplier_name}</div>
              </div>
              <button onClick={() => setShowEditModal(false)} className="text-orange-200 hover:text-white"><span className="text-xl leading-none">&times;</span></button>
            </div>
            <div className="p-6 space-y-4">
              <div className="form-grid">
                <div className="form-group">
                  <label className="form-label">原金额</label>
                  <div className="form-input bg-gray-50 text-gray-600 flex items-center">¥{editingBill.amount?.toLocaleString()}</div>
                </div>
                <div className="form-group">
                  <label className="form-label">确认金额</label>
                  <input type="number" className="form-input" value={editForm.confirmed_amount} onChange={e => setEditForm({ ...editForm, confirmed_amount: e.target.value })} placeholder="确认后的实际金额" />
                </div>
              </div>
              {editForm.confirmed_amount !== "" && +editForm.confirmed_amount !== editingBill.amount && (
                <div className="bg-orange-50 border border-orange-200 rounded-lg p-3 text-sm text-orange-700 flex items-center gap-2">
                  <AlertTriangle size={16} />
                  确认金额与原金额不一致，差额 ¥{Math.abs(editingBill.amount - +editForm.confirmed_amount).toLocaleString()}
                </div>
              )}
              <div className="form-group">
                <label className="form-label">差异处理说明</label>
                <textarea className="form-input" rows={2} value={editForm.diff_note} onChange={e => setEditForm({ ...editForm, diff_note: e.target.value })} placeholder="填写差异原因和处理结果，如：已与供应商协商少付100元" />
              </div>
              <div className="form-group">
                <label className="form-label">费用明细</label>
                <textarea className="form-input" rows={3} value={editForm.detail} onChange={e => setEditForm({ ...editForm, detail: e.target.value })} placeholder="费用明细描述" />
              </div>
              <div className="form-group">
                <label className="form-label">备注</label>
                <input className="form-input" value={editForm.remark} onChange={e => setEditForm({ ...editForm, remark: e.target.value })} placeholder="其他备注" />
              </div>
            </div>
            <div className="border-t px-6 py-4 bg-gray-50 rounded-b-xl flex justify-end gap-3">
              <button onClick={() => setShowEditModal(false)} className="btn-secondary min-w-[80px]">取消</button>
              <button onClick={handleEdit} className="btn-primary min-w-[80px]">保存修改</button>
            </div>
          </div></div>
      )}

      {/* 付款弹窗 */}
      {showPayModal && payingRow && (
        <div className="modal-overlay" onClick={() => setShowPayModal(false)}>
          <div className="bg-white rounded-xl w-full max-w-lg max-h-[85vh] overflow-auto shadow-2xl" onClick={e => e.stopPropagation()}>
            <div className="bg-green-600 text-white px-6 py-4 rounded-t-xl flex items-center gap-3">
              <Receipt size={22} />
              <div className="flex-1">
                <h2 className="text-lg font-semibold">付款</h2>
                <div className="text-xs text-green-100 mt-0.5">
                  账单编号：{payingRow.bill_number} · 供应商：{payingRow.supplier_name}
                </div>
              </div>
              <button onClick={() => setShowPayModal(false)} className="text-green-200 hover:text-white"><span className="text-xl leading-none">&times;</span></button>
            </div>

            <div className="p-6 space-y-5">
              <div className="grid grid-cols-4 gap-3">
                <div className="bg-blue-50 rounded-lg p-3 text-center">
                  <div className="text-xs text-blue-500 mb-1">应付总额</div>
                  <div className="font-bold text-lg text-blue-700">¥{payingRow.amount.toLocaleString()}</div>
                </div>
                <div className="bg-green-50 rounded-lg p-3 text-center">
                  <div className="text-xs text-green-500 mb-1">已付金额</div>
                  <div className="font-bold text-lg text-green-700">¥{payingRow.paid_amount.toLocaleString()}</div>
                </div>
                <div className="bg-purple-50 rounded-lg p-3 text-center">
                  <div className="text-xs text-purple-500 mb-1">本次付款</div>
                  <div className="font-bold text-lg text-purple-700">¥{(payAmounts[payingBillId] || 0).toLocaleString()}</div>
                </div>
                <div className={`rounded-lg p-3 text-center ${(payingRow.amount - payingRow.paid_amount - (payAmounts[payingBillId] || 0)) > 0 ? "bg-orange-50" : "bg-green-100"}`}>
                  <div className={`text-xs mb-1 ${(payingRow.amount - payingRow.paid_amount - (payAmounts[payingBillId] || 0)) > 0 ? "text-orange-500" : "text-green-600"}`}>付款后余额</div>
                  <div className={`font-bold text-lg ${(payingRow.amount - payingRow.paid_amount - (payAmounts[payingBillId] || 0)) > 0 ? "text-orange-700" : "text-green-700"}`}>¥{(payingRow.amount - payingRow.paid_amount - (payAmounts[payingBillId] || 0)).toLocaleString()}</div>
                </div>
              </div>

              <div className="border-t" />

              <div className="form-grid">
                <div className="form-group"><label className="form-label">付款金额</label><input type="number" className="form-input text-lg font-semibold" value={payAmounts[payingBillId] ?? ""} onChange={e => setPayAmounts(prev => ({ ...prev, [payingBillId]: e.target.value === "" ? "" : +e.target.value }))} /></div>
                <div className="form-group"><label className="form-label">付款方式</label><select className="form-input" value={payMethod} onChange={e => setPayMethod(e.target.value)}><option>银行转账</option><option>现金</option><option>支票</option><option>PromptPay</option><option>其他</option></select></div>
              </div>
              <div className="form-group">
                <label className="form-label">上传付款凭证（非必填）</label>
                <div className="border-2 border-dashed border-gray-200 rounded-lg p-4 text-center hover:border-green-400 transition-colors">
                  <Upload size={24} className="mx-auto text-gray-300 mb-2" />
                  <input type="file" accept="image/*" onChange={e => setVoucherFile(e.target.files?.[0] || null)} className="text-sm text-gray-500 file:mr-4 file:py-1 file:px-3 file:rounded file:border-0 file:text-sm file:bg-green-50 file:text-green-700 hover:file:bg-green-100" />
                  <div className="text-xs text-gray-400 mt-2">可选，上传转账截图或回单</div>
                </div>
              </div>
            </div>

            <div className="border-t px-6 py-4 bg-gray-50 rounded-b-xl flex justify-end gap-3">
              <button onClick={() => setShowPayModal(false)} className="btn-secondary min-w-[80px]">取消</button>
              <button onClick={handlePay} className="btn-primary min-w-[80px]">确认付款</button>
            </div>
          </div></div>
      )}

      {/* 图片预览弹窗 */}
      {previewUrl && (
        <div className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center" onClick={() => { setPreviewUrl(null); setPreviewLabel(""); }}>
          <div className="relative max-w-[90vw] max-h-[90vh]" onClick={e => e.stopPropagation()}>
            <div className="absolute top-2 left-4 text-white text-sm bg-black/50 px-3 py-1 rounded-full z-10">{previewLabel}</div>
            <button onClick={() => { setPreviewUrl(null); setPreviewLabel(""); }} className="absolute top-2 right-2 text-white bg-black/50 hover:bg-black/70 rounded-full w-8 h-8 flex items-center justify-center z-10 text-lg leading-none">&times;</button>
            {previewUrl.endsWith(".pdf") ? (
              <div className="bg-white rounded-xl p-8 text-center">
                <FileText size={48} className="mx-auto text-gray-400 mb-4" />
                <p className="text-gray-600 mb-4">PDF 文件</p>
                <a href={previewUrl} target="_blank" className="btn-primary" download>下载查看</a>
              </div>
            ) : (
              <img src={previewUrl} alt={previewLabel} className="max-w-[90vw] max-h-[85vh] object-contain rounded-lg shadow-2xl" />
            )}
          </div>
        </div>
      )}

      {/* 趋势图弹窗 */}
      {showTrend && (
        <div className="modal-overlay" onClick={() => setShowTrend(false)}>
          <div className="bg-white rounded-xl w-full max-w-3xl max-h-[90vh] overflow-auto shadow-2xl" onClick={e => e.stopPropagation()}>
            <div className="bg-indigo-600 text-white px-6 py-4 rounded-t-xl flex items-center gap-3">
              <TrendingUp size={22} /><h2 className="text-lg font-semibold">订单量 vs 耗材支出 趋势对比</h2>
              <div className="flex-1" /><button onClick={() => setShowTrend(false)} className="text-indigo-200 hover:text-white text-xl leading-none">&times;</button>
            </div>
            <div className="p-6">
              {/* SVG Chart */}
              {trendData.length > 0 ? (() => {
                const d = trendData; const m = d.length;
                const w = 800; const h = 300; const px = 60; const py = 40;
                const lw = w - px - 20; const lh = h - py * 2;
                const maxO = Math.max(...d.map((x: any) => x.order_count), 1);
                const maxS = Math.max(...d.map((x: any) => x.consumable_spending), 1);
                const scaleO = Math.ceil(maxO * 1.2); const scaleS = Math.ceil(maxS * 1.2);
                const step = lw / Math.max(m - 1, 1);
                let lineO = ""; let lineS = "";
                const dotsO: any[] = []; const dotsS: any[] = [];
                for (let i = 0; i < m; i++) {
                  const x = px + i * step;
                  const yO = py + lh - (d[i].order_count / scaleO * lh);
                  const yS = py + lh - (d[i].consumable_spending / scaleS * lh);
                  lineO += (i === 0 ? "M" : "L") + x + "," + yO + " ";
                  lineS += (i === 0 ? "M" : "L") + x + "," + yS + " ";
                  dotsO.push(<circle key={"o"+i} cx={x} cy={yO} r={4} fill="#2563EB"><title>订单量: {d[i].order_count}</title></circle>);
                  dotsS.push(<circle key={"s"+i} cx={x} cy={yS} r={4} fill="#EF4444"><title>耗材支出: ¥{d[i].consumable_spending.toLocaleString()}</title></circle>);
                }
                const grid: any[] = [];
                for (let j = 0; j <= 4; j++) {
                  const yy = py + j * lh / 4;
                  grid.push(<line key={"g"+j} x1={px} y1={yy} x2={w-20} y2={yy} stroke="#eee" strokeWidth={1} />);
                  grid.push(<text key={"gt"+j} x={px-8} y={yy+4} textAnchor="end" fill="#999" fontSize={10}>{(scaleO*(4-j)/4).toFixed(0)}</text>);
                }
                return (
                  <svg viewBox="0 0 800 300" className="w-full">
                    {grid}
                    {dotsO}{dotsS}
                    <path d={lineO.trim()} fill="none" stroke="#2563EB" strokeWidth={2.5} />
                    <path d={lineS.trim()} fill="none" stroke="#EF4444" strokeWidth={2.5} strokeDasharray="6,3" />
                    {d.map((x: any, i: number) => <text key={"l"+i} x={px+i*step} y={h-10} textAnchor="middle" fill="#666" fontSize={11}>{x.month.substring(5)}月</text>)}
                  </svg>
                );
              })()
              : (
                <div className="text-center py-12 text-gray-400">暂无数据</div>
              )}

              {/* Warnings */}
              {trendWarnings.length > 0 && (
                <div className="mt-4 space-y-2">
                  {trendWarnings.map((w: string, i: number) => (
                    <div key={i} className="bg-red-50 border border-red-200 rounded-lg p-3 text-sm text-red-700 flex items-center gap-2">
                      <AlertTriangle size={16} /> {w}
                    </div>
                  ))}
                </div>
              )}

              {/* Legend */}
              <div className="flex items-center gap-6 mt-4 pt-3 border-t justify-center">
                <div className="flex items-center gap-2"><div className="w-4 h-4 rounded-full bg-blue-600" /><span className="text-xs text-gray-600">订单量（笔）</span></div>
                <div className="flex items-center gap-2"><div className="w-4 h-4 rounded-full bg-red-500" /><span className="text-xs text-gray-600">耗材支出（元）</span></div>
              </div>
            </div>
          </div>
        </div>
      )}


    </>
  );
}

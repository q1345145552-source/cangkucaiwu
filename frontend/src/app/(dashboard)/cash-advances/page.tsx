"use client";
import { useEffect, useRef, useState } from "react";
import { api, getActiveWarehouseId, getToken } from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import { useMenuPermission } from "@/hooks/useMenuPermission";
import { useToast } from "@/components/ui/Toast";
import { Plus, Receipt, X } from "lucide-react";

interface Advance {
  id: number; payer_id: number | null; payer_name: string; advance_date: string;
  amount: number; purpose: string; purpose_label: string; status: string; status_label: string;
  outstanding_amount: number; description: string | null; voucher_path: string | null;
  reject_reason: string | null; created_by_name: string; created_at: string;
  reviewed_by_name: string | null; reviewed_at: string | null;
}
interface Payer { id: number; name: string; username: string; role: string }
interface Summary { payer_count: number; total_outstanding: number; data: { payer_id: number | null; payer_name: string; outstanding_amount: number }[] }
const PURPOSES = { salary: "工资", purchase: "采购", expense: "费用", other: "其他" };
const ROLES: Record<string, string> = { warehouse_admin: "仓库管理员", supervisor: "主管", staff: "财务", warehouse_labor: "劳工" };
const STATUS_STYLES: Record<string, string> = { pending: "bg-yellow-50 text-yellow-700", confirmed: "bg-green-50 text-green-700", rejected: "bg-red-50 text-red-700", repaid: "bg-gray-100 text-gray-600" };
const money = (value: number) => value.toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const today = () => new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Bangkok", year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());
const newForm = () => ({ payer_id: "", payer_name: "", advance_date: today(), amount: "", purpose: "", description: "" });

export default function CashAdvancesPage() {
  const { user } = useAuth() as { user: any };
  const canView = useMenuPermission("cash_advances");
  const canCreate = canView && ["warehouse_admin", "supervisor"].includes(user?.role);
  const canReview = user?.role === "warehouse_admin";
  const { toast } = useToast();
  const [rows, setRows] = useState<Advance[]>([]);
  const [summary, setSummary] = useState<Summary>({ payer_count: 0, total_outstanding: 0, data: [] });
  const [total, setTotal] = useState(0), [page, setPage] = useState(1);
  const [filters, setFilters] = useState({ start_date: "", end_date: "", status: "", payer_name: "" });
  const [loading, setLoading] = useState(false), [saving, setSaving] = useState(false);
  const [showForm, setShowForm] = useState(false), [manual, setManual] = useState(false);
  const [form, setForm] = useState(newForm), [file, setFile] = useState<File | null>(null);
  const [payers, setPayers] = useState<Payer[]>([]);
  const [reviewing, setReviewing] = useState<number | null>(null), [rejectId, setRejectId] = useState<number | null>(null);
  const [rejectReason, setRejectReason] = useState("");
  const loadVersion = useRef(0);

  useEffect(() => { if (canView) void load(); return () => { loadVersion.current++; }; }, [canView, page, filters]);
  async function load() {
    const version = ++loadVersion.current;
    setLoading(true);
    try {
      const params = new URLSearchParams({ page: String(page), page_size: "20" });
      Object.entries(filters).forEach(([key, value]) => { if (value.trim()) params.set(key, value.trim()); });
      const [list, totals] = await Promise.all([
        api.get<{ data: Advance[]; total: number }>(`/cash-advances?${params}`),
        api.get<Summary>("/cash-advances/summary"),
      ]);
      if (version === loadVersion.current) { setRows(list.data); setTotal(list.total); setSummary(totals); }
    } catch (err: any) { if (version === loadVersion.current) toast("error", err.message || "加载垫款单失败"); }
    finally { if (version === loadVersion.current) setLoading(false); }
  }
  function filter(key: string, value: string) { setPage(1); setFilters(current => ({ ...current, [key]: value })); }
  async function openForm() {
    if (!canCreate) return;
    setForm(newForm()); setManual(false); setFile(null); setPayers([]); setShowForm(true);
    try { const result = await api.get<{ data: Payer[] }>("/cash-advances/payers"); setPayers(result.data); }
    catch (err: any) { toast("error", err.message || "加载垫款账号失败，可填写姓名"); }
  }
  async function create() {
    if (!canCreate || saving) return;
    if (!form.advance_date) { toast("error", "请选择垫款日期"); return; }
    if (!Number.isFinite(Number(form.amount)) || Number(form.amount) <= 0) { toast("error", "垫款金额必须大于零"); return; }
    if (!form.purpose) { toast("error", "请选择用途"); return; }
    if (manual && !form.payer_name.trim()) { toast("error", "请填写垫款人姓名"); return; }
    setSaving(true);
    try {
      let voucher_path: string | null = null;
      if (file) {
        const body = new FormData(); body.append("file", file);
        const headers: Record<string, string> = { Authorization: `Bearer ${getToken()}` };
        const warehouse = getActiveWarehouseId(); if (warehouse) headers["X-Warehouse-ID"] = warehouse;
        const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "/api/v1"}/cash-advances/voucher`, { method: "POST", headers, body });
        const result = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(result.detail || "凭证上传失败");
        voucher_path = result.path;
      }
      await api.post("/cash-advances", { advance_date: form.advance_date, amount: form.amount, purpose: form.purpose,
        description: form.description.trim() || null, voucher_path,
        payer_id: !manual && form.payer_id ? Number(form.payer_id) : null,
        payer_name: manual ? form.payer_name.trim() : null,
      });
      toast("success", "垫款单已登记，待仓库管理员确认"); setShowForm(false); await load();
    } catch (err: any) { toast("error", err.message || "登记失败"); }
    finally { setSaving(false); }
  }
  async function review(id: number, reject = false) {
    if (!canReview || reviewing !== null) return;
    if (reject && !rejectReason.trim()) { toast("error", "请填写驳回原因"); return; }
    setReviewing(id);
    try {
      await api.post(`/cash-advances/${id}/${reject ? "reject" : "confirm"}`, reject ? { reject_reason: rejectReason.trim() } : {});
      toast("success", reject ? "垫款单已驳回" : "垫款单已确认，欠款已登记");
      setRejectId(null); setRejectReason(""); await load();
    } catch (err: any) { toast("error", err.message || "操作失败"); }
    finally { setReviewing(null); }
  }

  if (!canView) return <p className="text-sm text-gray-500">无此操作权限</p>;
  return <div className="space-y-4">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <h1 className="page-title flex items-center gap-2"><Receipt size={24} />垫款单</h1>
      {canCreate && <button type="button" onClick={openForm} className="btn-primary flex items-center gap-1"><Plus size={16} />新建垫款单</button>}
    </div>
    <section className="bg-white rounded-xl border p-4 space-y-2" aria-label="本仓垫款汇总">
      <p>本仓现在欠垫款 <strong>{summary.payer_count}</strong> 人，共 <strong className="text-red-600">{money(summary.total_outstanding)}</strong> 元</p>
      <p className="text-xs text-gray-500">汇总为本仓全部已确认、尚未归还的垫款，不随下方筛选变化。</p>
      {summary.data.length > 0 && <div className="divide-y text-sm">{summary.data.map((payer, index) => <div key={`${payer.payer_id}-${index}`} className="flex justify-between gap-3 py-2"><span>{payer.payer_name}</span><span>{money(payer.outstanding_amount)} 元</span></div>)}</div>}
    </section>
    <div className="flex flex-wrap gap-2 items-center">
      <input aria-label="开始日期" type="date" className="form-input w-auto" value={filters.start_date} onChange={e => filter("start_date", e.target.value)} />
      <span className="text-gray-400">至</span><input aria-label="结束日期" type="date" className="form-input w-auto" value={filters.end_date} onChange={e => filter("end_date", e.target.value)} />
      <select aria-label="状态筛选" className="form-input w-auto" value={filters.status} onChange={e => filter("status", e.target.value)}><option value="">全部状态</option><option value="pending">待确认</option><option value="confirmed">已确认</option><option value="rejected">已驳回</option><option value="repaid">已归还</option></select>
      <input aria-label="垫款人筛选" placeholder="按垫款人姓名筛选" className="form-input w-auto" maxLength={100} value={filters.payer_name} onChange={e => filter("payer_name", e.target.value)} />
    </div>
    <div className="bg-white rounded-xl border overflow-x-auto">
      <table className="w-full text-sm whitespace-nowrap"><thead className="bg-gray-50 text-gray-500"><tr>{["日期", "垫款人", "金额", "用途", "状态", "剩余未还", "说明 / 凭证", "操作"].map(title => <th key={title} className="text-left px-4 py-3">{title}</th>)}</tr></thead>
        <tbody className="divide-y">{rows.map(row => <tr key={row.id}>
          <td className="px-4 py-3">{row.advance_date}</td><td className="px-4 py-3">{row.payer_name}</td><td className="px-4 py-3">{money(row.amount)}</td><td className="px-4 py-3">{row.purpose_label}</td>
          <td className="px-4 py-3"><span className={`rounded px-2 py-1 text-xs ${STATUS_STYLES[row.status]}`}>{row.status_label}</span>{row.reject_reason && <p className="whitespace-normal max-w-48 text-xs text-red-600 mt-2">{row.reject_reason}</p>}</td>
          <td className="px-4 py-3">{money(row.outstanding_amount)}</td>
          <td className="px-4 py-3"><p className="whitespace-normal max-w-56">{row.description || "—"}</p>{row.voucher_path && <a href={`/${row.voucher_path}`} target="_blank" rel="noreferrer" className="text-blue-600">查看凭证</a>}</td>
          <td className="px-4 py-3">{canReview && row.status === "pending" && <div className="flex gap-3"><button type="button" disabled={reviewing !== null} onClick={() => review(row.id)} className="text-green-700 disabled:opacity-50">确认</button><button type="button" disabled={reviewing !== null} onClick={() => { setRejectReason(""); setRejectId(row.id); }} className="text-red-600 disabled:opacity-50">驳回</button></div>}</td>
        </tr>)}{!rows.length && <tr><td colSpan={8} className="text-center text-gray-400 py-10">{loading ? "加载中..." : "暂无垫款单"}</td></tr>}</tbody>
      </table>
    </div>
    <div className="flex items-center justify-between gap-3 text-sm"><span>共 {total} 条，第 {page} 页</span><div className="flex gap-2"><button type="button" className="btn-secondary" disabled={page === 1 || loading} onClick={() => setPage(page - 1)}>上一页</button><button type="button" className="btn-secondary" disabled={page * 20 >= total || loading} onClick={() => setPage(page + 1)}>下一页</button></div></div>
    {showForm && <div role="dialog" aria-modal="true" aria-labelledby="cash-advance-title" className="fixed inset-0 z-[110] bg-black/40 flex items-center justify-center p-3">
      <form onSubmit={e => { e.preventDefault(); void create(); }} className="bg-white rounded-2xl w-full max-w-lg max-h-[90dvh] flex flex-col overflow-hidden">
        <div className="flex justify-between items-center px-5 py-4 border-b shrink-0"><h2 id="cash-advance-title" className="font-semibold">新建垫款单</h2><button type="button" aria-label="关闭" disabled={saving} onClick={() => setShowForm(false)}><X size={20} /></button></div>
        <fieldset disabled={saving} className="p-5 space-y-4 overflow-y-auto min-h-0 min-w-0">
          <div><span className="text-sm">垫款人</span><div className="flex gap-4 text-sm my-2"><label><input type="radio" checked={!manual} onChange={() => setManual(false)} /> 选择账号</label><label><input type="radio" checked={manual} onChange={() => setManual(true)} /> 手填姓名</label></div>
            {manual ? <input aria-label="垫款人姓名" className="form-input" maxLength={100} value={form.payer_name} onChange={e => setForm({ ...form, payer_name: e.target.value })} /> : <select aria-label="垫款账号" className="form-input" value={form.payer_id} onChange={e => setForm({ ...form, payer_id: e.target.value })}><option value="">本人（{user?.display_name}）</option>{payers.map(p => <option key={p.id} value={p.id}>{p.name}（{p.username} / {ROLES[p.role] || p.role}）</option>)}</select>}
          </div>
          <label className="block text-sm">日期<input required type="date" className="form-input mt-1" value={form.advance_date} onChange={e => setForm({ ...form, advance_date: e.target.value })} /></label>
          <label className="block text-sm">金额<input required type="number" min="0.01" step="0.01" className="form-input mt-1" value={form.amount} onChange={e => setForm({ ...form, amount: e.target.value })} /></label>
          <label className="block text-sm">用途<select required className="form-input mt-1" value={form.purpose} onChange={e => setForm({ ...form, purpose: e.target.value })}><option value="">请选择用途</option>{Object.entries(PURPOSES).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
          <label className="block text-sm">说明<textarea className="form-input mt-1" rows={3} maxLength={2000} value={form.description} onChange={e => setForm({ ...form, description: e.target.value })} /></label>
          <label className="block text-sm">凭证照片<input aria-label="凭证照片" type="file" accept="image/png,image/jpeg,image/webp" className="block w-full mt-2 text-sm" onChange={e => setFile(e.target.files?.[0] || null)} />{file && <span className="block mt-1 break-all text-gray-500">{file.name}</span>}</label>
        </fieldset>
        <div className="px-5 py-4 border-t flex justify-end gap-3 shrink-0"><button type="button" disabled={saving} className="btn-secondary" onClick={() => setShowForm(false)}>取消</button><button type="submit" disabled={saving} className="btn-primary">{saving ? "保存中..." : "保存"}</button></div>
      </form>
    </div>}
    {rejectId !== null && <div role="dialog" aria-modal="true" aria-labelledby="cash-reject-title" className="fixed inset-0 z-[120] bg-black/40 flex items-center justify-center p-3"><form onSubmit={e => { e.preventDefault(); void review(rejectId, true); }} className="bg-white rounded-xl w-full max-w-sm max-h-[90dvh] overflow-y-auto p-5 space-y-4"><h2 id="cash-reject-title" className="font-semibold">驳回垫款单</h2><label className="block text-sm">驳回原因<textarea aria-label="驳回原因" className="form-input mt-1" rows={3} maxLength={500} value={rejectReason} onChange={e => setRejectReason(e.target.value)} /></label><div className="flex justify-end gap-3"><button type="button" disabled={reviewing !== null} className="btn-secondary" onClick={() => setRejectId(null)}>取消</button><button type="submit" disabled={reviewing !== null} className="btn-danger">确认驳回</button></div></form></div>}
  </div>;
}

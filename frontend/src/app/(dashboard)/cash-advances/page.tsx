"use client";
import ActionGate from "@/components/permissions/ActionGate";
import FinancialIdentityBoundary from "@/components/FinancialIdentityBoundary";
import { useEffect, useRef, useState } from "react";
import { api, getActiveWarehouseId, getToken } from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import { useMenuPermission } from "@/hooks/useMenuPermission";
import { useToast } from "@/components/ui/Toast";
import { Plus, Receipt, X } from "lucide-react";
import CashAdvanceRepaymentModal from "@/components/CashAdvanceRepaymentModal";
import CashAdvanceRepaymentHistory from "@/components/CashAdvanceRepaymentHistory";

interface Advance {
  capabilities?: {can_verify?:boolean;can_approve?:boolean;can_repay?:boolean;workflow_stage?:string};
  id: number; payer_id: number | null; payer_name: string; advance_date: string;
  amount: number; currency: string; purpose: string; purpose_label: string; status: string; status_label: string;
  outstanding_amount: number; repaid_amount: number; description: string | null; voucher_path: string | null;
  reject_reason: string | null; created_by_name: string; created_at: string;
  reviewed_by_name: string | null; reviewed_at: string | null;
  payroll_used_amount: number; payroll_available_amount: number;
  reimbursement_used_amount: number; employee_advance_used_amount?: number; available_amount: number;
  linked_documents?: LinkedDocument[]; linked_documents_total?: number; amount_difference_note?: string | null; can_edit?: boolean;
}
interface LinkedDocument { id?: number; document_type: string; document_type_label: string; document_id: number; document_number: string; title: string; document_date: string | null; amount: number; currency: string }
const DOCUMENT_TYPES: Record<string, string> = { payroll: "待发放工资单", payable: "待付款应付账单", reimbursement: "待付款报销", employee_advance: "未结清预支" };
const documentKey = (doc: LinkedDocument) => `${doc.document_type}:${doc.document_id}`;
const documentTotal = (docs: LinkedDocument[]) => docs.reduce((sum, doc) => sum + Math.round(doc.amount * 100), 0) / 100;
interface Payer { id: number; name: string; username: string; role: string }
interface CurrencyAmount { currency: string; amount: number }
interface Summary { payer_count: number; total_outstanding: number | null; totals_by_currency: CurrencyAmount[]; data: { payer_id: number | null; payer_name: string; outstanding_amount: number | null; totals_by_currency: CurrencyAmount[] }[] }
const PURPOSES = { salary: "工资", purchase: "采购", expense: "费用", other: "其他" };
const ROLES: Record<string, string> = { warehouse_admin: "仓库管理员", supervisor: "主管", staff: "财务", warehouse_labor: "劳工" };
const STATUS_STYLES: Record<string, string> = { pending: "bg-yellow-50 text-yellow-700", confirmed: "bg-green-50 text-green-700", rejected: "bg-red-50 text-red-700", repaid: "bg-gray-100 text-gray-600" };
const money = (value: number) => value.toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const currencyName = (currency: string) => currency === "CNY" ? "人民币" : "泰铢";
const currencyAmounts = (amounts: CurrencyAmount[], legacy: number | null) => amounts?.length ? amounts.map(item => `${money(item.amount)} ${currencyName(item.currency)}`).join(" / ") : money(legacy || 0);
const today = () => new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Bangkok", year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());
const newForm = () => ({ payer_id: "", payer_name: "", advance_date: today(), amount: "", currency: "THB", purpose: "", description: "", amount_difference_note: "" });

function CashAdvancesPageContent() {
  const { user } = useAuth() as { user: any };
  const advancePermission = useMenuPermission("cash_advances"), reportPermission = useMenuPermission("reports");
  const [reportView, setReportView] = useState(false), [queryReady, setQueryReady] = useState(false);
  const [reportFilter, setReportFilter] = useState({ payer_id: "", payer_name: "", currency: "" });
  const canView = reportView ? reportPermission : advancePermission;
  const canCreate = queryReady && !reportView && canView && ["warehouse_admin", "supervisor", "staff"].includes(user?.role);
  const canReview = queryReady && !reportView && user?.role === "warehouse_admin";
  const { toast } = useToast();
  const [rows, setRows] = useState<Advance[]>([]);
  const [summary, setSummary] = useState<Summary>({ payer_count: 0, total_outstanding: 0, totals_by_currency: [], data: [] });
  const [total, setTotal] = useState(0), [page, setPage] = useState(1);
  const [filters, setFilters] = useState({ start_date: "", end_date: "", status: "", payer_name: "" });
  const [loading, setLoading] = useState(false), [saving, setSaving] = useState(false);
  const [showForm, setShowForm] = useState(false), [manual, setManual] = useState(false);
  const [form, setForm] = useState(newForm), [file, setFile] = useState<File | null>(null);
  const [payers, setPayers] = useState<Payer[]>([]);
  const [reviewing, setReviewing] = useState<number | null>(null), [rejectId, setRejectId] = useState<number | null>(null);
  const [rejectReason, setRejectReason] = useState("");
  const loadVersion = useRef(0);
  const [repayAdvance, setRepayAdvance] = useState<Advance | null>(null);
  const [historyAdvance, setHistoryAdvance] = useState<Advance | null>(null);
  const [editing, setEditing] = useState<Advance | null>(null);
  const [selectedDocs, setSelectedDocs] = useState<LinkedDocument[]>([]), [docOptions, setDocOptions] = useState<LinkedDocument[]>([]);
  const [docKind, setDocKind] = useState("payroll"), [docSearch, setDocSearch] = useState(""), [docPage, setDocPage] = useState(1);
  const [docTotal, setDocTotal] = useState(0), [docLoading, setDocLoading] = useState(false), [docError, setDocError] = useState("");
  const [documentsAdvance, setDocumentsAdvance] = useState<Advance | null>(null), [documentDetail, setDocumentDetail] = useState<any>(null);
  const [detailLoading, setDetailLoading] = useState(false), [detailError, setDetailError] = useState("");
  const detailVersion = useRef(0);

  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    if (q.get("report_view") === "1") {
      setReportView(true); setReportFilter({ payer_id: q.get("payer_id") || "", payer_name: q.get("payer_name_exact") || "", currency: q.get("currency") || "" });
      setFilters({ start_date: q.get("start_date") || "", end_date: q.get("end_date") || "", status: "", payer_name: "" });
    }
    setQueryReady(true);
  }, []);
  useEffect(() => { if (queryReady && canView) void load(); return () => { loadVersion.current++; }; }, [canView, page, filters, reportView, reportFilter, queryReady]);
  useEffect(() => {
    if (!showForm) return;
    let active = true;
    setDocLoading(true); setDocError(""); setDocOptions([]);
    const params = new URLSearchParams({ document_type: docKind, currency: form.currency, search: docSearch, page: String(docPage), page_size: "50" });
    api.get<{ data: LinkedDocument[]; total: number }>(`/cash-advances/document-options?${params}`).then(result => {
      if (active) { setDocOptions(result.data); setDocTotal(result.total); }
    }).catch((err: any) => { if (active) { setDocError(err.message || "加载关联单据失败"); setDocTotal(0); } })
      .finally(() => { if (active) setDocLoading(false); });
    return () => { active = false; };
  }, [showForm, docKind, form.currency, docSearch, docPage]);
  async function load() {
    const version = ++loadVersion.current;
    setLoading(true);
    try {
      const params = new URLSearchParams({ page: String(page), page_size: "20" });
      Object.entries(filters).forEach(([key, value]) => { if (value.trim()) params.set(key, value.trim()); });
      const [list, totals] = reportView ? await (async () => {
        Object.entries(reportFilter).forEach(([key, value]) => { if (value) params.set(key, value); });
        const rows = await api.get<{ data: Advance[]; total: number }>(`/reports/cost-funds-debt/advances?${params}`);
        return [rows, null] as const;
      })() : await Promise.all([
        api.get<{ data: Advance[]; total: number }>(`/cash-advances?${params}`),
        api.get<Summary>("/cash-advances/summary"),
      ]);
      if (version === loadVersion.current) { setRows(list.data); setTotal(list.total); if (totals) setSummary(totals); }
    } catch (err: any) { if (version === loadVersion.current) toast("error", err.message || "加载垫款单失败"); }
    finally { if (version === loadVersion.current) setLoading(false); }
  }
  function filter(key: string, value: string) { setPage(1); setFilters(current => ({ ...current, [key]: value })); }
  async function openForm(row: Advance | null = null) {
    if (!canCreate) return;
    if (row && !row.can_edit) return;
    setEditing(row); setSelectedDocs(row?.linked_documents || []); setDocKind("payroll"); setDocSearch(""); setDocPage(1);
    setForm(row ? { payer_id: row.payer_id ? String(row.payer_id) : "", payer_name: row.payer_name, advance_date: row.advance_date,
      amount: String(row.amount), currency: row.currency, purpose: row.purpose, description: row.description || "", amount_difference_note: row.amount_difference_note || "" } : newForm());
    setManual(row ? !row.payer_id : false); setFile(null); setPayers([]); setShowForm(true);
    try { const result = await api.get<{ data: Payer[] }>("/cash-advances/payers"); setPayers(result.data); }
    catch (err: any) { toast("error", err.message || "加载垫款账号失败，可填写姓名"); }
  }
  function toggleDocument(doc: LinkedDocument) {
    const next = selectedDocs.some(item => documentKey(item) === documentKey(doc)) ? selectedDocs.filter(item => documentKey(item) !== documentKey(doc)) : [...selectedDocs, doc];
    setSelectedDocs(next);
    if (next.length) setForm(current => ({ ...current, amount: documentTotal(next).toFixed(2) }));
  }
  async function showDocument(row: Advance, doc: LinkedDocument) {
    const version = ++detailVersion.current;
    setDocumentDetail(null); setDetailError(""); setDetailLoading(true);
    try { const data = await api.get(`/cash-advances/${row.id}/documents/${doc.id}`); if (version === detailVersion.current) setDocumentDetail(data); }
    catch (err: any) { if (version === detailVersion.current) setDetailError(err.message || "加载单据失败"); }
    finally { if (version === detailVersion.current) setDetailLoading(false); }
  }
  async function create() {
    if (!canCreate || saving) return;
    if (!form.advance_date) { toast("error", "请选择垫款日期"); return; }
    if (!Number.isFinite(Number(form.amount)) || Number(form.amount) <= 0) { toast("error", "垫款金额必须大于零"); return; }
    if (!form.purpose) { toast("error", "请选择用途"); return; }
    if (manual && !form.payer_name.trim()) { toast("error", "请填写垫款人姓名"); return; }
    if (selectedDocs.length && Math.round(Number(form.amount) * 100) !== Math.round(documentTotal(selectedDocs) * 100) && !form.amount_difference_note.trim()) {
      toast("error", "垫款金额与关联单据合计不一致，请填写差额备注"); return;
    }
    setSaving(true);
    try {
      let voucher_path: string | null = editing?.voucher_path || null;
      if (file) {
        const body = new FormData(); body.append("file", file);
        const headers: Record<string, string> = { Authorization: `Bearer ${getToken()}` };
        const warehouse = getActiveWarehouseId(); if (warehouse) headers["X-Warehouse-ID"] = warehouse;
        const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "/api/v1"}/cash-advances/voucher`, { method: "POST", headers, body });
        const result = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(result.detail || "凭证上传失败");
        voucher_path = result.path;
      }
      const body = { advance_date: form.advance_date, amount: form.amount, currency: form.currency, purpose: form.purpose,
        description: form.description.trim() || null, voucher_path,
        payer_id: !manual && form.payer_id ? Number(form.payer_id) : null,
        payer_name: manual ? form.payer_name.trim() : null,
        linked_documents: selectedDocs.map(doc => ({ document_type: doc.document_type, document_id: doc.document_id })),
        amount_difference_note: form.amount_difference_note.trim() || null,
      };
      const result = editing ? await api.put<Advance>(`/cash-advances/${editing.id}`, body) : await api.post<Advance>("/cash-advances", body);
      toast("success", editing ? "垫款单已更新" : result.status === "confirmed" ? "垫款单已登记并确认" : "垫款单已登记，待仓库管理员确认"); setShowForm(false); await load();
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

  async function verify(id: number) {
    try { await api.post(`/cash-advances/${id}/verify`, {}); toast("success", "已核验，等待批准"); void load(); }
    catch (error: unknown) { toast("error", error instanceof Error ? error.message : "核验失败"); }
  }
  if (!canView) return <p className="text-sm text-gray-500">无此操作权限</p>;
  return <div className="space-y-4">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <h1 className="page-title flex items-center gap-2"><Receipt size={24} />{reportView ? "垫款单 · 报表只读明细" : "垫款单"}</h1>
      {canCreate && <ActionGate anyOf={["cash_advance.edit_advance#operate","cash_advance.create_advance#operate"]}><button type="button" onClick={() => void openForm()} className="btn-primary flex items-center gap-1"><Plus size={16} />新建垫款单</button></ActionGate>}
    </div>
    {!reportView && <section className="bg-white rounded-xl border p-4 space-y-2" aria-label="本仓垫款汇总">
      <p>本仓现在欠垫款 <strong>{summary.payer_count}</strong> 人，共 <strong className="text-red-600">{currencyAmounts(summary.totals_by_currency, summary.total_outstanding)}</strong></p>
      <p className="text-xs text-gray-500">汇总为本仓全部已确认、尚未归还的垫款，不随下方筛选变化。</p>
      {summary.data.length > 0 && <div className="divide-y text-sm">{summary.data.map((payer, index) => <div key={`${payer.payer_id}-${index}`} className="flex justify-between gap-3 py-2"><span>{payer.payer_name}</span><span>{currencyAmounts(payer.totals_by_currency, payer.outstanding_amount)}</span></div>)}</div>}
    </section>}
    <div className="flex flex-wrap gap-2 items-center">
      <input aria-label="开始日期" type="date" className="form-input w-auto" value={filters.start_date} onChange={e => filter("start_date", e.target.value)} />
      <span className="text-gray-400">至</span><input aria-label="结束日期" type="date" className="form-input w-auto" value={filters.end_date} onChange={e => filter("end_date", e.target.value)} />
      {!reportView && <><select aria-label="状态筛选" className="form-input w-auto" value={filters.status} onChange={e => filter("status", e.target.value)}><option value="">全部状态</option><option value="pending">待确认</option><option value="confirmed">已确认</option><option value="partially_repaid">部分归还</option><option value="rejected">已驳回</option><option value="repaid">已归还</option></select>
      <input aria-label="垫款人筛选" placeholder="按垫款人姓名筛选" className="form-input w-auto" maxLength={100} value={filters.payer_name} onChange={e => filter("payer_name", e.target.value)} /></>}
    </div>
    <div className="bg-white rounded-xl border overflow-x-auto">
      <table className="w-full text-sm whitespace-nowrap"><thead className="bg-gray-50 text-gray-500"><tr>{["日期", "垫款人", "金额", "用途", "状态", "剩余未还", "资金使用", "关联单据", "说明 / 凭证", "操作"].map(title => <th key={title} className="text-left px-4 py-3">{title}</th>)}</tr></thead>
        <tbody className="divide-y">{rows.map(row => <tr key={row.id} className="cursor-pointer hover:bg-gray-50" onClick={() => { if (!reportView) setHistoryAdvance(row); }}>
          <td className="px-4 py-3">{row.advance_date}</td><td className="px-4 py-3">{row.payer_name}</td><td className="px-4 py-3">{money(row.amount)} {currencyName(row.currency)}</td><td className="px-4 py-3">{row.purpose_label}</td>
          <td className="px-4 py-3"><span className={`rounded px-2 py-1 text-xs ${STATUS_STYLES[row.status]}`}>{row.capabilities?.workflow_stage || row.status_label}</span>{row.reject_reason && <p className="whitespace-normal max-w-48 text-xs text-red-600 mt-2">{row.reject_reason}</p>}</td>
          <td className="px-4 py-3">{money(row.outstanding_amount)} {currencyName(row.currency)}</td>
          <td className="px-4 py-3"><p>工资 {money(row.payroll_used_amount || 0)} · 报销 {money(row.reimbursement_used_amount || 0)} {currencyName(row.currency)}</p>{!!row.employee_advance_used_amount && <p>用于员工预支 {money(row.employee_advance_used_amount)} {currencyName(row.currency)}</p>}<p className="text-xs text-gray-500 mt-1">可用 {money(row.available_amount || 0)}</p></td>
          <td className="px-4 py-3">{!reportView && !!row.linked_documents?.length ? <button type="button" className="text-blue-600" onClick={event => { event.stopPropagation(); detailVersion.current++; setDocumentDetail(null); setDetailError(""); setDetailLoading(false); setDocumentsAdvance(row); }}>查看 {row.linked_documents.length} 张单据</button> : "—"}</td>
          <td className="px-4 py-3"><p className="whitespace-normal max-w-56">{row.description || "—"}</p>{row.amount_difference_note && <p className="whitespace-normal max-w-56 text-xs text-gray-500">差额备注：{row.amount_difference_note}</p>}{row.voucher_path && <a href={`/${row.voucher_path}`} onClick={event => event.stopPropagation()} target="_blank" rel="noreferrer" className="text-blue-600">查看凭证</a>}</td>
          <td className="px-4 py-3" onClick={event => event.stopPropagation()}><div className="flex gap-3">
            {canCreate && row.can_edit && <ActionGate anyOf={["cash_advance.edit_advance#operate","cash_advance.create_advance#operate"]}><button type="button" className="text-blue-600" onClick={() => void openForm(row)}>编辑</button></ActionGate>}
            {!reportView && ["staff","warehouse_admin"].includes(user?.role) && row.capabilities?.can_verify && <ActionGate anyOf={["cash_advance.verify_advance#operate"]}><button onClick={() => verify(row.id)} className="text-blue-600">核验</button></ActionGate>}
            {canReview && row.capabilities?.can_approve && <><button type="button" disabled={reviewing !== null} onClick={() => review(row.id)} className="text-green-700 disabled:opacity-50">确认</button><button type="button" disabled={reviewing !== null} onClick={() => { setRejectReason(""); setRejectId(row.id); }} className="text-red-600 disabled:opacity-50">驳回</button></>}
            {!reportView && ["staff","warehouse_admin"].includes(user?.role) && row.capabilities?.can_repay && row.outstanding_amount > 0 && <ActionGate anyOf={["cash_advance.repay_advance"]}><button type="button" onClick={() => setRepayAdvance(row)} className="text-blue-600">归还</button></ActionGate>}
            <button type="button" onClick={() => setHistoryAdvance(row)} className="text-gray-600" disabled={reportView}>{reportView ? "只读" : "归还记录"}</button>
          </div></td>
        </tr>)}{!rows.length && <tr><td colSpan={10} className="text-center text-gray-400 py-10">{loading ? "加载中..." : "暂无垫款单"}</td></tr>}</tbody>
      </table>
    </div>
    <div className="flex items-center justify-between gap-3 text-sm"><span>共 {total} 条，第 {page} 页</span><div className="flex gap-2"><button type="button" className="btn-secondary" disabled={page === 1 || loading} onClick={() => setPage(page - 1)}>上一页</button><button type="button" className="btn-secondary" disabled={page * 20 >= total || loading} onClick={() => setPage(page + 1)}>下一页</button></div></div>
    {showForm && <div role="dialog" aria-modal="true" aria-labelledby="cash-advance-title" className="fixed inset-0 z-[110] bg-black/40 flex items-center justify-center p-3">
      <form onSubmit={e => { e.preventDefault(); void create(); }} className="bg-white rounded-2xl w-full max-w-lg max-h-[90dvh] flex flex-col overflow-hidden">
        <div className="flex justify-between items-center px-5 py-4 border-b shrink-0"><h2 id="cash-advance-title" className="font-semibold">{editing ? "编辑垫款单" : "新建垫款单"}</h2><button type="button" aria-label="关闭" disabled={saving} onClick={() => setShowForm(false)}><X size={20} /></button></div>
        <div className="p-5 overflow-y-auto min-h-0 min-w-0"><fieldset disabled={saving} className="space-y-4 min-w-0">
          <div><span className="text-sm">垫款人</span><div className="flex gap-4 text-sm my-2"><label><input type="radio" checked={!manual} onChange={() => setManual(false)} /> 选择账号</label><label><input type="radio" checked={manual} onChange={() => setManual(true)} /> 手填姓名</label></div>
            {manual ? <input aria-label="垫款人姓名" className="form-input" maxLength={100} value={form.payer_name} onChange={e => setForm({ ...form, payer_name: e.target.value })} /> : <select aria-label="垫款账号" className="form-input" value={form.payer_id} onChange={e => setForm({ ...form, payer_id: e.target.value })}><option value="">本人（{user?.display_name}）</option>{payers.map(p => <option key={p.id} value={p.id}>{p.name}（{p.username} / {ROLES[p.role] || p.role}）</option>)}</select>}
          </div>
          <label className="block text-sm">日期<input required type="date" className="form-input mt-1" value={form.advance_date} onChange={e => setForm({ ...form, advance_date: e.target.value })} /></label>
          <label className="block text-sm">币种<select aria-label="垫款币种" className="form-input mt-1" value={form.currency} onChange={e => { setForm({ ...form, currency: e.target.value }); setSelectedDocs([]); setDocPage(1); }}><option value="THB">泰铢</option><option value="CNY">人民币</option></select></label>
          <section aria-label="关联单据" className="rounded-lg border p-3 space-y-3 text-sm">
            <p className="font-medium">关联单据（可多选，也可不选）</p>
            <select aria-label="关联单据类型" className="form-input" value={docKind} onChange={e => { setDocKind(e.target.value); setDocPage(1); }}>{Object.entries(DOCUMENT_TYPES).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select>
            <input aria-label="搜索关联单据" className="form-input" placeholder="姓名、供应商、账单号或编号" maxLength={100} value={docSearch} onChange={e => { setDocSearch(e.target.value); setDocPage(1); }} />
            <div className="max-h-48 overflow-y-auto space-y-2" aria-label="待付单据选项">
              {docLoading ? <p className="text-gray-500">加载中...</p> : docError ? <p className="text-red-600">{docError}</p> : !docOptions.length ? <p className="text-gray-500">暂无本仓同币种的待付单据，可直接手写说明</p> : docOptions.map(doc => <label key={documentKey(doc)} className="flex gap-2 items-start rounded border p-2 cursor-pointer">
                <input aria-label={`关联 ${doc.document_number}`} type="checkbox" className="mt-1 shrink-0" checked={selectedDocs.some(item => documentKey(item) === documentKey(doc))} onChange={() => toggleDocument(doc)} />
                <span className="min-w-0 break-words">{doc.document_number} · {doc.title}<span className="block text-gray-500">{doc.document_date} · {money(doc.amount)} {currencyName(doc.currency)}</span></span>
              </label>)}
            </div>
            <div className="flex items-center justify-between gap-2 text-xs"><span>共 {docTotal} 张，第 {docPage} 页</span><div className="flex gap-2"><button type="button" disabled={docLoading || docPage === 1} onClick={() => setDocPage(docPage - 1)}>上一组</button><button type="button" disabled={docLoading || docPage * 50 >= docTotal} onClick={() => setDocPage(docPage + 1)}>下一组</button></div></div>
            {!!selectedDocs.length && <div className="space-y-2 border-t pt-2">{selectedDocs.map(doc => <div key={documentKey(doc)} className="flex justify-between gap-2"><span className="break-words">{doc.document_number} · {money(doc.amount)} {currencyName(doc.currency)}</span><button type="button" className="shrink-0 text-red-600" aria-label={`移除 ${doc.document_number}`} onClick={() => toggleDocument(doc)}>移除</button></div>)}<p>已选 {selectedDocs.length} 张，合计 <strong>{money(documentTotal(selectedDocs))} {currencyName(form.currency)}</strong></p></div>}
            <p className="text-xs text-gray-500">仅登记垫款用途，不自动付款。后续付款仍需手动选择垫款单。</p>
          </section>
          <label className="block text-sm">金额<input required type="number" min="0.01" step="0.01" className="form-input mt-1" value={form.amount} onChange={e => setForm({ ...form, amount: e.target.value })} /></label>
          {!!selectedDocs.length && <label className="block text-sm">差额备注{Math.round(Number(form.amount) * 100) !== Math.round(documentTotal(selectedDocs) * 100) ? "（必填）" : ""}<textarea aria-label="差额备注" className="form-input mt-1" rows={2} maxLength={2000} placeholder="金额与所选单据合计不同时，请说明差额用途" value={form.amount_difference_note} onChange={e => setForm({ ...form, amount_difference_note: e.target.value })} /></label>}
          <label className="block text-sm">用途<select required className="form-input mt-1" value={form.purpose} onChange={e => setForm({ ...form, purpose: e.target.value })}><option value="">请选择用途</option>{Object.entries(PURPOSES).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
          <label className="block text-sm">说明<textarea className="form-input mt-1" rows={3} maxLength={2000} placeholder="没有系统单据时，请写清垫付了什么" value={form.description} onChange={e => setForm({ ...form, description: e.target.value })} /></label>
          <label className="block text-sm">凭证照片<input aria-label="凭证照片" type="file" accept="image/png,image/jpeg,image/webp" className="block w-full mt-2 text-sm" onChange={e => setFile(e.target.files?.[0] || null)} />{file && <span className="block mt-1 break-all text-gray-500">{file.name}</span>}</label>
        </fieldset></div>
        <div className="px-5 py-4 border-t flex justify-end gap-3 shrink-0"><button type="button" disabled={saving} className="btn-secondary" onClick={() => setShowForm(false)}>取消</button><button type="submit" disabled={saving} className="btn-primary">{saving ? "保存中..." : "保存"}</button></div>
      </form>
    </div>}
    {rejectId !== null && <div role="dialog" aria-modal="true" aria-labelledby="cash-reject-title" className="fixed inset-0 z-[120] bg-black/40 flex items-center justify-center p-3"><form onSubmit={e => { e.preventDefault(); void review(rejectId, true); }} className="bg-white rounded-xl w-full max-w-sm max-h-[90dvh] overflow-y-auto p-5 space-y-4"><h2 id="cash-reject-title" className="font-semibold">驳回垫款单</h2><label className="block text-sm">驳回原因<textarea aria-label="驳回原因" className="form-input mt-1" rows={3} maxLength={500} value={rejectReason} onChange={e => setRejectReason(e.target.value)} /></label><div className="flex justify-end gap-3"><button type="button" disabled={reviewing !== null} className="btn-secondary" onClick={() => setRejectId(null)}>取消</button><button type="submit" disabled={reviewing !== null} className="btn-danger">确认驳回</button></div></form></div>}
    {repayAdvance && <CashAdvanceRepaymentModal advance={repayAdvance} onClose={() => setRepayAdvance(null)} onSuccess={() => { void load(); }} />}
    {historyAdvance && <CashAdvanceRepaymentHistory advance={historyAdvance} canRevoke={canReview} onClose={() => setHistoryAdvance(null)} onSuccess={() => { void load(); }} />}
    {documentsAdvance && <div role="dialog" aria-modal="true" aria-labelledby="linked-documents-title" className="fixed inset-0 z-[110] bg-black/40 flex items-center justify-center p-3"><div className="bg-white rounded-xl w-full max-w-lg max-h-[90dvh] flex flex-col overflow-hidden">
      <h2 id="linked-documents-title" className="px-5 py-4 font-semibold border-b shrink-0">垫款单 #{documentsAdvance.id} · 关联单据</h2>
      <div className="p-5 overflow-y-auto min-h-0 space-y-3 text-sm">
        <p>关联合计 {money(documentsAdvance.linked_documents_total || 0)} {currencyName(documentsAdvance.currency)} · 垫款金额 {money(documentsAdvance.amount)} {currencyName(documentsAdvance.currency)}</p>
        {documentsAdvance.amount_difference_note && <p className="break-words">差额备注：{documentsAdvance.amount_difference_note}</p>}
        <p className="text-xs text-gray-500">用途关联不代表该单据已经由此垫款实际付款。</p>
        {documentsAdvance.linked_documents?.map(doc => <button type="button" key={doc.id} className="block w-full text-left border rounded-lg p-3 text-blue-600" onClick={() => void showDocument(documentsAdvance, doc)}><span className="block break-words">{doc.document_number} · {doc.title}</span><span>{money(doc.amount)} {currencyName(doc.currency)} · 查看单据详情</span></button>)}
        {detailLoading && <p>加载单据中...</p>}{detailError && <p className="text-red-600">{detailError}</p>}
        {documentDetail && <section aria-label="关联单据详情" className="bg-gray-50 rounded-lg p-3 space-y-2"><h3 className="font-medium">{documentDetail.snapshot.document_number}</h3><p className="break-words">{documentDetail.snapshot.title}</p><p>关联时金额：{money(documentDetail.snapshot.amount)} {currencyName(documentDetail.snapshot.currency)}</p>
          {documentDetail.current ? <><p>当前金额：{money(documentDetail.current.amount)} {currencyName(documentDetail.current.currency)}</p><p>当前状态：{({ pending: "待审批", confirmed: "已确认", paid: "已付款", partially_paid: "部分付款", overdue: "逾期", voided: "已作废", unpaid: "待结算", partial: "部分结清", deducted: "已随工资结清", approved: "已通过", partially_approved: "部分通过", rejected: "已驳回" } as Record<string, string>)[documentDetail.current.status] || documentDetail.current.status}{documentDetail.current.detail?.disbursed && " · 已发放"}{documentDetail.current.detail?.voided && " · 已作废"}</p></> : <p>原单据已不存在，保留上述关联时快照。</p>}
        </section>}
      </div><div className="border-t px-5 py-4 flex justify-end shrink-0"><button type="button" className="btn-secondary" onClick={() => { detailVersion.current++; setDocumentsAdvance(null); }}>关闭</button></div>
    </div></div>}
  </div>;
}

export default function CashAdvancesPage() { return <FinancialIdentityBoundary><CashAdvancesPageContent /></FinancialIdentityBoundary>; }

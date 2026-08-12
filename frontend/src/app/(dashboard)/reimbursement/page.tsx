"use client";
import { useEffect, useState } from "react";
import { api, getToken } from "@/lib/api";
import { useToast } from "@/components/ui/Toast";
import { useAuth } from "@/hooks/useAuth";
import { useRouter } from "next/navigation";
import {
  Receipt, Plus, PiggyBank, Info, Lock, Search, Download,
  CheckCircle, XCircle, FileText, Camera, Image as ImageIcon, X,
} from "lucide-react";

const CATEGORIES = ["交通费", "餐饮费", "办公用品", "通讯费", "差旅费", "水电费", "维修费", "其他"];
const STATUS_LABELS: Record<string, string> = {
  pending: "待审批", approved: "已通过", partially_approved: "部分通过",
  rejected: "已驳回", paid: "已付款", fund_linked: "转入备用金审核",
};
const STATUS_COLORS: Record<string, string> = {
  pending: "bg-yellow-50 text-yellow-700", approved: "bg-green-50 text-green-700",
  partially_approved: "bg-orange-50 text-orange-700", rejected: "bg-red-50 text-red-700",
  paid: "bg-blue-50 text-blue-700", fund_linked: "bg-purple-50 text-purple-700",
};

export default function ReimbursementPage() {
  const { toast } = useToast(); const { user } = useAuth(); const router = useRouter();
  const isAdmin = user?.role === "warehouse_admin";

  // ===== Tabs =====
  const [tab, setTab] = useState<"list" | "review">("list");

  // ===== List state =====
  const [data, setData] = useState<any[]>([]); const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [selMonth, setSelMonth] = useState("");
  const [selStatus, setSelStatus] = useState("");
  const [selEmployee, setSelEmployee] = useState("");
  const [employees, setEmployees] = useState<any[]>([]);
  const [page, setPage] = useState(1);
  const [detail, setDetail] = useState<any>(null);

  // Inline entry
  const [entryDate, setEntryDate] = useState(new Date().toISOString().slice(0, 10));
  const [entryCategory, setEntryCategory] = useState("交通费");
  const [entryAmount, setEntryAmount] = useState("");
  const [entryCurrency, setEntryCurrency] = useState("THB");
  const [entryDesc, setEntryDesc] = useState("");
  const [entryFile, setEntryFile] = useState<File | null>(null);
  const [fundLinked, setFundLinked] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  // ===== Review state =====
  const [reviewData, setReviewData] = useState<any[]>([]); const [reviewTotal, setReviewTotal] = useState(0);
  const [reviewLoading, setReviewLoading] = useState(false);
  const [reviewMonth, setReviewMonth] = useState("");
  const [reviewEmployee, setReviewEmployee] = useState("");
  const [reviewPage, setReviewPage] = useState(1);
  const [expandedReimb, setExpandedReimb] = useState<number | null>(null);
  const [reimbItems, setReimbItems] = useState<Record<number, any[]>>({});
  const [reviewDecisions, setReviewDecisions] = useState<Record<number, string>>({}); // item_id -> "approved"/"rejected"
  const [reviewRemark, setReviewRemark] = useState("");
  const [selectedReimbs, setSelectedReimbs] = useState<Set<number>>(new Set());

  useEffect(() => { if (!getToken()) router.push("/login"); load(); loadEmployees(); }, [page]);
  useEffect(() => { if (tab === "review") { loadReviews(); loadEmployees(); } }, [tab, reviewPage]);

  async function loadEmployees() {
    try {
      const r = await api.get<any>("/expense-fund/accounts");
      const seen = new Set<number>();
      setEmployees((r.data || []).filter((a: any) => { if (seen.has(a.employee_id)) return false; seen.add(a.employee_id); return true; }));
    } catch {}
  }

  // ===== List logic =====
  async function load() {
    setLoading(true);
    try {
      const params = new URLSearchParams({ page: String(page), page_size: "20" });
      if (selMonth) params.set("month", selMonth);
      if (selStatus) params.set("status", selStatus);
      if (selEmployee) params.set("employee_id", selEmployee);
      const r = await api.get<any>(`/reimbursement?${params.toString()}`);
      setData(r.data); setTotal(r.total);
    } catch (err) { console.error(err); }
    setLoading(false);
  }

  async function handleCreate() {
    if (!entryAmount || +entryAmount <= 0) { toast("error", "请输入金额"); return; }
    if (!entryDesc.trim()) { toast("error", "请输入说明"); return; }
    setSubmitting(true);
    try {
      let receiptPath = null;
      if (entryFile) {
        const fd = new FormData(); fd.append("file", entryFile);
        const upRes = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "/api/v1"}/upload`, {
          method: "POST", headers: { "Authorization": `Bearer ${getToken()}` }, body: fd,
        });
        const upData = await upRes.json();
        receiptPath = upData.url || upData.path || null;
      }
      const items = [{ category: entryCategory, amount: +entryAmount, description: entryDesc, receipt: receiptPath }];
      await api.post("/reimbursement", { items, submit_date: entryDate, currency: entryCurrency, is_fund_linked: fundLinked ? "1" : "0" });
      toast("success", fundLinked ? "已转入备用金审核" : "创建成功");
      setEntryAmount(""); setEntryDesc(""); setEntryFile(null); setFundLinked(false);
      load();
    } catch (err: any) { toast("error", err.message || "创建失败"); }
    setSubmitting(false);
  }

  async function viewDetail(id: number) {
    const r = await api.get<any>(`/reimbursement/${id}`);
    setDetail(r);
  }

  // ===== Review logic =====
  async function loadReviews() {
    setReviewLoading(true);
    try {
      const params = new URLSearchParams({ page: String(reviewPage), page_size: "20", status: "pending" });
      if (reviewMonth) params.set("month", reviewMonth);
      if (reviewEmployee) params.set("employee_id", reviewEmployee);
      const r = await api.get<any>(`/reimbursement?${params.toString()}`);
      setReviewData(r.data); setReviewTotal(r.total);
    } catch (err) { console.error(err); }
    setReviewLoading(false);
    setSelectedReimbs(new Set());
  }

  async function loadReimbItems(reimbId: number) {
    if (reimbItems[reimbId]) return;
    try {
      const r = await api.get<any>(`/reimbursement/${reimbId}`);
      setReimbItems(prev => ({ ...prev, [reimbId]: r.items || [] }));
    } catch {}
  }

  function toggleExpandReimb(id: number) {
    if (expandedReimb === id) { setExpandedReimb(null); return; }
    setExpandedReimb(id);
    loadReimbItems(id);
  }

  function setItemDecision(itemId: number, decision: string) {
    setReviewDecisions(prev => ({ ...prev, [itemId]: decision }));
  }

  async function reviewOne(reimbId: number) {
    const items = reimbItems[reimbId] || [];
    if (items.length === 0) { toast("error", "请先展开查看明细"); return; }
    const decisions = items.map((it: any) => ({
      item_id: it.id,
      status: reviewDecisions[it.id] || "rejected",
      remark: "",
    }));
    try {
      await api.post(`/reimbursement/${reimbId}/review`, { items: decisions, overall_remark: reviewRemark });
      toast("success", "审批完成");
      setReviewRemark(""); setReviewDecisions({});
      loadReviews();
    } catch (err: any) { toast("error", err.message || "审批失败"); }
  }

  async function markPaid(reimbId: number) {
    try {
      await api.post(`/reimbursement/${reimbId}/pay`);
      toast("success", "已标记付款");
      load();
    } catch (err: any) { toast("error", err.message || "操作失败"); }
  }

  async function doExport() {
    try {
      const params = new URLSearchParams();
      if (selMonth) params.set("month", selMonth);
      if (selStatus) params.set("status", selStatus);
      if (selEmployee) params.set("employee_id", selEmployee);
      const url = `${process.env.NEXT_PUBLIC_API_URL || "/api/v1"}/reimbursement/export?${params.toString()}`;
      const res = await fetch(url, { headers: { "Authorization": `Bearer ${getToken()}` } });
      const blob = await res.blob();
      const a = document.createElement("a"); a.href = URL.createObjectURL(blob);
      a.download = "报销清单.xlsx"; a.click();
      toast("success", "导出成功");
    } catch { toast("error", "导出失败"); }
  }

  function handleTabReview() {
    setTab("review"); setReviewPage(1); setExpandedReimb(null); setReimbItems({}); setReviewDecisions({}); setReviewRemark("");
  }

  return (
    <>
      {/* Header */}
      <div className="flex items-center gap-3 mb-5">
        <div className="w-9 h-9 rounded-xl bg-blue-100 flex items-center justify-center">
          <Receipt size={20} className="text-blue-600" />
        </div>
        <div className="flex-1">
          <h1 className="page-title">报销管理</h1>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-1 mb-5 bg-white rounded-xl p-1 shadow-sm border border-gray-100 w-fit">
        <button onClick={() => setTab("list")}
          className={`px-4 py-2 rounded-lg text-sm font-medium transition-all flex items-center gap-1.5 ${tab === "list" ? "bg-blue-600 text-white shadow-sm" : "text-gray-500 hover:text-gray-700"}`}>
          <FileText size={15} />列表
        </button>
        {isAdmin && (
          <button onClick={handleTabReview}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-all flex items-center gap-1.5 ${tab === "review" ? "bg-blue-600 text-white shadow-sm" : "text-gray-500 hover:text-gray-700"}`}>
            <CheckCircle size={15} />审批
            {reviewTotal > 0 && (
              <span className={`ml-1 px-1.5 py-0.5 rounded-full text-[11px] font-bold ${tab === "review" ? "bg-blue-500 text-white" : "bg-red-500 text-white"}`}>{reviewTotal}</span>
            )}
          </button>
        )}
      </div>

      {/* ========== LIST TAB ========== */}
      {tab === "list" && (
        <>
          {/* Inline entry form */}
          <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5 mb-5">
            <div className="flex items-end gap-3 flex-wrap">
              <div className="flex-shrink-0">
                <label className="form-label text-xs">日期</label>
                <input type="date" className="form-input text-sm py-1.5 w-32" value={entryDate} onChange={e => setEntryDate(e.target.value)} />
              </div>
              <div className="flex-shrink-0">
                <label className="form-label text-xs">类别</label>
                <select className="form-input text-sm py-1.5 w-28" value={entryCategory} onChange={e => setEntryCategory(e.target.value)}>
                  {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
                </select>
              </div>
              <div className="flex-shrink-0">
                <label className="form-label text-xs">金额</label>
                <input type="number" className="form-input text-sm py-1.5 w-28" placeholder="金额" value={entryAmount}
                  onChange={e => setEntryAmount(e.target.value === "" ? "" : String(+e.target.value))} />
              </div>
              <div className="flex-shrink-0">
                <label className="form-label text-xs">币种</label>
                <select className="form-input text-sm py-1.5 w-24" value={entryCurrency} onChange={e => setEntryCurrency(e.target.value)}>
                  <option value="THB">THB</option><option value="CNY">CNY</option>
                </select>
              </div>
              <div className="flex-1 min-w-[140px]">
                <label className="form-label text-xs">说明</label>
                <input className="form-input text-sm py-1.5" placeholder="费用说明" value={entryDesc} onChange={e => setEntryDesc(e.target.value)} />
              </div>
              <div className="flex-shrink-0">
                <label className="form-label text-xs">截图</label>
                <div className="border-2 border-dashed border-gray-200 rounded-lg px-2 py-1.5 text-center hover:border-blue-400 transition-colors cursor-pointer w-20" onClick={() => document.getElementById("reimbFile")?.click()}>
                  {entryFile ? <span className="text-xs text-blue-600 truncate block">{entryFile.name.slice(0, 8)}</span>
                   : <Camera size={14} className="mx-auto text-gray-300" />}
                  <input id="reimbFile" type="file" accept="image/*" className="hidden" onChange={e => setEntryFile(e.target.files?.[0] || null)} />
                </div>
              </div>
              <div>
                <button onClick={handleCreate} disabled={submitting} className="btn-primary text-sm py-1.5 flex items-center gap-1">
                  {submitting ? <span className="animate-spin w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full" /> : <Plus size={14} />}
                  提交
                </button>
              </div>
            </div>
            {/* Fund-linked checkbox */}
            <div className="mt-3 pt-3 border-t border-gray-100">
              <label className="flex items-center gap-2 cursor-pointer">
                <input type="checkbox" checked={fundLinked} onChange={e => setFundLinked(e.target.checked)} className="w-3.5 h-3.5 rounded border-gray-300 text-blue-600" />
                <span className="text-xs font-medium text-gray-600 flex items-center gap-1"><PiggyBank size={13} className="text-purple-600" />关联备用金扣款</span>
              </label>
              {fundLinked && (
                <p className="text-[11px] text-gray-400 mt-1 ml-5 flex items-start gap-1">
                  <Info size={11} className="mt-0.5 flex-shrink-0" />
                  勾选后将从备用金账户直接扣款，报销单自动转入备用金审核，提交后不可再修改
                </p>
              )}
            </div>
          </div>

          {/* Filters */}
          <div className="flex items-center gap-3 mb-4 flex-wrap">
            <div className="flex items-center gap-1.5">
              <label className="text-xs text-gray-500">月份</label>
              <input type="month" className="form-input text-sm py-1.5 w-36" value={selMonth} onChange={e => setSelMonth(e.target.value)} />
            </div>
            <div className="flex items-center gap-1.5">
              <label className="text-xs text-gray-500">状态</label>
              <select className="form-input text-sm py-1.5 w-32" value={selStatus} onChange={e => setSelStatus(e.target.value)}>
                <option value="">全部</option>
                {Object.entries(STATUS_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
            </div>
            <div className="flex items-center gap-1.5">
              <label className="text-xs text-gray-500">报销人</label>
              <select className="form-input text-sm py-1.5 w-32" value={selEmployee} onChange={e => setSelEmployee(e.target.value)}>
                <option value="">全部</option>
                {employees.map((e: any) => <option key={e.employee_id} value={e.employee_id}>{e.employee_name}</option>)}
              </select>
            </div>
            <button onClick={() => { setPage(1); load(); }} className="btn-primary text-sm py-1.5 flex items-center gap-1"><Search size={14} />查询</button>
            <button onClick={doExport} className="btn-secondary text-sm py-1.5 flex items-center gap-1 ml-auto"><Download size={14} />导出</button>
          </div>

          {/* Table */}
          <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
            {loading ? (
              <div className="flex items-center justify-center h-40 text-gray-400"><div className="animate-spin w-5 h-5 border-2 border-blue-600 border-t-transparent rounded-full mr-2" />加载中...</div>
            ) : data.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16 text-gray-400">
                <Receipt size={44} className="text-gray-200 mb-3" /><span className="text-sm">暂无报销记录</span>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b bg-gray-50">
                      <th className="text-left px-4 py-3 font-medium text-gray-500">报销人</th>
                      <th className="text-left px-4 py-3 font-medium text-gray-500">日期</th>
                      <th className="text-right px-4 py-3 font-medium text-gray-500">金额</th>
                      <th className="text-center px-4 py-3 font-medium text-gray-500 w-14">币种</th>
                      <th className="text-center px-4 py-3 font-medium text-gray-500">状态</th>
                      <th className="text-center px-4 py-3 font-medium text-gray-500">操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.map((row: any) => (
                      <tr key={row.id} className="border-b hover:bg-gray-50/50 cursor-pointer" onClick={() => viewDetail(row.id)}>
                        <td className="px-4 py-3 font-medium text-gray-800">{row.employee_name}</td>
                        <td className="px-4 py-3 text-gray-500">{row.submit_date?.slice(0, 10)}</td>
                        <td className="px-4 py-3 text-right font-mono text-sm">
                          {row.currency === "CNY" ? "¥" : "฿"}{row.total_amount?.toLocaleString()}
                        </td>
                        <td className="px-4 py-3 text-center">
                          <span className={`px-1.5 py-0.5 rounded text-xs ${row.currency === "CNY" ? "bg-red-50 text-red-600" : "bg-blue-50 text-blue-600"}`}>{row.currency}</span>
                        </td>
                        <td className="px-4 py-3 text-center">
                          <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_COLORS[row.status] || "bg-gray-50 text-gray-600"}`}>
                            {row.status === "fund_linked" && <Lock size={10} className="inline mr-0.5" />}
                            {STATUS_LABELS[row.status] || row.status}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-center">
                          <div className="flex items-center justify-center gap-1.5" onClick={e => e.stopPropagation()}>
                            <button onClick={() => viewDetail(row.id)} className="px-2 py-1 rounded text-xs bg-blue-50 text-blue-700 hover:bg-blue-100">详情</button>
                            {(row.status === "approved" || row.status === "partially_approved") && isAdmin && (
                              <button onClick={() => { markPaid(row.id); }} className="px-2 py-1 rounded text-xs bg-green-50 text-green-700 hover:bg-green-100">付款</button>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {total > 20 && (
              <div className="flex items-center justify-center gap-3 py-3 border-t">
                <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page <= 1} className="px-3 py-1 text-sm border rounded disabled:opacity-30">上一页</button>
                <span className="text-sm text-gray-500">{page} / {Math.ceil(total / 20)}</span>
                <button onClick={() => setPage(p => p + 1)} disabled={page >= Math.ceil(total / 20)} className="px-3 py-1 text-sm border rounded disabled:opacity-30">下一页</button>
              </div>
            )}
          </div>
        </>
      )}

      {/* ========== REVIEW TAB ========== */}
      {tab === "review" && (
        <>
          {/* Review filters */}
          <div className="flex items-center gap-3 mb-4 flex-wrap">
            <div className="flex items-center gap-1.5">
              <label className="text-xs text-gray-500">月份</label>
              <input type="month" className="form-input text-sm py-1.5 w-36" value={reviewMonth} onChange={e => setReviewMonth(e.target.value)} />
            </div>
            <div className="flex items-center gap-1.5">
              <label className="text-xs text-gray-500">报销人</label>
              <select className="form-input text-sm py-1.5 w-32" value={reviewEmployee} onChange={e => setReviewEmployee(e.target.value)}>
                <option value="">全部</option>
                {employees.map((e: any) => <option key={e.employee_id} value={e.employee_id}>{e.employee_name}</option>)}
              </select>
            </div>
            <button onClick={() => { setReviewPage(1); loadReviews(); }} className="btn-primary text-sm py-1.5 flex items-center gap-1"><Search size={14} />查询</button>
            <span className="text-sm text-gray-400 ml-auto">{reviewTotal} 条待审批</span>
          </div>

          {/* Review list */}
          <div className="space-y-4">
            {reviewLoading ? (
              <div className="flex items-center justify-center h-40 text-gray-400"><div className="animate-spin w-5 h-5 border-2 border-blue-600 border-t-transparent rounded-full mr-2" />加载中...</div>
            ) : reviewData.length === 0 ? (
              <div className="bg-white rounded-2xl shadow-sm border p-16 text-center text-gray-400">
                <FileText size={44} className="text-gray-200 mx-auto mb-3" /><span className="text-sm">暂无待审批报销单</span>
              </div>
            ) : (
              reviewData.map((reimb: any) => {
                const isExpanded = expandedReimb === reimb.id;
                const items = reimbItems[reimb.id] || [];
                return (
                  <div key={reimb.id} className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
                    {/* Header row */}
                    <div className={`flex items-center px-5 py-3 cursor-pointer hover:bg-gray-50/50 transition-colors ${isExpanded ? "bg-blue-50/30" : ""}`} onClick={() => toggleExpandReimb(reimb.id)}>
                      <div className="flex-1 flex items-center gap-4">
                        <span className="font-medium text-gray-800">{reimb.employee_name}</span>
                        <span className="text-sm text-gray-500">{reimb.submit_date?.slice(0, 10)}</span>
                        <span className="text-sm font-mono font-medium">{reimb.currency === "CNY" ? "¥" : "฿"}{reimb.total_amount?.toLocaleString()}</span>
                        <span className="text-xs px-2 py-0.5 bg-gray-100 rounded text-gray-600">{reimb.currency}</span>
                        {reimb.is_fund_linked === "1" && (
                          <span className="text-xs text-purple-600 bg-purple-50 px-2 py-0.5 rounded-full flex items-center gap-1"><Lock size={10} />备用金</span>
                        )}
                      </div>
                      <button onClick={e => { e.stopPropagation(); reviewOne(reimb.id); }}
                        className="btn-primary text-xs bg-green-600 hover:bg-green-700 py-1 px-3 flex items-center gap-1">
                        <CheckCircle size={13} />审批
                      </button>
                    </div>

                    {/* Expanded items */}
                    {isExpanded && (
                      <div className="border-t px-5 py-3 bg-gray-50/30">
                        <table className="w-full text-xs">
                          <thead>
                            <tr className="border-b bg-gray-100/50">
                              <th className="text-left py-1.5 px-2 text-gray-500">类别</th>
                              <th className="text-right py-1.5 px-2 text-gray-500 w-20">金额</th>
                              <th className="text-left py-1.5 px-2 text-gray-500">说明</th>
                              <th className="text-center py-1.5 px-2 text-gray-500 w-16">凭证</th>
                              <th className="text-center py-1.5 px-2 text-gray-500 w-32">审批决定</th>
                            </tr>
                          </thead>
                          <tbody>
                            {items.map((it: any) => (
                              <tr key={it.id} className="border-b border-gray-100">
                                <td className="py-1.5 px-2">{it.category}</td>
                                <td className="py-1.5 px-2 text-right font-mono">{reimb.currency === "CNY" ? "¥" : "฿"}{it.amount?.toLocaleString()}</td>
                                <td className="py-1.5 px-2 text-gray-500">{it.description}</td>
                                <td className="py-1.5 px-2 text-center">
                                  {it.receipt ? (
                                    <a href={it.receipt} target="_blank" className="text-blue-500 hover:text-blue-700 inline-flex"><ImageIcon size={14} /></a>
                                  ) : <span className="text-gray-300">-</span>}
                                </td>
                                <td className="py-1.5 px-2 text-center">
                                  <div className="flex items-center justify-center gap-1.5">
                                    <button onClick={() => setItemDecision(it.id, "approved")}
                                      className={`px-2 py-0.5 rounded text-[11px] border transition-colors ${reviewDecisions[it.id] === "approved" ? "bg-green-100 border-green-300 text-green-700" : "border-gray-200 text-gray-400 hover:border-green-300"}`}>通过</button>
                                    <button onClick={() => setItemDecision(it.id, "rejected")}
                                      className={`px-2 py-0.5 rounded text-[11px] border transition-colors ${reviewDecisions[it.id] === "rejected" ? "bg-red-100 border-red-300 text-red-700" : "border-gray-200 text-gray-400 hover:border-red-300"}`}>驳回</button>
                                  </div>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                        <div className="mt-2 flex items-center gap-2">
                          <input className="form-input text-xs py-1 flex-1" placeholder="审批备注" value={reviewRemark} onChange={e => setReviewRemark(e.target.value)} />
                        </div>
                      </div>
                    )}
                  </div>
                );
              })
            )}
            {reviewTotal > 20 && (
              <div className="flex items-center justify-center gap-3 py-3">
                <button onClick={() => setReviewPage(p => Math.max(1, p - 1))} disabled={reviewPage <= 1} className="px-3 py-1 text-sm border rounded disabled:opacity-30">上一页</button>
                <span className="text-sm text-gray-500">{reviewPage} / {Math.ceil(reviewTotal / 20)}</span>
                <button onClick={() => setReviewPage(p => p + 1)} disabled={reviewPage >= Math.ceil(reviewTotal / 20)} className="px-3 py-1 text-sm border rounded disabled:opacity-30">下一页</button>
              </div>
            )}
          </div>
        </>
      )}

      {/* ===== 详情弹窗 ===== */}
      {detail && (
        <div className="modal-overlay z-50" onClick={() => setDetail(null)}>
          <div className="bg-white rounded-2xl p-6 w-[560px] max-h-[80vh] overflow-auto shadow-2xl" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-semibold text-lg flex items-center gap-2">
                报销详情
                {detail.is_fund_linked === "1" && (
                  <span className="px-2 py-0.5 rounded-full text-xs bg-purple-50 text-purple-700 font-normal flex items-center gap-1"><Lock size={11} />关联备用金</span>
                )}
                <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_COLORS[detail.status] || ""}`}>
                  {STATUS_LABELS[detail.status] || detail.status}
                </span>
              </h2>
              <button onClick={() => setDetail(null)} className="text-gray-400 hover:text-gray-600"><X size={18} /></button>
            </div>
            <div className="text-sm text-gray-500 mb-3">
              <div>报销人: {detail.employee_name} | 日期: {detail.submit_date?.slice(0, 10)}</div>
              <div>总额: {detail.currency === "CNY" ? "¥" : "฿"}{detail.total_amount?.toLocaleString()} | 币种: {detail.currency}</div>
              {detail.is_fund_linked === "1" && (
                <div className="text-purple-600 text-xs flex items-center gap-1 mt-1"><Info size={12} />此报销已关联备用金扣款</div>
              )}
            </div>
            <table className="w-full text-sm">
              <thead><tr className="border-b bg-gray-50"><th className="text-left py-2 px-2 text-gray-500">类别</th><th className="text-right py-2 px-2 text-gray-500">金额</th><th className="text-left py-2 px-2 text-gray-500">说明</th><th className="text-center py-2 px-2 text-gray-500">凭证</th><th className="text-center py-2 px-2 text-gray-500">审核</th></tr></thead>
              <tbody>{detail.items?.map((i: any) => (
                <tr key={i.id} className="border-b">
                  <td className="py-2 px-2">{i.category}</td>
                  <td className="py-2 px-2 text-right font-mono">{detail.currency === "CNY" ? "¥" : "฿"}{i.amount?.toLocaleString()}</td>
                  <td className="py-2 px-2 text-gray-500">{i.description}</td>
                  <td className="py-2 px-2 text-center">{i.receipt ? <a href={i.receipt} target="_blank"><ImageIcon size={14} className="text-blue-500 mx-auto" /></a> : <span className="text-gray-300">-</span>}</td>
                  <td className="py-2 px-2 text-center">
                    <span className={`text-xs ${i.review_status === "approved" ? "text-green-600" : i.review_status === "rejected" ? "text-red-600" : "text-yellow-600"}`}>
                      {i.review_status === "approved" ? "已通过" : i.review_status === "rejected" ? "已驳回" : "待审核"}
                    </span>
                  </td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        </div>
      )}
    </>
  );
}

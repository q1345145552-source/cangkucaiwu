"use client";
import { useMenuPermission } from "@/hooks/useMenuPermission";
import { useEffect, useState } from "react";
import { api, getToken } from "@/lib/api";
import { useToast } from "@/components/ui/Toast";
import { useAuth } from "@/hooks/useAuth";
import { useRouter } from "next/navigation";
import { DollarSign, Plus, Ban } from "lucide-react";

function todayStr(): string {
  const n = new Date();
  return `${n.getFullYear()}-${String(n.getMonth() + 1).padStart(2, "0")}-${String(n.getDate()).padStart(2, "0")}`;
}

const SOURCE_LABELS: Record<string, string> = { supervisor: "主管垫付", fund: "备用金" };
const STATUS_LABELS: Record<string, string> = { unpaid: "待结算", partial: "部分结清", deducted: "已随工资结清", voided: "已作废" };

export default function EmployeeAdvancePage() {
  const canWrite = useMenuPermission("employee_advances");
  const { toast } = useToast(); const { user } = useAuth() as { user: any }; const router = useRouter();
  const [rows, setRows] = useState<any[]>([]);
  const [summary, setSummary] = useState<any>({ total_by_currency: [], debtor_count: 0 });
  const [employees, setEmployees] = useState<any[]>([]);
  const [recipients, setRecipients] = useState<any[]>([]);
  const [recipient, setRecipient] = useState("");
  const [fundAccounts, setFundAccounts] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ employee_id: 0, amount: "", advance_date: todayStr(), source: "supervisor", fund_account_id: 0, remark: "" });
  const [filterEmp, setFilterEmp] = useState(0);
  const [filterPeriod, setFilterPeriod] = useState("");

  const [approvalStatus, setApprovalStatus] = useState("");
  const [filtersReady, setFiltersReady] = useState(false);
  const [reviewing, setReviewing] = useState<number | null>(null);
  const [rejectId, setRejectId] = useState<number | null>(null);
  const [rejectReason, setRejectReason] = useState("");
  const [voidId, setVoidId] = useState<number | null>(null);
  const [voidReason, setVoidReason] = useState("");
  const [voiding, setVoiding] = useState(false);
  useEffect(() => {
    if (!getToken()) { router.push("/login"); return; }
    const status = new URLSearchParams(window.location.search).get("approval_status") || "";
    setApprovalStatus(["pending", "approved", "rejected"].includes(status) ? status : "");
    setFiltersReady(true); loadRefs();
  }, []);
  useEffect(() => { if (filtersReady) load(); }, [filtersReady, filterEmp, filterPeriod, approvalStatus]);

  async function review(id: number, reject = false) {
    if (reject && !rejectReason.trim()) { toast("error", "请填写驳回原因"); return; }
    setReviewing(id);
    try {
      await api.post(`/employee-advances/${id}/${reject ? "reject" : "approve"}`, reject ? { reject_reason: rejectReason.trim() } : {});
      toast("success", reject ? "已驳回" : "已通过");
      setRejectId(null); setRejectReason(""); await load();
    } catch (err: any) { toast("error", err.message || "审批失败"); }
    finally { setReviewing(null); }
  }

  async function load() {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (approvalStatus) params.set("approval_status", approvalStatus);
      if (filterEmp) params.set("employee_id", String(filterEmp));
      if (filterPeriod) params.set("period", filterPeriod);
      const [r, s] = await Promise.all([
        api.get<any>(`/employee-advances?${params.toString()}`),
        api.get<any>("/employee-advances/summary"),
      ]);
      setRows(r.data || []);
      setSummary(s);
    } catch (err: any) { toast("error", err.message || "加载预支记录失败"); }
    setLoading(false);
  }

  async function loadRefs() {
    try {
      const rr = await api.get<any>("/employee-advances/recipients");
      setRecipients(rr.data || []);
      const er = await api.get<any>("/employees?page_size=200&active_only=true");
      setEmployees(er.data || []);
      const fr = await api.get<any>("/expense-fund/accounts");
      setFundAccounts(fr.data || []);
    } catch {}
  }

  async function handleCreate() {
    if (!recipient) { toast("error", "请选择员工"); return; }
    const amt = parseFloat(form.amount);
    if (!amt || amt <= 0) { toast("error", "请填写预支金额"); return; }
    if (form.source === "fund" && !form.fund_account_id) { toast("error", "请选择备用金账户"); return; }
    try {
      const [kind, id] = recipient.split(":");
      const result = await api.post<{ message?: string }>("/employee-advances", { ...form, amount: amt,
        employee_id: kind === "employee" ? Number(id) : undefined,
        user_id: kind === "user" ? Number(id) : undefined,
      });
      toast("success", result.message || "预支记录已创建");
      setShowForm(false);
      setRecipient("");
      loadRefs();
      setForm({ employee_id: 0, amount: "", advance_date: todayStr(), source: "supervisor", fund_account_id: 0, remark: "" });
      load();
    } catch (err: any) { toast("error", err.message || "创建失败"); }
  }

  async function handleVoid() {
    if (voidId === null) return;
    if (!voidReason.trim()) { toast("error", "请填写作废原因"); return; }
    setVoiding(true);
    try {
      await api.delete(`/employee-advances/${voidId}`, { void_reason: voidReason.trim() });
      toast("success", "预支已作废");
      setVoidId(null); setVoidReason("");
      await load();
    } catch (err: any) { toast("error", err.message || "作废失败"); }
    finally { setVoiding(false); }
  }

  const fmtPeriod = (period: string, half: string) => `${period} ${half === "second_half" ? "下半月" : "上半月"}`;

  return (
    <div>
      <div className="flex justify-between mb-4 flex-wrap gap-2 items-center">
        <h1 className="page-title flex items-center gap-2"><DollarSign size={24}/>员工预支</h1>
        {canWrite && (<button onClick={() => setShowForm(true)} className="btn-primary flex items-center gap-1 text-sm px-4 py-2">
          <Plus size={16}/> 记预支
        </button>)}
      </div>

      {/* 欠款汇总 */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
        {(summary.total_by_currency || []).length > 0 ? summary.total_by_currency.map((c: any) => (
          <div key={c.currency} className="bg-white rounded-xl border p-4">
            <p className="text-xs text-gray-400">已预支 ({c.currency})</p>
            <p className="text-2xl font-bold text-red-600">{c.total?.toLocaleString()}</p>
          </div>
        )) : (
          <div className="bg-white rounded-xl border p-4">
            <p className="text-xs text-gray-400">已预支</p>
            <p className="text-2xl font-bold text-red-600">0</p>
          </div>
        )}
        <div className="bg-white rounded-xl border p-4">
          <p className="text-xs text-gray-400">预支人数</p>
          <p className="text-2xl font-bold text-gray-800">{summary.debtor_count ?? 0}</p>
        </div>
      </div>

      {/* 筛选 */}
      <div className="flex gap-2 items-center mb-3 flex-wrap">
        <select aria-label="审批状态" value={approvalStatus} onChange={e => setApprovalStatus(e.target.value)} className="border rounded-lg px-3 py-2 text-sm bg-white">
          <option value="">全部审批状态</option><option value="pending">待审批</option><option value="approved">已通过</option><option value="rejected">已驳回</option>
        </select>
        <select value={filterEmp || ""} onChange={e => setFilterEmp(+e.target.value)}
          className="border rounded-lg px-3 py-2 text-sm bg-white min-w-[160px]">
          <option value="">全部员工</option>
          {employees.map((e: any) => <option key={e.id} value={e.id}>{e.name}</option>)}
        </select>
        <input type="month" value={filterPeriod} onChange={e => setFilterPeriod(e.target.value)}
          className="border rounded-lg px-3 py-2 text-sm bg-white" />
        {(filterEmp || filterPeriod || approvalStatus) && (
          <button onClick={() => { setFilterEmp(0); setFilterPeriod(""); setApprovalStatus(""); }}
            className="text-sm text-gray-500 hover:text-gray-700">重置</button>
        )}
      </div>

      {/* 列表 */}
      {loading ? (
        <div className="text-center py-12 text-gray-400">加载中...</div>
      ) : rows.length === 0 ? (
        <div className="text-center py-12 text-gray-400 bg-white rounded-xl border">
          <DollarSign size={40} className="mx-auto mb-3 text-gray-300"/>
          <p>暂无预支记录</p>
        </div>
      ) : (
        <div className="bg-white rounded-xl border overflow-x-auto">
          <table className="w-full text-sm min-w-[1000px]">
            <thead>
              <tr className="border-b bg-gray-50">
                <th className="text-left px-3 py-3 font-medium text-gray-500">员工</th>
                <th className="text-right px-3 py-3 font-medium text-gray-500">预支金额</th>
                <th className="text-left px-3 py-3 font-medium text-gray-500">预支日期</th>
                <th className="text-left px-3 py-3 font-medium text-gray-500">所属周期</th>
                <th className="text-right px-3 py-3 font-medium text-gray-500">已结清金额</th>
                <th className="text-right px-3 py-3 font-medium text-gray-500">已预支</th>
                <th className="text-center px-3 py-3 font-medium text-gray-500">状态</th>
                <th className="text-center px-3 py-3 font-medium text-gray-500">来源</th>
                <th className="px-3 py-3">审批状态</th>
                <th className="text-left px-3 py-3 font-medium text-gray-500">操作人</th>
                <th className="text-left px-3 py-3 font-medium text-gray-500">备注</th>
                <th className="text-center px-3 py-3 font-medium text-gray-500">操作</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r: any) => (
                <tr key={r.id} className={`border-b border-gray-50 hover:bg-gray-50 ${r.is_voided || r.status === "voided" ? "text-gray-400 opacity-60" : ""}`}>
                  <td className="px-3 py-3 font-medium">{r.employee_name}{r.employee_status === "resigned" && <span className="ml-1 text-xs text-red-500">已离职</span>}</td>
                  <td className="px-3 py-3 text-right font-bold">{r.amount?.toLocaleString()} {r.currency}</td>
                  <td className="px-3 py-3">{r.advance_date}</td>
                  <td className="px-3 py-3">{fmtPeriod(r.period, r.half)}</td>
                  <td className="px-3 py-3 text-right">{r.deducted_amount?.toLocaleString()}</td>
                  <td className="px-3 py-3 text-right text-red-600">{r.remaining_amount?.toLocaleString()}</td>
                  <td className="px-3 py-3 text-center">
                    <span title={r.is_voided ? `作废人：${r.voided_by_name || r.voided_by || "-"}；时间：${r.voided_at || "-"}；原因：${r.void_reason || "-"}` : undefined} className={`px-2 py-0.5 rounded text-xs font-medium ${
                      r.is_voided || r.status === "voided" ? "bg-gray-100 text-gray-500" : r.status === "deducted" ? "bg-green-50 text-green-700" : r.status === "partial" ? "bg-amber-50 text-amber-700" : "bg-gray-100 text-gray-600"
                    }`}>
                      {r.is_voided ? "已作废" : STATUS_LABELS[r.status] || r.status}
                    </span>
                  </td>
                  <td className="px-3 py-3 text-center">{SOURCE_LABELS[r.source] || r.source}</td>
                  <td className="px-3 py-3 text-center whitespace-nowrap">{r.approval_status_label || r.approval_status}</td>
                  <td className="px-3 py-3">{r.operator_name || "-"}</td>
                  <td className="px-3 py-3 text-gray-500 max-w-32 truncate" title={r.remark}>{r.remark || "-"}</td>
                  <td className="px-3 py-3 text-center">
                    {user?.role === "warehouse_admin" && !r.is_voided && r.status !== "voided" && r.approval_status === "pending" && <div className="flex gap-2 mb-2 whitespace-nowrap">
                      <button disabled={reviewing !== null} onClick={() => review(r.id)} className="text-green-700 disabled:opacity-50">通过</button>
                      <button disabled={reviewing !== null} onClick={() => { setRejectId(r.id); setRejectReason(""); }} className="text-red-600">驳回</button>
                    </div>}
                    {user?.role === "warehouse_admin" && !r.is_voided && r.status !== "voided" && (<button
                      disabled={r.can_void === false || r.status === "deducted" || r.status === "partial" || (r.deducted_amount || 0) > 0}
                      onClick={() => { setVoidId(r.id); setVoidReason(""); }}
                      className="inline-flex items-center gap-1 text-red-400 hover:text-red-600 disabled:text-gray-300 disabled:cursor-not-allowed"
                      title={r.status === "deducted" ? "该预支已随工资结清 不能作废" : (r.deducted_amount || 0) > 0 || r.status === "partial" ? "该预支已随工资抵扣 不能作废" : "作废"}>
                      <Ban size={16}/>作废
                    </button>)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {voidId !== null && <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50 p-4">
        <div role="dialog" aria-label="作废预支" className="bg-white rounded-xl p-5 w-full max-w-md max-h-[85vh] overflow-y-auto space-y-4">
          <h2 className="font-semibold">确认作废预支</h2>
          <p className="text-sm text-red-600">作废后当作没预支过 关联的支出也会删除</p>
          <label className="block text-sm">作废原因 <span className="text-red-500">*</span>
            <textarea aria-label="作废原因" required maxLength={500} value={voidReason} onChange={e => setVoidReason(e.target.value)} className="form-input w-full mt-2" placeholder="请填写作废原因"/>
          </label>
          <div className="flex justify-end gap-3"><button disabled={voiding} onClick={() => setVoidId(null)}>取消</button><button disabled={voiding} className="btn-primary" onClick={handleVoid}>{voiding ? "作废中…" : "确认作废"}</button></div>
        </div>
      </div>}
      {rejectId !== null && <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50 p-4">
        <div role="dialog" aria-label="驳回预支" className="bg-white rounded-xl p-5 w-full max-w-md max-h-[85vh] overflow-y-auto space-y-4">
          <h2 className="font-semibold">驳回预支</h2>
          <textarea aria-label="驳回原因" placeholder="请填写驳回原因" maxLength={500} value={rejectReason} onChange={e => setRejectReason(e.target.value)} className="form-input w-full"/>
          <div className="flex justify-end gap-3"><button disabled={reviewing !== null} onClick={() => setRejectId(null)}>取消</button><button disabled={reviewing !== null} className="btn-primary" onClick={() => review(rejectId, true)}>确认驳回</button></div>
        </div>
      </div>}
      {/* 记预支弹窗 */}
      {canWrite && showForm && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50 p-4" onClick={() => setShowForm(false)}>
          <div className="bg-white rounded-2xl w-full max-w-md shadow-xl max-h-[85vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
            <div className="bg-blue-500 text-white px-5 py-3 rounded-t-2xl flex items-center gap-2">
              <DollarSign size={20} /><span className="font-semibold">记预支</span>
            </div>
            <div className="p-5 space-y-4">
              <div>
                <label className="form-label text-sm font-medium text-gray-600 mb-1 block">员工</label>
                <select className="form-input py-2.5 w-full" aria-label="预支对象" value={recipient} onChange={e => setRecipient(e.target.value)}>
                  <option value="">请选择员工</option>
                  {recipients.map((r: any) => <option key={r.value} value={r.value}>{r.name}（{r.role_label}）</option>)}
                </select>
              </div>
              <div>
                <label className="form-label text-sm font-medium text-gray-600 mb-1 block">金额</label>
                <input type="number" step="0.01" className="form-input py-2.5 w-full" value={form.amount} onChange={e => setForm({ ...form, amount: e.target.value })} />
              </div>
              <div>
                <label className="form-label text-sm font-medium text-gray-600 mb-1 block">预支日期</label>
                <input type="date" className="form-input py-2.5 w-full" value={form.advance_date} onChange={e => setForm({ ...form, advance_date: e.target.value })} />
              </div>
              <div>
                <label className="form-label text-sm font-medium text-gray-600 mb-1 block">来源</label>
                <select className="form-input py-2.5 w-full" value={form.source} onChange={e => setForm({ ...form, source: e.target.value })}>
                  <option value="supervisor">主管垫付</option>
                  <option value="fund">备用金</option>
                </select>
              </div>
              {form.source === "fund" && (
                <div>
                  <label className="form-label text-sm font-medium text-gray-600 mb-1 block">备用金账户</label>
                  <select className="form-input py-2.5 w-full" value={form.fund_account_id || ""} onChange={e => setForm({ ...form, fund_account_id: +e.target.value })}>
                    <option value="">请选择账户</option>
                    {fundAccounts.map((f: any) => <option key={f.id} value={f.id}>{f.employee_name || `账户${f.id}`} ({f.currency || "THB"})</option>)}
                  </select>
                </div>
              )}
              <div>
                <label className="form-label text-sm font-medium text-gray-600 mb-1 block">备注</label>
                <input className="form-input py-2.5 w-full" value={form.remark} onChange={e => setForm({ ...form, remark: e.target.value })} placeholder="可选" />
              </div>
            </div>
            <div className="border-t px-5 py-4 bg-gray-50 rounded-b-2xl flex justify-end gap-3">
              <button onClick={() => setShowForm(false)} className="btn-secondary text-sm px-6 py-2">取消</button>
              <button onClick={handleCreate} className="btn-primary text-sm px-6 py-2">提交</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

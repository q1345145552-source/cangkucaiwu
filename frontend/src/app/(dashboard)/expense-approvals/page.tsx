"use client";
import { useEffect, useState, useRef } from "react";
import { api, getToken } from "@/lib/api";
import { useToast } from "@/components/ui/Toast";
import { useAuth } from "@/hooks/useAuth";
import { useRouter } from "next/navigation";
import { Receipt, Plus, Settings, Edit2, XCircle, CheckCircle, Banknote, Trash2 } from "lucide-react";

const STATUS_LABELS: Record<string, string> = {
  pending: "待审批", approved: "已批准", paid: "已付款", rejected: "已驳回", completed: "已完成",
};
const STATUS_COLORS: Record<string, string> = {
  pending: "bg-amber-50 text-amber-700",
  approved: "bg-blue-50 text-blue-700",
  paid: "bg-green-50 text-green-700",
  rejected: "bg-red-50 text-red-700",
  completed: "bg-gray-100 text-gray-600",
};
const PAYMENT_LABELS: Record<string, string> = {
  alipay: "支付宝", wechat: "微信", bank_transfer: "银行转账", company_account: "公户", cash: "现金",
};
const FUND_LABELS: Record<string, string> = { fund: "备用金", company: "公司账户" };

function todayStr(): string {
  const n = new Date();
  return `${n.getFullYear()}-${String(n.getMonth() + 1).padStart(2, "0")}-${String(n.getDate()).padStart(2, "0")}`;
}

export default function ExpenseApprovalsPage() {
  const { toast } = useToast(); const { user } = useAuth(); const router = useRouter();
  const [rows, setRows] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [filterStatus, setFilterStatus] = useState("all");
  const [threshold, setThreshold] = useState(0);
  const [showThreshold, setShowThreshold] = useState(false);
  const [thresholdInput, setThresholdInput] = useState("0");
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState({
    amount: "", currency: "THB", purpose: "", expense_date: todayStr(),
    payment_method: "cash", fund_source: "company",
  });
  const [voucherFile, setVoucherFile] = useState<File | null>(null);
  const [rejectId, setRejectId] = useState<number | null>(null);
  const [rejectNote, setRejectNote] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  const role = user?.role;
  const canSubmit = role === "warehouse_admin" || role === "supervisor" || role === "staff";
  const canApprove = role === "warehouse_admin";
  const canSetThreshold = role === "warehouse_admin";

  useEffect(() => { if (!getToken()) { router.push("/login"); return; } load(); loadThreshold(); }, []);
  useEffect(() => { load(); }, [filterStatus]);

  async function load() {
    setLoading(true);
    try {
      const params = filterStatus !== "all" ? `?status=${filterStatus}` : "";
      const r = await api.get<any>(`/expense-approvals${params}`);
      setRows(r.data || []);
    } catch (err: any) { toast("error", err.message || "加载失败"); }
    setLoading(false);
  }

  async function loadThreshold() {
    try {
      const r = await api.get<any>("/expense-approvals/threshold");
      setThreshold(r.threshold ?? 0);
      setThresholdInput(String(r.threshold ?? 0));
    } catch {}
  }

  async function saveThreshold() {
    const v = parseFloat(thresholdInput);
    if (isNaN(v) || v < 0) { toast("error", "门槛不能为负数"); return; }
    try {
      await api.put("/expense-approvals/threshold", { threshold: v });
      setThreshold(v);
      setShowThreshold(false);
      toast("success", `审批门槛已设为 ${v}`);
    } catch (err: any) { toast("error", err.message || "保存失败"); }
  }

  function openCreate() {
    setEditingId(null);
    setForm({ amount: "", currency: "THB", purpose: "", expense_date: todayStr(), payment_method: "cash", fund_source: "company" });
    setVoucherFile(null);
    setShowForm(true);
  }

  function openEdit(r: any) {
    setEditingId(r.id);
    setForm({
      amount: String(r.amount ?? ""), currency: r.currency || "THB", purpose: r.purpose || "",
      expense_date: r.expense_date || todayStr(), payment_method: r.payment_method || "cash", fund_source: r.fund_source || "company",
    });
    setVoucherFile(null);
    setShowForm(true);
  }

  async function handleSubmit() {
    const amt = parseFloat(form.amount);
    if (!amt || amt <= 0) { toast("error", "请填写金额"); return; }
    if (!form.purpose.trim()) { toast("error", "请填写用途说明"); return; }
    try {
      let voucher_base64: string | undefined;
      if (voucherFile) {
        voucher_base64 = await new Promise<string>((resolve, reject) => {
          const reader = new FileReader();
          reader.onload = () => resolve(String(reader.result));
          reader.onerror = reject;
          reader.readAsDataURL(voucherFile);
        });
      }
      if (editingId) {
        const r = await api.put<any>(`/expense-approvals/${editingId}`, { ...form, amount: amt, voucher_base64 });
        toast("success", r.message || "已重新提交");
      } else {
        const r = await api.post<any>("/expense-approvals", { ...form, amount: amt, voucher_base64 });
        toast("success", r.status === "completed" ? "费用已直接生效" : "已提交，等待审批");
      }
      setShowForm(false);
      load();
    } catch (err: any) { toast("error", err.message || "提交失败"); }
  }

  async function approve(id: number) {
    try { await api.post(`/expense-approvals/${id}/approve`, {}); toast("success", "已批准"); load(); }
    catch (err: any) { toast("error", err.message || "操作失败"); }
  }

  async function reject(id: number) {
    try { await api.post(`/expense-approvals/${id}/reject`, { note: rejectNote }); toast("success", "已驳回"); setRejectId(null); setRejectNote(""); load(); }
    catch (err: any) { toast("error", err.message || "操作失败"); }
  }

  async function pay(id: number) {
    try { await api.post(`/expense-approvals/${id}/pay`, {}); toast("success", "已付款"); load(); }
    catch (err: any) { toast("error", err.message || "操作失败"); }
  }

  return (
    <div>
      <div className="flex justify-between mb-4 flex-wrap gap-2 items-center">
        <h1 className="page-title flex items-center gap-2"><Receipt size={24}/>费用审批</h1>
        <div className="flex gap-2 items-center">
          {canSetThreshold && (
            <div className="flex items-center gap-1 text-sm text-gray-500 bg-gray-100 rounded-lg px-3 py-1.5">
              <span>审批门槛: {threshold}</span>
              <button onClick={() => { setShowThreshold(!showThreshold); }} className="p-1 hover:bg-gray-200 rounded"><Settings size={14}/></button>
            </div>
          )}
          {showThreshold && canSetThreshold && (
            <div className="flex items-center gap-2 bg-white border rounded-lg px-3 py-1.5 shadow-sm">
              <input type="number" min="0" value={thresholdInput} onChange={e => setThresholdInput(e.target.value)} className="w-20 border rounded px-2 py-0.5 text-sm" />
              <button onClick={saveThreshold} className="text-xs bg-blue-500 text-white px-2 py-0.5 rounded">保存</button>
            </div>
          )}
          {canSubmit && (
            <button onClick={openCreate} className="btn-primary flex items-center gap-1 text-sm px-4 py-2">
              <Plus size={16}/> 提申请
            </button>
          )}
        </div>
      </div>

      {/* 状态筛选 */}
      <div className="flex gap-2 mb-3 flex-wrap">
        {[["all", "全部"], ["pending", "待审批"], ["approved", "已批准"], ["paid", "已付款"], ["rejected", "已驳回"], ["completed", "已完成"]].map(([k, label]) => (
          <button key={k} onClick={() => setFilterStatus(k)}
            className={`px-3 py-1.5 rounded-lg text-sm ${filterStatus === k ? "bg-blue-500 text-white" : "bg-white text-gray-600 border"}`}>
            {label}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="text-center py-12 text-gray-400">加载中...</div>
      ) : rows.length === 0 ? (
        <div className="text-center py-12 text-gray-400 bg-white rounded-xl border">
          <Receipt size={40} className="mx-auto mb-3 text-gray-300"/>
          <p>暂无费用申请</p>
        </div>
      ) : (
        <div className="bg-white rounded-xl border overflow-x-auto">
          <table className="w-full text-sm min-w-[860px]">
            <thead>
              <tr className="border-b bg-gray-50">
                <th className="text-left px-3 py-3 font-medium text-gray-500">申请人</th>
                <th className="text-right px-3 py-3 font-medium text-gray-500">金额</th>
                <th className="text-left px-3 py-3 font-medium text-gray-500">用途</th>
                <th className="text-left px-3 py-3 font-medium text-gray-500">日期</th>
                <th className="text-center px-3 py-3 font-medium text-gray-500">状态</th>
                <th className="text-left px-3 py-3 font-medium text-gray-500">审批人</th>
                <th className="text-center px-3 py-3 font-medium text-gray-500">操作</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r: any) => (
                <tr key={r.id} className="border-b border-gray-50 hover:bg-gray-50">
                  <td className="px-3 py-3 font-medium">{r.applicant_name}</td>
                  <td className="px-3 py-3 text-right font-bold">{r.amount?.toLocaleString()} {r.currency}</td>
                  <td className="px-3 py-3 text-gray-500 max-w-48 truncate" title={r.purpose}>{r.purpose}</td>
                  <td className="px-3 py-3">{r.expense_date}</td>
                  <td className="px-3 py-3 text-center">
                    <span className={`px-2 py-0.5 rounded text-xs font-medium ${STATUS_COLORS[r.status] || "bg-gray-100 text-gray-600"}`}>
                      {STATUS_LABELS[r.status] || r.status}
                    </span>
                  </td>
                  <td className="px-3 py-3">{r.approver_name || "-"}</td>
                  <td className="px-3 py-3 text-center">
                    <div className="flex items-center justify-center gap-2">
                      {(r.status === "pending" || r.status === "rejected") && (r.applicant_id === (user as any)?.id || canApprove) && (
                        <button onClick={() => openEdit(r)} className="text-blue-500 hover:text-blue-700" title="修改"><Edit2 size={15}/></button>
                      )}
                      {r.status === "pending" && canApprove && (
                        <>
                          <button onClick={() => approve(r.id)} className="text-green-600 hover:text-green-800" title="批准"><CheckCircle size={15}/></button>
                          <button onClick={() => { setRejectId(r.id); setRejectNote(""); }} className="text-red-500 hover:text-red-700" title="驳回"><XCircle size={15}/></button>
                        </>
                      )}
                      {r.status === "approved" && canApprove && (
                        <button onClick={() => pay(r.id)} className="text-green-600 hover:text-green-800" title="付款"><Banknote size={15}/></button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* 提申请/修改弹窗 */}
      {showForm && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50 p-4" onClick={() => setShowForm(false)}>
          <div className="bg-white rounded-2xl w-full max-w-md shadow-xl max-h-[90vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
            <div className="bg-blue-500 text-white px-5 py-3 rounded-t-2xl flex items-center gap-2">
              <Receipt size={20} /><span className="font-semibold">{editingId ? "修改费用申请" : "提费用申请"}</span>
            </div>
            <div className="p-5 space-y-4">
              <div>
                <label className="form-label text-sm font-medium text-gray-600 mb-1 block">金额 <span className="text-red-400">*</span></label>
                <input type="number" step="0.01" className="form-input py-2.5 w-full" value={form.amount} onChange={e => setForm({ ...form, amount: e.target.value })} />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="form-label text-sm font-medium text-gray-600 mb-1 block">币种</label>
                  <select className="form-input py-2.5 w-full" value={form.currency} onChange={e => setForm({ ...form, currency: e.target.value })}>
                    <option value="THB">泰铢 THB</option>
                    <option value="CNY">人民币 CNY</option>
                    <option value="USD">美元 USD</option>
                  </select>
                </div>
                <div>
                  <label className="form-label text-sm font-medium text-gray-600 mb-1 block">费用日期</label>
                  <input type="date" className="form-input py-2.5 w-full" value={form.expense_date} onChange={e => setForm({ ...form, expense_date: e.target.value })} />
                </div>
              </div>
              <div>
                <label className="form-label text-sm font-medium text-gray-600 mb-1 block">用途说明 <span className="text-red-400">*</span></label>
                <input className="form-input py-2.5 w-full" value={form.purpose} onChange={e => setForm({ ...form, purpose: e.target.value })} placeholder="如：购买耗材" />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="form-label text-sm font-medium text-gray-600 mb-1 block">付款方式</label>
                  <select className="form-input py-2.5 w-full" value={form.payment_method} onChange={e => setForm({ ...form, payment_method: e.target.value })}>
                    {Object.entries(PAYMENT_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                  </select>
                </div>
                <div>
                  <label className="form-label text-sm font-medium text-gray-600 mb-1 block">资金来源</label>
                  <select className="form-input py-2.5 w-full" value={form.fund_source} onChange={e => setForm({ ...form, fund_source: e.target.value })}>
                    {Object.entries(FUND_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                  </select>
                </div>
              </div>
              <div>
                <label className="form-label text-sm font-medium text-gray-600 mb-1 block">凭证照片</label>
                <div className="flex items-center gap-2">
                  <button onClick={() => fileRef.current?.click()} className="border border-dashed rounded-lg px-4 py-2 text-sm text-gray-400 hover:text-blue-500 hover:border-blue-300">
                    选择图片
                  </button>
                  {voucherFile && <span className="text-xs text-green-600">{voucherFile.name}</span>}
                </div>
                <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={e => setVoucherFile(e.target.files?.[0] || null)} />
              </div>
            </div>
            <div className="border-t px-5 py-4 bg-gray-50 rounded-b-2xl flex justify-end gap-3">
              <button onClick={() => setShowForm(false)} className="btn-secondary text-sm px-6 py-2">取消</button>
              <button onClick={handleSubmit} className="btn-primary text-sm px-6 py-2">提交</button>
            </div>
          </div>
        </div>
      )}

      {/* 驳回弹窗 */}
      {rejectId && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50 p-4" onClick={() => setRejectId(null)}>
          <div className="bg-white rounded-2xl w-full max-w-sm shadow-xl" onClick={e => e.stopPropagation()}>
            <div className="bg-red-500 text-white px-5 py-3 rounded-t-2xl flex items-center gap-2">
              <XCircle size={20} /><span className="font-semibold">驳回费用申请</span>
            </div>
            <div className="p-5 space-y-4">
              <div>
                <label className="form-label text-sm font-medium text-gray-600 mb-1 block">审批备注</label>
                <textarea className="form-input py-2.5 w-full" rows={2} value={rejectNote} onChange={e => setRejectNote(e.target.value)} placeholder="驳回原因（可选）" />
              </div>
            </div>
            <div className="border-t px-5 py-4 bg-gray-50 rounded-b-2xl flex justify-end gap-3">
              <button onClick={() => setRejectId(null)} className="btn-secondary text-sm px-6 py-2">取消</button>
              <button onClick={() => reject(rejectId)} className="bg-red-500 text-white text-sm px-6 py-2 rounded-lg">确认驳回</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

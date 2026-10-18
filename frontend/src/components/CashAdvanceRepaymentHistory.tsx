"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useToast } from "@/components/ui/Toast";
import { RepaymentAdvance } from "@/components/CashAdvanceRepaymentModal";
import SafeImage from "@/components/SafeImage";

interface Repayment {
  id: number; repayment_date: string; amount: number; account_name: string; currency: string; payment_method_label: string;
  created_by_name: string; created_at: string; voucher_path: string; description: string | null; status: string;
  revoked_by_name: string | null; revoked_at: string | null; revoke_reason: string | null;
}
interface PayrollUsage {
  payroll_used_amount: number; payroll_available_amount: number;
  data: { payroll_record_id: number; employee_name: string; period: string; settle_start_date: string | null; settle_end_date: string | null; amount: number; currency: string; disbursed_at: string | null }[];
}
interface ReimbursementUsage {
  reimbursement_used_amount: number;
  data: { payment_id: number; reimbursement_id: number; employee_name: string; amount: number; currency: string; paid_at: string; paid_by_name: string }[];
}
const money = (value: number) => value.toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const time = (value: string) => new Date(value).toLocaleString("zh-CN", { timeZone: "Asia/Bangkok", hour12: false });

export default function CashAdvanceRepaymentHistory({ advance, canRevoke, onClose, onSuccess }: { advance: RepaymentAdvance; canRevoke: boolean; onClose: () => void; onSuccess: () => void }) {
  const { toast } = useToast();
  const [rows, setRows] = useState<Repayment[]>([]), [activeCount, setActiveCount] = useState(0);
  const [loading, setLoading] = useState(true), [error, setError] = useState("");
  const [revoking, setRevoking] = useState(false), [target, setTarget] = useState<Repayment | null>(null), [reason, setReason] = useState("");
  const [loan, setLoan] = useState(advance);
  const [payrollUsage, setPayrollUsage] = useState<PayrollUsage | null>(null);
  const [reimbursementUsage, setReimbursementUsage] = useState<ReimbursementUsage | null>(null);
  async function load() {
    setLoading(true); setError("");
    try {
      const result = await api.get<{ data: Repayment[]; advance: RepaymentAdvance; active_count: number; payroll_usage?: PayrollUsage; reimbursement_usage?: ReimbursementUsage }>(`/cash-advances/${advance.id}/repayments`);
      setRows(result.data); setLoan(result.advance); setActiveCount(result.active_count);
      setPayrollUsage(result.payroll_usage || null);
      setReimbursementUsage(result.reimbursement_usage || null);
    } catch (err: any) { setError(err.message || "归还记录加载失败"); }
    finally { setLoading(false); }
  }
  useEffect(() => { void load(); }, [advance.id]);
  async function revoke() {
    if (!canRevoke || !target || revoking) return;
    if (!reason.trim()) { toast("error", "请填写撤销原因"); return; }
    setRevoking(true);
    try {
      await api.post(`/cash-advances/repayments/${target.id}/revoke`, { reason: reason.trim() });
      toast("success", "归还已撤销，账户余额已恢复，流水已冲销");
      setTarget(null); setReason(""); await load(); onSuccess();
    } catch (err: any) { toast("error", err.message || "撤销失败"); }
    finally { setRevoking(false); }
  }
  return <div role="dialog" aria-modal="true" aria-labelledby="repayment-history-title" className="fixed inset-0 z-[110] bg-black/40 flex items-center justify-center p-3">
    <div className="bg-white rounded-2xl w-full max-w-2xl max-h-[90dvh] flex flex-col overflow-hidden">
      <h2 id="repayment-history-title" className="font-semibold px-5 py-4 border-b shrink-0">垫款 #{advance.id} 归还与使用记录</h2>
      <div className="p-5 overflow-y-auto min-h-0 space-y-3">
        <p className="text-sm">{loan.payer_name} · 已还 {money(loan.repaid_amount)} · 剩余 {money(loan.outstanding_amount)} {loan.currency} · 有效归还 {activeCount} 次</p>
        {!loading && !error && payrollUsage && <section className="border rounded-lg p-3 space-y-2 text-sm" aria-label="工资使用记录">
          <h3 className="font-semibold">已用于工资 {money(payrollUsage.payroll_used_amount)} {loan.currency}</h3>
          <p className="text-xs text-gray-500">尚可用于工资 {money(payrollUsage.payroll_available_amount)} {loan.currency}。发工资不代表归还垫款，剩余未还单独计算。</p>
          {!payrollUsage.data.length ? <p className="text-gray-500">暂无工资使用记录</p> : payrollUsage.data.map(row => <div key={row.payroll_record_id} className="border-t pt-2 space-y-1">
            <p>工资单 #{row.payroll_record_id} · {row.employee_name} · {money(row.amount)} {row.currency}</p>
            <p className="text-xs text-gray-500">{row.settle_start_date && row.settle_end_date ? `${row.settle_start_date} 至 ${row.settle_end_date}` : row.period}{row.disbursed_at ? ` · ${time(row.disbursed_at)}` : ""}</p>
          </div>)}
        </section>}
        {!loading && !error && reimbursementUsage && <section className="border rounded-lg p-3 space-y-2 text-sm" aria-label="报销使用记录">
          <h3 className="font-semibold">已用于报销 {money(reimbursementUsage.reimbursement_used_amount)} {loan.currency}</h3>
          <p className="text-xs text-gray-500">工资和报销共用可用额度，使用垫款不减少剩余未还。</p>
          {!reimbursementUsage.data.length ? <p className="text-gray-500">暂无报销使用记录</p> : reimbursementUsage.data.map(row => <div key={row.payment_id} className="border-t pt-2 space-y-1">
            <p>报销单 #{row.reimbursement_id} · {row.employee_name} · {money(row.amount)} {row.currency}</p>
            <p className="text-xs text-gray-500">{row.paid_by_name} · {time(row.paid_at)}</p>
          </div>)}
        </section>}
        {loading ? <p>加载中...</p> : error ? <div><p className="text-red-600">{error}</p><button type="button" onClick={load} className="btn-secondary">重试</button></div> : !rows.length ? <p className="text-gray-500">暂无归还记录</p> : rows.map(row => <article key={row.id} className="border rounded-lg p-3 space-y-2 text-sm">
          <div className="flex flex-wrap items-center justify-between gap-2"><strong>{row.repayment_date} · {money(row.amount)} {row.currency}</strong><span className={row.status === "revoked" ? "text-gray-500" : "text-green-700"}>{row.status === "revoked" ? "已撤销 / 流水已冲销" : "有效"}</span></div>
          <p>账户：{row.account_name} · {row.payment_method_label}</p>
          <p>操作人：{row.created_by_name} · {time(row.created_at)}</p>
          {row.description && <p className="break-words">说明：{row.description}</p>}
          <a href={`/${row.voucher_path}`} target="_blank" rel="noreferrer" className="inline-block text-blue-600"><SafeImage src={`/${row.voucher_path}`} alt="归还凭证照片" className="max-w-full max-h-32 object-contain rounded border mb-1" />查看归还凭证照片</a>
          {row.status === "revoked" && <p className="text-gray-500 break-words">{row.revoked_by_name} 于 {row.revoked_at ? time(row.revoked_at) : "—"} 撤销：{row.revoke_reason}</p>}
          {canRevoke && row.status === "active" && <button type="button" disabled={revoking} onClick={() => { setTarget(row); setReason(""); }} className="block text-red-600">撤销这一笔</button>}
        </article>)}
      </div>
      <div className="px-5 py-4 border-t flex justify-end shrink-0"><button type="button" disabled={revoking} onClick={onClose} className="btn-secondary">关闭</button></div>
    </div>
    {target && <div role="alertdialog" aria-modal="true" aria-labelledby="revoke-repayment-title" className="fixed inset-0 z-[120] bg-black/40 flex items-center justify-center p-3">
      <form onSubmit={event => { event.preventDefault(); void revoke(); }} className="bg-white rounded-xl p-5 w-full max-w-sm max-h-[90dvh] overflow-y-auto space-y-4">
        <h3 id="revoke-repayment-title" className="font-semibold">确认撤销这一笔归还吗？</h3><p className="text-sm">{money(target.amount)} {target.currency} 将退回原账户，流水保留冲销记录。</p>
        <label className="block text-sm">撤销原因<textarea aria-label="撤销归还原因" className="form-input mt-1" rows={3} maxLength={500} value={reason} disabled={revoking} onChange={event => setReason(event.target.value)} /></label>
        <div className="flex justify-end gap-3"><button type="button" disabled={revoking} onClick={() => setTarget(null)} className="btn-secondary">取消</button><button type="submit" disabled={revoking} className="btn-danger">{revoking ? "撤销中..." : "确认撤销"}</button></div>
      </form>
    </div>}
  </div>;
}

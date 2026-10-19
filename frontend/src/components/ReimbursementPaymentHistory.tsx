"use client";
import { FINANCIAL_REVERSALS_ENABLED } from "@/lib/financial-reversals";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import SafeImage from "@/components/SafeImage";
import CashAdvanceLink from "@/components/CashAdvanceLink";
import { useToast } from "@/components/ui/Toast";

interface Payment {
  id: number; amount: number; currency: string; funding_source_label: string; account_name: string | null;
  cash_advance_id: number | null; cash_advance_number?: string | null; payment_method_label: string; paid_by_name: string; paid_at: string;
  expense_record_id: number | null;
  payment_voucher_path: string | null; status: string; can_revoke: boolean;
  revoked_by_name: string | null; revoked_at: string | null; revoke_reason: string | null;
}
const when = (value: string) => new Date(value).toLocaleString("zh-CN", { timeZone: "Asia/Bangkok", hour12: false });
export default function ReimbursementPaymentHistory({ reimbursementId, onChange }: { reimbursementId: number; onChange: () => void }) {
  const { toast } = useToast();
  const [rows, setRows] = useState<Payment[]>([]), [legacy, setLegacy] = useState(false);
  const [loading, setLoading] = useState(true), [error, setError] = useState("");
  const [target, setTarget] = useState<Payment | null>(null), [reason, setReason] = useState(""), [saving, setSaving] = useState(false);
  async function load() {
    setLoading(true); setError("");
    try {
      const r = await api.get<{ data: Payment[]; is_legacy_payment: boolean }>(`/reimbursement/${reimbursementId}/payments`);
      setRows(r.data); setLegacy(r.is_legacy_payment);
    } catch (err: any) { setError(err.message || "付款记录加载失败"); }
    finally { setLoading(false); }
  }
  useEffect(() => { void load(); }, [reimbursementId]);
  async function revoke() {
    if (!target || saving) return;
    if (!reason.trim()) { toast("error", "请填写撤销原因"); return; }
    setSaving(true);
    try {
      await api.post(`/reimbursement/${reimbursementId}/revoke-payment`, { reason: reason.trim() });
      toast("success", "付款已撤销，成本与资金按原来源恢复");
      setTarget(null); setReason(""); await load(); onChange();
    } catch (err: any) { toast("error", err.message || "撤销付款失败"); }
    finally { setSaving(false); }
  }
  return <section aria-label="付款记录" className="mt-5 border-t pt-4 space-y-3">
    <h3 className="font-semibold text-sm">付款记录</h3>
    {loading ? <p className="text-sm text-gray-500">加载中…</p> : error ? <div><p className="text-sm text-red-600">{error}</p><button onClick={load} className="text-sm text-blue-600">重试</button></div> : !rows.length ? <p className="text-sm text-gray-500">{legacy ? "历史已付款记录保持原样，未自动补成本或推断付款账户。" : "暂无付款记录"}</p> : rows.map(p => <article key={p.id} className="border rounded-lg p-3 space-y-2 text-sm">
      <div className="flex flex-wrap gap-2 justify-between"><strong>{Number(p.amount).toLocaleString("zh-CN", { minimumFractionDigits: 2 })} {p.currency}</strong><span className={p.status === "active" ? "text-green-700" : "text-gray-500"}>{p.status === "active" ? "已付款" : "已撤销"}</span></div>
      <p>资金来源：{p.funding_source_label} <CashAdvanceLink id={p.cash_advance_id} number={p.cash_advance_number} /></p>
      {p.expense_record_id && <p>关联运营支出 #{p.expense_record_id}{p.status === "revoked" ? "（已撤回）" : ""}</p>}
      <p>账户：{p.account_name || "不使用公司账户"} · {p.payment_method_label}</p>
      <p>付款人：{p.paid_by_name} · {when(p.paid_at)}</p>
      {p.payment_voucher_path && <a href={`/${p.payment_voucher_path}`} target="_blank" rel="noreferrer" className="inline-block text-blue-600"><SafeImage src={`/${p.payment_voucher_path}`} alt="付款凭证" className="max-w-full max-h-32 object-contain rounded border mb-1" />查看付款凭证</a>}
      {p.status === "revoked" && <p className="text-gray-500 break-words">{p.revoked_by_name} 于 {p.revoked_at ? when(p.revoked_at) : "—"} 撤销：{p.revoke_reason}</p>}
      {FINANCIAL_REVERSALS_ENABLED && p.can_revoke && <button className="block text-red-600" onClick={() => { setTarget(p); setReason(""); }}>撤销付款</button>}
    </article>)}
    {FINANCIAL_REVERSALS_ENABLED && target && <div role="alertdialog" aria-modal="true" aria-labelledby="reimbursement-revoke-title" className="fixed inset-0 z-[120] bg-black/40 flex items-center justify-center p-3" onClick={e => e.stopPropagation()}>
      <form onSubmit={e => { e.preventDefault(); void revoke(); }} className="bg-white rounded-xl p-5 w-full max-w-sm max-h-[90dvh] overflow-y-auto space-y-4">
        <h3 id="reimbursement-revoke-title" className="font-semibold">确认撤销这笔报销付款吗？</h3>
        <p className="text-sm">成本撤回，公司账户付款恢复余额并保留已冲销流水；垫款或备用金按原来源恢复。</p>
        <label className="block text-sm">撤销原因<textarea aria-label="撤销付款原因" className="form-input mt-1" rows={3} maxLength={500} value={reason} onChange={e => setReason(e.target.value)} disabled={saving} /></label>
        <div className="flex justify-end gap-3"><button type="button" className="btn-secondary" disabled={saving} onClick={() => setTarget(null)}>取消</button><button type="submit" className="btn-primary" disabled={saving}>{saving ? "撤销中…" : "确认撤销"}</button></div>
      </form>
    </div>}
  </section>;
}

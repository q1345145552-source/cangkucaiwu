"use client";
import { useState, useRef } from "react";
import { api, getActiveWarehouseId, getToken } from "@/lib/api";

type Exemption = { id: number; date: string; reason: string; created_by_name: string; created_at: string; status: string; revoke_reason?: string; revoked_by_name?: string };
type Result = { message: string; warning?: string; voided_makeup_count?: number };

export default function AttendanceExemptions({ onChanged }: { onChanged: () => void }) {
  const [open, setOpen] = useState(false);
  const [rows, setRows] = useState<Exemption[]>([]);
  const [date, setDate] = useState("");
  const [reason, setReason] = useState("");
  const [revokeId, setRevokeId] = useState<number | null>(null);
  const [revokeReason, setRevokeReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [warning, setWarning] = useState("");
  const generation = useRef(0);
  const scope = () => `${getToken()}:${getActiveWarehouseId()}`;
  async function load() {
    const expected = scope(), version = ++generation.current;
    try {
      const r = await api.get<{data: Exemption[]}>("/attendance/exemptions");
      if (scope() === expected && version === generation.current) setRows(r.data);
    } catch (err: unknown) { if (scope() === expected) setMessage(err instanceof Error ? err.message : "加载失败"); }
  }
  async function save(revoking: boolean) {
    const expected = scope();
    setBusy(true); setMessage(""); setWarning("");
    try {
      const result = await api.post<Result>(revoking ? `/attendance/exemptions/${revokeId}/revoke` : "/attendance/exemptions", revoking ? {reason: revokeReason} : {date, reason});
      if (scope() !== expected) return;
      setMessage(result.message + (result.voided_makeup_count != null ? `，已作废补卡 ${result.voided_makeup_count} 条` : ""));
      setWarning(result.warning || ""); setReason(""); setRevokeId(null); setRevokeReason("");
      await load(); onChanged();
    } catch (err: unknown) { if (scope() === expected) setMessage(err instanceof Error ? err.message : "操作失败"); }
    finally { setBusy(false); }
  }
  return <>
    <button type="button" className="btn-secondary" onClick={() => { setOpen(true); setMessage(""); setWarning(""); load(); }}>豁免日</button>
    {open && <div className="modal-overlay z-50" data-testid="exemption-overlay">
      <section role="dialog" aria-modal="true" aria-label="仓库豁免日" className="bg-white rounded-xl p-4 w-full max-w-xl max-h-[90vh] overflow-y-auto mx-3">
        <div className="flex justify-between items-center gap-3"><h2 className="font-semibold">仓库豁免日</h2><button type="button" className="btn-secondary" disabled={busy} onClick={() => { generation.current++; setOpen(false); }}>关闭</button></div>
        <p className="text-sm text-gray-500 my-3">当天按八小时满勤，请假照常扣除。设置后补卡自动作废，撤销豁免不会恢复补卡。</p>
        <form onSubmit={e => { e.preventDefault(); save(false); }} className="space-y-3">
          <label className="block text-sm">豁免日期<input aria-label="豁免日期" type="date" required value={date} onChange={e => setDate(e.target.value)} className="form-input mt-1" /></label>
          <label className="block text-sm">设置原因<textarea aria-label="设置原因" required maxLength={500} value={reason} onChange={e => setReason(e.target.value)} className="form-input mt-1" /></label>
          <button className="btn-primary" disabled={busy || !reason.trim()}>{busy ? "处理中…" : "保存豁免"}</button>
        </form>
        {message && <p role="status" className="my-3 text-sm">{message}</p>}
        {warning && <p role="alert" className="my-3 p-3 bg-amber-50 text-amber-800 text-sm">{warning}</p>}
        <div className="space-y-3 mt-4">{rows.map(row => <article key={row.id} className="border rounded-lg p-3 text-sm space-y-2 break-words">
          <p className="font-medium">{row.date} · {row.status === "active" ? "有效" : "已撤销"}</p>
          <p>{row.reason}</p><p className="text-gray-500">{row.created_by_name} · {new Date(row.created_at).toLocaleString()}</p>
          {row.revoke_reason && <p>撤销：{row.revoked_by_name} · {row.revoke_reason}</p>}
          {row.status === "active" && <button className="btn-secondary" disabled={busy} onClick={() => { setRevokeId(row.id); setRevokeReason(""); }}>撤销</button>}
          {revokeId === row.id && <form onSubmit={e => { e.preventDefault(); save(true); }} className="space-y-2">
            <label>撤销原因<textarea aria-label="撤销原因" required maxLength={500} value={revokeReason} onChange={e => setRevokeReason(e.target.value)} className="form-input" /></label>
            <button className="btn-primary" disabled={busy || !revokeReason.trim()}>确认撤销</button>
          </form>}
        </article>)}</div>
      </section>
    </div>}
  </>;
}

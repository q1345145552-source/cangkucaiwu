"use client";
import ActionGate from "@/components/permissions/ActionGate";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useToast } from "@/components/ui/Toast";

interface Batch {
  id: number; date: string; operator_name: string; operated_at: string;
  reason: string; created_count: number; status: string; status_label: string; can_revoke: boolean;
  revoked_by_name?: string; revoked_at?: string;
}

export default function MakeupBatchHistory({ onChange, onBusyChange }: { onChange: () => void; onBusyChange: (busy: boolean) => void }) {
  const { toast } = useToast();
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [range, setRange] = useState({ start_date: "", end_date: "" });
  const [page, setPage] = useState(1);
  const [refresh, setRefresh] = useState(0);
  const [batches, setBatches] = useState<Batch[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [confirmBatch, setConfirmBatch] = useState<Batch | null>(null);
  const [revoking, setRevoking] = useState(false);

  useEffect(() => {
    let active = true;
    setLoading(true); setError("");
    const params = new URLSearchParams({ page: String(page), page_size: "10" });
    if (range.start_date) params.set("start_date", range.start_date);
    if (range.end_date) params.set("end_date", range.end_date);
    api.get<{ data: Batch[]; total: number }>(`/clock-in/makeup-batches?${params}`)
      .then(result => { if (active) { setBatches(result.data); setTotal(result.total); } })
      .catch((err: any) => { if (active) { setBatches([]); setTotal(0); setError(err.message || "历史批次加载失败"); } })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [page, range, refresh]);

  function search() {
    if (startDate && endDate && startDate > endDate) { toast("error", "开始日期不能晚于结束日期"); return; }
    setPage(1); setRange({ start_date: startDate, end_date: endDate });
  }

  async function revoke() {
    if (!confirmBatch || revoking) return;
    setRevoking(true); onBusyChange(true);
    try {
      const result = await api.post<{ deleted_count: number }>(`/clock-in/makeup-batches/${confirmBatch.id}/revoke`, {});
      toast("success", `批次已撤销，删除${result.deleted_count}条补卡记录；已算工资单需人工重算`);
      setConfirmBatch(null); setRefresh(value => value + 1); onChange();
    } catch (err: any) { toast("error", err.message || "撤销失败"); }
    finally { setRevoking(false); onBusyChange(false); }
  }

  function formatTime(value: string) {
    return new Date(value).toLocaleString("zh-CN", { timeZone: "Asia/Bangkok", hour12: false });
  }

  return <section className="border-t pt-4 space-y-3" aria-label="历史批次">
    <h3 className="font-semibold text-sm">历史批次</h3>
    <div className="flex flex-wrap gap-2 items-end">
      <label className="text-xs flex-1 min-w-32">开始日期<input aria-label="批次开始日期" type="date" value={startDate} onChange={event => setStartDate(event.target.value)} className="form-input mt-1" /></label>
      <label className="text-xs flex-1 min-w-32">结束日期<input aria-label="批次结束日期" type="date" value={endDate} onChange={event => setEndDate(event.target.value)} className="form-input mt-1" /></label>
      <button type="button" disabled={loading || revoking} onClick={search} className="btn-secondary">查询历史</button>
    </div>
    {loading ? <p className="text-sm text-gray-500">正在加载历史批次...</p> : error ? <div className="text-sm text-red-600">{error}<button type="button" onClick={() => setRefresh(value => value + 1)} className="ml-2 underline">重试</button></div> : <>
      {!batches.length && <p className="text-sm text-gray-500">暂无历史批次</p>}
      {batches.map(batch => <div key={batch.id} className="border rounded-lg p-3 text-sm space-y-1">
        <div className="flex justify-between gap-2"><strong>批次 #{batch.id} · {batch.date}</strong><span className={batch.status === "revoked" ? "text-gray-500" : "text-green-700"}>{batch.status_label}</span></div>
        <p>操作人：{batch.operator_name} · 新建{batch.created_count}条</p>
        <p className="text-xs text-gray-500">操作时间：{formatTime(batch.operated_at)}</p>
        <p className="break-words">原因：{batch.reason}</p>
        {batch.revoked_at && <p className="text-xs text-gray-500">撤销人：{batch.revoked_by_name || "-"} · {formatTime(batch.revoked_at)}</p>}
        {batch.can_revoke && <ActionGate anyOf={["clock_in.revoke_makeup_batch"]}><button type="button" aria-label={`撤销批次${batch.id}`} disabled={revoking} onClick={() => setConfirmBatch(batch)} className="text-red-600 border border-red-200 rounded px-3 py-1 mt-1">撤销</button></ActionGate>}
      </div>)}
      {total > 10 && <div className="flex gap-3 items-center justify-between text-sm">
        <button type="button" disabled={page === 1 || revoking} onClick={() => setPage(value => value - 1)} className="btn-secondary">上一页</button>
        <span>{page} / {Math.ceil(total / 10)}（共{total}批）</span>
        <button type="button" disabled={page * 10 >= total || revoking} onClick={() => setPage(value => value + 1)} className="btn-secondary">下一页</button>
      </div>}
    </>}
    {confirmBatch && <div className="fixed inset-0 z-[120] bg-black/50 flex items-center justify-center p-3" role="alertdialog" aria-modal="true" aria-labelledby="revoke-makeup-title" data-modal-overlay="true">
      <div className="bg-white w-full max-w-sm rounded-xl p-5 shadow-xl space-y-4">
        <h3 id="revoke-makeup-title" className="font-semibold">确认撤销这一批吗？</h3>
        <p className="text-sm">批次 #{confirmBatch.id}，{confirmBatch.date}，新建{confirmBatch.created_count}条。会影响这一天这些人的考勤。已算工资单不会自动重算。</p>
        <div className="flex justify-end gap-3">
          <button type="button" disabled={revoking} onClick={() => setConfirmBatch(null)} className="btn-secondary" data-modal-close="true">暂不撤销</button>
          <ActionGate anyOf={["clock_in.revoke_makeup_batch#operate"]}><button type="button" disabled={revoking} onClick={revoke} className="btn-danger">{revoking ? "撤销中..." : "确认撤销"}</button></ActionGate>
        </div>
      </div>
    </div>}
  </section>;
}

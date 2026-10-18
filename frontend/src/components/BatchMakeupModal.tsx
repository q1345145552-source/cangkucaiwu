"use client";
import { useState } from "react";
import { api } from "@/lib/api";
import { useToast } from "@/components/ui/Toast";

interface Employee { id: number; name: string }
interface Props {
  employees: Employee[];
  scheduleTimes: Record<number, string>;
  onClose: () => void;
  onSuccess: () => void;
}
const sessions = [[1, "早上上班"], [2, "午休开始"], [3, "午休结束"], [4, "下午下班"]] as const;

export default function BatchMakeupModal({ employees, scheduleTimes, onClose, onSuccess }: Props) {
  const { toast } = useToast();
  const today = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Bangkok", year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());
  const [date, setDate] = useState(today);
  const [selectedEmployees, setSelectedEmployees] = useState<number[]>(employees.map(e => e.id));
  const [selectedSessions, setSelectedSessions] = useState<number[]>([1, 2, 3, 4]);
  const [reason, setReason] = useState("系统故障");
  const [saving, setSaving] = useState(false);
  const toggle = (values: number[], id: number) => values.includes(id) ? values.filter(v => v !== id) : [...values, id];

  async function submit() {
    if (saving) return;
    if (!date || date > today) { toast("error", "请选择今天或以前的日期"); return; }
    if (!selectedEmployees.length) { toast("error", "请选择员工"); return; }
    if (!selectedSessions.length) { toast("error", "请选择打卡时点"); return; }
    if (!reason.trim()) { toast("error", "请填写补卡原因"); return; }
    setSaving(true);
    try {
      const result = await api.post<{ created_count: number; skipped_count: number }>("/clock-in/batch-makeup", {
        date, employee_ids: selectedEmployees, sessions: selectedSessions, reason: reason.trim(),
      });
      toast("success", `批量补卡完成：建了${result.created_count}条，跳过${result.skipped_count}条`);
      onSuccess(); onClose();
    } catch (error: any) { toast("error", error.message || "批量补卡失败"); }
    finally { setSaving(false); }
  }

  return <div className="fixed inset-0 z-[110] bg-black/40 flex items-center justify-center p-3" role="dialog" aria-modal="true" aria-labelledby="batch-makeup-title">
    <div className="bg-white rounded-2xl shadow-xl w-full max-w-xl max-h-[90dvh] flex flex-col overflow-hidden">
      <h2 id="batch-makeup-title" className="text-lg font-semibold px-5 py-4 border-b shrink-0">批量补卡</h2>
      <fieldset disabled={saving} className="p-5 space-y-4 overflow-y-auto min-h-0">
        <label className="block text-sm">日期
          <input aria-label="补卡日期" type="date" max={today} value={date} onChange={e => setDate(e.target.value)} className="form-input mt-1" />
        </label>
        <div>
          <div className="flex items-center justify-between gap-2 mb-2">
            <span className="text-sm font-medium">员工（已选{selectedEmployees.length}人）</span>
            <div className="flex gap-3 text-sm text-blue-600">
              <button type="button" onClick={() => setSelectedEmployees(employees.map(e => e.id))}>员工全选</button>
              <button type="button" onClick={() => setSelectedEmployees([])}>员工全不选</button>
            </div>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 max-h-52 overflow-y-auto border rounded-lg p-3">
            {employees.map(employee => <label key={employee.id} className="flex gap-2 items-center text-sm py-1">
              <input type="checkbox" checked={selectedEmployees.includes(employee.id)} onChange={() => setSelectedEmployees(toggle(selectedEmployees, employee.id))} />{employee.name}
            </label>)}
            {!employees.length && <p className="text-sm text-gray-500">暂无可选员工</p>}
          </div>
        </div>
        <div>
          <div className="flex items-center justify-between gap-2 mb-2">
            <span className="text-sm font-medium">打卡时点</span>
            <div className="flex gap-3 text-sm text-blue-600">
              <button type="button" onClick={() => setSelectedSessions([1, 2, 3, 4])}>时点全选</button>
              <button type="button" onClick={() => setSelectedSessions([])}>时点全不选</button>
            </div>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {sessions.map(([id, label]) => <label key={id} className="flex gap-2 items-center text-sm py-1">
              <input type="checkbox" checked={selectedSessions.includes(id)} onChange={() => setSelectedSessions(toggle(selectedSessions, id))} />
              {label}{scheduleTimes[id] ? `（${scheduleTimes[id]}）` : ""}
            </label>)}
          </div>
        </div>
        <label className="block text-sm">补卡原因（必填）
          <textarea aria-label="补卡原因" value={reason} maxLength={500} onChange={e => setReason(e.target.value)} className="form-input mt-1" rows={2} required />
        </label>
        <p className="text-xs text-gray-500">已有记录会跳过；本次补卡不占个人每月两次额度。</p>
      </fieldset>
      <div className="px-5 py-4 border-t flex justify-end gap-3 shrink-0">
        <button type="button" disabled={saving} onClick={onClose} className="btn-secondary">取消</button>
        <button type="button" disabled={saving || !employees.length} onClick={submit} className="btn-primary">{saving ? "补卡中..." : "确认补卡"}</button>
      </div>
    </div>
  </div>;
}

"use client";
import type { MessageResponse } from "@/lib/api";
import { useEffect, useState } from "react";
import { api, getToken, getActiveWarehouseId } from "@/lib/api";
import { useToast } from "@/components/ui/Toast";
import { useAuth } from "@/hooks/useAuth";
import EmployeeLanguage from "@/components/EmployeeLanguage";
import { useEmployeeView } from "@/hooks/useEmployeeView";
import { useI18n } from "@/hooks/useI18n";
import { useRouter } from "next/navigation";
import { Clock, Plus, CheckCircle, XCircle, AlertTriangle, Upload } from "lucide-react";

export default function OvertimePage() {
  const { employeeView, initialLeave } = useEmployeeView();
  const { toast } = useToast(); const { user } = useAuth() as { user: any }; const { t, locale } = useI18n(employeeView || user?.role === "warehouse_labor"); const router = useRouter();
  const [tasks, setTasks] = useState<any[]>([]);
  const [employees, setEmployees] = useState<any[]>([]);
  const [pendingTasks, setPendingTasks] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [limitHours, setLimitHours] = useState(50);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [scheduleEnd, setScheduleEnd] = useState("18:00");
  const [verifyTask, setVerifyTask] = useState<any>(null);
  const [verifyHours, setVerifyHours] = useState<Record<number, string>>({});
  const [disputeTask, setDisputeTask] = useState<any>(null);
  const [disputeReason, setDisputeReason] = useState("");
  const [disputeFile, setDisputeFile] = useState<File | null>(null);
  const [disputePreview, setDisputePreview] = useState("");
  const [viewPhoto, setViewPhoto] = useState<string | null>(null);

  const isAdmin = !employeeView && user?.role === "warehouse_admin";
  const isLabor = user?.role === "warehouse_labor" || (employeeView && user?.role === "supervisor" && user?.attendance_enabled);
  const canVerify = !employeeView && (user?.role === "warehouse_admin" || user?.role === "supervisor");

  const defaultForm = {
    employee_ids: [] as number[],
    date: new Date().toISOString().slice(0, 10),
    start_time: "18:00",
    end_time: "",
  };
  const [form, setForm] = useState({ ...defaultForm });
  const [empSearch, setEmpSearch] = useState("");

  const [pendingOnly, setPendingOnly] = useState(false);
  const [filtersReady, setFiltersReady] = useState(false);
  useEffect(() => {
    setPendingOnly(new URLSearchParams(window.location.search).get("pending_verification") === "true");
    setFiltersReady(true);
  }, []);
  useEffect(() => { if (!getToken()) router.push("/login"); if (filtersReady) load(); }, [user?.id, employeeView, filtersReady, pendingOnly]);

  async function load() {
    setLoading(true);
    try {
      // Load overtime tasks
      const r = await api.get<any>(`/overtime?page_size=200${employeeView ? "&view=self" : pendingOnly ? "&pending_verification=true" : ""}`);
      const loaded = [...(r.data || [])];
      // Pending reminders are not capped at the first 200 task groups.
      if (!employeeView && pendingOnly) {
        for (let page = 2; loaded.length < r.total; page++) {
          const next = await api.get<any>(`/overtime?page_size=200&page=${page}&pending_verification=true`);
          if (!next.data?.length) break;
          loaded.push(...next.data);
        }
      }
      setTasks(loaded);
      // Load pending tasks for labor
      if (isLabor) {
        const p = await api.get<any>("/overtime/pending");
        setPendingTasks(p.data || []);
      }
      // Load employees for admin
      if (isAdmin) {
        const er = await api.get<any>("/employees?page_size=200&active_only=true");
        setEmployees(er.data || []);
        // 加班默认开始时间 = 排班的下午下班时间
        try {
          const sr = await api.get<any>("/config/work-schedule");
          if (sr.afternoon_end) {
            setScheduleEnd(sr.afternoon_end);
            setForm(f => ({ ...f, start_time: sr.afternoon_end }));
          }
        } catch {}
      }
      // Load limit
      const lr = await api.get<any>(`/overtime/limit${employeeView ? "?view=self" : ""}`);
      setLimitHours(lr.max_hours || 50);
      // Load monthly hours warnings
      if (isAdmin) {
        const month = new Date().toISOString().slice(0, 7);
        const mr = await api.get<any>(`/overtime/monthly-hours?month=${month}`);
        const ws: string[] = [];
        for (const d of (mr.data || [])) {
          if (d.total_hours > limitHours * 0.8) {
            ws.push(t("ot_monthly_warning").replace("{name}", d.employee_name).replace("{h}", String(d.total_hours)).replace("{limit}", String(limitHours)));
          }
        }
        setWarnings(ws);
      }
    } catch {}
    setLoading(false);
  }

  async function handleCreate() {
    if (form.employee_ids.length === 0) { toast("error", t("ot_please_select_employee")); return; }
    if (!form.end_time) { toast("error", t("ot_please_select_end_time")); return; }
    try {
      await api.post("/overtime", form);
      toast("success", t("ot_create_success"));
      setShowForm(false);
      setEmpSearch("");
      setForm({ ...defaultForm, start_time: scheduleEnd, employee_ids: [] });
      load();
    } catch (err: any) { toast("error", err.message || t("ot_create_failed")); }
  }

  async function confirmOvertime(taskId: number) {
    try {
      const r = await api.post<MessageResponse>(`/overtime/${taskId}/confirm`);
      toast("success", r.message || t("ot_confirm_success"));
      load();
    } catch (err: any) { toast("error", err.message || t("ot_confirm_failed")); }
  }

  async function deleteTask(taskId: number) {
    if (!confirm(t("ot_delete_confirm"))) return;
    try {
      await api.delete(`/overtime/${taskId}`);
      toast("success", t("ot_deleted"));
      load();
    } catch (err: any) { toast("error", err.message || t("ot_delete_failed")); }
  }

  function toggleEmployee(id: number) {
    setForm(f => ({
      ...f,
      employee_ids: f.employee_ids.includes(id)
        ? f.employee_ids.filter(eid => eid !== id)
        : [...f.employee_ids, id],
    }));
  }

  function calcMinutes() {
    try {
      const [sh, sm] = form.start_time.split(":").map(Number);
      const [eh, em] = form.end_time.split(":").map(Number);
      const mins = (eh * 60 + em) - (sh * 60 + sm);
      return mins > 0 ? mins : 0;
    } catch { return 0; }
  }
  function calcHours() {
    const m = calcMinutes();
    return (m / 60).toFixed(1);
  }
  function halfHours() {
    const m = calcMinutes();
    return Math.ceil(m / 30);
  }
  // 某员工的加班费 = 半小时数 × 该员工模板的「加班半小时费」
  function empOvertimeFee(e: any) {
    const fee = e.salary_template_overtime_fee != null ? Number(e.salary_template_overtime_fee) : 0;
    return halfHours() * fee;
  }
  // ── 核实加班 ──
  function verifiedCount(task: any) {
    return (task.assignments || []).filter((a: any) => a.actual_hours != null).length;
  }
  function openVerify(task: any) {
    const hours: Record<number, string> = {};
    for (const a of task.assignments || []) {
      hours[a.id] = a.actual_hours != null ? String(a.actual_hours) : String(task.hours ?? "");
    }
    setVerifyHours(hours);
    setVerifyTask(task);
  }
  // 弹框里给老板看的金额：半小时数 = 实际小时数 × 2 向上取整，加班费 = 半小时数 × 加班半小时费
  function verifyFee(a: any) {
    const raw = verifyHours[a.id];
    if (raw == null || raw.trim() === "") return 0;
    const h = Number(raw);
    if (isNaN(h) || h < 0) return 0;
    const half = Math.ceil(h * 2);
    const fee = Number(a.overtime_half_hour_fee ?? 0);
    return half * fee;
  }
  async function handleVerify() {
    if (!verifyTask) return;
    const assignments = (verifyTask.assignments || []).filter((a: any) => !a.confirmed);
    for (const a of assignments) {
      const raw = (verifyHours[a.id] ?? "").trim();
      if (raw === "") { toast("error", t("ot_verify_fill_all")); return; }
      const n = Number(raw);
      if (isNaN(n)) { toast("error", t("ot_verify_fill_all")); return; }
      if (n < 0) { toast("error", t("ot_verify_no_negative")); return; }
    }
    const payload = assignments.map((a: any) => ({ assignment_id: a.id, actual_hours: Number(verifyHours[a.id]) }));
    const hadDispute = assignments.some((a: any) => a.has_dispute);
    try {
      const r = await api.post<{ total_amount?: number }>(`/overtime/${verifyTask.id}/verify`, { assignments: payload });
      let msg = t("ot_verify_success").replace("{amount}", String(r.total_amount ?? 0));
      if (hadDispute) msg += "，" + t("ot_verify_dispute_notified");
      toast("success", msg);
      setVerifyTask(null);
      load();
    } catch (err: any) { toast("error", err.message || t("ot_save_failed")); }
  }
  // ── 提异议 ──
  function openDispute(task: any) {
    setDisputeTask(task);
    setDisputeReason("");
    setDisputeFile(null);
    setDisputePreview("");
  }
  function onDisputeFile(e: any) {
    const f = e.target.files?.[0] || null;
    setDisputeFile(f);
    setDisputePreview(f ? URL.createObjectURL(f) : "");
  }
  async function handleDispute() {
    if (!disputeTask) return;
    if (!disputeReason.trim()) { toast("error", t("ot_dispute_reason_required")); return; }
    if (!disputeFile) { toast("error", t("ot_dispute_photo_required")); return; }
    const fd = new FormData();
    fd.append("reason", disputeReason.trim());
    fd.append("file", disputeFile);
    try {
      const token = getToken();
      const headers: Record<string, string> = { Authorization: `Bearer ${token}` };
      headers["X-Language"] = locale;
      const whId = getActiveWarehouseId();
      if (whId) headers["X-Warehouse-ID"] = whId;
      const res = await fetch(`/api/v1/overtime/${disputeTask.id}/dispute`, { method: "POST", headers, body: fd });
      if (res.ok) {
        const r = await res.json();
        toast("success", r.message || t("ot_dispute_success"));
        setDisputeTask(null);
        setDisputeFile(null);
        setDisputePreview("");
        load();
      } else {
        const err = await res.json().catch(() => ({}));
        toast("error", err.detail || t("ot_dispute_failed"));
      }
    } catch (err: any) { toast("error", err.message || t("ot_dispute_failed")); }
  }

  return (
    <div>
      {isLabor && <EmployeeLanguage />}
      <div className="flex justify-between mb-4 flex-wrap gap-2 items-center">
        <h1 className="page-title flex items-center gap-2"><Clock size={24}/>{t("overtime_title")}</h1>
        <div className="flex gap-2 items-center">
          {isAdmin && (
            <>
              <div className="flex items-center gap-1 text-sm text-gray-500 bg-gray-100 rounded-lg px-3 py-1.5">
                <span>{t("overtime_limit_hint").replace("{h}", String(limitHours))}</span>
              </div>
              <button onClick={() => { setForm(f => ({ ...f, start_time: scheduleEnd || f.start_time })); setShowForm(true); }} className="btn-primary flex items-center gap-1 text-sm px-4 py-2">
                <Plus size={16}/> {t("create_overtime")}
              </button>
            </>
          )}
        </div>
      </div>

      {!isLabor && <label className="flex items-center gap-2 mb-4 text-sm">
        <input type="checkbox" checked={pendingOnly} onChange={e => setPendingOnly(e.target.checked)}/>只看待核实
      </label>}
      {/* Warnings */}
      {warnings.length > 0 && (
        <div className="mb-4 bg-amber-50 border border-amber-200 rounded-xl p-3">
          {warnings.map((w, i) => (
            <div key={i} className="flex items-center gap-2 text-sm text-amber-700">
              <AlertTriangle size={16} className="text-amber-500 shrink-0"/>
              <span>{w}</span>
            </div>
          ))}
        </div>
      )}

      {loading ? (
        <div className="text-center py-12 text-gray-400">{t("loading")}</div>
      ) : (
        <>
          {/* Pending tasks for labor */}
          {isLabor && pendingTasks.length > 0 && (
            <div className="mb-6">
              <h2 className="text-sm font-medium text-orange-600 mb-3 flex items-center gap-1">
                <Clock size={16} /> {t("pending_overtime")} ({pendingTasks.length})
              </h2>
              <div className="grid gap-3">
                {pendingTasks.map((task: any) => {
                  const notVerified = task.needs_verification && task.actual_hours == null;
                  const disputed = task.has_dispute;
                  if (disputed) {
                    return (
                      <div key={task.id} className="bg-orange-50 border border-orange-200 rounded-xl p-4">
                        <p className="font-medium text-orange-700">{task.date} {task.start_time}-{task.end_time} · {t("ot_disputed")}</p>
                        <p className="text-sm text-orange-600 mt-1">{t("ot_dispute_reason_label")}: {task.dispute_reason}</p>
                      </div>
                    );
                  }
                  if (notVerified) {
                    return (
                      <div key={task.id} className="bg-gray-50 border border-gray-200 rounded-xl p-4">
                        <p className="font-medium text-gray-700">{task.date} {task.start_time}-{task.end_time}</p>
                        <p className="text-sm text-gray-500 mt-1">{t("ot_planned")}{task.hours}h · {t("ot_actual")}{t("ot_wait_verify")}</p>
                      </div>
                    );
                  }
                  return (
                    <div key={task.id} className="bg-white border border-gray-200 rounded-xl p-4">
                      <p className="font-medium text-gray-800">{task.date} {task.start_time}-{task.end_time}</p>
                      <p className="text-sm text-gray-500 mt-1">{t("ot_planned")}{task.hours}h{task.actual_hours != null ? <> · {t("ot_actual")}{task.actual_hours}h</> : null} · {t("ot_pay_label")}{task.earned_amount}{t("baht")}</p>
                      <div className="flex gap-2 mt-3">
                        <button onClick={() => confirmOvertime(task.id)}
                          className="bg-green-500 text-white px-4 py-2 rounded-lg text-sm hover:bg-green-600 flex items-center gap-1">
                          <CheckCircle size={16}/> {t("confirm")}
                        </button>
                        <button onClick={() => openDispute(task)}
                          className="bg-orange-500 text-white px-4 py-2 rounded-lg text-sm hover:bg-orange-600 flex items-center gap-1">
                          <AlertTriangle size={16}/> {t("ot_has_dispute")}
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Task list */}
          {tasks.length === 0 ? (
            <div className="text-center py-12 text-gray-400 bg-white rounded-xl border">
              <Clock size={40} className="mx-auto mb-3 text-gray-300"/>
              <p>{t("no_overtime")}</p>
            </div>
          ) : (
            <div className="bg-white rounded-xl border overflow-hidden">
              <div className="overflow-x-auto touch-pan-x">
              <table className="w-full text-sm min-w-[900px]">
                <thead>
                  <tr className="border-b bg-gray-50">
                    <th className="text-left px-4 py-3 font-medium text-gray-500">{t("date")}</th>
                    <th className="text-left px-4 py-3 font-medium text-gray-500">{t("time")}</th>
                    <th className="text-left px-4 py-3 font-medium text-gray-500">{t("hours")}</th>
                    <th className="text-left px-4 py-3 font-medium text-gray-500">{t("ot_pay_per_person")}</th>
                    <th className="text-left px-4 py-3 font-medium text-gray-500">{t("ot_participants")}</th>
                    <th className="text-left px-4 py-3 font-medium text-gray-500">{t("status")}</th>
                    <th className="text-left px-4 py-3 font-medium text-gray-500">{t("operations")}</th>
                  </tr>
                </thead>
                <tbody>
                  {tasks.map((task: any) => (
                    <tr key={task.id} className="border-b border-gray-50 hover:bg-gray-50">
                      <td className="px-4 py-3">{task.date}</td>
                      <td className="px-4 py-3">{task.start_time} - {task.end_time}</td>
                      <td className="px-4 py-3">{task.hours}h</td>
                      <td className="px-4 py-3">{task.total_amount ?? 0} {t("baht")}</td>
                      <td className="px-4 py-3">
                        <div className="space-y-1">
                          {(task.assignments || []).map((a: any) => {
                            const stLabel = a.has_dispute ? t("ot_has_dispute") : a.confirmed ? t("confirmed") : t("pending_confirm");
                            const stColor = a.has_dispute ? "text-orange-600" : a.confirmed ? "text-green-600" : "text-gray-500";
                            return (
                              <div key={a.id} className="text-xs leading-5">
                                <span className="font-medium text-gray-800">{a.employee_name}</span>
                                <span className="text-gray-500"> {t("ot_planned")}{task.hours}h · {t("ot_actual")}{a.actual_hours != null ? `${a.actual_hours}h` : (task.needs_verification ? t("ot_not_verified") : "—")} · {t("ot_amount")}{a.earned_amount?.toFixed(0)}{t("baht")}</span>
                                <span className={`ml-1 ${stColor}`}>{stLabel}</span>
                              </div>
                            );
                          })}
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        {(() => {
                          if (task.status === "completed") {
                            return (
                              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-green-50 text-green-700">
                                <CheckCircle size={12}/> {t("completed_status")}
                              </span>
                            );
                          }
                          const disputeCount = (task.assignments || []).filter((a: any) => a.has_dispute).length;
                          const disputeSuffix = disputeCount > 0 ? (
                            <span className="text-orange-500 font-medium ml-1">{t("ot_status_dispute_suffix").replace("{n}", String(disputeCount))}</span>
                          ) : null;
                          if (task.needs_verification && (task.assignments || []).some((a: any) => a.actual_hours == null)) {
                            return (
                              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-orange-50 text-orange-600">
                                <Clock size={12}/> {t("ot_status_pending_verify")} {t("ot_progress_verified").replace("{n}", String(verifiedCount(task))).replace("{total}", String(task.total_assignments || 0))}{disputeSuffix}
                              </span>
                            );
                          }
                          return (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-blue-50 text-blue-700">
                              <Clock size={12}/> {t("overtime_pending_confirm")} {t("ot_progress_confirmed").replace("{n}", String(task.confirmed_count || 0)).replace("{total}", String(task.total_assignments || 0))}{disputeSuffix}
                            </span>
                          );
                        })()}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-3">
                          {canVerify && task.needs_verification && task.status !== "completed" && (
                            <button onClick={() => openVerify(task)}
                              className="text-blue-600 hover:text-blue-800 text-xs font-medium">{t("ot_go_verify")}</button>
                          )}
                          {isAdmin && (
                            <button onClick={() => deleteTask(task.id)}
                              className="text-red-500 hover:text-red-700 text-xs font-medium">{t("delete")}</button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              </div>
            </div>
          )}
        </>
      )}

      {/* Dispute overtime modal */}
      {disputeTask && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50 p-4" onClick={() => setDisputeTask(null)}>
          <div className="bg-white rounded-2xl w-full max-w-lg shadow-xl max-h-[85vh] flex flex-col" onClick={e => e.stopPropagation()}>
            <div className="bg-orange-500 text-white px-5 py-3 rounded-t-2xl flex items-center gap-2 shrink-0">
              <AlertTriangle size={20} />
              <span className="font-semibold">{t("ot_dispute_title")}</span>
            </div>
            <div className="p-5 space-y-4 overflow-y-auto">
              <div className="text-sm text-gray-600">
                {disputeTask.date} {disputeTask.start_time}-{disputeTask.end_time} · {t("ot_planned")}{disputeTask.hours}h · {t("ot_actual")}{disputeTask.actual_hours}h · {t("ot_pay_label")}{disputeTask.earned_amount}{t("baht")}
              </div>
              <div>
                <label className="form-label text-sm font-medium text-gray-600 mb-1 block">{t("ot_dispute_reason_label")}</label>
                <textarea className="form-input w-full text-base py-2" rows={4} value={disputeReason}
                  onChange={e => setDisputeReason(e.target.value)} placeholder={t("ot_dispute_reason_required")} />
              </div>
              <div>
                <button onClick={() => document.getElementById("dispute-file-input")?.click()}
                  className="btn-secondary text-sm px-4 py-2 flex items-center gap-2">
                  <Upload size={16}/> {t("ot_select_photo")}
                </button>
                <input id="dispute-file-input" type="file" accept="image/*" className="hidden" onChange={onDisputeFile} />
                {disputeFile && (
                  <div className="mt-2 flex items-center gap-2">
                    {disputePreview && <img src={disputePreview} alt="" className="w-16 h-16 object-cover rounded-lg border"/>}
                    <span className="text-sm text-gray-600">{disputeFile.name}</span>
                  </div>
                )}
              </div>
              <p className="text-xs text-gray-400">{t("ot_dispute_hint")}</p>
            </div>
            <div className="border-t px-5 py-4 bg-gray-50 rounded-b-2xl flex justify-end gap-3 shrink-0">
              <button onClick={() => setDisputeTask(null)} className="btn-secondary text-sm px-6 py-2">{t("cancel")}</button>
              <button onClick={handleDispute} className="bg-orange-500 text-white text-sm px-6 py-2 rounded-lg hover:bg-orange-600">{t("ot_submit_dispute")}</button>
            </div>
          </div>
        </div>
      )}

      {/* Verify overtime modal */}
      {verifyTask && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50 p-4" onClick={() => setVerifyTask(null)}>
          <div className="bg-white rounded-2xl w-full max-w-lg shadow-xl max-h-[85vh] flex flex-col" onClick={e => e.stopPropagation()}>
            <div className="bg-blue-500 text-white px-5 py-3 rounded-t-2xl flex items-center gap-2 shrink-0">
              <Clock size={20} />
              <span className="font-semibold">{t("verify_overtime_title")}</span>
            </div>
            <div className="p-5 space-y-4 overflow-y-auto">
              <div className="text-sm text-gray-600">
                {verifyTask.date} {verifyTask.start_time}-{verifyTask.end_time} {t("ot_planned")}{verifyTask.hours}h
              </div>
              {(verifyTask.assignments || []).some((a: any) => a.has_dispute) && (
                <div className="bg-orange-50 border border-orange-200 rounded-lg px-3 py-2 text-sm text-orange-600">
                  <AlertTriangle size={14} className="inline mr-1"/>
                  {t("ot_verify_dispute_hint").replace("{n}", String((verifyTask.assignments || []).filter((a: any) => a.has_dispute).length))}
                </div>
              )}
              {(verifyTask.assignments || []).some((a: any) => a.confirmed) && (
                <div className="bg-blue-50 border border-blue-200 rounded-lg px-3 py-2 text-sm text-blue-600">
                  <CheckCircle size={14} className="inline mr-1"/>
                  {t("ot_verify_confirmed_hint").replace("{n}", String((verifyTask.assignments || []).filter((a: any) => a.confirmed).length))}
                </div>
              )}
              <div className="space-y-3">
                {(verifyTask.assignments || []).map((a: any) => (
                  <div key={a.id} className={a.has_dispute ? "border border-orange-200 rounded-lg p-2" : ""}>
                    <div className="flex items-center gap-3">
                      <span className="w-20 font-medium text-sm shrink-0 flex items-center gap-1 flex-wrap">
                        {a.employee_name}
                        {a.has_dispute && (
                          <span className="bg-orange-500 text-white text-[10px] px-1 py-0.5 rounded leading-none">{t("ot_has_dispute")}</span>
                        )}
                      </span>
                      <input type="number" step="0.1"
                        className={`form-input flex-1 text-base py-2 ${a.confirmed ? "bg-gray-100 text-gray-400 cursor-not-allowed" : ""}`}
                        value={verifyHours[a.id] ?? ""}
                        disabled={a.confirmed}
                        onChange={e => setVerifyHours(h => ({ ...h, [a.id]: e.target.value }))} />
                      <span className={`w-24 text-right text-sm shrink-0 ${a.confirmed ? "text-gray-500" : "text-green-600 font-medium"}`}>{a.confirmed ? a.earned_amount : verifyFee(a)}{t("baht")}</span>
                    </div>
                    {a.confirmed && (
                      <div className="mt-1 pl-[92px] text-xs text-gray-400">{t("ot_verify_confirmed_note")}</div>
                    )}
                    {a.has_dispute && (
                      <div className="mt-1 pl-[92px] space-y-1">
                        {a.dispute_reason && <p className="text-xs text-orange-600">{a.dispute_reason}</p>}
                        {a.dispute_photo && (
                          <button onClick={() => setViewPhoto(a.dispute_photo)}
                            className="text-blue-600 hover:text-blue-800 text-xs font-medium">{t("ot_view_photo")}</button>
                        )}
                      </div>
                    )}
                  </div>
                ))}
              </div>
              <p className="text-xs text-gray-400">{t("ot_round_up_note")}</p>
            </div>
            <div className="border-t px-5 py-4 bg-gray-50 rounded-b-2xl flex justify-end gap-3 shrink-0">
              <button onClick={() => setVerifyTask(null)} className="btn-secondary text-sm px-6 py-2">{t("cancel")}</button>
              <button onClick={handleVerify} className="btn-primary text-sm px-6 py-2">{t("save_verify")}</button>
            </div>
          </div>
        </div>
      )}

      {/* Zoomed dispute photo */}
      {viewPhoto && (
        <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-[70] p-4" onClick={() => setViewPhoto(null)}>
          <img src={`/${viewPhoto}`} alt="" className="max-w-full max-h-[90vh] rounded-lg shadow-2xl object-contain" onClick={e => e.stopPropagation()} />
        </div>
      )}

      {/* Create overtime modal */}
      {showForm && isAdmin && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50 p-4" onClick={() => setShowForm(false)}>
          <div className="bg-white rounded-2xl w-full max-w-lg shadow-xl max-h-[85vh] flex flex-col" onClick={e => e.stopPropagation()}>
            <div className="bg-blue-500 text-white px-5 py-3 rounded-t-2xl flex items-center gap-2 shrink-0">
              <Clock size={20} />
              <span className="font-semibold">{t("create_overtime_task")}</span>
            </div>
            <div className="p-5 space-y-4 overflow-y-auto">
              <div>
                <label className="form-label text-sm font-medium text-gray-600 mb-1 block">{t("overtime_date")}</label>
                <input type="date" className="form-input text-base py-2.5 w-full" value={form.date}
                  onChange={e => setForm({ ...form, date: e.target.value })} />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="form-label text-sm font-medium text-gray-600 mb-1 block">{t("start_time")}</label>
                  <input type="time" className="form-input text-base py-2.5 w-full" value={form.start_time}
                    onChange={e => setForm({ ...form, start_time: e.target.value })} />
                </div>
                <div>
                  <label className="form-label text-sm font-medium text-gray-600 mb-1 block">{t("end_time")}</label>
                  <input type="time" className="form-input text-base py-2.5 w-full" value={form.end_time}
                    onChange={e => setForm({ ...form, end_time: e.target.value })} />
                </div>
              </div>
              <div className="bg-gray-50 rounded-lg p-3 text-center">
                <span className="text-sm text-gray-500">{t("estimated_hours")}: </span>
                <span className="font-bold text-blue-600">{calcHours()} {t("hours")}</span>
                <span className="text-sm text-gray-400 ml-2">{t("ot_half_hours").replace("{n}", String(halfHours()))}</span>
              </div>
              <div>
                <label className="form-label text-sm font-medium text-gray-600 mb-1 block">{t("select_employees")}</label>
                <input type="text" className="form-input text-base py-2 w-full mb-2" placeholder={t("search_by_employee_no")} value={empSearch}
                  onChange={e => setEmpSearch(e.target.value)} />
                <div className="border rounded-lg max-h-48 overflow-y-auto divide-y">
                  {employees.filter((e: any) => !empSearch || (e.employee_no || "").toLowerCase().includes(empSearch.toLowerCase()) || e.name.toLowerCase().includes(empSearch.toLowerCase())).length === 0 ? (
                    <p className="text-gray-400 text-sm text-center py-6">{t("no_matching_employee")}</p>
                  ) : (
                    employees.filter((e: any) => !empSearch || (e.employee_no || "").toLowerCase().includes(empSearch.toLowerCase()) || e.name.toLowerCase().includes(empSearch.toLowerCase())).map((e: any) => {
                      const hasTemplate = e.salary_template_id != null;
                      const fee = empOvertimeFee(e);
                      return (
                      <label key={e.id} className={`flex items-center gap-3 px-4 py-2.5 ${hasTemplate ? "cursor-pointer hover:bg-gray-50" : "cursor-not-allowed opacity-60"} ${
                        form.employee_ids.includes(e.id) ? "bg-blue-50" : ""
                      }`}>
                        <input type="checkbox" checked={form.employee_ids.includes(e.id)}
                          onChange={() => toggleEmployee(e.id)} disabled={!hasTemplate}
                          className="w-4 h-4 text-blue-500 rounded" />
                        <div className="flex-1">
                          <p className="text-sm font-medium">{e.name}</p>
                          <p className="text-xs text-gray-400">{t("employee_no")} {e.employee_no || "-"} · {e.position || t("position_labor")}</p>
                        </div>
                        {hasTemplate ? (
                          <span className="text-xs text-green-600 font-medium whitespace-nowrap">{t("ot_fee_per_emp").replace("{pay}", String(fee))}</span>
                        ) : (
                          <span className="text-xs text-red-500 font-medium whitespace-nowrap">{t("ot_no_template")}</span>
                        )}
                      </label>
                      );
                    })
                  )}
                </div>
                <p className="text-xs text-gray-400 mt-1">{t("selected_count").replace("{n}", String(form.employee_ids.length))}</p>
              </div>
            </div>
            <div className="border-t px-5 py-4 bg-gray-50 rounded-b-2xl flex justify-end gap-3 shrink-0">
              <button onClick={() => setShowForm(false)} className="btn-secondary text-sm px-6 py-2">{t("cancel")}</button>
              <button onClick={handleCreate} className="btn-primary text-sm px-6 py-2">{t("create_overtime")}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

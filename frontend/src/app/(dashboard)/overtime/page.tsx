"use client";
import { useEffect, useState } from "react";
import { api, getToken, getActiveWarehouseId } from "@/lib/api";
import { useToast } from "@/components/ui/Toast";
import { useAuth } from "@/hooks/useAuth";
import { useI18n } from "@/hooks/useI18n";
import { useRouter } from "next/navigation";
import { Clock, Plus, CheckCircle, XCircle, AlertTriangle } from "lucide-react";

export default function OvertimePage() {
  const { toast } = useToast(); const { user } = useAuth(); const { t } = useI18n(); const router = useRouter();
  const [tasks, setTasks] = useState<any[]>([]);
  const [employees, setEmployees] = useState<any[]>([]);
  const [pendingTasks, setPendingTasks] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [limitHours, setLimitHours] = useState(50);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [scheduleEnd, setScheduleEnd] = useState("18:00");

  const isAdmin = user?.role === "warehouse_admin";
  const isLabor = user?.role === "warehouse_labor";

  const defaultForm = {
    employee_ids: [] as number[],
    date: new Date().toISOString().slice(0, 10),
    start_time: "18:00",
    end_time: "",
  };
  const [form, setForm] = useState({ ...defaultForm });
  const [empSearch, setEmpSearch] = useState("");

  useEffect(() => { if (!getToken()) router.push("/login"); load(); }, []);

  async function load() {
    setLoading(true);
    try {
      // Load overtime tasks
      const r = await api.get<any>("/overtime?page_size=200");
      setTasks(r.data || []);
      // Load pending tasks for labor
      if (isLabor) {
        const p = await api.get<any>("/overtime/pending");
        setPendingTasks(p.data || []);
      }
      // Load employees for admin
      if (isAdmin) {
        const er = await api.get<any>("/employees?page_size=200");
        setEmployees((er.data || []).filter((e: any) => e.status !== "resigned"));
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
      const lr = await api.get<any>("/overtime/limit");
      setLimitHours(lr.max_hours || 50);
      setLimitInput(String(lr.max_hours || 50));
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
      const r = await api.post(`/overtime/${taskId}/confirm`);
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

  return (
    <div>
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
                {pendingTasks.map((task: any) => (
                  <div key={task.id} className="bg-orange-50 border border-orange-200 rounded-xl p-4 flex items-center justify-between">
                    <div>
                      <p className="font-medium text-gray-800">{task.date} {task.start_time}-{task.end_time}</p>
                      <p className="text-sm text-gray-500">{t("ot_hours_pay").replace("{h}", task.hours).replace("{pay}", String(task.earned_amount ?? 0))}</p>
                    </div>
                    <button onClick={() => confirmOvertime(task.id)}
                      className="bg-green-500 text-white px-4 py-2 rounded-lg text-sm hover:bg-green-600 flex items-center gap-1">
                      <CheckCircle size={16}/> {t("ot_confirm_btn")}
                    </button>
                  </div>
                ))}
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
              <table className="w-full text-sm">
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
                        <div className="flex flex-wrap gap-1">
                          {(task.assignments || []).map((a: any) => (
                            <span key={a.id} className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs ${
                              a.confirmed ? "bg-green-50 text-green-700" : "bg-gray-100 text-gray-500"
                            }`}>
                              {a.confirmed ? <CheckCircle size={12}/> : <Clock size={12}/>}
                              {a.employee_name} {a.earned_amount?.toFixed(0)}{t("baht")}
                            </span>
                          ))}
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium ${
                          task.status === "completed" ? "bg-green-50 text-green-700" : "bg-blue-50 text-blue-700"
                        }`}>
                          {task.status === "completed" ? <CheckCircle size={12}/> : <Clock size={12}/>}
                          {task.status === "completed" ? t("completed_status") : t("overtime_pending_confirm")}
                          {task.status !== "completed" && ` (${task.confirmed_count || 0}/${task.total_assignments || 0})`}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        {isLabor && !task.assignments?.find((a: any) => a.confirmed) && (
                          <button onClick={() => confirmOvertime(task.id)}
                            className="text-green-600 hover:text-green-800 text-xs font-medium">{t("confirm")}</button>
                        )}
                        {isAdmin && (
                          <button onClick={() => deleteTask(task.id)}
                            className="text-red-500 hover:text-red-700 text-xs font-medium">{t("delete")}</button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {/* Create overtime modal */}
      {showForm && isAdmin && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50 p-4" onClick={() => setShowForm(false)}>
          <div className="bg-white rounded-2xl w-full max-w-lg shadow-xl" onClick={e => e.stopPropagation()}>
            <div className="bg-blue-500 text-white px-5 py-3 rounded-t-2xl flex items-center gap-2">
              <Clock size={20} />
              <span className="font-semibold">{t("create_overtime_task")}</span>
            </div>
            <div className="p-5 space-y-4">
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
            <div className="border-t px-5 py-4 bg-gray-50 rounded-b-2xl flex justify-end gap-3">
              <button onClick={() => setShowForm(false)} className="btn-secondary text-sm px-6 py-2">{t("cancel")}</button>
              <button onClick={handleCreate} className="btn-primary text-sm px-6 py-2">{t("create_overtime")}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

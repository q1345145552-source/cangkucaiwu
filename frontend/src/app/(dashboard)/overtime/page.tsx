"use client";
import { useEffect, useState } from "react";
import { api, getToken, getActiveWarehouseId } from "@/lib/api";
import { useToast } from "@/components/ui/Toast";
import { useAuth } from "@/hooks/useAuth";
import { useRouter } from "next/navigation";
import { Clock, Plus, Settings, CheckCircle, XCircle, AlertTriangle } from "lucide-react";

export default function OvertimePage() {
  const { toast } = useToast(); const { user } = useAuth(); const router = useRouter();
  const [tasks, setTasks] = useState<any[]>([]);
  const [employees, setEmployees] = useState<any[]>([]);
  const [pendingTasks, setPendingTasks] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [limitHours, setLimitHours] = useState(50);
  const [showLimitSetting, setShowLimitSetting] = useState(false);
  const [limitInput, setLimitInput] = useState("50");
  const [warnings, setWarnings] = useState<string[]>([]);

  const isAdmin = user?.role === "warehouse_admin";
  const isLabor = user?.role === "warehouse_labor";

  const defaultForm = {
    employee_ids: [] as number[],
    date: new Date().toISOString().slice(0, 10),
    start_time: "17:00",
    end_time: "20:00",
    hourly_rate: 75,
  };
  const [form, setForm] = useState({ ...defaultForm });

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
            ws.push(`${d.employee_name} 本月已加班 ${d.total_hours}h，接近上限 ${limitHours}h`);
          }
        }
        setWarnings(ws);
      }
    } catch {}
    setLoading(false);
  }

  async function handleCreate() {
    if (form.employee_ids.length === 0) { toast("error", "请选择至少一位员工"); return; }
    try {
      await api.post("/overtime", form);
      toast("success", "加班任务创建成功");
      setShowForm(false);
      setForm({ ...defaultForm, employee_ids: [] });
      load();
    } catch (err: any) { toast("error", err.message || "创建失败"); }
  }

  async function confirmOvertime(taskId: number) {
    try {
      const r = await api.post(`/overtime/${taskId}/confirm`);
      toast("success", r.message || "确认成功");
      load();
    } catch (err: any) { toast("error", err.message || "确认失败"); }
  }

  async function deleteTask(taskId: number) {
    if (!confirm("确定删除该加班任务吗？")) return;
    try {
      await api.delete(`/overtime/${taskId}`);
      toast("success", "已删除");
      load();
    } catch (err: any) { toast("error", err.message || "删除失败"); }
  }

  async function saveLimit() {
    try {
      const v = parseFloat(limitInput) || 50;
      await api.put("/overtime/limit", { max_hours: v });
      setLimitHours(v);
      toast("success", `加班上限已设为 ${v}h/月`);
      setShowLimitSetting(false);
    } catch (err: any) { toast("error", err.message || "保存失败"); }
  }

  function toggleEmployee(id: number) {
    setForm(f => ({
      ...f,
      employee_ids: f.employee_ids.includes(id)
        ? f.employee_ids.filter(eid => eid !== id)
        : [...f.employee_ids, id],
    }));
  }

  function calcHours() {
    try {
      const [sh, sm] = form.start_time.split(":").map(Number);
      const [eh, em] = form.end_time.split(":").map(Number);
      const mins = (eh * 60 + em) - (sh * 60 + sm);
      return mins > 0 ? (mins / 60).toFixed(1) : "0.0";
    } catch { return "0.0"; }
  }

  return (
    <div>
      <div className="flex justify-between mb-4 flex-wrap gap-2 items-center">
        <h1 className="page-title flex items-center gap-2"><Clock size={24}/>加班管理</h1>
        <div className="flex gap-2 items-center">
          {isAdmin && (
            <>
              <div className="flex items-center gap-1 text-sm text-gray-500 bg-gray-100 rounded-lg px-3 py-1.5">
                <span>上限: {limitHours}h/月</span>
                <button onClick={() => { setShowLimitSetting(!showLimitSetting); load(); }}
                  className="p-1 hover:bg-gray-200 rounded"><Settings size={14}/></button>
              </div>
              {showLimitSetting && (
                <div className="flex items-center gap-2 bg-white border rounded-lg px-3 py-1.5 shadow-sm">
                  <span className="text-xs text-gray-400">上限(h)</span>
                  <input type="number" value={limitInput} onChange={e => setLimitInput(e.target.value)}
                    className="w-16 border rounded px-2 py-0.5 text-sm text-center" step="1" />
                  <button onClick={saveLimit} className="text-xs bg-blue-500 text-white px-2 py-0.5 rounded">确定</button>
                </div>
              )}
              <button onClick={() => setShowForm(true)} className="btn-primary flex items-center gap-1 text-sm px-4 py-2">
                <Plus size={16}/> 发起加班
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
        <div className="text-center py-12 text-gray-400">加载中...</div>
      ) : (
        <>
          {/* Pending tasks for labor */}
          {isLabor && pendingTasks.length > 0 && (
            <div className="mb-6">
              <h2 className="text-sm font-medium text-orange-600 mb-3 flex items-center gap-1">
                <Clock size={16} /> 待确认加班 ({pendingTasks.length})
              </h2>
              <div className="grid gap-3">
                {pendingTasks.map((t: any) => (
                  <div key={t.id} className="bg-orange-50 border border-orange-200 rounded-xl p-4 flex items-center justify-between">
                    <div>
                      <p className="font-medium text-gray-800">{t.date} {t.start_time}-{t.end_time}</p>
                      <p className="text-sm text-gray-500">工时 {t.hours}h × {t.hourly_rate}泰铢/h = {(t.hours * t.hourly_rate).toFixed(0)}泰铢</p>
                    </div>
                    <button onClick={() => confirmOvertime(t.id)}
                      className="bg-green-500 text-white px-4 py-2 rounded-lg text-sm hover:bg-green-600 flex items-center gap-1">
                      <CheckCircle size={16}/> 确认签到
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
              <p>暂无加班记录</p>
            </div>
          ) : (
            <div className="bg-white rounded-xl border overflow-hidden">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-gray-50">
                    <th className="text-left px-4 py-3 font-medium text-gray-500">日期</th>
                    <th className="text-left px-4 py-3 font-medium text-gray-500">时间</th>
                    <th className="text-left px-4 py-3 font-medium text-gray-500">工时</th>
                    <th className="text-left px-4 py-3 font-medium text-gray-500">费率</th>
                    <th className="text-left px-4 py-3 font-medium text-gray-500">参与员工</th>
                    <th className="text-left px-4 py-3 font-medium text-gray-500">状态</th>
                    <th className="text-left px-4 py-3 font-medium text-gray-500">操作</th>
                  </tr>
                </thead>
                <tbody>
                  {tasks.map((t: any) => (
                    <tr key={t.id} className="border-b border-gray-50 hover:bg-gray-50">
                      <td className="px-4 py-3">{t.date}</td>
                      <td className="px-4 py-3">{t.start_time} - {t.end_time}</td>
                      <td className="px-4 py-3">{t.hours}h</td>
                      <td className="px-4 py-3">{t.hourly_rate}泰铢/h</td>
                      <td className="px-4 py-3">
                        <div className="flex flex-wrap gap-1">
                          {(t.assignments || []).map((a: any) => (
                            <span key={a.id} className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs ${
                              a.confirmed ? "bg-green-50 text-green-700" : "bg-gray-100 text-gray-500"
                            }`}>
                              {a.confirmed ? <CheckCircle size={12}/> : <Clock size={12}/>}
                              {a.employee_name} {a.earned_amount?.toFixed(0)}泰铢
                            </span>
                          ))}
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium ${
                          t.status === "completed" ? "bg-green-50 text-green-700" : "bg-blue-50 text-blue-700"
                        }`}>
                          {t.status === "completed" ? <CheckCircle size={12}/> : <Clock size={12}/>}
                          {t.status === "completed" ? "已完成" : "进行中"}
                          {t.status !== "completed" && ` (${t.confirmed_count || 0}/${t.total_assignments || 0})`}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        {isLabor && !t.assignments?.find((a: any) => a.confirmed) && (
                          <button onClick={() => confirmOvertime(t.id)}
                            className="text-green-600 hover:text-green-800 text-xs font-medium">确认</button>
                        )}
                        {isAdmin && (
                          <button onClick={() => deleteTask(t.id)}
                            className="text-red-500 hover:text-red-700 text-xs font-medium">删除</button>
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
              <span className="font-semibold">发起加班任务</span>
            </div>
            <div className="p-5 space-y-4">
              <div>
                <label className="form-label text-sm font-medium text-gray-600 mb-1 block">加班日期</label>
                <input type="date" className="form-input text-base py-2.5 w-full" value={form.date}
                  onChange={e => setForm({ ...form, date: e.target.value })} />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="form-label text-sm font-medium text-gray-600 mb-1 block">开始时间</label>
                  <input type="time" className="form-input text-base py-2.5 w-full" value={form.start_time}
                    onChange={e => setForm({ ...form, start_time: e.target.value })} />
                </div>
                <div>
                  <label className="form-label text-sm font-medium text-gray-600 mb-1 block">结束时间</label>
                  <input type="time" className="form-input text-base py-2.5 w-full" value={form.end_time}
                    onChange={e => setForm({ ...form, end_time: e.target.value })} />
                </div>
              </div>
              <div className="bg-gray-50 rounded-lg p-3 text-center">
                <span className="text-sm text-gray-500">预计工时: </span>
                <span className="font-bold text-blue-600">{calcHours()} 小时</span>
                <span className="text-sm text-gray-400 ml-2">× {form.hourly_rate}泰铢/h = {(parseFloat(calcHours()) * form.hourly_rate).toFixed(0)}泰铢/人</span>
              </div>
              <div>
                <label className="form-label text-sm font-medium text-gray-600 mb-1 block">选择参与员工（可多选）</label>
                <div className="border rounded-lg max-h-48 overflow-y-auto divide-y">
                  {employees.length === 0 ? (
                    <p className="text-gray-400 text-sm text-center py-6">暂无可用员工</p>
                  ) : (
                    employees.map((e: any) => (
                      <label key={e.id} className={`flex items-center gap-3 px-4 py-2.5 cursor-pointer hover:bg-gray-50 ${
                        form.employee_ids.includes(e.id) ? "bg-blue-50" : ""
                      }`}>
                        <input type="checkbox" checked={form.employee_ids.includes(e.id)}
                          onChange={() => toggleEmployee(e.id)}
                          className="w-4 h-4 text-blue-500 rounded" />
                        <div>
                          <p className="text-sm font-medium">{e.name}</p>
                          <p className="text-xs text-gray-400">{e.position || "仓库劳工"} · {e.phone || "无电话"}</p>
                        </div>
                      </label>
                    ))
                  )}
                </div>
                <p className="text-xs text-gray-400 mt-1">已选: {form.employee_ids.length} 人</p>
              </div>
            </div>
            <div className="border-t px-5 py-4 bg-gray-50 rounded-b-2xl flex justify-end gap-3">
              <button onClick={() => setShowForm(false)} className="btn-secondary text-sm px-6 py-2">取消</button>
              <button onClick={handleCreate} className="btn-primary text-sm px-6 py-2">发起加班</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

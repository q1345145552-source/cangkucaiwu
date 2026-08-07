"use client";
import { useEffect, useState, useRef } from "react";
import { api, getToken, getActiveWarehouseId } from "@/lib/api";
import { useToast } from "@/components/ui/Toast";
import { useAuth } from "@/hooks/useAuth";
import { useRouter } from "next/navigation";
import { Calendar, ChevronLeft, ChevronRight, Clock, UserX, Bed, AlertCircle, CheckCircle, XCircle, Camera, Upload, UserPlus, Settings, Grid3X3 } from "lucide-react";
import ClockRecordsGrid from "@/components/ClockRecordsGrid";

const STATUS_COLORS: Record<string, string> = {
  "present": "bg-green-100 text-green-700 border-green-300",
  "late": "bg-orange-100 text-orange-700 border-orange-300",
  "leave": "bg-purple-100 text-purple-700 border-purple-300",
  "rest": "bg-blue-100 text-blue-700 border-blue-300",
  "absent": "bg-red-100 text-red-700 border-red-300",
  "missing": "bg-gray-100 text-gray-600 border-gray-300",
  "future": "bg-white text-gray-300 border-gray-100",
};

export default function AttendancePage() {
  const { toast } = useToast(); const { user } = useAuth(); const router = useRouter();
  const isAdmin = user?.role === "warehouse_admin" || user?.role === "super_admin";
  const [activeTab, setActiveTab] = useState<"calendar" | "records">("calendar");

  // Month navigation
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);

  // Data
  const [employees, setEmployees] = useState<any[]>([]);
  const [events, setEvents] = useState<Record<string, any>>({});
  const [leaves, setLeaves] = useState<any[]>([]);
  const [restDays, setRestDays] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);

  // Modals
  const [showLeaveForm, setShowLeaveForm] = useState(false);
  const [showRestForm, setShowRestForm] = useState(false);
  const [showAbsenceForm, setShowAbsenceForm] = useState(false);
  const [leaveDate, setLeaveDate] = useState("");
  const [leaveReason, setLeaveReason] = useState("");
  const [leavePhoto, setLeavePhoto] = useState<File | null>(null);
  const photoInputRef = useRef<HTMLInputElement>(null);

  // Rest day form
  const [restEmployeeId, setRestEmployeeId] = useState<number>(0);
  const [restDate1, setRestDate1] = useState("");
  const [restDate2, setRestDate2] = useState("");

  // Absence form
  const [absenceEmpId, setAbsenceEmpId] = useState<number>(0);
  const [absenceDate, setAbsenceDate] = useState("");
  const [absenceReason, setAbsenceReason] = useState("");
  const [photoPopup, setPhotoPopup] = useState<any>(null);
  const [photoSessions, setPhotoSessions] = useState<any[]>([]);

  const monthStr = `${year}-${String(month).padStart(2, "0")}`;

  async function openPhotoPopup(empId: number, empName: string, dateStr: string) {
    try {
      const r = await api.get<any>(`/clock-in/photos?employee_id=${empId}&date=${dateStr}`);
      setPhotoPopup({ employee_name: empName, date: dateStr });
      setPhotoSessions(r.sessions || []);
    } catch {}
  }

  useEffect(() => { if (!getToken()) router.push("/login"); loadCalendar(); loadLeaves(); loadRestDays(); }, [monthStr]);

  function prevMonth() { if (month === 1) { setMonth(12); setYear(y => y - 1); } else { setMonth(m => m - 1); } }
  function nextMonth() { setMonth(m => m === 12 ? 1 : m + 1); if (month === 12) setYear(y => y + 1); }

  async function loadCalendar() {
    setLoading(true);
    try {
      const r = await api.get<any>(`/attendance/calendar?month=${monthStr}`);
      const evtMap: Record<string, any> = {};
      (r.events || []).forEach((e: any) => { evtMap[`${e.date}_${e.employee_id}`] = e; });
      setEvents(evtMap);
      setEmployees(r.employees || []);
    } catch {}
    setLoading(false);
  }

  async function loadLeaves() {
    try {
      const r = await api.get<any>(`/attendance/leaves?month=${monthStr}`);
      setLeaves(r.data || []);
    } catch {}
  }

  async function loadRestDays() {
    try {
      const r = await api.get<any>(`/attendance/rest-days?month=${monthStr}`);
      setRestDays(r.data || []);
    } catch {}
  }

  async function submitLeave() {
    if (!leaveDate) { toast("error", "请选择请假日期"); return; }
    const fd = new FormData();
    fd.append("leave_date", leaveDate);
    if (leaveReason) fd.append("reason", leaveReason);
    if (leavePhoto) fd.append("file", leavePhoto);

    try {
      const token = getToken();
      const res = await fetch("/api/v1/attendance/leaves", { method: "POST", headers: { Authorization: `Bearer ${token}` }, body: fd });
      const r = await res.json();
      if (res.ok) { toast("success", r.message); setShowLeaveForm(false); setLeaveDate(""); setLeavePhoto(null); loadLeaves(); }
      else toast("error", r.detail || "提交失败");
    } catch { toast("error", "网络错误"); }
  }

  async function approveLeave(id: number) {
    try { await api.put(`/attendance/leaves/${id}/approve`, {}); toast("success", "已批准"); loadLeaves(); loadCalendar(); }
    catch { toast("error", "操作失败"); }
  }

  async function rejectLeave(id: number) {
    try { await api.put(`/attendance/leaves/${id}/reject`, { reason: "管理员驳回" }); toast("success", "已驳回"); loadLeaves(); }
    catch { toast("error", "操作失败"); }
  }

  async function submitRestDays() {
    if (!restEmployeeId) { toast("error", "请选择员工"); return; }
    const dates = [restDate1, restDate2].filter(Boolean);
    if (dates.length === 0) { toast("error", "至少选择一个休息日"); return; }
    try {
      const r = await api.post<any>("/attendance/rest-days", { employee_id: restEmployeeId, rest_dates: dates });
      toast("success", r.message);
      setShowRestForm(false); setRestDate1(""); setRestDate2("");
      loadRestDays(); loadCalendar();
    } catch (err: any) { toast("error", err.message || "设置失败"); }
  }

  async function deleteRestDay(id: number) {
    try { await api.delete(`/attendance/rest-days/${id}`); toast("success", "已删除"); loadRestDays(); loadCalendar(); }
    catch { toast("error", "操作失败"); }
  }

  async function submitAbsence() {
    if (!absenceEmpId || !absenceDate) { toast("error", "请选择员工和日期"); return; }
    try {
      await api.post("/attendance/absences", { employee_id: absenceEmpId, absence_date: absenceDate, reason: absenceReason });
      toast("success", "已标记未到");
      setShowAbsenceForm(false); setAbsenceReason(""); loadCalendar();
    } catch (err: any) { toast("error", err.message || "操作失败"); }
  }

  // Build calendar grid
  const daysInMonth = new Date(year, month, 0).getDate();
  const firstDayOfWeek = new Date(year, month - 1, 1).getDay();
  const dayHeaders = ["日", "一", "二", "三", "四", "五", "六"];

  return (
    <div className="space-y-6">
      {/* Header: Month Navigation + Tab Bar + Action Buttons */}
      <div className="flex justify-between items-center flex-wrap gap-3">
        <div className="flex items-center gap-3 flex-wrap">
          <button onClick={prevMonth} className="p-1.5 hover:bg-gray-100 rounded-lg transition">
            <ChevronLeft size={20} />
          </button>
          <h1 className="text-lg font-bold min-w-[120px] text-center">{year}年{month}月</h1>
          <button onClick={nextMonth} className="p-1.5 hover:bg-gray-100 rounded-lg transition">
            <ChevronRight size={20} />
          </button>
          {isAdmin && (
            <div className="flex items-center gap-1.5 ml-2">
              <button onClick={() => setShowLeaveForm(true)} className="px-3 py-1.5 text-xs bg-purple-50 text-purple-600 rounded-lg hover:bg-purple-100 flex items-center gap-1">
                <Bed size={14}/>请假
              </button>
              <button onClick={() => setShowRestForm(true)} className="px-3 py-1.5 text-xs bg-blue-50 text-blue-600 rounded-lg hover:bg-blue-100 flex items-center gap-1">
                <Settings size={14}/>休息日
              </button>
              <button onClick={() => setShowAbsenceForm(true)} className="px-3 py-1.5 text-xs bg-red-50 text-red-600 rounded-lg hover:bg-red-100 flex items-center gap-1">
                <UserX size={14}/>未到
              </button>
            </div>
          )}
        </div>
        {isAdmin && (
          <div className="flex bg-gray-100 rounded-lg p-0.5">
            <button onClick={() => setActiveTab("calendar")} className={`px-4 py-1.5 rounded-md text-sm font-medium transition ${activeTab === "calendar" ? "bg-white text-gray-800 shadow-sm" : "text-gray-500 hover:text-gray-700"}`}>
              <Calendar size={15} className="inline mr-1.5"/>日历视图
            </button>
            <button onClick={() => setActiveTab("records")} className={`px-4 py-1.5 rounded-md text-sm font-medium transition ${activeTab === "records" ? "bg-white text-gray-800 shadow-sm" : "text-gray-500 hover:text-gray-700"}`}>
              <Grid3X3 size={15} className="inline mr-1.5"/>打卡记录
            </button>
          </div>
        )}
      </div>

      {activeTab === "records" ? (
        <ClockRecordsGrid year={year} month={month} />
      ) : (
        <>

          {/* Calendar Grid */}
      <div className="bg-white rounded-xl border overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm min-w-[800px]">
            <thead>
              <tr className="bg-gray-50">
                <th className="px-3 py-2 text-left text-gray-500 font-medium w-[100px]">员工</th>
                {Array.from({ length: daysInMonth }, (_, i) => (
                  <th key={i} className={`px-1 py-2 text-center text-gray-500 font-medium w-[36px] ${dayHeaders[(firstDayOfWeek + i) % 7] === "日" ? "text-red-400" : ""}`}>
                    <div className="text-xs">{dayHeaders[(firstDayOfWeek + i) % 7]}</div>
                    <div>{i + 1}</div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {employees.map((emp: any) => (
                <tr key={emp.id} className="border-t hover:bg-gray-50/30">
                  <td className="px-3 py-2 font-medium text-gray-700 text-xs whitespace-nowrap">
                    {emp.name}
                    <div className="text-gray-400 font-normal">{emp.position}</div>
                  </td>
                  {Array.from({ length: daysInMonth }, (_, i) => {
                    const dt = `${year}-${String(month).padStart(2, "0")}-${String(i + 1).padStart(2, "0")}`;
                    const key = `${dt}_${emp.id}`;
                    const evt = events[key];
                    const status = evt?.status || "future";
                    const label = evt?.status_label || "";
                    const today = new Date().toISOString().slice(0, 10);
                    const isToday = dt === today;
                    return (
                      <td key={i} className={`px-0.5 py-1 text-center ${isToday ? "ring-2 ring-blue-400 ring-inset" : ""}`}>
                        <div
                          className={`rounded text-xs py-1 cursor-pointer hover:opacity-80 hover:ring-1 hover:ring-blue-300 ${STATUS_COLORS[status] || "bg-white text-gray-300"}`}
                          title={label + " - 点击查看打卡照片"}
                          onClick={() => openPhotoPopup(emp.id, emp.name, dt)}
                        >
                          {label.slice(0, 2)}
                        </div>
                      </td>
                    );
                  })}
                </tr>
              ))}
              {employees.length === 0 && (
                <tr><td colSpan={daysInMonth + 1} className="text-center py-12 text-gray-400">暂无员工数据</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Legend */}
      <div className="flex gap-4 flex-wrap text-xs text-gray-500">
        {Object.entries({ present: "正常出勤", late: "迟到", leave: "请假", rest: "休息日", absent: "未到", missing: "未打卡" }).map(([k, v]) => (
          <div key={k} className="flex items-center gap-1"><div className={`w-3 h-3 rounded ${STATUS_COLORS[k]}`} />{v}</div>
        ))}
      </div>

      {/* Leave Requests Panel (Admin) */}
      {isAdmin && leaves.length > 0 && (
        <div className="bg-white rounded-xl border p-4">
          <h3 className="font-semibold mb-3 flex items-center gap-2"><Bed size={18} className="text-purple-500"/>请假审批</h3>
          <div className="space-y-2">
            {leaves.filter((l: any) => l.status === "pending").map((l: any) => (
              <div key={l.id} className="flex items-center justify-between p-3 bg-purple-50 rounded-lg text-sm">
                <div>
                  <span className="font-medium">{l.employee_name}</span>
                  <span className="text-gray-500 ml-2">{l.leave_date}</span>
                  {l.reason && <span className="text-gray-400 ml-2">- {l.reason}</span>}
                  {l.photo_path && <a href={`/${l.photo_path}`} target="_blank" className="text-blue-500 ml-2 text-xs">查看证明</a>}
                </div>
                <div className="flex gap-2">
                  <button onClick={() => approveLeave(l.id)} className="text-green-600 hover:bg-green-50 px-2 py-1 rounded text-xs">通过</button>
                  <button onClick={() => rejectLeave(l.id)} className="text-red-500 hover:bg-red-50 px-2 py-1 rounded text-xs">驳回</button>
                </div>
              </div>
            ))}
            {leaves.filter((l: any) => l.status !== "pending").length > 0 && (
              <details className="text-xs text-gray-400">
                <summary>历史记录</summary>
                {leaves.filter((l: any) => l.status !== "pending").map((l: any) => (
                  <div key={l.id} className="py-1">{l.employee_name} {l.leave_date} - {l.status === "approved" ? "已通过" : "已驳回"}</div>
                ))}
              </details>
            )}
          </div>
        </div>
      )}

      {/* Rest Days Panel (Admin) */}
      {isAdmin && restDays.length > 0 && (
        <div className="bg-white rounded-xl border p-4">
          <h3 className="font-semibold mb-3 flex items-center gap-2"><Settings size={18} className="text-blue-500"/>休息日安排</h3>
          <div className="flex flex-wrap gap-2">
            {restDays.map((r: any) => (
              <div key={r.id} className="flex items-center gap-1 px-3 py-1 bg-blue-50 text-blue-700 rounded-full text-xs">
                {r.employee_name}: {r.rest_date}
                <button onClick={() => deleteRestDay(r.id)} className="ml-1 text-blue-400 hover:text-red-500">&times;</button>
              </div>
            ))}
          </div>
        </div>
      )}

        </>
      )}

      {/* Leave Form Modal */}
      {showLeaveForm && (
        <div className="modal-overlay z-50" onClick={() => setShowLeaveForm(false)}>
          <div className="bg-white rounded-2xl w-[420px]" onClick={e => e.stopPropagation()}>
            <div className="bg-purple-600 text-white px-5 py-3 rounded-t-2xl flex items-center gap-2">
              <Bed size={18} /><h3 className="font-semibold">病假申请</h3>
              <button onClick={() => setShowLeaveForm(false)} className="ml-auto text-purple-200 hover:text-white">&times;</button>
            </div>
            <div className="p-5 space-y-4">
              <div>
                <label className="form-label text-sm mb-1 block">请假日期 <span className="text-red-400">*</span></label>
                <input type="date" className="form-input py-2.5" value={leaveDate} onChange={e => setLeaveDate(e.target.value)} />
              </div>
              <div>
                <label className="form-label text-sm mb-1 block">原因</label>
                <input className="form-input py-2.5" placeholder="如: 身体不适" value={leaveReason} onChange={e => setLeaveReason(e.target.value)} />
              </div>
              <div>
                <label className="form-label text-sm mb-1 block">证明图片</label>
                <div className="flex items-center gap-2">
                  <button onClick={() => photoInputRef.current?.click()} className="border border-dashed rounded-lg px-4 py-3 text-sm text-gray-400 hover:text-blue-500 hover:border-blue-300 flex items-center gap-2">
                    <Upload size={16}/>选择图片
                  </button>
                  {leavePhoto && <span className="text-xs text-green-600">{leavePhoto.name}</span>}
                </div>
                <input ref={photoInputRef} type="file" accept="image/*" capture="environment" onChange={e => setLeavePhoto(e.target.files?.[0] || null)} className="hidden" />
              </div>
              <p className="text-xs text-gray-400">每月最多请1天病假</p>
            </div>
            <div className="border-t px-5 py-3 bg-gray-50 rounded-b-2xl flex justify-end gap-3">
              <button onClick={() => setShowLeaveForm(false)} className="btn-secondary px-4 py-2 text-sm">取消</button>
              <button onClick={submitLeave} className="bg-purple-600 text-white px-4 py-2 rounded-lg text-sm">提交申请</button>
            </div>
          </div>
        </div>
      )}

      {/* Rest Day Form Modal */}
      {showRestForm && (
        <div className="modal-overlay z-50" onClick={() => setShowRestForm(false)}>
          <div className="bg-white rounded-2xl w-[420px]" onClick={e => e.stopPropagation()}>
            <div className="bg-blue-600 text-white px-5 py-3 rounded-t-2xl flex items-center gap-2">
              <Settings size={18} /><h3 className="font-semibold">设置休息日</h3>
              <button onClick={() => setShowRestForm(false)} className="ml-auto text-blue-200 hover:text-white">&times;</button>
            </div>
            <div className="p-5 space-y-4">
              <div>
                <label className="form-label text-sm mb-1 block">选择员工 <span className="text-red-400">*</span></label>
                <select className="form-input py-2.5" value={restEmployeeId || ""} onChange={e => setRestEmployeeId(+e.target.value)}>
                  <option value="">请选择</option>
                  {employees.map(e => <option key={e.id} value={e.id}>{e.name}</option>)}
                </select>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="form-label text-sm mb-1 block">休息日1</label>
                  <input type="date" className="form-input py-2.5" value={restDate1} onChange={e => setRestDate1(e.target.value)} />
                </div>
                <div>
                  <label className="form-label text-sm mb-1 block">休息日2</label>
                  <input type="date" className="form-input py-2.5" value={restDate2} onChange={e => setRestDate2(e.target.value)} />
                </div>
              </div>
              <p className="text-xs text-gray-400">每月固定2天，至少选一个日期</p>
            </div>
            <div className="border-t px-5 py-3 bg-gray-50 rounded-b-2xl flex justify-end gap-3">
              <button onClick={() => setShowRestForm(false)} className="btn-secondary px-4 py-2 text-sm">取消</button>
              <button onClick={submitRestDays} className="bg-blue-600 text-white px-4 py-2 rounded-lg text-sm">保存</button>
            </div>
          </div>
        </div>
      )}

      {/* Absence Form Modal */}
      {showAbsenceForm && (
        <div className="modal-overlay z-50" onClick={() => setShowAbsenceForm(false)}>
          <div className="bg-white rounded-2xl w-[420px]" onClick={e => e.stopPropagation()}>
            <div className="bg-red-500 text-white px-5 py-3 rounded-t-2xl flex items-center gap-2">
              <UserX size={18} /><h3 className="font-semibold">标记未到</h3>
              <button onClick={() => setShowAbsenceForm(false)} className="ml-auto text-red-200 hover:text-white">&times;</button>
            </div>
            <div className="p-5 space-y-4">
              <div>
                <label className="form-label text-sm mb-1 block">员工 <span className="text-red-400">*</span></label>
                <select className="form-input py-2.5" value={absenceEmpId || ""} onChange={e => setAbsenceEmpId(+e.target.value)}>
                  <option value="">请选择</option>
                  {employees.map(e => <option key={e.id} value={e.id}>{e.name}</option>)}
                </select>
              </div>
              <div>
                <label className="form-label text-sm mb-1 block">日期 <span className="text-red-400">*</span></label>
                <input type="date" className="form-input py-2.5" value={absenceDate} onChange={e => setAbsenceDate(e.target.value)} />
              </div>
              <div>
                <label className="form-label text-sm mb-1 block">原因</label>
                <input className="form-input py-2.5" placeholder="如: 无故旷工" value={absenceReason} onChange={e => setAbsenceReason(e.target.value)} />
              </div>
            </div>
            <div className="border-t px-5 py-3 bg-gray-50 rounded-b-2xl flex justify-end gap-3">
              <button onClick={() => setShowAbsenceForm(false)} className="btn-secondary px-4 py-2 text-sm">取消</button>
              <button onClick={submitAbsence} className="bg-red-500 text-white px-4 py-2 rounded-lg text-sm">确认标记</button>
            </div>
          </div>
        </div>
      )}

      {/* Photo Popup */}
      {photoPopup && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4" onClick={() => setPhotoPopup(null)}>
          <div className="bg-white rounded-2xl w-full max-w-lg max-h-[90vh] overflow-y-auto shadow-xl" onClick={e => e.stopPropagation()}>
            <div className="bg-blue-500 text-white px-5 py-3 rounded-t-2xl flex items-center gap-2 sticky top-0 z-10">
              <Camera size={20} />
              <span className="font-semibold">{photoPopup.employee_name} · {photoPopup.date} 打卡照片</span>
              <button onClick={() => setPhotoPopup(null)} className="ml-auto text-2xl text-blue-200">&times;</button>
            </div>
            <div className="p-4 space-y-4">
              {photoSessions.map((s: any) => (
                <div key={s.session} className="bg-gray-50 rounded-xl p-3">
                  <div className="flex items-center justify-between mb-2">
                    <span className="font-medium text-sm text-gray-700">
                      {s.session}. {s.label}
                    </span>
                    {s.clocked_in_at ? (
                      <span className="text-xs text-gray-400">
                        {new Date(s.clocked_in_at).toLocaleTimeString("zh-CN", { timeZone: "Asia/Bangkok" })}
                        {s.status !== "normal" && (
                          <span className={s.status === "late_half" ? "text-orange-500 ml-1" : "text-red-500 ml-1"}>
                            · 迟到
                          </span>
                        )}
                      </span>
                    ) : (
                      <span className="text-xs text-gray-300">未打卡</span>
                    )}
                  </div>
                  {s.photo_path ? (
                    <img src={`/${s.photo_path}`} alt={`${s.label}打卡照`}
                      className="w-full rounded-lg max-h-64 object-cover border" />
                  ) : (
                    <div className="w-full h-32 rounded-lg bg-gray-100 flex items-center justify-center text-gray-400 text-sm">
                      📷 未拍照
                    </div>
                  )}
                </div>
              ))}
            </div>
            <div className="border-t px-5 py-3 bg-gray-50 rounded-b-2xl text-center">
              <button onClick={() => setPhotoPopup(null)} className="text-sm text-gray-400">关闭</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

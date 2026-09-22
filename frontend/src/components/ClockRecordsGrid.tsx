"use client";
import { useState, useMemo, useEffect } from "react";
import { api, getToken } from "@/lib/api";
import { useI18n } from "@/hooks/useI18n";
import { useToast } from "@/components/ui/Toast";
import { useAuth } from "@/hooks/useAuth";
import { Camera, ChevronLeft, ChevronRight, Download, CalendarClock } from "lucide-react";
import SafeImage from "@/components/SafeImage";

const SESSION_KEYS: Record<number, string> = {
  1: "morning_shift", 2: "noon_break_end", 3: "afternoon_shift", 4: "evening_shift",
};

function buildDateList(startDate: string, endDate: string, dayNames: string[]): { date: string; day: number; weekday: string }[] {
  const list: { date: string; day: number; weekday: string }[] = [];
  const s = new Date(startDate + "T00:00:00");
  const e = new Date(endDate + "T00:00:00");
  if (isNaN(s.getTime()) || isNaN(e.getTime())) return list;
  for (let d = new Date(s); d <= e; d.setDate(d.getDate() + 1)) {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const dd = String(d.getDate()).padStart(2, "0");
    list.push({ date: `${y}-${m}-${dd}`, day: d.getDate(), weekday: dayNames[d.getDay()] });
  }
  return list;
}

export default function ClockRecordsGrid(props: { startDate: string; endDate: string; onChange?: () => void }) {
  const { startDate, endDate, onChange } = props;
  const { t } = useI18n();
  const { toast } = useToast();
  const { user } = useAuth();
  const canMakeup = user?.role === "warehouse_admin" || user?.role === "supervisor";
  const [employees, setEmployees] = useState<any[]>([]);
  const [records, setRecords] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [zoomedPhoto, setZoomedPhoto] = useState<string | null>(null);
  const [detailPopup, setDetailPopup] = useState<{ empId: number; empName: string; date: string; sessions: Record<number, any> } | null>(null);
  const [makeupForm, setMakeupForm] = useState<{ empId: number; empName: string; date: string } | null>(null);
  const [makeupSessions, setMakeupSessions] = useState<number[]>([]);
  const [makeupReason, setMakeupReason] = useState("");

  const dayNames = [0, 1, 2, 3, 4, 5, 6].map(i => t(`att_weekday_${i}`));
  const dateList = buildDateList(startDate, endDate, dayNames);
  const totalDays = dateList.length;

  useEffect(() => { load(); }, [startDate, endDate]);

  async function load() {
    setLoading(true);
    try {
      const r = await api.get<any>(`/clock-in/records?start_date=${startDate}&end_date=${endDate}`);
      setEmployees(r.employees || []);
      setRecords(r.records || []);
    } catch {}
    setLoading(false);
  }

  function openMakeupForm() {
    if (!detailPopup) return;
    setMakeupForm({ empId: detailPopup.empId, empName: detailPopup.empName, date: detailPopup.date });
    setMakeupSessions([]);
    setMakeupReason("");
  }

  function toggleSession(s: number) {
    setMakeupSessions(prev => prev.includes(s) ? prev.filter(x => x !== s) : [...prev, s].sort());
  }

  async function submitMakeup() {
    if (!makeupForm) return;
    if (makeupSessions.length === 0) { toast("error", t("mk_please_select_sessions")); return; }
    if (!makeupReason.trim()) { toast("error", t("mk_please_enter_reason")); return; }
    try {
      const r = await api.post<any>("/clock-in/makeup", {
        employee_id: makeupForm.empId,
        date: makeupForm.date,
        sessions: makeupSessions,
        reason: makeupReason,
      });
      toast("success", r.message || t("mk_success"));
      setMakeupForm(null);
      setMakeupSessions([]);
      setMakeupReason("");
      load();
      if (onChange) onChange();
    } catch (err: any) { toast("error", err.message || t("mk_failed")); }
  }

  async function exportExcel() {
    try {
      const token = getToken();
      const url = `/api/v1/clock-in/records/export?start_date=${startDate}&end_date=${endDate}`;
      const res = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        toast("error", err.detail || t("export_failed"));
        return;
      }
      const blob = await res.blob();
      const cd = res.headers.get("Content-Disposition") || "";
      let filename = `${t("clock_records")}_${startDate}_${endDate}.xlsx`;
      const m = cd.match(/filename\*=UTF-8''(.+)/);
      if (m) filename = decodeURIComponent(m[1]);
      const objectUrl = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = objectUrl;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(objectUrl);
      toast("success", t("export_success"));
    } catch {
      toast("error", t("export_failed"));
    }
  }

  const grid = useMemo(() => {
    const map: Record<string, Record<number, any>> = {};
    records.forEach((r: any) => {
      const key = `${r.employee_id || r.user_id}_${r.clock_date}`;
      if (!map[key]) map[key] = {};
      map[key][r.session] = r;
    });
    return map;
  }, [records]);

  const summary = useMemo(() => {
    const result: Record<number, { days: number; late: number; absent: number }> = {};
    const today = new Date().toISOString().slice(0, 10);
    employees.forEach(e => {
      let attendanceDays = 0, lateCount = 0, absentDays = 0;
      for (const d of dateList) {
        const dt = d.date;
        if (dt > today) break;
        const cell = grid[`${e.id}_${dt}`];
        if (cell) {
          attendanceDays++;
          Object.values(cell).forEach((cr: any) => { if (cr.status === "late_half" || cr.status === "late_one") lateCount++; });
        } else {
          absentDays++;
        }
      }
      result[e.id] = { days: attendanceDays, late: lateCount, absent: absentDays };
    });
    return result;
  }, [employees, records, grid, dateList]);

  const formatTime = (iso: string) => {
    if (!iso) return "";
    return new Date(iso).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", timeZone: "Asia/Bangkok" });
  };

  return (
    <div>
      <div className="flex justify-end mb-2">
        <button onClick={exportExcel}
          className="px-3 py-1.5 text-xs bg-green-600 text-white rounded-lg hover:bg-green-700 flex items-center gap-1">
          <Download size={14}/>{t("export_excel")}
        </button>
      </div>
      {loading ? (
        <div className="text-center py-12 text-gray-400">{t("loading")}</div>
      ) : (
        <div className="bg-white rounded-xl border overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-xs min-w-[900px]">
              <thead>
                <tr className="bg-gray-50">
                  <th className="sticky left-0 bg-gray-50 z-10 text-left px-3 py-2 font-medium text-gray-600 whitespace-nowrap w-[90px]">{t("att_employee")}</th>
                  {dateList.map((d) => (
                    <th key={d.date} className="px-1 py-2 text-center font-medium w-[38px] text-gray-500">
                      <div className="text-[10px]">{d.day}</div>
                      <div className="text-[9px]">{d.weekday}</div>
                    </th>
                  ))}
                  <th className="text-center px-2 py-2 font-medium text-gray-600 bg-blue-50 whitespace-nowrap">{t("att_attendance")}</th>
                  <th className="text-center px-2 py-2 font-medium text-orange-500 bg-orange-50 whitespace-nowrap">{t("att_late")}</th>
                  <th className="text-center px-2 py-2 font-medium text-red-400 bg-red-50 whitespace-nowrap">{t("att_absence")}</th>
                </tr>
              </thead>
              <tbody>
                {employees.map((emp: any) => {
                  const s = summary[emp.id] || { days: 0, late: 0, absent: 0 };
                  return (
                    <tr key={emp.id} className="border-t hover:bg-gray-50/30">
                      <td className="sticky left-0 bg-white z-10 px-3 py-2 font-medium text-gray-700 whitespace-nowrap">
                        <div className="flex items-center gap-1.5">
                          {emp.photo_path ? (
                            <SafeImage
                              src={emp.photo_thumb_path ? `/${emp.photo_thumb_path}` : `/${emp.photo_path}`}
                              fallbackSrc={`/${emp.photo_path}`}
                              alt={emp.name}
                              className="w-6 h-6 rounded-full object-cover border cursor-pointer"
                              onClick={() => setZoomedPhoto(`/${emp.photo_path}`)}
                              fallback={<div className="w-6 h-6 rounded-full bg-gray-200 flex items-center justify-center text-[10px] text-gray-400 font-bold">{emp.name?.[0]}</div>}
                            />
                          ) : (
                            <div className="w-6 h-6 rounded-full bg-gray-200 flex items-center justify-center text-[10px] text-gray-400 font-bold">{emp.name?.[0]}</div>
                          )}
                          <span>{emp.name}</span>
                        </div>
                      </td>
                      {dateList.map((d) => {
                        const dt = d.date;
                        const cell = grid[`${emp.id}_${dt}`];
                        const today = new Date().toISOString().slice(0, 10);
                        const isFuture = dt > today;
                        const hasLate = cell && Object.values(cell).some((cr: any) => cr.status === "late_half" || cr.status === "late_one");
                        const hasMakeup = cell && Object.values(cell).some((cr: any) => cr.is_makeup);
                        const count = cell ? [1,2,3,4].filter(s => cell[s]).length : 0;
                        const isPartial = count > 0 && count < 4;
                        const colorClass = isPartial
                          ? "bg-yellow-50 text-yellow-600"
                          : (hasLate ? "bg-orange-50 text-orange-600" : "bg-green-50 text-green-600");
                        return (
                          <td key={dt} className="px-0.5 py-0.5 text-center cursor-pointer hover:bg-blue-50/50"
                            onClick={() => setDetailPopup({ empId: emp.id, empName: emp.name, date: dt, sessions: cell || {} })}>
                            {isFuture ? (
                              <span className="text-gray-200">-</span>
                            ) : cell ? (
                              <div className="flex flex-col items-center gap-0.5">
                                {hasLate && count >= 4 && <span className="w-1.5 h-1.5 rounded-full bg-orange-500" />}
                                <span className={`rounded px-1 py-0.5 font-medium ${colorClass}`}>
                                  {count}/4
                                </span>
                                {hasMakeup && <span className="text-[9px] font-bold text-purple-600 bg-purple-50 rounded px-0.5">{t("makeup_short")}</span>}
                                {cell[4] && <span className="text-[10px] text-gray-500">{formatTime(cell[4].clocked_in_at)}</span>}
                              </div>
                            ) : (
                              <span className="text-gray-300 text-[10px]">{t("att_not_clocked")}</span>
                            )}
                          </td>
                        );
                      })}
                      <td className="text-center px-2 py-2 bg-blue-50/30"><span className="font-bold text-blue-600">{s.days}</span></td>
                      <td className="text-center px-2 py-2 bg-orange-50/30"><span className={`font-bold ${s.late > 0 ? "text-orange-500" : "text-gray-400"}`}>{s.late}</span></td>
                      <td className="text-center px-2 py-2 bg-red-50/30"><span className={`font-bold ${s.absent > 0 ? "text-red-500" : "text-gray-400"}`}>{s.absent}</span></td>
                    </tr>
                  );
                })}
                {employees.length === 0 && (
                  <tr><td colSpan={totalDays + 4} className="text-center py-12 text-gray-400">{t("att_no_employee_data")}</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
      {detailPopup && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4" onClick={() => setDetailPopup(null)}>
          <div className="bg-white rounded-2xl w-full max-w-lg max-h-[90vh] overflow-y-auto shadow-xl" onClick={e => e.stopPropagation()}>
            <div className="bg-blue-500 text-white px-5 py-3 rounded-t-2xl flex items-center gap-2 sticky top-0 z-10">
              <Camera size={20} /><span className="font-semibold">{detailPopup.empName} · {detailPopup.date} {t("att_clock_detail_title")}</span>
              <button onClick={() => setDetailPopup(null)} className="ml-auto text-2xl text-blue-200 hover:text-white">&times;</button>
            </div>
            <div className="p-4 space-y-4">
              {[1,2,3,4].map(s => {
                const cr = detailPopup.sessions[s];
                return (
                  <div key={s} className="bg-gray-50 rounded-xl p-3">
                    <div className="flex items-center justify-between mb-2">
                      <span className="font-medium text-sm text-gray-700">{s}. {t(SESSION_KEYS[s])}</span>
                      {cr ? (
                        <div className="flex items-center gap-2 flex-wrap">
                          {cr.is_makeup && <span className="text-xs px-1.5 py-0.5 rounded bg-purple-50 text-purple-600 font-medium">{t("makeup")}</span>}
                          {cr.status !== "normal" && (
                            <span className={`text-xs px-1.5 py-0.5 rounded ${cr.status === "late_half" ? "bg-orange-50 text-orange-600" : "bg-red-50 text-red-600"}`}>
                              {cr.status === "late_half" ? t("att_late_half_hour") : t("att_late_one_hour")}</span>
                          )}
                          <span className="text-xs text-gray-500">{formatTime(cr.clocked_in_at)}</span>
                        </div>
                      ) : <span className="text-xs text-gray-300">{t("att_not_clocked")}</span>}
                    </div>
                    {cr?.is_makeup && (
                      <div className="mb-2 text-[11px] text-purple-600 bg-purple-50 rounded px-2 py-1">
                        {t("makeup_by")}：{cr.makeup_by_name || "-"} · {t("reason")}：{cr.makeup_reason || "-"}
                      </div>
                    )}
                    {cr?.photo_path ? (
                      <SafeImage
                        src={`/${cr.photo_thumb_path || cr.photo_path}`}
                        fallbackSrc={`/${cr.photo_path}`}
                        className="w-full rounded-lg max-h-64 object-cover border cursor-pointer hover:opacity-90"
                        onClick={() => setZoomedPhoto(`/${cr.photo_path}`)}
                        fallback={<div className="w-full h-32 rounded-lg bg-gray-100 flex items-center justify-center text-gray-400 text-sm">📷 {t("att_no_photo")}</div>}
                      />
                    ) : <div className="w-full h-32 rounded-lg bg-gray-100 flex items-center justify-center text-gray-400 text-sm">📷 {t("att_no_photo")}</div>}
                  </div>
                );
              })}
            </div>
            <div className="border-t px-5 py-3 bg-gray-50 rounded-b-2xl flex justify-end gap-3 items-center">
              {canMakeup && (
                <button onClick={openMakeupForm}
                  className="bg-purple-600 text-white px-4 py-2 rounded-lg text-sm flex items-center gap-1 hover:bg-purple-700">
                  <CalendarClock size={14}/>{t("makeup")}
                </button>
              )}
              <button onClick={() => setDetailPopup(null)} className="text-sm text-gray-400 px-4 py-2">{t("close")}</button>
            </div>
          </div>
        </div>
      )}
      {makeupForm && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-[60] p-4" onClick={() => setMakeupForm(null)}>
          <div className="bg-white rounded-2xl w-full max-w-md shadow-xl" onClick={e => e.stopPropagation()}>
            <div className="bg-purple-600 text-white px-5 py-3 rounded-t-2xl flex items-center gap-2">
              <CalendarClock size={18} /><span className="font-semibold">{t("makeup")}</span>
              <button onClick={() => setMakeupForm(null)} className="ml-auto text-2xl text-purple-200 hover:text-white">&times;</button>
            </div>
            <div className="p-5 space-y-4">
              <div>
                <label className="form-label text-xs mb-1 block">{t("att_employee")}</label>
                <div className="form-input py-2 bg-gray-50 text-gray-700">{makeupForm.empName}</div>
              </div>
              <div>
                <label className="form-label text-xs mb-1 block">{t("date")}</label>
                <div className="form-input py-2 bg-gray-50 text-gray-700">{makeupForm.date}</div>
              </div>
              <div>
                <label className="form-label text-xs mb-1 block">{t("sessions")} <span className="text-red-400">*</span></label>
                <div className="flex flex-wrap gap-2">
                  <button type="button" onClick={() => setMakeupSessions([1,2,3,4])}
                    className={`px-3 py-1.5 rounded-lg text-xs border ${makeupSessions.length === 4 ? "bg-purple-600 text-white border-purple-600" : "bg-white text-gray-600 border-gray-200"}`}>
                    {t("makeup_all_day")}
                  </button>
                  {[1,2,3,4].map(s => (
                    <button key={s} type="button" onClick={() => toggleSession(s)}
                      className={`px-3 py-1.5 rounded-lg text-xs border ${makeupSessions.includes(s) ? "bg-purple-600 text-white border-purple-600" : "bg-white text-gray-600 border-gray-200"}`}>
                      {t(SESSION_KEYS[s])}
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <label className="form-label text-xs mb-1 block">{t("reason")} <span className="text-red-400">*</span></label>
                <textarea className="form-input py-2 w-full" rows={2} value={makeupReason} onChange={e => setMakeupReason(e.target.value)} placeholder={t("mk_please_enter_reason")} />
              </div>
            </div>
            <div className="border-t px-5 py-3 bg-gray-50 rounded-b-2xl flex justify-end gap-3">
              <button onClick={() => setMakeupForm(null)} className="btn-secondary px-4 py-2 text-sm">{t("cancel")}</button>
              <button onClick={submitMakeup} className="bg-purple-600 text-white px-5 py-2 rounded-lg text-sm">{t("submit_makeup")}</button>
            </div>
          </div>
        </div>
      )}

      {zoomedPhoto && (
        <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-[70] p-4" onClick={() => setZoomedPhoto(null)}>
          <button onClick={() => setZoomedPhoto(null)} className="absolute top-4 right-4 text-white/70 hover:text-white text-4xl">&times;</button>
          <img src={zoomedPhoto} className="max-w-full max-h-[90vh] rounded-lg object-contain" onClick={e => e.stopPropagation()} />
        </div>
      )}
    </div>
  );
}

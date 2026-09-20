"use client";
import { useState, useMemo, useEffect } from "react";
import { api, getToken } from "@/lib/api";
import { useI18n } from "@/hooks/useI18n";
import { useToast } from "@/components/ui/Toast";
import { Camera, ChevronLeft, ChevronRight, Download } from "lucide-react";

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

export default function ClockRecordsGrid(props: { startDate: string; endDate: string }) {
  const { startDate, endDate } = props;
  const { t } = useI18n();
  const { toast } = useToast();
  const [employees, setEmployees] = useState<any[]>([]);
  const [records, setRecords] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [zoomedPhoto, setZoomedPhoto] = useState<string | null>(null);
  const [detailPopup, setDetailPopup] = useState<{ empName: string; date: string; sessions: Record<number, any> } | null>(null);

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

  async function exportExcel() {
    try {
      const token = getToken();
      const url = `/api/v1/clock-in/records/export?start_date=${startDate}&end_date=${endDate}`;
      const res = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        toast("error", err.detail || "导出失败");
        return;
      }
      const blob = await res.blob();
      const cd = res.headers.get("Content-Disposition") || "";
      let filename = `打卡记录_${startDate}_${endDate}.xlsx`;
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
      toast("success", "导出成功");
    } catch {
      toast("error", "导出失败");
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
          <Download size={14}/>导出Excel
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
                            <img src={`/${emp.photo_path}`} className="w-6 h-6 rounded-full object-cover border cursor-pointer"
                              onClick={() => setZoomedPhoto(`/${emp.photo_path}`)} />
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
                        return (
                          <td key={dt} className="px-0.5 py-0.5 text-center cursor-pointer hover:bg-blue-50/50"
                            onClick={() => setDetailPopup({ empName: emp.name, date: dt, sessions: cell || {} })}>
                            {isFuture ? (
                              <span className="text-gray-200">-</span>
                            ) : cell ? (
                              <div className="flex flex-col items-center gap-0.5">
                                {hasLate && <span className="w-1.5 h-1.5 rounded-full bg-orange-500" />}
                                <span className={`rounded px-1 py-0.5 font-medium ${hasLate ? "bg-orange-50 text-orange-600" : "bg-green-50 text-green-600"}`}>
                                  {[1,2,3,4].filter(s => cell[s]).length}/4
                                </span>
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
                        <div className="flex items-center gap-2">
                          {cr.status !== "normal" && (
                            <span className={`text-xs px-1.5 py-0.5 rounded ${cr.status === "late_half" ? "bg-orange-50 text-orange-600" : "bg-red-50 text-red-600"}`}>
                              {cr.status === "late_half" ? t("att_late_half_hour") : t("att_late_one_hour")}</span>
                          )}
                          <span className="text-xs text-gray-500">{formatTime(cr.clocked_in_at)}</span>
                        </div>
                      ) : <span className="text-xs text-gray-300">{t("att_not_clocked")}</span>}
                    </div>
                    {cr?.photo_path ? (
                      <img src={`/${cr.photo_path}`} className="w-full rounded-lg max-h-64 object-cover border cursor-pointer hover:opacity-90"
                        onClick={() => setZoomedPhoto(`/${cr.photo_path}`)} />
                    ) : <div className="w-full h-32 rounded-lg bg-gray-100 flex items-center justify-center text-gray-400 text-sm">📷 {t("att_no_photo")}</div>}
                  </div>
                );
              })}
            </div>
            <div className="border-t px-5 py-3 bg-gray-50 rounded-b-2xl text-center">
              <button onClick={() => setDetailPopup(null)} className="text-sm text-gray-400">{t("close")}</button>
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

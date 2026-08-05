"use client";
import { useEffect, useState, useMemo } from "react";
import { api, getToken } from "@/lib/api";
import { useRouter } from "next/navigation";
import { Camera, ChevronLeft, ChevronRight } from "lucide-react";

const SESSION_LABELS: Record<number, string> = {
  1: "早上上班", 2: "中午休息结束", 3: "下午上班", 4: "下午下班",
};

function daysInMonth(y: number, m: number) {
  return new Date(y, m, 0).getDate();
}

export default function ClockRecordsPage() {
  const router = useRouter();
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [employees, setEmployees] = useState<any[]>([]);
  const [records, setRecords] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [zoomedPhoto, setZoomedPhoto] = useState<string | null>(null);

  const monthStr = `${year}-${String(month).padStart(2, "0")}`;
  const totalDays = daysInMonth(year, month);

  useEffect(() => { if (!getToken()) { router.push("/login"); return; } load(); }, [monthStr]);

  function prevMonth() { if (month === 1) { setMonth(12); setYear(y => y - 1); } else { setMonth(m => m - 1); } }
  function nextMonth() { setMonth(m => m === 12 ? 1 : m + 1); if (month === 12) setYear(y => y + 1); }

  async function load() {
    setLoading(true);
    try {
      const r = await api.get<any>(`/clock-in/records?month=${monthStr}`);
      setEmployees(r.employees || []);
      setRecords(r.records || []);
    } catch {}
    setLoading(false);
  }

  // Build lookup: (employee_id, date) -> { session1, session2, session3, session4 }
  const grid = useMemo(() => {
    const map: Record<string, Record<number, any>> = {};
    records.forEach((r: any) => {
      const key = `${r.employee_id || r.user_id}_${r.clock_date}`;
      if (!map[key]) map[key] = {};
      map[key][r.session] = r;
    });
    return map;
  }, [records]);

  // Summary per employee
  const summary = useMemo(() => {
    const s: Record<number, { days: number; late: number; absent: number }> = {};
    employees.forEach(e => { s[e.id] = { days: 0, late: 0, absent: 0 }; });
    const seen = new Set<string>();
    records.forEach((r: any) => {
      const eid = r.employee_id || r.user_id;
      if (!s[eid]) return;
      const key = `${eid}_${r.clock_date}`;
      if (!seen.has(key)) {
        seen.add(key);
        s[eid].days++;
      }
      if (r.status === "late_half" || r.status === "late_one") {
        s[eid].late++;
      }
    });
    // Calculate absent days
    const today = new Date().toISOString().slice(0, 10);
    employees.forEach(e => {
      for (let d = 1; d <= totalDays; d++) {
        const dt = `${year}-${String(month).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
        if (dt > today) break;
        const dow = new Date(dt).getDay();
        if (dow === 0) continue; // Sunday
        const key = `${e.id}_${dt}`;
        if (!grid[key]) s[e.id].absent++;
      }
    });
    // Fix: the days count from records includes partial sessions. Use actual unique date count.
    // Actually the above `days` counts unique dates, which is correct for attendance days.
    // But absent should exclude dates already counted. Let me adjust.
    // Recalculate properly:
    const result: Record<number, { days: number; late: number; absent: number }> = {};
    employees.forEach(e => {
      let attendanceDays = 0;
      let lateCount = 0;
      let absentDays = 0;
      for (let d = 1; d <= totalDays; d++) {
        const dt = `${year}-${String(month).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
        if (dt > today) break;
        const dow = new Date(dt).getDay();
        if (dow === 0) continue;
        const cellKey = `${e.id}_${dt}`;
        const cell = grid[cellKey];
        if (cell) {
          attendanceDays++;
          Object.values(cell).forEach((cr: any) => {
            if (cr.status === "late_half" || cr.status === "late_one") lateCount++;
          });
        } else {
          absentDays++;
        }
      }
      result[e.id] = { days: attendanceDays, late: lateCount, absent: absentDays };
    });
    return result;
  }, [employees, records, grid, year, month, totalDays]);

  const formatTime = (iso: string) => {
    if (!iso) return "";
    const d = new Date(iso);
    return d.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", timeZone: "Asia/Bangkok" });
  };

  const dayHeaders = ["日", "一", "二", "三", "四", "五", "六"];

  return (
    <div>
      <div className="flex justify-between items-center flex-wrap gap-2 mb-4">
        <h1 className="page-title flex items-center gap-2"><Camera size={24} />打卡记录</h1>
        <div className="flex items-center gap-2">
          <button onClick={prevMonth} className="p-2 hover:bg-gray-100 rounded-lg"><ChevronLeft size={20}/></button>
          <span className="font-semibold text-lg min-w-[120px] text-center">{year}年{month}月</span>
          <button onClick={nextMonth} className="p-2 hover:bg-gray-100 rounded-lg"><ChevronRight size={20}/></button>
        </div>
      </div>

      {loading ? (
        <div className="text-center py-12 text-gray-400">加载中...</div>
      ) : (
        <div className="bg-white rounded-xl border overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-xs min-w-[900px]">
              <thead>
                <tr className="bg-gray-50">
                  <th className="sticky left-0 bg-gray-50 z-10 text-left px-3 py-2 font-medium text-gray-600 whitespace-nowrap w-[90px]">员工</th>
                  {Array.from({ length: totalDays }, (_, i) => {
                    const dt = new Date(year, month - 1, i + 1);
                    return (
                      <th key={i} className={`px-1 py-2 text-center font-medium w-[38px] ${dt.getDay() === 0 ? "text-red-400" : "text-gray-500"}`}>
                        <div className="text-[10px]">{i + 1}</div>
                        <div className="text-[9px]">{dayHeaders[dt.getDay()]}</div>
                      </th>
                    );
                  })}
                  <th className="text-center px-2 py-2 font-medium text-gray-600 bg-blue-50 whitespace-nowrap">出勤</th>
                  <th className="text-center px-2 py-2 font-medium text-orange-500 bg-orange-50 whitespace-nowrap">迟到</th>
                  <th className="text-center px-2 py-2 font-medium text-red-400 bg-red-50 whitespace-nowrap">缺勤</th>
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
                            <img src={`/${emp.photo_path}?v=${Date.now()}`} className="w-6 h-6 rounded-full object-cover border cursor-pointer"
                              onClick={() => setZoomedPhoto(`/${emp.photo_path}`)} />
                          ) : (
                            <div className="w-6 h-6 rounded-full bg-gray-200 flex items-center justify-center text-[10px] text-gray-400 font-bold">
                              {emp.name?.[0]}
                            </div>
                          )}
                          <span>{emp.name}</span>
                        </div>
                      </td>
                      {Array.from({ length: totalDays }, (_, i) => {
                        const d = i + 1;
                        const dt = `${year}-${String(month).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
                        const cellKey = `${emp.id}_${dt}`;
                        const cell = grid[cellKey];
                        const today = new Date().toISOString().slice(0, 10);
                        const isFuture = dt > today;
                        const isSunday = new Date(dt).getDay() === 0;
                        const hasLate = cell && Object.values(cell).some((cr: any) => cr.status === "late_half" || cr.status === "late_one");
                        return (
                          <td key={i} className={`px-0.5 py-0.5 text-center ${isSunday ? "bg-red-50/30" : ""}`}>
                            {isFuture ? (
                              <span className="text-gray-200">-</span>
                            ) : cell ? (
                              <div className="flex flex-col items-center gap-0.5" title={[1,2,3,4].map(s => {
                                const cr = cell[s];
                                return cr ? `${SESSION_LABELS[s]}: ${formatTime(cr.clocked_in_at)}` : `${SESSION_LABELS[s]}: -`;
                              }).join("\n")}>
                                {hasLate && <span className="w-1.5 h-1.5 rounded-full bg-orange-500" />}
                                <span className={`rounded px-1 py-0.5 font-medium ${hasLate ? "bg-orange-50 text-orange-600" : "bg-green-50 text-green-600"}`}>
                                  {[1,2,3,4].filter(s => cell[s]).length}/4
                                </span>
                                {cell[4] && (
                                  <span className="text-[10px] text-gray-500">{formatTime(cell[4].clocked_in_at)}</span>
                                )}
                              </div>
                            ) : isSunday ? (
                              <span className="text-gray-300 text-[10px]">休</span>
                            ) : (
                              <span className="text-gray-300 text-[10px]">未打卡</span>
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
                  <tr><td colSpan={totalDays + 4} className="text-center py-12 text-gray-400">暂无员工数据</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Photo zoom */}
      {zoomedPhoto && (
        <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-[70] p-4" onClick={() => setZoomedPhoto(null)}>
          <button onClick={() => setZoomedPhoto(null)} className="absolute top-4 right-4 text-white/70 hover:text-white text-4xl">&times;</button>
          <img src={zoomedPhoto} className="max-w-full max-h-[90vh] rounded-lg object-contain" onClick={e => e.stopPropagation()} />
        </div>
      )}
    </div>
  );
}

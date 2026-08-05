"use client";
import { useEffect, useState, useMemo } from "react";
import { api, getToken } from "@/lib/api";
import { useToast } from "@/components/ui/Toast";
import { useRouter } from "next/navigation";
import { Camera, ChevronLeft, ChevronRight, Clock, X } from "lucide-react";

const SESSION_LABELS: Record<number, string> = {
  1: "早上上班", 2: "中午休息结束", 3: "下午上班", 4: "下午下班",
};

export default function ClockRecordsPage() {
  const { toast } = useToast(); const router = useRouter();
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [records, setRecords] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);

  // Photo popup
  const [photoPopup, setPhotoPopup] = useState<any>(null);
  const [photoSessions, setPhotoSessions] = useState<any[]>([]);
  const [photoLoading, setPhotoLoading] = useState(false);

  const monthStr = `${year}-${String(month).padStart(2, "0")}`;

  useEffect(() => { if (!getToken()) { router.push("/login"); return; } loadRecords(); }, [monthStr]);

  function prevMonth() { if (month === 1) { setMonth(12); setYear(y => y - 1); } else { setMonth(m => m - 1); } }
  function nextMonth() {
    const n = new Date();
    if (year === n.getFullYear() && month === n.getMonth() + 1) return;
    setMonth(m => m === 12 ? 1 : m + 1);
    if (month === 12) setYear(y => y + 1);
  }

  async function loadRecords() {
    setLoading(true);
    try {
      const r = await api.get<any>(`/clock-in/records?month=${monthStr}`);
      setRecords(r.data || []);
    } catch {}
    setLoading(false);
  }

  // Group records by (date, user_id)
  const grouped = useMemo(() => {
    const map: Record<string, { date: string; user_id: number; employee_id: number | null; user_name: string; sessions: Record<number, any> }> = {};
    records.forEach((r: any) => {
      const key = `${r.clock_date}_${r.user_id}`;
      if (!map[key]) {
        map[key] = { date: r.clock_date, user_id: r.user_id, employee_id: r.employee_id || null, user_name: r.user_name, sessions: {} };
      }
      map[key].sessions[r.session] = r;
    });
    return Object.values(map).sort((a, b) => b.date.localeCompare(a.date) || a.user_name.localeCompare(b.user_name));
  }, [records]);

  async function openPhotoPopup(empId: number | null, userId: number, empName: string, dateStr: string) {
    setPhotoLoading(true);
    setPhotoPopup({ employee_name: empName, date: dateStr });
    try {
      const eid = empId || userId;
      const r = await api.get<any>(`/clock-in/photos?employee_id=${eid}&date=${dateStr}`);
      setPhotoSessions(r.sessions || []);
    } catch {
      setPhotoSessions([]);
    }
    setPhotoLoading(false);
  }

  const statusBadge = (status: string) => {
    if (!status || status === "normal") return null;
    if (status === "late_half") return <span className="text-xs px-1.5 py-0.5 rounded bg-orange-50 text-orange-600 font-medium">迟到半小时</span>;
    if (status === "late_one") return <span className="text-xs px-1.5 py-0.5 rounded bg-red-50 text-red-600 font-medium">迟到1小时</span>;
    return null;
  };

  return (
    <div>
      <h1 className="page-title flex items-center gap-2 mb-4">
        <Camera size={24} /> 打卡记录
      </h1>

      {/* Month selector */}
      <div className="flex items-center gap-3 mb-4 bg-white rounded-xl border px-4 py-2">
        <button onClick={prevMonth} className="p-1 hover:bg-gray-100 rounded min-w-[32px] min-h-[32px] flex items-center justify-center">
          <ChevronLeft size={18} />
        </button>
        <span className="font-medium text-gray-700 min-w-[100px] text-center">
          {year}年{String(month).padStart(2, "0")}月
        </span>
        <button onClick={nextMonth}
          className={`p-1 hover:bg-gray-100 rounded min-w-[32px] min-h-[32px] flex items-center justify-center ${
            year === new Date().getFullYear() && month === new Date().getMonth() + 1 ? "text-gray-300" : ""
          }`}
          disabled={year === new Date().getFullYear() && month === new Date().getMonth() + 1}
        >
          <ChevronRight size={18} />
        </button>
      </div>

      {loading ? (
        <div className="text-center py-12 text-gray-400">加载中...</div>
      ) : grouped.length === 0 ? (
        <div className="text-center py-12 text-gray-400 bg-white rounded-xl border">
          <Clock size={40} className="mx-auto mb-3 text-gray-300" />
          <p>暂无打卡记录</p>
        </div>
      ) : (
        <div className="bg-white rounded-xl border overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50 border-b">
                  <th className="text-left px-4 py-3 font-medium text-gray-600 whitespace-nowrap">日期</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-600 whitespace-nowrap">员工</th>
                  <th className="text-left px-3 py-3 font-medium text-gray-600 whitespace-nowrap">
                    <span className="text-xs">早上上班 09:00</span>
                  </th>
                  <th className="text-left px-3 py-3 font-medium text-gray-600 whitespace-nowrap">
                    <span className="text-xs">中午休息结束 12:00</span>
                  </th>
                  <th className="text-left px-3 py-3 font-medium text-gray-600 whitespace-nowrap">
                    <span className="text-xs">下午上班 13:00</span>
                  </th>
                  <th className="text-left px-3 py-3 font-medium text-gray-600 whitespace-nowrap">
                    <span className="text-xs">下午下班 18:00</span>
                  </th>
                  <th className="text-left px-4 py-3 font-medium text-gray-600 whitespace-nowrap">迟到</th>
                  <th className="text-center px-4 py-3 font-medium text-gray-600 whitespace-nowrap">照片</th>
                </tr>
              </thead>
              <tbody>
                {grouped.map((row, idx) => {
                  const hasLate = [1, 2, 3, 4].some(s => {
                    const r = row.sessions[s];
                    return r && (r.status === "late_half" || r.status === "late_one");
                  });
                  const hasPhoto = [1, 2, 3, 4].some(s => row.sessions[s]?.photo_path);
                  return (
                    <tr key={idx} className={`border-b hover:bg-gray-50 ${hasLate ? "bg-orange-50/30" : ""}`}>
                      <td className="px-4 py-3 whitespace-nowrap text-gray-700">{row.date}</td>
                      <td className="px-4 py-3 whitespace-nowrap font-medium text-gray-800">{row.user_name}</td>
                      {[1, 2, 3, 4].map(s => {
                        const r = row.sessions[s];
                        return (
                          <td key={s} className="px-3 py-3 whitespace-nowrap">
                            {r?.clocked_in_at ? (
                              <span className={s === 1 && (r.status === "late_half" || r.status === "late_one") ? "text-orange-600 font-medium" : "text-gray-600"}>
                                {new Date(r.clocked_in_at).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", timeZone: "Asia/Bangkok" })}
                              </span>
                            ) : (
                              <span className="text-gray-300">-</span>
                            )}
                          </td>
                        );
                      })}
                      <td className="px-4 py-3 whitespace-nowrap">
                        {hasLate ? (
                          [1, 2, 3, 4].map(s => {
                            const r = row.sessions[s];
                            return r && (r.status === "late_half" || r.status === "late_one") ? (
                              <span key={s} className="text-xs px-1.5 py-0.5 rounded bg-red-50 text-red-600 font-medium mr-1">
                                {r.status === "late_half" ? "迟到" : "严重迟到"}
                              </span>
                            ) : null;
                          })
                        ) : (
                          <span className="text-gray-300 text-xs">正常</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-center">
                        <button
                          onClick={() => openPhotoPopup(row.employee_id, row.user_id, row.user_name, row.date)}
                          className={`p-1.5 rounded-lg min-w-[36px] min-h-[36px] flex items-center justify-center ${
                            hasPhoto ? "text-blue-500 hover:bg-blue-50" : "text-gray-300"
                          }`}
                          title="查看打卡照片"
                        >
                          <Camera size={16} />
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Photo Popup Modal */}
      {photoPopup && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4" onClick={() => setPhotoPopup(null)}>
          <div className="bg-white rounded-2xl w-full max-w-lg max-h-[90vh] overflow-y-auto shadow-xl" onClick={e => e.stopPropagation()}>
            <div className="bg-blue-500 text-white px-5 py-3 rounded-t-2xl flex items-center gap-2 sticky top-0 z-10">
              <Camera size={20} />
              <span className="font-semibold">{photoPopup.employee_name} · {photoPopup.date} 打卡照片</span>
              <button onClick={() => setPhotoPopup(null)} className="ml-auto text-2xl text-blue-200 hover:text-white">&times;</button>
            </div>
            <div className="p-4 space-y-4">
              {photoLoading ? (
                <div className="text-center py-8 text-gray-400">加载中...</div>
              ) : (
                photoSessions.map((s: any) => (
                  <div key={s.session} className="bg-gray-50 rounded-xl p-3">
                    <div className="flex items-center justify-between mb-2">
                      <span className="font-medium text-sm text-gray-700">
                        {s.session}. {s.label}
                      </span>
                      {s.clocked_in_at ? (
                        <span className="text-xs text-gray-400">
                          {new Date(s.clocked_in_at).toLocaleTimeString("zh-CN", { timeZone: "Asia/Bangkok" })}
                          {s.status !== "normal" && s.status !== "missing" && (
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
                ))
              )}
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

"use client";
import { useEffect, useState, useRef } from "react";
import { api, getToken } from "@/lib/api";
import { useToast } from "@/components/ui/Toast";
import { useAuth } from "@/hooks/useAuth";
import { useRouter } from "next/navigation";
import { ClipboardCheck, Clock, Camera, CheckCircle2, AlertTriangle, Lock } from "lucide-react";
import { formatThaiTime, formatThaiDate } from "@/lib/thai-time";

const SESSION_LABELS: Record<number, { label: string; time: string; icon: string }> = {
  1: { label: "早上上班", time: "09:00", icon: "🌅" },
  2: { label: "中午休息结束", time: "12:00", icon: "☀️" },
  3: { label: "下午上班", time: "13:00", icon: "🕐" },
  4: { label: "下午下班", time: "18:00", icon: "🌇" },
};

function useThaiClock() {
  const [time, setTime] = useState<Date>(() => {
    const now = new Date();
    const utc = now.getTime() + now.getTimezoneOffset() * 60000;
    return new Date(utc + 7 * 60 * 60000);
  });

  useEffect(() => {
    const timer = setInterval(() => {
      const now = new Date();
      const utc = now.getTime() + now.getTimezoneOffset() * 60000;
      setTime(new Date(utc + 7 * 60 * 60000));
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  return time;
}

export default function ClockInPage() {
  const { toast } = useToast();
  const { user } = useAuth();
  const router = useRouter();
  const [completed, setCompleted] = useState<Record<number, any>>({});
  const [loading, setLoading] = useState<Record<number, boolean>>({});
  const [previewPhoto, setPreviewPhoto] = useState<string | null>(null);
  const [currentSession, setCurrentSession] = useState<number | null>(null);
  const [employeeInfo, setEmployeeInfo] = useState<any>(null);
  const cameraInputRef = useRef<HTMLInputElement>(null);
  const thaiTime = useThaiClock();

  useEffect(() => {
    if (!getToken()) { router.push("/login"); return; }
    loadToday();
    loadEmployeeInfo();
  }, []);

  async function loadToday() {
    try {
      const r = await api.get<any>("/clock-in/today");
      setCompleted(r.completed || {});
    } catch {}
  }

  async function loadEmployeeInfo() {
    try {
      const r = await api.get<any>("/employees?page_size=100");
      if (r.data) {
        const me = r.data.find((e: any) => e.user_id === user?.id);
        setEmployeeInfo(me || null);
      }
    } catch {}
  }

  // Get daily wage for dynamic penalty calculation
  const dailyWage = employeeInfo?.daily_wage || 400;
  const hourlyRate = dailyWage / 8;
  const penaltyHalf = Math.round(hourlyRate * 0.5); // 迟到半小时
  const penaltyOne = Math.round(hourlyRate);         // 迟到1小时

  // Check if session N is open: session 1 always open, session N needs session N-1 done
  function isSessionOpen(session: number): boolean {
    if (session === 1) return true;
    return !!completed[session - 1];
  }

  function triggerCamera(session: number) {
    if (!isSessionOpen(session)) return;
    setCurrentSession(session);
    setPreviewPhoto(null);
    cameraInputRef.current?.click();
  }

  function handlePhotoSelected(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      setPreviewPhoto(reader.result as string);
    };
    reader.readAsDataURL(file);
  }

  async function confirmClockIn() {
    if (!previewPhoto || !currentSession) return;
    setLoading(prev => ({ ...prev, [currentSession!]: true }));
    try {
      const formData = new FormData();
      formData.append("session", String(currentSession));
      formData.append("photo_base64", previewPhoto);
      const res = await fetch("/api/v1/clock-in", {
        method: "POST",
        headers: { Authorization: `Bearer ${getToken()}` },
        body: formData,
      });
      const r = await res.json();
      if (res.ok) {
        toast("success", r.message || "打卡成功");
        setCurrentSession(null);
        setPreviewPhoto(null);
        loadToday();
      } else {
        toast("error", r.detail || "打卡失败");
      }
    } catch {
      toast("error", "网络错误");
    }
    setLoading(prev => ({ ...prev, [currentSession!]: false }));
    if (cameraInputRef.current) cameraInputRef.current.value = "";
  }

  function cancelPhoto() {
    setCurrentSession(null);
    setPreviewPhoto(null);
    if (cameraInputRef.current) cameraInputRef.current.value = "";
  }

  // Count completed sessions
  const completedCount = Object.keys(completed).length;

  return (
    <div className="max-w-md mx-auto space-y-4 px-1">
      {/* Header */}
      <div className="text-center space-y-2 pt-2">
        <h1 className="text-xl font-bold text-gray-800">打卡签到</h1>
        <p className="text-sm text-gray-500">{user?.display_name}</p>

        {/* Live clock - large for mobile */}
        <div className="inline-flex items-center gap-2 bg-blue-50 border border-blue-200 rounded-xl px-5 py-3">
          <Clock size={22} className="text-blue-500" />
          <span className="text-2xl font-mono font-bold text-blue-700">{formatThaiTime(thaiTime)}</span>
          <span className="text-xs text-blue-400 ml-1">泰国</span>
        </div>
        <p className="text-sm text-gray-400">今日已完成 {completedCount}/4</p>
      </div>

      {/* Photo Preview Modal */}
      {previewPhoto && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4" onClick={cancelPhoto}>
          <div className="bg-white rounded-2xl w-full max-w-sm shadow-xl" onClick={e => e.stopPropagation()}>
            <div className="bg-blue-600 text-white px-5 py-3 rounded-t-2xl flex items-center gap-2">
              <Camera size={20} />
              <h3 className="font-semibold text-lg">打卡拍照确认</h3>
              <button onClick={cancelPhoto} className="ml-auto text-2xl text-blue-200">&times;</button>
            </div>
            <div className="p-4">
              <img src={previewPhoto} alt="打卡照片" className="w-full rounded-lg max-h-64 object-cover" />
              <p className="text-base text-gray-600 mt-3 text-center font-medium">
                {SESSION_LABELS[currentSession!]?.label} · {formatThaiTime()}
              </p>
              <div className="flex gap-3 mt-4">
                <button onClick={cancelPhoto} className="flex-1 py-3 border rounded-xl text-base active:bg-gray-100">
                  重新拍照
                </button>
                <button onClick={confirmClockIn} disabled={loading[currentSession!]}
                  className="flex-1 py-3 bg-blue-600 text-white rounded-xl text-base font-semibold active:bg-blue-700 disabled:opacity-50">
                  {loading[currentSession!] ? "提交中..." : "确认打卡"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      <input ref={cameraInputRef} type="file" accept="image/*" capture="environment"
        onChange={handlePhotoSelected} className="hidden" />

      {/* 4 Clock-in Cards - vertical, mobile-first */}
      <div className="space-y-3">
        {[1, 2, 3, 4].map(session => {
          const done = completed[session];
          const open = isSessionOpen(session);
          const isActive = loading[session];
          const info = SESSION_LABELS[session];

          return (
            <div key={session}
              className={`rounded-2xl border-2 transition-all ${
                done
                  ? "border-green-300 bg-green-50/50"
                  : open
                  ? "border-gray-200 bg-white active:border-blue-300"
                  : "border-gray-100 bg-gray-50 opacity-60"
              }`}>
              {/* Card body */}
              <div className="flex items-center gap-4 p-4">
                {/* Icon + label */}
                <div className="flex-shrink-0 w-12 h-12 rounded-xl flex items-center justify-center text-2xl"
                  style={{ background: done ? "#dcfce7" : open ? "#eff6ff" : "#f3f4f6" }}>
                  {info.icon}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold text-gray-700">{info.label}</span>
                    <span className="text-xs px-2 py-0.5 rounded-full bg-gray-100 text-gray-500 font-mono">{info.time}</span>
                  </div>
                  {done ? (
                    <div className="mt-1 space-y-0.5">
                      <div className="flex items-center gap-1 text-green-600 text-sm">
                        <CheckCircle2 size={14} />
                        <span>{new Date(done.clocked_in_at).toLocaleTimeString("zh-CN", { timeZone: "Asia/Bangkok" })}</span>
                      </div>
                      {done.status === "late_half" && (
                        <div className="text-xs text-orange-500 flex items-center gap-1">
                          <AlertTriangle size={12} /> 迟到 · 预计扣 {penaltyHalf} 泰铢
                        </div>
                      )}
                      {done.status === "late_one" && (
                        <div className="text-xs text-red-500 flex items-center gap-1">
                          <AlertTriangle size={12} /> 严重迟到 · 预计扣 {penaltyOne} 泰铢
                        </div>
                      )}
                    </div>
                  ) : (
                    <p className="text-xs text-gray-400 mt-1">
                      {open ? "点击右侧按钮拍照打卡" : `需先完成「${SESSION_LABELS[session - 1]?.label}」`}
                    </p>
                  )}
                </div>

                {/* Action button */}
                {done ? (
                  done.photo_path ? (
                    <img src={`/${done.photo_path}`} alt="打卡照"
                      className="w-14 h-14 rounded-lg object-cover flex-shrink-0" />
                  ) : (
                    <div className="w-14 h-14 rounded-lg bg-green-100 flex items-center justify-center flex-shrink-0">
                      <CheckCircle2 size={24} className="text-green-500" />
                    </div>
                  )
                ) : (
                  <button
                    onClick={() => triggerCamera(session)}
                    disabled={!open || isActive}
                    className={`flex-shrink-0 w-14 h-14 rounded-xl flex items-center justify-center text-white font-bold text-sm transition-all active:scale-95 ${
                      open
                        ? "bg-blue-600 hover:bg-blue-700 shadow-md shadow-blue-200"
                        : "bg-gray-300 cursor-not-allowed"
                    } disabled:opacity-70`}
                    title={open ? "拍照打卡" : "该时段未开放"}
                  >
                    {open ? <Camera size={22} /> : <Lock size={18} />}
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Legend */}
      <div className="text-center text-xs text-gray-400 pb-4 space-y-1">
        <p>必须按顺序打卡：上班 → 午休结束 → 下午上班 → 下班</p>
        <p>早上9:05前正常，9:05-9:30迟到扣{penaltyHalf}铢，9:31后扣{penaltyOne}铢</p>
        <p className="text-gray-300">日薪 {dailyWage}铢 · 时薪 {hourlyRate}铢</p>
      </div>
    </div>
  );
}

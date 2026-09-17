"use client";
import { useEffect, useState, useRef } from "react";
import { api, getToken } from "@/lib/api";
import { useToast } from "@/components/ui/Toast";
import { useAuth } from "@/hooks/useAuth";
import { useI18n } from "@/hooks/useI18n";
import { useRouter } from "next/navigation";
import { Clock, Camera, CheckCircle2, AlertTriangle, Globe, Check } from "lucide-react";
import { formatThaiTime } from "@/lib/thai-time";

const SESSION_LABELS: Record<number, { labelKey: string; time: string; icon: string }> = {
  1: { labelKey: "morning_shift", time: "09:00", icon: "🌅" },
  2: { labelKey: "noon_break_end", time: "12:00", icon: "☀️" },
  3: { labelKey: "afternoon_shift", time: "13:00", icon: "🕐" },
  4: { labelKey: "evening_shift", time: "18:00", icon: "🌇" },
};

const LANG_OPTIONS = [
  { code: "my", label: "缅甸语", native: "မြန်မာ" },
  { code: "th", label: "泰语", native: "ไทย" },
  { code: "zh", label: "中文", native: "中文" },
];

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
  const { t, locale, setLocale } = useI18n();
  const router = useRouter();
  const [completed, setCompleted] = useState<Record<number, any>>({});
  const [loading, setLoading] = useState<Record<number, boolean>>({});
  const [previewPhoto, setPreviewPhoto] = useState<string | null>(null);
  const [currentSession, setCurrentSession] = useState<number | null>(null);
  const [employeeInfo, setEmployeeInfo] = useState<any>(null);
  const [showLang, setShowLang] = useState(false);
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

  function triggerCamera(session: number) {
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
        headers: {
          Authorization: `Bearer ${getToken()}`,
          "X-Language": localStorage.getItem("locale") || "zh",
        },
        body: formData,
      });
      const r = await res.json();
      if (res.ok) {
        toast("success", r.message || t("clock_in_success"));
        setCurrentSession(null);
        setPreviewPhoto(null);
        loadToday();
      } else {
        toast("error", r.detail || t("clock_in_failed"));
      }
    } catch {
      toast("error", t("network_error"));
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
      {/* Language selector (top-right) */}
      <div className="relative flex justify-end pt-2">
        <button
          onClick={() => setShowLang(!showLang)}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-gray-200 bg-white text-gray-600 text-sm hover:bg-gray-50 min-h-[36px]"
        >
          <Globe size={16} />
          <span>{t("language")}</span>
        </button>
        {showLang && (
          <div className="absolute right-0 top-full mt-1 bg-white rounded-lg shadow-lg border w-40 py-1 z-50">
            {LANG_OPTIONS.map(opt => (
              <button
                key={opt.code}
                onClick={() => { setLocale(opt.code as any); setShowLang(false); }}
                className={`w-full text-left px-3 py-2 text-sm hover:bg-gray-50 flex items-center gap-2 min-h-[40px] ${
                  locale === opt.code ? "text-blue-600 font-medium" : "text-gray-700"
                }`}
              >
                <span className="flex-1">{opt.label}</span>
                <span className="text-xs text-gray-400">{opt.native}</span>
                {locale === opt.code && <Check size={14} className="text-blue-500" />}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Header */}
      <div className="text-center space-y-2">
        <h1 className="text-xl font-bold text-gray-800">{t("clock_page_title")}</h1>
        <p className="text-sm text-gray-500">{user?.display_name}</p>

        {/* Live clock - large for mobile */}
        <div className="inline-flex items-center gap-2 bg-blue-50 border border-blue-200 rounded-xl px-5 py-3">
          <Clock size={22} className="text-blue-500" />
          <span className="text-2xl font-mono font-bold text-blue-700">{formatThaiTime(thaiTime)}</span>
          <span className="text-xs text-blue-400 ml-1">{t("thailand")}</span>
        </div>
        <p className="text-sm text-gray-400">{t("clock_completed_today").replace("{count}", String(completedCount))}</p>
      </div>

      {/* Photo Preview Modal */}
      {previewPhoto && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4" onClick={cancelPhoto}>
          <div className="bg-white rounded-2xl w-full max-w-sm shadow-xl" onClick={e => e.stopPropagation()}>
            <div className="bg-blue-600 text-white px-5 py-3 rounded-t-2xl flex items-center gap-2">
              <Camera size={20} />
              <h3 className="font-semibold text-lg">{t("clock_photo_confirm")}</h3>
              <button onClick={cancelPhoto} className="ml-auto text-2xl text-blue-200">&times;</button>
            </div>
            <div className="p-4">
              <img src={previewPhoto} alt="打卡照片" className="w-full rounded-lg max-h-64 object-cover" />
              <p className="text-base text-gray-600 mt-3 text-center font-medium">
                {t(SESSION_LABELS[currentSession!]?.labelKey || "morning_shift")} · {formatThaiTime()}
              </p>
              <div className="flex gap-3 mt-4">
                <button onClick={cancelPhoto} className="flex-1 py-3 border rounded-xl text-base active:bg-gray-100">
                  {t("clock_retake")}
                </button>
                <button onClick={confirmClockIn} disabled={loading[currentSession!]}
                  className="flex-1 py-3 bg-blue-600 text-white rounded-xl text-base font-semibold active:bg-blue-700 disabled:opacity-50">
                  {loading[currentSession!] ? t("clock_submitting") : t("clock_confirm")}
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
          const isActive = loading[session];
          const info = SESSION_LABELS[session];

          return (
            <div key={session}
              className={`rounded-2xl border-2 transition-all ${
                done
                  ? "border-green-300 bg-green-50/50"
                  : "border-gray-200 bg-white active:border-blue-300"
              }`}>
              {/* Card body */}
              <div className="flex items-center gap-4 p-4">
                {/* Icon + label */}
                <div className="flex-shrink-0 w-12 h-12 rounded-xl flex items-center justify-center text-2xl"
                  style={{ background: done ? "#dcfce7" : "#eff6ff" }}>
                  {info.icon}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold text-gray-700">{t(info.labelKey)}</span>
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
                          <AlertTriangle size={12} /> {t("clock_late_half").replace("{amount}", String(penaltyHalf))}
                        </div>
                      )}
                      {done.status === "late_one" && (
                        <div className="text-xs text-red-500 flex items-center gap-1">
                          <AlertTriangle size={12} /> {t("clock_late_one").replace("{amount}", String(penaltyOne))}
                        </div>
                      )}
                    </div>
                  ) : (
                    <p className="text-xs text-gray-400 mt-1">{t("clock_tap_to_clock")}</p>
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
                    disabled={isActive}
                    className="flex-shrink-0 w-14 h-14 rounded-xl flex items-center justify-center text-white font-bold text-sm transition-all active:scale-95 bg-blue-600 hover:bg-blue-700 shadow-md shadow-blue-200 disabled:opacity-70"
                    title={t("clock_take_photo")}
                  >
                    <Camera size={22} />
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Legend */}
      <div className="text-center text-xs text-gray-400 pb-4 space-y-1">
        <p>{t("clock_anytime_hint")}</p>
        <p>{t("clock_late_rule").replace("{half}", String(penaltyHalf)).replace("{one}", String(penaltyOne))}</p>
        <p className="text-gray-300">{t("clock_daily_wage_hint").replace("{daily}", String(dailyWage)).replace("{rate}", String(hourlyRate))}</p>
      </div>
    </div>
  );
}

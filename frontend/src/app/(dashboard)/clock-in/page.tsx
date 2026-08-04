"use client";
import { useEffect, useState, useRef, useCallback } from "react";
import { api, getToken } from "@/lib/api";
import { useToast } from "@/components/ui/Toast";
import { useAuth } from "@/hooks/useAuth";
import { useRouter } from "next/navigation";
import { ClipboardCheck, Clock, Camera, CheckCircle2, AlertTriangle, Image, X } from "lucide-react";
import { formatThaiTime, formatThaiDate } from "@/lib/thai-time";

const SESSION_LABELS: Record<number, { label: string; time: string }> = {
  1: { label: "早上上班", time: "09:00" },
  2: { label: "中午休息结束", time: "12:00" },
  3: { label: "下午上班", time: "13:00" },
  4: { label: "下午下班", time: "18:00" },
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
  const cameraInputRef = useRef<HTMLInputElement>(null);
  const thaiTime = useThaiClock();

  useEffect(() => {
    if (!getToken()) { router.push("/login"); return; }
    loadToday();
  }, []);

  async function loadToday() {
    try {
      const r = await api.get<any>("/clock-in/today");
      setCompleted(r.completed || {});
    } catch {}
  }

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
      const token = getToken();
      const res = await fetch("/api/v1/clock-in", {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
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

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      {/* Header with live clock */}
      <div className="text-center space-y-3">
        <div className="mx-auto w-16 h-16 bg-blue-100 rounded-full flex items-center justify-center">
          <ClipboardCheck size={32} className="text-blue-600" />
        </div>
        <h1 className="text-2xl font-bold text-gray-800">打卡签到</h1>
        <p className="text-gray-500">{user?.display_name}，{formatThaiDate(thaiTime)}</p>

        {/* Live Thailand clock */}
        <div className="inline-flex items-center gap-2 bg-blue-50 border border-blue-200 rounded-xl px-4 py-2">
          <Clock size={18} className="text-blue-500" />
          <span className="text-xl font-mono font-bold text-blue-700">{formatThaiTime(thaiTime)}</span>
          <span className="text-xs text-blue-400">泰国时间</span>
        </div>
      </div>

      {/* Photo Preview Modal */}
      {previewPhoto && (
        <div className="modal-overlay z-50" onClick={cancelPhoto}>
          <div className="bg-white rounded-2xl w-[400px] shadow-2xl" onClick={e => e.stopPropagation()}>
            <div className="bg-blue-600 text-white px-5 py-3 rounded-t-2xl flex items-center gap-2">
              <Camera size={18} />
              <h3 className="font-semibold">打卡拍照确认</h3>
              <button onClick={cancelPhoto} className="ml-auto text-blue-200 hover:text-white">&times;</button>
            </div>
            <div className="p-4">
              <img src={previewPhoto} alt="打卡照片" className="w-full rounded-lg max-h-64 object-cover" />
              <p className="text-sm text-gray-500 mt-2 text-center">
                {SESSION_LABELS[currentSession!]?.label} 打卡 · 泰国时间 {formatThaiTime()}
              </p>
              <div className="flex gap-3 mt-4">
                <button onClick={cancelPhoto} className="flex-1 py-2 border rounded-lg text-sm">重新拍照</button>
                <button onClick={confirmClockIn}
                  disabled={loading[currentSession!]}
                  className="flex-1 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium disabled:opacity-50">
                  {loading[currentSession!] ? "提交中..." : "确认打卡"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      <input ref={cameraInputRef} type="file" accept="image/*" capture="environment"
        onChange={handlePhotoSelected} className="hidden" />

      {/* 4 Clock-in Buttons */}
      <div className="grid grid-cols-2 gap-4">
        {[1, 2, 3, 4].map(session => {
          const done = completed[session];
          const isActive = loading[session];
          return (
            <div key={session}
              className={`rounded-2xl border-2 p-5 text-center transition-all ${
                done ? "border-green-200 bg-green-50" : "border-gray-200 bg-white hover:border-blue-300 hover:shadow-sm"
              }`}>
              <div className="text-sm text-gray-500 mb-1">{SESSION_LABELS[session].label}</div>
              <div className="text-2xl font-bold text-gray-700 mb-3">{SESSION_LABELS[session].time}</div>

              {done ? (
                <div className="space-y-1">
                  <div className="flex items-center justify-center gap-1 text-green-600">
                    <CheckCircle2 size={16} />
                    <span className="text-sm font-medium">已打卡</span>
                  </div>
                  <div className="text-xs text-gray-400">
                    {new Date(done.clocked_in_at).toLocaleTimeString("zh-CN", { timeZone: "Asia/Bangkok" })}
                  </div>
                  {done.status === "late_half" && (
                    <div className="text-xs text-orange-500 flex items-center justify-center gap-1 mt-1">
                      <AlertTriangle size={12} />迟到（月底结算扣款）
                    </div>
                  )}
                  {done.status === "late_one" && (
                    <div className="text-xs text-red-500 flex items-center justify-center gap-1 mt-1">
                      <AlertTriangle size={12} />严重迟到（月底结算扣款）
                    </div>
                  )}
                  {done.photo_path && (
                    <img src={`/${done.photo_path}`} alt="打卡照" className="mt-2 w-full h-20 object-cover rounded-lg" />
                  )}
                </div>
              ) : (
                <button
                  onClick={() => triggerCamera(session)}
                  disabled={isActive}
                  className="w-full py-3 bg-blue-600 text-white rounded-xl font-medium hover:bg-blue-700 disabled:opacity-50 flex items-center justify-center gap-2 shadow-md shadow-blue-200 transition-all"
                >
                  <Camera size={18} />
                  {isActive ? "提交中..." : "拍照打卡"}
                </button>
              )}
            </div>
          );
        })}
      </div>

      {/* Legend */}
      <div className="text-center text-xs text-gray-400 space-y-1">
        <p>早上9:05前打卡正常，9:05-9:30迟到扣半小时，9:31后扣一小时（按日薪折算）</p>
        <p>各时段仅限窗口时间内打卡，其他时段记录时间无惩罚</p>
      </div>
    </div>
  );
}

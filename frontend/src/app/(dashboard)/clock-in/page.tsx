"use client";
import { useEffect, useState } from "react";
import { api, getToken } from "@/lib/api";
import { useToast } from "@/components/ui/Toast";
import { useAuth } from "@/hooks/useAuth";
import { useRouter } from "next/navigation";
import { ClipboardCheck, Clock, CheckCircle2 } from "lucide-react";

export default function ClockInPage() {
  const { toast } = useToast(); const { user } = useAuth(); const router = useRouter();
  const [todayRecord, setTodayRecord] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => { if (!getToken()) router.push("/login"); loadToday(); }, []);

  async function loadToday() {
    try {
      const r = await api.get<any>("/clock-in/today");
      setTodayRecord(r.clocked_in_at || null);
    } catch {}
  }

  async function handleClockIn() {
    setLoading(true);
    try {
      const r = await api.post<any>("/clock-in", {});
      toast("success", r.message || "打卡成功");
      loadToday();
    } catch (err: any) { toast("error", err.message || "打卡失败"); }
    setLoading(false);
  }

  return (
    <div className="flex flex-col items-center justify-center min-h-[70vh]">
      <div className="text-center space-y-6 max-w-md">
        <div className="mx-auto w-20 h-20 bg-blue-100 rounded-full flex items-center justify-center">
          <ClipboardCheck size={40} className="text-blue-600" />
        </div>
        <h1 className="text-2xl font-bold text-gray-800">打卡签到</h1>
        <p className="text-gray-500">
          {user?.display_name}，{todayRecord ? "今日已打卡" : "请点击下方按钮签到"}
        </p>

        {todayRecord ? (
          <div className="bg-green-50 border border-green-200 rounded-xl p-6 space-y-2">
            <CheckCircle2 size={48} className="text-green-500 mx-auto" />
            <p className="text-green-700 font-medium">今日已打卡</p>
            <p className="text-green-600 text-sm">打卡时间: {new Date(todayRecord).toLocaleTimeString("zh-CN")}</p>
          </div>
        ) : (
          <button
            onClick={handleClockIn}
            disabled={loading}
            className="w-full py-4 bg-blue-600 text-white rounded-2xl text-lg font-semibold hover:bg-blue-700 disabled:opacity-50 flex items-center justify-center gap-2 shadow-lg shadow-blue-200"
          >
            <Clock size={24} />
            {loading ? "打卡中..." : "签到打卡"}
          </button>
        )}
      </div>
    </div>
  );
}

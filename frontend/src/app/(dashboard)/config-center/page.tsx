"use client";
import { useEffect, useState } from "react";
import { api, getToken } from "@/lib/api";
import { useToast } from "@/components/ui/Toast";
import { useRouter } from "next/navigation";
import { SlidersHorizontal, Clock, ShieldCheck } from "lucide-react";

const DEFAULTS = {
  morning_start: "09:00",
  late_half: "09:05",
  late_one: "09:31",
  noon_break_start: "12:00",
  noon_break_end: "13:00",
  early_one: "17:00",
  early_half: "17:30",
  afternoon_end: "18:00",
  overtime_limit: "50",
};

export default function ConfigCenterPage() {
  const { toast } = useToast();
  const router = useRouter();
  const [form, setForm] = useState({ ...DEFAULTS });
  const [editable, setEditable] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!getToken()) { router.push("/login"); return; }
    load();
  }, []);

  async function load() {
    try {
      const r = await api.get<any>("/config/work-schedule");
      setForm({
        morning_start: r.morning_start || DEFAULTS.morning_start,
        late_half: r.late_half || DEFAULTS.late_half,
        late_one: r.late_one || DEFAULTS.late_one,
        noon_break_start: r.noon_break_start || DEFAULTS.noon_break_start,
        noon_break_end: r.noon_break_end || DEFAULTS.noon_break_end,
        early_one: r.early_one || DEFAULTS.early_one,
        early_half: r.early_half || DEFAULTS.early_half,
        afternoon_end: r.afternoon_end || DEFAULTS.afternoon_end,
        overtime_limit: r.overtime_limit != null ? String(r.overtime_limit) : DEFAULTS.overtime_limit,
      });
      setEditable(!!r.editable);
    } catch (err: any) { toast("error", err.message || "加载配置失败"); }
  }

  async function save() {
    setSaving(true);
    try {
      await api.put("/config/work-schedule", {
        ...form,
        overtime_limit: parseFloat(form.overtime_limit) || 0,
      });
      toast("success", "作息设置已保存");
      load();
    } catch (err: any) { toast("error", err.message || "保存失败"); }
    setSaving(false);
  }

  const timeField = (label: string, key: string) => (
    <div>
      <label className="form-label text-xs">{label}</label>
      <input type="time" className="form-input text-sm" value={(form as any)[key]}
        disabled={!editable}
        onChange={e => setForm({ ...form, [key]: e.target.value })} />
    </div>
  );

  return (
    <div className="max-w-3xl space-y-6">
      <div className="mb-2">
        <h1 className="page-title flex items-center gap-2"><SlidersHorizontal size={24}/> 配置中心</h1>
        <p className="text-sm text-gray-400 mt-1">每个仓库单独配置，切换仓库后显示对应仓库的值</p>
      </div>

      {/* 第一组：仓库作息 */}
      <div className="bg-white rounded-xl p-5 shadow-sm">
        <h3 className="font-semibold mb-3 flex items-center gap-2"><Clock size={18} className="text-indigo-500"/> 仓库作息</h3>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
          {timeField("早上上班时间", "morning_start")}
          {timeField("迟到半小时红线", "late_half")}
          {timeField("迟到1小时红线", "late_one")}
          {timeField("中午休息开始", "noon_break_start")}
          {timeField("中午休息结束", "noon_break_end")}
          {timeField("早退1小时红线", "early_one")}
          {timeField("早退半小时红线", "early_half")}
          {timeField("下午下班时间", "afternoon_end")}
          <div>
            <label className="form-label text-xs">加班月度上限（小时/月）</label>
            <input type="number" step="1" min="0" className="form-input text-sm" value={form.overtime_limit}
              disabled={!editable}
              onChange={e => setForm({ ...form, overtime_limit: e.target.value })} />
          </div>
        </div>
        <div className="text-xs text-gray-400 mt-3">顺序：上班 &lt; 迟到半小时 &lt; 迟到1小时 &lt; 午休开始 &lt; 午休结束 &lt; 早退1小时 &lt; 早退半小时 &lt; 下班</div>
        {!editable && <div className="text-xs text-gray-400 mt-2">仅仓库管理员可修改</div>}
        {editable && (
          <button onClick={save} disabled={saving} className="btn-primary mt-4">
            {saving ? "保存中..." : "保存作息"}
          </button>
        )}
      </div>

      {/* 第二组：审批门槛（占位） */}
      <div className="bg-white rounded-xl p-5 shadow-sm">
        <h3 className="font-semibold mb-3 flex items-center gap-2"><ShieldCheck size={18} className="text-blue-500"/> 审批门槛</h3>
        <div className="text-sm text-gray-300 py-4 text-center">待开放</div>
      </div>
    </div>
  );
}

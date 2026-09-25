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

const THRESHOLD_DEFAULTS = { expense: "0", purchase: "0", concentration: "70" };

export default function ConfigCenterPage() {
  const { toast } = useToast();
  const router = useRouter();
  const [form, setForm] = useState({ ...DEFAULTS });
  const [thresholds, setThresholds] = useState({ ...THRESHOLD_DEFAULTS });
  const [editable, setEditable] = useState(false);
  const [saving, setSaving] = useState(false);
  const [savingThresholds, setSavingThresholds] = useState(false);

  useEffect(() => {
    if (!getToken()) { router.push("/login"); return; }
    load();
    loadThresholds();
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

  async function loadThresholds() {
    const res: any = { ...THRESHOLD_DEFAULTS };
    try {
      const r = await api.get<any>("/expense-approvals/threshold");
      res.expense = String(r.threshold ?? 0);
    } catch {}
    try {
      const r = await api.get<any>("/suppliers/purchase-approval-threshold");
      res.purchase = String(r.threshold ?? 0);
    } catch {}
    try {
      const r = await api.get<any>("/suppliers/concentration-threshold");
      res.concentration = String(r.threshold ?? 70);
    } catch {}
    setThresholds(res);
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

  async function saveThresholds() {
    setSavingThresholds(true);
    try {
      await api.put("/expense-approvals/threshold", { threshold: parseFloat(thresholds.expense) || 0 });
      await api.put("/suppliers/purchase-approval-threshold", { threshold: parseFloat(thresholds.purchase) || 0 });
      await api.put("/suppliers/concentration-threshold", { threshold: parseFloat(thresholds.concentration) || 0 });
      toast("success", "审批门槛已保存");
      loadThresholds();
    } catch (err: any) { toast("error", err.message || "保存失败"); }
    setSavingThresholds(false);
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

      {/* 第二组：审批门槛 */}
      <div className="bg-white rounded-xl p-5 shadow-sm">
        <h3 className="font-semibold mb-3 flex items-center gap-2"><ShieldCheck size={18} className="text-blue-500"/> 审批门槛</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div>
            <label className="form-label text-xs">费用审批门槛（泰铢）</label>
            <input type="number" step="1" min="0" className="form-input text-sm" value={thresholds.expense}
              disabled={!editable}
              onChange={e => setThresholds({ ...thresholds, expense: e.target.value })} />
            <p className="text-xs text-gray-400 mt-1">0 表示全部都走审批</p>
          </div>
          <div>
            <label className="form-label text-xs">采购审批门槛（泰铢）</label>
            <input type="number" step="1" min="0" className="form-input text-sm" value={thresholds.purchase}
              disabled={!editable}
              onChange={e => setThresholds({ ...thresholds, purchase: e.target.value })} />
            <p className="text-xs text-gray-400 mt-1">0 表示不需要审批</p>
          </div>
          <div>
            <label className="form-label text-xs">集中度预警阈值（%）</label>
            <input type="number" step="1" min="0" max="100" className="form-input text-sm" value={thresholds.concentration}
              disabled={!editable}
              onChange={e => setThresholds({ ...thresholds, concentration: e.target.value })} />
            <p className="text-xs text-gray-400 mt-1">超过这个比例会红色预警</p>
          </div>
        </div>
        {!editable && <div className="text-xs text-gray-400 mt-2">仅仓库管理员可修改</div>}
        {editable && (
          <button onClick={saveThresholds} disabled={savingThresholds} className="btn-primary mt-4">
            {savingThresholds ? "保存中..." : "保存审批门槛"}
          </button>
        )}
      </div>
    </div>
  );
}

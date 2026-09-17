"use client";
import { useEffect, useState, useCallback } from "react";
import { api, getToken } from "@/lib/api";
import { useToast } from "@/components/ui/Toast";
import { useRouter } from "next/navigation";
import { Gauge, Clock, Users, Package, TrendingUp, ChevronLeft, ChevronRight, Save, AlertTriangle, CheckCircle2, DollarSign, Percent } from "lucide-react";
import { thaiNow } from "@/lib/thai-time";

const WEEKDAYS = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"];

function toDateStr(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function currentMonday(): string {
  const now = thaiNow();
  const diff = (now.getDay() + 6) % 7; // 距周一的天数
  const monday = new Date(now);
  monday.setDate(monday.getDate() - diff);
  return toDateStr(monday);
}

function currentMonth(): string {
  const now = thaiNow();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

function addDays(dateStr: string, days: number): string {
  const [y, m, d] = dateStr.split("-").map(Number);
  const dt = new Date(y, m - 1, d);
  dt.setDate(dt.getDate() + days);
  return toDateStr(dt);
}

function addMonths(monthStr: string, delta: number): string {
  const [y, m] = monthStr.split("-").map(Number);
  const dt = new Date(y, m - 1 + delta, 1);
  return `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, "0")}`;
}

function buildMonthDays(monthStr: string): { date: string | null; day: number }[] {
  const [y, m] = monthStr.split("-").map(Number);
  const first = new Date(y, m - 1, 1);
  const daysInMonth = new Date(y, m, 0).getDate();
  const lead = first.getDay(); // 0=周日
  const cells: { date: string | null; day: number }[] = [];
  for (let i = 0; i < lead; i++) cells.push({ date: null, day: 0 });
  for (let d = 1; d <= daysInMonth; d++) {
    cells.push({ date: `${monthStr}-${String(d).padStart(2, "0")}`, day: d });
  }
  return cells;
}

function weekdayLabel(dateStr: string): string {
  const [y, m, d] = dateStr.split("-").map(Number);
  const dt = new Date(y, m - 1, d);
  return `${WEEKDAYS[dt.getDay()]} ${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
}

function fmt(n: any, digits = 1): string {
  const v = Number(n);
  if (isNaN(v)) return (0).toFixed(digits);
  return v.toFixed(digits);
}

function shortDate(dateStr: string): string {
  return dateStr.slice(5); // MM-DD
}

function TrendChart({ data }: { data: any[] }) {
  const [hover, setHover] = useState<number | null>(null);
  if (!data || data.length === 0) {
    return <div className="text-gray-400 text-sm py-8 text-center">暂无趋势数据</div>;
  }

  const W = 800, H = 240;
  const padL = 46, padR = 16, padT = 16, padB = 30;
  const innerW = W - padL - padR;
  const innerH = H - padT - padB;

  const vals = data.map((d: any) => Number(d.efficiency) || 0);
  const maxVal = Math.max(...vals);
  const minVal = Math.min(...vals);
  const range = maxVal - minVal || 1;
  const yMax = maxVal + range * 0.15;
  const yMin = Math.max(0, minVal - range * 0.15);

  const x = (i: number) => data.length === 1 ? padL + innerW / 2 : padL + (i / (data.length - 1)) * innerW;
  const y = (v: number) => padT + (1 - (v - yMin) / (yMax - yMin)) * innerH;

  const points = data.map((d: any, i: number) => ({ x: x(i), y: y(Number(d.efficiency) || 0), ...d }));
  const linePath = points.map((p, i) => (i === 0 ? `M ${p.x.toFixed(1)} ${p.y.toFixed(1)}` : `L ${p.x.toFixed(1)} ${p.y.toFixed(1)}`)).join(" ");

  // y-axis ticks (4)
  const ticks = [0, 1, 2, 3, 4].map(t => yMin + (t / 4) * (yMax - yMin));

  const colW = data.length > 1 ? innerW / (data.length - 1) : innerW;
  const hp = hover != null ? points[hover] : null;

  return (
    <div className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto"
        onMouseLeave={() => setHover(null)}>
        {/* grid + y labels */}
        {ticks.map((t, i) => (
          <g key={i}>
            <line x1={padL} x2={W - padR} y1={y(t)} y2={y(t)} stroke="#f0f0f0" strokeWidth={1} />
            <text x={padL - 6} y={y(t) + 3} textAnchor="end" fontSize={10} fill="#9ca3af">{Math.round(t)}</text>
          </g>
        ))}
        {/* x labels (every other) */}
        {points.map((p, i) => (
          i % 2 === 0 ? (
            <text key={i} x={p.x} y={H - 8} textAnchor="middle" fontSize={10} fill="#9ca3af">{shortDate(p.week_start)}</text>
          ) : null
        ))}
        {/* line */}
        <path d={linePath} fill="none" stroke="#2563eb" strokeWidth={2} />
        {/* points */}
        {points.map((p, i) => (
          <circle key={i} cx={p.x} cy={p.y} r={hover === i ? 5 : 3.2} fill="#2563eb" />
        ))}
        {/* hover vertical guide */}
        {hp && <line x1={hp.x} x2={hp.x} y1={padT} y2={H - padB} stroke="#2563eb" strokeWidth={1} strokeDasharray="3 3" />}
        {/* hover capture columns */}
        {points.map((p, i) => (
          <rect key={`r${i}`} x={p.x - colW / 2} y={padT} width={colW} height={innerH} fill="transparent"
            onMouseEnter={() => setHover(i)} />
        ))}
      </svg>
      {/* tooltip */}
      {hp && (
        <div className="absolute pointer-events-none bg-slate-800 text-white text-xs rounded-lg px-3 py-2 shadow-lg whitespace-nowrap z-10"
          style={{
            left: `${(hp.x / W) * 100}%`,
            top: `${(hp.y / H) * 100}%`,
            transform: "translate(-50%, -110%)",
          }}>
          <div className="font-semibold">{hp.week_start} ~ {hp.week_end}</div>
          <div>人效 {fmt(hp.efficiency)} 单/人次</div>
          <div>订单 {hp.order_count ?? 0} · 人次 {fmt(hp.person_times)}</div>
        </div>
      )}
    </div>
  );
}

function MonthStdCell({ label, value, onSave }: { label: string; value: number; onSave: (v: number) => void }) {
  const [draft, setDraft] = useState(String(value));
  useEffect(() => { setDraft(String(value)); }, [value]);
  return (
    <div className="border rounded-lg p-2">
      <div className="text-xs text-gray-500">{label}</div>
      <input
        type="number" min={0} step="any" value={draft}
        onChange={e => setDraft(e.target.value)}
        onBlur={() => {
          const v = parseFloat(draft);
          if (!isNaN(v) && v >= 0 && v !== value) onSave(v);
        }}
        onKeyDown={e => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }}
        className="w-full border rounded px-2 py-1 text-sm mt-1"
      />
    </div>
  );
}

export default function LaborEfficiencyPage() {
  const { toast } = useToast();
  const router = useRouter();
  const [view, setView] = useState<"week" | "month">("week");
  const [weekStart, setWeekStart] = useState<string>("");
  const [month, setMonth] = useState<string>("");
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [orderCalMonth, setOrderCalMonth] = useState<string>(currentMonth());
  const [dailyOrders, setDailyOrders] = useState<Record<string, number>>({});
  const [orderModal, setOrderModal] = useState<{ date: string; current: number | null } | null>(null);
  const [orderModalInput, setOrderModalInput] = useState("");
  const [orderModalSaving, setOrderModalSaving] = useState(false);
  const [stdInput, setStdInput] = useState("450");
  const [stdSaving, setStdSaving] = useState(false);
  const [suppModal, setSuppModal] = useState<{ employee_id: number; name: string; date: string; current: number | null } | null>(null);
  const [suppInput, setSuppInput] = useState("");
  const [suppSaving, setSuppSaving] = useState(false);
  const [trend, setTrend] = useState<any[]>([]);
  const [compareData, setCompareData] = useState<any[]>([]);
  const [standards, setStandards] = useState<{ default: number; monthly: Record<string, number> }>({ default: 450, monthly: {} });
  const [stdYear, setStdYear] = useState<string>(currentMonth().slice(0, 4));

  useEffect(() => {
    if (!getToken()) { router.push("/login"); return; }
    setWeekStart(currentMonday());
    setMonth(currentMonth());
    setStdYear(currentMonth().slice(0, 4));
    api.get<any>("/efficiency/trend?weeks=12").then(r => setTrend(r.weeks || [])).catch(() => {});
    api.get<any>("/efficiency/standards").then(r => setStandards({ default: r.default ?? 450, monthly: r.monthly || {} })).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = view === "week" ? `view=week&week_start=${weekStart}` : `view=month&month=${month}`;
      const r = await api.get<any>(`/efficiency/summary?${params}`);
      setData(r);
      setStdInput(r.standard != null ? String(r.standard) : "450");
      api.get<any>(`/efficiency/compare?${params}`).then(c => setCompareData(c.warehouses || [])).catch(() => {});
    } catch (e: any) {
      toast("error", e.message || "加载失败");
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view, weekStart, month]);

  useEffect(() => {
    if (view === "week" && !weekStart) return;
    if (view === "month" && !month) return;
    load();
  }, [view, weekStart, month, load]);

  const loadDailyOrders = useCallback(async () => {
    try {
      const r = await api.get<any>(`/efficiency/daily-orders?month=${orderCalMonth}`);
      setDailyOrders(r.daily || {});
    } catch {}
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [orderCalMonth]);

  useEffect(() => {
    if (orderCalMonth) loadDailyOrders();
  }, [orderCalMonth, loadDailyOrders]);

  function openOrderModal(date: string) {
    setOrderModal({ date, current: dailyOrders[date] ?? null });
    setOrderModalInput(dailyOrders[date] != null ? String(dailyOrders[date]) : "");
  }

  async function saveDailyOrder() {
    if (!orderModal) return;
    const val = parseInt(orderModalInput, 10);
    if (isNaN(val) || val < 0) { toast("error", "请输入有效的订单数"); return; }
    setOrderModalSaving(true);
    try {
      await api.put("/efficiency/order-count", { date: orderModal.date, order_count: val });
      toast("success", "订单数已保存");
      setOrderModal(null);
      await loadDailyOrders();
      await load();
    } catch (e: any) {
      toast("error", e.message || "保存失败");
    } finally {
      setOrderModalSaving(false);
    }
  }

  const stdMonth = view === "week" ? (weekStart ? weekStart.slice(0, 7) : "") : month;

  async function saveStandard() {
    const val = parseFloat(stdInput);
    if (isNaN(val) || val < 0) { toast("error", "请输入有效的标准值"); return; }
    setStdSaving(true);
    try {
      await api.put("/efficiency/standard", { standard: val, month: stdMonth || undefined });
      toast("success", `${stdMonth || "默认"} 标准已保存`);
      setStandards(prev => ({ ...prev, monthly: { ...prev.monthly, [stdMonth]: val } }));
      await load();
    } catch (e: any) {
      toast("error", e.message || "保存失败");
    } finally {
      setStdSaving(false);
    }
  }

  async function saveMonthStd(monthKey: string, v: number) {
    try {
      await api.put("/efficiency/standard", { standard: v, month: monthKey });
      toast("success", `${monthKey} 标准已设为 ${v}`);
      setStandards(prev => ({ ...prev, monthly: { ...prev.monthly, [monthKey]: v } }));
      if (monthKey === stdMonth) await load();
    } catch (e: any) {
      toast("error", e.message || "保存失败");
    }
  }

  async function saveDefaultStd(v: number) {
    try {
      await api.put("/efficiency/standard", { standard: v });
      toast("success", `默认标准已设为 ${v}`);
      setStandards(prev => ({ ...prev, default: v }));
      await load();
    } catch (e: any) {
      toast("error", e.message || "保存失败");
    }
  }

  function openSupplement(emp: any, day: any) {
    setSuppModal({ employee_id: emp.employee_id, name: emp.name, date: day.date, current: day.hours ?? null });
    setSuppInput(day.hours != null ? String(day.hours) : "");
  }

  async function saveSupplement() {
    if (!suppModal) return;
    const val = parseFloat(suppInput);
    if (isNaN(val) || val < 0) { toast("error", "请输入有效的工时小时数"); return; }
    setSuppSaving(true);
    try {
      await api.put("/efficiency/manual-hour", { employee_id: suppModal.employee_id, date: suppModal.date, hours: val });
      toast("success", "补录已保存");
      setSuppModal(null);
      await load();
    } catch (e: any) {
      toast("error", e.message || "保存失败");
    } finally {
      setSuppSaving(false);
    }
  }

  async function clearSupplement() {
    if (!suppModal) return;
    setSuppSaving(true);
    try {
      await api.delete(`/efficiency/manual-hour?employee_id=${suppModal.employee_id}&date=${suppModal.date}`);
      toast("success", "已清除补录");
      setSuppModal(null);
      await load();
    } catch (e: any) {
      toast("error", e.message || "清除失败");
    } finally {
      setSuppSaving(false);
    }
  }

  const below = data?.below_standard;

  return (
    <div className="max-w-6xl mx-auto space-y-5 p-1">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center gap-3">
        <div>
          <h1 className="text-xl font-bold text-gray-800 flex items-center gap-2">
            <Gauge size={22} className="text-blue-600" /> 人效管理
          </h1>
          <p className="text-sm text-gray-500 mt-0.5">
            {data?.period_label || ""}
            {data?.pending_days > 0 && <span className="ml-2 text-orange-500">· {data.pending_days} 天待补</span>}
          </p>
        </div>

        <div className="sm:ml-auto flex items-center gap-2 flex-wrap">
          {/* 周/月切换 */}
          <div className="flex rounded-lg border overflow-hidden">
            <button
              onClick={() => setView("week")}
              className={`px-3 py-2 text-sm ${view === "week" ? "bg-blue-600 text-white" : "bg-white text-gray-600 hover:bg-gray-50"}`}
            >
              按周
            </button>
            <button
              onClick={() => setView("month")}
              className={`px-3 py-2 text-sm ${view === "month" ? "bg-blue-600 text-white" : "bg-white text-gray-600 hover:bg-gray-50"}`}
            >
              按月
            </button>
          </div>

          {/* 周期切换 */}
          <div className="flex items-center gap-1">
            <button
              onClick={() => view === "week" ? setWeekStart(addDays(weekStart, -7)) : setMonth(addMonths(month, -1))}
              className="p-2 border rounded-lg hover:bg-gray-50 min-w-[40px]"
            >
              <ChevronLeft size={18} />
            </button>
            <button
              onClick={() => view === "week" ? setWeekStart(currentMonday()) : setMonth(currentMonth())}
              className="px-2 py-2 text-sm border rounded-lg hover:bg-gray-50"
            >
              {view === "week" ? "本周" : "本月"}
            </button>
            <button
              onClick={() => view === "week" ? setWeekStart(addDays(weekStart, 7)) : setMonth(addMonths(month, 1))}
              className="p-2 border rounded-lg hover:bg-gray-50 min-w-[40px]"
            >
              <ChevronRight size={18} />
            </button>
          </div>
        </div>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
        <div className="bg-white rounded-xl border p-4">
          <div className="flex items-center gap-2 text-gray-500 text-sm"><Clock size={16} /> 总工时</div>
          <div className="text-2xl font-bold text-gray-800 mt-2">{fmt(data?.total_hours)}h</div>
          <div className="text-xs text-gray-400 mt-1">正常 {fmt(data?.regular_hours)}h</div>
        </div>
        <div className="bg-white rounded-xl border p-4">
          <div className="flex items-center gap-2 text-gray-500 text-sm"><Users size={16} /> 人次</div>
          <div className="text-2xl font-bold text-gray-800 mt-2">{fmt(data?.person_times)}</div>
          <div className="text-xs text-gray-400 mt-1">总工时 ÷ 8</div>
        </div>
        <div className="bg-white rounded-xl border p-4">
          <div className="flex items-center gap-2 text-gray-500 text-sm"><Package size={16} /> 订单数</div>
          <div className="text-2xl font-bold text-gray-800 mt-2">{data?.order_count ?? 0}</div>
          <div className="text-xs text-gray-400 mt-1">{view === "week" ? "本周订单" : "当月累计订单"}</div>
        </div>
        <div className={`rounded-xl border p-4 ${below ? "bg-red-50 border-red-200" : "bg-green-50 border-green-200"}`}>
          <div className={`flex items-center gap-2 text-sm ${below ? "text-red-600" : "text-green-700"}`}>
            {below ? <AlertTriangle size={16} /> : <CheckCircle2 size={16} />} 人效
          </div>
          <div className={`text-2xl font-bold mt-2 ${below ? "text-red-600" : "text-green-700"}`}>{fmt(data?.efficiency)}</div>
          <div className={`text-xs mt-1 ${below ? "text-red-500" : "text-green-600"}`}>
            标准 ≥ {fmt(data?.standard, 0)} · {below ? "低于标准" : "达标"}
          </div>
        </div>
        <div className="bg-white rounded-xl border p-4">
          <div className="flex items-center gap-2 text-gray-500 text-sm"><DollarSign size={16} /> 每单人工成本</div>
          <div className="text-2xl font-bold text-gray-800 mt-2">每单 {fmt(data?.cost_per_order, 2)} 铢</div>
          <div className="text-xs text-gray-400 mt-1">人工成本 ÷ 订单数</div>
        </div>
        <div className="bg-white rounded-xl border p-4">
          <div className="flex items-center gap-2 text-gray-500 text-sm"><Clock size={16} /> 加班工时</div>
          <div className="text-2xl font-bold text-gray-800 mt-2">{fmt(data?.overtime_hours)}h</div>
          <div className="text-xs text-gray-400 mt-1">已确认加班时长</div>
        </div>
        <div className="bg-white rounded-xl border p-4">
          <div className="flex items-center gap-2 text-gray-500 text-sm"><Percent size={16} /> 加班占比</div>
          <div className="text-2xl font-bold text-gray-800 mt-2">{fmt(data?.overtime_ratio)}%</div>
          <div className="text-xs text-gray-400 mt-1">加班工时 ÷ 总工时</div>
        </div>
      </div>

      {/* Trend chart */}
      <div className="bg-white rounded-xl border p-4">
        <div className="flex items-center justify-between mb-2">
          <h2 className="font-semibold text-gray-700">人效趋势（最近 12 周）</h2>
          <span className="text-xs text-gray-400">纵轴：每人次单数</span>
        </div>
        <TrendChart data={trend} />
      </div>

      {/* Daily order entry calendar + standard config */}
      <div className="grid lg:grid-cols-3 gap-3">
        <div className="lg:col-span-2 bg-white rounded-xl border p-4">
          <div className="flex items-center justify-between flex-wrap gap-2 mb-3">
            <div className="flex items-center gap-2 text-gray-700 font-medium">
              <TrendingUp size={16} className="text-blue-600" /> 订单数录入（按天）
            </div>
            <div className="flex items-center gap-1">
              <button onClick={() => setOrderCalMonth(addMonths(orderCalMonth, -1))} className="p-1.5 border rounded hover:bg-gray-50 min-w-[32px]"><ChevronLeft size={16} /></button>
              <span className="text-sm font-medium w-20 text-center">{orderCalMonth}</span>
              <button onClick={() => setOrderCalMonth(addMonths(orderCalMonth, 1))} className="p-1.5 border rounded hover:bg-gray-50 min-w-[32px]"><ChevronRight size={16} /></button>
            </div>
          </div>
          <p className="text-xs text-gray-400 mb-3">点击某天录入/修改当天订单数，未录入的天按 0 计算。</p>
          <div className="grid grid-cols-7 gap-1 text-center text-xs">
            {["日", "一", "二", "三", "四", "五", "六"].map((w, i) => (
              <div key={i} className="text-gray-400 py-1">{w}</div>
            ))}
            {buildMonthDays(orderCalMonth).map((cell, i) => (
              cell.date ? (
                <button key={i} onClick={() => openOrderModal(cell.date!)}
                  className="min-h-[52px] border rounded-lg p-1 flex flex-col items-center justify-center hover:border-blue-300 hover:bg-blue-50/40 bg-white">
                  <span className="text-gray-600">{cell.day}</span>
                  {dailyOrders[cell.date!] != null ? (
                    <span className="text-blue-600 font-semibold text-xs mt-0.5">{dailyOrders[cell.date!]}</span>
                  ) : (
                    <span className="text-gray-300 text-[10px] mt-0.5">-</span>
                  )}
                </button>
              ) : (
                <div key={i} className="min-h-[52px]"></div>
              )
            ))}
          </div>
        </div>
        <div className="bg-white rounded-xl border p-4">
          <div className="flex items-center gap-2 text-gray-700 font-medium"><Gauge size={16} className="text-amber-500" /> 当前标准（{stdMonth || "默认"}）</div>
          <p className="text-xs text-gray-400 mt-1">设置 {stdMonth || "默认"} 的人效标准，低于该值显示红色，达标显示绿色。</p>
          <div className="flex gap-2 mt-3">
            <input
              type="number"
              min={0}
              step="any"
              value={stdInput}
              onChange={e => setStdInput(e.target.value)}
              className="flex-1 border rounded-lg px-3 py-2 text-sm"
              placeholder="默认 450"
            />
            <button
              onClick={saveStandard}
              disabled={stdSaving}
              className="px-4 py-2 bg-amber-500 text-white rounded-lg text-sm flex items-center gap-1 disabled:opacity-50"
            >
              <Save size={16} /> {stdSaving ? "保存中" : "保存"}
            </button>
          </div>
        </div>
      </div>

      {/* Cross-check (订单数交叉校验) */}
      {view === "week" && data?.cross_check && (
        <div className={`rounded-xl border p-4 ${
          data.cross_check.status === "warning" ? "bg-orange-50 border-orange-200" :
          data.cross_check.status === "ok" ? "bg-green-50 border-green-200" : "bg-gray-50 border-gray-200"
        }`}>
          <div className="flex items-center gap-2">
            {data.cross_check.status === "warning" ? <AlertTriangle size={18} className="text-orange-500" /> :
             data.cross_check.status === "ok" ? <CheckCircle2 size={18} className="text-green-600" /> :
             <Percent size={18} className="text-gray-400" />}
            <span className="font-medium text-gray-800">订单数交叉校验</span>
          </div>
          <p className={`text-sm mt-1.5 ${data.cross_check.status === "warning" ? "text-orange-700" : "text-gray-600"}`}>
            {data.cross_check.message}
          </p>
          {data.cross_check.status === "ok" || data.cross_check.status === "warning" ? (
            <p className="text-xs text-gray-400 mt-1.5">
              本周订单 {data.cross_check.order_count}（上周 {data.cross_check.prev_order_count}）· 本周充值 {fmt(data.cross_check.recharge_amount, 0)} 铢（上周 {fmt(data.cross_check.prev_recharge_amount, 0)} 铢）· 阈值 {data.cross_check.threshold}pp
            </p>
          ) : null}
        </div>
      )}

      {/* Multi-warehouse comparison */}
      {compareData.length > 1 && (
        <div className="bg-white rounded-xl border overflow-hidden">
          <div className="px-4 py-3 border-b bg-gray-50">
            <h2 className="font-semibold text-gray-700">多仓库对比（{view === "week" ? "本周" : "本月"}）</h2>
            <p className="text-xs text-gray-400 mt-0.5">按人效从高到低排序，横向比较各仓库效率</p>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-gray-500 border-b bg-gray-50/50">
                  <th className="px-4 py-2 font-medium">仓库</th>
                  <th className="px-3 py-2 font-medium text-right">人效</th>
                  <th className="px-3 py-2 font-medium text-right">人次</th>
                  <th className="px-3 py-2 font-medium text-right">总工时</th>
                  <th className="px-3 py-2 font-medium text-right">订单数</th>
                  <th className="px-3 py-2 font-medium text-right">标准</th>
                </tr>
              </thead>
              <tbody>
                {compareData.map((w: any) => (
                  <tr key={w.warehouse_id} className="border-b hover:bg-gray-50">
                    <td className="px-4 py-2 font-medium text-gray-700 whitespace-nowrap">{w.warehouse_name}</td>
                    <td className={`px-3 py-2 text-right font-semibold ${w.below_standard ? "text-red-600" : "text-green-700"}`}>{fmt(w.efficiency)}</td>
                    <td className="px-3 py-2 text-right text-gray-700">{fmt(w.person_times)}</td>
                    <td className="px-3 py-2 text-right text-gray-700">{fmt(w.total_hours)}h</td>
                    <td className="px-3 py-2 text-right text-gray-700">{w.order_count}</td>
                    <td className="px-3 py-2 text-right text-gray-500">{fmt(w.standard, 0)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Monthly standards (淡旺季标准) */}
      <div className="bg-white rounded-xl border p-4">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div>
            <h2 className="font-semibold text-gray-700">月度标准（淡旺季）</h2>
            <p className="text-xs text-gray-400 mt-0.5">按月单独设置标准，未设置的月份用默认值</p>
          </div>
          <div className="flex items-center gap-1">
            <button onClick={() => setStdYear(String(Number(stdYear) - 1))} className="p-1.5 border rounded hover:bg-gray-50"><ChevronLeft size={16} /></button>
            <span className="text-sm font-medium w-16 text-center">{stdYear}年</span>
            <button onClick={() => setStdYear(String(Number(stdYear) + 1))} className="p-1.5 border rounded hover:bg-gray-50"><ChevronRight size={16} /></button>
          </div>
        </div>
        <div className="mt-3 mb-2">
          <MonthStdCell label="默认值（未设置月份用）" value={standards.default} onSave={saveDefaultStd} />
        </div>
        <div className="grid grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-2">
          {Array.from({ length: 12 }, (_, i) => {
            const monthKey = `${stdYear}-${String(i + 1).padStart(2, "0")}`;
            const val = standards.monthly[monthKey] ?? standards.default;
            const custom = standards.monthly[monthKey] != null;
            return (
              <div key={monthKey} className="relative">
                <MonthStdCell label={`${i + 1}月${custom ? " ·已设" : ""}`} value={val} onSave={(v) => saveMonthStd(monthKey, v)} />
              </div>
            );
          })}
        </div>
      </div>

      {/* Breakdown */}
      {view === "week" && data?.employees && (
        <div className="bg-white rounded-xl border overflow-hidden">
          <div className="px-4 py-3 border-b bg-gray-50 flex flex-wrap items-center gap-3">
            <div>
              <h2 className="font-semibold text-gray-700">员工工时明细</h2>
              <p className="text-xs text-gray-400 mt-0.5">2 次打卡 = 第2次-第1次（第1次在12点前扣1小时午休）；4 次 = (第2-第1)+(第4-第3)；1/3 次待补，可手动补录</p>
            </div>
            <div className="ml-auto flex items-center gap-3 text-xs text-gray-500">
              <span className="flex items-center gap-1"><span className="inline-block w-3 h-3 rounded-sm bg-gray-200"></span> 打卡工时</span>
              <span className="flex items-center gap-1"><span className="inline-block px-1 rounded bg-amber-100 text-amber-600 text-[10px] font-bold">补</span> 手动补录</span>
            </div>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm min-w-[760px]">
              <thead>
                <tr className="text-left text-gray-500 border-b bg-gray-50/50">
                  <th className="px-4 py-2 font-medium sticky left-0 bg-gray-50">员工</th>
                  {Array.from({ length: 7 }, (_, i) => addDays(weekStart, i)).map((d) => (
                    <th key={d} className="px-2 py-2 font-medium text-center whitespace-nowrap">{weekdayLabel(d)}</th>
                  ))}
                  <th className="px-3 py-2 font-medium text-center">合计</th>
                </tr>
              </thead>
              <tbody>
                {data.employees.map((emp: any) => {
                  const dayMap: Map<string, any> = new Map((emp.days || []).map((d: any) => [d.date, d] as [string, any]));
                  return (
                    <tr key={emp.employee_id ?? emp.user_id} className="border-b hover:bg-gray-50">
                      <td className="px-4 py-2 font-medium text-gray-700 sticky left-0 bg-white whitespace-nowrap">
                        {emp.name}
                        {emp.status === "resigned" && (
                          <span className="ml-1.5 inline-block px-1.5 py-0.5 rounded bg-gray-200 text-gray-500 text-[10px] font-normal">已离职</span>
                        )}
                      </td>
                      {Array.from({ length: 7 }, (_, i) => addDays(weekStart, i)).map((d) => {
                        const info = dayMap.get(d);
                        const canEdit = emp.employee_id != null;
                        return (
                          <td key={d} className="px-2 py-2 text-center">
                            {info?.source === "pending" ? (
                              <div className="flex flex-col items-center gap-1">
                                <span className="text-orange-500 font-medium text-xs">待补</span>
                                {canEdit && (
                                  <button onClick={() => openSupplement(emp, info)} className="text-[11px] px-2 py-0.5 rounded bg-blue-50 text-blue-600 hover:bg-blue-100">补录</button>
                                )}
                              </div>
                            ) : info?.source === "manual" ? (
                              <div className="flex flex-col items-center gap-1">
                                <span className="flex items-center gap-1 text-gray-700">
                                  <span className="inline-block px-1 rounded bg-amber-100 text-amber-600 text-[10px] font-bold">补</span>
                                  {fmt(info.hours)}h
                                </span>
                                {canEdit && (
                                  <button onClick={() => openSupplement(emp, info)} className="text-[11px] px-2 py-0.5 rounded bg-amber-50 text-amber-600 hover:bg-amber-100">修改</button>
                                )}
                              </div>
                            ) : info?.source === "clock" ? (
                              <span className="text-gray-700">{fmt(info.hours)}h</span>
                            ) : (
                              <span className="text-gray-300">-</span>
                            )}
                          </td>
                        );
                      })}
                      <td className="px-3 py-2 text-center font-semibold text-gray-800">{fmt(emp.total_hours)}h</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* 订单数录入弹窗 */}
      {orderModal && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4" onClick={() => setOrderModal(null)}>
          <div className="bg-white rounded-2xl w-full max-w-sm shadow-xl" onClick={e => e.stopPropagation()}>
            <div className="bg-blue-600 text-white px-5 py-3 rounded-t-2xl flex items-center gap-2">
              <TrendingUp size={20} />
              <h3 className="font-semibold text-lg">录入订单数</h3>
              <button onClick={() => setOrderModal(null)} className="ml-auto text-2xl text-blue-200">&times;</button>
            </div>
            <div className="p-4 space-y-3">
              <div className="text-sm text-gray-600">
                <span className="font-medium text-gray-800">{orderModal.date}</span>
              </div>
              <div>
                <label className="text-xs text-gray-500">订单数（单）</label>
                <input
                  type="number"
                  min={0}
                  value={orderModalInput}
                  onChange={e => setOrderModalInput(e.target.value)}
                  className="w-full border rounded-lg px-3 py-2 text-sm mt-1"
                  placeholder="输入当天处理单量"
                />
              </div>
              <div className="flex gap-3 pt-1">
                <button onClick={() => setOrderModal(null)} className="flex-1 py-2 border rounded-lg text-sm active:bg-gray-100">取消</button>
                <button onClick={saveDailyOrder} disabled={orderModalSaving}
                  className="flex-1 py-2 bg-blue-600 text-white rounded-lg text-sm font-semibold active:bg-blue-700 disabled:opacity-50">
                  {orderModalSaving ? "保存中..." : "保存"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 补录工时弹窗 */}
      {suppModal && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4" onClick={() => setSuppModal(null)}>
          <div className="bg-white rounded-2xl w-full max-w-sm shadow-xl" onClick={e => e.stopPropagation()}>
            <div className="bg-amber-500 text-white px-5 py-3 rounded-t-2xl flex items-center gap-2">
              <Clock size={20} />
              <h3 className="font-semibold text-lg">补录工时</h3>
              <button onClick={() => setSuppModal(null)} className="ml-auto text-2xl text-amber-100">&times;</button>
            </div>
            <div className="p-4 space-y-3">
              <div className="text-sm text-gray-600">
                <span className="font-medium text-gray-800">{suppModal.name}</span>
                <span className="ml-2 text-gray-400">{suppModal.date}</span>
              </div>
              <div>
                <label className="text-xs text-gray-500">工时（小时）</label>
                <input
                  type="number"
                  min={0}
                  step="any"
                  value={suppInput}
                  onChange={e => setSuppInput(e.target.value)}
                  className="w-full border rounded-lg px-3 py-2 text-sm mt-1"
                  placeholder="例如 8"
                />
              </div>
              <div className="flex gap-3 pt-1">
                {suppModal.current != null && (
                  <button onClick={clearSupplement} disabled={suppSaving}
                    className="px-3 py-2 border border-red-200 text-red-500 rounded-lg text-sm hover:bg-red-50 disabled:opacity-50">
                    清除
                  </button>
                )}
                <button onClick={() => setSuppModal(null)} className="flex-1 py-2 border rounded-lg text-sm active:bg-gray-100">取消</button>
                <button onClick={saveSupplement} disabled={suppSaving}
                  className="flex-1 py-2 bg-amber-500 text-white rounded-lg text-sm font-semibold active:bg-amber-600 disabled:opacity-50">
                  {suppSaving ? "保存中..." : "保存"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {view === "month" && data?.weeks && (
        <div className="bg-white rounded-xl border overflow-hidden">
          <div className="px-4 py-3 border-b bg-gray-50">
            <h2 className="font-semibold text-gray-700">各周汇总</h2>
            <p className="text-xs text-gray-400 mt-0.5">按月汇总各周（周一在当月内的周）订单数与工时</p>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-gray-500 border-b bg-gray-50/50">
                  <th className="px-4 py-2 font-medium">周（周一 ~ 周日）</th>
                  <th className="px-3 py-2 font-medium text-right">总工时</th>
                  <th className="px-3 py-2 font-medium text-right">人次</th>
                  <th className="px-3 py-2 font-medium text-right">订单数</th>
                  <th className="px-3 py-2 font-medium text-right">人效</th>
                </tr>
              </thead>
              <tbody>
                {data.weeks.map((w: any) => (
                  <tr key={w.week_start} className="border-b hover:bg-gray-50">
                    <td className="px-4 py-2 text-gray-700 whitespace-nowrap">{w.week_start} ~ {w.week_end}</td>
                    <td className="px-3 py-2 text-right text-gray-700">{fmt(w.total_hours)}h</td>
                    <td className="px-3 py-2 text-right text-gray-700">{fmt(w.person_times)}</td>
                    <td className="px-3 py-2 text-right text-gray-700">{w.order_count}</td>
                    <td className="px-3 py-2 text-right font-medium">{fmt(w.efficiency)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {loading && <div className="text-center text-gray-400 text-sm py-4">加载中...</div>}
    </div>
  );
}

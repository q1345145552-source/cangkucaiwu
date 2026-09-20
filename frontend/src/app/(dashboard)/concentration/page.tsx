"use client";
import { useEffect, useState } from "react";
import { api, getToken } from "@/lib/api";
import { useRouter } from "next/navigation";
import { useAuth } from "@/hooks/useAuth";
import { useToast } from "@/components/ui/Toast";
import { BarChart3, AlertTriangle, TrendingUp, Users, Package } from "lucide-react";

export default function ConcentrationPage() {
  const { toast } = useToast();
  const { user } = useAuth();
  const router = useRouter();

  const [month, setMonth] = useState("");
  const [data, setData] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [threshold, setThreshold] = useState(70);
  const [alert, setAlert] = useState<any>(null);
  const [trend, setTrend] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!getToken()) { router.push("/login"); return; }
    const now = new Date();
    setMonth(`${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`);
  }, []);

  useEffect(() => {
    if (!month) return;
    load();
    loadTrend();
  }, [month]);

  async function load() {
    setLoading(true);
    try {
      const r = await api.get<any>(`/suppliers/concentration?month=${month}`);
      setData(r.data || []);
      setTotal(r.total || 0);
      setThreshold(r.threshold ?? 70);
      setAlert(r.alert || null);
    } catch (err: any) {
      toast("error", err.message || "加载失败");
    }
    setLoading(false);
  }

  async function loadTrend() {
    try {
      const r = await api.get<any>("/suppliers/concentration-trend?months=6");
      setTrend(r.data || []);
    } catch { setTrend([]); }
  }

  async function saveThreshold() {
    try {
      await api.put("/suppliers/concentration-threshold", { threshold });
      toast("success", "预警阈值已保存");
      load();
    } catch (err: any) { toast("error", err.message || "保存失败"); }
  }

  const isBoss = user?.role === "super_admin";
  const topSupplier = data.length > 0 ? data[0] : null;

  return (
    <>
      <div className="flex justify-between mb-5 flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <h1 className="page-title">供应商采购分析</h1>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <input
            type="month"
            value={month}
            onChange={e => setMonth(e.target.value)}
            className="border rounded px-3 py-2 text-sm"
          />
          {isBoss && (
            <div className="flex items-center gap-2">
              <label className="text-sm text-gray-600">预警阈值(%)</label>
              <input
                type="number"
                min={0}
                max={100}
                value={threshold}
                onChange={e => setThreshold(+e.target.value)}
                className="border rounded px-2 py-1.5 text-sm w-20"
              />
              <button onClick={saveThreshold} className="px-3 py-1.5 bg-blue-600 text-white rounded text-sm">保存</button>
            </div>
          )}
        </div>
      </div>

      {/* 预警提醒 */}
      {alert && (
        <div className="mb-5 bg-red-50 border border-red-200 rounded-xl p-4 flex items-start gap-3">
          <AlertTriangle size={20} className="text-red-500 mt-0.5 flex-shrink-0" />
          <div>
            <div className="font-semibold text-red-700">集中度过高提醒</div>
            <div className="text-sm text-red-600 mt-1">{alert.message}</div>
            <div className="text-xs text-red-400 mt-1">建议核查该供应商的采购金额与价格是否合理。</div>
          </div>
        </div>
      )}

      {/* 汇总卡片 */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-5">
        <div className="card bg-gradient-to-br from-blue-500 to-blue-600 text-white border-0">
          <div className="flex items-center gap-2 mb-1"><BarChart3 size={18} /><span className="text-sm opacity-80">{month} 采购总额</span></div>
          <div className="text-2xl font-bold">¥{(total || 0).toLocaleString()}</div>
        </div>
        <div className="card bg-gradient-to-br from-green-500 to-green-600 text-white border-0">
          <div className="flex items-center gap-2 mb-1"><Users size={18} /><span className="text-sm opacity-80">供应商数量</span></div>
          <div className="text-2xl font-bold">{data.length}</div>
        </div>
        <div className={`card text-white border-0 ${topSupplier && topSupplier.percent > threshold ? "bg-gradient-to-br from-red-500 to-red-600" : "bg-gradient-to-br from-orange-500 to-orange-600"}`}>
          <div className="flex items-center gap-2 mb-1"><Package size={18} /><span className="text-sm opacity-80">最高占比供应商</span></div>
          <div className="text-2xl font-bold">{topSupplier ? `${topSupplier.supplier_name} · ${topSupplier.percent}%` : "-"}</div>
        </div>
      </div>

      {/* 供应商占比明细 */}
      <div className="card mb-5">
        <h3 className="card-title mb-4">各供应商采购占比（{month}）</h3>
        {loading ? (
          <div className="text-center py-8 text-gray-400">加载中...</div>
        ) : data.length === 0 ? (
          <div className="text-center py-12 text-gray-400 text-sm">该月暂无采购数据</div>
        ) : (
          <div className="space-y-3">
            {data.map((s: any, i: number) => (
              <div key={s.supplier_id} className={`rounded-lg p-3 ${s.percent > threshold ? "bg-red-50 border border-red-200" : "bg-gray-50"}`}>
                <div className="flex items-center gap-3 flex-wrap">
                  <span className="text-xs text-gray-400 w-5">{i + 1}</span>
                  <span className="font-medium text-sm w-40 truncate">{s.supplier_name || "-"}</span>
                  <div className="flex-1 min-w-[150px]">
                    <div className="h-2.5 bg-gray-200 rounded-full overflow-hidden">
                      <div
                        className={`h-full rounded-full ${s.percent > threshold ? "bg-red-500" : "bg-blue-500"}`}
                        style={{ width: `${Math.min(s.percent, 100)}%` }}
                      />
                    </div>
                  </div>
                  <span className={`text-sm font-semibold w-16 text-right ${s.percent > threshold ? "text-red-600" : "text-gray-700"}`}>
                    {s.percent}%
                  </span>
                  <span className="text-sm text-gray-600 w-28 text-right">¥{(s.amount || 0).toLocaleString()}</span>
                  <span className="text-xs text-gray-400 w-20 text-right">{s.order_count} 笔订单</span>
                  {s.percent > threshold && (
                    <AlertTriangle size={16} className="text-red-500" title={`占比超过 ${threshold}%`} />
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 集中度趋势 */}
      <div className="card">
        <h3 className="card-title mb-4 flex items-center gap-2"><TrendingUp size={18} className="text-blue-500" />集中度趋势（最近 {trend.length} 个月最高供应商占比）</h3>
        {trend.length === 0 ? (
          <div className="text-center py-12 text-gray-400 text-sm">暂无趋势数据</div>
        ) : (
          <div className="overflow-x-auto">
            <svg viewBox="0 0 800 280" className="w-full min-w-[600px]">
              {(() => {
                const w = 800, h = 280, px = 60, py = 30;
                const lw = w - px - 20, lh = h - py - 40;
                const n = trend.length;
                const step = lw / n;
                const barW = Math.min(step * 0.5, 60);
                const grid = [];
                for (let j = 0; j <= 4; j++) {
                  const yy = py + lh - j * lh / 4;
                  grid.push(<line key={"g" + j} x1={px} y1={yy} x2={w - 20} y2={yy} stroke="#eee" strokeWidth={1} />);
                  grid.push(<text key={"t" + j} x={px - 8} y={yy + 4} textAnchor="end" fill="#999" fontSize={10}>{j * 25}%</text>);
                }
                const bars = trend.map((t: any, i: number) => {
                  const x = px + i * step + (step - barW) / 2;
                  const bh = Math.max((t.top_percent || 0) / 100 * lh, 2);
                  const y = py + lh - bh;
                  const over = (t.top_percent || 0) > threshold;
                  return (
                    <g key={t.month}>
                      <rect x={x} y={y} width={barW} height={bh} rx={3} fill={over ? "#EF4444" : "#3B82F6"} opacity={0.85}>
                        <title>{t.month}：{t.top_supplier_name || "无"} {t.top_percent}%</title>
                      </rect>
                      <text x={x + barW / 2} y={y - 6} textAnchor="middle" fill={over ? "#DC2626" : "#2563EB"} fontSize={11} fontWeight="bold">{t.top_percent}%</text>
                      <text x={x + barW / 2} y={h - 18} textAnchor="middle" fill="#666" fontSize={11}>{t.month.substring(5)}月</text>
                      <text x={x + barW / 2} y={h - 4} textAnchor="middle" fill="#999" fontSize={9}>{t.top_supplier_name ? (t.top_supplier_name.length > 6 ? t.top_supplier_name.slice(0, 6) + "…" : t.top_supplier_name) : "-"}</text>
                    </g>
                  );
                });
                return <>{grid}{bars}</>;
              })()}
            </svg>
          </div>
        )}
        {trend.some((t: any) => (t.top_percent || 0) > threshold) && (
          <div className="mt-3 text-xs text-red-500 flex items-center gap-1">
            <AlertTriangle size={14} /> 红色柱表示该月单一供应商占比超过预警阈值，存在长期依赖单一供应商的风险。
          </div>
        )}
      </div>
    </>
  );
}

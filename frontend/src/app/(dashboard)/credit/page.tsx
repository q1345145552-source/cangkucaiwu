"use client";
import { useEffect, useState } from "react";
import { api, getToken } from "@/lib/api";
import { useToast } from "@/components/ui/Toast";
import { useRouter } from "next/navigation";
import {
  Clock, Plus, Download, TrendingUp, TrendingDown, Shield, ShieldAlert,
  ShieldCheck, Star, Calendar, BarChart3, AlertTriangle, X,
} from "lucide-react";

const RATING_COLORS: Record<string, string> = {
  A: "bg-green-50 text-green-700 border-green-200",
  B: "bg-blue-50 text-blue-700 border-blue-200",
  C: "bg-red-50 text-red-700 border-red-200",
};
const RATING_LABELS: Record<string, string> = { A: "A级 优质", B: "B级 正常", C: "C级 风险" };
const RATING_ICONS: Record<string, any> = { A: ShieldCheck, B: Shield, C: ShieldAlert };

export default function CreditPage() {
  const { toast } = useToast(); const router = useRouter();
  const [data, setData] = useState<any[]>([]); const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [db, setDb] = useState<any>({});
  const [alerts, setAlerts] = useState<any[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [customers, setCustomers] = useState<any[]>([]);
  const [form, setForm] = useState({ customer_id: 0, credit_limit: 0, repayment_day: 15 });
  const [detail, setDetail] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => { if (!getToken()) router.push("/login"); load(); loadDashboard(); loadCustomers(); loadAlerts(); }, [page]);

  async function load() {
    setLoading(true);
    try {
      const r = await api.get<any>(`/credit?page=${page}&page_size=20`);
      setData(r.data); setTotal(r.total);
    } catch (err) { console.error(err); }
    setLoading(false);
  }
  async function loadDashboard() { try { setDb(await api.get<any>("/credit/dashboard")); } catch {} }
  async function loadCustomers() { try { const r = await api.get<any>("/customers?page_size=100"); setCustomers(r.data); } catch {} }
  async function loadAlerts() { try { const r = await api.get<any>("/credit/alerts"); setAlerts(r.data); } catch {} }

  async function handleCreate() {
    try {
      await api.post("/credit", form);
      toast("success", "创建成功");
      setShowForm(false); load(); loadDashboard();
    } catch (err: any) { toast("error", err.message || "创建失败"); }
  }

  async function viewDetail(id: number) {
    try {
      const d = await api.get<any>(`/credit/${id}/detail`);
      setDetail(d);
    } catch {}
  }

  async function doExport() {
    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "/api/v1"}/credit/assessment/export`, {
        headers: { "Authorization": `Bearer ${getToken()}` },
      });
      const blob = await res.blob();
      const a = document.createElement("a"); a.href = URL.createObjectURL(blob);
      a.download = "账期客户评估报告.xlsx"; a.click();
      toast("success", "导出成功");
    } catch { toast("error", "导出失败"); }
  }

  return (
    <>
      {/* Header */}
      <div className="flex items-center gap-3 mb-5">
        <div className="w-9 h-9 rounded-xl bg-blue-100 flex items-center justify-center">
          <Clock size={20} className="text-blue-600" />
        </div>
        <div className="flex-1">
          <h1 className="page-title">账期管理</h1>
        </div>
        <button onClick={doExport} className="btn-secondary text-sm flex items-center gap-1.5">
          <Download size={14} />导出评估报告
        </button>
        <button onClick={() => setShowForm(true)} className="btn-primary text-sm flex items-center gap-1.5">
          <Plus size={14} />新建账期客户
        </button>
      </div>

      {/* Dashboard cards */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-5">
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-4">
          <div className="text-xs text-gray-400 mb-1">总欠款</div>
          <div className="text-xl font-bold text-blue-600">฿{(db.total_debt || 0).toLocaleString()}</div>
        </div>
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-4">
          <div className="text-xs text-gray-400 mb-1">总额度</div>
          <div className="text-xl font-bold text-gray-700">฿{(db.total_credit_limit || 0).toLocaleString()}</div>
        </div>
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-4">
          <div className="text-xs text-gray-400 mb-1">额度使用率</div>
          <div className="text-xl font-bold text-orange-600">{db.utilization_rate || 0}%</div>
        </div>
        <div className="bg-red-50 rounded-2xl shadow-sm border border-red-100 p-4">
          <div className="text-xs text-red-500 mb-1 flex items-center gap-1"><AlertTriangle size={12} />逾期客户</div>
          <div className="text-xl font-bold text-red-600">{db.overdue_count || 0}</div>
        </div>
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-4">
          <div className="text-xs text-gray-400 mb-1">账期客户总数</div>
          <div className="text-xl font-bold text-gray-700">{db.total_customers || 0}</div>
        </div>
      </div>

      {/* Rating distribution */}
      {db.rating_dist && (
        <div className="grid grid-cols-3 gap-4 mb-5">
          {(["A", "B", "C"] as const).map(grade => {
            const Icon = RATING_ICONS[grade];
            const count = db.rating_dist[grade] || 0;
            return (
              <div key={grade} className={`bg-white rounded-2xl shadow-sm border p-4 flex items-center gap-3 ${RATING_COLORS[grade].split(" ")[0]} border-opacity-30`}>
                <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${RATING_COLORS[grade].split(" ")[0]}`}>
                  <Icon size={20} className={RATING_COLORS[grade].split(" ")[1]} />
                </div>
                <div>
                  <div className="text-xs text-gray-400">{RATING_LABELS[grade]}</div>
                  <div className={`text-xl font-bold ${RATING_COLORS[grade].split(" ")[1]}`}>{count} 个</div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Alerts */}
      {alerts.length > 0 && (
        <div className="bg-red-50 border border-red-200 rounded-2xl p-4 mb-5">
          <h3 className="font-semibold text-red-700 mb-2 text-sm flex items-center gap-1.5">
            <AlertTriangle size={15} />逾期预警
          </h3>
          {alerts.map((a: any) => (
            <div key={a.id} className="text-sm text-red-600 py-0.5">{a.customer_name} — 逾期{a.overdue_days}天 — ฿{a.current_debt?.toLocaleString()}</div>
          ))}
        </div>
      )}

      {/* Table */}
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center h-40 text-gray-400"><div className="animate-spin w-5 h-5 border-2 border-blue-600 border-t-transparent rounded-full mr-2" />加载中...</div>
        ) : data.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-gray-400">
            <Clock size={44} className="text-gray-200 mb-3" /><span className="text-sm">暂无账期客户</span>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-gray-50">
                  <th className="text-left px-4 py-3 font-medium text-gray-500">评级</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-500">客户</th>
                  <th className="text-right px-4 py-3 font-medium text-gray-500">额度</th>
                  <th className="text-right px-4 py-3 font-medium text-gray-500">当前欠款</th>
                  <th className="text-center px-4 py-3 font-medium text-gray-500">逾期天数</th>
                  <th className="text-center px-4 py-3 font-medium text-gray-500">还款日</th>
                  <th className="text-center px-4 py-3 font-medium text-gray-500">状态</th>
                </tr>
              </thead>
              <tbody>
                {data.map((row: any) => {
                  // Quick rating: overdue > 0 → C, otherwise B (full assessment via API)
                  const quickRating = row.overdue_days > 30 ? "C" : row.overdue_days > 0 ? "B" : "A";
                  const Icon = RATING_ICONS[quickRating] || Shield;
                  return (
                    <tr key={row.id} className="border-b hover:bg-gray-50/50 cursor-pointer" onClick={() => viewDetail(row.id)}>
                      <td className="px-4 py-3">
                        <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs border font-medium ${RATING_COLORS[quickRating]}`}>
                          <Icon size={11} />{RATING_LABELS[quickRating]}
                        </span>
                      </td>
                      <td className="px-4 py-3 font-medium text-gray-800">{row.customer_name}</td>
                      <td className="px-4 py-3 text-right font-mono text-sm">฿{row.credit_limit?.toLocaleString()}</td>
                      <td className="px-4 py-3 text-right font-mono text-sm text-blue-700">฿{row.current_debt?.toLocaleString()}</td>
                      <td className={`px-4 py-3 text-center font-medium ${row.overdue_days > 0 ? "text-red-600" : "text-gray-400"}`}>{row.overdue_days || 0}天</td>
                      <td className="px-4 py-3 text-center text-gray-500">每月{row.repayment_day}号</td>
                      <td className="px-4 py-3 text-center">
                        <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${row.status === "active" ? "bg-green-50 text-green-700" : row.status === "paused" ? "bg-yellow-50 text-yellow-700" : "bg-gray-50 text-gray-500"}`}>
                          {row.status === "active" ? "正常" : row.status === "paused" ? "暂停" : "已取消"}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        {total > 20 && (
          <div className="flex items-center justify-center gap-3 py-3 border-t">
            <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page <= 1} className="px-3 py-1 text-sm border rounded disabled:opacity-30">上一页</button>
            <span className="text-sm text-gray-500">{page} / {Math.ceil(total / 20)}</span>
            <button onClick={() => setPage(p => p + 1)} disabled={page >= Math.ceil(total / 20)} className="px-3 py-1 text-sm border rounded disabled:opacity-30">下一页</button>
          </div>
        )}
      </div>

      {/* 详情弹窗 */}
      {detail && (
        <div className="modal-overlay z-50" onClick={() => setDetail(null)}>
          <div className="bg-white rounded-2xl p-6 w-[640px] max-h-[85vh] overflow-auto shadow-2xl" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-semibold text-lg flex items-center gap-2">
                {detail.customer_name}
                {detail.rating && (
                  <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs border font-medium ${RATING_COLORS[detail.rating]}`}>
                    {(() => { const I = RATING_ICONS[detail.rating]; return I ? <I size={11} /> : null; })()}
                    {RATING_LABELS[detail.rating]}
                  </span>
                )}
              </h2>
              <button onClick={() => setDetail(null)} className="text-gray-400 hover:text-gray-600"><X size={18} /></button>
            </div>

            {/* Assessment data */}
            {detail.rating && (
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-4">
                <div className="bg-gray-50 rounded-xl p-3 text-center">
                  <div className="text-[10px] text-gray-400 mb-0.5">合作时长</div>
                  <div className="text-sm font-bold text-gray-700">{detail.coop_months || 0} 个月</div>
                </div>
                <div className="bg-green-50 rounded-xl p-3 text-center">
                  <div className="text-[10px] text-green-500 mb-0.5">还款准时率</div>
                  <div className="text-sm font-bold text-green-700">{detail.on_time_rate || 100}%</div>
                </div>
                <div className="bg-red-50 rounded-xl p-3 text-center">
                  <div className="text-[10px] text-red-500 mb-0.5">逾期次数</div>
                  <div className="text-sm font-bold text-red-700">{detail.overdue_count || 0} 次</div>
                </div>
                <div className="bg-red-50 rounded-xl p-3 text-center">
                  <div className="text-[10px] text-red-500 mb-0.5">最长逾期</div>
                  <div className="text-sm font-bold text-red-700">{detail.max_overdue_days || 0} 天</div>
                </div>
                <div className="bg-blue-50 rounded-xl p-3 text-center">
                  <div className="text-[10px] text-blue-500 mb-0.5">月均还款</div>
                  <div className="text-sm font-bold text-blue-700">฿{(detail.avg_monthly_repay || 0).toLocaleString()}</div>
                </div>
                <div className="bg-orange-50 rounded-xl p-3 text-center">
                  <div className="text-[10px] text-orange-500 mb-0.5">额度使用率</div>
                  <div className="text-sm font-bold text-orange-700">{detail.utilization_rate || 0}%</div>
                </div>
              </div>
            )}

            <div className="text-sm text-gray-500 mb-4 grid grid-cols-2 gap-2">
              <div>信用额度: <span className="font-mono font-medium text-gray-700">฿{detail.credit_limit?.toLocaleString()}</span></div>
              <div>当前欠款: <span className="font-mono font-medium text-blue-700">฿{(detail.current_debt || 0).toLocaleString()}</span></div>
              <div>逾期天数: <span className={`font-medium ${detail.overdue_days > 0 ? "text-red-600" : ""}`}>{detail.overdue_days || 0}天</span></div>
              <div>状态: <span className="font-medium">{detail.status === "active" ? "正常" : detail.status}</span></div>
            </div>

            <h3 className="text-sm font-semibold mb-2 flex items-center gap-1.5"><TrendingUp size={14} className="text-gray-400" />还款记录</h3>
            <table className="w-full text-sm mb-4">
              <thead><tr className="border-b bg-gray-50"><th className="text-left py-1.5 px-2 text-gray-500">日期</th><th className="text-right py-1.5 px-2 text-gray-500">金额</th><th className="text-left py-1.5 px-2 text-gray-500">备注</th></tr></thead>
              <tbody>
                {detail.repayments?.length > 0 ? detail.repayments.map((r: any) => (
                  <tr key={r.id} className="border-b"><td className="py-1.5 px-2">{r.repayment_date?.slice(0, 10)}</td><td className="py-1.5 px-2 text-right font-mono">฿{r.amount?.toLocaleString()}</td><td className="py-1.5 px-2 text-gray-500">{r.remark}</td></tr>
                )) : <tr><td colSpan={3} className="py-2 text-center text-gray-400 text-xs">暂无还款记录</td></tr>}
              </tbody>
            </table>

            <h3 className="text-sm font-semibold mb-2 flex items-center gap-1.5"><TrendingDown size={14} className="text-gray-400" />发货记录</h3>
            <table className="w-full text-sm">
              <thead><tr className="border-b bg-gray-50"><th className="text-left py-1.5 px-2 text-gray-500">日期</th><th className="text-right py-1.5 px-2 text-gray-500">金额</th><th className="text-left py-1.5 px-2 text-gray-500">订单号</th><th className="text-left py-1.5 px-2 text-gray-500">备注</th></tr></thead>
              <tbody>
                {detail.shipments?.length > 0 ? detail.shipments.map((s: any) => (
                  <tr key={s.id} className="border-b"><td className="py-1.5 px-2">{s.ship_date?.slice(0, 10)}</td><td className="py-1.5 px-2 text-right font-mono">฿{s.amount?.toLocaleString()}</td><td className="py-1.5 px-2">{s.order_no}</td><td className="py-1.5 px-2 text-gray-500">{s.remark}</td></tr>
                )) : <tr><td colSpan={4} className="py-2 text-center text-gray-400 text-xs">暂无发货记录</td></tr>}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* 新建弹窗 */}
      {showForm && (
        <div className="modal-overlay z-50" onClick={() => setShowForm(false)}>
          <div className="bg-white rounded-2xl w-full max-w-sm shadow-2xl" onClick={e => e.stopPropagation()}>
            <div className="bg-blue-600 text-white px-5 py-3.5 rounded-t-2xl flex items-center gap-2">
              <Clock size={18} /><h2 className="font-semibold">新建账期客户</h2>
              <button onClick={() => setShowForm(false)} className="ml-auto text-blue-200 hover:text-white text-lg leading-none">&times;</button>
            </div>
            <div className="p-5 space-y-4">
              <div><label className="form-label">客户</label><select className="form-input" value={form.customer_id} onChange={e => setForm({ ...form, customer_id: +e.target.value })}><option value={0}>选择</option>{customers.map((c: any) => <option key={c.id} value={c.id}>{c.company_name}</option>)}</select></div>
              <div><label className="form-label">信用额度</label><input type="number" className="form-input" value={form.credit_limit} onChange={e => setForm({ ...form, credit_limit: +e.target.value })} /></div>
              <div><label className="form-label">还款日（每月）</label><input type="number" min={1} max={31} className="form-input" value={form.repayment_day} onChange={e => setForm({ ...form, repayment_day: +e.target.value })} /></div>
            </div>
            <div className="border-t px-5 py-3.5 bg-gray-50 rounded-b-2xl flex justify-end gap-3">
              <button onClick={() => setShowForm(false)} className="btn-secondary text-sm">取消</button>
              <button onClick={handleCreate} className="btn-primary text-sm">保存</button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

"use client";
import { useEffect, useState, useCallback } from "react";
import { api, getToken } from "@/lib/api";
import { useToast } from "@/components/ui/Toast";
import { useAuth } from "@/hooks/useAuth";
import { useRouter } from "next/navigation";
import { thaiNow } from "@/lib/thai-time";
import { Calculator, CheckCircle, Trash2, FileText, TrendingUp, TrendingDown, DollarSign, AlertTriangle, Banknote, Eye, User } from "lucide-react";

// 合并周期：后端已有周期 + 当前月上下半月（去重，最近的在前）
function mergePeriods(ps: any[]): any[] {
  const t = thaiNow();
  const cur = `${t.getFullYear()}-${String(t.getMonth() + 1).padStart(2, "0")}`;
  const list = [...(ps || [])];
  for (const half of ["first_half", "second_half"]) {
    list.push({
      period: cur,
      half,
      label: `${cur} ${half === "second_half" ? "下半月" : "上半月"}`,
    });
  }
  const seen = new Set<string>();
  const out: any[] = [];
  for (const p of list) {
    const key = `${p.period}_${p.half}`;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(p);
  }
  out.sort((a, b) => {
    if (a.period !== b.period) return a.period < b.period ? 1 : -1;
    return a.half < b.half ? 1 : -1;
  });
  return out;
}

export default function PayrollPage() {
  const { toast } = useToast(); const { user } = useAuth(); const router = useRouter();
  const [records, setRecords] = useState<any[]>([]);
  const [summary, setSummary] = useState<any>(null);
  const [periods, setPeriods] = useState<any[]>([]);
  const [periodsLoading, setPeriodsLoading] = useState(true);
  const [loading, setLoading] = useState(false);
  const [calculating, setCalculating] = useState(false);
  const [selectedPeriod, setSelectedPeriod] = useState("");
  const [selectedPeriodKey, setSelectedPeriodKey] = useState("");
  const [showPayslip, setShowPayslip] = useState<any>(null);
  const [dailyDetailOpen, setDailyDetailOpen] = useState(false);
  const [lateDetailOpen, setLateDetailOpen] = useState(false);
  const [disbursing, setDisbursing] = useState<number | null>(null);
  const [showSingleModal, setShowSingleModal] = useState(false);
  const [singleEmpId, setSingleEmpId] = useState<number>(0);
  const [singleEndDate, setSingleEndDate] = useState(new Date().toISOString().slice(0, 10));
  const [singleEmployees, setSingleEmployees] = useState<any[]>([]);
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const isAdmin = user?.role === "warehouse_admin";

  useEffect(() => {
    if (!getToken()) { router.push("/login"); return; }
    // Default to current month
    const now = new Date().toISOString().slice(0, 7);
    setSelectedPeriod(now);
    initPage();
  }, []);

  // 首次进入：拉周期下拉 + 自动选中第一个周期并加载
  async function initPage() {
    setPeriodsLoading(true);
    try {
      const r = await api.get<any>("/payroll");
      const ps = mergePeriods(r.periods || []);
      setPeriods(ps);
      if (ps.length > 0) {
        const first = ps[0];
        const key = `${first.period}_${first.half}`;
        setSelectedPeriodKey(key);
        setSelectedPeriod(first.period);
        loadRecords(key);
      }
    } catch (err: any) {
      toast("error", err.message || "加载工资周期失败");
    }
    setPeriodsLoading(false);
  }

  // 刷新周期下拉（计算/删除后调用）
  async function loadPeriods() {
    try {
      const r = await api.get<any>("/payroll");
      setPeriods(mergePeriods(r.periods || []));
    } catch (err: any) {
      toast("error", err.message || "加载工资周期失败");
    }
  }

  function periodKeyToApi(periodKey: string) {
    const [p, h] = periodKey.split("_");
    return { period: p || periodKey, half: h || "first_half" };
  }
  
  function periodLabel(periodKey: string) {
    const parts = periodKey.split("_");
    return parts[0] ? `${parts[0]} ${parts[1] === "second_half" ? "下半月" : "上半月"}` : periodKey;
  }

  async function loadRecords(periodKeyOverride?: string) {
    const key = periodKeyOverride || selectedPeriodKey;
    if (!key) return;
    const { period, half } = periodKeyToApi(key);
    setSelectedPeriod(period);
    setLoading(true);
    setSelectedIds([]);  // 重新加载/切换周期时清空勾选
    try {
      const params = `period=${period}&half=${half}`;
      const [recR, sumR] = await Promise.all([
        api.get<any>(`/payroll?${params}`),
        api.get<any>(`/payroll/summary?${params}`),
      ]);
      setRecords(recR.data || []);
      setSummary(sumR);
    } catch (err: any) {
      toast("error", err.message || "加载工资数据失败");
    }
    setLoading(false);
  }

  async function handleCalculate() {
    if (!selectedPeriodKey) { toast("error", "请先选择周期"); return; }
    const { period, half } = periodKeyToApi(selectedPeriodKey);
    const label = periodLabel(selectedPeriodKey);
    if (!confirm(`确定计算 ${label} 的工资吗？`)) return;
    setCalculating(true);
    try {
      const r = await api.post<any>("/payroll/calculate", { period, half });
      if (r.record_count > 0) {
        toast("success", `${label} 工资计算完成`);
      } else {
        toast("error", `${label} 已计算过，未新增工资单`);
      }
      loadPeriods();
      loadRecords(selectedPeriodKey);
    } catch (err: any) {
      toast("error", err.message || "计算失败");
    }
    setCalculating(false);
  }

  async function openSingleModal() {
    setShowSingleModal(true);
    setSingleEndDate(new Date().toISOString().slice(0, 10));
    try {
      const r = await api.get<any>("/employees?page_size=200");
      setSingleEmployees((r.data || []).filter((e: any) => e.status !== "resigned"));
    } catch (err: any) {
      toast("error", err.message || "加载员工列表失败");
    }
  }

  async function handleSingleSettle() {
    if (!singleEmpId) { toast("error", "请选择员工"); return; }
    if (!singleEndDate) { toast("error", "请选择截止日期"); return; }
    setCalculating(true);
    try {
      const r = await api.post<any>("/payroll/single-settle", { employee_id: singleEmpId, end_date: singleEndDate });
      toast("success", r.message || "结算完成");
      setShowSingleModal(false);
      const d = new Date(singleEndDate);
      const newKey = `${singleEndDate.slice(0, 7)}_${d.getDate() <= 15 ? "first_half" : "second_half"}`;
      setSelectedPeriodKey(newKey);
      loadPeriods();
      loadRecords(newKey);
    } catch (err: any) { toast("error", err.message || "结算失败"); }
    setCalculating(false);
  }

  async function handleConfirm(recordId: number) {
    try {
      await api.post(`/payroll/${recordId}/confirm`);
      toast("success", "工资单已确认");
      loadRecords();
    } catch (err: any) {
      toast("error", err.message || "确认失败");
    }
  }

  async function handleConfirmAll() {
    const { period, half } = periodKeyToApi(selectedPeriodKey);
    if (!confirm(`确定将 ${periodLabel(selectedPeriodKey)} 所有待确认工资单全部确认吗？`)) return;
    try {
      const r = await api.post(`/payroll/confirm-all?period=${period}&half=${half}`);
      toast("success", r.message || "全部确认成功");
      loadRecords();
    } catch (err: any) {
      toast("error", err.message || "确认失败");
    }
  }

  async function handleDelete(recordId: number) {
    if (!confirm("确定删除该工资记录吗？")) return;
    try {
      await api.delete(`/payroll/${recordId}`);
      toast("success", "已删除");
      loadRecords();
      loadPeriods();
    } catch (err: any) {
      toast("error", err.message || "删除失败");
    }
  }

  async function handleRecalculate() {
    const { period, half } = periodKeyToApi(selectedPeriodKey);
    if (!confirm(`将删除 ${periodLabel(selectedPeriodKey)} 全部工资记录并重新计算，确定吗？`)) return;
    setCalculating(true);
    try {
      await api.delete(`/payroll/period/${period}?half=${half}`);
      await api.post("/payroll/calculate", { period, half });
      toast("success", `${periodLabel(selectedPeriodKey)} 重新计算完成`);
      loadPeriods();
      loadRecords(selectedPeriodKey);
    } catch (err: any) {
      toast("error", err.message || "操作失败");
    }
    setCalculating(false);
  }

  async function handleDisburse(recordId: number) {
    setDisbursing(recordId);
    try {
      const r = await api.post(`/payroll/${recordId}/disburse`, {});
      toast("success", r.message || "发放成功");
      loadRecords();
    } catch (err: any) {
      toast("error", err.message || "发放失败");
    }
    setDisbursing(null);
  }

  function viewPayslip(record: any) {
    setShowPayslip(record);
    setDailyDetailOpen(false);
    setLateDetailOpen(false);
  }

  // 工资单展示用的计算值 + 公式（空值保护）
  const psDetail = showPayslip?.detail || {};
  const psWorkHours = psDetail.work_hours ?? (showPayslip?.attendance_days ?? 0);
  const psHourlyRate = psDetail.hourly_rate ?? 0;
  const psWorkPay = showPayslip?.base_pay ?? 0;
  const psOvertimePay = showPayslip?.overtime_pay ?? 0;
  const psOvertimeHours = showPayslip?.overtime_hours ?? 0;
  const psLatePenalty = showPayslip?.late_penalty ?? 0;
  const psTotalDeductions = showPayslip?.total_deductions ?? 0;
  const psDailyHours = psDetail.daily_hours || [];
  const psLateDetails = psDetail.late_details || [];
  const psLateHalfCount = psDetail.late_half_count ?? 0;
  const psLateOneCount = psDetail.late_one_count ?? 0;
  const psHourlyFormula = showPayslip?.employee_status === "trial"
    ? `日薪 ${showPayslip?.daily_wage ?? 0} ÷ 8`
    : `底薪 ${showPayslip?.base_salary ?? 0} ÷ ${(showPayslip?.total_days_in_month ?? 30) - 2} ÷ 8`;
  const psLateFormula = psLateHalfCount > 0 && psLateOneCount > 0
    ? `迟到半小时${psLateHalfCount}次 + 迟到1小时${psLateOneCount}次`
    : psLateHalfCount > 0
      ? `迟到半小时${psLateHalfCount}次 × ${(psHourlyRate * 0.5).toFixed(2)}`
      : psLateOneCount > 0
        ? `迟到1小时${psLateOneCount}次 × ${psHourlyRate.toFixed(2)}`
        : "";

  function fmtClockTime(t: string) {
    if (!t) return "";
    const [h, m] = t.split(":");
    return m === "00" ? `${parseInt(h, 10)}点` : `${parseInt(h, 10)}:${m}`;
  }

  function dailyStatusText(d: any) {
    switch (d.status) {
      case "leave": return "请假 不计算";
      case "rest": return "休息日";
      case "absence": return "缺勤";
      case "no_clock": return "无打卡记录";
      default: {
        const times = (d.times || []).map((t: string) => fmtClockTime(t)).join(" ");
        return `${d.hours ?? 0}小时${times ? ` (${times})` : ""}`;
      }
    }
  }

  function toggleSelect(id: number) {
    setSelectedIds(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]);
  }

  function toggleSelectAll() {
    setSelectedIds(prev => (prev.length === records.length && records.length > 0) ? [] : records.map(r => r.id));
  }

  async function handleBatchConfirm() {
    if (!selectedIds.length) return;
    setCalculating(true);
    try {
      const r = await api.post<any>("/payroll/batch-confirm", { record_ids: selectedIds });
      toast("success", r.message || `已确认 ${r.count} 条`);
      loadRecords();
    } catch (err: any) { toast("error", err.message || "批量确认失败"); }
    setCalculating(false);
  }

  async function handleBatchDisburse() {
    if (!selectedIds.length) return;
    setCalculating(true);
    try {
      const r = await api.post<any>("/payroll/batch-disburse", { record_ids: selectedIds });
      toast("success", r.message || `已发放 ${r.count} 条`);
      loadRecords();
    } catch (err: any) { toast("error", err.message || "批量发放失败"); }
    setCalculating(false);
  }

  async function handleBatchDelete() {
    if (!selectedIds.length) return;
    if (!confirm(`确定删除选中的 ${selectedIds.length} 条工资单吗？删除后可以重新计算`)) return;
    setCalculating(true);
    try {
      const r = await api.post<any>("/payroll/batch-delete", { record_ids: selectedIds });
      toast("success", r.message || `已删除 ${r.count} 条`);
      loadRecords();
      loadPeriods();
    } catch (err: any) { toast("error", err.message || "批量删除失败"); }
    setCalculating(false);
  }

  return (
    <div>
      <div className="flex justify-between mb-4 flex-wrap gap-2 items-center">
        <h1 className="page-title flex items-center gap-2"><Calculator size={24}/>工资管理</h1>
        <div className="flex gap-2 items-center">
          {/* Period + Half selector */}
          <select value={selectedPeriodKey} onChange={e => { const v = e.target.value; setSelectedPeriodKey(v); if (v) loadRecords(v); }}
            className="border rounded-lg px-3 py-2 text-sm bg-white min-w-[160px]">
            <option value="">选择周期</option>
            {periods.map((p: any) => {
              const key = `${p.period}_${p.half}`;
              return <option key={key} value={key}>{p.label}</option>
            })}
          </select>
          {isAdmin && (
            <>
              <button onClick={handleCalculate}
                className="btn-primary flex items-center gap-1 text-sm px-4 py-2">
                <Calculator size={16}/> 计算工资
              </button>
              <button onClick={openSingleModal}
                className="border border-blue-300 text-blue-600 flex items-center gap-1 text-sm px-4 py-2 rounded-lg hover:bg-blue-50">
                <User size={16}/> 单人结算
              </button>
              {records.length > 0 && (
                <>
                  <button onClick={handleConfirmAll}
                    className="bg-green-500 text-white flex items-center gap-1 text-sm px-4 py-2 rounded-lg hover:bg-green-600">
                    <CheckCircle size={16}/> 全部确认
                  </button>
                  <button onClick={handleRecalculate}
                    className="bg-amber-500 text-white flex items-center gap-1 text-sm px-4 py-2 rounded-lg hover:bg-amber-600">
                    <AlertTriangle size={16}/> 重新计算
                  </button>
                </>
              )}
            </>
          )}
        </div>
      </div>

      {/* Summary Card */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
        <div className="bg-white rounded-xl border p-4">
          <p className="text-xs text-gray-400">总人数</p>
          <p className="text-2xl font-bold text-gray-800">{summary?.employee_count ?? 0}</p>
          <p className="text-xs text-gray-400">{summary?.confirmed_count ?? 0}已确认 / {summary?.pending_count ?? 0}待确认</p>
        </div>
        <div className="bg-white rounded-xl border p-4">
          <p className="text-xs text-gray-400">应发总额</p>
          <p className="text-2xl font-bold text-blue-600">{(summary?.total_gross ?? 0).toLocaleString()}</p>
        </div>
        <div className="bg-white rounded-xl border p-4">
          <p className="text-xs text-gray-400">加班费合计</p>
          <p className="text-2xl font-bold text-green-600">{(summary?.total_overtime ?? 0).toLocaleString()}</p>
        </div>
        <div className="bg-white rounded-xl border p-4">
          <p className="text-xs text-gray-400">实发总额</p>
          <p className="text-2xl font-bold text-orange-600">{(summary?.total_net ?? 0).toLocaleString()}</p>
        </div>
      </div>

      {/* Batch action bar */}
      {selectedIds.length > 0 && (
        <div className="flex items-center justify-between bg-blue-50 border border-blue-200 rounded-lg px-4 py-2 mb-3">
          <span className="text-sm font-medium text-blue-700">已选 {selectedIds.length} 条</span>
          <div className="flex gap-2">
            <button onClick={handleBatchConfirm} disabled={calculating}
              className="bg-green-500 text-white px-3 py-1.5 rounded text-sm hover:bg-green-600 disabled:opacity-50">批量确认</button>
            <button onClick={handleBatchDisburse} disabled={calculating}
              className="bg-blue-500 text-white px-3 py-1.5 rounded text-sm hover:bg-blue-600 disabled:opacity-50">批量发放</button>
            <button onClick={handleBatchDelete} disabled={calculating}
              className="bg-red-500 text-white px-3 py-1.5 rounded text-sm hover:bg-red-600 disabled:opacity-50">批量删除</button>
          </div>
        </div>
      )}

      {/* Records Table */}
      {loading || periodsLoading ? (
        <div className="text-center py-12 text-gray-400">加载中...</div>
      ) : periods.length === 0 ? (
        <div className="text-center py-12 text-gray-400 bg-white rounded-xl border">
          <Calculator size={40} className="mx-auto mb-3 text-gray-300"/>
          <p>该仓库还没有计算过工资</p>
          {isAdmin && <p className="text-sm mt-1">点击右上角「计算工资」开始</p>}
        </div>
      ) : records.length === 0 ? (
        <div className="text-center py-12 text-gray-400 bg-white rounded-xl border">
          <Calculator size={40} className="mx-auto mb-3 text-gray-300"/>
          <p>该月份暂无工资记录</p>
          {isAdmin && <p className="text-sm mt-1">点击右上角「计算工资」开始</p>}
        </div>
      ) : (
        <div className="bg-white rounded-xl border overflow-x-auto">
          <table className="w-full text-sm min-w-[900px]">
            <thead>
              <tr className="border-b bg-gray-50">
                <th className="text-center px-2 py-3 w-10">
                  <input type="checkbox" checked={records.length > 0 && selectedIds.length === records.length}
                    onChange={toggleSelectAll} className="w-4 h-4 cursor-pointer align-middle" />
                </th>
                <th className="text-left px-3 py-3 font-medium text-gray-500">员工</th>
                <th className="text-left px-3 py-3 font-medium text-gray-500">类型</th>
                <th className="text-center px-3 py-3 font-medium text-gray-500">出勤</th>
                <th className="text-center px-3 py-3 font-medium text-gray-500">请假</th>
                <th className="text-center px-3 py-3 font-medium text-gray-500">休息</th>
                <th className="text-center px-3 py-3 font-medium text-gray-500">缺勤</th>
                <th className="text-right px-3 py-3 font-medium text-gray-500">基本工资</th>
                <th className="text-right px-3 py-3 font-medium text-gray-500">加班费</th>
                <th className="text-right px-3 py-3 font-medium text-gray-500">扣款</th>
                <th className="text-right px-3 py-3 font-medium text-gray-500">实发</th>
                <th className="text-center px-3 py-3 font-medium text-gray-500">确认</th>
                <th className="text-center px-3 py-3 font-medium text-gray-500">发放</th>
                <th className="text-center px-3 py-3 font-medium text-gray-500">操作</th>
              </tr>
            </thead>
            <tbody>
              {records.map((r: any) => (
                <tr key={r.id} className="border-b border-gray-50 hover:bg-gray-50">
                  <td className="px-2 py-3 text-center">
                    <input type="checkbox" checked={selectedIds.includes(r.id)}
                      onChange={() => toggleSelect(r.id)} className="w-4 h-4 cursor-pointer align-middle" />
                  </td>
                  <td className="px-3 py-3 font-medium">
                    {r.employee_name ?? "—"}
                    {r.settle_end_date && <div className="text-[11px] text-gray-400 font-normal">结算到 {r.settle_end_date.slice(5).replace("-", "月")}日</div>}
                  </td>
                  <td className="px-3 py-3">
                    <span className={`px-2 py-0.5 rounded text-xs ${
                      r.employee_status === "trial" ? "bg-amber-50 text-amber-700" : "bg-blue-50 text-blue-700"
                    }`}>
                      {r.employee_status === "trial" ? "试用期" : "正式"}
                    </span>
                  </td>
                  <td className="px-3 py-3 text-center">{r.attendance_days ?? 0}</td>
                  <td className="px-3 py-3 text-center">{r.leave_days ?? 0}</td>
                  <td className="px-3 py-3 text-center">{r.rest_days ?? 0}</td>
                  <td className="px-3 py-3 text-center">{r.absence_days ?? 0}</td>
                  <td className="px-3 py-3 text-right">{(r.base_pay ?? 0).toLocaleString()}</td>
                  <td className="px-3 py-3 text-right text-green-600">{(r.overtime_pay ?? 0) > 0 ? (r.overtime_pay ?? 0).toLocaleString() : "-"}</td>
                  <td className="px-3 py-3 text-right text-red-500">{(r.total_deductions ?? 0) > 0 ? (r.total_deductions ?? 0).toLocaleString() : "-"}</td>
                  <td className="px-3 py-3 text-right font-bold">{(r.net_pay ?? 0).toLocaleString()}</td>
                  <td className="px-3 py-3 text-center">
                    <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                      r.status === "confirmed" ? "bg-green-50 text-green-700" : "bg-amber-50 text-amber-700"
                    }`}>
                      {r.status === "confirmed" ? "已确认" : "待确认"}
                    </span>
                  </td>
                  <td className="px-3 py-3 text-center">
                    {r.disbursed ? (
                      <span className="bg-blue-50 text-blue-700 px-2 py-0.5 rounded text-xs font-medium">
                        已发放
                      </span>
                    ) : (
                      <span className="text-gray-400 text-xs">待发放</span>
                    )}
                  </td>
                  <td className="px-3 py-3 text-center">
                    <div className="flex items-center justify-center gap-2">
                      {r.status !== "confirmed" && isAdmin && (
                        <button onClick={() => handleConfirm(r.id)}
                          className="text-green-600 hover:text-green-800 text-xs font-medium"
                          title="确认">
                          <CheckCircle size={16}/>
                        </button>
                      )}
                      {r.status === "confirmed" && !r.disbursed && isAdmin && (
                        <button onClick={() => handleDisburse(r.id)} disabled={disbursing === r.id}
                          className="text-blue-600 hover:text-blue-800 text-xs font-medium"
                          title="发放">
                          <Banknote size={16}/>
                        </button>
                      )}
                      <button onClick={() => viewPayslip(r)}
                        className="text-gray-400 hover:text-gray-600 text-xs"
                        title="查看工资单">
                        <Eye size={14}/>
                      </button>
                      {isAdmin && (
                        <button onClick={() => handleDelete(r.id)}
                          className="text-red-400 hover:text-red-600 text-xs"
                          title="删除">
                          <Trash2 size={14}/>
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* 单人结算 Modal */}
      {showSingleModal && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50 p-4" onClick={() => setShowSingleModal(false)}>
          <div className="bg-white rounded-2xl w-full max-w-sm shadow-xl" onClick={e => e.stopPropagation()}>
            <div className="bg-blue-500 text-white px-5 py-3 rounded-t-2xl flex items-center gap-2">
              <User size={20} /><span className="font-semibold">单人结算</span>
            </div>
            <div className="p-5 space-y-4">
              <div>
                <label className="form-label text-sm font-medium text-gray-600 mb-1 block">选择员工</label>
                <select className="form-input text-base py-2.5" value={singleEmpId || ""} onChange={e => setSingleEmpId(+e.target.value)}>
                  <option value="">请选择员工</option>
                  {singleEmployees.map((e: any) => <option key={e.id} value={e.id}>{e.name}</option>)}
                </select>
              </div>
              <div>
                <label className="form-label text-sm font-medium text-gray-600 mb-1 block">截止日期</label>
                <input type="date" className="form-input text-base py-2.5" value={singleEndDate} onChange={e => setSingleEndDate(e.target.value)} />
                <p className="text-xs text-gray-400 mt-1">从当前半月周期开始算到截止日（1-15 上半月，16-月末 下半月）。</p>
              </div>
            </div>
            <div className="border-t px-5 py-4 bg-gray-50 rounded-b-2xl flex justify-end gap-3">
              <button onClick={() => setShowSingleModal(false)} className="btn-secondary text-sm px-6 py-2">取消</button>
              <button onClick={handleSingleSettle} disabled={calculating} className="btn-primary text-sm px-6 py-2">
                {calculating ? "结算中..." : "结算"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Payslip Detail Modal */}
      {showPayslip && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50 p-4" onClick={() => setShowPayslip(null)}>
          <div className="bg-white rounded-2xl w-full max-w-md shadow-xl max-h-[90vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
            <div className="bg-blue-500 text-white px-5 py-3 rounded-t-2xl flex items-center gap-2 sticky top-0 z-10">
              <FileText size={20} />
              <span className="font-semibold">工资单</span>
            </div>
            <div className="p-5 space-y-3">
              {/* Header */}
              <div className="text-center pb-3 border-b">
                <h3 className="text-lg font-bold">{showPayslip.employee_name}</h3>
                <p className="text-sm text-gray-500">{showPayslip.period} {showPayslip.half === "second_half" ? "下半月" : "上半月"} 工资单</p>
                <span className={`inline-block mt-1 px-2 py-0.5 rounded text-xs font-medium ${
                  showPayslip.employee_status === "trial" ? "bg-amber-50 text-amber-700" : "bg-blue-50 text-blue-700"
                }`}>
                  {showPayslip.employee_status === "trial" ? "试用期" : "正式员工"}
                </span>
              </div>

              {/* Attendance */}
              <div className="bg-gray-50 rounded-lg p-3">
                <p className="text-xs text-gray-400 mb-2">出勤统计 ({(showPayslip.total_days_in_month ?? 0)}天/月)</p>
                <div className="grid grid-cols-4 gap-2 text-center">
                  <div><p className="text-lg font-bold text-green-600">{showPayslip.attendance_days ?? 0}</p><p className="text-xs text-gray-400">出勤</p></div>
                  <div><p className="text-lg font-bold text-amber-600">{showPayslip.leave_days ?? 0}</p><p className="text-xs text-gray-400">请假</p></div>
                  <div><p className="text-lg font-bold text-blue-600">{showPayslip.rest_days ?? 0}</p><p className="text-xs text-gray-400">休息</p></div>
                  <div><p className="text-lg font-bold text-red-600">{showPayslip.absence_days ?? 0}</p><p className="text-xs text-gray-400">缺勤</p></div>
                </div>
              </div>

              {/* Salary breakdown（按工时） */}
              <div className="space-y-2">
                <div className="flex justify-between text-sm">
                  <button onClick={() => setDailyDetailOpen(true)} className="text-blue-600 hover:underline cursor-pointer">上班工时</button>
                  <span>{psWorkHours} 小时</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-500">时薪</span>
                  <span>{psHourlyRate} <span className="text-gray-400 text-xs">({psHourlyFormula})</span></span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-500">上班工资</span>
                  <span><b>{psWorkPay.toLocaleString()}</b> <span className="text-gray-400 text-xs">({psWorkHours}小时 × {psHourlyRate})</span></span>
                </div>
                {psOvertimePay > 0 && (
                  <div className="flex justify-between text-sm text-green-600">
                    <span>加班费 ({psOvertimeHours}h)</span>
                    <span>+{psOvertimePay}</span>
                  </div>
                )}
                {psLatePenalty > 0 && (
                  <div className="flex justify-between text-sm text-red-500">
                    <button onClick={() => setLateDetailOpen(true)} className="text-red-500 hover:underline cursor-pointer">迟到扣款</button>
                    <span>-{psLatePenalty}{psLateFormula ? <span className="text-red-300 text-xs"> ({psLateFormula})</span> : null}</span>
                  </div>
                )}
              </div>

              {/* Total */}
              <div className="border-t pt-3 space-y-1">
                <div className="flex justify-between text-sm text-gray-500">
                  <span>应发合计</span><span>{showPayslip.gross_pay ?? 0}</span>
                </div>
                <div className="flex justify-between text-sm text-gray-500">
                  <span>扣款合计</span><span className="text-red-500">-{showPayslip.total_deductions ?? 0}</span>
                </div>
                <div className="flex justify-between text-base font-bold pt-1 border-t">
                  <span>实发工资</span>
                  <span className="text-blue-600 text-lg">{(showPayslip.net_pay ?? 0).toLocaleString()} 泰铢
                    <span className="text-gray-400 text-xs font-normal ml-1">({psWorkPay} + {psOvertimePay} - {psTotalDeductions})</span>
                  </span>
                </div>
              </div>

              {/* Status & Disbursement */}
              <div className="bg-gray-50 rounded-lg p-3 space-y-1 text-sm">
                <div className="flex justify-between">
                  <span className="text-gray-400">确认状态</span>
                  <span className={showPayslip.status === "confirmed" ? "text-green-600 font-medium" : "text-amber-600"}>
                    {showPayslip.status === "confirmed" ? "已确认" : "待确认"}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">发放状态</span>
                  {showPayslip.disbursed ? (
                    <span className="text-blue-600 font-medium">
                      已发放 {showPayslip.disbursed_at ? new Date(showPayslip.disbursed_at).toLocaleDateString("zh-CN") : ""}
                    </span>
                  ) : (
                    <span className="text-gray-400">待发放</span>
                  )}
                </div>
              </div>

              {/* Disburse action */}
              {showPayslip.status === "confirmed" && !showPayslip.disbursed && isAdmin && (
                <button onClick={() => { handleDisburse(showPayslip.id); setShowPayslip(null); }}
                  className="w-full bg-blue-500 text-white py-2.5 rounded-lg hover:bg-blue-600 flex items-center justify-center gap-2 font-medium">
                  <Banknote size={18} /> 现金发放 {(showPayslip.net_pay ?? 0).toLocaleString()} 泰铢
                </button>
              )}
            </div>
            <div className="border-t px-5 py-3 bg-gray-50 rounded-b-2xl text-center">
              <button onClick={() => setShowPayslip(null)} className="text-sm text-gray-400">关闭</button>
            </div>
          </div>
        </div>
      )}

      {/* 逐天出勤明细 Modal */}
      {dailyDetailOpen && showPayslip && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-[70] p-4" onClick={() => setDailyDetailOpen(false)}>
          <div className="bg-white rounded-2xl w-full max-w-md max-h-[80vh] overflow-y-auto shadow-xl" onClick={e => e.stopPropagation()}>
            <div className="bg-blue-500 text-white px-5 py-3 rounded-t-2xl flex items-center gap-2 sticky top-0 z-10">
              <FileText size={18} />
              <span className="font-semibold">上班工时明细</span>
              <button onClick={() => setDailyDetailOpen(false)} className="ml-auto text-2xl text-white/80 hover:text-white">&times;</button>
            </div>
            <div className="p-4 space-y-1.5">
              {psDailyHours.length === 0 ? (
                <div className="text-center py-8 text-gray-400 text-sm">暂无逐天明细</div>
              ) : psDailyHours.map((d: any) => (
                <div key={d.date} className="flex justify-between items-center text-sm py-1.5 border-b border-gray-50">
                  <span className="font-medium text-gray-700 shrink-0">{d.day}号</span>
                  <span className={`text-gray-600 ${d.status === "leave" ? "text-amber-600" : d.status === "rest" ? "text-blue-600" : d.status === "absence" ? "text-red-600" : d.status === "no_clock" ? "text-gray-400" : ""}`}>{dailyStatusText(d)}</span>
                </div>
              ))}
            </div>
            <div className="border-t px-5 py-3 bg-gray-50 rounded-b-2xl text-center">
              <button onClick={() => setDailyDetailOpen(false)} className="text-sm text-gray-400">关闭</button>
            </div>
          </div>
        </div>
      )}

      {/* 迟到明细 Modal */}
      {lateDetailOpen && showPayslip && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-[70] p-4" onClick={() => setLateDetailOpen(false)}>
          <div className="bg-white rounded-2xl w-full max-w-md max-h-[80vh] overflow-y-auto shadow-xl" onClick={e => e.stopPropagation()}>
            <div className="bg-red-500 text-white px-5 py-3 rounded-t-2xl flex items-center gap-2 sticky top-0 z-10">
              <AlertTriangle size={18} />
              <span className="font-semibold">迟到明细</span>
              <button onClick={() => setLateDetailOpen(false)} className="ml-auto text-2xl text-white/80 hover:text-white">&times;</button>
            </div>
            <div className="p-4 space-y-1.5">
              {psLateDetails.length === 0 ? (
                <div className="text-center py-8 text-gray-400 text-sm">暂无迟到记录</div>
              ) : psLateDetails.map((l: any, i: number) => (
                <div key={`${l.date}_${i}`} className="flex justify-between items-center text-sm py-1.5 border-b border-gray-50">
                  <span className="font-medium text-gray-700 shrink-0">{l.day}号</span>
                  <span className="text-red-600">{l.type === "late_half" ? "迟到半小时" : "迟到1小时"} 扣{l.amount}</span>
                </div>
              ))}
            </div>
            <div className="border-t px-5 py-3 bg-gray-50 rounded-b-2xl text-center">
              <button onClick={() => setLateDetailOpen(false)} className="text-sm text-gray-400">关闭</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

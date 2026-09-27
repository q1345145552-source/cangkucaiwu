"use client";
import { useEffect, useState, useCallback } from "react";
import { api, getToken } from "@/lib/api";
import { useToast } from "@/components/ui/Toast";
import { useAuth } from "@/hooks/useAuth";
import { useRouter } from "next/navigation";
import { thaiNow } from "@/lib/thai-time";
import { Calculator, CheckCircle, FileText, TrendingUp, TrendingDown, DollarSign, AlertTriangle, Banknote, Eye, User } from "lucide-react";

// 泰国时间的今天/昨天/过去15号/过去月末（用于结算日期输入）
function thaiDateStr(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
function thaiTodayStr(): string {
  return thaiDateStr(thaiNow());
}
function thaiYesterdayStr(): string {
  const t = thaiNow();
  return thaiDateStr(new Date(t.getFullYear(), t.getMonth(), t.getDate() - 1));
}
function past15thStr(): string {
  const t = thaiNow();
  if (t.getDate() > 15) {
    return `${t.getFullYear()}-${String(t.getMonth() + 1).padStart(2, "0")}-15`;
  }
  const prev = new Date(t.getFullYear(), t.getMonth() - 1, 15);
  return `${prev.getFullYear()}-${String(prev.getMonth() + 1).padStart(2, "0")}-15`;
}
function pastMonthEndStr(): string {
  const t = thaiNow();
  const lastDay = new Date(t.getFullYear(), t.getMonth(), 0);
  return thaiDateStr(lastDay);
}

// 薪资模板类型 → 中文标签（工资按模板算，不再按试用期/正式分段）
const TEMPLATE_TYPE_LABELS: Record<string, string> = { hourly: "按小时", daily: "按天", monthly: "按月" };
function templateTypeLabel(tt?: string): string {
  return tt ? (TEMPLATE_TYPE_LABELS[tt] || tt) : "";
}
function templateTypeBadge(tt?: string): string {
  if (tt === "monthly") return "bg-blue-50 text-blue-700";
  if (tt === "hourly") return "bg-teal-50 text-teal-700";
  return "bg-amber-50 text-amber-700";
}

export default function PayrollPage() {
  const { toast } = useToast(); const { user } = useAuth(); const router = useRouter();
  const [records, setRecords] = useState<any[]>([]);
  const [summary, setSummary] = useState<any>(null);
  const [months, setMonths] = useState<string[]>([]);
  const [monthsLoading, setMonthsLoading] = useState(true);
  const [loading, setLoading] = useState(false);
  const [calculating, setCalculating] = useState(false);
  const [selectedMonth, setSelectedMonth] = useState("");
  const [voidFilter, setVoidFilter] = useState("valid");
  const [showPayslip, setShowPayslip] = useState<any>(null);
  const [dailyDetailOpen, setDailyDetailOpen] = useState(false);
  const [lateDetailOpen, setLateDetailOpen] = useState(false);
  const [disbursing, setDisbursing] = useState<number | null>(null);
  const [showSingleModal, setShowSingleModal] = useState(false);
  const [singleEmpId, setSingleEmpId] = useState<number>(0);
  const [singleEndDate, setSingleEndDate] = useState(new Date().toISOString().slice(0, 10));
  const [singleEmployees, setSingleEmployees] = useState<any[]>([]);
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [calcEndDate, setCalcEndDate] = useState("");
  const [previewData, setPreviewData] = useState<any>(null);
  const [showPreview, setShowPreview] = useState(false);
  const [progressData, setProgressData] = useState<any[]>([]);
  const [showProgress, setShowProgress] = useState(false);
  const isAdmin = user?.role === "warehouse_admin";

  useEffect(() => {
    if (!getToken()) { router.push("/login"); return; }
    setCalcEndDate(thaiYesterdayStr());
    initPage();
    loadProgress();
  }, []);

  async function loadProgress() {
    try {
      const r = await api.get<any>("/payroll/settlement-progress");
      setProgressData(r.data || []);
    } catch {}
  }

  // 首次进入：拉月份下拉 + 自动选中最近月份并加载
  async function initPage() {
    setMonthsLoading(true);
    try {
      const r = await api.get<any>("/payroll");
      const ms = r.months || [];
      setMonths(ms);
      if (ms.length > 0) {
        setSelectedMonth(ms[0]);
        loadRecordsByMonth(ms[0]);
      }
    } catch (err: any) {
      toast("error", err.message || "加载工资月份失败");
    }
    setMonthsLoading(false);
  }

  // 刷新月份下拉（计算/删除后调用）
  async function loadMonths() {
    try {
      const r = await api.get<any>("/payroll");
      setMonths(r.months || []);
    } catch (err: any) {
      toast("error", err.message || "加载工资月份失败");
    }
  }

  // 单条工资单的结算区间显示：「X月X日 到 X月X日」
  function recordDateLabel(r: any): string {
    const s = r.settle_start_date;
    const e = r.settle_end_date;
    if (s && e) {
      const fmt = (d: string) => {
        const [y, m, dd] = d.split("-").map(Number);
        return `${m}月${dd}日`;
      };
      return `${fmt(s)} 到 ${fmt(e)}`;
    }
    return `${r.period} ${r.half === "second_half" ? "下半月" : "上半月"}`;
  }

  async function loadRecordsByMonth(month?: string, vf?: string) {
    const m = month || selectedMonth;
    if (!m) return;
    const f = vf || voidFilter;
    setSelectedMonth(m);
    setLoading(true);
    setSelectedIds([]);
    try {
      const params = `settle_month=${m}&voided_filter=${f}`;
      const [recR, sumR] = await Promise.all([
        api.get<any>(`/payroll?${params}`),
        api.get<any>(`/payroll/summary?settle_month=${m}`),
      ]);
      setRecords(recR.data || []);
      setSummary(sumR);
    } catch (err: any) {
      toast("error", err.message || "加载工资数据失败");
    }
    setLoading(false);
  }

  async function handleCalculate() {
    if (!calcEndDate) { toast("error", "请选择结算日期"); return; }
    setCalculating(true);
    try {
      const r = await api.post<any>("/payroll/preview", { end_date: calcEndDate });
      setPreviewData(r);
      setShowPreview(true);
    } catch (err: any) {
      toast("error", err.message || "预览失败");
    }
    setCalculating(false);
  }

  async function confirmCalculate() {
    if (!calcEndDate) return;
    setShowPreview(false);
    setCalculating(true);
    try {
      const r = await api.post<any>("/payroll/calculate", { end_date: calcEndDate });
      toast("success", r.message || "计算完成");
      loadMonths();
      loadProgress();
      const m = calcEndDate.slice(0, 7);
      setSelectedMonth(m);
      loadRecordsByMonth(m);
    } catch (err: any) {
      toast("error", err.message || "计算失败");
    }
    setCalculating(false);
  }

  async function openSingleModal() {
    setShowSingleModal(true);
    setSingleEndDate(new Date().toISOString().slice(0, 10));
    try {
      const r = await api.get<any>("/employees?page_size=200&active_only=true");
      setSingleEmployees(r.data || []);
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
      const m = singleEndDate.slice(0, 7);
      setSelectedMonth(m);
      loadMonths();
      loadRecordsByMonth(m);
    } catch (err: any) { toast("error", err.message || "结算失败"); }
    setCalculating(false);
  }

  async function handleConfirm(recordId: number) {
    try {
      await api.post(`/payroll/${recordId}/confirm`);
      toast("success", "工资单已确认");
      loadRecordsByMonth();
    } catch (err: any) {
      toast("error", err.message || "确认失败");
    }
  }

  async function handleConfirmAll() {
    if (!selectedMonth) { toast("error", "请先选择月份"); return; }
    if (!confirm(`确定将 ${selectedMonth} 月 所有待确认工资单全部确认吗`)) return;
    try {
      const r = await api.post(`/payroll/confirm-all?settle_month=${selectedMonth}`);
      toast("success", r.message || "全部确认成功");
      loadRecordsByMonth();
    } catch (err: any) {
      toast("error", err.message || "确认失败");
    }
  }

  async function handleRecalcOne(recordId: number) {
    const reason = prompt("请填写作废原因：");
    if (reason === null) return;
    if (!reason.trim()) { toast("error", "请填写作废原因"); return; }
    setCalculating(true);
    try {
      const r = await api.post<any>(`/payroll/${recordId}/recalc`, { void_reason: reason });
      const msg = r.note ? `${r.message || "重算成功"}；${r.note}` : (r.message || "重算成功");
      toast("success", msg);
      loadRecordsByMonth();
      loadMonths();
      loadProgress();
    } catch (err: any) {
      toast("error", err.message || "重算失败");
    }
    setCalculating(false);
  }

  async function handleDisburse(recordId: number) {
    setDisbursing(recordId);
    try {
      const r = await api.post(`/payroll/${recordId}/disburse`, {});
      toast("success", r.message || "发放成功");
      loadRecordsByMonth();
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
  const psAdvanceDeduction = showPayslip?.advance_deduction ?? 0;
  const psRemainingDebt = showPayslip?.remaining_debt ?? 0;
  const psDailyHours = psDetail.daily_hours || [];
  const psLateDetails = psDetail.late_details || [];
  const psLateHalfCount = psDetail.late_half_count ?? 0;
  const psLateOneCount = psDetail.late_one_count ?? 0;
  const psTemplateType = psDetail.salary_template_type || (showPayslip?.employee_status === "trial" ? "daily" : "monthly");
  const psTemplateName = psDetail.salary_template_name || "";
  const psAttendanceDays = psDetail.attendance_days ?? (showPayslip?.attendance_days ?? 0);
  const psDailyWage = psDetail.daily_wage ?? showPayslip?.daily_wage ?? 0;
  const psBaseSalary = psDetail.base_salary ?? showPayslip?.base_salary ?? 0;
  const psLeaveDeduction = showPayslip?.leave_deduction ?? 0;
  const psAbsenceDeduction = showPayslip?.absence_deduction ?? 0;
  const psEarlyPenalty = showPayslip?.early_penalty ?? 0;
  const psAbsenceFine = showPayslip?.absence_fine ?? 0;
  const psFixedDeduction = showPayslip?.fixed_deduction ?? 0;
  const psTempDeduction = showPayslip?.temp_deduction ?? 0;
  const psFixedItems = psDetail.fixed_deductions || [];
  const psTempItems = psDetail.temp_deductions || [];
  const psEarlyDetails = psDetail.early_details || [];
  const psEarlyHalfCount = psDetail.early_half_count ?? 0;
  const psEarlyOneCount = psDetail.early_one_count ?? 0;
  const psPeriodBase = psDetail.period_base ?? null;
  const psPeriodDays = psDetail.period_days ?? null;
  const psHourlyFormula = psTemplateType === "monthly"
    ? `月薪 ${psBaseSalary} ÷ ${(showPayslip?.total_days_in_month ?? 30)} ÷ 8`
    : `日薪 ${psDailyWage} ÷ 8`;
  const psLateFormula = psLateHalfCount > 0 && psLateOneCount > 0
    ? `迟到半小时${psLateHalfCount}次 + 迟到1小时${psLateOneCount}次`
    : psLateHalfCount > 0
      ? `迟到半小时${psLateHalfCount}次`
      : psLateOneCount > 0
        ? `迟到1小时${psLateOneCount}次`
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
    const selectable = records.filter(r => !r.voided).map(r => r.id);
    setSelectedIds(prev => (prev.length === selectable.length && selectable.length > 0) ? [] : selectable);
  }

  async function handleBatchConfirm() {
    if (!selectedIds.length) return;
    setCalculating(true);
    try {
      const r = await api.post<any>("/payroll/batch-confirm", { record_ids: selectedIds });
      toast("success", r.message || `已确认 ${r.count} 条`);
      loadRecordsByMonth();
      loadProgress();
    } catch (err: any) { toast("error", err.message || "批量确认失败"); }
    setCalculating(false);
  }

  async function handleBatchDisburse() {
    if (!selectedIds.length) return;
    setCalculating(true);
    try {
      const r = await api.post<any>("/payroll/batch-disburse", { record_ids: selectedIds });
      toast("success", r.message || `已发放 ${r.count} 条`);
      loadRecordsByMonth();
      loadProgress();
    } catch (err: any) { toast("error", err.message || "批量发放失败"); }
    setCalculating(false);
  }

  async function handleBatchRecalc() {
    if (!selectedIds.length) return;
    const reason = prompt("请填写作废原因（对选中的所有工资单统一生效）：");
    if (reason === null) return;
    if (!reason.trim()) { toast("error", "请填写作废原因"); return; }
    setCalculating(true);
    try {
      const r = await api.post<any>("/payroll/batch-recalc", { record_ids: selectedIds, void_reason: reason });
      const skippedText = (r.skipped || []).map((s: any) => `${s.name}：${s.reason}`).join("；");
      const msg = r.message || "批量重算完成";
      toast("success", skippedText ? `${msg}；跳过：${skippedText}` : msg);
      loadRecordsByMonth();
      loadMonths();
      loadProgress();
    } catch (err: any) { toast("error", err.message || "批量重算失败"); }
    setCalculating(false);
  }

  return (
    <div>
      <div className="flex justify-between mb-4 flex-wrap gap-2 items-center">
        <h1 className="page-title flex items-center gap-2"><Calculator size={24}/>工资管理</h1>
        <div className="flex flex-col gap-2 items-end">
          {/* 第一组：算工资用 */}
          {isAdmin && (
            <div className="flex gap-2 items-center flex-wrap">
              <label className="text-sm text-gray-500">结算到哪天</label>
              <input type="date" className="border rounded-lg px-3 py-2 text-sm bg-white" value={calcEndDate}
                onChange={e => setCalcEndDate(e.target.value)} />
              <button onClick={() => setCalcEndDate(past15thStr())}
                className="border border-gray-300 text-gray-600 text-sm px-3 py-2 rounded-lg hover:bg-gray-50">15号</button>
              <button onClick={() => setCalcEndDate(pastMonthEndStr())}
                className="border border-gray-300 text-gray-600 text-sm px-3 py-2 rounded-lg hover:bg-gray-50">月末</button>
              <button onClick={handleCalculate}
                className="btn-primary flex items-center gap-1 text-sm px-4 py-2">
                <Calculator size={16}/> 计算工资
              </button>
              <button onClick={openSingleModal}
                className="border border-blue-300 text-blue-600 flex items-center gap-1 text-sm px-4 py-2 rounded-lg hover:bg-blue-50">
                <User size={16}/> 单人结算
              </button>
            </div>
          )}

          {/* 第二组：看列表用 */}
          <div className="flex gap-2 items-center flex-wrap">
            <label className="text-sm text-gray-500">查看月份</label>
            <select value={selectedMonth}
              onChange={e => {
                const v = e.target.value;
                setSelectedMonth(v);
                if (v) loadRecordsByMonth(v);
              }}
              className="border rounded-lg px-3 py-2 text-sm bg-white min-w-[160px]">
              <option value="">选择月份</option>
              {months.map((m: string) => (
                <option key={m} value={m}>{m}</option>
              ))}
            </select>
            <select value={voidFilter}
              onChange={e => {
                setVoidFilter(e.target.value);
                loadRecordsByMonth(selectedMonth, e.target.value);
              }}
              className="border rounded-lg px-3 py-2 text-sm bg-white">
              <option value="valid">只看有效</option>
              <option value="voided">只看已作废</option>
              <option value="all">全部</option>
            </select>
            {isAdmin && records.length > 0 && (
              <button onClick={handleConfirmAll}
                className="bg-green-500 text-white flex items-center gap-1 text-sm px-4 py-2 rounded-lg hover:bg-green-600">
                <CheckCircle size={16}/> 全部确认
              </button>
            )}
          </div>
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

      {/* 结算进度 */}
      <div className="bg-white rounded-xl border mb-3">
        <button onClick={() => setShowProgress(!showProgress)}
          className="w-full flex items-center justify-between px-4 py-3 text-sm font-medium text-gray-700 hover:bg-gray-50">
          <span className="flex items-center gap-2"><TrendingUp size={16} className="text-blue-500"/> 结算进度（{progressData.length} 人）</span>
          <span className="text-gray-400">{showProgress ? "收起" : "展开"}</span>
        </button>
        {showProgress && (
          <div className="border-t px-4 py-2 max-h-72 overflow-y-auto">
            {progressData.length === 0 ? (
              <div className="text-center py-6 text-gray-400 text-sm">暂无在职员工</div>
            ) : progressData.map((p: any) => (
              <div key={p.employee_id} className="flex justify-between items-center text-sm py-1.5 border-b border-gray-50">
                <span className="text-gray-700">{p.name}</span>
                <span className={p.settle_end_date ? "text-gray-500" : "text-red-500"}>
                  已结算到 {p.settle_end_date ? p.settle_end_date : "从未结算"}
                </span>
              </div>
            ))}
          </div>
        )}
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
            <button onClick={handleBatchRecalc} disabled={calculating}
              className="bg-amber-500 text-white px-3 py-1.5 rounded text-sm hover:bg-amber-600 disabled:opacity-50">批量重算</button>
          </div>
        </div>
      )}

      {/* Records Table */}
      {loading || monthsLoading ? (
        <div className="text-center py-12 text-gray-400">加载中...</div>
      ) : months.length === 0 ? (
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
                  <input type="checkbox" checked={records.length > 0 && selectedIds.length === records.filter(r => !r.voided).length && records.filter(r => !r.voided).length > 0}
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
                <tr key={r.id} className={`border-b ${r.voided ? "bg-gray-50 text-gray-400" : "border-gray-50 hover:bg-gray-50"}`}>
                  <td className="px-2 py-3 text-center">
                    <input type="checkbox" disabled={r.voided} checked={selectedIds.includes(r.id)}
                      onChange={() => toggleSelect(r.id)} className="w-4 h-4 cursor-pointer align-middle disabled:cursor-not-allowed" />
                  </td>
                  <td className="px-3 py-3 font-medium">
                    <span className={r.voided ? "text-gray-400" : ""}>{r.employee_name ?? "—"}</span>
                    {r.voided && (
                      <span className="ml-1 px-1.5 py-0.5 rounded bg-gray-200 text-gray-500 text-[10px] font-medium">已作废</span>
                    )}
                    <div className="text-[11px] text-gray-400 font-normal">{recordDateLabel(r)}</div>
                  </td>
                  <td className="px-3 py-3">
                    <span className={`px-2 py-0.5 rounded text-xs ${templateTypeBadge(r.detail?.salary_template_type)}`}>
                      {templateTypeLabel(r.detail?.salary_template_type) || (r.employee_status === "trial" ? "试用期" : "正式")}
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
                    {r.voided ? (
                      <span className="px-2 py-0.5 rounded text-xs font-medium bg-gray-200 text-gray-500">已作废</span>
                    ) : (
                      <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                        r.status === "confirmed" ? "bg-green-50 text-green-700" : "bg-amber-50 text-amber-700"
                      }`}>
                        {r.status === "confirmed" ? "已确认" : "待确认"}
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-3 text-center">
                    {r.voided ? (
                      <span className="text-gray-400 text-xs">—</span>
                    ) : r.disbursed ? (
                      <span className="bg-blue-50 text-blue-700 px-2 py-0.5 rounded text-xs font-medium">
                        已发放
                      </span>
                    ) : (
                      <span className="text-gray-400 text-xs">待发放</span>
                    )}
                  </td>
                  <td className="px-3 py-3 text-center">
                    <div className="flex items-center justify-center gap-2">
                      {!r.voided && r.status !== "confirmed" && isAdmin && (
                        <button onClick={() => handleConfirm(r.id)}
                          className="text-green-600 hover:text-green-800 text-xs font-medium"
                          title="确认">
                          <CheckCircle size={16}/>
                        </button>
                      )}
                      {!r.voided && r.status === "confirmed" && !r.disbursed && isAdmin && (
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
                      {!r.voided && isAdmin && (
                        <button onClick={() => handleRecalcOne(r.id)}
                          className="text-amber-500 hover:text-amber-700 text-xs font-medium"
                          title="重算">
                          <AlertTriangle size={14}/>
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
                <p className="text-xs text-gray-400 mt-1">从他上次结算的第二天开始算到截止日。</p>
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

      {/* 算工资预览 Modal */}
      {showPreview && previewData && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50 p-4" onClick={() => setShowPreview(false)}>
          <div className="bg-white rounded-2xl w-full max-w-lg shadow-xl max-h-[85vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
            <div className="bg-blue-500 text-white px-5 py-3 rounded-t-2xl flex items-center gap-2 sticky top-0 z-10">
              <Calculator size={20} /><span className="font-semibold">算工资预览</span>
              <button onClick={() => setShowPreview(false)} className="ml-auto text-2xl text-white/80 hover:text-white">&times;</button>
            </div>
            <div className="p-5 space-y-4">
              <div>
                <div className="text-sm text-gray-700">本次结算到 <b>{previewData.batch_end}</b></div>
                {previewData.cap_note && <div className="text-xs text-amber-600 mt-1">{previewData.cap_note}</div>}
              </div>

              <div>
                <div className="text-sm font-medium mb-2">一共会给 <b>{previewData.total_count}</b> 个人算</div>
                {(previewData.employees || []).map((e: any) => (
                  <div key={e.name} className="text-sm text-gray-700 py-1 border-b border-gray-50 flex justify-between">
                    <span>{e.name}</span>
                    <span className="text-gray-500">{e.start} 到 {e.end}</span>
                  </div>
                ))}
              </div>

              {(previewData.skipped || []).length > 0 && (
                <div>
                  <div className="text-sm font-medium mb-2">已结清 跳过</div>
                  {(previewData.skipped || []).map((s: string, i: number) => (
                    <div key={i} className="text-sm text-gray-600 py-1 border-b border-gray-50">{s}</div>
                  ))}
                </div>
              )}

              {(previewData.problems || []).length > 0 && (
                <div>
                  <div className="text-sm font-medium mb-2 text-red-600">有问题 不能计算</div>
                  {(previewData.problems || []).map((p: any, i: number) => (
                    <div key={i} className="text-sm text-red-600 py-1 border-b border-gray-50">{p.name} · {p.reason}</div>
                  ))}
                </div>
              )}
            </div>
            <div className="border-t px-5 py-4 bg-gray-50 rounded-b-2xl flex justify-end gap-3">
              {(previewData.problems || []).length > 0 ? (
                <button onClick={() => setShowPreview(false)} className="btn-primary text-sm px-6 py-2">知道了</button>
              ) : (
                <>
                  <button onClick={() => setShowPreview(false)} className="btn-secondary text-sm px-6 py-2">取消</button>
                  <button onClick={confirmCalculate} disabled={calculating} className="btn-primary text-sm px-6 py-2">确认计算</button>
                </>
              )}
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
                <p className="text-sm text-gray-500">{recordDateLabel(showPayslip)} 工资单</p>
                <span className={`inline-block mt-1 px-2 py-0.5 rounded text-xs font-medium ${templateTypeBadge(psTemplateType)}`}>
                  {templateTypeLabel(psTemplateType) || (showPayslip.employee_status === "trial" ? "试用期" : "正式员工")}
                </span>
                {showPayslip.voided && (
                  <span className="inline-block ml-1 mt-1 px-2 py-0.5 rounded text-xs font-medium bg-gray-200 text-gray-600">已作废</span>
                )}
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

              {/* Salary breakdown（按薪资模板） */}
              <div className="space-y-2">
                {psTemplateName && (
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-500">薪资模板</span>
                    <span>{psTemplateName}</span>
                  </div>
                )}
                {psTemplateType === "hourly" ? (
                  <>
                    <div className="flex justify-between text-sm">
                      <button onClick={() => setDailyDetailOpen(true)} className="text-blue-600 hover:underline cursor-pointer">上班工时</button>
                      <span>{psWorkHours} 小时</span>
                    </div>
                    <div className="flex justify-between text-sm">
                      <span className="text-gray-500">时薪</span>
                      <span>{psHourlyRate} <span className="text-gray-400 text-xs">({psHourlyFormula})</span></span>
                    </div>
                  </>
                ) : psTemplateType === "monthly" ? (
                  <div className="flex justify-between text-sm">
                    <button onClick={() => setDailyDetailOpen(true)} className="text-blue-600 hover:underline cursor-pointer">周期基础</button>
                    <span>{psPeriodBase != null ? psPeriodBase.toLocaleString() : psBaseSalary.toLocaleString()} <span className="text-gray-400 text-xs">(月薪 {psBaseSalary} × {psPeriodDays ?? 0}/{showPayslip?.total_days_in_month ?? 30} 天)</span></span>
                  </div>
                ) : (
                  <div className="flex justify-between text-sm">
                    <button onClick={() => setDailyDetailOpen(true)} className="text-blue-600 hover:underline cursor-pointer">出勤天数</button>
                    <span>{psAttendanceDays} 天 <span className="text-gray-400 text-xs">(日薪 {psDailyWage})</span></span>
                  </div>
                )}
                <div className="flex justify-between text-sm">
                  <span className="text-gray-500">上班工资</span>
                  <span><b>{psWorkPay.toLocaleString()}</b></span>
                </div>
                {psTemplateType === "monthly" && psLeaveDeduction > 0 && (
                  <div className="flex justify-between text-sm text-red-500">
                    <span>请假扣款</span><span>-{psLeaveDeduction.toLocaleString()}</span>
                  </div>
                )}
                {psTemplateType === "monthly" && psAbsenceDeduction > 0 && (
                  <div className="flex justify-between text-sm text-red-500">
                    <span>缺勤扣款</span><span>-{psAbsenceDeduction.toLocaleString()}</span>
                  </div>
                )}
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
                {psEarlyPenalty > 0 && (
                  <div className="flex justify-between text-sm text-red-500">
                    <span>早退扣款</span>
                    <span>-{psEarlyPenalty}{psEarlyHalfCount > 0 || psEarlyOneCount > 0 ? <span className="text-red-300 text-xs"> ({psEarlyHalfCount > 0 ? `早退半小时${psEarlyHalfCount}次` : ""}{psEarlyHalfCount > 0 && psEarlyOneCount > 0 ? " + " : ""}{psEarlyOneCount > 0 ? `早退1小时${psEarlyOneCount}次` : ""})</span> : null}</span>
                  </div>
                )}
                {psAbsenceFine > 0 && (
                  <div className="flex justify-between text-sm text-red-500">
                    <span>旷工扣款</span>
                    <span>-{psAbsenceFine.toLocaleString()}</span>
                  </div>
                )}
                {psFixedItems.map((f: any) => (
                  <div key={f.id || f.name} className="flex justify-between text-sm text-red-500">
                    <span>固定扣款 · {f.name}</span>
                    <span>-{Number(f.deducted ?? f.amount ?? 0).toLocaleString()}</span>
                  </div>
                ))}
                {psTempItems.map((t: any) => (
                  <div key={t.id || (t.reason + t.date)} className="flex justify-between text-sm text-red-500">
                    <span>临时扣款 · {t.reason}</span>
                    <span>-{Number(t.amount ?? 0).toLocaleString()}</span>
                  </div>
                ))}
                {psAdvanceDeduction > 0 && (
                  <div className="flex justify-between text-sm text-red-500">
                    <span>预支扣款</span>
                    <span>-{psAdvanceDeduction.toLocaleString()}</span>
                  </div>
                )}
                <div className="flex justify-between text-sm text-gray-500">
                  <span>剩余欠款</span>
                  <span>{psRemainingDebt.toLocaleString()}</span>
                </div>
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
                    <span className="text-gray-400 text-xs font-normal ml-1">({psWorkPay} + {psOvertimePay} - {psTotalDeductions} - {psAdvanceDeduction})</span>
                  </span>
                </div>
              </div>

              {/* Status & Disbursement */}
              <div className="bg-gray-50 rounded-lg p-3 space-y-1 text-sm">
                <div className="flex justify-between">
                  <span className="text-gray-400">确认状态</span>
                  <span className={showPayslip.voided ? "text-gray-400 font-medium" : showPayslip.status === "confirmed" ? "text-green-600 font-medium" : "text-amber-600"}>
                    {showPayslip.voided ? "已作废" : showPayslip.status === "confirmed" ? "已确认" : "待确认"}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">发放状态</span>
                  {showPayslip.voided ? (
                    <span className="text-gray-400">—</span>
                  ) : showPayslip.disbursed ? (
                    <span className="text-blue-600 font-medium">
                      已发放 {showPayslip.disbursed_at ? new Date(showPayslip.disbursed_at).toLocaleDateString("zh-CN") : ""}
                    </span>
                  ) : (
                    <span className="text-gray-400">待发放</span>
                  )}
                </div>
              </div>

              {/* 作废信息 */}
              {(showPayslip.voided || showPayslip.recalc_from_id || showPayslip.recalc_to_id) && (
                <div className="border border-gray-200 rounded-lg p-3 space-y-1 text-sm">
                  <div className="text-xs text-gray-400 font-medium mb-1">作废 / 重算信息</div>
                  {showPayslip.voided && (
                    <>
                      <div className="flex justify-between">
                        <span className="text-gray-400">作废人</span>
                        <span className="text-gray-700">{showPayslip.voided_by_name || "—"}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-gray-400">作废时间</span>
                        <span className="text-gray-700">{showPayslip.voided_at ? new Date(showPayslip.voided_at).toLocaleString("zh-CN", { timeZone: "Asia/Bangkok" }) : "—"}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-gray-400">作废原因</span>
                        <span className="text-gray-700">{showPayslip.void_reason || "—"}</span>
                      </div>
                      {showPayslip.recalc_to_id && (
                        <div className="flex justify-between">
                          <span className="text-gray-400">重算成了</span>
                          <span className="text-gray-700">工资单 #{showPayslip.recalc_to_id}</span>
                        </div>
                      )}
                    </>
                  )}
                  {showPayslip.recalc_from_id && (
                    <div className="flex justify-between">
                      <span className="text-gray-400">从哪张单重算</span>
                      <span className="text-gray-700">工资单 #{showPayslip.recalc_from_id}</span>
                    </div>
                  )}
                </div>
              )}

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

"use client";
import { useEffect, useState, useCallback } from "react";
import { api, getToken } from "@/lib/api";
import { useToast } from "@/components/ui/Toast";
import { useAuth } from "@/hooks/useAuth";
import { useRouter } from "next/navigation";
import { Calculator, CheckCircle, Trash2, FileText, TrendingUp, TrendingDown, DollarSign, AlertTriangle, Banknote, Eye } from "lucide-react";

export default function PayrollPage() {
  const { toast } = useToast(); const { user } = useAuth(); const router = useRouter();
  const [records, setRecords] = useState<any[]>([]);
  const [summary, setSummary] = useState<any>(null);
  const [periods, setPeriods] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [calculating, setCalculating] = useState(false);
  const [selectedPeriod, setSelectedPeriod] = useState("");
  const [calcPeriod, setCalcPeriod] = useState(new Date().toISOString().slice(0, 7));
  const [showCalcModal, setShowCalcModal] = useState(false);
  const [showPayslip, setShowPayslip] = useState<any>(null);
  const [disbursing, setDisbursing] = useState<number | null>(null);
  const isAdmin = user?.role === "warehouse_admin";

  useEffect(() => {
    if (!getToken()) { router.push("/login"); return; }
    loadPeriods();
    // Default to current month
    const now = new Date().toISOString().slice(0, 7);
    setSelectedPeriod(now);
  }, []);

  useEffect(() => {
    if (selectedPeriod) loadRecords(selectedPeriod);
  }, [selectedPeriod]);

  async function loadPeriods() {
    try {
      const r = await api.get<any>("/payroll");
      setPeriods(r.periods || []);
      if (r.periods?.length > 0 && !selectedPeriod) {
        setSelectedPeriod(r.periods[0]);
      }
    } catch {}
  }

  async function loadRecords(period: string) {
    setLoading(true);
    try {
      const [recR, sumR] = await Promise.all([
        api.get<any>(`/payroll?period=${period}`),
        api.get<any>(`/payroll/summary?period=${period}`),
      ]);
      setRecords(recR.data || []);
      setSummary(sumR);
    } catch {}
    setLoading(false);
  }

  async function handleCalculate() {
    setCalculating(true);
    try {
      await api.post("/payroll/calculate", { period: calcPeriod });
      toast("success", `${calcPeriod} 工资计算完成`);
      setShowCalcModal(false);
      setSelectedPeriod(calcPeriod);
      loadPeriods();
    } catch (err: any) {
      toast("error", err.message || "计算失败");
    }
    setCalculating(false);
  }

  async function handleConfirm(recordId: number) {
    try {
      await api.post(`/payroll/${recordId}/confirm`);
      toast("success", "工资单已确认");
      loadRecords(selectedPeriod);
    } catch (err: any) {
      toast("error", err.message || "确认失败");
    }
  }

  async function handleConfirmAll() {
    if (!confirm(`确定将 ${selectedPeriod} 所有待确认工资单全部确认吗？`)) return;
    try {
      const r = await api.post(`/payroll/confirm-all?period=${selectedPeriod}`);
      toast("success", r.message || "全部确认成功");
      loadRecords(selectedPeriod);
    } catch (err: any) {
      toast("error", err.message || "确认失败");
    }
  }

  async function handleDelete(recordId: number) {
    if (!confirm("确定删除该工资记录吗？")) return;
    try {
      await api.delete(`/payroll/${recordId}`);
      toast("success", "已删除");
      loadRecords(selectedPeriod);
      loadPeriods();
    } catch (err: any) {
      toast("error", err.message || "删除失败");
    }
  }

  async function handleRecalculate() {
    if (!confirm(`将删除 ${selectedPeriod} 全部工资记录并重新计算，确定吗？`)) return;
    try {
      await api.delete(`/payroll/period/${selectedPeriod}`);
      setRecords([]);
      setCalcPeriod(selectedPeriod);
      setShowCalcModal(true);
    } catch (err: any) {
      toast("error", err.message || "操作失败");
    }
  }

  async function handleDisburse(recordId: number) {
    setDisbursing(recordId);
    try {
      const r = await api.post(`/payroll/${recordId}/disburse`, {});
      toast("success", r.message || "发放成功");
      loadRecords(selectedPeriod);
    } catch (err: any) {
      toast("error", err.message || "发放失败");
    }
    setDisbursing(null);
  }

  function viewPayslip(record: any) {
    setShowPayslip(record);
  }

  return (
    <div>
      <div className="flex justify-between mb-4 flex-wrap gap-2 items-center">
        <h1 className="page-title flex items-center gap-2"><Calculator size={24}/>工资管理</h1>
        <div className="flex gap-2 items-center">
          {/* Period selector */}
          <select value={selectedPeriod} onChange={e => setSelectedPeriod(e.target.value)}
            className="border rounded-lg px-3 py-2 text-sm bg-white min-w-[120px]">
            <option value="">选择月份</option>
            {periods.map(p => <option key={p} value={p}>{p}</option>)}
            {!periods.includes(selectedPeriod) && selectedPeriod && (
              <option value={selectedPeriod}>{selectedPeriod}</option>
            )}
          </select>
          {isAdmin && (
            <>
              <button onClick={() => { setCalcPeriod(new Date().toISOString().slice(0, 7)); setShowCalcModal(true); }}
                className="btn-primary flex items-center gap-1 text-sm px-4 py-2">
                <Calculator size={16}/> 计算工资
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
      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
          <div className="bg-white rounded-xl border p-4">
            <p className="text-xs text-gray-400">总人数</p>
            <p className="text-2xl font-bold text-gray-800">{summary.employee_count}</p>
            <p className="text-xs text-gray-400">{summary.confirmed_count}已确认 / {summary.pending_count}待确认</p>
          </div>
          <div className="bg-white rounded-xl border p-4">
            <p className="text-xs text-gray-400">应发总额</p>
            <p className="text-2xl font-bold text-blue-600">{summary.total_gross?.toLocaleString()}</p>
          </div>
          <div className="bg-white rounded-xl border p-4">
            <p className="text-xs text-gray-400">加班费合计</p>
            <p className="text-2xl font-bold text-green-600">{summary.total_overtime?.toLocaleString()}</p>
          </div>
          <div className="bg-white rounded-xl border p-4">
            <p className="text-xs text-gray-400">实发总额</p>
            <p className="text-2xl font-bold text-orange-600">{summary.total_net?.toLocaleString()}</p>
          </div>
        </div>
      )}

      {/* Records Table */}
      {loading ? (
        <div className="text-center py-12 text-gray-400">加载中...</div>
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
                  <td className="px-3 py-3 font-medium">{r.employee_name}</td>
                  <td className="px-3 py-3">
                    <span className={`px-2 py-0.5 rounded text-xs ${
                      r.employee_status === "trial" ? "bg-amber-50 text-amber-700" : "bg-blue-50 text-blue-700"
                    }`}>
                      {r.employee_status === "trial" ? "试用期" : "正式"}
                    </span>
                  </td>
                  <td className="px-3 py-3 text-center">{r.attendance_days}</td>
                  <td className="px-3 py-3 text-center">{r.leave_days}</td>
                  <td className="px-3 py-3 text-center">{r.rest_days}</td>
                  <td className="px-3 py-3 text-center">{r.absence_days}</td>
                  <td className="px-3 py-3 text-right">{r.base_pay?.toLocaleString()}</td>
                  <td className="px-3 py-3 text-right text-green-600">{r.overtime_pay > 0 ? r.overtime_pay.toLocaleString() : "-"}</td>
                  <td className="px-3 py-3 text-right text-red-500">{r.total_deductions > 0 ? r.total_deductions.toLocaleString() : "-"}</td>
                  <td className="px-3 py-3 text-right font-bold">{r.net_pay?.toLocaleString()}</td>
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

      {/* Calculate Modal */}
      {showCalcModal && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50 p-4" onClick={() => setShowCalcModal(false)}>
          <div className="bg-white rounded-2xl w-full max-w-sm shadow-xl" onClick={e => e.stopPropagation()}>
            <div className="bg-blue-500 text-white px-5 py-3 rounded-t-2xl flex items-center gap-2">
              <Calculator size={20} />
              <span className="font-semibold">计算工资</span>
            </div>
            <div className="p-5 space-y-4">
              <div>
                <label className="form-label text-sm font-medium text-gray-600 mb-1 block">选择月份</label>
                <input type="month" className="form-input text-base py-2.5 w-full" value={calcPeriod}
                  onChange={e => setCalcPeriod(e.target.value)} />
              </div>
              <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 text-sm text-amber-700">
                <p>系统将根据打卡记录自动统计每位员工的出勤天数，并计算工资。</p>
                <p className="mt-1 text-xs text-amber-500">计算完成后请核对并确认工资单。</p>
              </div>
            </div>
            <div className="border-t px-5 py-4 bg-gray-50 rounded-b-2xl flex justify-end gap-3">
              <button onClick={() => setShowCalcModal(false)} className="btn-secondary text-sm px-6 py-2">取消</button>
              <button onClick={handleCalculate} disabled={calculating}
                className="btn-primary text-sm px-6 py-2 flex items-center gap-1">
                {calculating ? "计算中..." : "开始计算"}
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
                <p className="text-sm text-gray-500">{showPayslip.period} 工资单</p>
                <span className={`inline-block mt-1 px-2 py-0.5 rounded text-xs font-medium ${
                  showPayslip.employee_status === "trial" ? "bg-amber-50 text-amber-700" : "bg-blue-50 text-blue-700"
                }`}>
                  {showPayslip.employee_status === "trial" ? "试用期" : "正式员工"}
                </span>
              </div>

              {/* Attendance */}
              <div className="bg-gray-50 rounded-lg p-3">
                <p className="text-xs text-gray-400 mb-2">出勤统计 ({showPayslip.total_days_in_month}天/月)</p>
                <div className="grid grid-cols-4 gap-2 text-center">
                  <div><p className="text-lg font-bold text-green-600">{showPayslip.attendance_days}</p><p className="text-xs text-gray-400">出勤</p></div>
                  <div><p className="text-lg font-bold text-amber-600">{showPayslip.leave_days}</p><p className="text-xs text-gray-400">请假</p></div>
                  <div><p className="text-lg font-bold text-blue-600">{showPayslip.rest_days}</p><p className="text-xs text-gray-400">休息</p></div>
                  <div><p className="text-lg font-bold text-red-600">{showPayslip.absence_days}</p><p className="text-xs text-gray-400">缺勤</p></div>
                </div>
              </div>

              {/* Salary breakdown */}
              <div className="space-y-2">
                {showPayslip.employee_status === "trial" ? (
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-500">日薪 × 出勤天数</span>
                    <span>{showPayslip.daily_wage} × {showPayslip.attendance_days} = <b>{showPayslip.base_pay}</b></span>
                  </div>
                ) : (
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-500">底薪 ÷ 有效天数 × 出勤</span>
                    <span>{showPayslip.base_salary} ÷ {showPayslip.total_days_in_month - 2} × {showPayslip.attendance_days} = <b>{showPayslip.base_pay}</b></span>
                  </div>
                )}
                {showPayslip.overtime_pay > 0 && (
                  <div className="flex justify-between text-sm text-green-600">
                    <span>加班费 ({showPayslip.overtime_hours}h)</span>
                    <span>+{showPayslip.overtime_pay}</span>
                  </div>
                )}
                {showPayslip.late_penalty > 0 && (
                  <div className="flex justify-between text-sm text-red-500">
                    <span>迟到扣款</span>
                    <span>-{showPayslip.late_penalty}</span>
                  </div>
                )}
                {showPayslip.leave_deduction > 0 && (
                  <div className="flex justify-between text-sm text-red-500">
                    <span>请假扣款 ({showPayslip.leave_days}天)</span>
                    <span>-{showPayslip.leave_deduction}</span>
                  </div>
                )}
                {showPayslip.absence_deduction > 0 && (
                  <div className="flex justify-between text-sm text-red-500">
                    <span>缺勤扣款 ({showPayslip.absence_days}天)</span>
                    <span>-{showPayslip.absence_deduction}</span>
                  </div>
                )}
              </div>

              {/* Total */}
              <div className="border-t pt-3 space-y-1">
                <div className="flex justify-between text-sm text-gray-500">
                  <span>应发合计</span><span>{showPayslip.gross_pay}</span>
                </div>
                <div className="flex justify-between text-sm text-gray-500">
                  <span>扣款合计</span><span className="text-red-500">-{showPayslip.total_deductions}</span>
                </div>
                <div className="flex justify-between text-base font-bold pt-1 border-t">
                  <span>实发工资</span>
                  <span className="text-blue-600 text-lg">{showPayslip.net_pay?.toLocaleString()} 泰铢</span>
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
                  <Banknote size={18} /> 现金发放 {showPayslip.net_pay?.toLocaleString()} 泰铢
                </button>
              )}
            </div>
            <div className="border-t px-5 py-3 bg-gray-50 rounded-b-2xl text-center">
              <button onClick={() => setShowPayslip(null)} className="text-sm text-gray-400">关闭</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

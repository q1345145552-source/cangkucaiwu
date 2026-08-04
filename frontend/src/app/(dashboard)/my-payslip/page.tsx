"use client";
import { useEffect, useState } from "react";
import { api, getToken } from "@/lib/api";
import { useToast } from "@/components/ui/Toast";
import { useRouter } from "next/navigation";
import { FileText, DollarSign, ChevronRight } from "lucide-react";

export default function MyPayslipPage() {
  const { toast } = useToast(); const router = useRouter();
  const [records, setRecords] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<any>(null);

  useEffect(() => {
    if (!getToken()) { router.push("/login"); return; }
    load();
  }, []);

  async function load() {
    setLoading(true);
    try {
      const r = await api.get<any>("/payroll/my-payslip");
      setRecords(r.data || []);
    } catch {}
    setLoading(false);
  }

  return (
    <div>
      <h1 className="page-title flex items-center gap-2 mb-4"><FileText size={24}/>我的工资单</h1>

      {loading ? (
        <div className="text-center py-12 text-gray-400">加载中...</div>
      ) : records.length === 0 ? (
        <div className="text-center py-12 text-gray-400 bg-white rounded-xl border">
          <DollarSign size={40} className="mx-auto mb-3 text-gray-300"/>
          <p>暂无工资单</p>
          <p className="text-sm mt-1">管理员计算工资后将在此显示</p>
        </div>
      ) : (
        <div className="space-y-3">
          {records.map((r: any) => (
            <div key={r.id} onClick={() => setSelected(r)}
              className="bg-white rounded-xl border p-4 hover:shadow-md cursor-pointer transition-shadow">
              <div className="flex justify-between items-center">
                <div>
                  <p className="font-medium text-gray-800">{r.period} 工资单</p>
                  <div className="flex gap-2 mt-1">
                    <span className={`px-2 py-0.5 rounded text-xs ${
                      r.status === "confirmed" ? "bg-green-50 text-green-700" : "bg-amber-50 text-amber-700"
                    }`}>
                      {r.status === "confirmed" ? "已确认" : "待确认"}
                    </span>
                    {r.disbursed && (
                      <span className="px-2 py-0.5 rounded text-xs bg-blue-50 text-blue-700">已发放</span>
                    )}
                  </div>
                </div>
                <div className="text-right">
                  <p className="text-xl font-bold text-blue-600">{r.net_pay?.toLocaleString()} 泰铢</p>
                  <ChevronRight size={16} className="text-gray-300 ml-auto mt-1"/>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Payslip Detail Modal */}
      {selected && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50 p-4" onClick={() => setSelected(null)}>
          <div className="bg-white rounded-2xl w-full max-w-md shadow-xl max-h-[90vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
            <div className="bg-blue-500 text-white px-5 py-3 rounded-t-2xl flex items-center gap-2 sticky top-0">
              <FileText size={20} />
              <span className="font-semibold">{selected.period} 工资单</span>
            </div>
            <div className="p-5 space-y-3">
              <div className="text-center pb-3 border-b">
                <h3 className="text-lg font-bold">{selected.employee_name}</h3>
                <span className={`inline-block mt-1 px-2 py-0.5 rounded text-xs font-medium ${
                  selected.employee_status === "trial" ? "bg-amber-50 text-amber-700" : "bg-blue-50 text-blue-700"
                }`}>
                  {selected.employee_status === "trial" ? "试用期" : "正式员工"}
                </span>
              </div>

              <div className="bg-gray-50 rounded-lg p-3">
                <p className="text-xs text-gray-400 mb-2">出勤统计 ({selected.total_days_in_month}天/月)</p>
                <div className="grid grid-cols-4 gap-2 text-center">
                  <div><p className="text-lg font-bold text-green-600">{selected.attendance_days}</p><p className="text-xs text-gray-400">出勤</p></div>
                  <div><p className="text-lg font-bold text-amber-600">{selected.leave_days}</p><p className="text-xs text-gray-400">请假</p></div>
                  <div><p className="text-lg font-bold text-blue-600">{selected.rest_days}</p><p className="text-xs text-gray-400">休息</p></div>
                  <div><p className="text-lg font-bold text-red-600">{selected.absence_days}</p><p className="text-xs text-gray-400">缺勤</p></div>
                </div>
              </div>

              <div className="space-y-2">
                {selected.employee_status === "trial" ? (
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-500">日薪 × 出勤天数</span>
                    <span>{selected.daily_wage} × {selected.attendance_days} = <b>{selected.base_pay}</b></span>
                  </div>
                ) : (
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-500">底薪计算</span>
                    <span><b>{selected.base_pay}</b></span>
                  </div>
                )}
                {selected.overtime_pay > 0 && (
                  <div className="flex justify-between text-sm text-green-600"><span>加班费 ({selected.overtime_hours}h)</span><span>+{selected.overtime_pay}</span></div>
                )}
                {selected.late_penalty > 0 && (
                  <div className="flex justify-between text-sm text-red-500"><span>迟到扣款</span><span>-{selected.late_penalty}</span></div>
                )}
                {selected.leave_deduction > 0 && (
                  <div className="flex justify-between text-sm text-red-500"><span>请假扣款</span><span>-{selected.leave_deduction}</span></div>
                )}
              </div>

              <div className="border-t pt-3 space-y-1">
                <div className="flex justify-between text-sm text-gray-500"><span>应发合计</span><span>{selected.gross_pay}</span></div>
                <div className="flex justify-between text-sm text-gray-500"><span>扣款合计</span><span className="text-red-500">-{selected.total_deductions}</span></div>
                <div className="flex justify-between text-base font-bold pt-1 border-t">
                  <span>实发工资</span>
                  <span className="text-blue-600 text-lg">{selected.net_pay?.toLocaleString()} 泰铢</span>
                </div>
              </div>

              <div className="bg-gray-50 rounded-lg p-3 text-sm">
                <div className="flex justify-between">
                  <span className="text-gray-400">状态</span>
                  <span className={selected.disbursed ? "text-blue-600 font-medium" : "text-amber-600"}>
                    {selected.disbursed ? "已发放" : selected.status === "confirmed" ? "已确认待发放" : "待确认"}
                  </span>
                </div>
                {selected.disbursed && selected.disbursed_at && (
                  <div className="flex justify-between mt-1">
                    <span className="text-gray-400">发放时间</span>
                    <span>{new Date(selected.disbursed_at).toLocaleString("zh-CN")}</span>
                  </div>
                )}
              </div>
            </div>
            <div className="border-t px-5 py-3 bg-gray-50 rounded-b-2xl text-center">
              <button onClick={() => setSelected(null)} className="text-sm text-gray-400">关闭</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

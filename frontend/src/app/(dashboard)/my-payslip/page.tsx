"use client";
import { useEffect, useState } from "react";
import { api, getToken } from "@/lib/api";
import { useToast } from "@/components/ui/Toast";
import { useI18n } from "@/hooks/useI18n";
import { useRouter } from "next/navigation";
import { FileText, DollarSign, ChevronRight } from "lucide-react";

// 薪资模板类型 → 标签（工资按模板算，不再按试用期/正式分段）
const TEMPLATE_TYPE_LABELS: Record<string, string> = { hourly: "按小时", daily: "按天", monthly: "按月" };
function templateTypeLabel(tt?: string): string {
  return tt ? (TEMPLATE_TYPE_LABELS[tt] || tt) : "";
}
function templateTypeBadge(tt?: string): string {
  if (tt === "monthly") return "bg-blue-50 text-blue-700";
  if (tt === "hourly") return "bg-teal-50 text-teal-700";
  return "bg-amber-50 text-amber-700";
}

export default function MyPayslipPage() {
  const { toast } = useToast(); const { t } = useI18n(); const router = useRouter();
  const [records, setRecords] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<any>(null);
  const [myDebt, setMyDebt] = useState<any[]>([]);

  useEffect(() => {
    if (!getToken()) { router.push("/login"); return; }
    load();
    loadDebt();
  }, []);

  async function load() {
    setLoading(true);
    try {
      const r = await api.get<any>("/payroll/my-payslip");
      setRecords(r.data || []);
    } catch {}
    setLoading(false);
  }

  async function loadDebt() {
    try {
      const r = await api.get<any>("/employee-advances/my-debt");
      setMyDebt(r.total_by_currency || []);
    } catch {}
  }

  return (
    <div>
      <h1 className="page-title flex items-center gap-2 mb-4"><FileText size={24}/>{t("payslip_title")}</h1>

      {/* 我的欠款 */}
      <div className="bg-white rounded-xl border p-4 mb-4">
        <p className="text-sm font-semibold text-gray-700 mb-2">{t("my_debt")}</p>
        {myDebt.length === 0 ? (
          <p className="text-sm text-gray-400">0</p>
        ) : (
          <div className="flex flex-wrap gap-4">
            {myDebt.map((d: any) => (
              <div key={d.currency}>
                <p className="text-2xl font-bold text-red-600">{d.total?.toLocaleString()}</p>
                <p className="text-xs text-gray-400">{d.currency}</p>
              </div>
            ))}
          </div>
        )}
      </div>

      {loading ? (
        <div className="text-center py-12 text-gray-400">{t("loading")}</div>
      ) : records.length === 0 ? (
        <div className="text-center py-12 text-gray-400 bg-white rounded-xl border">
          <DollarSign size={40} className="mx-auto mb-3 text-gray-300"/>
          <p>{t("no_payslip")}</p>
          <p className="text-sm mt-1">{t("no_payslip_hint")}</p>
        </div>
      ) : (
        <div className="space-y-3">
          {records.map((r: any) => (
            <div key={r.id} onClick={() => setSelected(r)}
              className="bg-white rounded-xl border p-4 hover:shadow-md cursor-pointer transition-shadow">
              <div className="flex justify-between items-center">
                <div>
                  <p className="font-medium text-gray-800">{t("payslip_label").replace("{period}", r.period)}</p>
                  <div className="flex gap-2 mt-1">
                    <span className={`px-2 py-0.5 rounded text-xs ${
                      r.status === "confirmed" ? "bg-green-50 text-green-700" : "bg-amber-50 text-amber-700"
                    }`}>
                      {r.status === "confirmed" ? t("confirmed") : t("pending_confirm")}
                    </span>
                    {r.disbursed && (
                      <span className="px-2 py-0.5 rounded text-xs bg-blue-50 text-blue-700">{t("disbursed")}</span>
                    )}
                  </div>
                </div>
                <div className="text-right">
                  <p className="text-xl font-bold text-blue-600">{r.net_pay?.toLocaleString()} {t("baht")}</p>
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
              <span className="font-semibold">{t("payslip_label").replace("{period}", selected.period)}</span>
            </div>
            <div className="p-5 space-y-3">
              <div className="text-center pb-3 border-b">
                <h3 className="text-lg font-bold">{selected.employee_name}</h3>
                <span className={`inline-block mt-1 px-2 py-0.5 rounded text-xs font-medium ${templateTypeBadge(selected.detail?.salary_template_type)}`}>
                  {templateTypeLabel(selected.detail?.salary_template_type) || (selected.employee_status === "trial" ? t("trial_status") : t("regular_status"))}
                </span>
              </div>

              <div className="bg-gray-50 rounded-lg p-3">
                <p className="text-xs text-gray-400 mb-2">{t("attendance_title")} ({t("days_per_month").replace("{d}", String(selected.total_days_in_month))})</p>
                <div className="grid grid-cols-4 gap-2 text-center">
                  <div><p className="text-lg font-bold text-green-600">{selected.attendance_days}</p><p className="text-xs text-gray-400">{t("attendance_days")}</p></div>
                  <div><p className="text-lg font-bold text-amber-600">{selected.leave_days}</p><p className="text-xs text-gray-400">{t("leave_days")}</p></div>
                  <div><p className="text-lg font-bold text-blue-600">{selected.rest_days}</p><p className="text-xs text-gray-400">{t("rest_days")}</p></div>
                  <div><p className="text-lg font-bold text-red-600">{selected.absence_days}</p><p className="text-xs text-gray-400">{t("absence_days")}</p></div>
                </div>
              </div>

              <div className="space-y-2">
                {selected.detail?.salary_template_type === "hourly" ? (
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-500">{t("hourly_rate")}</span>
                    <span>{(selected.detail?.work_hours ?? 0)} 小时 × {(selected.detail?.hourly_rate ?? 0)} = <b>{selected.base_pay}</b></span>
                  </div>
                ) : selected.detail?.salary_template_type === "monthly" ? (
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-500">{t("base_salary_calc")}</span>
                    <span><b>{selected.base_pay}</b></span>
                  </div>
                ) : (
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-500">{t("daily_wage_x_attendance")}</span>
                    <span>{selected.daily_wage} × {selected.attendance_days} = <b>{selected.base_pay}</b></span>
                  </div>
                )}
                {selected.overtime_pay > 0 && (
                  <div className="flex justify-between text-sm text-green-600"><span>{t("overtime_pay")} ({selected.overtime_hours}h)</span><span>+{selected.overtime_pay}</span></div>
                )}
                {selected.late_penalty > 0 && (
                  <div className="flex justify-between text-sm text-red-500"><span>{t("late_penalty")}</span><span>-{selected.late_penalty}</span></div>
                )}
                {selected.leave_deduction > 0 && (
                  <div className="flex justify-between text-sm text-red-500"><span>{t("leave_deduction")}</span><span>-{selected.leave_deduction}</span></div>
                )}
                {selected.absence_deduction > 0 && (
                  <div className="flex justify-between text-sm text-red-500"><span>{t("absence_deduction")}</span><span>-{selected.absence_deduction}</span></div>
                )}
                {selected.advance_deduction > 0 && (
                  <div className="flex justify-between text-sm text-red-500"><span>{t("advance_deduction")}</span><span>-{selected.advance_deduction}</span></div>
                )}
                <div className="flex justify-between text-sm text-gray-500"><span>{t("remaining_debt")}</span><span>{selected.remaining_debt ?? 0}</span></div>
              </div>

              <div className="border-t pt-3 space-y-1">
                <div className="flex justify-between text-sm text-gray-500"><span>{t("gross_pay")}</span><span>{selected.gross_pay}</span></div>
                <div className="flex justify-between text-sm text-gray-500"><span>{t("total_deductions")}</span><span className="text-red-500">-{selected.total_deductions}</span></div>
                <div className="flex justify-between text-base font-bold pt-1 border-t">
                  <span>{t("net_pay")}</span>
                  <span className="text-blue-600 text-lg">{selected.net_pay?.toLocaleString()} {t("baht")}</span>
                </div>
              </div>

              <div className="bg-gray-50 rounded-lg p-3 text-sm">
                <div className="flex justify-between">
                  <span className="text-gray-400">{t("status")}</span>
                  <span className={selected.disbursed ? "text-blue-600 font-medium" : "text-amber-600"}>
                    {selected.disbursed ? t("disbursed") : selected.status === "confirmed" ? t("confirmed_pending_disburse") : t("pending_confirm")}
                  </span>
                </div>
                {selected.disbursed && selected.disbursed_at && (
                  <div className="flex justify-between mt-1">
                    <span className="text-gray-400">{t("disbursed_at")}</span>
                    <span>{new Date(selected.disbursed_at).toLocaleString("zh-CN")}</span>
                  </div>
                )}
              </div>
            </div>
            <div className="border-t px-5 py-3 bg-gray-50 rounded-b-2xl text-center">
              <button onClick={() => setSelected(null)} className="text-sm text-gray-400">{t("close")}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

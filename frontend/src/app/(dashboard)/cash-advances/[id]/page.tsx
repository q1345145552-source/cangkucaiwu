"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

const money = (value: number) => Number(value || 0).toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const when = (value: string | null) => value ? new Date(value).toLocaleString("zh-CN", { timeZone: "Asia/Bangkok", hour12: false }) : "—";

export default function CashAdvanceDetailPage({ params }: { params: { id: string } }) {
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(true), [error, setError] = useState("");
  const id = /^[1-9]\d*$/.test(params.id) && Number.isSafeInteger(Number(params.id)) ? Number(params.id) : null;
  useEffect(() => {
    let active = true;
    setResult(null); setError(""); setLoading(true);
    if (!id) { setError("垫款单不存在"); setLoading(false); return; }
    // Use the original permission- and warehouse-scoped reader, never a payment action.
    api.get<any>(`/cash-advances/${id}/repayments`).then(data => {
      if (active) setResult(data);
    }).catch(err => { if (active) setError(err.message || "垫款单加载失败"); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [id]);
  const advance = result?.advance;
  return <div className="space-y-4">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <h1 className="page-title">垫款单 {id ? `#${id}` : "详情"}</h1>

    </div>
    {loading ? <p className="text-sm text-gray-500">加载中...</p> : error ? <p role="alert" className="text-sm text-red-600">{error}</p> : advance && <>
      <dl className="bg-white rounded-xl border p-4 grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
        <div><dt className="text-gray-500">垫款人</dt><dd className="break-words">{advance.payer_name}</dd></div>
        <div><dt className="text-gray-500">状态</dt><dd>{advance.status_label}</dd></div>
        <div><dt className="text-gray-500">日期</dt><dd>{advance.advance_date}</dd></div>
        <div><dt className="text-gray-500">用途</dt><dd>{advance.purpose_label}</dd></div>
        <div><dt className="text-gray-500">金额</dt><dd>{money(advance.amount)} {advance.currency}</dd></div>
        <div><dt className="text-gray-500">已归还</dt><dd>{money(advance.repaid_amount)} {advance.currency}</dd></div>
        <div><dt className="text-gray-500">剩余未还</dt><dd>{money(advance.outstanding_amount)} {advance.currency}</dd></div>
        <div><dt className="text-gray-500">登记人 / 时间</dt><dd>{advance.created_by_name} · {when(advance.created_at)}</dd></div>
        <div><dt className="text-gray-500">确认人 / 时间</dt><dd>{advance.reviewed_by_name || "—"} · {when(advance.reviewed_at)}</dd></div>
        {advance.description && <div className="sm:col-span-2"><dt className="text-gray-500">说明</dt><dd className="whitespace-pre-wrap break-words">{advance.description}</dd></div>}
        {advance.amount_difference_note && <div className="sm:col-span-2"><dt className="text-gray-500">差额备注</dt><dd className="break-words">{advance.amount_difference_note}</dd></div>}
        {advance.reject_reason && <div className="sm:col-span-2"><dt className="text-gray-500">驳回原因</dt><dd className="break-words">{advance.reject_reason}</dd></div>}
        {advance.voucher_path && <div><dt className="text-gray-500">登记凭证</dt><dd><a href={`/${advance.voucher_path}`} target="_blank" rel="noreferrer" className="text-blue-600 underline">查看凭证</a></dd></div>}
      </dl>
      <section aria-label="垫款使用记录" className="bg-white rounded-xl border p-4 space-y-3 text-sm">
        <h2 className="font-semibold">使用记录</h2>
        {(result.payroll_usage?.data || []).map((row: any) => <p key={`payroll-${row.payroll_record_id}`} className="break-words">工资单 #{row.payroll_record_id} · {row.employee_name} · {money(row.amount)} {row.currency}</p>)}
        {(result.reimbursement_usage?.data || []).map((row: any) => <p key={`reimbursement-${row.payment_id}`} className="break-words">报销单 #{row.reimbursement_id} · {row.employee_name} · {money(row.amount)} {row.currency}</p>)}
        {(result.employee_advance_usage?.data || []).map((row: any) => <p key={`advance-${row.employee_advance_id}`} className="break-words">预支单 #{row.employee_advance_id} · {row.employee_name} · {money(row.amount)} {row.currency}</p>)}
        {!result.payroll_usage?.data?.length && !result.reimbursement_usage?.data?.length && !result.employee_advance_usage?.data?.length && <p className="text-gray-500">暂无使用记录</p>}
      </section>
      <section aria-label="垫款归还记录" className="bg-white rounded-xl border p-4 space-y-3 text-sm">
        <h2 className="font-semibold">归还记录</h2>
        {(result.data || []).map((row: any) => <p key={row.id} className="break-words">{row.repayment_date} · {money(row.amount)} {advance.currency} · {row.account_name} · {row.status === "revoked" ? "已撤销" : "有效"}</p>)}
        {!result.data?.length && <p className="text-gray-500">暂无归还记录</p>}
      </section>
    </>}
  </div>;
}

"use client";
import InternalTransferSummary, { type TransferSummary } from "@/components/InternalTransferSummary";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { fmtMoneyByCurrency } from "@/lib/currency";

type Totals = { internal_transfers: TransferSummary; income_by_currency: Record<string, number>; expense_by_currency: Record<string, number>; net_by_currency: Record<string, number>; income_count: number; expense_count: number };
type Overview = { data: (Totals & { warehouse_id: number; warehouse_name: string })[]; totals: Totals; basis: string };

export default function WarehouseSummary({ startDate, endDate }: { startDate: string; endDate: string }) {
  const [data, setData] = useState<Overview | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  const requestId = useRef(0);
  useEffect(() => {
    const reload = () => { requestId.current++; setData(null); setLoading(true); setRevision(n => n + 1); };
    window.addEventListener("warehouse-changed", reload);
    window.addEventListener("auth-user-refreshed", reload);
    return () => { window.removeEventListener("warehouse-changed", reload); window.removeEventListener("auth-user-refreshed", reload); };
  }, []);
  useEffect(() => {
    let active = true;
    const id = ++requestId.current;
    setData(null); setError(""); setLoading(true);
    api.get<Overview>(`/dashboard/warehouse-summary?${new URLSearchParams({ start_date: startDate, end_date: endDate })}`)
      .then(result => { if (active && id === requestId.current) setData(result); })
      .catch(err => { if (active && id === requestId.current) setError(`仓库汇总加载失败：${err.message || "请稍后重试"}`); })
      .finally(() => { if (active && id === requestId.current) setLoading(false); });
    return () => { active = false; };
  }, [startDate, endDate, revision]);
  const amount = (values: Record<string, number>) => Object.keys(values).length ? fmtMoneyByCurrency(values) : "0";
  const line = (label: string, totals: Totals) => <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-sm">
    <strong>{label}</strong><span>收入 {amount(totals.income_by_currency)}（{totals.income_count}笔）</span>
    <span>支出 {amount(totals.expense_by_currency)}（{totals.expense_count}笔）</span><span>净收支 {amount(totals.net_by_currency)}</span>
  </div>;
  return <section aria-label="各仓概况" className="bg-white rounded-2xl p-4 border border-gray-100 mb-6 space-y-3">
    <h2 className="font-semibold text-gray-700">各仓概况</h2>
    <p className="text-xs text-gray-500">{startDate} 至 {endDate} · 当前所选授权仓库 · 各币种分别统计</p>
    {loading ? <p className="text-sm text-gray-500">仓库汇总加载中...</p> : error ? <div role="alert" className="text-sm text-red-600">{error}<button className="ml-3 underline" onClick={() => setRevision(n => n + 1)}>重试</button></div> : data && <>
      {data.data.length ? data.data.map(row => <div key={row.warehouse_id} className="border-b border-gray-100 pb-3">{line(row.warehouse_name, row)}<InternalTransferSummary data={row.internal_transfers} /></div>) : <p className="text-sm text-gray-500">暂无可查看的启用仓库</p>}
      {line("合计", data.totals)}<InternalTransferSummary data={data.totals.internal_transfers} /><p className="text-xs text-gray-500">{data.basis}</p>
    </>}
  </section>;
}

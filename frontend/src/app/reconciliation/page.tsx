"use client";
import { useEffect, useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import { useI18n } from "@/hooks/useI18n";
import { api, getToken } from "@/lib/api";
import { useRouter } from "next/navigation";
import DashboardLayout from "@/components/layout/DashboardLayout";
import DataTable from "@/components/common/DataTable";

export default function ReconciliationPage() {
  const { t } = useI18n(); const { user } = useAuth(); const router = useRouter();
  const [month, setMonth] = useState("2026-07");
  const [warehouses, setWarehouses] = useState<any[]>([]);
  const [whId, setWhId] = useState(0);
  const [result, setResult] = useState<any>(null);
  const [data, setData] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [tab, setTab] = useState("all");

  useEffect(() => { if (!getToken()) router.push("/login"); loadWarehouses(); }, []);

  async function loadWarehouses() {
    const r = await api.get<any>("/warehouses"); setWarehouses(r.data);
    if (r.data.length > 0) setWhId(r.data[0].id);
  }

  async function runRecon() {
    const res = await api.post<any>("/reconciliation/run", { month, warehouse_id: whId });
    setResult(res); loadResults();
  }

  async function loadResults() {
    const res = await api.get<any>(`/reconciliation/results?month=${month}&warehouse_id=${whId}&page=${page}&page_size=20`);
    setData(res.data); setTotal(res.total);
  }

  useEffect(() => { loadResults(); }, [page, tab]);

  const columns = [
    { key: "match_status", label: "状态", render: (v: string) => {
      const m: any = { matched: "✅ 已匹配", unmatched: "❌ 未匹配", manual_matched: "🔧 手动匹配" };
      return m[v] || v;
    }},
    { key: "declaration", label: "申报", render: (v: any) => v ? `¥${v.amount} ${v.currency}` : "-" },
    { key: "flow", label: "到账", render: (v: any) => v ? `¥${v.amount} ${v.currency}` : "-" },
    { key: "amount_diff", label: "差额" },
    { key: "handling_note", label: "处理说明" },
  ];

  return (
    <DashboardLayout>
      <div className="mb-4">
        <h1 className="text-xl font-bold mb-3">{t("reconciliation")}</h1>
        <div className="flex items-center gap-3 bg-white p-4 rounded-xl shadow-sm">
          <input type="month" value={month} onChange={e => setMonth(e.target.value)} className="border rounded px-3 py-2 text-sm" />
          <select value={whId} onChange={e => setWhId(+e.target.value)} className="border rounded px-3 py-2 text-sm">
            {warehouses.map((w: any) => <option key={w.id} value={w.id}>{w.name}</option>)}
          </select>
          <button onClick={runRecon} className="bg-primary text-white px-4 py-2 rounded-lg text-sm">发起对账</button>
        </div>
      </div>
      {result && (
        <div className="grid grid-cols-4 gap-4 mb-4">
          <div className="bg-green-50 rounded-xl p-4"><div className="text-2xl font-bold">{result.matched}</div><div className="text-xs text-gray-500">已匹配</div></div>
          <div className="bg-orange-50 rounded-xl p-4"><div className="text-2xl font-bold">{result.unmatched_declarations}</div><div className="text-xs text-gray-500">申报未匹配</div></div>
          <div className="bg-orange-50 rounded-xl p-4"><div className="text-2xl font-bold">{result.unmatched_flows}</div><div className="text-xs text-gray-500">到账未匹配</div></div>
          <div className="bg-blue-50 rounded-xl p-4"><div className="text-2xl font-bold">{result.total_declarations + result.total_flows}</div><div className="text-xs text-gray-500">总记录数</div></div>
        </div>
      )}
      <DataTable columns={columns} data={data} total={total} page={page} pageSize={20} onPageChange={setPage} />
    </DashboardLayout>
  );
}

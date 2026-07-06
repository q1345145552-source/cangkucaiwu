"use client";
import { useEffect, useState } from "react";
import { api, getToken } from "@/lib/api";
import { useI18n } from "@/hooks/useI18n";
import { useRouter } from "next/navigation";
import { TrendingUp, TrendingDown, FileText, PiggyBank, Receipt, CreditCard, Clock, AlertTriangle } from "lucide-react";

const reportTypes = [
  { key: "recharge-summary", label: "recharge", icon: <TrendingUp size={24} />, color: "text-green-600" },
  { key: "incoming-summary", label: "incoming", icon: <TrendingDown size={24} />, color: "text-blue-600" },
  { key: "income-expense", label: "income_expense", icon: <FileText size={24} />, color: "text-purple-600" },
  { key: "payable", label: "payable", icon: <CreditCard size={24} />, color: "text-red-600" },
  { key: "expense-fund", label: "expense_fund", icon: <PiggyBank size={24} />, color: "text-orange-600" },
  { key: "reimbursement", label: "reimbursement", icon: <Receipt size={24} />, color: "text-teal-600" },
  { key: "credit", label: "credit", icon: <Clock size={24} />, color: "text-yellow-600" },
  { key: "reconciliation-diff", label: "对账差异", icon: <AlertTriangle size={24} />, color: "text-pink-600" },
];

export default function ReportsPage() {
  const { t } = useI18n(); const router = useRouter();
  const [selected, setSelected] = useState("");
  const [data, setData] = useState<any>(null);
  const [month, setMonth] = useState("2026-07");
  const [loading, setLoading] = useState(false);

  useEffect(() => { if (!getToken()) router.push("/login"); }, []);

  async function loadReport(key: string) {
    setSelected(key); setLoading(true);
    try {
      const r = await api.get<any>(`/reports/${key}?month=${month}`);
      setData(r);
    } catch { setData(null); }
    setLoading(false);
  }

  function exportExcel(key: string) {
    const token = getToken();
    window.open(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1"}/reports/${key}?format=excel&month=${month}`, "_blank");
  }

  return (
    <>
      <div className="mb-4"><h1 className="page-title">{t("reports")}</h1></div>

      <div className="flex items-center gap-3 mb-6">
        <input type="month" value={month} onChange={e => { setMonth(e.target.value); if (selected) loadReport(selected); }} className="border rounded px-3 py-2 text-sm" />
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        {reportTypes.map((rt) => (
          <button key={rt.key} onClick={() => loadReport(rt.key)}
                  className={`bg-white rounded-xl p-4 shadow-sm text-left hover:shadow-md transition-shadow ${selected === rt.key ? "ring-2 ring-primary" : ""}`}>
            <div className={rt.color}>{rt.icon}</div>
            <div className="font-semibold text-sm mt-2">{rt.label === "对账差异" ? rt.label : t(rt.label)}</div>
          </button>
        ))}
      </div>

      {loading && <div className="text-center text-gray-400 py-8">加载中...</div>}

      {data && selected && (
        <div className="bg-white rounded-xl shadow-sm p-6">
          <div className="flex justify-between mb-4">
            <h2 className="font-semibold text-lg">{t(reportTypes.find(r => r.key === selected)?.label || selected)}</h2>
            <button onClick={() => exportExcel(selected)} className="border border-primary text-primary px-4 py-1.5 rounded text-sm hover:bg-primary-light">导出 Excel</button>
          </div>

          {/* Summary stats */}
          {data.total_amount !== undefined && (
            <div className="text-3xl font-bold text-primary mb-4">¥{data.total_amount?.toLocaleString()}</div>
          )}
          {data.total_income !== undefined && (
            <div className="grid grid-cols-3 gap-4 mb-4">
              <div className="bg-green-50 rounded-lg p-3"><div className="text-xs text-gray-500">收入</div><div className="text-lg font-bold text-green-600">¥{data.total_income?.toLocaleString()}</div></div>
              <div className="bg-red-50 rounded-lg p-3"><div className="text-xs text-gray-500">支出</div><div className="text-lg font-bold text-red-600">¥{data.total_expense?.toLocaleString()}</div></div>
              <div className="bg-blue-50 rounded-lg p-3"><div className="text-xs text-gray-500">净额</div><div className={`text-lg font-bold ${data.net >= 0 ? "text-blue-600" : "text-red-600"}`}>¥{data.net?.toLocaleString()}</div></div>
            </div>
          )}
          {data.total_pending !== undefined && (
            <div className="text-lg font-semibold text-red-600 mb-4">待付总额: ¥{data.total_pending?.toLocaleString()}</div>
          )}
          {data.total_debt !== undefined && (
            <div className="text-lg font-semibold text-orange-600 mb-4">总欠款: ¥{data.total_debt?.toLocaleString()}</div>
          )}

          {/* Data table */}
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="border-b bg-gray-50">{data.data?.[0] && Object.keys(data.data[0]).map(k => <th key={k} className="text-left px-3 py-2 font-medium text-gray-600">{k}</th>)}</tr></thead>
              <tbody>
                {data.data?.slice(0, 50).map((row: any, i: number) => (
                  <tr key={i} className="border-b hover:bg-gray-50">
                    {Object.values(row).map((v: any, j: number) => <td key={j} className="px-3 py-2 text-gray-700">{String(v ?? "-")}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {data.total !== undefined && <div className="text-xs text-gray-400 mt-2">共 {data.total} 条</div>}
        </div>
      )}
    </>
  );
}

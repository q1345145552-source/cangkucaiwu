"use client";
import { useEffect, useState } from "react";
import { api, getToken } from "@/lib/api";
import { useRouter } from "next/navigation";
import { TrendingUp, TrendingDown, FileText, PiggyBank, Receipt, CreditCard, Clock, AlertTriangle, Download } from "lucide-react";

const reportTypes = [
  { key: "recharge-summary", label: "充值汇总", icon: <TrendingUp size={24} />, color: "text-green-600 bg-green-50" },
  { key: "incoming-summary", label: "到账汇总", icon: <TrendingDown size={24} />, color: "text-blue-600 bg-blue-50" },
  { key: "income-expense", label: "收支报表", icon: <FileText size={24} />, color: "text-purple-600 bg-purple-50" },
  { key: "payable", label: "应付报表", icon: <CreditCard size={24} />, color: "text-red-600 bg-red-50" },
  { key: "expense-fund", label: "备用金报表", icon: <PiggyBank size={24} />, color: "text-orange-600 bg-orange-50" },
  { key: "reimbursement", label: "报销报表", icon: <Receipt size={24} />, color: "text-teal-600 bg-teal-50" },
  { key: "credit", label: "账期报表", icon: <Clock size={24} />, color: "text-yellow-600 bg-yellow-50" },
  { key: "reconciliation-diff", label: "对账差异", icon: <AlertTriangle size={24} />, color: "text-pink-600 bg-pink-50" },
];

const columnConfig: Record<string, string[]> = {
  "recharge-summary": ["日期", "金额", "币种", "状态"],
  "incoming-summary": ["日期", "金额", "币种", "付款方"],
  "income-expense": ["类型", "日期", "金额", "币种", "备注"],
  "payable": ["账单号", "到期日", "金额", "已付", "状态"],
  "expense-fund": ["用途", "金额", "余额", "状态"],
  "reimbursement": ["日期", "金额", "币种", "状态"],
  "credit": ["额度", "欠款", "逾期天数", "状态"],
  "reconciliation-diff": ["月份", "状态", "差额", "处理说明"],
};

// Columns that contain amounts (right-align, bold)
const amtCols = new Set(["金额", "已付", "余额", "欠款", "差额", "额度", "净额"]);
// Columns that contain status (colored tag)
const statusCols = new Set(["状态"]);
// Columns that contain dates
const dateCols = new Set(["日期", "到期日"]);

const STATUS_COLOR_MAP: Record<string, string> = {
  "待处理": "bg-yellow-50 text-yellow-700",
  "已匹配": "bg-green-50 text-green-700",
  "未匹配": "bg-gray-100 text-gray-500",
  "已付款": "bg-blue-50 text-blue-700",
  "正常": "bg-green-50 text-green-700",
  "已通过": "bg-green-50 text-green-700",
  "已驳回": "bg-red-50 text-red-700",
  "部分通过": "bg-orange-50 text-orange-700",
  "转入备用金审核": "bg-purple-50 text-purple-700",
  "部分付款": "bg-orange-50 text-orange-700",
  "逾期": "bg-red-50 text-red-700",
  "暂停": "bg-yellow-50 text-yellow-700",
  "已取消": "bg-gray-100 text-gray-500",
  "已结清": "bg-blue-50 text-blue-700",
};

function statusColor(s: string): string {
  return STATUS_COLOR_MAP[s] || "bg-gray-100 text-gray-600";
}

export default function ReportsPage() {
  const router = useRouter();
  const today = new Date();
  const curMonth = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}`;

  const [selected, setSelected] = useState("");
  const [data, setData] = useState<any>(null);
  const [month, setMonth] = useState(curMonth);
  const [loading, setLoading] = useState(false);
  const [previews, setPreviews] = useState<Record<string, any>>({});

  useEffect(() => { if (!getToken()) router.push("/login"); loadPreviews(); }, []);
  useEffect(() => { loadPreviews(); }, [month]);

  async function loadPreviews() {
    try {
      const r = await api.get<any>(`/reports/previews?month=${month}`);
      setPreviews(r.previews || {});
    } catch {}
  }

  async function loadReport(key: string) {
    setSelected(key); setLoading(true);
    try {
      const r = await api.get<any>(`/reports/${key}?month=${month}`);
      setData(r);
    } catch { setData(null); }
    setLoading(false);
  }

  async function exportExcel(key: string) {
    const token = getToken();
    const base = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";
    try {
      const res = await fetch(`${base}/reports/${key}?format=excel&month=${month}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error("导出失败");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `report_${key}_${month}.xlsx`;
      document.body.appendChild(a); a.click();
      document.body.removeChild(a); URL.revokeObjectURL(url);
    } catch (err) { console.error("导出失败:", err); }
  }

  function formatPreview(key: string, p: any): string {
    if (!p) return "";
    if (key === "income-expense") return `¥${(p.preview || 0).toLocaleString()}`;
    if (key === "credit") return `¥${(p.preview || 0).toLocaleString()}`;
    if (key === "reconciliation-diff") return `${p.count || 0}条`;
    return `¥${(p.preview || 0).toLocaleString()}`;
  }

  const cols = selected ? (columnConfig[selected] || []) : [];

  return (
    <>
      <div className="flex items-center gap-3 mb-5">
        <div className="w-9 h-9 rounded-xl bg-blue-100 flex items-center justify-center">
          <FileText size={20} className="text-blue-600" />
        </div>
        <div className="flex-1">
          <h1 className="page-title">报表中心</h1>
        </div>
        <div className="flex items-center gap-2">
          <input type="month" value={month} onChange={e => { setMonth(e.target.value); if (selected) loadReport(selected); }} className="form-input text-sm py-1.5 w-36" />
        </div>
      </div>

      {/* Report type cards with preview badges */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        {reportTypes.map((rt) => {
          const pv = previews[rt.key];
          const previewText = formatPreview(rt.key, pv);
          return (
            <button key={rt.key} onClick={() => loadReport(rt.key)}
              className={`relative bg-white rounded-2xl p-4 shadow-sm border text-left hover:shadow-md transition-all ${selected === rt.key ? "ring-2 ring-blue-500 border-blue-200" : "border-gray-100"}`}>
              <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${rt.color}`}>{rt.icon}</div>
              <div className="font-semibold text-sm mt-2.5 text-gray-700">{rt.label}</div>
              {previewText && (
                <span className="absolute top-3 right-3 bg-gray-900 text-white text-[10px] font-semibold px-2 py-0.5 rounded-full">
                  {previewText}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {/* Loading */}
      {loading && (
        <div className="bg-white rounded-2xl shadow-sm border p-12 text-center text-gray-400">
          <div className="animate-spin w-6 h-6 border-2 border-blue-600 border-t-transparent rounded-full mx-auto mb-2" />加载中...
        </div>
      )}

      {/* Report content */}
      {data && selected && !loading && (
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
          {/* Title bar */}
          <div className="flex items-center justify-between px-6 py-4 border-b bg-gray-50/50">
            <h2 className="font-semibold text-gray-800">{reportTypes.find(r => r.key === selected)?.label || selected}</h2>
            <button onClick={() => exportExcel(selected)} className="btn-secondary text-sm flex items-center gap-1.5">
              <Download size={14} />导出 Excel
            </button>
          </div>

          {/* Summary cards */}
          <div className="px-6 pt-5 pb-2">
            {selected === "recharge-summary" && (
              <div className="grid grid-cols-2 gap-3 mb-3">
                <div className="bg-green-50 rounded-xl p-4"><div className="text-xs text-green-500 mb-1">当月总充值金额</div><div className="text-xl font-bold text-green-700">฿{(data.total_amount || 0).toLocaleString()}</div></div>
                <div className="bg-blue-50 rounded-xl p-4"><div className="text-xs text-blue-500 mb-1">总笔数</div><div className="text-xl font-bold text-blue-700">{data.total_count || 0} 笔</div></div>
              </div>
            )}
            {selected === "incoming-summary" && (
              <div className="grid grid-cols-2 gap-3 mb-3">
                <div className="bg-blue-50 rounded-xl p-4"><div className="text-xs text-blue-500 mb-1">当月总到账金额</div><div className="text-xl font-bold text-blue-700">฿{(data.total_amount || 0).toLocaleString()}</div></div>
                <div className="bg-green-50 rounded-xl p-4"><div className="text-xs text-green-500 mb-1">总笔数</div><div className="text-xl font-bold text-green-700">{data.total_count || 0} 笔</div></div>
              </div>
            )}
            {selected === "income-expense" && (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
                <div className="bg-green-50 rounded-xl p-4"><div className="text-xs text-green-500 mb-1">总收入</div><div className="text-lg font-bold text-green-700">฿{(data.total_income || 0).toLocaleString()}</div></div>
                <div className="bg-blue-50 rounded-xl p-4"><div className="text-xs text-blue-500 mb-1">充值收入</div><div className="text-lg font-bold text-blue-700">฿{(data.recharge_income || 0).toLocaleString()}</div></div>
                <div className="bg-orange-50 rounded-xl p-4"><div className="text-xs text-orange-500 mb-1">其他收入</div><div className="text-lg font-bold text-orange-700">฿{(data.other_income || 0).toLocaleString()}</div></div>
                <div className="bg-red-50 rounded-xl p-4"><div className="text-xs text-red-500 mb-1">总支出</div><div className="text-lg font-bold text-red-700">฿{(data.total_expense || 0).toLocaleString()}</div></div>
                <div className={`rounded-xl p-4 col-span-2 md:col-span-4 ${(data.net || 0) >= 0 ? "bg-indigo-50" : "bg-red-50"}`}>
                  <div className={`text-xs mb-1 ${(data.net || 0) >= 0 ? "text-indigo-500" : "text-red-500"}`}>净额（总收入 - 总支出）</div>
                  <div className={`text-lg font-bold ${(data.net || 0) >= 0 ? "text-indigo-700" : "text-red-700"}`}>฿{(data.net || 0).toLocaleString()}</div>
                </div>
              </div>
            )}
            {selected === "payable" && (
              <div className="grid grid-cols-2 gap-3 mb-3">
                <div className="bg-red-50 rounded-xl p-4"><div className="text-xs text-red-500 mb-1">待付总额</div><div className="text-xl font-bold text-red-700">฿{(data.total_pending || 0).toLocaleString()}</div></div>
                <div className="bg-orange-50 rounded-xl p-4"><div className="text-xs text-orange-500 mb-1">逾期笔数</div><div className="text-xl font-bold text-orange-700">{data.overdue_count || 0} 笔</div></div>
              </div>
            )}
            {selected === "expense-fund" && (
              <div className="grid grid-cols-2 gap-3 mb-3">
                <div className="bg-orange-50 rounded-xl p-4"><div className="text-xs text-orange-500 mb-1">在途总额</div><div className="text-xl font-bold text-orange-700">฿{(data.in_transit_total || 0).toLocaleString()}</div></div>
                <div className="bg-blue-50 rounded-xl p-4"><div className="text-xs text-blue-500 mb-1">总笔数</div><div className="text-xl font-bold text-blue-700">{data.total_count || 0} 笔</div></div>
              </div>
            )}
            {selected === "reimbursement" && (
              <div className="grid grid-cols-2 gap-3 mb-3">
                <div className="bg-teal-50 rounded-xl p-4"><div className="text-xs text-teal-500 mb-1">当月报销总额</div><div className="text-xl font-bold text-teal-700">฿{(data.total_amount || 0).toLocaleString()}</div></div>
                <div className="bg-blue-50 rounded-xl p-4"><div className="text-xs text-blue-500 mb-1">总笔数</div><div className="text-xl font-bold text-blue-700">{data.total_count || 0} 笔</div></div>
              </div>
            )}
            {selected === "credit" && (
              <div className="grid grid-cols-2 gap-3 mb-3">
                <div className="bg-yellow-50 rounded-xl p-4"><div className="text-xs text-yellow-600 mb-1">总欠款</div><div className="text-xl font-bold text-yellow-700">฿{(data.total_debt || 0).toLocaleString()}</div></div>
                <div className="bg-red-50 rounded-xl p-4"><div className="text-xs text-red-500 mb-1">逾期客户数</div><div className="text-xl font-bold text-red-700">{data.overdue_count || 0}</div></div>
              </div>
            )}
            {selected === "reconciliation-diff" && (
              <div className="grid grid-cols-2 gap-3 mb-3">
                <div className="bg-pink-50 rounded-xl p-4"><div className="text-xs text-pink-500 mb-1">差异笔数</div><div className="text-xl font-bold text-pink-700">{data.diff_count || 0} 笔</div></div>
                <div className="bg-red-50 rounded-xl p-4"><div className="text-xs text-red-500 mb-1">总差额</div><div className="text-xl font-bold text-red-700">฿{(data.total_diff || 0).toLocaleString()}</div></div>
              </div>
            )}
          </div>

          {/* Data table */}
          <div className="overflow-x-auto px-6 pb-5">
            {data.data?.length > 0 ? (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-gray-100">
                    {cols.map(k => (
                      <th key={k} className={`px-4 py-3 font-semibold text-gray-600 whitespace-nowrap ${amtCols.has(k) ? "text-right" : "text-left"}`}>{k}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.data.slice(0, 100).map((row: any, i: number) => (
                    <tr key={i} className="border-b hover:bg-gray-50/50 transition-colors">
                      {cols.map(k => {
                        const val = row[k];
                        let display: any = val === null || val === undefined || val === "" ? "-" : String(val);

                        // Date formatting
                        if (dateCols.has(k) && val && String(val).length >= 10) {
                          display = String(val).slice(0, 10);
                        }
                        // Amount columns: right-aligned bold
                        if (amtCols.has(k) && typeof val === "number") {
                          display = val.toLocaleString();
                          return (
                            <td key={k} className="px-4 py-3 text-right font-mono text-sm font-semibold text-gray-800 whitespace-nowrap">
                              {display}
                            </td>
                          );
                        }
                        // Status column: colored tag
                        if (statusCols.has(k)) {
                          const label = String(val || "-");
                          return (
                            <td key={k} className="px-4 py-3 whitespace-nowrap">
                              <span className={`inline-flex px-2.5 py-0.5 rounded-full text-xs font-medium ${statusColor(label)}`}>
                                {label}
                              </span>
                            </td>
                          );
                        }
                        // Default
                        return (
                          <td key={k} className="px-4 py-3 text-gray-700 whitespace-nowrap">
                            {display}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <div className="text-center py-12 text-gray-400 text-sm">暂无数据</div>
            )}
          </div>

          {data.total !== undefined && <div className="px-6 pb-4 text-xs text-gray-400">共 {data.total} 条</div>}
        </div>
      )}
    </>
  );
}

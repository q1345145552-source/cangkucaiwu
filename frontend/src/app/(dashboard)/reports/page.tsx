"use client";
import InternalTransferSummary from "@/components/InternalTransferSummary";
import { useEffect, useRef, useState } from "react";
import { api, getToken, getActiveWarehouseId } from "@/lib/api";
import { fmtMoney, fmtMoneyByCurrency } from "@/lib/currency";
import { useToast } from "@/components/ui/Toast";
import { useRouter } from "next/navigation";
import { operatingEntriesEnabled } from "@/lib/retiredEntries";
import OperatingReport from "@/components/OperatingReport";
import WarehouseSummary from "@/components/WarehouseSummary";
import { TrendingUp, TrendingDown, FileText, PiggyBank, Receipt, CreditCard, Clock, AlertTriangle, Download } from "lucide-react";

const reportTypes = [
  { key: "cost-funds-debt", label: "成本资金欠款", icon: <FileText size={24} />, color: "text-indigo-600 bg-indigo-50" },
  { key: "recharge-summary", label: "充值汇总", icon: <TrendingUp size={24} />, color: "text-green-600 bg-green-50" },
  { key: "incoming-summary", label: "到账汇总", icon: <TrendingDown size={24} />, color: "text-blue-600 bg-blue-50" },
  { key: "income-expense", label: "收支报表", icon: <FileText size={24} />, color: "text-purple-600 bg-purple-50" },
  { key: "payable", label: "应付报表", icon: <CreditCard size={24} />, color: "text-red-600 bg-red-50" },
  { key: "expense-fund", label: "备用金报表", icon: <PiggyBank size={24} />, color: "text-orange-600 bg-orange-50" },
  { key: "reimbursement", label: "报销报表", icon: <Receipt size={24} />, color: "text-teal-600 bg-teal-50" },
  { key: "credit", label: "账期报表", icon: <Clock size={24} />, color: "text-yellow-600 bg-yellow-50" },
  { key: "reconciliation-diff", label: "对账差异", icon: <AlertTriangle size={24} />, color: "text-pink-600 bg-pink-50" },
  { key: "operations", label: "经营情况（独立）", icon: <FileText size={24} />, color: "text-cyan-600 bg-cyan-50" },
];

const columnConfig: Record<string, string[]> = {
  "recharge-summary": ["日期", "金额", "币种", "状态"],
  "incoming-summary": ["日期", "金额", "币种", "付款方"],
  "income-expense": ["类型", "日期", "金额", "币种", "备注"],
  "payable": ["账单号", "到期日", "金额", "已付", "币种", "状态"],
  "expense-fund": ["用途", "金额", "余额", "状态"],
  "reimbursement": ["日期", "金额", "币种", "状态"],
  "credit": ["额度", "欠款", "逾期天数", "状态"],
  "reconciliation-diff": ["月份", "状态", "差额", "币种", "处理说明"],
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
  const { toast } = useToast();
  const router = useRouter();
  const todayStr = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Bangkok", year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());
  const curMonth = todayStr.slice(0,7);

  const reportRequest=useRef(0),previewRequest=useRef(0);
  const [scopeRevision,setScopeRevision]=useState(0);
  const [selected, setSelected] = useState("");
  const [data, setData] = useState<any>(null);
  const [dateRange, setDateRange] = useState({ start_date: `${curMonth}-01`, end_date: todayStr });
  const [loading, setLoading] = useState(false);
  const [previews, setPreviews] = useState<Record<string, any>>({});
  const [previewLoading,setPreviewLoading] = useState(true);
  const [previewError,setPreviewError] = useState(""), [reportError,setReportError] = useState("");

  useEffect(() => {
    if (!getToken()) router.push("/login");
    const q=new URLSearchParams(window.location.search);
    if(operatingEntriesEnabled && q.get("view")==="operations"){
      setSelected("operations");
      if(q.get("start_date")&&q.get("end_date"))setDateRange({start_date:q.get("start_date")!,end_date:q.get("end_date")!});
    }
  }, []);
  useEffect(()=>{
    if(operatingEntriesEnabled && selected==="operations")window.history.replaceState(window.history.state,"",`/reports?${new URLSearchParams({view:"operations",...dateRange})}`);
  },[selected,dateRange]);
  useEffect(() => { loadPreviews(); if (selected && selected !== "operations") loadReport(selected); }, [dateRange,scopeRevision]);

  useEffect(()=>{
    const change=()=>{reportRequest.current++;previewRequest.current++;setData(null);setPreviews({});setPreviewLoading(true);setPreviewError("");setReportError("");setLoading(false);setScopeRevision(n=>n+1);};
    window.addEventListener("warehouse-changed",change);window.addEventListener("auth-user-refreshed",change);
    return()=>{reportRequest.current++;previewRequest.current++;window.removeEventListener("warehouse-changed",change);window.removeEventListener("auth-user-refreshed",change);};
  },[]);

  async function loadPreviews() {
    const id=++previewRequest.current;
    setPreviews({});setPreviewError("");setPreviewLoading(true);
    try {
      const r = await api.get<any>(`/reports/previews?start_date=${dateRange.start_date}&end_date=${dateRange.end_date}`);
      if(id===previewRequest.current)setPreviews(r.previews || {});
    } catch (err: any) {
      if(id===previewRequest.current){setPreviews({});setPreviewError(`报表预览加载失败：${err.message || "请稍后重试"}`);}
    } finally { if(id===previewRequest.current)setPreviewLoading(false); }
  }

  function openOperatingReport() {
    if (!operatingEntriesEnabled) return;
    const month = new Intl.DateTimeFormat("en-CA",{timeZone:"Asia/Bangkok",year:"numeric",month:"2-digit",day:"2-digit"}).format(new Date()).slice(0,7);
    const [y,m]=month.split("-").map(Number);
    reportRequest.current++;setSelected("operations");setData(null);setLoading(false);
    setDateRange({start_date:`${month}-01`,end_date:`${month}-${String(new Date(y,m,0).getDate()).padStart(2,"0")}`});
  }

  async function loadReport(key: string) {
    if (key === "operations" && !operatingEntriesEnabled) return;
    const query=new URLSearchParams(window.location.search);
    if(query.get("view")==="operations"){
      query.delete("view");query.delete("start_date");query.delete("end_date");
      window.history.replaceState(window.history.state,"",`/reports${query.size?`?${query}`:""}`);
    }
    const id=++reportRequest.current;setSelected(key);setData(null);setReportError("");setLoading(true);
    try {
      const r = await api.get<any>(`/reports/${key}?start_date=${dateRange.start_date}&end_date=${dateRange.end_date}`);
      if(id===reportRequest.current)setData(r);
    } catch (err: any) { if(id===reportRequest.current){setData(null);setReportError(`报表加载失败：${err.message || "请稍后重试"}`);} }
    if(id===reportRequest.current)setLoading(false);
  }

  async function exportExcel(key: string) {
    const requestId=reportRequest.current;
    const token = getToken();
    const base = process.env.NEXT_PUBLIC_API_URL || "/api/v1";
    const headers: Record<string, string> = { Authorization: `Bearer ${token}` };
    const warehouse = getActiveWarehouseId();
    if (warehouse !== null) headers["X-Warehouse-ID"] = warehouse;
    try {
      const res = await fetch(`${base}/reports/${key}?format=excel&start_date=${dateRange.start_date}&end_date=${dateRange.end_date}`, {
        headers,
      });
      if (!res.ok) throw new Error("导出失败");
      const blob = await res.blob();
      if(requestId!==reportRequest.current || warehouse!==getActiveWarehouseId())throw new Error("筛选已变化，请重新导出");
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `report_${key}_${dateRange.start_date}_${dateRange.end_date}.xlsx`;
      document.body.appendChild(a); a.click();
      document.body.removeChild(a); URL.revokeObjectURL(url);
    } catch (err) {
      console.error("导出失败:", err);
      toast("error", err instanceof Error ? err.message : "导出失败 请稍后再试");
    }
  }

  function formatPreview(key: string, p: any): string {
    if (!p) return "";
    if (key === "reconciliation-diff") return `${p.count || 0}条`;
    if (p.preview_by_currency) return reportAmounts(p.preview_by_currency);
    return p.preview == null ? "按币种查看" : fmtMoney(p.preview);
  }

  function changeRange(next: typeof dateRange) {
    reportRequest.current++;previewRequest.current++;
    setData(null);setPreviews({});setPreviewError("");setReportError("");setPreviewLoading(true);
    setDateRange(next);
  }
  function reportAmounts(values?: Record<string,number>) {
    if (!values || !Object.keys(values).length) return "0";
    const known=Object.fromEntries(Object.entries(values).filter(([c])=>c!=="UNKNOWN"));
    const parts=Object.keys(known).length ? [fmtMoneyByCurrency(known)==="-" ? "0" : fmtMoneyByCurrency(known)] : [];
    if(values.UNKNOWN!==undefined)parts.push(`${values.UNKNOWN.toLocaleString()}（币种待核对）`);
    return parts.join("；");
  }

  const cols = selected ? (columnConfig[selected] || []) : [];

  return (
    <>
      <div className="flex items-center gap-3 mb-5 flex-wrap">
        <div className="flex items-center gap-3 flex-1 min-w-[160px]">
          <div className="w-9 h-9 rounded-xl bg-blue-100 flex items-center justify-center shrink-0">
            <FileText size={20} className="text-blue-600" />
          </div>
          <h1 className="page-title">报表中心</h1>
        </div>
        <div className="flex items-center gap-2 w-full sm:w-auto sm:justify-end flex-wrap">
          {operatingEntriesEnabled && selected === "operations" && <label className="text-xs">经营月份<input aria-label="经营月份" type="month" className="form-input text-sm w-36" value={dateRange.start_date.slice(0,7)} onChange={e=>{if(e.target.value){const [y,m]=e.target.value.split("-").map(Number);setDateRange({start_date:`${e.target.value}-01`,end_date:`${e.target.value}-${String(new Date(y,m,0).getDate()).padStart(2,"0")}`});}}}/></label>}
          <input aria-label="开始日期" type="date" value={dateRange.start_date} onChange={e => changeRange({ ...dateRange, start_date: e.target.value })} className="form-input text-sm py-1.5 w-36" />
          <span className="text-gray-400 text-xs">至</span>
          <input aria-label="结束日期" type="date" value={dateRange.end_date} onChange={e => changeRange({ ...dateRange, end_date: e.target.value })} className="form-input text-sm py-1.5 w-36" />
        </div>
      </div>

      {selected !== "operations" && <WarehouseSummary startDate={dateRange.start_date} endDate={dateRange.end_date} />}

      {previewError && <div role="alert" className="mb-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">{previewError}<button className="ml-3 underline" onClick={() => loadPreviews()}>重试预览</button></div>}
      {reportError && <div role="alert" className="mb-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">{reportError}<button className="ml-3 underline" onClick={() => loadReport(selected)}>重试报表</button></div>}
      {/* Report type cards with preview badges */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        {reportTypes.filter(rt => operatingEntriesEnabled || rt.key !== "operations").map((rt) => {
          const pv = previews[rt.key];
          const previewText = previewLoading && rt.key !== "cost-funds-debt" ? "加载中" : formatPreview(rt.key, pv);
          return (
            <button key={rt.key} onClick={() => { if(rt.key === "operations"){openOperatingReport();}else if(rt.key === "cost-funds-debt")router.push(`/reports/cost-funds-debt?${new URLSearchParams(dateRange)}`);else loadReport(rt.key); }}
              className={`relative bg-white rounded-2xl p-4 shadow-sm border text-left hover:shadow-md transition-all ${selected === rt.key ? "ring-2 ring-blue-500 border-blue-200" : "border-gray-100"}`}>
              <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${rt.color}`}>{rt.icon}</div>
              <div className="font-semibold text-sm mt-2.5 text-gray-700">{rt.label}</div>
              {rt.key === "income-expense" && pv && <div className="mt-1 text-xs text-gray-500" aria-label="收支预览金额"><p>收入 {reportAmounts(pv.income_by_currency)}</p><p>支出 {reportAmounts(pv.expense_by_currency)}</p></div>}
              {(rt.key === "expense-fund" || rt.key === "credit") && <p className="mt-1 text-[10px] text-gray-400">当前余额，不按日期回溯</p>}
              {previewText && (
                <span className="absolute top-3 right-3 bg-gray-900 text-white text-[10px] font-semibold px-2 py-0.5 rounded-full">
                  {previewText}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {operatingEntriesEnabled && selected === "operations" && <OperatingReport startDate={dateRange.start_date} endDate={dateRange.end_date} />}

      {/* Loading */}
      {loading && selected !== "operations" && (
        <div className="bg-white rounded-2xl shadow-sm border p-12 text-center text-gray-400">
          <div className="animate-spin w-6 h-6 border-2 border-blue-600 border-t-transparent rounded-full mx-auto mb-2" />加载中...
        </div>
      )}

      {/* Report content */}
      {data && selected && selected !== "operations" && !loading && (
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
                <div className="bg-green-50 rounded-xl p-4"><div className="text-xs text-green-500 mb-1">当月总充值金额</div><div className="text-xl font-bold text-green-700">{fmtMoneyByCurrency(data.total_amount_by_currency)}</div></div>
                <div className="bg-blue-50 rounded-xl p-4"><div className="text-xs text-blue-500 mb-1">总笔数</div><div className="text-xl font-bold text-blue-700">{data.total_count || 0} 笔</div></div>
              </div>
            )}
            {selected === "incoming-summary" && (
              <div className="grid grid-cols-2 gap-3 mb-3">
                <div className="bg-blue-50 rounded-xl p-4"><div className="text-xs text-blue-500 mb-1">当月总到账金额</div><div className="text-xl font-bold text-blue-700">{fmtMoneyByCurrency(data.total_amount_by_currency)}</div></div>
                <div className="bg-green-50 rounded-xl p-4"><div className="text-xs text-green-500 mb-1">总笔数</div><div className="text-xl font-bold text-green-700">{data.total_count || 0} 笔</div></div>
              </div>
            )}
            {selected === "income-expense" && (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
                <div className="bg-green-50 rounded-xl p-4"><div className="text-xs text-green-500 mb-1">总收入</div><div className="text-lg font-bold text-green-700">{fmtMoneyByCurrency(data.total_income_by_currency)}</div></div>
                <div className="bg-blue-50 rounded-xl p-4"><div className="text-xs text-blue-500 mb-1">到账收入</div><div className="text-lg font-bold text-blue-700">{fmtMoneyByCurrency(data.recharge_income_by_currency)}</div></div>
                <div className="bg-orange-50 rounded-xl p-4"><div className="text-xs text-orange-500 mb-1">其他收入</div><div className="text-lg font-bold text-orange-700">{fmtMoneyByCurrency(data.other_income_by_currency)}</div></div>
                <div className="bg-red-50 rounded-xl p-4"><div className="text-xs text-red-500 mb-1">总支出</div><div className="text-lg font-bold text-red-700">{fmtMoneyByCurrency(data.total_expense_by_currency)}</div></div>
              </div>
            )}
            {selected === "income-expense" && <InternalTransferSummary data={data.internal_transfers} />}
            {selected === "payable" && (
              <div className="grid grid-cols-2 gap-3 mb-3">
                <div className="bg-red-50 rounded-xl p-4"><div className="text-xs text-red-500 mb-1">待付总额</div><div className="text-xl font-bold text-red-700">{fmtMoneyByCurrency(data.total_pending_by_currency)}</div></div>
                <div className="bg-orange-50 rounded-xl p-4"><div className="text-xs text-orange-500 mb-1">逾期笔数</div><div className="text-xl font-bold text-orange-700">{data.overdue_count || 0} 笔</div></div>
              </div>
            )}
            {selected === "expense-fund" && (
              <div className="grid grid-cols-2 gap-3 mb-3">
                <div className="bg-orange-50 rounded-xl p-4"><div className="text-xs text-orange-500 mb-1">在途总额</div><div className="text-xl font-bold text-orange-700">{fmtMoneyByCurrency(data.in_transit_total_by_currency)}</div></div>
                <div className="bg-blue-50 rounded-xl p-4"><div className="text-xs text-blue-500 mb-1">总笔数</div><div className="text-xl font-bold text-blue-700">{data.total_count || 0} 笔</div></div>
              </div>
            )}
            {selected === "reimbursement" && (
              <div className="grid grid-cols-2 gap-3 mb-3">
                <div className="bg-teal-50 rounded-xl p-4"><div className="text-xs text-teal-500 mb-1">当月报销总额</div><div className="text-xl font-bold text-teal-700">{fmtMoneyByCurrency(data.total_amount_by_currency)}</div></div>
                <div className="bg-blue-50 rounded-xl p-4"><div className="text-xs text-blue-500 mb-1">总笔数</div><div className="text-xl font-bold text-blue-700">{data.total_count || 0} 笔</div></div>
              </div>
            )}
            {selected === "credit" && (
              <div className="grid grid-cols-2 gap-3 mb-3">
                <div className="bg-yellow-50 rounded-xl p-4"><div className="text-xs text-yellow-600 mb-1">总欠款</div><div className="text-xl font-bold text-yellow-700">{reportAmounts(data.total_debt_by_currency)}</div></div>
                <div className="bg-red-50 rounded-xl p-4"><div className="text-xs text-red-500 mb-1">逾期客户数</div><div className="text-xl font-bold text-red-700">{data.overdue_count || 0}</div></div>
              </div>
            )}
            {selected === "reconciliation-diff" && (
              <div className="grid grid-cols-2 gap-3 mb-3">
                <div className="bg-pink-50 rounded-xl p-4"><div className="text-xs text-pink-500 mb-1">差异笔数</div><div className="text-xl font-bold text-pink-700">{data.diff_count || 0} 笔</div></div>
                <div className="bg-red-50 rounded-xl p-4"><div className="text-xs text-red-500 mb-1">总差额</div><div className="text-xl font-bold text-red-700">{reportAmounts(data.total_diff_by_currency)}</div></div>
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
                        let display: any = val === null || val === undefined || val === "" ? "-" : val === "UNKNOWN" ? "待核对" : String(val);

                        // Date formatting
                        if (dateCols.has(k) && val && String(val).length >= 10) {
                          display = String(val).slice(0, 10);
                        }
                        // Amount columns: right-aligned bold, with currency symbol
                        if (amtCols.has(k) && typeof val === "number") {
                          const cur = row["币种"] || "THB";
                          display = cur === "UNKNOWN" ? `${val.toLocaleString()}（币种待核对）` : `${cur === "CNY" ? "¥" : "฿"}${val.toLocaleString()}`;
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

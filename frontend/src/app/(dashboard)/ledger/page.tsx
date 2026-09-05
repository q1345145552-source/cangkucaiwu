"use client";
import { useEffect, useState } from "react";
import { api, getToken } from "@/lib/api";
import { useRouter } from "next/navigation";
import { TrendingUp, TrendingDown, DollarSign, Search, Download, RotateCcw, ArrowUp, ArrowDown, Minus } from "lucide-react";

const SOURCE_OPTIONS = [
  { value: "", label: "全部来源" },
  { value: "recharge", label: "充值申报" },
  { value: "incoming", label: "到账流水" },
  { value: "expense_fund", label: "备用金领用" },
  { value: "fund_item", label: "备用金开销" },
  { value: "reimbursement", label: "报销" },
  { value: "payable", label: "应付账款" },
  { value: "manual", label: "手工收支" },
];

const TYPE_OPTIONS = [
  { value: "", label: "全部类型" },
  { value: "income", label: "收入" },
  { value: "expense", label: "支出" },
];

export default function LedgerPage() {
  const router = useRouter();
  const today = new Date();
  const curMonth = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}`;
  const todayStr = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`;

  const [data, setData] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(30);
  const [dateRange, setDateRange] = useState({ start_date: `${curMonth}-01`, end_date: todayStr });
  const [source, setSource] = useState("");
  const [flowType, setFlowType] = useState("");
  const [loading, setLoading] = useState(false);

  // summary cards
  const [totalIncome, setTotalIncome] = useState(0);
  const [totalExpense, setTotalExpense] = useState(0);
  const [net, setNet] = useState(0);

  useEffect(() => { if (!getToken()) router.push("/login"); }, []);
  useEffect(() => { setPage(1); }, [dateRange, source, flowType]);
  useEffect(() => { loadData(); }, [page, dateRange, source, flowType]);

  async function loadData() {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      params.set("page", String(page));
      params.set("page_size", String(pageSize));
      if (dateRange.start_date) params.set("start_date", dateRange.start_date);
      if (dateRange.end_date) params.set("end_date", dateRange.end_date);
      if (source) params.set("source", source);
      if (flowType) params.set("flow_type", flowType);
      const r = await api.get<any>(`/income-expense/ledger?${params.toString()}`);
      setData(r.data || []);
      setTotal(r.total || 0);
      setTotalIncome(r.total_income || 0);
      setTotalExpense(r.total_expense || 0);
      setNet(r.net || 0);
    } catch (err) { console.error("加载失败:", err); }
    setLoading(false);
  }

  async function handleExport() {
    const params = new URLSearchParams();
    if (dateRange.start_date) params.set("start_date", dateRange.start_date);
    if (dateRange.end_date) params.set("end_date", dateRange.end_date);
    if (source) params.set("source", source);
    if (flowType) params.set("flow_type", flowType);
    const token = getToken();
    const base = process.env.NEXT_PUBLIC_API_URL || "/api/v1";
    try {
      const res = await fetch(`${base}/income-expense/ledger/export?${params.toString()}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error("导出失败");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `ledger_${dateRange.start_date}_${dateRange.end_date}.xlsx`;
      document.body.appendChild(a); a.click();
      document.body.removeChild(a); URL.revokeObjectURL(url);
    } catch (err) { console.error("导出失败:", err); }
  }

  function handleReset() {
    setDateRange({ start_date: `${curMonth}-01`, end_date: todayStr });
    setSource("");
    setFlowType("");
  }

  return (
    <>
      {/* Page header */}
      <div className="flex items-center gap-3 mb-5">
        <div className="w-9 h-9 rounded-xl bg-indigo-100 flex items-center justify-center">
          <DollarSign size={20} className="text-indigo-600" />
        </div>
        <div className="flex-1">
          <h1 className="page-title">资金流水总览</h1>
          <p className="text-xs text-gray-400 mt-0.5">聚合充值申报、到账流水、备用金、报销、应付账款、手工收支所有资金变动</p>
        </div>
        <button onClick={handleExport} className="btn-primary flex items-center gap-1.5 text-sm">
          <Download size={15} />导出Excel
        </button>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-3 gap-4 mb-5">
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5">
          <div className="flex items-center gap-2 mb-2">
            <div className="w-8 h-8 rounded-lg bg-green-50 flex items-center justify-center">
              <TrendingUp size={16} className="text-green-600" />
            </div>
            <span className="text-xs text-gray-400">总收入</span>
          </div>
          <div className="text-2xl font-bold text-green-700">฿{totalIncome.toLocaleString()}</div>
        </div>
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5">
          <div className="flex items-center gap-2 mb-2">
            <div className="w-8 h-8 rounded-lg bg-red-50 flex items-center justify-center">
              <TrendingDown size={16} className="text-red-500" />
            </div>
            <span className="text-xs text-gray-400">总支出</span>
          </div>
          <div className="text-2xl font-bold text-red-600">฿{totalExpense.toLocaleString()}</div>
        </div>
        <div className={`bg-white rounded-2xl shadow-sm border p-5 ${net >= 0 ? "border-indigo-100" : "border-red-100"}`}>
          <div className="flex items-center gap-2 mb-2">
            <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${net >= 0 ? "bg-indigo-50" : "bg-red-50"}`}>
              {net >= 0 ? <ArrowUp size={16} className="text-indigo-600" /> : <ArrowDown size={16} className="text-red-500" />}
            </div>
            <span className="text-xs text-gray-400">净额</span>
          </div>
          <div className={`text-2xl font-bold ${net >= 0 ? "text-indigo-700" : "text-red-600"}`}>
            {net >= 0 ? "" : "-"}฿{Math.abs(net).toLocaleString()}
          </div>
        </div>
      </div>

      {/* Filters */}
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
        <div className="px-6 py-4 border-b bg-gray-50/50">
          <div className="flex items-end gap-3 flex-wrap">
            <div className="w-[150px]">
              <label className="form-label text-xs">开始日期</label>
              <input type="date" value={dateRange.start_date} onChange={e => setDateRange({ ...dateRange, start_date: e.target.value })} className="form-input text-sm" />
            </div>
            <div className="w-[150px]">
              <label className="form-label text-xs">结束日期</label>
              <input type="date" value={dateRange.end_date} onChange={e => setDateRange({ ...dateRange, end_date: e.target.value })} className="form-input text-sm" />
            </div>
            <div className="w-[150px]">
              <label className="form-label text-xs">来源模块</label>
              <select value={source} onChange={e => setSource(e.target.value)} className="form-input text-sm">
                {SOURCE_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            </div>
            <div className="w-[120px]">
              <label className="form-label text-xs">类型</label>
              <select value={flowType} onChange={e => setFlowType(e.target.value)} className="form-input text-sm">
                {TYPE_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            </div>
            <button onClick={() => { setPage(1); loadData(); }} className="btn-primary flex items-center gap-1.5 text-sm h-[38px]">
              <Search size={15} />查询
            </button>
            <button onClick={handleReset} className="btn-secondary flex items-center gap-1.5 text-sm h-[38px]">
              <RotateCcw size={15} />重置
            </button>
          </div>
        </div>

        {/* Table */}
        {loading ? (
          <div className="flex items-center justify-center py-16 text-gray-400">
            <div className="animate-spin w-6 h-6 border-2 border-blue-600 border-t-transparent rounded-full mr-2" />加载中...
          </div>
        ) : data.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-gray-400">
            <Minus size={44} className="text-gray-200 mb-3" />
            <span className="text-sm">暂无流水记录</span>
          </div>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-gray-100">
                    <th className="text-left px-4 py-3 font-medium text-gray-500 whitespace-nowrap">日期</th>
                    <th className="text-right px-4 py-3 font-medium text-gray-500 whitespace-nowrap">金额</th>
                    <th className="text-center px-4 py-3 font-medium text-gray-500 whitespace-nowrap">币种</th>
                    <th className="text-center px-4 py-3 font-medium text-gray-500 whitespace-nowrap">类型</th>
                    <th className="text-left px-4 py-3 font-medium text-gray-500 whitespace-nowrap">来源模块</th>
                    <th className="text-left px-4 py-3 font-medium text-gray-500 whitespace-nowrap">说明</th>
                    <th className="text-left px-4 py-3 font-medium text-gray-500 whitespace-nowrap">关联单号</th>
                  </tr>
                </thead>
                <tbody>
                  {data.map((row: any, i: number) => (
                    <tr key={`${row.source || 'x'}-${row.id}-${i}`} className="border-b hover:bg-gray-50/50">
                      <td className="px-4 py-3 text-gray-700 whitespace-nowrap">{row.date || "-"}</td>
                      <td className={`px-4 py-3 text-right whitespace-nowrap ${row.type === "income" ? "text-green-700" : "text-red-600"}`}>
                        <span className="inline-flex items-center gap-1 font-mono text-sm font-semibold">
                          {row.type === "income" ? <ArrowUp size={14} className="text-green-600" /> : <ArrowDown size={14} className="text-red-500" />}
                          ฿{(row.amount || 0).toLocaleString()}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-center text-gray-500">{row.currency || "THB"}</td>
                      <td className="px-4 py-3 text-center">
                        <span className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium ${row.type === "income" ? "bg-green-50 text-green-700" : "bg-red-50 text-red-600"}`}>
                          {row.type === "income" ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
                          {row.type === "income" ? "收入" : "支出"}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
                          row.source === "recharge" ? "bg-blue-50 text-blue-700" :
                          row.source === "incoming" ? "bg-cyan-50 text-cyan-700" :
                          row.source === "expense_fund" || row.source === "fund_item" ? "bg-orange-50 text-orange-700" :
                          row.source === "reimbursement" ? "bg-teal-50 text-teal-700" :
                          row.source === "payable" ? "bg-red-50 text-red-700" :
                          "bg-gray-100 text-gray-600"
                        }`}>
                          {row.source_label || row.source}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-gray-600 max-w-[260px] truncate" title={row.remark}>{row.remark || "-"}</td>
                      <td className="px-4 py-3 text-gray-400 text-xs font-mono whitespace-nowrap">{row.ref_no || "-"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            <div className="flex items-center justify-between px-6 py-4 border-t bg-gray-50/30">
              <span className="text-xs text-gray-400">共 {total} 条记录</span>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setPage(p => Math.max(1, p - 1))}
                  disabled={page <= 1}
                  className="btn-secondary text-xs px-3 py-1.5 disabled:opacity-40"
                >上一页</button>
                <span className="text-xs text-gray-500 px-2">第 {page} / {Math.max(1, Math.ceil(total / pageSize))} 页</span>
                <button
                  onClick={() => setPage(p => p + 1)}
                  disabled={page >= Math.ceil(total / pageSize)}
                  className="btn-secondary text-xs px-3 py-1.5 disabled:opacity-40"
                >下一页</button>
              </div>
            </div>
          </>
        )}
      </div>
    </>
  );
}

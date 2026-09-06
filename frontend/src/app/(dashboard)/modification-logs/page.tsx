"use client";
import { useEffect, useState } from "react";
import { api, getToken } from "@/lib/api";
import { useRouter } from "next/navigation";
import { History, Search, RotateCcw } from "lucide-react";

const MODULE_LABELS: Record<string, string> = {
  recharge: "充值申报",
  reimbursement: "报销",
  expense: "运营支出",
};
const OP_LABELS: Record<string, string> = { create: "新建", edit: "编辑", delete: "删除" };
const OP_COLORS: Record<string, string> = {
  create: "bg-green-100 text-green-700",
  edit: "bg-blue-100 text-blue-700",
  delete: "bg-red-100 text-red-700",
};
const FIELD_LABELS: Record<string, string> = {
  amount: "金额", currency: "币种", declare_date: "申报日期", expense_date: "支出日期",
  category_id: "类别", account_id: "账户", remark: "备注", voucher: "凭证",
  payment_method: "付款方式", customer_id: "客户", total_amount: "总额", submit_date: "提交日期",
  items: "明细", status: "状态", supplier_id: "供应商",
};

function diffSummary(before: any, after: any): string {
  if (!before || !after) return "";
  const keys = new Set([...Object.keys(before), ...Object.keys(after)]);
  const changed: string[] = [];
  keys.forEach(k => {
    if (JSON.stringify(before[k]) !== JSON.stringify(after[k])) changed.push(FIELD_LABELS[k] || k);
  });
  return changed.join("、");
}

function renderVal(v: any): string {
  if (v === null || v === undefined) return "-";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

export default function ModificationLogsPage() {
  const router = useRouter();
  const [data, setData] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [module, setModule] = useState("");
  const [operatorId, setOperatorId] = useState(0);
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [operators, setOperators] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [detail, setDetail] = useState<any>(null);

  useEffect(() => { if (!getToken()) router.push("/login"); loadOperators(); }, []);
  useEffect(() => { load(); }, [page, module, operatorId, startDate, endDate]);

  async function loadOperators() {
    try {
      const r = await api.get<any>("/history/operators");
      setOperators(r.data || []);
    } catch {}
  }

  async function load() {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      params.set("page", String(page)); params.set("page_size", "20");
      if (module) params.set("module", module);
      if (operatorId) params.set("operator_id", String(operatorId));
      if (startDate) params.set("start_date", startDate);
      if (endDate) params.set("end_date", endDate);
      const r = await api.get<any>(`/history?${params.toString()}`);
      setData(r.data || []);
      setTotal(r.total || 0);
    } catch (err) { console.error("加载失败:", err); }
    setLoading(false);
  }

  function resetFilters() {
    setModule(""); setOperatorId(0); setStartDate(""); setEndDate(""); setPage(1);
  }

  return (
    <>
      <div className="flex items-center gap-3 mb-5">
        <div className="w-9 h-9 rounded-xl bg-indigo-100 flex items-center justify-center">
          <History size={20} className="text-indigo-600" />
        </div>
        <div>
          <h1 className="page-title">修改日志</h1>
          <p className="text-xs text-gray-400 mt-0.5">充值申报 / 报销 / 运营支出 的新建、编辑、删除记录</p>
        </div>
      </div>

      {/* 筛选 */}
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-4 mb-5">
        <div className="flex items-end gap-3 flex-wrap">
          <div className="w-[150px]">
            <label className="form-label text-xs">模块</label>
            <select className="form-input text-sm" value={module} onChange={e => { setModule(e.target.value); setPage(1); }}>
              <option value="">全部模块</option>
              <option value="recharge">充值申报</option>
              <option value="reimbursement">报销</option>
              <option value="expense">运营支出</option>
            </select>
          </div>
          <div className="w-[160px]">
            <label className="form-label text-xs">操作人</label>
            <select className="form-input text-sm" value={operatorId} onChange={e => { setOperatorId(+e.target.value); setPage(1); }}>
              <option value={0}>全部操作人</option>
              {operators.map((o: any) => <option key={o.operator_id} value={o.operator_id}>{o.operator_name}</option>)}
            </select>
          </div>
          <div className="w-[140px]">
            <label className="form-label text-xs">开始日期</label>
            <input type="date" className="form-input text-sm" value={startDate} onChange={e => { setStartDate(e.target.value); setPage(1); }} />
          </div>
          <div className="w-[140px]">
            <label className="form-label text-xs">结束日期</label>
            <input type="date" className="form-input text-sm" value={endDate} onChange={e => { setEndDate(e.target.value); setPage(1); }} />
          </div>
          <button onClick={resetFilters} className="btn-secondary flex items-center gap-1.5 text-sm h-[38px]">
            <RotateCcw size={14} />重置
          </button>
        </div>
      </div>

      {/* 列表 */}
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center py-16 text-gray-400"><div className="animate-spin w-6 h-6 border-2 border-indigo-600 border-t-transparent rounded-full mr-2" />加载中...</div>
        ) : data.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-gray-400"><History size={44} className="text-gray-200 mb-3" /><span className="text-sm">暂无修改记录</span></div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50">
                  <th className="text-left px-4 py-3 font-medium text-gray-500">模块</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-500">记录编号</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-500">操作人</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-500">操作时间</th>
                  <th className="text-center px-4 py-3 font-medium text-gray-500">操作类型</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-500">修改内容</th>
                </tr>
              </thead>
              <tbody>
                {data.map((h: any) => (
                  <tr key={h.id} className="border-b hover:bg-gray-50/50 cursor-pointer" onClick={() => setDetail(h)}>
                    <td className="px-4 py-3 text-gray-700">{MODULE_LABELS[h.module] || h.module}</td>
                    <td className="px-4 py-3 text-gray-600 font-mono">#{h.record_id}</td>
                    <td className="px-4 py-3 text-gray-700">{h.operator_name || "-"}</td>
                    <td className="px-4 py-3 text-gray-500">{h.created_at ? new Date(h.created_at).toLocaleString("zh-CN", { timeZone: "Asia/Bangkok" }) : "-"}</td>
                    <td className="px-4 py-3 text-center">
                      <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${OP_COLORS[h.operation_type] || ""}`}>{OP_LABELS[h.operation_type] || h.operation_type}</span>
                    </td>
                    <td className="px-4 py-3 text-gray-600">
                      {h.operation_type === "edit" ? (diffSummary(h.before_data, h.after_data) || "更新") : h.operation_type === "delete" ? "删除记录" : "新建记录"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {total > 20 && (
          <div className="flex items-center justify-center gap-3 py-3 border-t">
            <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page <= 1} className="px-3 py-1 text-sm border rounded disabled:opacity-30">上一页</button>
            <span className="text-sm text-gray-500">{page} / {Math.ceil(total / 20)}</span>
            <button onClick={() => setPage(p => p + 1)} disabled={page >= Math.ceil(total / 20)} className="px-3 py-1 text-sm border rounded disabled:opacity-30">下一页</button>
          </div>
        )}
      </div>

      {/* 详情弹窗 */}
      {detail && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-[70] p-4" onClick={() => setDetail(null)}>
          <div className="bg-white rounded-2xl w-full max-w-lg max-h-[80vh] overflow-y-auto shadow-2xl" onClick={e => e.stopPropagation()}>
            <div className="bg-gray-800 text-white px-6 py-4 rounded-t-2xl flex items-center gap-3 sticky top-0">
              <h2 className="text-lg font-semibold">修改详情</h2>
              <button onClick={() => setDetail(null)} className="ml-auto text-gray-300 hover:text-white text-xl leading-none">&times;</button>
            </div>
            <div className="p-5 space-y-4">
              <div className="flex items-center gap-2">
                <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${OP_COLORS[detail.operation_type] || ""}`}>{OP_LABELS[detail.operation_type] || detail.operation_type}</span>
                <span className="text-sm text-gray-600">{MODULE_LABELS[detail.module] || detail.module} · #{detail.record_id}</span>
                <span className="text-xs text-gray-400 ml-auto">{detail.operator_name || "-"} · {detail.created_at ? new Date(detail.created_at).toLocaleString("zh-CN", { timeZone: "Asia/Bangkok" }) : "-"}</span>
              </div>

              {detail.before_data && (
                <div className="bg-gray-50 rounded-lg p-3">
                  <div className="text-xs text-gray-400 mb-1.5">修改前</div>
                  <div className="space-y-1">
                    {Object.entries(detail.before_data).map(([k, v]) => (
                      <div key={k} className="text-sm flex gap-2"><span className="text-gray-500 w-20 shrink-0">{FIELD_LABELS[k] || k}</span><span className="text-gray-700 break-all">{renderVal(v)}</span></div>
                    ))}
                  </div>
                </div>
              )}

              {detail.after_data && (
                <div className="bg-blue-50 rounded-lg p-3">
                  <div className="text-xs text-blue-400 mb-1.5">修改后</div>
                  <div className="space-y-1">
                    {Object.entries(detail.after_data).map(([k, v]) => (
                      <div key={k} className="text-sm flex gap-2"><span className="text-blue-500 w-20 shrink-0">{FIELD_LABELS[k] || k}</span><span className="text-blue-700 break-all">{renderVal(v)}</span></div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}

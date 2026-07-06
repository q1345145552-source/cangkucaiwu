"use client";
import { useEffect, useState } from "react";
import { api, getToken } from "@/lib/api";
import { useToast } from "@/components/ui/Toast";
import { useRouter } from "next/navigation";
import { CheckCircle, XCircle, FileText, Search, X, Image as ImageIcon, Eye } from "lucide-react";

export default function FundReviewPage() {
  const { toast } = useToast(); const router = useRouter();
  const [data, setData] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [employees, setEmployees] = useState<any[]>([]);

  // Filters
  const [selEmployee, setSelEmployee] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [selCurrency, setSelCurrency] = useState("");

  // Selection
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [rejectRemark, setRejectRemark] = useState("");

  // Receipt preview
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);

  useEffect(() => { if (!getToken()) router.push("/login"); load(); loadEmployees(); }, []);

  async function load() {
    setLoading(true);
    try {
      const params = new URLSearchParams({ page_size: "100" });
      if (selEmployee) params.set("employee_id", selEmployee);
      if (startDate) params.set("start_date", startDate);
      if (endDate) params.set("end_date", endDate);
      if (selCurrency) params.set("currency", selCurrency);
      const r = await api.get<any>(`/expense-fund/review/pending?${params.toString()}`);
      setData(r.data || []);
    } catch (err) { console.error("加载失败:", err); }
    setLoading(false); setSelectedIds(new Set());
  }

  async function loadEmployees() {
    try {
      const r = await api.get<any>("/expense-fund/accounts");
      const emps = (r.data || []).map((a: any) => ({ id: a.employee_id, name: a.employee_name }));
      // dedupe
      const seen = new Set<number>();
      setEmployees(emps.filter((e: any) => { if (seen.has(e.id)) return false; seen.add(e.id); return true; }));
    } catch {}
  }

  function toggleAll() {
    if (selectedIds.size === data.length) setSelectedIds(new Set());
    else setSelectedIds(new Set(data.map(r => r.id)));
  }
  function toggleOne(id: number) {
    setSelectedIds(prev => { const n = new Set(prev); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  }

  async function doReview(action: "approve" | "reject") {
    if (selectedIds.size === 0) { toast("error", "请先勾选要审核的记录"); return; }
    try {
      await api.post("/expense-fund/review/batch", {
        item_ids: Array.from(selectedIds), action,
        remark: action === "reject" ? rejectRemark : undefined,
      });
      toast("success", action === "approve" ? "已批量通过" : "已批量驳回");
      setRejectRemark(""); load();
    } catch (err: any) { toast("error", err.message || "审核失败"); }
  }

  async function approveOne(id: number) {
    try {
      await api.post("/expense-fund/review/batch", { item_ids: [id], action: "approve" });
      toast("success", "已通过");
      load();
    } catch (err: any) { toast("error", err.message || "审核失败"); }
  }
  function rejectOne(id: number) {
    const reason = prompt("请输入驳回原因");
    if (reason === null) return;
    (async () => {
      try {
        await api.post("/expense-fund/review/batch", { item_ids: [id], action: "reject", remark: reason });
        toast("success", "已驳回");
        load();
      } catch (err: any) { toast("error", err.message || "审核失败"); }
    })();
  }

  return (
    <>
      <div className="mb-5">
        <h1 className="page-title">备用金审核</h1>
        <div className="text-sm text-gray-400 mt-1">{data.length} 条待审核</div>
      </div>

      {/* 筛选栏 */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-100 px-5 py-3 mb-4">
        <div className="flex items-center gap-3 flex-wrap">
          <div className="flex items-center gap-1.5">
            <label className="text-xs text-gray-500 whitespace-nowrap">员工</label>
            <select className="form-input text-sm py-1.5 w-36" value={selEmployee} onChange={e => setSelEmployee(e.target.value)}>
              <option value="">全部</option>
              {employees.map(e => <option key={e.id} value={e.id}>{e.name}</option>)}
            </select>
          </div>
          <div className="flex items-center gap-1.5">
            <label className="text-xs text-gray-500 whitespace-nowrap">日期</label>
            <input type="date" className="form-input text-sm py-1.5 w-36" value={startDate} onChange={e => setStartDate(e.target.value)} />
            <span className="text-gray-300 text-xs">至</span>
            <input type="date" className="form-input text-sm py-1.5 w-36" value={endDate} onChange={e => setEndDate(e.target.value)} />
          </div>
          <div className="flex items-center gap-1.5">
            <label className="text-xs text-gray-500 whitespace-nowrap">币种</label>
            <select className="form-input text-sm py-1.5 w-24" value={selCurrency} onChange={e => setSelCurrency(e.target.value)}>
              <option value="">全部</option>
              <option value="THB">THB</option>
              <option value="CNY">CNY</option>
            </select>
          </div>
          <button onClick={load} className="btn-primary text-sm flex items-center gap-1 py-1.5">
            <Search size={14} />查询
          </button>
          {selectedIds.size > 0 && (
            <div className="flex items-center gap-2 ml-auto">
              <button onClick={() => doReview("approve")} className="btn-primary text-sm bg-green-600 hover:bg-green-700 flex items-center gap-1">
                <CheckCircle size={15} />通过所选 ({selectedIds.size})
              </button>
              <button onClick={() => doReview("reject")} className="btn-secondary text-sm text-red-600 border-red-300 hover:bg-red-50 flex items-center gap-1">
                <XCircle size={15} />驳回所选
              </button>
              <input className="form-input text-sm py-1 w-36" placeholder="驳回原因" value={rejectRemark} onChange={e => setRejectRemark(e.target.value)} />
            </div>
          )}
        </div>
      </div>

      {/* 表格 */}
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center h-40 text-gray-400">
            <div className="animate-spin w-5 h-5 border-2 border-blue-600 border-t-transparent rounded-full mr-2" />加载中...
          </div>
        ) : data.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-gray-400">
            <FileText size={44} className="text-gray-200 mb-3" />
            <span className="text-sm">暂无待审核记录</span>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-gray-50">
                  <th className="text-left px-2 py-3 w-10">
                    <input type="checkbox" checked={selectedIds.size === data.length && data.length > 0} onChange={toggleAll} className="rounded" />
                  </th>
                  <th className="text-left px-3 py-3 font-medium text-gray-500 whitespace-nowrap">员工</th>
                  <th className="text-left px-3 py-3 font-medium text-gray-500 whitespace-nowrap">仓库</th>
                  <th className="text-right px-3 py-3 font-medium text-gray-500 whitespace-nowrap">额度</th>
                  <th className="text-left px-3 py-3 font-medium text-gray-500 whitespace-nowrap">领用日期</th>
                  <th className="text-left px-3 py-3 font-medium text-gray-500 whitespace-nowrap">开销日期</th>
                  <th className="text-left px-3 py-3 font-medium text-gray-500 whitespace-nowrap">类别</th>
                  <th className="text-right px-3 py-3 font-medium text-gray-500 whitespace-nowrap">金额</th>
                  <th className="text-center px-3 py-3 font-medium text-gray-500 whitespace-nowrap w-14">币种</th>
                  <th className="text-left px-3 py-3 font-medium text-gray-500 whitespace-nowrap">说明</th>
                  <th className="text-center px-3 py-3 font-medium text-gray-500 whitespace-nowrap">凭证</th>
                  <th className="text-center px-3 py-3 font-medium text-gray-500 whitespace-nowrap">状态</th>
                  <th className="text-center px-3 py-3 font-medium text-gray-500 whitespace-nowrap w-24">操作</th>
                </tr>
              </thead>
              <tbody>
                {data.map((row: any) => (
                  <tr key={row.id} className={`border-b hover:bg-gray-50/50 ${selectedIds.has(row.id) ? "bg-blue-50" : ""}`}>
                    <td className="px-2 py-3">
                      <input type="checkbox" checked={selectedIds.has(row.id)} onChange={() => toggleOne(row.id)} className="rounded" />
                    </td>
                    <td className="px-3 py-3 font-medium text-gray-800">{row.employee_name}</td>
                    <td className="px-3 py-3 text-gray-500">{row.warehouse_name}</td>
                    <td className="px-3 py-3 text-right text-gray-500">฿{(row.fund_limit || 5000).toLocaleString()}</td>
                    <td className="px-3 py-3 text-gray-500">{row.receive_date?.slice(0, 10) || "-"}</td>
                    <td className="px-3 py-3">{row.expense_date?.slice(0, 10)}</td>
                    <td className="px-3 py-3">{row.category}</td>
                    <td className="px-3 py-3 text-right font-medium">
                      {row.currency === "CNY" ? "¥" : "฿"}{row.amount?.toLocaleString()}
                    </td>
                    <td className="px-3 py-3 text-center">
                      <span className={`px-1.5 py-0.5 rounded text-xs ${row.currency === "CNY" ? "bg-red-50 text-red-600" : "bg-blue-50 text-blue-600"}`}>
                        {row.currency || "THB"}
                      </span>
                    </td>
                    <td className="px-3 py-3 text-gray-600 max-w-[140px] truncate">{row.description}</td>
                    <td className="px-3 py-3 text-center">
                      {row.receipt ? (
                        <button onClick={() => setPreviewUrl(row.receipt)} className="text-blue-500 hover:text-blue-700" title="点击查看凭证">
                          <Eye size={16} />
                        </button>
                      ) : (
                        <span className="text-gray-300">-</span>
                      )}
                    </td>
                    <td className="px-3 py-3 text-center">
                      <span className="px-2 py-0.5 rounded-full text-xs bg-yellow-50 text-yellow-700 font-medium">待审核</span>
                    </td>
                    <td className="px-3 py-3 text-center">
                      <div className="flex items-center justify-center gap-1.5">
                        <button onClick={() => approveOne(row.id)}
                          className="p-1 rounded hover:bg-green-50 text-green-600 transition-colors" title="通过">
                          <CheckCircle size={16} />
                        </button>
                        <button onClick={() => rejectOne(row.id)}
                          className="p-1 rounded hover:bg-red-50 text-red-500 transition-colors" title="驳回">
                          <XCircle size={16} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* 凭证大图弹窗 */}
      {previewUrl && (
        <div className="modal-overlay z-50" onClick={() => setPreviewUrl(null)}>
          <div className="bg-white rounded-2xl max-w-2xl max-h-[85vh] overflow-auto shadow-2xl" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between px-5 py-3 border-b">
              <h3 className="font-semibold text-gray-700 flex items-center gap-2">
                <ImageIcon size={18} />凭证查看
              </h3>
              <button onClick={() => setPreviewUrl(null)} className="text-gray-400 hover:text-gray-600">
                <X size={20} />
              </button>
            </div>
            <div className="p-4 flex items-center justify-center bg-gray-100">
              <img src={previewUrl} alt="凭证" className="max-w-full max-h-[70vh] object-contain rounded" />
            </div>
          </div>
        </div>
      )}
    </>
  );
}

"use client";
import { useEffect, useState } from "react";
import { useToast } from "@/components/ui/Toast";
import { api, getToken } from "@/lib/api";
import { useRouter } from "next/navigation";
import DataTable from "@/components/common/DataTable";
import { Download, Link2, CheckCircle, Search, ArrowRight, Image as ImageIcon } from "lucide-react";

export default function ReconciliationPage() {
  const { toast } = useToast(); const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [loadingResults, setLoadingResults] = useState(false);

  const today = new Date(); const yyyy = today.getFullYear(); const mm = String(today.getMonth()+1).padStart(2,"0");
  const [startDate, setStartDate] = useState(`${yyyy}-${mm}-01`);
  const [endDate, setEndDate] = useState(`${yyyy}-${mm}-${String(today.getDate()).padStart(2,"0")}`);
  const [warehouses, setWarehouses] = useState<any[]>([]);
  const [whId, setWhId] = useState(0);

  const [decls, setDecls] = useState<any[]>([]);
  const [flows, setFlows] = useState<any[]>([]);
  const [selectedDeclId, setSelectedDeclId] = useState<number | null>(null);
  const [selectedFlowId, setSelectedFlowId] = useState<number | null>(null);
  const [note, setNote] = useState("");
  const [showMatchConfirm, setShowMatchConfirm] = useState(false);
  const [previewScreenshot, setPreviewScreenshot] = useState("");

  const [results, setResults] = useState<any[]>([]);
  const [resultsTotal, setResultsTotal] = useState(0);
  const [resultsPage, setResultsPage] = useState(1);
  const [resultsStartDate, setResultsStartDate] = useState(`${yyyy}-${mm}-01`);
  const [resultsEndDate, setResultsEndDate] = useState(`${yyyy}-${mm}-${String(today.getDate()).padStart(2,"0")}`);
  const [resultsSearch, setResultsSearch] = useState("");
  const [resultsSearchCode, setResultsSearchCode] = useState("");
  const [resultsDeclTotal, setResultsDeclTotal] = useState(0);
  const [resultsFlowTotal, setResultsFlowTotal] = useState(0);

  function setThisMonth() {
    setStartDate(`${yyyy}-${mm}-01`);
    setEndDate(`${yyyy}-${mm}-${String(today.getDate()).padStart(2,"0")}`);
  }
  function setLastMonth() {
    const d = new Date(today.getFullYear(), today.getMonth()-1, 1);
    const lastDay = new Date(today.getFullYear(), today.getMonth(), 0).getDate();
    setStartDate(`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}-01`);
    setEndDate(`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}-${lastDay}`);
  }

  useEffect(() => { if (!getToken()) router.push("/login"); loadWarehouses(); }, []);

  async function loadWarehouses() {
    try {
      const r = await api.get<any>("/warehouses"); setWarehouses(r.data);
      if (r.data.length > 0) {
        const wid = r.data[0].id; setWhId(wid);
        queryUnmatched(startDate, endDate, wid);
        loadResults(resultsStartDate, resultsEndDate, wid);
      }
    } catch {}
  }

  async function queryUnmatched(sd?: string, ed?: string, wid?: number) {
    const s = sd || startDate; const e = ed || endDate; const w = wid ?? whId;
    setLoading(true);
    try {
      const res = await api.get<any>(`/reconciliation/unmatched?start_date=${s}&end_date=${e}&warehouse_id=${w}`);
      setDecls(res.declarations || []);
      setFlows(res.incoming || []);
      setSelectedDeclId(null); setSelectedFlowId(null);
    } catch (err: any) { toast("error", err.message || "查询失败"); }
    setLoading(false);
  }

  async function loadResults(sd?: string, ed?: string, wid?: number) {
    const s = sd || resultsStartDate; const e = ed || resultsEndDate; const w = wid ?? whId;
    setLoadingResults(true);
    try {
      let url = `/reconciliation/results?start_date=${s}&end_date=${e}&warehouse_id=${w}&page=${resultsPage}&page_size=50`;
      if (resultsSearch) url += `&search=${encodeURIComponent(resultsSearch)}`;
      if (resultsSearchCode) url += `&search_code=${encodeURIComponent(resultsSearchCode)}`;
      const res = await api.get<any>(url);
      setResults(res.data); setResultsTotal(res.total);
      setResultsDeclTotal(res.total_matched_decl || 0);
      setResultsFlowTotal(res.total_matched_flow || 0);
    } catch {}
    setLoadingResults(false);
  }

  function handleQuery() {
    const sd = startDate; const ed = endDate; const w = whId;
    setResultsStartDate(sd); setResultsEndDate(ed);
    queryUnmatched(sd, ed, w);
    loadResults(sd, ed, w);
  }

  useEffect(() => {
    if (whId > 0) loadResults();
  }, [resultsPage, resultsStartDate, resultsEndDate, resultsSearch, resultsSearchCode]);

  function triggerMatch() {
    if (!selectedDeclId || !selectedFlowId) { toast("error", "请分别选择一条申报和一条流水"); return; }
    setNote(""); setShowMatchConfirm(true);
  }

  async function confirmMatch() {
    try {
      await api.post(`/reconciliation/manual-match?declaration_id=${selectedDeclId}&flow_id=${selectedFlowId}&handling_note=${encodeURIComponent(note)}`, {});
      toast("success", "匹配成功");
      setShowMatchConfirm(false);
      setSelectedDeclId(null); setSelectedFlowId(null);
      queryUnmatched();
      setResultsPage(1); loadResults();
    } catch (err: any) { toast("error", err.message || "匹配失败"); }
  }

  async function handleUnmatch(row: any) {
    if (!confirm("确认解除匹配？")) return;
    try {
      await api.post(`/reconciliation/unmatch?record_id=${row.id}`, {});
      toast("success", "已解除匹配");
      queryUnmatched(); loadResults();
    } catch (err: any) { toast("error", err.message || "操作失败"); }
  }

  async function handleExport() {
    try {
      let url = `${process.env.NEXT_PUBLIC_API_URL || "/api/v1"}/reconciliation/export?start_date=${resultsStartDate}&end_date=${resultsEndDate}&warehouse_id=${whId}`;
      if (resultsSearch) url += `&search=${encodeURIComponent(resultsSearch)}`;
      if (resultsSearchCode) url += `&search_code=${encodeURIComponent(resultsSearchCode)}`;
      const res = await fetch(url, { headers: { "Authorization": `Bearer ${getToken()}` } });
      const blob = await res.blob();
      const a = document.createElement("a"); a.href = window.URL.createObjectURL(blob);
      a.download = `reconciliation_${resultsStartDate}_${resultsEndDate}.xlsx`; a.click();
      toast("success", "导出成功");
    } catch { toast("error", "导出失败"); }
  }

  function toggleDecl(id: number) { setSelectedDeclId(prev => prev === id ? null : id); }
  function toggleFlow(id: number) { setSelectedFlowId(prev => prev === id ? null : id); }

  const declColumns = [
    { key: "_sel", label: "", headerRender: () => <span className="text-xs text-gray-400">选</span>, render: (_: any, row: any) => (
      <button onClick={() => toggleDecl(row.id)} className={`w-5 h-5 rounded-full border-2 flex items-center justify-center transition-all ${selectedDeclId === row.id ? "bg-blue-600 border-blue-600 text-white" : "border-gray-300 hover:border-blue-400"}`}>{selectedDeclId === row.id ? <CheckCircle size={14} /> : null}</button>
    )},
    { key: "customer_code", label: "编号" }, { key: "customer_name", label: "客户" },
    { key: "declare_date", label: "申报日期", render: (v: string) => v?.slice(0,10) },
    { key: "amount", label: "金额", align: "right" as const, render: (v: number, row: any) => `${v?.toLocaleString()} ${row.currency || ""}` },
    { key: "screenshot", label: "截图", render: (v: string) => v ? (
      <button onClick={() => setPreviewScreenshot(v.startsWith("http") ? v : `/${v}`)} className="text-blue-600 text-xs hover:underline flex items-center gap-0.5"><ImageIcon size={12} />查看</button>
    ) : <span className="text-red-400 text-xs">未上传</span> },
    { key: "payment_method", label: "方式", render: (v: string) => v || "-" },
  ];

  const flowColumns = [
    { key: "_sel", label: "", headerRender: () => <span className="text-xs text-gray-400">选</span>, render: (_: any, row: any) => (
      <button onClick={() => toggleFlow(row.id)} className={`w-5 h-5 rounded-full border-2 flex items-center justify-center transition-all ${selectedFlowId === row.id ? "bg-green-600 border-green-600 text-white" : "border-gray-300 hover:border-green-400"}`}>{selectedFlowId === row.id ? <CheckCircle size={14} /> : null}</button>
    )},
    { key: "payer_name", label: "付款方" },
    { key: "received_date", label: "到账日期", render: (v: string) => v?.slice(0,10) },
    { key: "amount", label: "金额", align: "right" as const, render: (v: number, row: any) => `${v?.toLocaleString()} ${row.currency || ""}` },
    { key: "screenshot", label: "截图", render: (v: string) => v ? (
      <button onClick={() => setPreviewScreenshot(v.startsWith("http") ? v : `/${v}`)} className="text-blue-600 text-xs hover:underline flex items-center gap-0.5"><ImageIcon size={12} />查看</button>
    ) : <span className="text-red-400 text-xs">未上传</span> },
    { key: "payment_method", label: "方式", render: (v: string) => v || "-" },
  ];

  const resultColumns = [
    { key: "created_at", label: "匹配时间", render: (v: string) => v?.slice(0,16)?.replace("T"," ") },
    { key: "customer_code", label: "客户编号" },
    { key: "customer_name", label: "客户名称" },
    { key: "decl_amount", label: "申报金额", align: "right" as const, render: (v: number, row: any) => v ? `${v?.toLocaleString()} ${row.decl_currency||""}` : "-" },
    { key: "flow_payer", label: "流水付款方" },
    { key: "flow_amount", label: "流水金额", align: "right" as const, render: (v: number, row: any) => v ? `${v?.toLocaleString()} ${row.flow_currency||""}` : "-" },
    { key: "amount_diff", label: "差额", align: "right" as const, render: (v: number) => v ? <span className="text-orange-600 font-medium">{v}</span> : <span className="text-green-600">0</span> },
    { key: "handling_note", label: "备注", render: (v: string) => v || "-" },
    { key: "id", label: "操作", render: (_: any, row: any) => (
      <button onClick={() => handleUnmatch(row)} className="btn-secondary btn-xs">解除匹配</button>
    )},
  ];

  return (
    <>
      <h1 className="page-title mb-5">对账中心</h1>

      {/* 筛选栏 */}
      <div className="card mb-4 p-4">
        <div className="flex items-end gap-3 flex-wrap">
          <button onClick={setThisMonth} className={`h-10 px-4 rounded-lg text-sm font-medium ${startDate === `${yyyy}-${mm}-01` ? "bg-blue-600 text-white" : "bg-gray-100 text-gray-600 hover:bg-gray-200"}`}>本月</button>
          <button onClick={setLastMonth} className="h-10 px-4 rounded-lg text-sm font-medium bg-gray-100 text-gray-600 hover:bg-gray-200">上月</button>
          <div className="w-[140px]"><label className="form-label">开始日期</label><input type="date" className="form-input" value={startDate} onChange={e => setStartDate(e.target.value)} /></div>
          <div className="w-[140px]"><label className="form-label">结束日期</label><input type="date" className="form-input" value={endDate} onChange={e => setEndDate(e.target.value)} /></div>
          <div className="w-[160px]"><label className="form-label">仓库</label>
            <select className="form-input" value={whId} onChange={e => setWhId(+e.target.value)}>
              {warehouses.map((w: any) => <option key={w.id} value={w.id}>{w.name}</option>)}
            </select>
          </div>
          <button onClick={handleQuery} className="btn-primary h-10 flex items-center gap-1.5"><Search size={16} />查询</button>
        </div>
      </div>

      {/* 左右双栏 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6 relative">
        <div className="card border-blue-200">
          <div className="bg-blue-50 px-4 py-3 rounded-t-xl border-b flex items-center gap-2">
            <span className="font-semibold text-sm text-blue-700">未匹配充值申报</span>
            <span className="text-xs text-blue-500 bg-blue-100 px-2 py-0.5 rounded-full">{decls.length} 条</span>
            {selectedDeclId && <span className="text-xs text-blue-400 ml-auto">已选 1 条 · <button onClick={() => setSelectedDeclId(null)} className="underline hover:text-blue-600">取消</button></span>}
          </div>
          <div className="overflow-auto max-h-[420px]">
            {loading ? <div className="text-center py-12 text-gray-400">加载中...</div> : decls.length === 0 ? <div className="text-center py-12 text-gray-400">暂无未匹配申报</div> : (
              <DataTable columns={declColumns} data={decls} total={decls.length} page={1} pageSize={100} onPageChange={() => {}} />
            )}
          </div>
        </div>
        <div className="card border-green-200">
          <div className="bg-green-50 px-4 py-3 rounded-t-xl border-b flex items-center gap-2">
            <span className="font-semibold text-sm text-green-700">未匹配到账流水</span>
            <span className="text-xs text-green-500 bg-green-100 px-2 py-0.5 rounded-full">{flows.length} 条</span>
            {selectedFlowId && <span className="text-xs text-green-400 ml-auto">已选 1 条 · <button onClick={() => setSelectedFlowId(null)} className="underline hover:text-green-600">取消</button></span>}
          </div>
          <div className="overflow-auto max-h-[420px]">
            {loading ? <div className="text-center py-12 text-gray-400">加载中...</div> : flows.length === 0 ? <div className="text-center py-12 text-gray-400">暂无未匹配流水</div> : (
              <DataTable columns={flowColumns} data={flows} total={flows.length} page={1} pageSize={100} onPageChange={() => {}} />
            )}
          </div>
        </div>
        {selectedDeclId && selectedFlowId && (
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-10">
            <button onClick={triggerMatch} className="bg-blue-600 hover:bg-blue-700 text-white h-12 px-6 rounded-full shadow-2xl flex items-center gap-2 font-semibold">
              <Link2 size={20} /> 匹配 <ArrowRight size={16} />
            </button>
          </div>
        )}
      </div>

      {/* 匹配确认弹窗 */}
      {showMatchConfirm && (
        <div className="modal-overlay" onClick={() => setShowMatchConfirm(false)}>
          <div className="bg-white rounded-xl w-full max-w-md shadow-2xl" onClick={e => e.stopPropagation()}>
            <div className="bg-blue-600 text-white px-6 py-4 rounded-t-xl flex items-center gap-3">
              <Link2 size={22} /><h2 className="text-lg font-semibold">确认匹配</h2>
              <div className="flex-1" /><button onClick={() => setShowMatchConfirm(false)} className="text-blue-200 hover:text-white text-xl leading-none">&times;</button>
            </div>
            <div className="p-6 space-y-4">
              <div><div className="text-xs text-gray-400 mb-1">申报记录</div><div className="bg-blue-50 rounded-lg p-3 text-sm">{decls.find(d => d.id === selectedDeclId)?.customer_name} · ¥{decls.find(d => d.id === selectedDeclId)?.amount?.toLocaleString()}</div></div>
              <div><div className="text-xs text-gray-400 mb-1">到账流水</div><div className="bg-green-50 rounded-lg p-3 text-sm">{flows.find(f => f.id === selectedFlowId)?.payer_name} · ¥{flows.find(f => f.id === selectedFlowId)?.amount?.toLocaleString()}</div></div>
              {(() => {
                const d = decls.find(d => d.id === selectedDeclId); const f = flows.find(f => f.id === selectedFlowId);
                const diff = (d?.amount || 0) - (f?.amount || 0);
                return diff !== 0 ? <div className="bg-orange-50 border border-orange-200 rounded-lg p-3 text-sm text-orange-700">差异金额：¥{Math.abs(diff).toLocaleString()}</div>
                  : <div className="bg-green-50 border border-green-200 rounded-lg p-3 text-sm text-green-700 flex items-center gap-2"><CheckCircle size={16} />金额一致</div>;
              })()}
              <div className="form-group"><label className="form-label">备注说明</label><input className="form-input" value={note} onChange={e => setNote(e.target.value)} placeholder="匹配备注（可选）" /></div>
            </div>
            <div className="border-t px-6 py-4 bg-gray-50 rounded-b-xl flex justify-end gap-3">
              <button onClick={() => setShowMatchConfirm(false)} className="btn-secondary min-w-[80px]">取消</button>
              <button onClick={confirmMatch} className="btn-primary min-w-[80px]">确认匹配</button>
            </div>
          </div>
        </div>
      )}

      {/* 截图预览弹窗 */}
      {previewScreenshot && (
        <div className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center" onClick={() => setPreviewScreenshot("")}>
          <div className="relative max-w-[90vw] max-h-[90vh]" onClick={e => e.stopPropagation()}>
            <button onClick={() => setPreviewScreenshot("")} className="absolute top-2 right-2 text-white bg-black/50 hover:bg-black/70 rounded-full w-8 h-8 flex items-center justify-center z-10 text-lg leading-none">&times;</button>
            <div className="absolute top-2 left-4 text-white text-sm bg-black/50 px-3 py-1 rounded-full">付款截图</div>
            <img src={previewScreenshot} alt="付款截图" className="max-w-[90vw] max-h-[85vh] object-contain rounded-lg shadow-2xl" />
          </div>
        </div>
      )}

      {/* 已匹配记录 */}
      <div className="card">
        <div className="bg-gray-50 px-4 py-3 rounded-t-xl border-b space-y-2">
          <div className="flex items-center justify-between flex-wrap gap-2">
            <div className="flex items-center gap-3 flex-wrap">
              <div className="flex items-center gap-2">
                <CheckCircle size={18} className="text-green-600" />
                <span className="font-semibold text-sm">已匹配记录</span>
                <span className="text-xs text-gray-500 bg-gray-200 px-2 py-0.5 rounded-full">{resultsTotal} 条</span>
              </div>
              <div className="flex items-center gap-3 text-xs text-gray-500">
                <span>匹配申报总额 <span className="font-semibold text-blue-600">฿{resultsDeclTotal.toLocaleString()}</span></span>
                <span>匹配流水总额 <span className="font-semibold text-green-600">฿{resultsFlowTotal.toLocaleString()}</span></span>
              </div>
            </div>
            <button onClick={handleExport} className="btn-secondary h-8 text-xs flex items-center gap-1"><Download size={14} />导出</button>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <input type="text" className="form-input w-[130px] text-xs" placeholder="搜索客户名" value={resultsSearch} onChange={e => { setResultsSearch(e.target.value); setResultsPage(1); }} />
            <input type="text" className="form-input w-[120px] text-xs" placeholder="搜索客户编号" value={resultsSearchCode} onChange={e => { setResultsSearchCode(e.target.value); setResultsPage(1); }} />
            <input type="date" className="form-input w-[130px] text-xs" value={resultsStartDate} onChange={e => { setResultsStartDate(e.target.value); setResultsPage(1); }} />
            <span className="text-xs text-gray-400">至</span>
            <input type="date" className="form-input w-[130px] text-xs" value={resultsEndDate} onChange={e => { setResultsEndDate(e.target.value); setResultsPage(1); }} />
          </div>
        </div>
        {loadingResults ? <div className="text-center py-8 text-gray-400">加载中...</div> : (
          <DataTable columns={resultColumns} data={results} total={resultsTotal} page={resultsPage} pageSize={50} onPageChange={setResultsPage} />
        )}
      </div>
    </>
  );
}

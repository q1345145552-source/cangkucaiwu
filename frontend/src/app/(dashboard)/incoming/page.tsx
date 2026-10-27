"use client";
import { useBusinessAction } from "@/hooks/useMenuPermission";
import ExcelImportDialog from "@/components/ExcelImportDialog";
import { downloadExcel, checkExcel, importScope } from "@/lib/excelImport";
import WalletAccountSelect from "@/components/WalletAccountSelect";
import { useEffect, useRef, useState } from "react";
import { useToast } from "@/components/ui/Toast";
import { api, getToken, getActiveWarehouseId } from "@/lib/api";
import { submitIncoming, IncomingOperation, SavedIncoming } from "@/lib/incomingSubmission";
import { useRouter } from "next/navigation";
import { Download, Upload, Plus } from "lucide-react";
import DataTable from "@/components/common/DataTable";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "/api/v1";
function todayThai() { return new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Bangkok" }); }
async function incomingRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = { Authorization: `Bearer ${getToken()}`, ...(options.headers as Record<string, string>) };
  const warehouse = getActiveWarehouseId();
  if (warehouse !== null) headers["X-Warehouse-ID"] = warehouse;
  const response = await fetch(`${API_URL}${path}`, { ...options, headers });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    const error = new Error(typeof data.detail === "string" ? data.detail : "录入内容不符合要求，请检查日期、金额和备注长度") as Error & { status: number };
    error.status = response.status;
    throw error;
  }
  return response.json();
}

export default function IncomingPage() {
  const canWrite = useBusinessAction("incoming", "bookkeeping");
  const { toast } = useToast(); const router = useRouter();
  const [accountGuide,setAccountGuide] = useState<{scope:string;rows:any[]}|null>(null);
  const [excelFile,setExcelFile] = useState<File|null>(null);
  const [data, setData] = useState<any[]>([]); const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [customers, setCustomers] = useState<any[]>([]);
  const [accountId, setAccountId] = useState(0);
  const [saving, setSaving] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [operation, setOperation] = useState<IncomingOperation | null>(null);
  const [storageReady, setStorageReady] = useState(false);
  const operationRef = useRef<IncomingOperation | null>(null);
  const storageKey = useRef("");
  const busy = useRef(false);
  const [preview, setPreview] = useState("");
  const screenshotFile = useRef<HTMLInputElement>(null);
  const initialScreenshotFile = useRef<HTMLInputElement>(null);
  const [screenshotTarget, setScreenshotTarget] = useState<number | null>(null);

  const today = todayThai();
  const [form, setForm] = useState({
    received_date: today, amount: "", currency: "THB",
    payer_name: "", customer_id: 0, payment_method: "银行转账", remark: ""
  });

  useEffect(() => { if (!getToken()) router.push("/login"); load(); loadCustomers(); }, [page]);
  useEffect(() => {
    let active = true;
    try {
      const user = JSON.parse(localStorage.getItem("user") || "{}");
      if (!user.id) throw new Error("登录账号未就绪");
      storageKey.current = `incoming-operation:${user.id}:${getActiveWarehouseId() || user.warehouse_id}`;
      const raw = localStorage.getItem(storageKey.current);
      if (raw) {
        const restored = JSON.parse(raw) as IncomingOperation;
        if (!restored.requestKey || !restored.payload) throw new Error("无效录入草稿");
        operationRef.current = restored; setOperation(restored);
        const { account_id, amount, ...fields } = restored.payload;
        setAccountId(account_id); setForm({ ...fields, customer_id: fields.customer_id || 0, amount: String(amount) });
        lookup(restored.requestKey).then(saved => {
          if (!active || !saved || operationRef.current?.requestKey !== restored.requestKey) return;
          remember({ ...restored, savedId: saved.id, screenshotPending: restored.screenshotPending && !saved.has_screenshot });
        }).catch(() => { /* 仍保留同一请求；用户可恢复网络后继续。 */ });
      }
      setStorageReady(true);
    } catch { toast("error", "上次录入状态读取失败，请先在到账列表核对，勿重复录入"); }
    return () => { active = false; };
  }, []);
  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview); }, [preview]);

  function remember(current: IncomingOperation) {
    localStorage.setItem(storageKey.current, JSON.stringify(current));
    operationRef.current = current; setOperation(current);
  }
  async function lookup(key: string) {
    try { return await incomingRequest<SavedIncoming>(`/incoming/by-request/${encodeURIComponent(key)}`); }
    catch (error) { if ((error as { status?: number }).status === 404) return null; throw error; }
  }
  async function uploadScreenshot(id: number, file: File) {
    const body = new FormData(); body.append("file", file);
    return incomingRequest(`/incoming/${id}/screenshot`, { method: "POST", body });
  }
  function startNext() {
    localStorage.removeItem(storageKey.current);
    operationRef.current = null; setOperation(null); setSelectedFile(null);
    setForm({ received_date: todayThai(), amount: "", currency: "THB", payer_name: "", customer_id: 0, payment_method: "银行转账", remark: "" });
    if (screenshotFile.current) screenshotFile.current.value = "";
    if (initialScreenshotFile.current) initialScreenshotFile.current.value = "";
  }
  async function viewScreenshot(id: number) {
    try {
      const headers: Record<string, string> = { Authorization: `Bearer ${getToken()}` };
      const warehouse = getActiveWarehouseId(); if (warehouse !== null) headers["X-Warehouse-ID"] = warehouse;
      const response = await fetch(`${API_URL}/incoming/${id}/screenshot`, { headers });
      if (!response.ok) throw new Error("截图读取失败或无权查看");
      setPreview(URL.createObjectURL(await response.blob()));
    } catch (error: any) { toast("error", error.message); }
  }
  async function uploadForRow(file: File) {
    if (!screenshotTarget || busy.current) return;
    busy.current = true; setSaving(true);
    try { await uploadScreenshot(screenshotTarget, file); toast("success", "截图已补传，到账金额未改变"); load(); }
    catch (error: any) { toast("error", `到账记录保留，截图未保存，请仅补传截图：${error.message}`); }
    finally { busy.current = false; setSaving(false); }
  }

  async function load() {
    setLoading(true);
    try {
      const res = await api.get<any>(`/incoming?page=${page}&page_size=20`);
      setData(res.data); setTotal(res.total);
    } catch {}
    setLoading(false);
  }

  async function loadCustomers() {
    try { const r = await api.get<any>("/customers?page_size=200"); setCustomers(r.data); } catch {}
  }

  async function handleCreate() {
    if (busy.current || !storageReady) return;
    if (!operationRef.current) {
      if (!form.customer_id) { toast("error", "请选择付款客户，不能仅凭名字关联到账"); return; }
      if (!form.amount || Number(form.amount) <= 0) { toast("error", "请填写大于零的金额"); return; }
      if (!accountId) { toast("error", "请选择收款账户"); return; }
    }
    busy.current = true;
    setSaving(true);
    try {
      const current = operationRef.current || { requestKey: crypto.randomUUID(), savedId: null,
        payload: { ...form, amount: Number(form.amount), account_id: accountId }, screenshotPending: !!selectedFile };
      const result = await submitIncoming(current, selectedFile, {
        create: payload => incomingRequest<SavedIncoming>("/incoming", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }),
        lookup, upload: uploadScreenshot, remember,
      });
      if (result.status === "saved") {
        toast("success", current.savedId && selectedFile ? "截图已补传，到账金额未改变" : selectedFile ? "到账已入账，截图已保存" : "到账已入账，录入成功"); startNext();
      } else if (result.status === "rejected") {
        localStorage.removeItem(storageKey.current); operationRef.current = null; setOperation(null);
        toast("error", (result.error as Error)?.message || "录入未保存，请修正后重试");
      } else if (result.status === "unconfirmed") {
        toast("error", "本次到账结果待确认，请恢复网络后重试本次录入；系统会查询原记录并防止重复入账");
      } else {
        toast("error", `到账 #${result.id} 已入账；截图未保存，请仅补传截图，不要重新录入到账`);
      }
      load();
    } catch (err: any) { toast("error", err.message || "本次操作未完成，请先核对到账状态"); }
    finally { busy.current = false; setSaving(false); }
  }

  const columns = [
    { key: "received_date", label: "到账日期", render: (v: string) => v?.slice(0, 10) },
    { key: "amount", label: "金额", align: "right" as const, render: (v: number) => v?.toLocaleString() },
    { key: "currency", label: "币种" },
    { key: "payer_name", label: "付款方" },
    { key: "payment_method", label: "付款方式", render: (v: string) => v || "-" },
    { key: "match_status", label: "匹配状态", render: (v: string) => {
      const map: any = { matched: "已匹配", unmatched: "未匹配" };
      const color: any = { matched: "bg-green-100 text-green-700", unmatched: "bg-orange-100 text-orange-600" };
      return <span className={`px-2 py-0.5 rounded text-xs font-medium ${color[v]||""}`}>{map[v]||v}</span>;
    }},
    { key: "entrant_name", label: "录入人" },
    { key: "has_screenshot", label: "截图", render: (value: boolean, row: any) => <div className="flex gap-2 whitespace-nowrap">
      {value && <button className="text-blue-600 text-xs" onClick={() => viewScreenshot(row.id)}>查看截图</button>}
      <button className="text-blue-600 text-xs" disabled={!(canWrite) || (saving)} onClick={() => { setScreenshotTarget(row.id); screenshotFile.current?.click(); }}>{value ? "更换截图" : "补传截图"}</button>
    </div> },
  ];

  return (
    <>
      <h1 className="page-title mb-4">到账流水</h1>
      {operation && <div role="status" className="bg-amber-50 border border-amber-200 rounded-lg p-3 mb-4 text-sm">
        <p>{operation.savedId ? `到账 #${operation.savedId} 已入账${operation.screenshotPending ? "，截图待补传" : "，请核对列表"}。补传截图不会增加到账。` : "上次录入结果待确认。请重试本次录入，系统会防止同一请求重复入账。"}</p>
        {operation.savedId && <button className="btn-secondary mt-2" disabled={saving} onClick={startNext}>录入另一笔</button>}
      </div>}

      {/* 顶部行内录入区 */}
      <div className="card mb-5 p-5">
        <div className="flex items-center gap-2 mb-4 text-sm font-semibold text-gray-600">
          <Plus size={18} className="text-green-600" /> 录入到账流水
        </div>
        <fieldset className="min-w-0" disabled={!canWrite || !storageReady || saving || !!operation}><div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 items-end">
          <div>
            <label className="form-label">到账日期</label>
            <input type="date" className="form-input" value={form.received_date} onChange={e => setForm({ ...form, received_date: e.target.value })} />
          </div>
          <div>
            <label className="form-label">金额</label>
            <input type="number" step="0.01" className="form-input" value={form.amount} onChange={e => setForm({ ...form, amount: e.target.value })} />
          </div>
          <div>
            <label className="form-label">币种</label>
            <select className="form-input" value={form.currency} onChange={e => setForm({ ...form, currency: e.target.value })}>
              <option value="THB">泰铢 (THB)</option>
              <option value="CNY">人民币 (CNY)</option>
            </select>
          </div>
          <WalletAccountSelect value={accountId} onChange={setAccountId} currency={form.currency} label="收款账户" />
          <div>
            <label className="form-label">付款方</label>
            <select className="form-input" aria-label="到账付款客户" value={form.customer_id || ""} onChange={e => {
              const customer = customers.find(c => c.id === +e.target.value);
              setForm({ ...form, customer_id: customer?.id || 0, payer_name: customer?.company_name || "" });
            }}>
              <option value="">选择客户</option>
              {customers.map((c: any) => <option key={c.id} value={c.id}>{c.customer_code || `#${c.id}`} · {c.company_name}</option>)}
            </select>
          </div>
          <div>
            <label className="form-label">付款方式</label>
            <select className="form-input" value={form.payment_method} onChange={e => setForm({ ...form, payment_method: e.target.value })}>
              <option value="现金">现金</option>
              <option value="银行转账">银行转账</option>
              <option value="支付宝">支付宝</option>
              <option value="微信">微信</option>
              <option value="PromptPay">PromptPay</option>
            </select>
          </div>
          <div>
            <label className="form-label">备注</label>
            <input className="form-input" maxLength={500} value={form.remark} onChange={e => setForm({ ...form, remark: e.target.value })} placeholder="可选" />
          </div>
        </div></fieldset>

        <div className="flex flex-col sm:flex-row sm:items-center gap-3 mt-4 pt-3 border-t min-w-0">
          <div className="flex flex-col sm:flex-row sm:items-center gap-2 min-w-0 flex-1">
            <label className="form-label mb-0 whitespace-nowrap">截图 <span className="text-gray-400 font-normal text-xs">非必填</span></label>
            <input ref={initialScreenshotFile} disabled={!canWrite} type="file" accept="image/png,image/jpeg,image/jpg,image/webp" onChange={(e) => setSelectedFile(e.target.files?.[0] || null)}
              className="w-full min-w-0 max-w-full text-xs text-gray-500 file:mr-2 file:py-1 file:px-2 file:rounded file:border-0 file:text-xs file:bg-green-50 file:text-green-700" />
          </div>
          <button onClick={handleCreate} disabled={!(canWrite) || (saving || !storageReady)} className="btn-primary h-10 flex items-center gap-1.5 w-full sm:w-auto sm:min-w-[100px] justify-center whitespace-nowrap">
            {saving ? "处理中..." : <><Upload size={16} />{operation?.savedId ? operation.screenshotPending ? "补传截图" : "完成本次" : operation ? "重试本次录入" : "录入"}</>}
          </button>
        </div>
      </div>

      {/* 操作按钮行 */}
      <div className="flex flex-wrap items-center gap-3 mb-4">
        <button onClick={async()=>{try{await downloadExcel('/incoming/template','incoming_template.xlsx');}catch(e:any){toast('error',e.message);}}} className="btn-secondary flex items-center gap-1 h-9"><Download size={14}/>下载模板</button>
        <button className="btn-secondary" onClick={async()=>{const scope=importScope();try{const result=await api.get<any>('/accounts');if(scope===importScope())setAccountGuide({scope,rows:result.data||[]});}catch(e:any){toast('error',e.message);}}}>查看收款账户编号</button>
        <label className="btn-secondary cursor-pointer">批量导入Excel<input disabled={!canWrite} type="file" accept=".xlsx" aria-label="到账Excel文件" className="hidden" onChange={e=>{const file=e.target.files?.[0];e.target.value='';if(file)try{checkExcel(file);setExcelFile(file);}catch(err:any){toast('error',err.message);}}}/></label>
      </div>

      {accountGuide&&accountGuide.scope===importScope()&&<div className="card p-3 mb-4 text-sm space-y-1"><p>请将明确选择的编号填入Excel“收款账户编号”列。此处只读展示，不自动选择账户。</p>{accountGuide.rows.map(a=><p key={a.id}>编号 {a.id} · {a.account_name} · {a.currency||'THB'} · {a.status==='inactive'?'已停用，不可导入':'账户可用条件以导入校验为准'}</p>)}{!accountGuide.rows.length&&<p>未找到可查看的账户，请核对当前仓库和权限。</p>}<button className="btn-secondary" onClick={()=>setAccountGuide(null)}>收起账户编号</button></div>}
      {canWrite&&excelFile&&<ExcelImportDialog file={excelFile} endpoint="/incoming/import-excel" title="到账流水Excel预览与确认" onClose={()=>setExcelFile(null)} onImported={r=>{toast('success',r.message);load();}}/>}
      {loading ? <div className="text-center py-8 text-gray-400">加载中...</div> : (
        <DataTable columns={columns} data={data} total={total} page={page} pageSize={20} onPageChange={setPage} />
      )}
      <input ref={screenshotFile} aria-label="补传到账截图" disabled={!canWrite} type="file" accept="image/png,image/jpeg,image/webp" className="hidden" onChange={event => { const file = event.target.files?.[0]; if (file) uploadForRow(file); event.target.value = ""; }} />
      {preview && <div className="modal-overlay" onClick={() => setPreview("")}><div className="bg-white p-4 rounded-xl max-w-[95vw] max-h-[90dvh] overflow-auto" onClick={e => e.stopPropagation()}>
        <button className="btn-secondary mb-2" onClick={() => setPreview("")}>关闭截图</button><img src={preview} alt="到账截图" className="max-w-full max-h-[75dvh] object-contain" />
      </div></div>}
    </>
  );
}

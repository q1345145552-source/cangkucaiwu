"use client";
import ActionGate from "@/components/permissions/ActionGate";
import { useTierPermission } from "@/hooks/useActionPermission";
import FinancialIdentityBoundary from "@/components/FinancialIdentityBoundary";
import WalletAccountSelect from "@/components/WalletAccountSelect";
import { useEffect, useState, useRef } from "react";
import DataTable from "@/components/common/DataTable";
import { api, getToken, warehouseRequestHeaders, ApiError } from "@/lib/api";
import { fmtMoney, fmtMoneyByCurrency } from "@/lib/currency";
import { useI18n } from "@/hooks/useI18n";
import { useToast } from "@/components/ui/Toast";
import { useAuth } from "@/hooks/useAuth";
import { useRouter } from "next/navigation";
import { Upload, AlertTriangle, DollarSign, Clock, CheckCircle, AlertCircle, FileText, Receipt, Download, Edit, TrendingUp, Package, Trash2 } from "lucide-react";

import PayableDetail from "@/components/PayableDetail";
import { pendingPayablePayment, submitPayablePayment, uploadPayableVoucher, payableScope, PayableVoucherTask } from "@/lib/payablePayment";
import { useMenuPermission } from "@/hooks/useMenuPermission";
import { registrationDraft, submitRegistration } from "@/lib/registrationRequest";
import PayableDuplicateDialog, { DuplicateConfirmation } from "@/components/PayableDuplicateDialog";
import { useCostIdentity,CostConfirmation } from "@/components/CostIdentity";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "/api/v1";
const emptyInvoice={issuer_identifier:"",series:"",number:"",verified:false};

function summaryAmount(value:number|null, known:number, currency:string) {
  return value == null ? `待核实（已知单据小计 ${fmtMoney(known,currency)}）` : fmtMoney(value,currency);
}
function summaryCurrencies(values?:Record<string,number|null>, known:Record<string,number>={}) {
  if(!values)return "加载中";
  return Object.entries(values).map(([currency,value])=>summaryAmount(value,known[currency] || 0,currency)).join("；") || "暂无有效应付";
}

function PayablePageContent() {
  const cost=useCostIdentity();
  const { t } = useI18n();
  const { toast } = useToast(); const { user } = useAuth(); const router = useRouter();
  const [data, setData] = useState<any[]>([]); const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1); const [showForm, setShowForm] = useState(false);
  const [suppliers, setSuppliers] = useState<any[]>([]);
  const [stats, setStats] = useState<any>(null);
  const [form, setForm] = useState({ supplier_id: 0, bill_number: "", bill_date: "", due_date: "", amount: "" as string | number, confirmed_amount: "" as string | number, payment_commitment_days: "" as string | number, currency: "THB", detail: "", remark: "", is_fund_linked: "", purchase_order_number: "" });
  const [billFile, setBillFile] = useState<File | null>(null);
  const [invoice,setInvoice]=useState(emptyInvoice),[creating,setCreating]=useState(false);
  const [duplicateChallenge,setDuplicateChallenge]=useState<{detail:any;retry:(confirmation:DuplicateConfirmation)=>Promise<void>}|null>(null);
  const [payAmounts, setPayAmounts] = useState<Record<number, number | "">>({});
  const [voucherFile, setVoucherFile] = useState<File | null>(null);
  const [payingBillId, setPayingBillId] = useState(0);
  const [payingRow, setPayingRow] = useState<any>(null);
  const [paymentSaving, setPaymentSaving] = useState(false);
  const [payAccountId, setPayAccountId] = useState(0);
  const payablePermission=useTierPermission("payable", "operate");
  const canWriteBill=payablePermission && ["warehouse_admin","supervisor"].includes((user as {role?:string} | null)?.role || "");
  const [pendingRecovery,setPendingRecovery]=useState(false);
  const [billDetailId,setBillDetailId]=useState(0),[detailRevision,setDetailRevision]=useState(0);
  const [voucherRetries,setVoucherRetries]=useState<PayableVoucherTask[]>([]);
  const [listError,setListError]=useState(""),[statsError,setStatsError]=useState("");
  const listRequest=useRef(0),statsRequest=useRef(0);
  useEffect(()=>{const id=Number(new URLSearchParams(window.location.search).get("bill_id"));if(Number.isInteger(id)&&id>0)setBillDetailId(id);return()=>{listRequest.current++;statsRequest.current++;};},[]);
  const [payMethod, setPayMethod] = useState("银行转账");
  const [showPayModal, setShowPayModal] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [editingBill, setEditingBill] = useState<any>(null);
  const [editForm, setEditForm] = useState({ supplier_id: 0, bill_number: "", currency: "THB", purchase_order_number: "", bill_date: "", due_date: "", amount: "" as string | number, confirmed_amount: "" as string | number, payment_commitment_days: "" as string | number, detail: "", remark: "", diff_note: "" });
  const [showVoidModal, setShowVoidModal] = useState(false);
  const [voidTarget, setVoidTarget] = useState<any>(null);
  const [voidReason, setVoidReason] = useState("");
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewLabel, setPreviewLabel] = useState("");
  const _now = new Date();
  const _curMonth = `${_now.getFullYear()}-${String(_now.getMonth() + 1).padStart(2, "0")}`;
  const _todayStr = `${_now.getFullYear()}-${String(_now.getMonth() + 1).padStart(2, "0")}-${String(_now.getDate()).padStart(2, "0")}`;
  const [listFilters, setListFilters] = useState({ supplier_id: 0, start_date: `${_curMonth}-01`, end_date: _todayStr, status: "", source: "", purchase_order_number: "", currency: "", effective_only: false });

  useEffect(() => { if (!getToken()) router.push("/login"); load(); loadSuppliers(); loadStats(); }, [page, listFilters]);

  async function paymentStage(id: number, action: "verify-payment" | "approve-payment") {
    try { await api.post(`/payable/${id}/${action}`, {}); toast("success", action === "verify-payment" ? "已核验，等待资金批准" : "已批准，等待独立财务付款"); void load(); }
    catch (error: unknown) { toast("error", error instanceof Error ? error.message : "操作失败"); }
  }
  async function load() {
    const request=++listRequest.current;setLoading(true);setData([]);setListError("");
    try {
      const params = new URLSearchParams(); params.set("page", String(page)); params.set("page_size", "25");
      if (listFilters.supplier_id) params.set("supplier_id", String(listFilters.supplier_id));
      if (listFilters.start_date) params.set("start_date", listFilters.start_date);
      if (listFilters.end_date) params.set("end_date", listFilters.end_date);
      if (listFilters.status) params.set("status", listFilters.status);
      if (listFilters.source) params.set("source", listFilters.source);
      if (listFilters.purchase_order_number) params.set("purchase_order_number", listFilters.purchase_order_number);
      if(listFilters.currency)params.set("currency",listFilters.currency);
      if(listFilters.effective_only)params.set("effective_only","true");
      const r = await api.get<any>(`/payable?${params.toString()}`); if(request===listRequest.current){setData(r.data);setTotal(r.total);}
    }
    catch (err:any) { if(request===listRequest.current)setListError(err.message || "列表加载失败"); }
    if(request===listRequest.current)setLoading(false);
  }
  async function loadSuppliers() { try { const r = await api.get<any>("/suppliers?page_size=100"); setSuppliers(r.data); } catch {} }
  async function loadStats() {
    const request=++statsRequest.current;setStats(null);setStatsError("");
    const params=new URLSearchParams();
    for(const key of ["start_date","end_date","supplier_id","currency","status","source","purchase_order_number"] as const){if(listFilters[key])params.set(key,String(listFilters[key]));}
    if(!listFilters.start_date && !listFilters.end_date)params.set("all_dates","true");
    try{const result=await api.get<any>(`/payable/stats?${params}`);if(request===statsRequest.current)setStats(result);}
    catch(e:any){if(request===statsRequest.current)setStatsError(e.message || "应付总表加载失败");}
  }

  // === 月度订单量 ===
  const today = new Date(); const yyyy = today.getFullYear(); const mm = String(today.getMonth()+1).padStart(2,"0");
  const [orderCount, setOrderCount] = useState("");
  const [orderMonth, setOrderMonth] = useState(`${yyyy}-${mm}`);
  const [orderSaved, setOrderSaved] = useState("");
  async function loadOrderVolume() {
    try {
      const r = await api.get<any>(`/payable/monthly-order?start_month=${yyyy}-01&end_month=${yyyy}-12`);
      const found = r.data.find((x: any) => x.month === `${yyyy}-${mm}`);
      if (found) { setOrderCount(String(found.order_count)); setOrderSaved(String(found.order_count)); }
    } catch {}
  }
  async function saveOrderVolume() {
    try {
      await api.post("/payable/monthly-order", { month: orderMonth, order_count: +orderCount });
      toast("success", "订单量已保存"); setOrderSaved(orderCount);
    } catch { toast("error", "保存失败"); }
  }
  useEffect(() => { loadOrderVolume(); }, []);

  // === 趋势图 ===
  const [showTrend, setShowTrend] = useState(false);
  const [trendData, setTrendData] = useState<any[]>([]);
  const [trendWarnings, setTrendWarnings] = useState<string[]>([]);
  async function loadTrend() {
    try {
      const r = await api.get<any>("/payable/trend?months=6");
      setTrendData(r.data || []);
      setTrendWarnings(r.warnings || []);
      setShowTrend(true);
    } catch { toast("error", "加载趋势失败"); }
  }

  const [matchingKind,setMatchingKind]=useState("unknown");
  function openBillForm(){
    try{const draft=registrationDraft("manual_bill");if(draft){setForm(draft.payload.form);setInvoice(draft.payload.invoice);setMatchingKind(draft.payload.matchingKind || "unknown");toast("success","已恢复未完成登记，请重新选择原凭证后重试");}setBillFile(null);setShowForm(true);}
    catch(e:any){toast("error",e.message);}
  }
  function duplicateError(e:any,retry:(confirmation:DuplicateConfirmation)=>Promise<void>){
    if(e.detail?.candidates && ["payable_duplicate_confirmation","payable_invoice_duplicate"].includes(e.detail.code)){setDuplicateChallenge({detail:e.detail,retry});return true;}
    return false;
  }
  async function handleCreate(confirmation?:DuplicateConfirmation,costConfirmation?:CostConfirmation) {
    if (!billFile) { toast("error", "请上传凭证图片"); return; }
    if(!form.bill_date || !form.due_date || !form.bill_number.trim() || !Number.isFinite(Number(form.amount)) || Number(form.amount)<=0){toast("error","请填写有效账单编号、日期和大于零的金额");return;}
    if((invoice.issuer_identifier || invoice.series || invoice.number) && !invoice.verified){toast("error","请先核对完整发票身份；无法确认请清空身份字段");return;}
    if(creating)return;setCreating(true);
    try {
      const fd = new FormData();
      fd.append("supplier_id", String(form.supplier_id));
      fd.append("bill_number", form.bill_number);
      fd.append("bill_date", form.bill_date);
      fd.append("due_date", form.due_date);
      fd.append("amount", String(form.amount || 0));
      if (form.confirmed_amount) fd.append("confirmed_amount", String(form.confirmed_amount));
      fd.append("currency", form.currency || "THB");
      if (form.remark) fd.append("remark", form.remark);
      if (form.payment_commitment_days) fd.append("payment_commitment_days", String(form.payment_commitment_days));
      if (form.detail) fd.append("detail", form.detail);
      if (form.is_fund_linked) fd.append("is_fund_linked", form.is_fund_linked);
      if (form.purchase_order_number) fd.append("purchase_order_number", form.purchase_order_number);
      fd.append("file", billFile);fd.append("matching_kind",matchingKind);
      if(invoice.verified)fd.append("invoice_identity",JSON.stringify(invoice));
      if(confirmation)fd.append("duplicate_confirmation",JSON.stringify(confirmation));
      if(costConfirmation)fd.append('cost_confirmation',JSON.stringify(costConfirmation));
      const r=await submitRegistration<any>("manual_bill",0,{form,invoice,...(matchingKind==="unknown"?{}:{matchingKind})},async key=>{
        fd.set("request_key",key);
        const res=await fetch(`${API_URL}/payable`,{method:"POST",headers:warehouseRequestHeaders(),body:fd});
        const result=await res.json();
        if(!res.ok)throw new ApiError(res.status,result.detail || "创建失败");
        return result;
      });
      toast("success", r.has_diff ? "账单创建成功，已标记对账差异" : "创建成功");
      setShowForm(false); setBillFile(null); setForm({ supplier_id: 0, bill_number: "", bill_date: "", due_date: "", amount: "", confirmed_amount: "", payment_commitment_days: "", currency: "THB", detail: "", remark: "", is_fund_linked: "", purchase_order_number: "" });
      setInvoice(emptyInvoice);setMatchingKind("unknown");setDuplicateChallenge(null);
      load(); loadStats();
    } catch (err: any) { if(!cost.capture(err,data=>handleCreate(confirmation,data))&&!duplicateError(err,data=>handleCreate(data,costConfirmation)))toast("error", err.message || "创建失败"); }
    finally{setCreating(false);}
  }

  function hasPendingPayment(id:number){try{return !!pendingPayablePayment(id);}catch{return true;}}
  function openPayModal(row: any) {
    try{
      const pending=pendingPayablePayment(row.id);
      if(!pending && row.paid_amount==null)throw Error("累计已付未记录，请先核对历史付款");
      setPendingRecovery(!!pending);
      setPayAmounts(prev=>({...prev,[row.id]:pending?.payload.paid_amount ?? Math.round((row.amount-(row.paid_amount || 0))*100)/100}));
      setPayingBillId(row.id);setPayingRow(row);setVoucherFile(null);
      setPayAccountId(pending?.payload.account_id || 0);setPayMethod(pending?.payload.payment_method || "银行转账");setShowPayModal(true);
    }catch(e:any){toast("error",e.message);}
  }
  async function retryVoucher(task:PayableVoucherTask){if(paymentSaving)return;setPaymentSaving(true);
    try{await uploadPayableVoucher(task.billId,task.file,task.scope);setVoucherRetries(tasks=>tasks.filter(t=>t!==task));setDetailRevision(n=>n+1);toast("success","凭证已补传，没有再次付款");}
    catch(e:any){toast("error",`付款已记录，凭证上传失败：${e.message}`);}finally{setPaymentSaving(false);}}
  async function handlePay() {
    if(!payAccountId){toast("error","请选择付款账户");return;}
    const payAmount=Number(payAmounts[payingBillId]);
    if(!Number.isFinite(payAmount)||payAmount<=0){toast("error","请填写大于零的付款金额");return;}
    if(paymentSaving)return;setPaymentSaving(true);
    try{
      // Capture this payment's file and identity; another modal must never replace a failed upload.
      const scope=payableScope(), billId=payingBillId, file=voucherFile;
      await submitPayablePayment(payingBillId,{paid_amount:payAmount,account_id:payAccountId,payment_method:payMethod});
      setShowPayModal(false);setPendingRecovery(false);
      let currentScope;try{currentScope=payableScope();}catch{}
      if(scope.userId!==currentScope?.userId || scope.warehouseId!==currentScope?.warehouseId){
        if(file)setVoucherRetries(tasks=>[...tasks,{billId,file,scope}]);
        toast("success",file ? "付款已记录，请切回原账号和原仓库仅重传凭证" : "付款已记录，请在原仓库查看");return;
      }
      setBillDetailId(payingBillId);setDetailRevision(n=>n+1);load();loadStats();
      if(file){
        try{await uploadPayableVoucher(billId,file,scope);setDetailRevision(n=>n+1);}
        catch(e:any){setVoucherRetries(tasks=>[...tasks,{billId,file,scope}]);toast("error",`付款已记录，凭证上传失败：${e.message}，请仅重传凭证`);return;}
      }
      toast("success","付款已记录");
    }catch(e:any){setPendingRecovery(hasPendingPayment(payingBillId));toast("error",e.message || "付款结果待确认，请重试同一请求");}
    finally{setPaymentSaving(false);}
  }

  function openEditModal(row: any) {
    setEditingBill(row);
    setEditForm({
      supplier_id: row.supplier_id || 0,
      bill_number: row.bill_number || "",
      currency: row.currency || "THB",
      purchase_order_number: row.purchase_order_number || "",
      bill_date: row.bill_date ? row.bill_date.slice(0, 10) : "",
      due_date: row.due_date ? row.due_date.slice(0, 10) : "",
      amount: row.amount != null ? String(row.amount) : "",
      confirmed_amount: row.confirmed_amount != null ? String(row.confirmed_amount) : "",
      payment_commitment_days: row.payment_commitment_days != null ? String(row.payment_commitment_days) : "",
      detail: row.detail || "",
      remark: row.remark || "",
      diff_note: row.diff_note || "",
    });
    setShowEditModal(true);
  }

  const [reviewTarget,setReviewTarget]=useState(0),[reviewReason,setReviewReason]=useState(""),[reviewSaving,setReviewSaving]=useState(false);
  async function confirmBoss(billId:number){setReviewTarget(billId);setReviewReason("");}
  async function saveMatchReview(){
    if(!reviewReason.trim()){toast("error","请填写本次匹配复核原因");return;}
    if(!reviewTarget || reviewSaving)return;setReviewSaving(true);
    try{
      await api.put(`/payable/${reviewTarget}/confirm`,{reason:reviewReason});
      toast("success","本次匹配复核已保存，后续变化须重新复核");setReviewTarget(0);setReviewReason("");
      setDetailRevision(n=>n+1);load();loadStats();
    }catch(e:any){toast("error",e.message || "复核失败");}finally{setReviewSaving(false);}
  }

  async function handleEdit(confirmation?:DuplicateConfirmation,costConfirmation?:CostConfirmation) {
    try {
      const isPaid = (editingBill.status === "paid" || editingBill.paid_amount > 0);
      const payload: any = {};
      if (isPaid) {
        // 已付款：只发备注和差异说明，避免后端按“有其他字段”拒绝
        payload.remark = editForm.remark;
        payload.diff_note = editForm.diff_note;
      } else {
        payload.supplier_id = editForm.supplier_id || undefined;
        payload.bill_number = editForm.bill_number;
        payload.currency = editForm.currency;
        payload.purchase_order_number = editForm.purchase_order_number;
        payload.bill_date = editForm.bill_date;
        payload.due_date = editForm.due_date;
        payload.amount = editForm.amount === "" ? undefined : +editForm.amount;
        payload.confirmed_amount = editForm.confirmed_amount === "" ? undefined : +editForm.confirmed_amount;
        payload.payment_commitment_days = editForm.payment_commitment_days === "" ? undefined : +editForm.payment_commitment_days;
        payload.detail = editForm.detail;
        payload.remark = editForm.remark;
        payload.diff_note = editForm.diff_note;
      }
      if(confirmation)payload.duplicate_confirmation=confirmation;
      if(costConfirmation)payload.cost_confirmation=costConfirmation;
      await api.put<any>(`/payable/${editingBill.id}`, payload);
      toast("success", "账单更新成功");
      setShowEditModal(false);setDuplicateChallenge(null); load(); loadStats();
    } catch (err: any) { if(!cost.capture(err,data=>handleEdit(confirmation,data))&&!duplicateError(err,data=>handleEdit(data,costConfirmation)))toast("error", err.message || "更新失败"); }
  }

  function openVoidModal(row: any) {
    setVoidTarget(row);
    setVoidReason("");
    setShowVoidModal(true);
  }

  async function handleVoid() {
    if (!voidReason.trim()) {
      toast("error", "请填写作废原因");
      return;
    }
    try {
      await api.put<any>(`/payable/${voidTarget.id}/void?void_reason=${encodeURIComponent(voidReason.trim())}`);
      toast("success", "已作废");
      setShowVoidModal(false); load(); loadStats();
    } catch (err: any) { toast("error", err.message || "作废失败"); }
  }

  function toggleSelectAll() {
    if (selectedIds.size === data.length) { setSelectedIds(new Set()); }
    else { setSelectedIds(new Set(data.map(r => r.id))); }
  }
  function toggleSelect(id: number) {
    setSelectedIds(prev => { const next = new Set(prev); if (next.has(id)) next.delete(id); else next.add(id); return next; });
  }

  async function handleExport() {
    if (selectedIds.size === 0) { toast("error", "请先在列表中勾选要导出的账单"); return; }
    try {
      const billIds = Array.from(selectedIds).join(",");
      const res = await fetch(`${API_URL}/payable/batch-export?bill_ids=${billIds}`, {
        headers: warehouseRequestHeaders(),
      });
      const blob = await res.blob();
      const a = document.createElement("a"); a.href = window.URL.createObjectURL(blob);
      a.download = "payable_export.xlsx"; a.click();
      toast("success", `已导出 ${selectedIds.size} 条账单`);
    } catch { toast("error", "导出失败"); }
  }

  function handleQuery() { setPage(1); setSelectedIds(new Set()); load(); }

  function getFileUrl(path: string) {
    if (!path) return "";
    if (path.startsWith("http")) return path;
    return `${API_URL.replace("/api/v1", "")}${path}`;
  }

  function openPreview(url: string, label: string) {
    setPreviewUrl(url); setPreviewLabel(label);
  }

  const statusColors: Record<string, string> = {
    pending: "px-2 py-1 rounded text-xs font-medium bg-yellow-100 text-yellow-700",
    paid: "px-2 py-1 rounded text-xs font-medium bg-green-100 text-green-700",
    partially_paid: "px-2 py-1 rounded text-xs font-medium bg-blue-100 text-blue-700",
    overdue: "px-2 py-1 rounded text-xs font-medium bg-red-100 text-red-700",
    voided: "px-2 py-1 rounded text-xs font-medium bg-gray-200 text-gray-500",
  };
  const statusLabels: Record<string, string> = {
    pending: "待付", paid: "已付", partially_paid: "部分付款", overdue: "逾期", voided: "已作废",
  };

  return (
    <>
      <h1 className="page-title mb-5">{t("payable")}</h1>

      {listError && <p role="alert" className="text-red-600">{listError}</p>}
      {statsError && <p role="alert" className="text-red-600">{statsError}</p>}
      {voucherRetries.map((task,i)=><div role="alert" key={`${task.scope.userId}:${task.scope.warehouseId}:${task.billId}:${i}`} className="p-3 bg-amber-50 text-amber-800">账单 #{task.billId}（仓库 #{task.scope.warehouseId}）付款已记录，凭证上传失败。<button onClick={()=>retryVoucher(task)} disabled={paymentSaving}>仅重传付款凭证</button></div>)}
      {/* 总览看板 */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-5">
        <div className="card bg-gradient-to-br from-blue-500 to-blue-600 text-white border-0">
          <div className="flex items-center gap-2 mb-1"><DollarSign size={18} /><span className="text-sm opacity-80">所选账单日期应付</span></div>
          <div className="text-2xl font-bold">{summaryCurrencies(stats?.month_total_by_currency)}</div>
        </div>
        <div className="card bg-gradient-to-br from-red-500 to-red-600 text-white border-0">
          <div className="flex items-center gap-2 mb-1"><AlertCircle size={18} /><span className="text-sm opacity-80">逾期未付</span></div>
          <div className="text-2xl font-bold">{summaryCurrencies(stats?.overdue_by_currency,stats?.overdue_known_by_currency)}</div>
        </div>
        <div className="card bg-gradient-to-br from-green-500 to-green-600 text-white border-0">
          <div className="flex items-center gap-2 mb-1"><CheckCircle size={18} /><span className="text-sm opacity-80">所选账单日期累计已付</span></div>
          <div className="text-2xl font-bold">{summaryCurrencies(stats?.month_paid_by_currency,stats?.month_paid_known_by_currency)}</div>
        </div>
        <div className="card bg-gradient-to-br from-orange-500 to-orange-600 text-white border-0">
          <div className="flex items-center gap-2 mb-1"><Clock size={18} /><span className="text-sm opacity-80">所选账单日期剩余应付</span></div>
          <div className="text-2xl font-bold">{summaryCurrencies(stats?.month_unpaid_by_currency,stats?.month_unpaid_known_by_currency)}</div>
        </div>
      </div>

      {/* 本月订单量录入 */}
      <div className="card mb-5 p-4">
        <div className="flex items-end gap-3">
          <div className="flex items-center gap-2">
            <Package size={20} className="text-blue-600" />
            <span className="text-sm font-semibold text-gray-600">本月订单量</span>
          </div>
          <div className="w-[100px]"><label className="form-label">月份</label>
            <input type="month" className="form-input text-sm" value={orderMonth} onChange={e => setOrderMonth(e.target.value)} />
          </div>
          <div className="w-[120px]"><label className="form-label">订单数（笔）</label>
            <input type="number" className="form-input" value={orderCount} onChange={e => setOrderCount(e.target.value)} placeholder="输入数量" />
          </div>
          <ActionGate anyOf={["payable.save_monthly_order#operate"]}><button onClick={saveOrderVolume} className="btn-primary h-[42px]">保存</button></ActionGate>
          {orderSaved && orderCount === orderSaved && <span className="text-xs text-green-600 self-center pb-1">已保存</span>}
          <div className="flex-1" />
          <button onClick={loadTrend} className="btn-secondary h-[42px] flex items-center gap-1.5"><TrendingUp size={16} />查看趋势</button>
        </div>
      </div>

      <section className="card mb-5 p-4" aria-label="应付总表">
        <h2 className="font-semibold">应付总表（供应商 × 币种）</h2>
        <p className="text-xs text-gray-500 my-2">按账单日期：{listFilters.start_date || "不限起日"} 至 {listFilters.end_date || "不限止日"}；仅有效应付，累计已付含历史。逾期属于剩余，不重复加总；付款计划不另算应付。</p>
        {!stats ? <p>{statsError ? "总表未能加载" : "加载中"}</p> : <div className="overflow-x-auto"><table className="w-full min-w-[680px] text-sm"><thead><tr>{["供应商","币种","有效应付","累计已付","剩余应付","其中逾期未付","单据数","明细"].map(x=><th className="p-2 text-left" key={x}>{x}</th>)}</tr></thead><tbody>
          {stats.supplier_summary.map((row:any)=><tr className="border-t" key={`${row.supplier_id}:${row.currency}`}>
            <td className="p-2">{row.supplier_name}{row.link_warning_count>0 && <p className="text-amber-700 text-xs">{row.link_warning_count}笔历史关联异常，详情需核对；未移除应付金额</p>}</td><td>{row.currency}</td><td>{fmtMoney(row.total_amount,row.currency)}</td><td>{summaryAmount(row.paid_amount,row.known_paid_amount,row.currency)}</td><td>{summaryAmount(row.unpaid_amount,row.known_unpaid_amount,row.currency)}</td><td>{summaryAmount(row.overdue_amount,row.known_overdue_amount,row.currency)}</td><td>{row.bill_count}{row.unknown_payment_count>0 && <p className="text-amber-700 text-xs">其中{row.unknown_payment_count}笔累计付款待核实</p>}</td>
            <td><button className="text-blue-600 underline" onClick={()=>{setPage(1);setListFilters(prev=>({...prev,supplier_id:row.supplier_id,currency:row.currency,effective_only:true}));}}>查看对应明细</button></td>
          </tr>)}
        </tbody></table>{!stats.supplier_summary.length && <p>当前范围暂无有效应付</p>}</div>}
      </section>

      <p className="text-xs text-gray-500 mb-2">列表日期口径：账单日期。{listFilters.effective_only ? "当前为总表钻取的有效账单范围。" : "列表可包含已作废记录，总表仅统计有效账单。"}</p>
      {/* 列表筛选 + 操作栏 */}
      <div className="card mb-4 p-4">
        <div className="flex items-end gap-3 flex-wrap">
          <div className="flex-1 min-w-[120px]"><label className="form-label">供应商</label>
            <select className="form-input" value={listFilters.supplier_id} onChange={e => setListFilters({ ...listFilters, supplier_id: +e.target.value })}>
              <option value={0}>全部供应商</option>
              {suppliers.map((s: any) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </div>
          <div className="w-[130px]"><label className="form-label">开始日期</label>
            <input type="date" className="form-input" value={listFilters.start_date} onChange={e => setListFilters({ ...listFilters, start_date: e.target.value })} />
          </div>
          <div className="w-[130px]"><label className="form-label">结束日期</label>
            <input type="date" className="form-input" value={listFilters.end_date} onChange={e => setListFilters({ ...listFilters, end_date: e.target.value })} />
          </div>
          <div className="w-[130px]"><label className="form-label">状态</label>
            <select className="form-input" value={listFilters.status} onChange={e => setListFilters({ ...listFilters, status: e.target.value })}>
              <option value="">全部</option>
              <option value="pending">待付</option>
              <option value="paid">已付</option>
              <option value="partially_paid">部分付款</option>
              <option value="overdue">逾期</option>
            </select>
          </div>
          <div className="w-[130px]"><label className="form-label">来源</label>
            <select className="form-input" value={listFilters.source} onChange={e => setListFilters({ ...listFilters, source: e.target.value })}>
              <option value="">全部</option>
              <option value="purchase_order">采购单</option>
              <option value="manual">手动</option>
            </select>
          </div>
          <div className="w-[160px]"><label className="form-label">采购单号</label>
            <input className="form-input" value={listFilters.purchase_order_number} onChange={e => setListFilters({ ...listFilters, purchase_order_number: e.target.value })} placeholder="输入采购单号" />
          </div>
          <div className="w-[130px]"><label className="form-label">币种</label><select className="form-input" value={listFilters.currency} onChange={e=>{setPage(1);setListFilters({...listFilters,currency:e.target.value});}}><option value="">全部币种（分列）</option><option value="THB">THB</option><option value="CNY">CNY</option></select></div>
          <button className="btn-secondary" onClick={()=>{setPage(1);setListFilters({...listFilters,start_date:"",end_date:""});}}>全部账单日期</button>
          {listFilters.effective_only && <button onClick={()=>setListFilters({...listFilters,effective_only:false})}>取消有效账单限定</button>}
          <button onClick={handleQuery} className="btn-primary h-[42px]">查询</button>
          <div className="flex-1" />
          <button onClick={handleExport} className="btn-secondary flex items-center gap-1 h-[42px]" disabled={selectedIds.size === 0}>
            <Download size={16} />导出选中{selectedIds.size > 0 ? ` (${selectedIds.size})` : ""}
          </button>
          {selectedIds.size > 0 && (
            <button onClick={() => { setSelectedIds(new Set()); }} className="text-xs text-gray-400 hover:text-gray-600 self-center">
              清除选择
            </button>
          )}
          {canWriteBill && <ActionGate anyOf={["payable.create_bill"]}><button onClick={openBillForm} className="btn-primary h-[42px]">新建账单</button></ActionGate>}
        </div>
      </div>

      {loading ? <div className="text-center py-8 text-gray-400">加载中...</div> : <DataTable columns={[
        {
          key: "_select", label: "",
          headerRender: () => <input type="checkbox" checked={data.length > 0 && selectedIds.size === data.length} onChange={toggleSelectAll} className="w-4 h-4" />,
          render: (_: any, row: any) => <input type="checkbox" checked={selectedIds.has(row.id)} onChange={() => toggleSelect(row.id)} className="w-4 h-4" />
        },
        { key: "supplier_name", label: "供应商" },
        { key: "bill_number", label: "账单编号", render:(v:any,row:any)=><button className="text-blue-600 underline" onClick={()=>setBillDetailId(row.id)}>{v}</button> },
        { key: "source", label: "来源", render: (v: any, row: any) => v === "purchase_order" ? <span className="px-2 py-0.5 rounded text-xs bg-blue-50 text-blue-600">采购单</span> : <span className="px-2 py-0.5 rounded text-xs bg-gray-100 text-gray-600">手动</span> },
        { key: "need_boss_confirm", label: "标记", render: (v: any,row:any) => <>{v === "true" && <span className="px-2 py-0.5 rounded text-xs bg-red-100 text-red-600 font-medium">待老板确认</span>}{row.link_warning && <span className="text-xs text-amber-700" title={row.link_warning}>历史关联异常，需核对</span>}{v!=="true" && !row.link_warning && <span className="text-xs text-gray-300">-</span>}</> },
        { key: "bill_date", label: "账单日期", render: (v: any) => v?.slice(0, 10) },
        { key: "due_date", label: "到期日", render: (v: any) => v?.slice(0, 10) },
        {
          key: "amount", label: "金额", align: "right", render: (v: any, row: any) => {
            const diff = row.confirmed_amount && row.confirmed_amount !== row.amount;
            return <span>{fmtMoney(v, row.currency)} {diff && <span title={`供应商确认: ${row.confirmed_amount}`}><AlertTriangle size={12} className="inline text-orange-500 ml-1" /></span>}</span>
          }
        },
        { key: "paid_amount", label: "已付", align: "right", render: (v: any, row: any) => v==null ? "未记录，待核实" : fmtMoney(v, row.currency) },
        { key: "status", label: "状态", render: (v: string, row: { capabilities?: { workflow_stage?: string } }) => <span className={statusColors[v] || ""}>{row.capabilities?.workflow_stage || statusLabels[v] || v}</span> },
        { key: "detail", label: "明细", render: (v: any) => v ? <span className="text-xs text-gray-500 max-w-32 truncate block" title={v}>{v.length > 12 ? v.slice(0, 12) + "..." : v}</span> : "-" },
        { key: "bill_attachment", label: "附件", render: (v: any) => v ? <button onClick={() => openPreview(getFileUrl(v), "账单附件")} className="text-blue-600 text-xs hover:underline cursor-pointer">查看</button> : <span className="text-gray-300 text-xs">-</span> },
        { key: "payment_voucher", label: "凭证", render: (v: any) => v ? <button onClick={() => openPreview(getFileUrl(v), "付款凭证")} className="text-blue-600 text-xs hover:underline cursor-pointer">查看</button> : <span className="text-gray-300 text-xs">-</span> },
        { key: "id", label: "操作", render: (_: any, row: any) => <div className="flex items-center gap-1">{["staff","warehouse_admin"].includes(user?.role || "") && row.capabilities?.can_verify && <button onClick={()=>paymentStage(row.id,"verify-payment")} className="btn-secondary btn-xs">核验付款依据</button>}{user?.role === "warehouse_admin" && row.capabilities?.can_approve && <button onClick={()=>paymentStage(row.id,"approve-payment")} className="btn-secondary btn-xs">批准资金</button>}<button onClick={()=>setBillDetailId(row.id)} className="btn-secondary btn-xs">详情</button>{canWriteBill && hasPendingPayment(row.id) && <ActionGate anyOf={["payable.pay_bill"]}><button onClick={()=>openPayModal(row)} className="btn-secondary btn-xs">核对上次付款</button></ActionGate>}{row.need_boss_confirm === "true" && row.status !== "voided" && user?.role === "warehouse_admin" && <ActionGate anyOf={["payable.confirm_bill"]}><button onClick={() => confirmBoss(row.id)} className="btn-primary btn-xs bg-purple-600 hover:bg-purple-700">确认</button></ActionGate>}{["staff","warehouse_admin"].includes(user?.role || "") && row.capabilities?.can_pay && row.need_boss_confirm !== "true" && <ActionGate anyOf={["payable.pay_bill"]}><button onClick={() => openPayModal(row)} className="btn-primary btn-xs">付款</button></ActionGate>}{canWriteBill && row.status !== "voided" && <ActionGate anyOf={["payable.update_bill"]}><button onClick={() => openEditModal(row)} className="btn-secondary btn-xs flex items-center gap-0.5"><Edit size={12} />编辑</button></ActionGate>}{user?.role === "warehouse_admin" && row.status !== "paid" && row.status !== "voided" && <button onClick={() => openVoidModal(row)} className="btn-xs flex items-center gap-0.5 text-red-600 hover:bg-red-50 px-2 py-1 rounded"><Trash2 size={12} />作废</button>}</div> },
      ]} data={data} total={total} page={page} pageSize={25} onPageChange={setPage} rowClassName={(row) => row.status === "voided" ? "opacity-50" : ""} />}

      {billDetailId>0 && <PayableDetail billId={billDetailId} revision={detailRevision} onClose={()=>setBillDetailId(0)} onPay={bill=>{setBillDetailId(0);openPayModal(bill);}} onConfirm={confirmBoss}/>}
      {reviewTarget>0 && <div className="modal-overlay z-[85]"><div role="dialog" aria-label="匹配复核" className="bg-white rounded-xl w-full max-w-lg max-h-[90vh] flex flex-col">
        <div className="p-4 border-b"><h2 className="font-semibold">本次采购、收货与应付复核</h2></div>
        <div className="p-4 overflow-auto space-y-3"><p className="text-sm">记录当前匹配快照、复核人和时间。后续收货或账单变化须重新复核；已有付款保持原样。</p><label className="block text-sm">本次匹配复核原因<textarea className="form-input min-h-[120px]" maxLength={1000} value={reviewReason} onChange={e=>setReviewReason(e.target.value)}/></label></div>
        <div className="p-4 border-t flex justify-end gap-3"><button className="btn-secondary" disabled={reviewSaving} onClick={()=>setReviewTarget(0)}>取消复核</button><ActionGate anyOf={["payable.confirm_bill#approve"]}><button className="btn-primary" disabled={reviewSaving} onClick={saveMatchReview}>{reviewSaving ? "保存中" : "保存本次复核"}</button></ActionGate></div>
      </div></div>}
      {duplicateChallenge && <PayableDuplicateDialog challenge={duplicateChallenge.detail} onClose={()=>setDuplicateChallenge(null)} onConfirm={async data=>{const retry=duplicateChallenge.retry;setDuplicateChallenge(null);await retry(data);}}/>}
      {cost.dialog}
      {/* 新建账单弹窗 */}
      {showForm && (
        <div className="modal-overlay" onClick={() => setShowForm(false)}>
          <div className="bg-white rounded-xl w-full max-w-lg max-h-[90vh] overflow-auto shadow-2xl" onClick={e => e.stopPropagation()}>
            <div className="bg-blue-600 text-white px-6 py-4 rounded-t-xl flex items-center gap-3">
              <FileText size={22} />
              <div className="flex-1"><h2 className="text-lg font-semibold">新建应付账单</h2></div>
              <button onClick={() => setShowForm(false)} className="text-blue-200 hover:text-white"><span className="text-xl leading-none">&times;</span></button>
            </div>

            <div className="p-6 space-y-4">
              {/* 基本信息 */}
              <div className="text-sm font-semibold text-gray-400 pb-1 border-b">基本信息</div>
              <div className="form-group"><label className="form-label">供应商</label>
                <select className="form-input" value={form.supplier_id} onChange={e => setForm({ ...form, supplier_id: +e.target.value })}>
                  <option value={0}>选择供应商</option>
                  {suppliers.map((s: any) => <option key={s.id} value={s.id}>{s.name}</option>)}
                </select>
              </div>
              <div className="form-grid">
                <div className="form-group"><label className="form-label">账单编号（登记号）</label><input className="form-input" value={form.bill_number} onChange={e => setForm({ ...form, bill_number: e.target.value })} /></div>
                <div className="form-group"><label className="form-label">币种</label><select className="form-input" value={form.currency} onChange={e => setForm({ ...form, currency: e.target.value })}><option>THB</option><option>CNY</option><option>USD</option></select></div>
              </div>
              <div className="form-group"><label className="form-label">关联采购单号（可选）</label><input className="form-input" value={form.purchase_order_number} onChange={e => setForm({ ...form, purchase_order_number: e.target.value })} placeholder="如 PO2026..." /></div>
              <label className="form-label block">三单匹配业务类型<select className="form-input" value={matchingKind} onChange={e=>setMatchingKind(e.target.value)}><option value="unknown">待核实（不猜测历史类型）</option><option value="goods">商品采购</option><option value="prepayment">预付款</option><option value="non_goods">非商品费用</option></select></label>
              <fieldset className="border rounded p-3 space-y-2"><legend>真实发票身份（选填）</legend><p className="text-xs text-gray-500">登记号不默认当作发票号。仅按原始凭证核实后填写；无法确认请留空。只去首尾空白，保留大小写、内部字符和标点。</p>
                {([["issuer_identifier","供应商官方唯一识别号"],["series","发票类型／系列（完整）"],["number","完整发票号码"]] as const).map(([key,label])=><label className="block text-sm" key={key}>{label}<input className="form-input" maxLength={150} value={invoice[key]} onChange={e=>setInvoice({...invoice,[key]:e.target.value})}/></label>)}
                <label className="flex gap-2 text-sm"><input type="checkbox" checked={invoice.verified} onChange={e=>setInvoice({...invoice,verified:e.target.checked})}/>我已核对原凭证，确认真实供应商和完整发票身份一致</label>
              </fieldset>
              <div className="form-grid">
                <div className="form-group"><label className="form-label">账单日期</label><input type="date" className="form-input" value={form.bill_date} onChange={e => setForm({ ...form, bill_date: e.target.value })} /></div>
                <div className="form-group"><label className="form-label">到期日期</label><input type="date" className="form-input" value={form.due_date} onChange={e => setForm({ ...form, due_date: e.target.value })} /></div>
              </div>

              <div className="text-sm font-semibold text-gray-400 pb-1 border-b">金额信息</div>
              <div className="form-grid">
                <div className="form-group"><label className="form-label">金额</label><input type="number" className="form-input" value={form.amount || ""} onChange={e => setForm({ ...form, amount: e.target.value===""?"":+e.target.value })} /></div>
                <div className="form-group"><label className="form-label">供应商确认金额</label><input type="number" className="form-input" value={form.confirmed_amount || ""} onChange={e => setForm({ ...form, confirmed_amount: e.target.value===""?"":+e.target.value })} /></div>
              </div>
              <div className="form-group"><label className="form-label">付款承诺天数</label><input type="number" className="form-input" value={form.payment_commitment_days || ""} onChange={e => setForm({ ...form, payment_commitment_days: e.target.value===""?"":+e.target.value })} /></div>

              <div className="text-sm font-semibold text-gray-400 pb-1 border-b">补充信息</div>
              <div className="form-group"><label className="form-label">费用明细</label><textarea className="form-input" rows={3} value={form.detail} onChange={e => setForm({ ...form, detail: e.target.value })} placeholder="费用明细描述" /></div>
              <div className="form-group">
                <label className="form-label">凭证图片 <span className="text-red-400">*</span></label>
                <div className="border-2 border-dashed border-gray-200 rounded-lg p-4 text-center hover:border-blue-400 transition-colors">
                  <Upload size={24} className="mx-auto text-gray-300 mb-2" />
                  <input type="file" accept="image/*" onChange={e => setBillFile(e.target.files?.[0] || null)} className="text-sm text-gray-500" />
                  <div className="text-xs text-gray-400 mt-2">手动账单必须上传凭证图片</div>
                  {billFile && <div className="text-xs text-green-600 mt-1">{billFile.name}</div>}
                </div>
              </div>
            </div>

            <div className="border-t px-6 py-4 bg-gray-50 rounded-b-xl flex justify-end gap-3">
              <button onClick={() => setShowForm(false)} className="btn-secondary min-w-[80px]">取消</button>
              <ActionGate anyOf={["payable.create_bill"]}><button onClick={()=>handleCreate()} disabled={creating} className="btn-primary min-w-[80px]">{creating ? "保存中" : "保存"}</button></ActionGate>
            </div>
          </div></div>
      )}

      {/* 编辑弹窗 */}
      {showEditModal && editingBill && (
        <div className="modal-overlay" onClick={() => setShowEditModal(false)}>
          <div className="bg-white rounded-xl w-full max-w-lg max-h-[90vh] flex flex-col overflow-hidden shadow-2xl" onClick={e => e.stopPropagation()}>
            <div className="bg-orange-500 text-white px-6 py-4 rounded-t-xl flex items-center gap-3 shrink-0">
              <Edit size={22} />
              <div className="flex-1">
                <h2 className="text-lg font-semibold">编辑账单</h2>
                <div className="text-xs text-orange-100 mt-0.5">账单编号：{editingBill.bill_number} · 供应商：{editingBill.supplier_name}</div>
              </div>
              <button onClick={() => setShowEditModal(false)} className="text-orange-200 hover:text-white"><span className="text-xl leading-none">&times;</span></button>
            </div>

            <div className="p-6 space-y-4 overflow-y-auto flex-1 min-h-0">
              {(editingBill.status === "paid" || editingBill.paid_amount > 0) && (
                <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 text-sm text-amber-700">已付款的账单只能修改备注</div>
              )}

              {/* 基本信息 */}
              <div className="text-sm font-semibold text-gray-400 pb-1 border-b">基本信息</div>
              <div className="form-group">
                <label className="form-label">供应商</label>
                <select className="form-input" value={editForm.supplier_id} onChange={e => setEditForm({ ...editForm, supplier_id: +e.target.value })} disabled={(editingBill.status === "paid" || editingBill.paid_amount > 0)}>
                  <option value={0}>选择供应商</option>
                  {suppliers.map((s: any) => <option key={s.id} value={s.id}>{s.name}</option>)}
                </select>
              </div>
              <div className="form-grid">
                <div className="form-group"><label className="form-label">账单编号</label><input className="form-input" value={editForm.bill_number} onChange={e => setEditForm({ ...editForm, bill_number: e.target.value })} disabled={(editingBill.status === "paid" || editingBill.paid_amount > 0)} /></div>
                <div className="form-group"><label className="form-label">币种</label><select className="form-input" value={editForm.currency} onChange={e => setEditForm({ ...editForm, currency: e.target.value })} disabled={(editingBill.status === "paid" || editingBill.paid_amount > 0)}><option>THB</option><option>CNY</option><option>USD</option></select></div>
              </div>
              <div className="form-group"><label className="form-label">关联采购单号（可选）</label><input className="form-input" value={editForm.purchase_order_number} onChange={e => setEditForm({ ...editForm, purchase_order_number: e.target.value })} placeholder="如 PO2026..." disabled={(editingBill.status === "paid" || editingBill.paid_amount > 0)} /></div>
              <div className="form-grid">
                <div className="form-group"><label className="form-label">账单日期</label><input type="date" className="form-input" value={editForm.bill_date} onChange={e => setEditForm({ ...editForm, bill_date: e.target.value })} disabled={(editingBill.status === "paid" || editingBill.paid_amount > 0)} /></div>
                <div className="form-group"><label className="form-label">到期日期</label><input type="date" className="form-input" value={editForm.due_date} onChange={e => setEditForm({ ...editForm, due_date: e.target.value })} disabled={(editingBill.status === "paid" || editingBill.paid_amount > 0)} /></div>
              </div>

              {/* 金额信息 */}
              <div className="text-sm font-semibold text-gray-400 pb-1 border-b">金额信息</div>
              <div className="form-grid">
                <div className="form-group"><label className="form-label">金额</label><input type="number" className="form-input" value={editForm.amount || ""} onChange={e => setEditForm({ ...editForm, amount: e.target.value === "" ? "" : +e.target.value })} disabled={(editingBill.status === "paid" || editingBill.paid_amount > 0)} /></div>
                <div className="form-group"><label className="form-label">供应商确认金额</label><input type="number" className="form-input" value={editForm.confirmed_amount || ""} onChange={e => setEditForm({ ...editForm, confirmed_amount: e.target.value === "" ? "" : +e.target.value })} disabled={(editingBill.status === "paid" || editingBill.paid_amount > 0)} /></div>
              </div>
              {editForm.confirmed_amount !== "" && +editForm.confirmed_amount !== (editForm.amount !== "" ? +editForm.amount : editingBill.amount) && (
                <div className="bg-orange-50 border border-orange-200 rounded-lg p-3 text-sm text-orange-700 flex items-center gap-2">
                  <AlertTriangle size={16} />
                  确认金额与金额不一致，差额 {fmtMoney(Math.abs((editForm.amount !== "" ? +editForm.amount : editingBill.amount) - +editForm.confirmed_amount), editForm.currency || editingBill.currency)}
                </div>
              )}
              <div className="form-group"><label className="form-label">付款承诺天数</label><input type="number" className="form-input" value={editForm.payment_commitment_days || ""} onChange={e => setEditForm({ ...editForm, payment_commitment_days: e.target.value === "" ? "" : +e.target.value })} disabled={(editingBill.status === "paid" || editingBill.paid_amount > 0)} /></div>

              {/* 补充信息 */}
              <div className="text-sm font-semibold text-gray-400 pb-1 border-b">补充信息</div>
              <div className="form-group"><label className="form-label">费用明细</label><textarea className="form-input" rows={3} value={editForm.detail} onChange={e => setEditForm({ ...editForm, detail: e.target.value })} placeholder="费用明细描述" disabled={(editingBill.status === "paid" || editingBill.paid_amount > 0)} /></div>
              <div className="form-group"><label className="form-label">差异处理说明</label><textarea className="form-input" rows={2} value={editForm.diff_note} onChange={e => setEditForm({ ...editForm, diff_note: e.target.value })} placeholder="填写差异原因和处理结果" /></div>
              <div className="form-group"><label className="form-label">备注</label><input className="form-input" value={editForm.remark} onChange={e => setEditForm({ ...editForm, remark: e.target.value })} placeholder="其他备注" /></div>
            </div>

            <div className="border-t px-6 py-4 bg-gray-50 rounded-b-xl flex justify-end gap-3 shrink-0">
              <button onClick={() => setShowEditModal(false)} className="btn-secondary min-w-[80px]">取消</button>
              <ActionGate anyOf={["payable.update_bill#operate"]}><button onClick={()=>handleEdit()} className="btn-primary min-w-[80px]">保存修改</button></ActionGate>
            </div>
          </div>
        </div>
      )}

      {/* 作废弹窗 */}
      {showVoidModal && voidTarget && (
        <div className="modal-overlay" onClick={() => setShowVoidModal(false)}>
          <div className="bg-white rounded-xl w-full max-w-md max-h-[90vh] flex flex-col overflow-hidden shadow-2xl" onClick={e => e.stopPropagation()}>
            <div className="bg-red-500 text-white px-6 py-4 rounded-t-xl flex items-center gap-3 shrink-0">
              <Trash2 size={22} />
              <div className="flex-1"><h2 className="text-lg font-semibold">作废账单</h2></div>
              <button onClick={() => setShowVoidModal(false)} className="text-red-200 hover:text-white"><span className="text-xl leading-none">&times;</span></button>
            </div>
            <div className="p-6 space-y-4 overflow-y-auto flex-1 min-h-0">
              <div className="bg-gray-50 rounded-lg p-3 text-sm space-y-1.5">
                <div className="flex justify-between"><span className="text-gray-500">供应商</span><span className="text-gray-800">{voidTarget.supplier_name || "-"}</span></div>
                <div className="flex justify-between"><span className="text-gray-500">账单编号</span><span className="text-gray-800">{voidTarget.bill_number}</span></div>
                <div className="flex justify-between"><span className="text-gray-500">金额</span><span className="text-gray-800 font-medium">{fmtMoney(voidTarget.amount, voidTarget.currency)}</span></div>
              </div>
              <div className="form-group">
                <label className="form-label">作废原因 <span className="text-red-400">*</span></label>
                <textarea className="form-input" rows={3} value={voidReason} onChange={e => setVoidReason(e.target.value)} placeholder="请填写作废原因" />
              </div>
              <div className="text-xs text-gray-400">作废后这条账单会从应付里去掉，但记录会保留</div>
            </div>
            <div className="border-t px-6 py-4 bg-gray-50 rounded-b-xl flex justify-end gap-3 shrink-0">
              <button onClick={() => setShowVoidModal(false)} className="btn-secondary min-w-[80px]">取消</button>
              <ActionGate anyOf={["payable.void_bill#operate"]}><button onClick={handleVoid} className="bg-red-500 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-red-600 min-w-[100px]">确认作废</button></ActionGate>
            </div>
          </div>
        </div>
      )}

      {/* 付款弹窗 */}
      {showPayModal && payingRow && (
        <div className="modal-overlay" onClick={() => setShowPayModal(false)}>
          <div className="bg-white rounded-xl w-full max-w-lg max-h-[85vh] overflow-auto shadow-2xl" onClick={e => e.stopPropagation()}>
            <div className="bg-green-600 text-white px-6 py-4 rounded-t-xl flex items-center gap-3">
              <Receipt size={22} />
              <div className="flex-1">
                <h2 className="text-lg font-semibold">付款</h2>
                <div className="text-xs text-green-100 mt-0.5">
                  账单编号：{payingRow.bill_number} · 供应商：{payingRow.supplier_name}
                </div>
              </div>
              <button onClick={() => setShowPayModal(false)} className="text-green-200 hover:text-white"><span className="text-xl leading-none">&times;</span></button>
            </div>

            <div className="p-6 space-y-5">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <div className="bg-blue-50 rounded-lg p-3 text-center">
                  <div className="text-xs text-blue-500 mb-1">应付总额</div>
                  <div className="font-bold text-lg text-blue-700">{fmtMoney(payingRow.amount, payingRow.currency)}</div>
                </div>
                <div className="bg-green-50 rounded-lg p-3 text-center">
                  <div className="text-xs text-green-500 mb-1">已付金额</div>
                  <div className="font-bold text-lg text-green-700">{fmtMoney(payingRow.paid_amount, payingRow.currency)}</div>
                </div>
                <div className="bg-purple-50 rounded-lg p-3 text-center">
                  <div className="text-xs text-purple-500 mb-1">本次付款</div>
                  <div className="font-bold text-lg text-purple-700">{fmtMoney(payAmounts[payingBillId] || 0, payingRow.currency)}</div>
                </div>
                <div className={`rounded-lg p-3 text-center ${(payingRow.amount - payingRow.paid_amount - (payAmounts[payingBillId] || 0)) > 0 ? "bg-orange-50" : "bg-green-100"}`}>
                  <div className={`text-xs mb-1 ${(payingRow.amount - payingRow.paid_amount - (payAmounts[payingBillId] || 0)) > 0 ? "text-orange-500" : "text-green-600"}`}>{pendingRecovery ? "上次付款结果" : "付款后剩余应付"}</div>
                  <div className={`font-bold text-lg ${(payingRow.amount - payingRow.paid_amount - (payAmounts[payingBillId] || 0)) > 0 ? "text-orange-700" : "text-green-700"}`}>{pendingRecovery ? "待核对" : fmtMoney(payingRow.amount - payingRow.paid_amount - (payAmounts[payingBillId] || 0), payingRow.currency)}</div>
                </div>
              </div>

              <div className="border-t" />

              <div className="form-grid">
                {pendingRecovery && <p className="text-amber-700 text-sm">上次付款结果待确认，将沿用原请求编号、原金额、账户#{payAccountId}和方式，不会新建一笔付款。若修改输入，后端请求不会发送。</p>}<fieldset disabled={pendingRecovery}><WalletAccountSelect value={payAccountId} onChange={id=>{if(!pendingRecovery)setPayAccountId(id);}} currency={payingRow.currency || "THB"} /></fieldset>
                <div className="form-group"><label className="form-label">付款金额</label><input disabled={pendingRecovery} type="number" className="form-input text-lg font-semibold" value={payAmounts[payingBillId] ?? ""} onChange={e => setPayAmounts(prev => ({ ...prev, [payingBillId]: e.target.value === "" ? "" : +e.target.value }))} /></div>
                <div className="form-group"><label className="form-label">付款方式</label><select disabled={pendingRecovery} className="form-input" value={payMethod} onChange={e => setPayMethod(e.target.value)}><option>银行转账</option><option>现金</option><option>支票</option><option>PromptPay</option><option>其他</option></select></div>
              </div>
              <div className="form-group">
                <label className="form-label">上传付款凭证（非必填）</label>
                <div className="border-2 border-dashed border-gray-200 rounded-lg p-4 text-center hover:border-green-400 transition-colors">
                  <Upload size={24} className="mx-auto text-gray-300 mb-2" />
                  <input type="file" accept="image/*" onChange={e => setVoucherFile(e.target.files?.[0] || null)} className="text-sm text-gray-500 file:mr-4 file:py-1 file:px-3 file:rounded file:border-0 file:text-sm file:bg-green-50 file:text-green-700 hover:file:bg-green-100" />
                  <div className="text-xs text-gray-400 mt-2">可选，上传转账截图或回单</div>
                </div>
              </div>
            </div>

            <div className="border-t px-6 py-4 bg-gray-50 rounded-b-xl flex justify-end gap-3">
              <button onClick={() => setShowPayModal(false)} className="btn-secondary min-w-[80px]">取消</button>
              <ActionGate anyOf={["payable.pay_bill"]}><button onClick={handlePay} disabled={paymentSaving || !payAccountId} className="btn-primary min-w-[80px]">确认付款</button></ActionGate>
            </div>
          </div></div>
      )}

      {/* 图片预览弹窗 */}
      {previewUrl && (
        <div className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center" onClick={() => { setPreviewUrl(null); setPreviewLabel(""); }}>
          <div className="relative max-w-[90vw] max-h-[90vh]" onClick={e => e.stopPropagation()}>
            <div className="absolute top-2 left-4 text-white text-sm bg-black/50 px-3 py-1 rounded-full z-10">{previewLabel}</div>
            <button onClick={() => { setPreviewUrl(null); setPreviewLabel(""); }} className="absolute top-2 right-2 text-white bg-black/50 hover:bg-black/70 rounded-full w-8 h-8 flex items-center justify-center z-10 text-lg leading-none">&times;</button>
            {previewUrl.endsWith(".pdf") ? (
              <div className="bg-white rounded-xl p-8 text-center">
                <FileText size={48} className="mx-auto text-gray-400 mb-4" />
                <p className="text-gray-600 mb-4">PDF 文件</p>
                <a href={previewUrl} target="_blank" className="btn-primary" download>下载查看</a>
              </div>
            ) : (
              <img src={previewUrl} alt={previewLabel} className="max-w-[90vw] max-h-[85vh] object-contain rounded-lg shadow-2xl" />
            )}
          </div>
        </div>
      )}

      {/* 趋势图弹窗 */}
      {showTrend && (
        <div className="modal-overlay" onClick={() => setShowTrend(false)}>
          <div className="bg-white rounded-xl w-full max-w-3xl max-h-[90vh] overflow-auto shadow-2xl" onClick={e => e.stopPropagation()}>
            <div className="bg-indigo-600 text-white px-6 py-4 rounded-t-xl flex items-center gap-3">
              <TrendingUp size={22} /><h2 className="text-lg font-semibold">订单量 vs 耗材支出 趋势对比</h2>
              <div className="flex-1" /><button onClick={() => setShowTrend(false)} className="text-indigo-200 hover:text-white text-xl leading-none">&times;</button>
            </div>
            <div className="p-6">
              {/* SVG Chart */}
              {trendData.length > 0 ? (() => {
                const d = trendData; const m = d.length;
                const w = 800; const h = 300; const px = 60; const py = 40;
                const lw = w - px - 20; const lh = h - py * 2;
                const maxO = Math.max(...d.map((x: any) => x.order_count), 1);
                const maxS = Math.max(...d.map((x: any) => x.consumable_spending), 1);
                const scaleO = Math.ceil(maxO * 1.2); const scaleS = Math.ceil(maxS * 1.2);
                const step = lw / Math.max(m - 1, 1);
                let lineO = ""; let lineS = "";
                const dotsO: any[] = []; const dotsS: any[] = [];
                for (let i = 0; i < m; i++) {
                  const x = px + i * step;
                  const yO = py + lh - (d[i].order_count / scaleO * lh);
                  const yS = py + lh - (d[i].consumable_spending / scaleS * lh);
                  lineO += (i === 0 ? "M" : "L") + x + "," + yO + " ";
                  lineS += (i === 0 ? "M" : "L") + x + "," + yS + " ";
                  dotsO.push(<circle key={"o"+i} cx={x} cy={yO} r={4} fill="#2563EB"><title>订单量: {d[i].order_count}</title></circle>);
                  dotsS.push(<circle key={"s"+i} cx={x} cy={yS} r={4} fill="#EF4444"><title>耗材支出: {fmtMoney(d[i].consumable_spending)}</title></circle>);
                }
                const grid: any[] = [];
                for (let j = 0; j <= 4; j++) {
                  const yy = py + j * lh / 4;
                  grid.push(<line key={"g"+j} x1={px} y1={yy} x2={w-20} y2={yy} stroke="#eee" strokeWidth={1} />);
                  grid.push(<text key={"gt"+j} x={px-8} y={yy+4} textAnchor="end" fill="#999" fontSize={10}>{(scaleO*(4-j)/4).toFixed(0)}</text>);
                }
                return (
                  <svg viewBox="0 0 800 300" className="w-full">
                    {grid}
                    {dotsO}{dotsS}
                    <path d={lineO.trim()} fill="none" stroke="#2563EB" strokeWidth={2.5} />
                    <path d={lineS.trim()} fill="none" stroke="#EF4444" strokeWidth={2.5} strokeDasharray="6,3" />
                    {d.map((x: any, i: number) => <text key={"l"+i} x={px+i*step} y={h-10} textAnchor="middle" fill="#666" fontSize={11}>{x.month.substring(5)}月</text>)}
                  </svg>
                );
              })()
              : (
                <div className="text-center py-12 text-gray-400">暂无数据</div>
              )}

              {/* Warnings */}
              {trendWarnings.length > 0 && (
                <div className="mt-4 space-y-2">
                  {trendWarnings.map((w: string, i: number) => (
                    <div key={i} className="bg-red-50 border border-red-200 rounded-lg p-3 text-sm text-red-700 flex items-center gap-2">
                      <AlertTriangle size={16} /> {w}
                    </div>
                  ))}
                </div>
              )}

              {/* Legend */}
              <div className="flex items-center gap-6 mt-4 pt-3 border-t justify-center">
                <div className="flex items-center gap-2"><div className="w-4 h-4 rounded-full bg-blue-600" /><span className="text-xs text-gray-600">订单量（笔）</span></div>
                <div className="flex items-center gap-2"><div className="w-4 h-4 rounded-full bg-red-500" /><span className="text-xs text-gray-600">耗材支出（元）</span></div>
              </div>
            </div>
          </div>
        </div>
      )}


    </>
  );
}

export default function PayablePage() { return <FinancialIdentityBoundary><PayablePageContent /></FinancialIdentityBoundary>; }

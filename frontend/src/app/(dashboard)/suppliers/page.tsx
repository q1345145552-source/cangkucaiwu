"use client";
import { useEffect, useState, useRef } from "react";
import DataTable from "@/components/common/DataTable";
import { api, getToken, warehouseRequestHeaders } from "@/lib/api";
import { fmtMoney, fmtMoneyByCurrency } from "@/lib/currency";
import { useI18n } from "@/hooks/useI18n";
import { useToast } from "@/components/ui/Toast";
import { useAuth } from "@/hooks/useAuth";
import { useRouter } from "next/navigation";
import { LinkedPayable, PurchaseQuantities } from "@/components/ProcurementInfo";
import { ReceiptHistory, ThreeWayMatch } from "@/components/PurchaseReceiptInfo";
import { ApiError } from "@/lib/api";
import { useMenuPermission } from "@/hooks/useMenuPermission";
import { registrationDraft, submitRegistration, acceptQuotePreviewRejection, acceptDutyRejection } from "@/lib/registrationRequest";
import { controlScope,controlFields,controlMutation } from "@/lib/procurementControlRequest";
import ProcurementDutyFields from "@/components/ProcurementDutyFields";
import { useCostIdentity,CostConfirmation } from "@/components/CostIdentity";
import ExcelImportDialog from "@/components/ExcelImportDialog";
import { downloadExcel, checkExcel } from "@/lib/excelImport";
import ProductImportDialog from "@/components/ProductImportDialog";
import SkuProductMapping from "@/components/SkuProductMapping";
import SupplierQuoteEditor from "@/components/SupplierQuoteEditor";
import PurchaseQuotePreview from "@/components/PurchaseQuotePreview";
import PayableDuplicateDialog, { DuplicateConfirmation } from "@/components/PayableDuplicateDialog";
import { Sparkles, Eye, TrendingUp, TrendingDown, BarChart3, DollarSign, Lightbulb, Scale, Plus, Trash2, Download, Upload, User, Phone, MapPin, FileText, Calendar, Package, Truck, ShoppingCart, CheckCircle, Tag, AlertCircle } from "lucide-react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "/api/v1";

const FLOW_STATUS_MAP: Record<string, { label: string; cls: string }> = {
  pending_confirmation: { label: "待供应商确认", cls: "bg-yellow-100 text-yellow-700" },
  supplier_confirmed: { label: "供应商已确认", cls: "bg-blue-100 text-blue-700" },
  shipped: { label: "已发货", cls: "bg-purple-100 text-purple-700" },
  arrived: { label: "已到货验收", cls: "bg-orange-100 text-orange-700" },
  completed: { label: "已完成", cls: "bg-green-100 text-green-700" },
};

export default function SuppliersPage() {
  const cost=useCostIdentity();
  const { t } = useI18n();
  const { toast } = useToast(); const { user } = useAuth(); const router = useRouter();
  const [data, setData] = useState<any[]>([]); const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [showForm, setShowForm] = useState(false);
  const [categories, setCategories] = useState<any[]>([]);
  const canViewReport=useMenuPermission('suppliers')&&['warehouse_admin','supervisor','staff'].includes((user as {role?:string}|null)?.role||'');
  const canReadCatalog=useMenuPermission("sku_catalog"), canManageCatalog=useMenuPermission("sku_catalog_manage")&&canReadCatalog;
  const [mappingProductId,setMappingProductId]=useState(0),[productImportFile,setProductImportFile]=useState<File|null>(null),[productAttrsText,setProductAttrsText]=useState("");
  const [orderAvailableQuotes,setOrderAvailableQuotes]=useState<any[]>([]);
  const [quoteProductId,setQuoteProductId]=useState(0),[orderQuotes,setOrderQuotes]=useState<Record<number,number|null>>({}),[orderRequirements,setOrderRequirements]=useState<any>({quality_tags:[],max_lead_days:null}),[orderPricing,setOrderPricing]=useState<any>(null),[orderDraft,setOrderDraft]=useState<any>(null),[pricingRejection,setPricingRejection]=useState<any>(null);
  const quoteScope=JSON.stringify(warehouseRequestHeaders());
  useEffect(()=>{setQuoteProductId(0);setOrderAvailableQuotes([]);setOrderQuotes({});setOrderRequirements({quality_tags:[],max_lead_days:null});setOrderPricing(null);setOrderDraft(null);setPricingRejection(null);setShowOrder(false);},[quoteScope]);
  const [filterCat, setFilterCat] = useState(1);
  const [form, setForm] = useState({ name: "", contact_person: "", contact_info: "", address: "", payment_terms: "", cooperation_content: "", settlement_cycle: "", category_id: 0, default_currency: "THB" });
  const [aiResult, setAiResult] = useState("");
  const [procurement, setProcurement] = useState<any>(null);
  const [showProcurement, setShowProcurement] = useState(false);
  // Price monitor
  const [showPriceMonitor, setShowPriceMonitor] = useState(false);
  const [priceAnomalies, setPriceAnomalies] = useState<any[]>([]);
  const [priceStats, setPriceStats] = useState<any[]>([]);
  const [priceTrend, setPriceTrend] = useState<any[]>([]);
  const [trendProduct, setTrendProduct] = useState<any>(null);
  const [priceThreshold, setPriceThreshold] = useState(10);
  const [nonLowestRecords, setNonLowestRecords] = useState<any[]>([]);
  const [nonLowestSummary, setNonLowestSummary] = useState<any>(null);
  // 非最低价原因弹窗
  const [showReasonDialog, setShowReasonDialog] = useState(false);
  const [reasonItems, setReasonItems] = useState<any[]>([]);
  const [reasonMap, setReasonMap] = useState<Record<number, string>>({});
  // 采购审批
  const [showApprovals, setShowApprovals] = useState(false);
  const [pendingOrders, setPendingOrders] = useState<any[]>([]);
  const [splitGroups, setSplitGroups] = useState<any[]>([]);
  const [approvalThreshold, setApprovalThreshold] = useState(0);
  const [rejectTarget, setRejectTarget] = useState<any>(null);
  const [rejectReason, setRejectReason] = useState("");
  const [dutyDialog,setDutyDialog]=useState<any>(null),[receiveDuty,setReceiveDuty]=useState<any>(null),[dutyBusy,setDutyBusy]=useState(false);
  useEffect(()=>{setDutyDialog(null);setRejectTarget(null);setReceiveTarget(null);setReceiveDuty(null);setShowApprovals(false);setPendingOrders([]);setShowReceipt(false);setReceiptOrders([]);setPoDetail(null);poRequest.current++;},[quoteScope]);
  async function readDuty(po:any,action:string){
    const scope=controlScope(),kind=action==='receive'?'purchase_receipt':`duty_${action}`;
    const draft=registrationDraft(kind,po.id);
    const ctx=await api.get<any>(`/supplier-controls/orders/${po.id}/context?action=${action}`);
    if(controlScope()!==scope)throw Error('账号或仓库已变化，请重新打开');
    const locked=!!draft?.unknown;
    const fields=locked?(action==='receive'?draft!.payload.duty:((({reason,...rest}:any)=>rest)(draft!.payload))):controlFields(ctx);
    return {po,action,scope,ctx,fields,locked,exception:String(fields?.exception_id||''),draft:locked?draft:null};
  }
  function dutyPayload(value:any){
    if(value.locked)return value.fields;
    if(value.ctx.unknown_creator)throw Error('原采购人无法判断，请先核对原单');
    const exception=value.exception.trim();
    if(exception&&!/^[1-9]\d*$/.test(exception))throw Error('请输入有效的一次性例外授权编号');
    if(value.ctx.needs_exception&&!exception)throw Error('本人操作需要老板明确授予一次性例外，请填写授权编号');
    return {...value.fields,...(exception?{exception_id:Number(exception)}:{})};
  }
  async function startDuty(po:any,action:string){
    const scope=controlScope();
    try{const value=await readDuty(po,action);setDutyDialog(value);if(action==='reject'){setRejectTarget(po);setRejectReason(value.draft?.payload.reason||'');}}
    catch(e:any){if(controlScope()===scope)toast('error',e.message||'职责上下文读取失败');}
  }

  const [detail, setDetail] = useState<any>(null);
  // Products
  const [products, setProducts] = useState<any[]>([]);
  const [showProducts, setShowProducts] = useState(false);
  const [productSupplierId, setProductSupplierId] = useState(0);
  const [productForm, setProductForm] = useState({ product_name: "", spec: "", spec_price: "" as string | number, unit_price: "" as string | number, unit: "个", remark: "", currency: "THB" });
  // Logistics prices
  const [logisticsPrices, setLogisticsPrices] = useState<any[]>([]);
  const [showLogistics, setShowLogistics] = useState(false);
  const [logisticsSupplierId, setLogisticsSupplierId] = useState(0);
  const [logisticsForm, setLogisticsForm] = useState({ transport_method: "陆运", cargo_type: "普货", origin_warehouse: "深圳仓", price_per_cbm: "" as string | number, estimated_days: "", currency: "CNY" });
  // Compare
  const [compareData, setCompareData] = useState<any[]>([]);
  const [showCompare, setShowCompare] = useState(false);
  const [compareMode, setCompareMode] = useState<"product"|"logistics">("product");
  const [compareProduct, setCompareProduct] = useState("");
  const [compareSpec, setCompareSpec] = useState("");
  const [compareTransport, setCompareTransport] = useState("陆运");
  const [compareCargo, setCompareCargo] = useState("普货");
  const [compareWarehouse, setCompareWarehouse] = useState("深圳仓");
  const [compareCat, setCompareCat] = useState(0);
  const [aiCompareResult, setAiCompareResult] = useState("");
  // Import
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [logisticsFile,setLogisticsFile] = useState<File|null>(null);
  const [importMode, setImportMode] = useState<"products"|"logistics">("products");
  const [importSupplierId, setImportSupplierId] = useState<number | null>(null);
  // Order
  const [showOrder, setShowOrder] = useState(false);
  const [orderItems, setOrderItems] = useState<Record<number, number>>({});
  const [orderSupplierId, setOrderSupplierId] = useState(0);
  const [orderTotal, setOrderTotal] = useState(0);
  const [orderSubmitting, setOrderSubmitting] = useState(false);
  const priceReviewToken=useRef<string|null>(null);
  const [duplicateChallenge,setDuplicateChallenge]=useState<{detail:any;retry:(confirmation:DuplicateConfirmation)=>Promise<void>}|null>(null);
  // 采购收货验收
  const [showReceipt, setShowReceipt] = useState(false);
  const [receiptOrders, setReceiptOrders] = useState<any[]>([]);
  const [receiveTarget, setReceiveTarget] = useState<any>(null);
  const [receiveQty, setReceiveQty] = useState<Record<string, string>>({});
  const [receiveRemark,setReceiveRemark]=useState("");
  const [receivePhoto, setReceivePhoto] = useState<File | null>(null);
  const [receiptSubmitting, setReceiptSubmitting] = useState(false);
  const [showDiscrepancies, setShowDiscrepancies] = useState(false);
  const [discrepancies, setDiscrepancies] = useState<any[]>([]);
  // 采购单列表
  const [showPoList, setShowPoList] = useState(false);
  const [poList, setPoList] = useState<any[]>([]);
  const [poDetail, setPoDetail] = useState<any>(null);
  const poRequest=useRef(0);
  const payablePermission=useMenuPermission("payable"), planPermission=useMenuPermission("payment_plans");
  const receiptInputRef = useRef<HTMLInputElement>(null);
  const [receiptPoId, setReceiptPoId] = useState<number | null>(null);

  useEffect(() => { if (!getToken()) router.push("/login"); load(); loadCategories(); }, [page, filterCat]);

  async function load() {
    setLoading(true);
    try {
      let url = `/suppliers?page=${page}&page_size=20`;
      if (filterCat) url += `&category_id=${filterCat}`;
      const r = await api.get<any>(url); setData(r.data); setTotal(r.total);
    } catch (err) { console.error("加载失败:", err); }
    setLoading(false);
  }

  async function loadCategories() { try { const r = await api.get<any>("/suppliers/categories"); setCategories(r.data); } catch {} }

  async function handleCreate() {
    try {
      const payload: any = { ...form };
      if (!payload.category_id) delete payload.category_id;
      await api.post("/suppliers", payload);
      toast("success", "创建成功"); setShowForm(false); load();
    } catch (err: any) { toast("error", err.message || "创建失败"); }
  }

  // ─── Import ───
  async function downloadTemplate(mode: string) {
    try {
      await downloadExcel(`/suppliers/import-template/${mode}`,`${mode}_import_template.xlsx`);
    } catch (e: any) {
      toast("error", e.message || "下载失败");
    }
  }

  async function handleSupplierImport() {
    const file = fileInputRef.current?.files?.[0];
    const sid = importSupplierId;
    if (!file) return;
    if (fileInputRef.current) fileInputRef.current.value = "";
    try { checkExcel(file); if(importMode === "products") setProductImportFile(file); else setLogisticsFile(file); }
    catch(e:any) { toast("error",e.message); }
  }

  // ─── Products ───
  async function openProducts(sid: number) {
    setProductSupplierId(sid);setProductAttrsText("");
    const s = data.find((x: any) => x.id === sid);
    setProductForm(prev => ({ ...prev, currency: s?.default_currency || "THB" }));
    try { const r = await api.get<any>(`/suppliers/${sid}/products`); setProducts(r.data); } catch { setProducts([]); }
    setShowProducts(true);
  }
  async function addProduct() {
    try { await api.post(`/suppliers/${productSupplierId}/products`, { ...productForm,...(productAttrsText.trim()?{catalog_attributes:JSON.parse(productAttrsText)}:{}), spec_price: productForm.spec_price || 0, unit_price: productForm.unit_price || 0 }); toast("success", "产品添加成功");setProductAttrsText("");
      const r = await api.get<any>(`/suppliers/${productSupplierId}/products`); setProducts(r.data);
      setProductForm(prev => ({ product_name: "", spec: "", spec_price: "", unit_price: "", unit: "个", remark: "", currency: prev.currency }));
    } catch (err: any) { toast("error", err.message || "添加失败"); }
  }
  async function deleteProduct(pid: number) {
    try { await api.delete(`/suppliers/${productSupplierId}/products/${pid}`); toast("success", "已删除");
      const r = await api.get<any>(`/suppliers/${productSupplierId}/products`); setProducts(r.data);
    } catch { toast("error", "删除失败"); }
  }

  // ─── Place Order ───
  function openOrder(sid: number) {
    setOrderSupplierId(sid);
    setOrderItems({});
    setOrderTotal(0);priceReviewToken.current=null;
    setReasonMap({});setOrderAvailableQuotes([]);setOrderQuotes({});setOrderRequirements({quality_tags:[],max_lead_days:null});setOrderPricing(null);setOrderDraft(null);setPricingRejection(null);
    try {
      const draft=registrationDraft("purchase_order",sid);
      if(draft){priceReviewToken.current=draft.payload.price_review_token||null;setOrderDraft(draft);setOrderQuotes(Object.fromEntries(draft.payload.items.map((i:any)=>[i.product_id,i.quote_id||null])));setOrderRequirements(draft.payload.requirements||{quality_tags:[],max_lead_days:null});}
      if(draft){setOrderItems(Object.fromEntries(draft.payload.items.map((i:any)=>[i.product_id,i.quantity])));setReasonMap(Object.fromEntries(draft.payload.items.map((i:any)=>[i.product_id,i.reason || ""])));toast("success","已恢复原采购登记，请核对后沿用原请求重试");}
      api.get<any>(`/suppliers/${sid}/products`).then((r: any) => {
        setProducts(r.data);
        setShowOrder(true);
      });
    } catch { toast("error", "加载产品失败"); }
  }
  function toggleOrderItem(pid: number) {
    if(orderDraft?.unknown)return;
    priceReviewToken.current=null;setOrderPricing(null);
    const p = products.find((x: any) => x.id === pid);
    if (!p || (!(p.unit_price > 0)&&!orderAvailableQuotes.some(q=>q.product_id===pid))) {
      toast("error", "该产品尚未录入价格，请先录入价格后再下单");
      return;
    }
    setOrderItems(prev => {
      const next = { ...prev };
      if (next[pid]) { delete next[pid]; } else { next[pid] = 1; }
      return next;
    });
  }
  function updateQuantity(pid: number, qty: number) {
    if(orderDraft?.unknown)return;
    if(!Number.isInteger(qty)){toast("error","采购仅支持整数原单位，不会自动截断小数");return;}
    if (qty < 1) return;
    priceReviewToken.current=null;setOrderPricing(null);
    setOrderItems(prev => ({ ...prev, [pid]: qty }));
  }
  const selectedOrderIds=Object.keys(orderItems).map(Number).filter(id=>orderItems[id]>0);
  const orderPricingCurrent=orderPricing&&orderPricing.rows.length===selectedOrderIds.length&&JSON.stringify(orderPricing.requirements)===JSON.stringify(orderRequirements)&&orderPricing.rows.every((r:any)=>orderItems[r.product_id]===Number(r.quantity)&&(orderQuotes[r.product_id]||null)===(r.selected_quote?.id||null));
  // Compute order total; an explicit quote never silently uses the old product price.
  useEffect(() => {
    if(orderPricingCurrent){setOrderTotal(Number(orderPricing.total));return;}
    if(selectedOrderIds.some(id=>orderQuotes[id])){setOrderTotal(0);return;}
    let total = 0;
    products.forEach((p: any) => {
      if (orderItems[p.id]) total += (p.unit_price || 0) * (orderItems[p.id] || 0);
    });
    setOrderTotal(Math.round(total * 100) / 100);
  }, [orderItems, products, orderQuotes, orderPricing, orderPricingCurrent]);
  const orderCurrency = (() => {
    for (const p of products) {
      if (orderItems[p.id] > 0) return p.currency || "THB";
    }
    return "THB";
  })();
  const QUICK_REASONS = ["质量更好", "交货更快", "距离更近", "长期合作", "其他"];

  async function doSubmitOrder(confirmAnomaly: boolean, reasons: Record<number, string>, confirmation?:DuplicateConfirmation,costConfirmation?:CostConfirmation) {
    const selectedIds = Object.keys(orderItems).map(Number).filter(id => orderItems[id] > 0);
    if (selectedIds.length === 0) { toast("error", "请至少选择一个产品"); return; }
    setOrderSubmitting(true);
    try {
      const stored=registrationDraft("purchase_order",orderSupplierId);
      const needsPricing=selectedIds.some(id=>!!orderQuotes[id])||orderRequirements.quality_tags.length>0||orderRequirements.max_lead_days!==null;
      if(!stored?.unknown&&needsPricing&&(!orderPricingCurrent||!orderPricing.can_order))throw Error("请先核对有效报价与数量，处理不满足的条件后再提交");
      const payload = stored?.unknown?stored.payload:{
        items: selectedIds.map(id => ({ product_id: id, quantity: orderItems[id], reason: reasons[id] || "",...(orderQuotes[id]?{quote_id:orderQuotes[id]}:{}) })),
        ...(needsPricing?{pricing_version:orderPricing.version,requirements:orderRequirements}:{}),
        ...(priceReviewToken.current?{price_review_token:priceReviewToken.current}:{})
      };
      const r = await submitRegistration<any>("purchase_order",orderSupplierId,payload,key=>api.post<any>(`/suppliers/${orderSupplierId}/purchase-order`,{
        ...payload,request_key:key,confirm_price_anomaly:confirmAnomaly,duplicate_confirmation:confirmation,cost_confirmation:costConfirmation,
      }));
      if(r.price_review_token)priceReviewToken.current=r.price_review_token;
      if (r.need_confirm) {
        // 价格异常：确认后再提交
        const lines = (r.anomalies || []).map((a: any) =>
          `· ${a.product_name}${a.spec ? `（${a.spec}）` : ""}：采购价 ${a.unit_price} ${a.currency || ""}/${a.original_unit || ""}，历史均价 ${a.historical_avg}，高出 ${a.exceed_percent}%\n${a.note || "历史价格参考，不代表当前有效最低价或真实损失。"}`
        ).join("\n");
        const ok = confirm(`${r.message}\n\n${lines}\n\n价格高于历史均价，确认仍要提交？`);
        if (!ok) return;
        await doSubmitOrder(true, reasons);
        return;
      }
      if (r.need_reason) {
        // 非最低价：弹原因输入框
        setReasonItems(r.non_lowest_items || []);
        setReasonMap({ ...reasons });
        setShowReasonDialog(true);
        return;
      }
      toast("success", r.message || "下单成功");
      setShowOrder(false);
      setShowProducts(false);
      if (r.pending) {
        return; // 待审批，不跳转
      }
      if (confirm(`采购单已创建，应付账单编号: ${r.payable_bill_number}\n是否跳转到应付账款页面？`)) {
        router.push(payablePermission || planPermission ? `/payable?bill_id=${r.payable_bill_id}` : `/suppliers/purchase-orders/${r.order.id}`);
      }
    } catch (err: any) { setOrderDraft(registrationDraft("purchase_order",orderSupplierId));if(err.detail?.code==='quote_preview_changed'){priceReviewToken.current=null;setOrderPricing(null);setPricingRejection(err.detail);toast("error",err.message);}else if(cost.capture(err,data=>doSubmitOrder(confirmAnomaly,reasons,confirmation,data))){}else if(err.detail?.candidates){setDuplicateChallenge({detail:err.detail,retry:data=>doSubmitOrder(confirmAnomaly,reasons,data,costConfirmation)});}else toast("error", err.message || "下单失败"); }
    finally { setOrderSubmitting(false); }
  }

  function submitOrder() { doSubmitOrder(false, reasonMap); }

  function confirmReasonSubmit() {
    for (const item of reasonItems) {
      if (!(reasonMap[item.product_id] || "").trim()) {
        toast("error", `请为「${item.product_name}」填写采购原因`);
        return;
      }
    }
    setShowReasonDialog(false);
    doSubmitOrder(true, reasonMap);
  }
  // ─── 采购审批 ───
  async function openApprovals() {
    const scope=controlScope();
    setShowApprovals(true);
    try {
      const [r, th] = await Promise.all([
        api.get<any>("/suppliers/purchase-approvals"),
        api.get<any>("/suppliers/purchase-approval-threshold"),
      ]);
      if(controlScope()!==scope)return;
      setPendingOrders(r.pending || []);
      setSplitGroups(r.split_groups || []);
      setApprovalThreshold(th.threshold ?? 0);
    } catch {}
  }
  async function approveOrder(id:number,confirmation?:DuplicateConfirmation,costConfirmation?:CostConfirmation,payload?:any,scope?:string) {
    if(!payload||!scope)return startDuty({id},'approve');
    setDutyBusy(true);
    try {
      await controlMutation('duty_approve',id,payload,`/suppliers/purchase-approvals/${id}/approve`,'PUT',scope,{duplicate_confirmation:confirmation,cost_confirmation:costConfirmation});
      if(controlScope()!==scope)return;
      setDutyDialog(null);await openPoDetail(id);
      toast("success", "审批通过，应付账单已生成");openApprovals();
    } catch(e:any){if(controlScope()!==scope)return;
      if(cost.capture(e,data=>approveOrder(id,confirmation,data,payload,scope))){}
      else if(e.detail?.candidates)setDuplicateChallenge({detail:e.detail,retry:data=>approveOrder(id,data,costConfirmation,payload,scope)});
      else {const draft=registrationDraft('duty_approve',id);setDutyDialog((old:any)=>old?.scope===scope?{...old,locked:!!draft?.unknown,...(draft?.unknown?{fields:draft.payload,draft}:{})}:old);toast('error',e.message||'审批失败');}
    }finally{setDutyBusy(false);}
  }
  async function confirmApprove(){
    if(!dutyDialog||dutyBusy)return;
    try{await approveOrder(dutyDialog.po.id,undefined,undefined,dutyPayload(dutyDialog),dutyDialog.scope);}
    catch(e:any){toast('error',e.message);}
  }
  async function confirmReject() {
    if(!rejectTarget||!dutyDialog||dutyBusy)return;
    if(!rejectReason.trim()){toast('error','请填写驳回原因');return;}
    const value=dutyDialog;setDutyBusy(true);
    try {
      const payload=value.locked?value.draft.payload:{reason:rejectReason,...dutyPayload(value)};
      await controlMutation('duty_reject',rejectTarget.id,payload,`/suppliers/purchase-approvals/${rejectTarget.id}/reject`,'PUT',value.scope);
      if(controlScope()!==value.scope)return;
      toast('success','已驳回');setRejectTarget(null);setDutyDialog(null);setRejectReason('');openApprovals();
    }catch(e:any){if(controlScope()===value.scope){const draft=registrationDraft('duty_reject',rejectTarget.id);setDutyDialog((old:any)=>old?{...old,locked:!!draft?.unknown,...(draft?.unknown?{fields:draft.payload,draft}:{})}:old);toast('error',e.message||'驳回失败');}}
    finally{setDutyBusy(false);}
  }
  // ─── 采购收货验收 ───
  async function openReceipt() {
    const scope=controlScope();
    setShowReceipt(true);
    setReceiptOrders([]);
    try {
      const r = await api.get<any>("/suppliers/purchase-orders?page=1&page_size=100");
      if(controlScope()===scope)setReceiptOrders(r.data || []);
    } catch { if(controlScope()===scope)setReceiptOrders([]); }
  }
  async function openReceiveForm(po: any) {
    try {
      const scope=controlScope();
      const [fresh,value]=await Promise.all([api.get<any>(`/suppliers/purchase-orders/${po.id}`),readDuty(po,'receive')]);
      if(controlScope()!==scope)return;
      const draft=registrationDraft("purchase_receipt",po.id);
      setReceiveDuty(value);
      const restored:Record<string,string>={};
      (fresh.items || []).forEach((it:any)=>{restored[it.line_id]=String(it.remaining_quantity ?? 0);});
      if(draft)draft.payload.items.forEach((it:any)=>{restored[it.line_id]=String(it.received_quantity);});
      setReceiveTarget(fresh);setReceiveQty(restored);setReceiveRemark(draft?.payload.remark || "");setReceivePhoto(null);
      if(draft)toast("success","已恢复原收货请求，请选择原照片沿用原请求重试");
    }catch(e:any){toast("error",e.message || "收货明细读取失败");}
  }
  async function submitReceive() {
    if (!receiveTarget || receiptSubmitting) return;
    if (!receivePhoto) { toast("error", "请上传到货照片"); return; }
    const items=[];
    for(const it of receiveTarget.items || []) {
      const raw=receiveQty[it.line_id] ?? "";
      if(!/^\d+$/.test(raw) || !Number.isSafeInteger(Number(raw)) || Number(raw)>2147483647) {
        toast("error","本次收货数量必须是非负整数，不支持小数或自动截断");return;
      }
      items.push({line_id:it.line_id,received_quantity:Number(raw)});
    }
    if(!items.some(it=>it.received_quantity>0)){toast("error","本次至少一行收货数量须大于零");return;}
    const target=receiveTarget,value=receiveDuty;
    if(!value||controlScope()!==value.scope){toast('error','账号或仓库已变化，请重新打开');return;}
    let duty:any;try{duty=dutyPayload(value);}catch(e:any){toast('error',e.message);return;}
    const payload={items,remark:receiveRemark,...(duty?{duty}:{})},headers=warehouseRequestHeaders();
    setReceiptSubmitting(true);
    try {
      const fd = new FormData();fd.append("items",JSON.stringify(items));fd.append("file",receivePhoto);fd.append("remark",receiveRemark);
      const r=await submitRegistration<any>("purchase_receipt",target.id,payload,async key=>{
        if(controlScope()!==value.scope)throw Error('账号或仓库已变化，未提交');
        fd.set("request_key",key);
        Object.entries(duty||{}).forEach(([k,v])=>fd.set(k,String(v)));
        const res=await fetch(`/api/v1/suppliers/purchase-orders/${target.id}/receive`,{method:"POST",headers,body:fd});
        const result=await res.json();
        if(controlScope()!==value.scope)throw Error('账号或仓库已变化，原结果待核对，请回原仓沿用原请求重试');
        if(!res.ok)throw new ApiError(res.status,result.detail || "收货失败");return result;
      });
      toast("success",`收货批次 #${r.receipt_event_id} 已保存${r.replayed ? "，未重复累计" : r.has_diff ? "，累计数量有差异，待老板复核" : ""}`);
      setReceiveTarget(null);openReceipt();
      if(poDetail?.id===target.id)await openPoDetail(target.id);
      if(showDiscrepancies)openDiscrepancies();
    }catch(e:any){if(controlScope()===value.scope){
      if(e.detail?.code==='procurement_duty_changed')acceptDutyRejection('purchase_receipt',target.id,e.detail);
      const draft=registrationDraft('purchase_receipt',target.id);setReceiveDuty((old:any)=>old?{...old,locked:!!draft?.unknown,...(draft?.unknown?{fields:draft.payload.duty,draft}:{})}:old);
      toast("error",e.message || "收货失败");
    }}finally{setReceiptSubmitting(false);}
  }
  async function openDiscrepancies() {
    setShowDiscrepancies(true);
    setDiscrepancies([]);
    try {
      const r = await api.get<any>("/suppliers/purchase-receipt-discrepancies");
      setDiscrepancies(r.data || []);
    } catch { setDiscrepancies([]); }
  }
  function uploadUrl(p: string) {
    if (!p) return "";
    if (p.startsWith("http")) return p;
    return API_URL.replace("/api/v1", "") + p;
  }
  // ─── 采购单列表 ───
  async function openPoList() {
    setShowPoList(true);
    setPoList([]);
    setPoDetail(null);
    try {
      const r = await api.get<any>("/suppliers/purchase-orders?page=1&page_size=100");
      setPoList(r.data || []);
    } catch { setPoList([]); }
  }
  async function downloadPoPdf(po: any) {
    try {
      const res = await fetch(`/api/v1/suppliers/purchase-orders/${po.id}/pdf`, {
        headers: warehouseRequestHeaders(),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "下载失败" }));
        toast("error", err.detail || "下载失败");
        return;
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `采购单_${po.order_number}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch { toast("error", "下载失败"); }
  }
  async function openPoDetail(id: number) {
    const request=++poRequest.current,scope=controlScope();setPoDetail(null);
    try { const result=await api.get<any>(`/suppliers/purchase-orders/${id}`);if(request===poRequest.current&&controlScope()===scope)setPoDetail(result); }
    catch(e:any){if(request===poRequest.current&&controlScope()===scope)toast("error",e.message || "采购详情加载失败");}
  }
  async function refreshPoDetail() { if(poDetail?.id)await openPoDetail(poDetail.id); }
  async function markSent(po: any) {
    try {
      await api.post(`/suppliers/purchase-orders/${po.id}/mark-sent`, {});
      toast("success", "已标记发送给供应商");
      refreshPoDetail();
    } catch (e: any) { toast("error", e.message || "操作失败"); }
  }
  async function markShipped(po: any) {
    try {
      await api.post(`/suppliers/purchase-orders/${po.id}/mark-shipped`, {});
      toast("success", "已标记发货");
      refreshPoDetail();
    } catch (e: any) { toast("error", e.message || "操作失败"); }
  }
  function triggerReceiptUpload(poId: number) {
    setReceiptPoId(poId);
    setTimeout(() => receiptInputRef.current?.click(), 50);
  }
  async function handleReceiptUpload(file: File) {
    if (!receiptPoId) return;
    try {
      const fd = new FormData();
      fd.append("file", file);
      const res = await fetch(`/api/v1/suppliers/purchase-orders/${receiptPoId}/receipt`, {
        method: "POST", headers: warehouseRequestHeaders(), body: fd,
      });
      const r = await res.json();
      if (!res.ok) { toast("error", r.detail || "上传失败"); return; }
      toast("success", "回执已上传，供应商已确认");
      setReceiptPoId(null);
      refreshPoDetail();
    } catch { toast("error", "上传失败"); }
    if (receiptInputRef.current) receiptInputRef.current.value = "";
  }
  // ─── 价格监控 ───
  async function openPriceMonitor() {
    setShowPriceMonitor(true);
    setTrendProduct(null); setPriceTrend([]);
    try {
      const [anoms, stats, th, nl, nls] = await Promise.all([
        api.get<any>("/suppliers/price-anomalies?page_size=100"),
        api.get<any>("/suppliers/price-stats"),
        api.get<any>("/suppliers/price-threshold"),
        api.get<any>("/suppliers/non-lowest-records?page_size=100"),
        api.get<any>("/suppliers/non-lowest-summary"),
      ]);
      setPriceAnomalies(anoms.data || []);
      setPriceStats(stats.data || []);
      setPriceThreshold(th.threshold ?? 10);
      setNonLowestRecords(nl.data || []);
      setNonLowestSummary(nls);
    } catch {}
  }
  async function loadPriceTrend(name: string, spec: string | null) {
    setTrendProduct({ product_name: name, spec });
    try {
      const r = await api.get<any>(`/suppliers/price-trend?product_name=${encodeURIComponent(name)}&spec=${encodeURIComponent(spec || "")}`);
      setPriceTrend(r.data || []);
    } catch { setPriceTrend([]); }
  }
  // ─── Logistics Prices ───
  async function openLogistics(sid: number) {
    setLogisticsSupplierId(sid);
    try { const r = await api.get<any>(`/suppliers/${sid}/logistics-prices`); setLogisticsPrices(r.data); } catch { setLogisticsPrices([]); }
    setShowLogistics(true);
  }
  async function addLogisticsPrice() {
    try { await api.post(`/suppliers/${logisticsSupplierId}/logistics-prices`, { ...logisticsForm, price_per_cbm: logisticsForm.price_per_cbm || 0 }); toast("success", "报价添加成功");
      const r = await api.get<any>(`/suppliers/${logisticsSupplierId}/logistics-prices`); setLogisticsPrices(r.data);
      setLogisticsForm({ transport_method: "陆运", cargo_type: "普货", origin_warehouse: "深圳仓", price_per_cbm: "", estimated_days: "", currency: "CNY" });
    } catch { toast("error", "添加失败"); }
  }
  async function deleteLogisticsPrice(pid: number) {
    try { await api.delete(`/suppliers/${logisticsSupplierId}/logistics-prices/${pid}`); toast("success", "已删除");
      const r = await api.get<any>(`/suppliers/${logisticsSupplierId}/logistics-prices`); setLogisticsPrices(r.data);
    } catch { toast("error", "删除失败"); }
  }

  // ─── Compare ───
  async function doCompare(mode: string) {
    setCompareMode(mode as any);
    try {
      if (mode === "logistics") {
        let url = `/suppliers/compare-logistics?transport_method=${encodeURIComponent(compareTransport)}&cargo_type=${encodeURIComponent(compareCargo)}&origin_warehouse=${encodeURIComponent(compareWarehouse)}`;
        if (compareCat) url += `&category_id=${compareCat}`;
        const r = await api.get<any>(url);
        setCompareData(r.data.map((x: any) => ({ ...x, _type: "logistics" })));
      } else {
        let url = `/suppliers/compare-prices?product_name=${encodeURIComponent(compareProduct)}`;
        if (compareSpec) url += `&spec=${encodeURIComponent(compareSpec)}`;
        if (compareCat) url += `&category_id=${compareCat}`;
        const r = await api.get<any>(url);
        setCompareData(r.data.map((x: any) => ({ ...x, _type: "product" })));
      }
    } catch { setCompareData([]); }
  }

  async function doAiCompare() {
    setAiCompareResult("分析中...");
    try {
      const r = await api.post<{ result?: string }>("/suppliers/ai-compare", { compare_data: compareData, mode: compareMode });
      setAiCompareResult(r.result || "分析完成");
    } catch (e: any) { setAiCompareResult(e.message); }
  }


  async function viewDetail(sid: number) {
    try {
      const r = await api.get<any>(`/suppliers/${sid}`);
      try { const prods = await api.get<any>(`/suppliers/${sid}/products`); r.products = prods.data; } catch { r.products = []; }
      try { const lp = await api.get<any>(`/suppliers/${sid}/logistics-prices`); r.logistics_prices = lp.data; } catch { r.logistics_prices = []; }
      setDetail(r);
    } catch {}
  }

  async function deleteSupplier(sid: number) {
    if (!confirm("确定要删除该供应商吗？")) return;
    try { await api.delete(`/suppliers/${sid}`); toast("success", "已删除"); load(); }
    catch (err: any) { toast("error", err.message || "删除失败"); }
  }

  const isAdmin = user?.role === "warehouse_admin" || user?.role === "supervisor";

  return (
    <>
      {duplicateChallenge && <PayableDuplicateDialog challenge={duplicateChallenge.detail} onClose={()=>setDuplicateChallenge(null)} onConfirm={async data=>{const retry=duplicateChallenge.retry;setDuplicateChallenge(null);await retry(data);}}/>}
      {cost.dialog}
      {logisticsFile&&<ExcelImportDialog file={logisticsFile} endpoint={importSupplierId?`/suppliers/${importSupplierId}/import/logistics`:'/suppliers/import/logistics'} title={`物流报价预览 · ${data.find((s:any)=>s.id===importSupplierId)?.name||'本仓多供应商'}`} resource={importSupplierId||0} onClose={()=>{setLogisticsFile(null);setImportSupplierId(null);}} onImported={r=>{toast('success',r.message);load();}}/>}
      {productImportFile&&<ProductImportDialog canMap={canManageCatalog} file={productImportFile} supplierName={data.find((s:any)=>s.id===importSupplierId)?.name} supplierId={importSupplierId||undefined} onClose={()=>{setProductImportFile(null);setImportSupplierId(null);if(fileInputRef.current)fileInputRef.current.value="";}} onImported={r=>{toast("success",r.message);load();}}/>}
      {quoteProductId>0&&<SupplierQuoteEditor supplierId={productSupplierId} productId={quoteProductId} canEdit={canManageCatalog} onClose={()=>setQuoteProductId(0)} onDone={()=>toast("success","报价版本已保存，旧采购快照不变")}/>}
      {mappingProductId>0&&<SkuProductMapping productId={mappingProductId} canEdit={canManageCatalog} onClose={()=>setMappingProductId(0)} onDone={()=>{toast("success","人工映射已保存，历史订单不变");openProducts(productSupplierId);}}/>}
      <div className="flex justify-between mb-4 flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <h1 className="page-title">{t("suppliers")}</h1>
          <button onClick={() => { setFilterCat(1); setPage(1); }}
            className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-colors ${filterCat === 1 ? "bg-blue-600 text-white shadow" : "bg-gray-100 text-gray-500 hover:bg-gray-200"}`}>
            耗材商
          </button>
          <button onClick={() => { setFilterCat(2); setPage(1); }}
            className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-colors ${filterCat === 2 ? "bg-green-600 text-white shadow" : "bg-gray-100 text-gray-500 hover:bg-gray-200"}`}>
            物流
          </button>
        </div>
        <div className="flex gap-2 flex-wrap">
          {(user as {role?:string}|null)?.role==='warehouse_admin'&&<button className="btn-secondary text-sm" onClick={()=>router.push('/suppliers/risk')}>采购风险看板</button>}
          {canViewReport&&<button className="btn-secondary text-sm" onClick={()=>router.push("/suppliers/monthly-price-report")}>采购价差月报</button>}
          {isAdmin && (
            <>
              {/* Template download */}
              <button onClick={() => downloadTemplate("products")} className="border px-3 py-2 rounded text-sm flex items-center gap-1"><Download size={14}/>耗材模板</button>
              <button onClick={() => downloadTemplate("logistics")} className="border px-3 py-2 rounded text-sm flex items-center gap-1"><Download size={14}/>物流模板</button>
              <button className="btn-secondary" onClick={()=>{setImportSupplierId(null);setImportMode('products');setTimeout(()=>fileInputRef.current?.click(),0);}}>多供应商耗材导入</button>
              <button className="btn-secondary" onClick={()=>{setImportSupplierId(null);setImportMode('logistics');setTimeout(()=>fileInputRef.current?.click(),0);}}>多供应商物流导入</button>
              <p className="text-xs">仅.xlsx；.xls请另存为.xlsx，不能只改扩展名。单供应商入口在对应供应商行。</p>
              <input ref={fileInputRef} type="file" accept=".xlsx" onChange={handleSupplierImport} className="hidden" />
              <input aria-label="上传采购回执" ref={receiptInputRef} type="file" accept="image/*" onChange={e => { const f = e.target.files?.[0]; if (f) handleReceiptUpload(f); }} className="hidden" />
              <button onClick={() => { setCompareMode("product"); setShowCompare(true); }}
                className="border px-3 py-2 rounded text-sm flex items-center gap-1"><Scale size={16}/>比价</button>
              <button onClick={async () => { try { const r = await api.get<any>("/suppliers/procurement-summary"); setProcurement(r); setShowProcurement(true); } catch {} }}
                className="border px-3 py-2 rounded text-sm flex items-center gap-1"><TrendingUp size={16}/>采购汇总</button>
              <button onClick={openPriceMonitor}
                className="border px-3 py-2 rounded text-sm flex items-center gap-1"><BarChart3 size={16}/>价格监控</button>
              {(user?.role === "warehouse_admin" || user?.role === "supervisor") && (
                <button onClick={openApprovals}
                  className="border px-3 py-2 rounded text-sm flex items-center gap-1"><CheckCircle size={16}/>采购审批</button>
              )}
              <button onClick={openReceipt}
                className="border px-3 py-2 rounded text-sm flex items-center gap-1"><Package size={16}/>收货验收</button>
              <button onClick={openDiscrepancies}
                className="border px-3 py-2 rounded text-sm flex items-center gap-1"><AlertCircle size={16}/>收货差异</button>
              <button onClick={openPoList}
                className="border px-3 py-2 rounded text-sm flex items-center gap-1"><FileText size={16}/>采购单列表</button>
              <button onClick={() => { setForm({...form, category_id: filterCat}); setShowForm(true); }} className="btn-primary">新建供应商</button>
            </>
          )}
        </div>
      </div>
      {loading ? <div className="text-center py-8 text-gray-400">加载中...</div> : <DataTable columns={[
        { key: "name", label: "名称" },
        { key: "category_name", label: "类别", render: (v:any) => v ? <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${v==="耗材商"?"bg-blue-100 text-blue-700":"bg-green-100 text-green-700"}`}>{v}</span> : "-" },
        { key: "contact_person", label: "联系人" },
        { key: "contact_info", label: "联系方式" },
        { key: "settlement_cycle", label: "结算周期", render: (v:any)=>v||"-" },
        { key: "id", label: "操作", render: (_:any, row:any) => (
          <div className="flex gap-1 flex-wrap items-center">
            {row.category_id === 1 && (
              <>
                <button onClick={()=>{setImportSupplierId(row.id);setImportMode("products");setTimeout(()=>fileInputRef.current?.click(),100);}} className="text-purple-500 hover:bg-purple-50 flex items-center gap-1 text-xs px-1.5 py-1 rounded" title="导入产品"><Upload size={12}/></button>
                <button onClick={()=>openProducts(row.id)} className="text-green-600 hover:bg-green-50 flex items-center gap-1 text-xs px-1.5 py-1 rounded"><Plus size={12}/>产品</button>
              </>
            )}
            {row.category_id === 2 && (
              <>
                <button onClick={()=>{setImportSupplierId(row.id);setImportMode("logistics");setTimeout(()=>fileInputRef.current?.click(),100);}} className="text-purple-500 hover:bg-purple-50 flex items-center gap-1 text-xs px-1.5 py-1 rounded" title="导入物流"><Upload size={12}/></button>
                <button onClick={()=>openLogistics(row.id)} className="text-orange-600 hover:bg-orange-50 flex items-center gap-1 text-xs px-1.5 py-1 rounded"><TrendingUp size={12}/>物流</button>
              </>
            )}
            <button onClick={()=>viewDetail(row.id)} className="text-blue-500 flex items-center gap-1 text-xs"><Eye size={12}/>详情</button>
            {isAdmin && (
              <button onClick={()=>deleteSupplier(row.id)} className="text-red-500 flex items-center gap-1 text-xs"><Trash2 size={12}/>删除</button>
            )}
          </div>
        )},
      ]} data={data} total={total} page={page} pageSize={20} onPageChange={setPage} />}
      
      {/* Products Modal */}
      {showProducts && (
        <div className="modal-overlay z-50" onClick={()=>setShowProducts(false)}>
          <div className="bg-white rounded-2xl w-[900px] max-h-[85vh] overflow-auto shadow-2xl" onClick={e=>e.stopPropagation()}>
            {/* Header */}
            <div className="bg-blue-600 text-white px-5 py-3.5 rounded-t-2xl flex items-center gap-2 sticky top-0 z-10">
              <Package size={18} />
              <h2 className="font-semibold">产品定价 - {data.find((s:any)=>s.id===productSupplierId)?.name || ""}{(()=>{const s=data.find((x:any)=>x.id===productSupplierId); return s?.settlement_cycle ? ` （账期: ${s.settlement_cycle}）` : "";})()}</h2>
              <button onClick={()=>setShowProducts(false)} className="ml-auto text-blue-200 hover:text-white text-lg leading-none">&times;</button>
            </div>
            {/* Form */}
            <div className="p-5 space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="form-label text-sm font-medium text-gray-600 mb-1 block">产品名称 <span className="text-red-400">*</span></label>
                  <input className="form-input text-base py-2.5" placeholder="输入产品名称" value={productForm.product_name} onChange={e=>setProductForm({...productForm,product_name:e.target.value})} autoFocus />
                </div>
                <div>
                  <label className="form-label text-sm font-medium text-gray-600 mb-1 block">产品规格</label>
                  <input className="form-input text-base py-2.5" placeholder="如: 38*45cm / 一打80个" value={productForm.spec} onChange={e=>setProductForm({...productForm,spec:e.target.value})} />
                </div>
              </div>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <div>
                  <label className="form-label text-sm font-medium text-gray-600 mb-1 block">规格报价</label>
                  <input type="number" className="form-input text-base py-2.5" placeholder="规格对应报价" value={productForm.spec_price||""} onChange={e=>setProductForm({...productForm,spec_price:e.target.value===""?"":+e.target.value})} />
                </div>
                <div>
                  <label className="form-label text-sm font-medium text-gray-600 mb-1 block">单价 <span className="text-red-400">*</span></label>
                  <input type="number" className="form-input text-base py-2.5" placeholder="标准单价" value={productForm.unit_price||""} onChange={e=>setProductForm({...productForm,unit_price:e.target.value===""?"":+e.target.value})} />
                </div>
                <div>
                  <label className="form-label text-sm font-medium text-gray-600 mb-1 block">币种</label>
                  <select className="form-input text-base py-2.5" value={productForm.currency} onChange={e=>setProductForm({...productForm,currency:e.target.value})}>
                    <option value="THB">泰铢 (฿)</option>
                    <option value="CNY">人民币 (¥)</option>
                  </select>
                </div>
                <div className="flex items-end">
                  <button onClick={addProduct} disabled={!productForm.product_name.trim() || !productForm.unit_price}
                    className={`w-full py-2.5 rounded-lg text-sm font-medium transition-colors ${!productForm.product_name.trim() || !productForm.unit_price ? "bg-gray-200 text-gray-400 cursor-not-allowed" : "bg-green-600 text-white hover:bg-green-700"}`}>
                    + 添加产品
                  </button>
                </div>
              </div>

              <label className="block text-sm mb-3">结构化规格JSON（可选，用于SKU候选核对）<textarea aria-label="新产品结构化规格JSON" className="form-input" value={productAttrsText} onChange={e=>setProductAttrsText(e.target.value)} placeholder={'例如 {"material":"PE","width":{"value":38,"unit":"cm"},"packaging":"single"}'}/></label>
              {/* Product Table */}
              <div className="pt-3">
                <div className="flex items-center gap-2 mb-3">
                  <div className="h-px flex-1 bg-gray-200" />
                  <span className="text-xs text-gray-400 font-medium">共 {products.length} 个产品</span>
                  <div className="h-px flex-1 bg-gray-200" />
                </div>
                {products.length === 0 ? (
                  <div className="text-center py-12 text-gray-400 text-sm">暂无产品，请在上方添加</div>
                ) : (
                  <div className="overflow-x-auto touch-pan-x">
                    <table className="w-full text-sm min-w-[900px]">
                      <thead>
                        <tr className="border-b bg-gray-50">
                          <th className="text-left px-3 py-3 font-medium text-gray-500 w-[23%]">产品名称</th>
                          <th className="text-left px-3 py-3 font-medium text-gray-500 w-[17%]">产品规格</th>
                          <th className="text-right px-3 py-3 font-medium text-gray-500 w-[12%]">规格报价</th>
                          <th className="text-right px-3 py-3 font-medium text-gray-500 w-[15%]">单价</th>
                          <th className="text-center px-3 py-3 font-medium text-gray-500 w-[15%]">价格对比</th>
                          <th className="text-center px-3 py-3 font-medium text-gray-500 w-[18%]">操作</th>
                        </tr>
                      </thead>
                      <tbody>
                        {products.map((p:any)=>(
                          <tr key={p.id} className="border-b hover:bg-gray-50/50 transition-colors">
                            <td className="px-3 py-3 font-medium text-gray-800">{p.product_name}<p className="text-xs text-gray-500">{p.mapping_label||"未映射/待核对"} {p.sku_snapshot?.code||""}</p></td>
                            <td className="px-3 py-3 text-gray-500">{p.spec||"-"}</td>
                            <td className="px-3 py-3 text-right text-gray-700">{p.spec_price != null ? fmtMoney(p.spec_price, p.currency) : "-"}</td>
                            <td className="px-3 py-3 text-right font-semibold text-green-700">{fmtMoney(p.unit_price, p.currency)}</td>
                            <td className="px-3 py-3 text-center">
                              {p.is_lowest ? (
                                <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-green-100 text-green-700 rounded-full text-xs font-medium">
                                  <Tag size={10} />同名规格参考最低
                                </span>
                              ) : p.price_diff != null ? (
                                <span className="text-xs text-orange-500">高于最低价 {fmtMoney(p.price_diff, p.currency)}</span>
                              ) : p.min_price != null ? (
                                <span className="text-xs text-gray-400">与最低价持平</span>
                              ) : (
                                <span className="text-xs text-gray-400">-</span>
                              )}
                            </td>
                            <td className="px-3 py-3 text-center">
                              {canReadCatalog&&<button className="text-blue-600 px-2" onClick={()=>setMappingProductId(p.id)}>SKU映射</button>}
                              {canReadCatalog&&<button className="text-xs text-indigo-600" onClick={()=>setQuoteProductId(p.id)}>阶梯报价</button>}
                              <button onClick={()=>deleteProduct(p.id)} className="text-red-400 hover:text-red-600 hover:bg-red-50 p-1.5 rounded transition-colors" title="停用产品，保留历史">
                                <Trash2 size={16} />
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </div>
            {/* Footer */}
            <div className="border-t px-5 py-3.5 bg-gray-50 rounded-b-2xl flex justify-between items-center">
              <div className="flex items-center gap-2 text-xs text-gray-400">
                <Tag size={12} /><span>同名规格、同币种及原单位参考；未映射不作为标准SKU可比</span>
              </div>
              <div className="flex gap-3">
                <button onClick={()=>openOrder(productSupplierId)} className="flex items-center gap-2 px-5 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors text-sm font-medium"><ShoppingCart size={16}/>下单</button>
                <button onClick={()=>setShowProducts(false)} className="btn-secondary text-sm px-6 py-2">关闭</button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Order Modal */}
      {showOrder && (
        <div className="modal-overlay z-50" onClick={()=>setShowOrder(false)}>
          <div className="bg-white rounded-2xl w-[800px] max-h-[85vh] overflow-auto shadow-2xl" onClick={e=>e.stopPropagation()}>
            <div className="bg-green-600 text-white px-5 py-3.5 rounded-t-2xl flex items-center gap-2 sticky top-0 z-10">
              <ShoppingCart size={18} />
              <h2 className="font-semibold">下单 - {data.find((s:any)=>s.id===orderSupplierId)?.name || ""}{(()=>{const s=data.find((x:any)=>x.id===orderSupplierId); return s?.settlement_cycle ? ` （账期: ${s.settlement_cycle}）` : "";})()}</h2>
              <button onClick={()=>setShowOrder(false)} className="ml-auto text-green-200 hover:text-white text-lg leading-none">&times;</button>
            </div>
            <div className="p-5">
              <div className="overflow-x-auto touch-pan-x">
              <table className="w-full text-sm min-w-[900px]">
                <thead>
                  <tr className="border-b bg-gray-50">
                    <th className="text-left px-3 py-3 font-medium text-gray-500 w-[5%]">选</th>
                    <th className="text-left px-3 py-3 font-medium text-gray-500 w-[25%]">产品名称</th>
                    <th className="text-left px-3 py-3 font-medium text-gray-500 w-[15%]">规格</th>
                    <th className="text-right px-3 py-3 font-medium text-gray-500 w-[12%]">单价</th>
                    <th className="text-center px-3 py-3 font-medium text-gray-500 w-[13%]">有效价对比</th>
                    <th className="text-center px-3 py-3 font-medium text-gray-500 w-[12%]">数量</th>
                    <th className="text-right px-3 py-3 font-medium text-gray-500 w-[18%]">小计</th>
                  </tr>
                </thead>
                <tbody>
                  {products.map((p:any) => {
                    const qty = orderItems[p.id] || 0;
                    const selected = qty > 0;
                    const hasPrice = (p.unit_price || 0) > 0||orderAvailableQuotes.some(q=>q.product_id===p.id);
                    const pricingRow=orderPricingCurrent?orderPricing.rows.find((r:any)=>r.product_id===p.id):null;
                    const shownPrice=pricingRow?.unit_price??(orderQuotes[p.id]?null:p.unit_price);
                    const subtotal=pricingRow?.subtotal??(orderQuotes[p.id]?null:(p.unit_price||0)*qty);
                    return (
                      <tr key={p.id} className={`border-b hover:bg-gray-50/50 transition-colors ${selected ? "bg-green-50/50" : ""} ${!hasPrice ? "opacity-50" : ""}`}>
                        <td className="px-3 py-3 text-center">
                          {hasPrice ? (
                            <button disabled={!!orderDraft?.unknown} onClick={()=>toggleOrderItem(p.id)}
                              className={`w-5 h-5 rounded border-2 flex items-center justify-center transition-colors ${
                                selected ? "bg-green-600 border-green-600 text-white" : "border-gray-300 hover:border-green-400"
                              }`}>
                              {selected && <CheckCircle size={12} />}
                            </button>
                          ) : (
                            <button disabled className="w-5 h-5 rounded border-2 border-gray-200 flex items-center justify-center cursor-not-allowed" title="未录入价格">
                              <span className="text-gray-300 text-xs">×</span>
                            </button>
                          )}
                        </td>
                        <td className="px-3 py-3 font-medium text-gray-800">{p.product_name}</td>
                        <td className="px-3 py-3 text-gray-500">{p.spec||"-"}</td>
                        <td className="px-3 py-3 text-right font-semibold text-gray-700">
                          {!hasPrice?<span className="text-red-500 text-xs">未录价格</span>:shownPrice===null?<span className="text-amber-600 text-xs">待核对报价</span>:Number(shownPrice)<=0?<span className="text-amber-600 text-xs">请选择有效报价</span>:fmtMoney(Number(shownPrice),p.currency)}
                        </td>
                        <td className="px-3 py-3 text-center">
                          <span className={pricingRow?.non_lowest?"text-xs text-amber-600":"text-xs text-gray-500"}>{pricingRow?.lowest_comparable_price!=null?(pricingRow.non_lowest?'非最低，需原因':'最低有效价 / 并列最低'):'无有效可比推荐'}</span>
                        </td>
                        <td className="px-3 py-3 text-center">
                          {selected ? (
                            <div className="flex items-center justify-center gap-1">
                              <button disabled={!!orderDraft?.unknown} onClick={()=>updateQuantity(p.id, qty-1)}
                                className="w-6 h-6 rounded border border-gray-300 hover:bg-gray-100 flex items-center justify-center text-sm">-</button>
                              <input aria-label={`采购数量 ${p.id}`} type="number" step="1" disabled={!!orderDraft?.unknown} value={qty} onChange={e=>updateQuantity(p.id, Number(e.target.value))}
                                className="w-14 text-center border rounded py-1 text-sm" min="1" />
                              <button disabled={!!orderDraft?.unknown} onClick={()=>updateQuantity(p.id, qty+1)}
                                className="w-6 h-6 rounded border border-gray-300 hover:bg-gray-100 flex items-center justify-center text-sm">+</button>
                            </div>
                          ) : (
                            <span className="text-gray-300">-</span>
                          )}
                        </td>
                        <td className="px-3 py-3 text-right font-semibold text-green-700">
                          {selected ? subtotal===null?'待核对':fmtMoney(Number(subtotal), p.currency) : "-"}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              </div>
              <PurchaseQuotePreview supplierId={orderSupplierId} products={products} quantities={orderItems} selections={orderQuotes} onSelect={(pid,qid)=>{priceReviewToken.current=null;setOrderPricing(null);setOrderQuotes(v=>({...v,[pid]:qid}));}} requirements={orderRequirements} onRequirements={v=>{priceReviewToken.current=null;setOrderRequirements(v);}} onPreview={setOrderPricing} onQuotes={setOrderAvailableQuotes} canRead={canReadCatalog} locked={!!orderDraft?.unknown}/>
              {pricingRejection&&<div role="alert" className="border border-amber-400 rounded p-3 my-3 text-sm"><p>{pricingRejection.message}</p><button className="btn-secondary" onClick={()=>{try{acceptQuotePreviewRejection(orderSupplierId,pricingRejection);setOrderDraft(registrationDraft("purchase_order",orderSupplierId));setOrderPricing(pricingRejection.preview);setPricingRejection(null);}catch(e:any){toast("error",e.message);}}}>服务器确认未创建，重新核对报价</button></div>}
              {Object.keys(orderItems).filter(k => orderItems[+k] > 0).length === 0 && (
                <div className="text-center py-8 text-gray-400 text-sm">请勾选需要采购的产品，并填写数量</div>
              )}
            </div>
            <div className="border-t px-5 py-4 bg-gray-50 rounded-b-2xl flex justify-between items-center">
              <div className="text-sm">
                已选 <span className="font-semibold text-green-600">{Object.keys(orderItems).filter(k => orderItems[+k] > 0).length}</span> 个产品，
                总价 <span className="font-semibold text-green-600 text-lg">{orderDraft?.unknown||(selectedOrderIds.some(id=>orderQuotes[id])&&!orderPricingCurrent)?"待核对":fmtMoney(orderTotal, orderCurrency)}</span>
              </div>
              <div className="flex gap-3">
                <button onClick={()=>setShowOrder(false)} className="btn-secondary text-sm px-5 py-2">取消</button>
                <button onClick={submitOrder} disabled={orderSubmitting || (!orderDraft?.unknown && orderTotal === 0)}
                  className={`flex items-center gap-2 px-5 py-2 rounded-lg text-sm font-medium transition-colors ${
                    !orderDraft?.unknown&&orderTotal === 0 ? "bg-gray-200 text-gray-400 cursor-not-allowed" : "bg-green-600 text-white hover:bg-green-700"
                  }`}>
                  <ShoppingCart size={16}/>{orderSubmitting ? "提交中..." : orderDraft?.unknown?"重试原采购请求":"确认下单"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Logistics Prices Modal */}
      {showLogistics && (
        <div className="modal-overlay" onClick={()=>setShowLogistics(false)}>
          <div className="bg-white rounded-xl p-6 w-[700px] max-h-[80vh] overflow-auto" onClick={e=>e.stopPropagation()}>
            <h2 className="font-semibold mb-4">跨境物流报价</h2>
            <div className="grid grid-cols-3 gap-2 mb-2 p-3 bg-gray-50 rounded">
              <select className="border rounded px-2 py-1.5 text-sm" value={logisticsForm.transport_method} onChange={e=>setLogisticsForm({...logisticsForm,transport_method:e.target.value})}>
                <option>陆运</option><option>海运</option>
              </select>
              <select className="border rounded px-2 py-1.5 text-sm" value={logisticsForm.cargo_type} onChange={e=>setLogisticsForm({...logisticsForm,cargo_type:e.target.value})}>
                <option>普货</option><option>商检货</option><option>敏感货</option>
              </select>
              <select className="border rounded px-2 py-1.5 text-sm" value={logisticsForm.origin_warehouse} onChange={e=>setLogisticsForm({...logisticsForm,origin_warehouse:e.target.value})}>
                <option>深圳仓</option><option>义乌仓</option><option>广州仓</option>
              </select>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-4 p-3 bg-gray-50 rounded">
              <div><label className="text-xs text-gray-500">单价(元/方)</label><input type="number" className="border rounded px-2 py-1.5 text-sm w-full" value={logisticsForm.price_per_cbm||""} onChange={e=>setLogisticsForm({...logisticsForm,price_per_cbm:e.target.value===""?"":+e.target.value})} /></div>
              <div><label className="text-xs text-gray-500">时效</label><input className="border rounded px-2 py-1.5 text-sm w-full" placeholder="如 5-7天" value={logisticsForm.estimated_days} onChange={e=>setLogisticsForm({...logisticsForm,estimated_days:e.target.value})} /></div>
              <div><label className="text-xs text-gray-500">币种</label><input className="border rounded px-2 py-1.5 text-sm w-full" value={logisticsForm.currency} onChange={e=>setLogisticsForm({...logisticsForm,currency:e.target.value})} /></div>
              <button onClick={addLogisticsPrice} disabled={!logisticsForm.price_per_cbm || !logisticsForm.estimated_days.trim()} className={`rounded px-2 py-1.5 text-sm self-end ${!logisticsForm.price_per_cbm || !logisticsForm.estimated_days.trim() ? "bg-gray-300 text-gray-500 cursor-not-allowed" : "bg-green-600 text-white"}`}>+添加</button>
            </div>
            {logisticsPrices.length === 0 ? <div className="text-gray-400 text-sm py-4 text-center">暂无报价</div> : (
              <div className="overflow-x-auto touch-pan-x">
              <table className="w-full text-sm min-w-[900px]"><thead><tr className="bg-gray-100"><th className="p-2 text-left">运输方式</th><th>货物类型</th><th>发货仓库</th><th>单价(元/方)</th><th>时效</th><th></th></tr></thead>
                <tbody>{logisticsPrices.map((p:any)=><tr key={p.id} className="border-t"><td className="p-2">{p.transport_method}</td><td>{p.cargo_type}</td><td>{p.origin_warehouse}</td><td>{p.price_per_cbm}</td><td>{p.estimated_days||"-"}</td>
                  <td><button onClick={()=>deleteLogisticsPrice(p.id)} className="text-red-500 text-xs"><Trash2 size={14}/></button></td></tr>)}</tbody></table>
              </div>
            )}
            <button onClick={()=>setShowLogistics(false)} className="mt-4 px-4 py-2 border rounded text-sm">关闭</button>
          </div></div>
      )}

      {/* Compare Modal */}
      {showCompare && (
        <div className="modal-overlay" onClick={()=>setShowCompare(false)}>
          <div className="bg-white rounded-xl p-6 w-[800px] max-h-[85vh] overflow-auto" onClick={e=>e.stopPropagation()}>
            <h2 className="font-semibold mb-4 flex items-center gap-2"><Scale size={20}/>供应商比价</h2>
            {/* Mode tabs */}
            <div className="flex gap-1 mb-4 bg-gray-100 rounded-lg p-1 w-fit">
              <button onClick={() => { setCompareMode("product"); setCompareData([]); setAiCompareResult(""); }}
                className={`px-4 py-1.5 rounded-md text-sm ${compareMode==="product"?"bg-white shadow font-medium":"text-gray-500"}`}>耗材比价</button>
              <button onClick={() => { setCompareMode("logistics"); setCompareData([]); setAiCompareResult(""); }}
                className={`px-4 py-1.5 rounded-md text-sm ${compareMode==="logistics"?"bg-white shadow font-medium":"text-gray-500"}`}>物流比价</button>
            </div>

            {compareMode === "product" ? (
              <div className="flex gap-2 mb-4 flex-wrap">
                <input className="border rounded px-3 py-2 text-sm flex-1 min-w-[150px]" placeholder="产品名称" value={compareProduct} onChange={e=>setCompareProduct(e.target.value)} />
                <input className="border rounded px-3 py-2 text-sm flex-1 min-w-[150px]" placeholder="规格（可选）" value={compareSpec} onChange={e=>setCompareSpec(e.target.value)} />
                <select className="border rounded px-3 py-2 text-sm" value={compareCat} onChange={e=>setCompareCat(+e.target.value)}>
                  <option value={0}>全部类别</option>
                  {categories.map((c:any)=><option key={c.id} value={c.id}>{c.name}</option>)}
                </select>
                <button onClick={()=>doCompare("product")} className="btn-primary">查询</button>
              </div>
            ) : (
              <div className="flex gap-2 mb-4 flex-wrap">
                <select className="border rounded px-3 py-2 text-sm" value={compareTransport} onChange={e=>setCompareTransport(e.target.value)}>
                  <option>陆运</option><option>海运</option>
                </select>
                <select className="border rounded px-3 py-2 text-sm" value={compareCargo} onChange={e=>setCompareCargo(e.target.value)}>
                  <option>普货</option><option>商检货</option><option>敏感货</option>
                </select>
                <select className="border rounded px-3 py-2 text-sm" value={compareWarehouse} onChange={e=>setCompareWarehouse(e.target.value)}>
                  <option>深圳仓</option><option>义乌仓</option><option>广州仓</option>
                </select>
                <button onClick={()=>doCompare("logistics")} className="btn-primary">查询</button>
              </div>
            )}

            {compareData.length === 0 ? <div className="text-gray-400 text-sm py-4 text-center">请填写查询条件</div> : (
              <>
                {compareMode === "product" ? (
                  <div className="overflow-x-auto touch-pan-x">
                  <table className="w-full text-sm mb-4 min-w-[900px]"><thead><tr className="bg-gray-100"><th className="p-2 text-left">排名</th><th>供应商</th><th>类别</th><th>产品</th><th>规格</th><th>规格报价</th><th>单价</th></tr></thead>
                    <tbody>{compareData.map((r:any,i:number)=><tr key={i} className={`border-t ${i===0?"bg-green-50":""}`}>
                      <td className="p-2 font-bold">{i+1}</td><td>{r.supplier_name}</td><td>{r.category_name||"-"}</td><td>{r.product_name}</td><td>{r.spec||"-"}</td>
                      <td className="text-sm">{r.spec_price != null ? r.spec_price + (r.unit||"") : "-"}</td>
                      <td className="font-semibold text-green-700">{r.unit_price}{r.unit}</td></tr>)}</tbody></table>
                  </div>
                ) : (
                  <div className="overflow-x-auto touch-pan-x">
                  <table className="w-full text-sm mb-4 min-w-[900px]"><thead><tr className="bg-gray-100"><th className="p-2 text-left">排名</th><th>供应商</th><th>运输</th><th>货物</th><th>发货仓</th><th>单价(元/方)</th><th>最低消费</th><th>时效</th><th>备注</th></tr></thead>
                    <tbody>{compareData.map((r:any,i:number)=><tr key={i} className={`border-t ${i===0?"bg-green-50":""}`}>
                      <td className="p-2 font-bold">{i+1}</td><td>{r.supplier_name}</td><td>{r.transport_method}</td><td>{r.cargo_type}</td>
                      <td>{r.origin_warehouse}</td><td className="font-semibold text-green-700">{r.price_per_cbm}</td>
                      <td className="text-xs">{r.min_cbm}方起 / {fmtMoney(r.min_amount, r.currency)}</td><td>{r.estimated_days||"-"}</td>
                      <td className="text-xs text-orange-600">{r.price_note}{r.heavy_cargo_warning&&<><br/>{r.heavy_cargo_warning}</>}</td></tr>)}</tbody></table>
                  </div>
                )}
                <button onClick={doAiCompare} className="bg-purple-600 text-white px-4 py-2 rounded text-sm flex items-center gap-1 mb-4"><Sparkles size={16}/>AI比价分析</button>
                {aiCompareResult && <div className="bg-purple-50 rounded-lg p-4 text-sm whitespace-pre-wrap">{aiCompareResult}</div>}
              </>
            )}
            <button onClick={()=>setShowCompare(false)} className="mt-4 px-4 py-2 border rounded text-sm">关闭</button>
          </div></div>
      )}

      {/* Detail Modal */}
      {detail && (
        <div className="modal-overlay" onClick={()=>setDetail(null)}>
          <div className="bg-white rounded-xl w-[700px] max-h-[85vh] overflow-auto" onClick={e=>e.stopPropagation()}>
            {/* Header - Blue Bar */}
            <div className="sticky top-0 bg-blue-600 text-white px-5 py-3.5 rounded-t-xl flex items-center justify-between z-10">
              <div className="flex items-center gap-3">
                <User size={18} />
                <h2 className="text-lg font-semibold">{detail.name}</h2>
                {detail.category_name && (
                  <span className={`inline-block px-2.5 py-0.5 rounded-full text-xs font-medium ${detail.category_name==="耗材商"?"bg-blue-200 text-blue-800":"bg-green-200 text-green-800"}`}>
                    {detail.category_name}
                  </span>
                )}
              </div>
              <button onClick={()=>setDetail(null)} className="text-blue-200 hover:text-white text-xl leading-none">&times;</button>
            </div>

            <div className="p-6 space-y-5">
              {/* 第一块：基本信息 */}
              <div className="bg-gray-50 rounded-xl p-5">
                <h3 className="font-semibold text-sm text-gray-500 mb-3 uppercase tracking-wide">基本信息</h3>
                <div className="grid grid-cols-2 gap-x-8 gap-y-3 text-sm">
                  <div className="flex items-center gap-2">
                    <User size={15} className="text-gray-400 flex-shrink-0"/>
                    <div><span className="text-gray-400 text-xs">联系人</span><div className="font-medium">{detail.contact_person||"-"}</div></div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Phone size={15} className="text-gray-400 flex-shrink-0"/>
                    <div><span className="text-gray-400 text-xs">联系方式</span><div className="font-medium">{detail.contact_info||"-"}</div></div>
                  </div>
                  <div className="flex items-start gap-2 col-span-2">
                    <MapPin size={15} className="text-gray-400 flex-shrink-0 mt-0.5"/>
                    <div><span className="text-gray-400 text-xs">地址</span><div className="font-medium">{detail.address||"-"}</div></div>
                  </div>
                </div>
              </div>

              {/* 第二块：合作信息 */}
              <div className="bg-gray-50 rounded-xl p-5">
                <h3 className="font-semibold text-sm text-gray-500 mb-3 uppercase tracking-wide">合作信息</h3>
                <div className="grid grid-cols-2 gap-x-8 gap-y-3 text-sm">
                  <div className="flex items-center gap-2">
                    <FileText size={15} className="text-gray-400 flex-shrink-0"/>
                    <div><span className="text-gray-400 text-xs">合作内容</span><div className="font-medium">{detail.cooperation_content||"-"}</div></div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Calendar size={15} className="text-gray-400 flex-shrink-0"/>
                    <div><span className="text-gray-400 text-xs">结算周期</span><div className="font-medium">{detail.settlement_cycle||"-"}</div></div>
                  </div>
                  <div className="flex items-center gap-2 col-span-2">
                    <DollarSign size={15} className="text-gray-400 flex-shrink-0"/>
                    <div><span className="text-gray-400 text-xs">付款条件</span><div className="font-medium">{detail.payment_terms||"-"}</div></div>
                  </div>
                </div>
              </div>

              {/* 第三块：产品（仅耗材商） */}
              {detail.category_id === 1 && (
                <div className="bg-gray-50 rounded-xl p-5">
                  <h3 className="font-semibold text-sm text-gray-500 mb-3 uppercase tracking-wide flex items-center gap-2">
                    <Package size={15} className="text-blue-500"/>产品与价格
                  </h3>
                  {(!detail.products || detail.products.length === 0) ? (
                    <div className="text-gray-400 text-sm py-3 text-center">暂无产品</div>
                  ) : (
                    <div className="overflow-x-auto touch-pan-x">
                    <table className="w-full text-sm min-w-[700px]">
                      <thead><tr className="border-b text-gray-500 text-xs"><th className="text-left pb-2 font-medium">产品名</th><th className="text-left pb-2 font-medium">产品规格</th><th className="text-right pb-2 font-medium">规格报价</th><th className="text-right pb-2 font-medium">单价</th></tr></thead>
                      <tbody>{detail.products.map((p:any)=><tr key={p.id} className="border-b border-gray-100">
                        <td className="py-2">{p.product_name}</td><td className="py-2 text-gray-500">{p.spec||"-"}</td>
                        <td className="py-2 text-right">{p.spec_price != null ? p.spec_price : "-"}</td><td className="py-2 text-right font-medium">{p.unit_price}</td>
                      </tr>)}</tbody></table>
                    </div>
                  )}
                </div>
              )}

              {/* 第四块：物流报价（仅物流商） */}
              {detail.category_id === 2 && (
                <div className="bg-gray-50 rounded-xl p-5">
                  <h3 className="font-semibold text-sm text-gray-500 mb-3 uppercase tracking-wide flex items-center gap-2">
                    <Truck size={15} className="text-orange-500"/>物流报价
                  </h3>
                  {(!detail.logistics_prices || detail.logistics_prices.length === 0) ? (
                    <div className="text-gray-400 text-sm py-3 text-center">暂无报价</div>
                  ) : (
                    <div className="overflow-x-auto touch-pan-x">
                    <table className="w-full text-sm min-w-[700px]">
                      <thead><tr className="border-b text-gray-500 text-xs"><th className="text-left pb-2 font-medium">运输方式</th><th className="text-left pb-2 font-medium">货物类型</th><th className="text-left pb-2 font-medium">发货仓库</th><th className="text-right pb-2 font-medium">单价(元/方)</th><th className="text-right pb-2 font-medium">时效</th></tr></thead>
                      <tbody>{detail.logistics_prices.map((p:any)=><tr key={p.id} className="border-b border-gray-100">
                        <td className="py-2">{p.transport_method}</td><td className="py-2 text-gray-500">{p.cargo_type}</td>
                        <td className="py-2 text-gray-500">{p.origin_warehouse}</td><td className="py-2 text-right font-medium">{p.price_per_cbm}</td>
                        <td className="py-2 text-right text-gray-500">{p.estimated_days||"-"}</td>
                      </tr>)}</tbody></table>
                    </div>
                  )}
                </div>
              )}

              {/* 底部操作 */}
              <div className="flex justify-end pt-2">
                <button onClick={()=>setDetail(null)} className="px-5 py-2 border rounded-lg text-sm hover:bg-gray-50">关闭</button>
              </div>
            </div>
          </div></div>
      )}

      {/* Procurement Modal */}
      {showProcurement && (
        <div className="modal-overlay" onClick={()=>setShowProcurement(false)}>
          <div className="bg-white rounded-xl w-[92vw] max-w-6xl max-h-[90vh] overflow-auto p-6" onClick={e=>e.stopPropagation()}>
            <div className="flex justify-between items-center mb-6">
              <h2 className="text-xl font-bold">采购汇总报表</h2>
              <button onClick={()=>setShowProcurement(false)} className="px-4 py-2 border rounded-lg text-sm hover:bg-gray-50">关闭</button>
            </div>

            {/* 顶部总览卡片 */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
              <div className="bg-gradient-to-br from-blue-500 to-blue-600 text-white rounded-xl p-5 shadow">
                <div className="text-sm opacity-80 mb-1">本月采购总支出</div>
                <div className="text-2xl font-bold">{fmtMoneyByCurrency(procurement?.overview?.month_total_by_currency)}</div>
              </div>
              {Object.entries(procurement?.overview?.cat_spending || {}).map(([cat, amt]: [string, any]) => (
                <div key={cat} className={`rounded-xl p-5 shadow text-white ${cat==="耗材商" ? "bg-gradient-to-br from-emerald-500 to-emerald-600" : "bg-gradient-to-br from-orange-500 to-orange-600"}`}>
                  <div className="text-sm opacity-80 mb-1">{cat}采购</div>
                  <div className="text-2xl font-bold">{fmtMoneyByCurrency(amt)}</div>
                </div>
              ))}
            </div>

            {/* 主体两栏 */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* 左侧：供应商排名 */}
              <div>
                <h3 className="font-semibold mb-3 text-base flex items-center gap-2"><BarChart3 size={18} className="text-blue-500"/>供应商支出排名</h3>
                <div className="space-y-2 max-h-[400px] overflow-auto">
                  {(procurement?.supplier_ranking || []).length === 0 ? <div className="text-gray-400 text-sm py-4">暂无支出数据</div> :
                    (procurement?.supplier_ranking || []).map((r: any, i: number) => (
                      <div key={r.supplier_id} className="flex items-center gap-3 p-3 bg-gray-50 rounded-lg">
                        <div className={`w-8 h-8 rounded-full flex items-center justify-center text-white text-sm font-bold ${i===0 ? "bg-yellow-500" : i===1 ? "bg-gray-400" : i===2 ? "bg-amber-700" : "bg-gray-300 text-gray-600"}`}>{i+1}</div>
                        <div className="flex-1 min-w-0">
                          <div className="font-medium text-sm truncate">{r.supplier_name}</div>
                          <div className="text-xs text-gray-400">{r.category_name} · 最近采购 {r.last_bill_date || "-"}</div>
                        </div>
                        <div className="text-right">
                          <div className="font-semibold text-sm">{fmtMoneyByCurrency(r.month_amount_by_currency)}</div>
                          <div className="text-xs text-gray-400">累计 {fmtMoneyByCurrency(r.total_amount_by_currency)}</div>
                        </div>
                      </div>
                    ))}
                </div>
              </div>

              {/* 右侧：产品比价汇总 + 省钱提示 */}
              <div>
                <h3 className="font-semibold mb-3 text-base flex items-center gap-2"><DollarSign size={18} className="text-green-500"/>产品比价一览</h3>
                <div className="space-y-2 max-h-[200px] overflow-auto mb-4">
                  {(procurement?.product_compare || []).length === 0 ? <div className="text-gray-400 text-sm py-4">暂无产品数据</div> :
                    (procurement?.product_compare || []).map((p: any) => (
                      <div key={p.product_name + p.spec + p.currency} className="flex items-center gap-3 p-3 bg-gray-50 rounded-lg text-sm">
                        <div className="flex-1">
                          <span className="font-medium">{p.product_name}</span>
                          <span className="text-gray-400 ml-1">{p.spec || ""}</span>
                          <span className="text-xs text-gray-400 ml-2">{p.supplier_count}家供应商</span>
                        </div>
                        <div className="text-right text-xs">
                          <div>最低 <span className="text-green-600 font-semibold">{fmtMoney(p.min_price, p.currency)}</span> <span className="text-gray-400">({p.min_supplier})</span></div>
                          <div>最高 <span className="text-red-500">{fmtMoney(p.max_price, p.currency)}</span></div>
                        </div>
                      </div>
                    ))}
                </div>

                {/* 省钱提示 */}
                {(procurement?.savings_tips || []).length > 0 && (
                  <>
                    <h3 className="font-semibold mb-3 text-base flex items-center gap-2"><Lightbulb size={18} className="text-amber-500"/>省钱建议</h3>
                    <div className="space-y-2 max-h-[180px] overflow-auto">
                      {(procurement?.savings_tips || []).map((t: any, i: number) => (
                        <div key={i} className="p-3 bg-amber-50 border border-amber-200 rounded-lg text-sm">
                          <div className="flex items-start gap-2">
                            <Lightbulb size={16} className="text-amber-500 mt-0.5 flex-shrink-0"/>
                            <div>
                              <span className="font-medium">{t.product_name}{t.spec ? ` (${t.spec})` : ""}</span>
                              <span className="text-gray-600 ml-1">当前最便宜 <span className="text-green-600 font-semibold">{t.cheapest_supplier} {fmtMoney(t.cheapest_price, t.currency)}</span></span>
                              <div className="text-xs text-gray-500 mt-1">比最贵供应商省 {fmtMoney(t.savings_per_unit, t.currency)}/件</div>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </>
                )}
              </div>
            </div>
          </div></div>
      )}

      {/* 价格监控 */}
      {showPriceMonitor && (
        <div className="modal-overlay z-50" onClick={() => setShowPriceMonitor(false)}>
          <div className="bg-white rounded-xl w-[760px] max-w-[95vw] max-h-[85vh] overflow-auto" onClick={e => e.stopPropagation()}>
            <div className="bg-indigo-600 text-white px-5 py-3 rounded-t-xl flex items-center gap-2 sticky top-0 z-10">
              <BarChart3 size={20} />
              <h2 className="font-semibold">价格监控</h2>
              <span className="text-xs text-indigo-200 ml-2">偏高阈值 {priceThreshold}%</span>
              <button onClick={() => setShowPriceMonitor(false)} className="ml-auto text-indigo-200 hover:text-white text-xl">&times;</button>
            </div>
            <div className="p-5 space-y-5">
              {/* 价格异常列表 */}
              <div>
                <h3 className="font-semibold mb-2 text-sm text-red-600">价格异常记录</h3>
                {priceAnomalies.length === 0 ? (
                  <div className="text-gray-400 text-sm py-4 text-center">暂无价格异常</div>
                ) : (
                  <div className="overflow-x-auto touch-pan-x">
                    <table className="w-full text-sm min-w-[900px]">
                      <thead><tr className="border-b bg-gray-50 text-left text-gray-500">
                        <th className="px-3 py-2 font-medium">产品</th><th className="px-3 py-2 font-medium text-right">采购价</th>
                        <th className="px-3 py-2 font-medium text-right">历史均价</th><th className="px-3 py-2 font-medium text-right">高出</th>
                        <th className="px-3 py-2 font-medium">下单人</th><th className="px-3 py-2 font-medium">时间</th>
                      </tr></thead>
                      <tbody>
                        {priceAnomalies.map((a: any) => (
                          <tr key={a.id} className="border-b">
                            <td className="px-3 py-2">{a.product_name}{a.spec ? <span className="text-gray-400 text-xs">（{a.spec}）</span> : null}</td>
                            <td className="px-3 py-2 text-right font-mono">{a.purchase_price}</td>
                            <td className="px-3 py-2 text-right font-mono">{a.historical_avg}</td>
                            <td className="px-3 py-2 text-right text-red-600 font-semibold">+{a.exceed_percent}%</td>
                            <td className="px-3 py-2">{a.orderer_name || "-"}</td>
                            <td className="px-3 py-2 text-gray-500 text-xs">{a.created_at ? new Date(a.created_at).toLocaleString("zh-CN", { timeZone: "Asia/Bangkok" }) : "-"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>

              {/* 非最低价采购列表 */}
              <div>
                <h3 className="font-semibold mb-2 text-sm text-amber-600">
                  非最低价采购
                  {nonLowestSummary && (
                    <span className="ml-2 text-xs font-normal text-gray-500">
                      本期多花 <span className="text-red-600 font-semibold">{nonLowestSummary.total_extra_amount ?? 0}</span>（{nonLowestSummary.count ?? 0} 条记录）
                    </span>
                  )}
                </h3>
                {nonLowestRecords.length === 0 ? (
                  <div className="text-gray-400 text-sm py-4 text-center">暂无非最低价采购</div>
                ) : (
                  <div className="overflow-x-auto touch-pan-x">
                    <table className="w-full text-sm min-w-[900px]">
                      <thead><tr className="border-b bg-gray-50 text-left text-gray-500">
                        <th className="px-3 py-2 font-medium">产品</th><th className="px-3 py-2 font-medium">所选供应商/价格</th>
                        <th className="px-3 py-2 font-medium">最低供应商/价格</th><th className="px-3 py-2 font-medium text-right">差价</th>
                        <th className="px-3 py-2 font-medium">原因</th><th className="px-3 py-2 font-medium">下单人</th><th className="px-3 py-2 font-medium">时间</th>
                      </tr></thead>
                      <tbody>
                        {nonLowestRecords.map((r: any) => (
                          <tr key={r.id} className="border-b">
                            <td className="px-3 py-2">{r.product_name}{r.spec ? <span className="text-gray-400 text-xs">（{r.spec}）</span> : null}</td>
                            <td className="px-3 py-2">{r.selected_supplier_name || "-"} <span className="font-mono text-gray-500">{r.selected_price}</span></td>
                            <td className="px-3 py-2">{r.lowest_supplier_name || "-"} <span className="font-mono text-green-600">{r.lowest_price}</span></td>
                            <td className="px-3 py-2 text-right text-amber-600 font-semibold">{r.price_diff}</td>
                            <td className="px-3 py-2">{r.reason || "-"}</td>
                            <td className="px-3 py-2">{r.orderer_name || "-"}</td>
                            <td className="px-3 py-2 text-gray-500 text-xs">{r.created_at ? new Date(r.created_at).toLocaleString("zh-CN", { timeZone: "Asia/Bangkok" }) : "-"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>

              {/* 产品价格统计 + 趋势 */}
              <div>
                <h3 className="font-semibold mb-2 text-sm text-gray-700">产品价格统计（点击看趋势）</h3>
                {priceStats.length === 0 ? (
                  <div className="text-gray-400 text-sm py-4 text-center">暂无采购记录</div>
                ) : (
                  <div className="overflow-x-auto touch-pan-x">
                    <table className="w-full text-sm min-w-[700px]">
                      <thead><tr className="border-b bg-gray-50 text-left text-gray-500">
                        <th className="px-3 py-2 font-medium">产品</th><th className="px-3 py-2 font-medium text-right">历史最低</th>
                        <th className="px-3 py-2 font-medium text-right">历史均价</th><th className="px-3 py-2 font-medium text-right">最近采购</th>
                        <th className="px-3 py-2 font-medium text-right">次数</th>
                      </tr></thead>
                      <tbody>
                        {priceStats.map((p: any) => (
                          <tr key={p.product_name + (p.spec || "")} className="border-b cursor-pointer hover:bg-indigo-50/40" onClick={() => loadPriceTrend(p.product_name, p.spec)}>
                            <td className="px-3 py-2">{p.product_name}{p.spec ? <span className="text-gray-400 text-xs">（{p.spec}）</span> : null}</td>
                            <td className="px-3 py-2 text-right font-mono text-green-600">{p.lowest}</td>
                            <td className="px-3 py-2 text-right font-mono">{p.avg}</td>
                            <td className="px-3 py-2 text-right font-mono">{p.last}</td>
                            <td className="px-3 py-2 text-right text-gray-500">{p.count}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>

              {/* 趋势 */}
              {trendProduct && (
                <div>
                  <h3 className="font-semibold mb-2 text-sm text-gray-700">价格趋势 · {trendProduct.product_name}{trendProduct.spec ? `（${trendProduct.spec}）` : ""}</h3>
                  {priceTrend.length === 0 ? (
                    <div className="text-gray-400 text-sm py-3 text-center">暂无价格记录</div>
                  ) : (
                    <div className="space-y-1">
                      {priceTrend.map((t: any, i: number) => (
                        <div key={t.id} className="flex items-center gap-3 text-sm">
                          <span className="text-gray-400 text-xs w-5">{i + 1}</span>
                          <span className="font-mono">{t.unit_price}</span>
                          <span className="text-gray-400 text-xs">x{t.quantity}</span>
                          <span className="text-gray-500 text-xs ml-auto">{t.created_at ? new Date(t.created_at).toLocaleString("zh-CN", { timeZone: "Asia/Bangkok" }) : "-"}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
            <div className="border-t px-5 py-3 text-center">
              <button onClick={() => setShowPriceMonitor(false)} className="text-sm text-gray-400">关闭</button>
            </div>
          </div>
        </div>
      )}

      {/* 采购审批弹窗 */}
      {showApprovals && (
        <div className="modal-overlay z-[60]" onClick={() => setShowApprovals(false)}>
          <div className="bg-white rounded-xl w-[820px] max-w-[95vw] max-h-[85vh] overflow-auto" onClick={e => e.stopPropagation()}>
            <div className="bg-blue-600 text-white px-5 py-3 rounded-t-xl flex items-center gap-2 sticky top-0 z-10">
              <CheckCircle size={20} />
              <h2 className="font-semibold">采购审批</h2>
              <span className="text-xs text-blue-200 ml-2">门槛 {approvalThreshold} 泰铢</span>
              <button onClick={() => setShowApprovals(false)} className="ml-auto text-blue-200 hover:text-white text-xl">&times;</button>
            </div>
            <div className="p-5 space-y-5">
              {/* 门槛只读（去配置中心修改） */}
              <div className="flex items-center gap-2 text-sm text-gray-600">
                <span>审批门槛（泰铢）：{approvalThreshold}</span>
                <span className="text-xs text-gray-400">去配置中心修改</span>
              </div>

              {/* 疑似拆单 */}
              {splitGroups.length > 0 && (
                <div>
                  <h3 className="font-semibold mb-2 text-sm text-red-600">疑似拆单</h3>
                  {splitGroups.map((g: any, i: number) => (
                    <div key={i} className="bg-red-50 border border-red-200 rounded-lg p-3 mb-2 text-sm">
                      <div className="font-medium text-red-700">
                        {g.date} · {g.supplier_name || "-"} · {g.orderer_name || "-"} · {g.order_count} 笔合计 {g.total_amount} 泰铢
                      </div>
                      <div className="text-xs text-red-500 mt-1">
                        {g.orders.map((o: any) => `${o.order_number}(${o.total_amount})`).join("、")} 每笔未超门槛，合计已超门槛
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {/* 待审批 */}
              <div>
                <h3 className="font-semibold mb-2 text-sm text-gray-700">待审批采购单</h3>
                {pendingOrders.length === 0 ? (
                  <div className="text-gray-400 text-sm py-4 text-center">暂无待审批采购单</div>
                ) : (
                  <div className="space-y-3">
                    {pendingOrders.map((po: any) => (
                      <div key={po.id} className="border rounded-lg p-3">
                        <div className="flex items-center justify-between text-sm">
                          <div>
                            <span className="font-medium">{po.order_number}</span>
                            <span className="text-gray-500 ml-2">{po.supplier_name}</span>
                            <span className="text-gray-400 ml-2">下单人 {po.orderer_name || "-"}</span>
                            <span className="text-gray-400 ml-2">{po.created_at ? new Date(po.created_at).toLocaleString("zh-CN", { timeZone: "Asia/Bangkok" }) : "-"}</span>
                          </div>
                          <div className="font-semibold text-gray-800">{po.total_amount} 泰铢</div>
                        </div>
                        <div className="mt-2 text-xs text-gray-600 space-y-0.5">
                          {(po.items || []).map((it: any, i: number) => (
                            <div key={i}>{it.product_name}{it.spec ? `（${it.spec}）` : ""} ×{it.quantity} @ {it.unit_price} = {it.subtotal}</div>
                          ))}
                        </div>
                        <div className="flex gap-2 mt-2">
                          <button onClick={() => approveOrder(po.id)} className="px-3 py-1 bg-green-600 text-white rounded text-xs">通过</button>
                          <button onClick={() => startDuty(po,"reject")} className="px-3 py-1 bg-red-500 text-white rounded text-xs">驳回</button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {dutyDialog?.action==='approve'&&<div className="modal-overlay z-[70]" onClick={()=>!dutyBusy&&setDutyDialog(null)}>
        <div role="dialog" aria-label="采购审批职责确认" className="bg-white rounded-xl p-5 w-[480px] max-w-[95vw] max-h-[85vh] overflow-auto" onClick={e=>e.stopPropagation()}>
          <h3 className="font-semibold mb-3">采购审批职责确认 · PO #{dutyDialog.po.id}</h3>
          <ProcurementDutyFields value={dutyDialog} onChange={setDutyDialog} onRefresh={()=>startDuty(dutyDialog.po,'approve')}/>
          <div className="flex gap-3 justify-end mt-4"><button onClick={()=>setDutyDialog(null)} disabled={dutyBusy} className="btn-secondary">取消</button><button disabled={dutyBusy} onClick={confirmApprove} className="btn-primary">{dutyBusy?'提交中...':'确认通过'}</button></div>
        </div>
      </div>}
      {/* 驳回原因弹窗 */}
      {rejectTarget && (
        <div className="modal-overlay z-[70]" onClick={() => setRejectTarget(null)}>
          <div className="bg-white rounded-xl w-[420px] max-w-[95vw] max-h-[85vh] overflow-auto p-5" onClick={e => e.stopPropagation()}>
            <h3 className="font-semibold mb-3">驳回采购单 {rejectTarget.order_number}</h3>
            <ProcurementDutyFields value={dutyDialog} onChange={setDutyDialog} onRefresh={()=>startDuty(rejectTarget,'reject')}/>
            <textarea value={rejectReason} disabled={dutyDialog?.locked} onChange={e => setRejectReason(e.target.value)}
              className="w-full border rounded px-3 py-2 text-sm" rows={3} placeholder="填写驳回原因" />
            <div className="flex justify-end gap-3 mt-4">
              <button onClick={() => setRejectTarget(null)} className="px-4 py-2 border rounded text-sm">取消</button>
              <button onClick={confirmReject} disabled={dutyBusy} className="px-4 py-2 bg-red-500 text-white rounded text-sm">确认驳回</button>
            </div>
          </div>
        </div>
      )}

      {/* 非最低价原因弹窗 */}
      {showReasonDialog && (
        <div className="modal-overlay z-[60]" onClick={() => setShowReasonDialog(false)}>
          <div className="bg-white rounded-xl w-[560px] max-w-[95vw] max-h-[85vh] overflow-auto" onClick={e => e.stopPropagation()}>
            <div className="bg-amber-500 text-white px-5 py-3 rounded-t-xl flex items-center gap-2 sticky top-0 z-10">
              <AlertCircle size={20} />
              <h2 className="font-semibold">非最低价采购原因</h2>
              <button onClick={() => setShowReasonDialog(false)} className="ml-auto text-amber-100 hover:text-white text-xl">&times;</button>
            </div>
            <div className="p-5 space-y-4">
              <p className="text-sm text-gray-600">以下产品所选价格高于该产品最低报价，需填写采购原因后才能提交。</p>
              {reasonItems.map((item: any) => (
                <div key={item.product_id} className="border rounded-lg p-3">
                  <div className="flex items-center justify-between text-sm">
                    <span className="font-medium">{item.product_name}{item.spec ? `（${item.spec}）` : ""}</span>
                    <span className="text-xs text-amber-600">采购价 {item.unit_price} · 最低 {item.lowest_price}（{item.lowest_supplier_name}）· 差价 {item.price_diff}</span>
                  </div>
                  <div className="flex flex-wrap gap-1.5 mt-2">
                    {QUICK_REASONS.map(q => (
                      <button key={q} onClick={() => setReasonMap(prev => ({ ...prev, [item.product_id]: q }))}
                        className={`px-2.5 py-1 rounded-full text-xs border ${reasonMap[item.product_id] === q ? "bg-amber-500 text-white border-amber-500" : "bg-white text-gray-600 border-gray-200 hover:border-amber-300"}`}>
                        {q}
                      </button>
                    ))}
                  </div>
                  <input value={reasonMap[item.product_id] || ""} onChange={e => setReasonMap(prev => ({ ...prev, [item.product_id]: e.target.value }))}
                    className="w-full border rounded px-3 py-2 text-sm mt-2" placeholder="填写采购原因" />
                </div>
              ))}
            </div>
            <div className="border-t px-5 py-3 flex justify-end gap-3">
              <button onClick={() => setShowReasonDialog(false)} className="px-4 py-2 border rounded text-sm">取消</button>
              <button onClick={confirmReasonSubmit} className="px-4 py-2 bg-amber-500 text-white rounded text-sm">确认提交</button>
            </div>
          </div>
        </div>
      )}

      {/* Create Supplier Form */}
      {showForm && (
        <div className="modal-overlay" onClick={()=>setShowForm(false)}>
          <div className="bg-white rounded-xl p-6 w-[500px] max-h-[85vh] overflow-auto" onClick={e=>e.stopPropagation()}>
            <h2 className="font-semibold mb-4">新建供应商</h2>
            <div className="grid grid-cols-2 gap-3">
              <div><label className="form-label">名称</label><input className="form-input" value={form.name} onChange={e=>setForm({...form,name:e.target.value})} /></div>

              <div><label className="form-label">联系人</label><input className="form-input" value={form.contact_person} onChange={e=>setForm({...form,contact_person:e.target.value})} /></div>
              <div><label className="form-label">联系方式</label><input className="form-input" value={form.contact_info} onChange={e=>setForm({...form,contact_info:e.target.value})} /></div>
              <div><label className="form-label">地址</label><input className="form-input" value={form.address} onChange={e=>setForm({...form,address:e.target.value})} /></div>
              <div><label className="form-label">付款条件</label><input className="form-input" value={form.payment_terms} onChange={e=>setForm({...form,payment_terms:e.target.value})} /></div>
              <div><label className="form-label">结算周期</label><input className="form-input" value={form.settlement_cycle} onChange={e=>setForm({...form,settlement_cycle:e.target.value})} placeholder="如: 月结30天" /></div>
              <div><label className="form-label">默认币种</label>
                <select className="form-input" value={form.default_currency} onChange={e=>setForm({...form,default_currency:e.target.value})}>
                  <option value="THB">泰铢 (฿)</option>
                  <option value="CNY">人民币 (¥)</option>
                </select>
              </div>
            </div>
            <div className="mt-3"><label className="form-label">合作内容</label><textarea className="form-input" rows={2} value={form.cooperation_content} onChange={e=>setForm({...form,cooperation_content:e.target.value})} /></div>

            <div className="flex justify-end gap-3 mt-6"><button onClick={()=>setShowForm(false)} className="px-4 py-2 border rounded">取消</button><button onClick={handleCreate} className="px-4 py-2 bg-primary text-white rounded">保存</button></div>
          </div></div>
      )}

      {/* 收货验收弹窗 */}
      {showReceipt && (
        <div className="modal-overlay z-50" onClick={() => setShowReceipt(false)}>
          <div className="bg-white rounded-xl w-[880px] max-w-[95vw] max-h-[85vh] overflow-auto" onClick={e => e.stopPropagation()}>
            <div className="bg-green-600 text-white px-5 py-3 rounded-t-xl flex items-center gap-2 sticky top-0 z-10">
              <Package size={20} />
              <h2 className="font-semibold">采购收货验收</h2>
              <button onClick={() => setShowReceipt(false)} className="ml-auto text-green-200 hover:text-white text-xl">&times;</button>
            </div>
            <div className="p-5">
              {receiptOrders.length === 0 ? (
                <div className="text-gray-400 text-sm py-8 text-center">暂无采购单</div>
              ) : (
                <div className="overflow-x-auto touch-pan-x">
                <table className="w-full text-sm min-w-[900px]">
                  <thead><tr className="border-b bg-gray-50 text-left text-gray-500">
                    <th className="px-3 py-2 font-medium">单号</th>
                    <th className="px-3 py-2 font-medium">供应商</th>
                    <th className="px-3 py-2 font-medium text-right">金额</th>
                    <th className="px-3 py-2 font-medium">状态</th>
                    <th className="px-3 py-2 font-medium">收货状态</th>
                    <th className="px-3 py-2 font-medium text-center">操作</th>
                  </tr></thead>
                  <tbody>
                    {receiptOrders.map((po: any) => (
                      <tr key={po.id} className="border-b">
                        <td className="px-3 py-2 font-medium">{po.order_number}</td>
                        <td className="px-3 py-2">{po.supplier_name || "-"}</td>
                        <td className="px-3 py-2 text-right font-mono">{po.total_amount}</td>
                        <td className="px-3 py-2">
                          {po.status === "pending" ? <span className="text-xs px-2 py-0.5 rounded bg-yellow-100 text-yellow-700">待审批</span>
                            : po.status === "confirmed" ? <span className="text-xs px-2 py-0.5 rounded bg-blue-100 text-blue-700">已生效</span>
                            : <span className="text-xs px-2 py-0.5 rounded bg-red-100 text-red-700">已驳回</span>}
                        </td>
                        <td className="px-3 py-2">
                          {po.receipt_status === "received" ? <span className="text-xs px-2 py-0.5 rounded bg-green-100 text-green-700">已收货</span>
                            : po.receipt_status === "partially_received" ? <span className="text-xs px-2 py-0.5 rounded bg-red-100 text-red-700">有差异</span>
                            : <span className="text-xs px-2 py-0.5 rounded bg-gray-100 text-gray-500">未收货</span>}
                        </td>
                        <td className="px-3 py-2 text-center">
                          {po.status === "confirmed" && (
                            <button onClick={() => openReceiveForm(po)} className="px-3 py-1 bg-green-600 text-white rounded text-xs">登记本次收货</button>
                          )}
                          {po.arrival_photo && (
                            <button onClick={() => window.open(uploadUrl(po.arrival_photo), "_blank")} className="text-blue-600 text-xs hover:underline ml-2">照片</button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                </div>
              )}
            </div>
            <div className="border-t px-5 py-3 text-center">
              <button onClick={() => setShowReceipt(false)} className="text-sm text-gray-400">关闭</button>
            </div>
          </div>
        </div>
      )}

      {/* 收货录入弹窗 */}
      {receiveTarget && (
        <div className="modal-overlay z-[60]" onClick={() => setReceiveTarget(null)}>
          <div role="dialog" aria-label="登记本次收货" className="bg-white rounded-xl w-[760px] max-w-[95vw] max-h-[85vh] overflow-auto" onClick={e => e.stopPropagation()}>
            <div className="bg-green-600 text-white px-5 py-3 rounded-t-xl flex items-center gap-2 sticky top-0 z-10">
              <CheckCircle size={20} />
              <h2 className="font-semibold">登记本次收货 - {receiveTarget.order_number}</h2>
              <button onClick={() => setReceiveTarget(null)} className="ml-auto text-green-200 hover:text-white text-xl">&times;</button>
            </div>
            <div className="p-5 space-y-4">
              <div className="text-sm text-gray-600">供应商：{receiveTarget.supplier_name || "-"} · 金额：{receiveTarget.total_amount}</div>
              <ProcurementDutyFields value={receiveDuty} onChange={setReceiveDuty} onRefresh={()=>openReceiveForm(receiveTarget)}/>
              <p className="text-amber-800 text-sm">填写本次收到的数量，系统加到已有累计中；补收20填20，不填累计100。现有采购仅支持整数单位。</p>
              <div className="space-y-3">{(receiveTarget.items || []).map((it:any)=><div className="border rounded p-3 space-y-2" key={it.line_id}>
                <p className="font-medium">{it.product_name} {it.spec || ""} · {it.unit || "单位未记录"}</p>
                <p className="text-xs text-gray-500 break-all">行编号：{it.line_id}</p>
                <div className="grid grid-cols-3 gap-2 text-sm"><span>订购 {it.quantity ?? "未知"}</span><span>累计已记录 {it.received_quantity ?? "未知"}</span><span>尚差 {it.remaining_quantity ?? "未知"}</span></div>
                <label className="block text-sm">本次收货数量<input aria-label={`本次收货数量-${it.line_id}`} type="number" min="0" step="1" className="form-input" value={receiveQty[it.line_id] ?? ""} onChange={e=>setReceiveQty(prev=>({...prev,[it.line_id]:e.target.value}))}/></label>
              </div>)}</div>
              <label className="block text-sm">本次备注<textarea className="form-input" maxLength={1000} value={receiveRemark} onChange={e=>setReceiveRemark(e.target.value)}/></label>
              <div>
                <label className="form-label text-sm font-medium text-gray-600 mb-1 block">到货照片 <span className="text-red-400">*</span></label>
                <input type="file" accept="image/*" onChange={e => setReceivePhoto(e.target.files?.[0] || null)} className="text-sm text-gray-500" />
                {receivePhoto && <div className="text-xs text-green-600 mt-1">{receivePhoto.name}</div>}
              </div>
            </div>
            <div className="border-t px-5 py-3 flex justify-end gap-3 bg-gray-50 rounded-b-xl">
              <button onClick={() => setReceiveTarget(null)} className="btn-secondary text-sm px-5 py-2">取消</button>
              <button onClick={submitReceive} disabled={receiptSubmitting}
                className="bg-green-600 text-white px-5 py-2 rounded-lg text-sm font-medium hover:bg-green-700 disabled:opacity-50">
                {receiptSubmitting ? "提交中..." : "确认本次收货"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 收货差异列表弹窗 */}
      {showDiscrepancies && (
        <div className="modal-overlay z-50" onClick={() => setShowDiscrepancies(false)}>
          <div className="bg-white rounded-xl w-[900px] max-w-[95vw] max-h-[85vh] overflow-auto" onClick={e => e.stopPropagation()}>
            <div className="bg-red-500 text-white px-5 py-3 rounded-t-xl flex items-center gap-2 sticky top-0 z-10">
              <AlertCircle size={20} />
              <h2 className="font-semibold">收货差异列表</h2>
              <button onClick={() => setShowDiscrepancies(false)} className="ml-auto text-red-200 hover:text-white text-xl">&times;</button>
            </div>
            <div className="p-5">
              {discrepancies.length === 0 ? (
                <div className="text-gray-400 text-sm py-8 text-center">暂无收货差异</div>
              ) : (
                <div className="overflow-x-auto touch-pan-x">
                <table className="w-full text-sm min-w-[900px]">
                  <thead><tr className="border-b bg-gray-50 text-left text-gray-500">
                    <th className="px-3 py-2 font-medium">单号</th>
                    <th className="px-3 py-2 font-medium">供应商</th>
                    <th className="px-3 py-2 font-medium">产品</th>
                    <th className="px-3 py-2 font-medium text-right">订购</th>
                    <th className="px-3 py-2 font-medium text-right">实收</th>
                    <th className="px-3 py-2 font-medium text-right">差异</th>
                    <th className="px-3 py-2 font-medium text-right">差异金额</th>
                    <th className="px-3 py-2 font-medium">收货人</th>
                  </tr></thead>
                  <tbody>
                    {discrepancies.map((d: any, i: number) => (
                      <tr key={`${d.purchase_order_id}:${d.line_id}`} className="border-b">
                        <td className="px-3 py-2 font-medium">{d.order_number}</td>
                        <td className="px-3 py-2">{d.supplier_name || "-"}</td>
                        <td className="px-3 py-2">{d.product_name}{d.spec ? <span className="text-gray-400 text-xs">（{d.spec}）</span> : null}</td>
                        <td className="px-3 py-2 text-right">{d.order_quantity ?? "未记录"}</td>
                        <td className="px-3 py-2 text-right">{d.received_quantity ?? "未记录"}</td>
                        <td className="px-3 py-2 text-right text-red-600 font-semibold">{d.diff_quantity==null ? "未知" : `${d.diff_quantity>0 ? "少" : "多"} ${Math.abs(d.diff_quantity)}`}</td>
                        <td className="px-3 py-2 text-right text-red-600 font-semibold">{d.diff_amount==null ? "待核对" : fmtMoney(d.diff_amount,d.currency)}</td>
                        <td className="px-3 py-2 text-gray-500">{d.receiver_name || "-"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                </div>
              )}
            </div>
            <div className="border-t px-5 py-3 text-center">
              <button onClick={() => setShowDiscrepancies(false)} className="text-sm text-gray-400">关闭</button>
            </div>
          </div>
        </div>
      )}

      {/* 采购单列表弹窗 */}
      {showPoList && (
        <div className="modal-overlay z-50" onClick={() => setShowPoList(false)}>
          <div className="bg-white rounded-xl w-[960px] max-w-[95vw] max-h-[85vh] overflow-auto" onClick={e => e.stopPropagation()}>
            <div className="bg-blue-600 text-white px-5 py-3 rounded-t-xl flex items-center gap-2 sticky top-0 z-10">
              <FileText size={20} />
              <h2 className="font-semibold">采购单列表</h2>
              <button onClick={() => setShowPoList(false)} className="ml-auto text-blue-200 hover:text-white text-xl">&times;</button>
            </div>
            <div className="p-5">
              {poList.length === 0 ? (
                <div className="text-gray-400 text-sm py-8 text-center">暂无采购单</div>
              ) : (
                <div className="overflow-x-auto touch-pan-x">
                <table className="w-full text-sm min-w-[900px]">
                  <thead><tr className="border-b bg-gray-50 text-left text-gray-500">
                    <th className="px-3 py-2 font-medium">单号</th>
                    <th className="px-3 py-2 font-medium">供应商</th>
                    <th className="px-3 py-2 font-medium">仓库</th>
                    <th className="px-3 py-2 font-medium text-right">金额</th>
                    <th className="px-3 py-2 font-medium">状态</th>
                    <th className="px-3 py-2 font-medium">流程</th>
                    <th className="px-3 py-2 font-medium">收货</th>
                    <th className="px-3 py-2 font-medium">下单时间</th>
                    <th className="px-3 py-2 font-medium text-center">操作</th>
                  </tr></thead>
                  <tbody>
                    {poList.map((po: any) => (
                      <tr key={po.id} className="border-b">
                        <td className="px-3 py-2 font-medium">{po.order_number}</td>
                        <td className="px-3 py-2">{po.supplier_name || "-"}</td>
                        <td className="px-3 py-2">{po.warehouse_name || "-"}</td>
                        <td className="px-3 py-2 text-right font-mono">{po.total_amount}</td>
                        <td className="px-3 py-2">
                          {po.status === "pending" ? <span className="text-xs px-2 py-0.5 rounded bg-yellow-100 text-yellow-700">待审批</span>
                            : po.status === "confirmed" ? <span className="text-xs px-2 py-0.5 rounded bg-blue-100 text-blue-700">已生效</span>
                            : <span className="text-xs px-2 py-0.5 rounded bg-red-100 text-red-700">已驳回</span>}
                        </td>
                        <td className="px-3 py-2">
                          <span className={`text-xs px-2 py-0.5 rounded ${FLOW_STATUS_MAP[po.flow_status]?.cls || "bg-gray-100 text-gray-600"}`}>
                            {FLOW_STATUS_MAP[po.flow_status]?.label || po.flow_status || "-"}
                          </span>
                        </td>
                        <td className="px-3 py-2">
                          {po.receipt_status === "received" ? <span className="text-xs px-2 py-0.5 rounded bg-green-100 text-green-700">已收货</span>
                            : po.receipt_status === "partially_received" ? <span className="text-xs px-2 py-0.5 rounded bg-red-100 text-red-700">有差异</span>
                            : <span className="text-xs px-2 py-0.5 rounded bg-gray-100 text-gray-500">未收货</span>}
                        </td>
                        <td className="px-3 py-2 text-gray-500 text-xs">{po.created_at ? new Date(po.created_at).toLocaleString("zh-CN", { timeZone: "Asia/Bangkok" }) : "-"}</td>
                        <td className="px-3 py-2 text-center">
                          <div className="flex items-center justify-center gap-2">
                            <button onClick={() => openPoDetail(po.id)} className="text-blue-600 text-xs hover:underline">明细</button>
                            <button onClick={() => downloadPoPdf(po)} className="text-green-600 text-xs hover:underline flex items-center gap-1"><Download size={12}/>PDF</button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                </div>
              )}
            </div>
            <div className="border-t px-5 py-3 text-center">
              <button onClick={() => setShowPoList(false)} className="text-sm text-gray-400">关闭</button>
            </div>
          </div>
        </div>
      )}

      {/* 采购单明细弹窗 */}
      {poDetail && (
        <div className="modal-overlay z-[60]" onClick={() => setPoDetail(null)}>
          <div className="bg-white rounded-xl w-[720px] max-w-[95vw] max-h-[85vh] overflow-auto" onClick={e => e.stopPropagation()}>
            <div className="bg-blue-600 text-white px-5 py-3 rounded-t-xl flex items-center gap-2 sticky top-0 z-10">
              <FileText size={20} />
              <h2 className="font-semibold">采购单明细 - {poDetail.order_number}</h2>
              <button onClick={() => setPoDetail(null)} className="ml-auto text-blue-200 hover:text-white text-xl">&times;</button>
            </div>
            <div className="p-5 space-y-4">
              <div className="grid grid-cols-2 gap-3 text-sm">
                <div><span className="text-gray-400">供应商：</span>{poDetail.supplier_name || "-"}</div>
                <div><span className="text-gray-400">仓库：</span>{poDetail.warehouse_name || "-"}</div>
                <div><span className="text-gray-400">状态：</span>{poDetail.status === "pending" ? "待审批" : poDetail.status === "confirmed" ? "已生效" : "已驳回"}</div>
                <div><span className="text-gray-400">下单时间：</span>{poDetail.created_at ? new Date(poDetail.created_at).toLocaleString("zh-CN", { timeZone: "Asia/Bangkok" }) : "-"}</div>
                <div className="col-span-2">
                  <span className="text-gray-400">流程状态：</span>
                  <span className={`text-xs px-2 py-0.5 rounded ${FLOW_STATUS_MAP[poDetail.flow_status]?.cls || "bg-gray-100 text-gray-600"}`}>
                    {FLOW_STATUS_MAP[poDetail.flow_status]?.label || poDetail.flow_status || "-"}
                  </span>
                </div>
              </div>

              <LinkedPayable order={poDetail}/>
              <p className="text-sm">收货状态：{({not_received:"未收货", received:"已收货", partially_received:"收货有差异"} as Record<string,string>)[poDetail.receipt_status] || "尚未记录"}</p>
              {/* 流程操作 */}
              {poDetail.status === "confirmed" && poDetail.flow_status !== "completed" && (
                <div className="bg-gray-50 rounded-lg p-3 space-y-2">
                  <div className="text-sm font-medium text-gray-600">流程操作</div>
                  <div className="flex flex-wrap gap-2">
                    <button onClick={() => markSent(poDetail)} className="px-3 py-1.5 bg-blue-600 text-white rounded text-xs">标记已发送</button>
                    <button onClick={() => triggerReceiptUpload(poDetail.id)} className="px-3 py-1.5 bg-green-600 text-white rounded text-xs">上传回执</button>
                    <button onClick={() => markShipped(poDetail)} className="px-3 py-1.5 bg-purple-600 text-white rounded text-xs">标记已发货</button>
                  </div>
                  {poDetail.sent_at && <div className="text-xs text-gray-500">已发送：{new Date(poDetail.sent_at).toLocaleString("zh-CN", { timeZone: "Asia/Bangkok" })}</div>}
                  {poDetail.receipt_uploaded_at && <div className="text-xs text-gray-500">回执上传：{new Date(poDetail.receipt_uploaded_at).toLocaleString("zh-CN", { timeZone: "Asia/Bangkok" })}</div>}
                  {poDetail.shipped_at && <div className="text-xs text-gray-500">已发货：{new Date(poDetail.shipped_at).toLocaleString("zh-CN", { timeZone: "Asia/Bangkok" })}</div>}
                </div>
              )}

              <PurchaseQuantities order={poDetail}/><ReceiptHistory order={poDetail}/><ThreeWayMatch value={poDetail.matching}/>
              <div className="text-right font-semibold">总价：{poDetail.total_amount}</div>
            </div>
            <div className="border-t px-5 py-3 flex justify-end gap-3 bg-gray-50 rounded-b-xl">
              {poDetail.receipt_file && (
                <button onClick={() => window.open(uploadUrl(poDetail.receipt_file), "_blank")} className="bg-amber-500 text-white px-4 py-2 rounded text-sm flex items-center gap-1"><Eye size={14}/>查看回执</button>
              )}
              <button onClick={() => downloadPoPdf(poDetail)} className="bg-green-600 text-white px-4 py-2 rounded text-sm flex items-center gap-1"><Download size={14}/>下载PDF</button>
              <button onClick={() => setPoDetail(null)} className="btn-secondary text-sm px-5 py-2">关闭</button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

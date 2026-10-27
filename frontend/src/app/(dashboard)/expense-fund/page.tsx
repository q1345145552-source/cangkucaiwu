"use client";
import { balanceWarningText,confirmBalanceWarning } from "@/lib/balanceWarning";
import type { MessageResponse } from "@/lib/api";
import { useEffect, useState,useRef } from "react";
import { useCostIdentity,CostConfirmation } from "@/components/CostIdentity";
import { submitRegistration,registrationDraft } from "@/lib/registrationRequest";
import { api, getActiveWarehouseId, getToken } from "@/lib/api";
import { fmtMoney, fmtMoneyByCurrency } from "@/lib/currency";
import { useToast } from "@/components/ui/Toast";
import { useAuth } from "@/hooks/useAuth";
import { useRouter } from "next/navigation";
import {
  PiggyBank, Wallet, Plus, ArrowUp, FileText, Camera, Image,
  RefreshCw, AlertTriangle, ChevronDown, ChevronRight,
  Users, DollarSign, TrendingUp, Activity, X, CheckCircle as CheckC,
  XCircle, Search, Eye, ClipboardCheck, CreditCard,
} from "lucide-react";

export default function ExpenseFundPage() {
  const cost=useCostIdentity();
  const receiptCache=useRef<{file:File;path:string}|null>(null);
  const { toast } = useToast();
  const { user } = useAuth();
  const router = useRouter();
  const isAdmin = user?.role === "warehouse_admin";

  // ====== Tab ======
  const [tab, setTab] = useState<"manage" | "review">("manage");

  // ====== Management state ======
  const [accounts, setAccounts] = useState<any[]>([]);
  const [employees, setEmployees] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [items, setItems] = useState<Record<number, any[]>>({});
  const [itemsLoading, setItemsLoading] = useState<Record<number, boolean>>({});
  const [showCreate, setShowCreate] = useState(false);
  const [newEmpId, setNewEmpId] = useState("");
  const [newLimit, setNewLimit] = useState("");
  const [showTopUp, setShowTopUp] = useState(false);
  const [topUpAccount, setTopUpAccount] = useState<any>(null);
  const [topUpAmount, setTopUpAmount] = useState("");
  const [topUpReason, setTopUpReason] = useState("");
  const [paymentAccounts, setPaymentAccounts] = useState<any[]>([]);
  const [paymentAccountId, setPaymentAccountId] = useState("");
  const [topUpDate, setTopUpDate] = useState("");
  const [topUpBusy, setTopUpBusy] = useState(false);
  const [rechargeReviewId, setRechargeReviewId] = useState<number | null>(null);
  const [disbursements, setDisbursements] = useState<Record<number, any[]>>({});
  const [showExpense, setShowExpense] = useState(false);
  const [expenseAccount, setExpenseAccount] = useState<any>(null);
  const [itemForm, setItemForm] = useState({ expense_date: new Date().toISOString().slice(0, 10), category: "耗材", amount: "" as string | number, currency: "THB", description: "" });
  const [receiptFile, setReceiptFile] = useState<File | null>(null);
  const [expenseBusy, setExpenseBusy] = useState(false);
  const [editingItem, setEditingItem] = useState<any>(null);
  const [voidTarget, setVoidTarget] = useState<{ account: any; item: any } | null>(null);
  const [voidReason, setVoidReason] = useState(""), [voidBusy, setVoidBusy] = useState(false);

  // ====== Review state ======
  const [reviewData, setReviewData] = useState<any[]>([]);
  const [reviewLoading, setReviewLoading] = useState(false);
  const [reviewEmployees, setReviewEmployees] = useState<any[]>([]);
  const [selEmployee, setSelEmployee] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [selCurrency, setSelCurrency] = useState("");
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [rejectRemark, setRejectRemark] = useState("");
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);

  const [reviewTab, setReviewTab] = useState<"expense" | "recharge">("expense");
  const [rechargeData, setRechargeData] = useState<any[]>([]);
  const [rechargeLoading, setRechargeLoading] = useState(false);
  const [rechargeHistory, setRechargeHistory] = useState<Record<number, any[]>>({});
  const [rechargeHistoryLoading, setRechargeHistoryLoading] = useState<Record<number, boolean>>({});

  useEffect(() => { if (!getToken()) router.push("/login"); loadAll(); }, []);

  async function loadAll() {
    await loadAccounts();
    loadEmployees();
  }

  // ====== Management logic ======
  async function loadAccounts() {
    setLoading(true);
    try {
      const r = await api.get<any>("/expense-fund/accounts");
      setAccounts(r.data || []);
    } catch (err) { console.error(err); }
    setLoading(false);
  }

  async function loadEmployees() {
    try {
      const r = await api.get<any>("/expense-fund/employees");
      setEmployees(r.data || []);
      const emps = (r.data || []).map((a: any) => ({ id: a.id, name: a.display_name }));
      const seen = new Set<number>();
      setReviewEmployees(emps.filter((e: any) => { if (seen.has(e.id)) return false; seen.add(e.id); return true; }));
    } catch {}
  }

  async function toggleExpand(acc: any) {
    if (expandedId === acc.id) { setExpandedId(null); return; }
    setExpandedId(acc.id);
    if (!items[acc.id]) {
      setItemsLoading(prev => ({ ...prev, [acc.id]: true }));
      try {
        const r = await api.get<any>(`/expense-fund/accounts/${acc.id}/items`);
        setItems(prev => ({ ...prev, [acc.id]: r.data || [] }));
      } catch {}
      setItemsLoading(prev => ({ ...prev, [acc.id]: false }));
    }
    loadRechargeHistory(acc);
    loadDisbursements(acc.id);
  }

  async function doCreate() {
    if (!newEmpId) { toast("error", "请选择员工"); return; }
    try {
      const r = await api.post<MessageResponse>("/expense-fund/accounts", { employee_id: +newEmpId, fund_limit: newLimit ? +newLimit : undefined });
      toast("success", r.message || "创建成功");
      setShowCreate(false); setNewEmpId(""); setNewLimit("");
      loadAll();
    } catch (err: any) { toast("error", err.message || "创建失败"); }
  }

  async function openTopUp(acc: any, request?: any) {
    setTopUpAccount(acc); setTopUpAmount(request ? String(request.amount) : ""); setTopUpReason("");
    setRechargeReviewId(request?.id ?? null);
    setTopUpDate(new Date().toLocaleDateString("sv-SE", { timeZone: "Asia/Bangkok" }));
    setPaymentAccountId(""); setPaymentAccounts([]); setShowTopUp(true);
    if (isAdmin) {
      try {
        const r = await api.get<any>("/expense-fund/payment-accounts");
        const matching = (r.data || []).filter((a: any) => (a.currency || "THB") === (acc.currency || "THB"));
        setPaymentAccounts(matching);
        setPaymentAccountId(String((matching.find((a: any) => a.account_type === "cash") || matching[0])?.id || ""));
      } catch (err: any) { toast("error", err.message || "付款账户加载失败"); }
    }
  }
  async function doTopUp() {
    if (!topUpAccount || !topUpAmount || topUpBusy) return;
    if (isAdmin && !paymentAccountId) { toast("error", "请选择备用金拨付账户"); return; }
    setTopUpBusy(true);
    try {
      if (isAdmin) {
        const fresh=await api.get<any>('/expense-fund/payment-accounts');
        const selected=(fresh.data||[]).find((a:any)=>String(a.id)===paymentAccountId);
        if(!selected)throw Error('付款账户已变化，请重新选择');
        setPaymentAccounts((fresh.data||[]).filter((a:any)=>(a.currency||'THB')===(topUpAccount.currency||'THB')));
        if(!confirmBalanceWarning(selected.current_balance,+topUpAmount))return;
        // 管理员直接充值
        const fields = { payment_account_id: +paymentAccountId, receive_date: topUpDate };
        const r = rechargeReviewId !== null
          ? await api.post<MessageResponse>("/expense-fund/recharge/review", { request_id: rechargeReviewId, action: "approve", ...fields })
          : await api.post<MessageResponse>(`/expense-fund/accounts/${topUpAccount.id}/topup`, { amount: +topUpAmount, ...fields });
        toast("success", r.message || "充值成功");
      } else {
        // 财务提交充值申请
        const r = await api.post<MessageResponse>("/expense-fund/recharge/request", { amount: +topUpAmount, reason: topUpReason });
        toast("success", r.message || "充值申请已提交");
      }
      setShowTopUp(false); setTopUpAmount(""); setTopUpReason(""); setTopUpReason("");
      loadAccounts();
      loadDisbursements(topUpAccount.id);
      setRechargeHistory({});
      if (rechargeReviewId !== null) loadRechargeRequests();
    } catch (err: any) { toast("error", err.message || "充值失败"); }
    finally { setTopUpBusy(false); }
  }

  function openExpense(acc: any) {
    const pending=registrationDraft('cost_fund_item',acc.id)?.payload;
    cost.reset(pending?.cost);
    setEditingItem(null);
    setExpenseAccount(acc);
    setItemForm({ expense_date: new Date().toISOString().slice(0, 10), category: "耗材", amount: "", currency: acc.currency || "THB", description: "" });
    if(pending){setItemForm(pending.form);}else{setReceiptFile(null);receiptCache.current=null;}
    setShowExpense(true);
  }
  function openEditExpense(acc: any, item: any) {
    if (!isAdmin || !item.can_edit) return;
    cost.reset();cost.edit('fund_item',item.id).catch(e=>toast('error',e.message));
    setExpenseAccount(acc); setEditingItem(item); setReceiptFile(null);
    setItemForm({ expense_date: item.expense_date?.slice(0, 10) || "", category: item.category,
      amount: String(item.amount), currency: item.currency || "THB", description: item.description || "" });
    setShowExpense(true);
  }
  async function doAddExpense(costConfirmation?:CostConfirmation) {
    if (!expenseAccount || expenseBusy) return;
    if (editingItem && !isAdmin) return;
    if (!receiptFile && !editingItem?.receipt && !registrationDraft('cost_fund_item',expenseAccount.id)?.payload?.receipt) { toast("error", "请上传开销凭证"); return; }
    setExpenseBusy(true);
    try {
      if(itemForm.category!=='报销'){
        const fresh=await api.get<any>('/expense-fund/accounts');const fund=(fresh.data||[]).find((f:any)=>f.id===expenseAccount.id);
        if(!fund)throw Error('备用金账户已变化，请重新选择');
        const available=Number(fund.available??fund.current_balance??0)+(editingItem&&editingItem.category!=='报销'?Number(editingItem.amount):0);
        if(!confirmBalanceWarning(available,itemForm.amount))return;
      }

      let receipt = editingItem?.receipt || registrationDraft('cost_fund_item',expenseAccount.id)?.payload?.receipt;
      if (receiptFile && receiptCache.current?.file!==receiptFile) {
        const fd = new FormData(); fd.append("file", receiptFile);
        const headers: Record<string, string> = { Authorization: `Bearer ${getToken()}` };
        const warehouse = getActiveWarehouseId(); if (warehouse) headers["X-Warehouse-ID"] = warehouse;
        const upRes = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "/api/v1"}/expense-fund/accounts/${expenseAccount.id}/upload-receipt`, {
          method: "POST", headers, body: fd,
        });
        const upData = await upRes.json().catch(() => ({}));
        if (!upRes.ok || !upData.receipt) throw new Error(upData.detail || "凭证上传失败，请重试");
        receipt = upData.receipt;
        receiptCache.current={file:receiptFile,path:receipt};
      }
      if(receiptFile&&receiptCache.current?.file===receiptFile)receipt=receiptCache.current.path;
      const body = { ...itemForm,...cost.payload(),cost_confirmation:costConfirmation, amount: itemForm.amount || 0, currency: itemForm.currency, receipt };
      if (editingItem) await api.put(`/expense-fund/accounts/${expenseAccount.id}/items/${editingItem.id}`, body);
      else await submitRegistration<any>('cost_fund_item',expenseAccount.id,{form:itemForm,cost:cost.value,receipt},key=>api.post(`/expense-fund/accounts/${expenseAccount.id}/items`,{...body,request_key:key}));
      toast("success", editingItem ? "开销修改成功" : "开销添加成功");
      setShowExpense(false);
      loadAccounts();
      const updated = await api.get<any>(`/expense-fund/accounts/${expenseAccount.id}/items`);
      setItems(prev => ({ ...prev, [expenseAccount.id]: updated.data || [] }));
      loadDisbursements(expenseAccount.id);
    } catch (err: any) { if(!cost.capture(err,doAddExpense))toast("error", err.message || "添加失败"); }
    finally { setExpenseBusy(false); }
  }
  async function doVoidExpense() {
    if (!isAdmin || !voidTarget || voidBusy) return;
    if (!voidReason.trim()) { toast("error", "请填写作废原因"); return; }
    setVoidBusy(true);
    try {
      await api.delete(`/expense-fund/accounts/${voidTarget.account.id}/items/${voidTarget.item.id}`, { reason: voidReason.trim() });
      const accountId = voidTarget.account.id;
      toast("success", "开销已作废，原记录已保留"); setVoidTarget(null); setVoidReason("");
      loadAccounts(); loadDisbursements(accountId);
      const updated = await api.get<any>(`/expense-fund/accounts/${accountId}/items`);
      setItems(previous => ({ ...previous, [accountId]: updated.data || [] }));
    } catch (err: any) { toast("error", err.message || "作废失败"); }
    finally { setVoidBusy(false); }
  }

  // ====== Review logic ======
  useEffect(() => {
    if (tab === "review") {
      if (reviewTab === "recharge") loadRechargeRequests();
      else loadReviews();
    }
  }, [tab, reviewTab]);

  async function loadReviews() {
    setReviewLoading(true);
    try {
      const params = new URLSearchParams({ page_size: "100" });
      if (selEmployee) params.set("employee_id", selEmployee);
      if (startDate) params.set("start_date", startDate);
      if (endDate) params.set("end_date", endDate);
      if (selCurrency) params.set("currency", selCurrency);
      const r = await api.get<any>(`/expense-fund/review/pending?${params.toString()}`);
      setReviewData(r.data || []);
    } catch (err) { console.error("审核数据加载失败:", err); }
    setReviewLoading(false); setSelectedIds(new Set());
  }

  function toggleAllReview() {
    if (selectedIds.size === reviewData.length) setSelectedIds(new Set());
    else setSelectedIds(new Set(reviewData.map(r => r.id)));
  }
  function toggleOneReview(id: number) {
    setSelectedIds(prev => { const n = new Set(prev); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  }

  async function doReview(action: "approve" | "reject",costConfirmations:Record<number,CostConfirmation>={}) {
    if (selectedIds.size === 0) { toast("error", "请先勾选要审核的记录"); return; }
    try {
      await api.post("/expense-fund/review/batch", { item_ids: Array.from(selectedIds), action,cost_confirmations:costConfirmations, remark: action === "reject" ? rejectRemark : undefined });
      toast("success", action === "approve" ? "已批量通过" : "已批量驳回");
      setRejectRemark(""); loadReviews();
    } catch (err: any) { if(!cost.capture(err,data=>doReview(action,{...costConfirmations,[Number(data.target_ref?.split(':')[1])]:data})))toast("error", err.message || "审核失败"); }
  }

  async function approveOne(id: number,costConfirmation?:CostConfirmation) {
    try {
      await api.post("/expense-fund/review/batch", { item_ids: [id], action: "approve",cost_confirmation:costConfirmation });
      toast("success", "已通过"); loadReviews();
    } catch (err: any) { if(!cost.capture(err,data=>approveOne(id,data)))toast("error", err.message || "审核失败"); }
  }
  function rejectOne(id: number) {
    const reason = prompt("请输入驳回原因");
    if (reason === null) return;
    (async () => {
      try {
        await api.post("/expense-fund/review/batch", { item_ids: [id], action: "reject", remark: reason });
        toast("success", "已驳回"); loadReviews();
      } catch (err: any) { toast("error", err.message || "审核失败"); }
    })();
  }

  // Recharge Request functions
  async function loadRechargeRequests() {
    setRechargeLoading(true);
    try {
      const r = await api.get<any>("/expense-fund/recharge/requests?status=pending&page_size=100");
      setRechargeData(r.data || []);
    } catch (err) { console.error(err); }
    setRechargeLoading(false);
  }
  async function approveRecharge(reqId: number) {
    const request = rechargeData.find(r => r.id === reqId);
    if (request) await openTopUp({ id: request.fund_id, employee_name: request.applicant_name,
      currency: request.currency, current_balance: request.current_balance, available: request.available, fund_limit: request.fund_limit }, request);
  }
  async function loadDisbursements(id: number) {
    try {
      const r = await api.get<any>(`/expense-fund/accounts/${id}/disbursements`);
      setDisbursements(prev => ({ ...prev, [id]: r.data || [] }));
    } catch (err: any) { toast("error", err.message || "拨付记录加载失败"); }
  }
  function rejectRecharge(reqId: number) {
    const reason = prompt("请输入驳回原因");
    if (reason === null) return;
    (async () => {
      try {
        await api.post<MessageResponse>("/expense-fund/recharge/review", { request_id: reqId, action: "reject", remark: reason });
        toast("success", "充值申请已驳回");
        loadRechargeRequests();
      } catch (err: any) { toast("error", err.message || "审核失败"); }
    })();
  }
  async function loadRechargeHistory(acc: any) {
    if (rechargeHistory[acc.id]) return;
    setRechargeHistoryLoading(prev => ({ ...prev, [acc.id]: true }));
    try {
      const r = await api.get<any>(`/expense-fund/recharge/requests?page_size=10&applicant_id=${acc.employee_id}`);
      setRechargeHistory(prev => ({ ...prev, [acc.id]: r.data || [] }));
    } catch {}
    setRechargeHistoryLoading(prev => ({ ...prev, [acc.id]: false }));
  }

  // ====== Stats ======
  const totalBalanceByCurrency = accounts.reduce((m: Record<string, number>, a: any) => { const c = a.currency || "THB"; m[c] = (m[c] || 0) + (a.available ?? a.current_balance ?? 0); return m; }, {});
  const totalSpentByCurrency = accounts.reduce((m: Record<string, number>, a: any) => { Object.entries(a.spent_by_currency || {}).forEach(([c, v]: [string, any]) => { m[c] = (m[c] || 0) + (v || 0); }); return m; }, {});
  const lowCount = accounts.filter((a: any) => a.is_low).length;

  return (
    <>
      {/* Header with tabs */}
      <div className="flex items-center gap-3 mb-5">
        <div className="w-9 h-9 rounded-xl bg-blue-100 flex items-center justify-center">
          <PiggyBank size={20} className="text-blue-600" />
        </div>
        <div className="flex-1">
          <h1 className="page-title">备用金</h1>
        </div>
        {isAdmin && tab === "manage" && (
          <button onClick={() => setShowCreate(true)} className="btn-primary flex items-center gap-1.5">
            <Plus size={16} />新建备用金
          </button>
        )}
      </div>

      {/* Tab bar */}
      <div className="flex items-center gap-1 mb-5 bg-white rounded-xl p-1 shadow-sm border border-gray-100 w-fit">
        <button
          onClick={() => setTab("manage")}
          className={`px-4 py-2 rounded-lg text-sm font-medium transition-all flex items-center gap-1.5 ${
            tab === "manage" ? "bg-blue-600 text-white shadow-sm" : "text-gray-500 hover:text-gray-700"
          }`}
        >
          <Wallet size={15} />管理
        </button>
        {isAdmin && (
          <button
            onClick={() => setTab("review")}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-all flex items-center gap-1.5 ${
              tab === "review" ? "bg-blue-600 text-white shadow-sm" : "text-gray-500 hover:text-gray-700"
            }`}
          >
            <ClipboardCheck size={15} />审核
            {reviewData.length > 0 && (
              <span className={`ml-1 px-1.5 py-0.5 rounded-full text-[11px] font-bold ${tab === "review" ? "bg-blue-500 text-white" : "bg-red-500 text-white"}`}>
                {reviewData.length}
              </span>
            )}
          </button>
        )}
      </div>

      {/* ========== MANAGEMENT TAB ========== */}
      {tab === "manage" && (
        <>
          {/* Stats cards */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-5">
            <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-4">
              <div className="flex items-center gap-2 text-xs text-gray-400 mb-2"><Users size={14} />账户数量</div>
              <div className="text-2xl font-bold text-gray-800">{accounts.length}</div>
            </div>
            <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-4">
              <div className="flex items-center gap-2 text-xs text-gray-400 mb-2"><DollarSign size={14} />账户总余额</div>
              <div className="text-2xl font-bold text-blue-700">{fmtMoneyByCurrency(totalBalanceByCurrency)}</div>
            </div>
            <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-4">
              <div className="flex items-center gap-2 text-xs text-gray-400 mb-2"><TrendingUp size={14} />累计开销</div>
              <div className="text-2xl font-bold text-yellow-700">{fmtMoneyByCurrency(totalSpentByCurrency)}</div>
            </div>
            <div className={`bg-white rounded-2xl shadow-sm border p-4 ${lowCount > 0 ? "border-red-200" : "border-gray-100"}`}>
              <div className="flex items-center gap-2 text-xs text-gray-400 mb-2"><AlertTriangle size={14} />余额不足</div>
              <div className={`text-2xl font-bold ${lowCount > 0 ? "text-red-600" : "text-gray-400"}`}>{lowCount}</div>
            </div>
          </div>

          {/* Account table */}
          <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
            {loading ? (
              <div className="flex items-center justify-center h-40 text-gray-400"><div className="animate-spin w-5 h-5 border-2 border-blue-600 border-t-transparent rounded-full mr-2" />加载中...</div>
            ) : accounts.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16 text-gray-400">
                <Wallet size={48} className="text-gray-200 mb-3" /><span className="text-sm">暂无备用金账户</span>
                {isAdmin && <button onClick={() => setShowCreate(true)} className="btn-primary mt-4 text-sm"><Plus size={14} className="mr-1" />新建备用金</button>}
              </div>
            ) : (
              <div className="overflow-x-auto touch-pan-x">
              <table className="w-full text-sm min-w-[900px]">
                <thead>
                  <tr className="border-b bg-gray-50">
                    <th className="w-8"></th>
                    <th className="text-left px-4 py-3 font-medium text-gray-500">员工姓名</th>
                    <th className="text-right px-4 py-3 font-medium text-gray-500">备用金总额</th>
                    <th className="text-right px-4 py-3 font-medium text-gray-500">已用金额</th>
                    <th className="text-right px-4 py-3 font-medium text-gray-500">可用余额</th>
                    <th className="text-right px-4 py-3 font-medium text-gray-500">上限</th>
                    <th className="text-center px-4 py-3 font-medium text-gray-500">状态</th>
                    <th className="text-center px-4 py-3 font-medium text-gray-500">操作</th>
                  </tr>
                </thead>
                <tbody>
                  {accounts.map((acc: any) => {
                    const isExpanded = expandedId === acc.id;
                    const accItems = items[acc.id] || [];
                    const accSpentTotal = acc.total_spent ?? accItems.filter((i: any) => i.review_status !== "rejected" && i.review_status !== "voided" && !i.is_voided).reduce((s: number, i: any) => s + (i.amount || 0), 0);
                    const accPendingSpent = accItems.filter((i: any) => i.review_status === "pending").reduce((s: number, i: any) => s + (i.amount || 0), 0);
                    const accAvailable = acc.available ?? Math.max(0, (acc.current_balance || 0) - accPendingSpent);
                    return (
                      <>
                        <tr key={acc.id} className={`border-b hover:bg-gray-50/50 cursor-pointer transition-colors ${acc.is_low ? "bg-red-50/30" : ""}`} onClick={() => toggleExpand(acc)}>
                          <td className="pl-4 py-3">{isExpanded ? <ChevronDown size={14} className="text-gray-400" /> : <ChevronRight size={14} className="text-gray-400" />}</td>
                          <td className="px-4 py-3 font-medium text-gray-800">
                            <div className="flex items-center gap-2">
                              <div className={`w-7 h-7 rounded-lg flex items-center justify-center ${acc.is_low ? "bg-red-100" : "bg-blue-100"}`}>
                                <Wallet size={14} className={acc.is_low ? "text-red-600" : "text-blue-600"} />
                              </div>
                              {acc.employee_name}
                            </div>
                          </td>
                          <td className="px-4 py-3 text-right font-mono text-sm">{fmtMoney(acc.total_topped_up, acc.currency)}</td>
                          <td className="px-4 py-3 text-right font-mono text-sm text-yellow-700">{fmtMoney(accSpentTotal, acc.currency)}</td>
                          <td className={`px-4 py-3 text-right font-mono text-sm font-semibold ${accAvailable <= 0 ? "text-red-600" : "text-green-700"}`}>{fmtMoney(accAvailable, acc.currency)}</td>
                          <td className="px-4 py-3 text-right font-mono text-sm text-gray-500">{fmtMoney(acc.fund_limit || 5000, acc.currency)}</td>
                          <td className="px-4 py-3 text-center">
                            <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${acc.is_low ? "bg-red-50 text-red-700" : "bg-green-50 text-green-700"}`}>{acc.is_low ? "余额不足" : "正常"}</span>
                          </td>
                          <td className="px-4 py-3 text-center">
                            <div className="flex items-center justify-center gap-1.5" onClick={e => e.stopPropagation()}>
                              <button onClick={() => openTopUp(acc)} className="px-2 py-1 rounded text-xs bg-green-50 text-green-700 hover:bg-green-100 transition-colors flex items-center gap-1"><ArrowUp size={12} />充值</button>
                              <button onClick={() => openExpense(acc)} className="px-2 py-1 rounded text-xs bg-blue-50 text-blue-700 hover:bg-blue-100 transition-colors flex items-center gap-1"><FileText size={12} />开销</button>
                            </div>
                          </td>
                        </tr>
                        {isExpanded && (
                          <tr key={`${acc.id}-detail`}>
                            <td colSpan={8} className="bg-gray-50/50 px-6 py-3">
                              {itemsLoading[acc.id] ? (
                                <div className="flex items-center justify-center py-4 text-gray-400 text-xs"><div className="animate-spin w-4 h-4 border-2 border-blue-600 border-t-transparent rounded-full mr-2" />加载中...</div>
                              ) : accItems.length === 0 ? (
                                <div className="text-center py-4 text-xs text-gray-400">暂无开销记录</div>
                              ) : (
                                <div className="overflow-x-auto touch-pan-x">
                                <table className="w-full text-xs min-w-[900px]">
                                  <thead>
                                    <tr className="border-b bg-gray-100/50">
                                      <th className="text-left px-2 py-1.5 text-gray-500">日期</th>
                                      <th className="text-left px-2 py-1.5 text-gray-500">类别</th>
                                      <th className="text-right px-2 py-1.5 text-gray-500">金额</th>
                                      <th className="text-center px-2 py-1.5 text-gray-500 w-12">币种</th>
                                      <th className="text-left px-2 py-1.5 text-gray-500">说明</th>
                                      <th className="text-center px-2 py-1.5 text-gray-500">审核</th>
                                      <th className="text-center px-2 py-1.5 text-gray-500">凭证</th>
                                      {isAdmin && <th className="text-center px-2 py-1.5 text-gray-500">操作</th>}
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {accItems.map((it: any) => (
                                      <tr key={it.id} className={`border-b border-gray-100 ${it.is_voided || it.review_status === "voided" ? "bg-gray-100 text-gray-400" : ""}`}>
                                        <td className="px-2 py-1.5">{it.expense_date?.slice(0, 10)}</td>
                                        <td className="px-2 py-1.5">{it.category}</td>
                                        <td className="px-2 py-1.5 text-right font-mono">{it.currency === "CNY" ? "¥" : "฿"}{it.amount?.toLocaleString()}</td>
                                        <td className="px-2 py-1.5 text-center"><span className={`px-1 py-0.5 rounded text-[10px] ${it.currency === "CNY" ? "bg-red-50 text-red-600" : "bg-blue-50 text-blue-600"}`}>{it.currency || "THB"}</span></td>
                                        <td className="px-2 py-1.5 text-gray-500">{it.description}
                                          {(it.disbursement_sources || []).map((p: any, index: number) => <div key={index} className="text-[10px] text-gray-400">{p.label} · {fmtMoney(p.amount, it.currency)}</div>)}
                                        </td>
                                        <td className="px-2 py-1.5 text-center">
                                          <span className={`px-1.5 py-0.5 rounded text-[10px] ${it.is_voided || it.review_status === "voided" ? "bg-gray-200 text-gray-500" : it.review_status === "approved" ? "bg-green-50 text-green-600" : it.review_status === "rejected" ? "bg-red-50 text-red-600" : "bg-yellow-50 text-yellow-600"}`}>
                                            {it.is_voided || it.review_status === "voided" ? "已作废" : it.review_status === "approved" ? "已通过" : it.review_status === "rejected" ? "已驳回" : "待审核"}
                                          </span>
                                          {it.void_reason && <p className="mt-1 max-w-40 whitespace-normal">原因：{it.void_reason}</p>}
                                        </td>
                                        <td className="px-2 py-1.5 text-center">{it.is_voided || it.review_status === "voided" ? <span>—</span> : it.receipt ? <button type="button" onClick={() => setPreviewUrl(it.receipt)} className="text-blue-600 whitespace-nowrap" aria-label={`查看开销 #${it.id} 凭证`}><Eye size={14} className="inline mr-1" />查看凭证</button> : <span className="text-gray-400">未上传</span>}</td>
                                        {isAdmin && <td className="px-2 py-1.5 text-center whitespace-nowrap">{it.can_edit && <button type="button" aria-label={`编辑开销 #${it.id}`} className="text-blue-600 mr-3" onClick={() => openEditExpense(acc, it)}>编辑</button>}{it.can_void && <button type="button" aria-label={`作废开销 #${it.id}`} className="text-red-600" onClick={() => { setVoidTarget({ account: acc, item: it }); setVoidReason(""); }}>作废</button>}</td>}
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                                </div>
                              )}
                              <div className="border-t border-gray-200 mt-3 pt-3 text-xs">
                                <div className="font-medium text-gray-500 mb-2">拨付记录</div>
                                {(disbursements[acc.id] || []).map((d: any) => <details key={d.id} className="bg-white rounded-md border border-gray-100 p-2 mb-2">
                                  <summary className="cursor-pointer">拨付 #{d.id} · {d.disbursed_date} · {fmtMoney(d.amount, d.currency)} · {d.account_name} · 支出 #{d.expense_record_id}</summary>
                                  <div className="mt-1 text-gray-500">经办：{d.operator_name}，已用 {fmtMoney(d.used_amount, d.currency)}</div>
                                  {(d.items || []).map((it: any) => <div key={it.item_id} className="mt-1 text-gray-500">开销 #{it.item_id} · {it.expense_date} · {it.description} · 本笔使用 {fmtMoney(it.amount, d.currency)}{it.receipt && <button type="button" onClick={() => setPreviewUrl(it.receipt)} className="text-blue-600 ml-2" aria-label={`查看明细开销 #${it.item_id} 凭证`}>查看凭证</button>}</div>)}
                                </details>)}
                                {!disbursements[acc.id]?.length && <div className="text-gray-400">暂无逐笔拨付记录，历史余额保留原记录</div>}
                              </div>
                              {/* Recharge history */}
                              <div className="border-t border-gray-200 mt-3 pt-3">
                                <div className="flex items-center gap-2 mb-2">
                                  <CreditCard size={14} className="text-gray-400" />
                                  <span className="text-xs font-medium text-gray-500">充值申请记录</span>
                                </div>
                                {rechargeHistoryLoading[acc.id] ? (
                                  <div className="text-xs text-gray-400 py-2">加载中...</div>
                                ) : (rechargeHistory[acc.id] || []).length === 0 ? (
                                  <div className="text-xs text-gray-400 py-2">暂无充值申请</div>
                                ) : (
                                  <div className="space-y-1.5">
                                    {(rechargeHistory[acc.id] || []).slice(0, 5).map((r: any) => (
                                      <div key={r.id} className="flex items-center justify-between text-xs bg-white rounded-md px-3 py-1.5 border border-gray-100">
                                        <div className="flex items-center gap-2">
                                          <span className={r.status === "approved" ? "text-green-600" : r.status === "rejected" ? "text-red-500" : "text-yellow-600"}>
                                            {r.status === "approved" ? "已通过" : r.status === "rejected" ? "已驳回" : "待审核"}
                                          </span>
                                          <span className="text-gray-400">{r.created_at ? new Date(r.created_at).toLocaleString("zh-CN") : "-"}</span>
                                        </div>
                                        <div className="flex items-center gap-3">
                                          <span className="text-gray-500 max-w-[120px] truncate">{r.reason || "-"}</span>
                                          <span className="font-medium text-green-700">+{fmtMoney(r.amount, r.currency)}</span>
                                        </div>
                                      </div>
                                    ))}
                                    {(rechargeHistory[acc.id] || []).length > 5 && <div className="text-xs text-gray-400 text-center">仅显示最近5条</div>}
                                  </div>
                                )}
                              </div>
                              <div className="flex items-center gap-2 mt-3">
                                <button onClick={() => openTopUp(acc)} className="px-2 py-1 rounded text-xs bg-green-50 text-green-700 hover:bg-green-100 transition-colors flex items-center gap-1"><RefreshCw size={11} />充值</button>
                                <button onClick={() => openExpense(acc)} className="px-2 py-1 rounded text-xs bg-blue-50 text-blue-700 hover:bg-blue-100 transition-colors flex items-center gap-1"><Plus size={11} />添加开销</button>
                              </div>
                            </td>
                          </tr>
                        )}
                      </>
                    );
                  })}
                </tbody>
              </table>
              </div>
            )}
          </div>

          {/* === Modals for management === */}

          {/* New account modal */}
          {showCreate && (
            <div className="modal-overlay z-50" onClick={() => setShowCreate(false)}>
              <div className="bg-white rounded-2xl w-full max-w-sm shadow-2xl" onClick={e => e.stopPropagation()}>
                <div className="bg-blue-600 text-white px-5 py-3.5 rounded-t-2xl flex items-center gap-2">
                  <PiggyBank size={18} /><h2 className="font-semibold">新建备用金账户</h2>
                  <button onClick={() => setShowCreate(false)} className="ml-auto text-blue-200 hover:text-white text-lg leading-none">&times;</button>
                </div>
                <div className="p-5 space-y-4">
                  <div>
                    <label className="form-label">选择员工</label>
                    <select className="form-input" value={newEmpId} onChange={e => setNewEmpId(e.target.value)}>
                      <option value="">请选择员工</option>
                      {employees.filter((e: any) => !e.has_account).map((e: any) => (
                        <option key={e.id} value={e.id}>{e.display_name} ({e.role === "staff" ? "财务" : "管理员"})</option>
                      ))}
                    </select>
                    {employees.filter((e: any) => !e.has_account).length === 0 && <p className="text-xs text-gray-400 mt-1">所有员工已有备用金账户</p>}
                  </div>
                  <div><label className="form-label">备用金上限（默认 5,000）</label><input type="number" className="form-input" value={newLimit} onChange={e => setNewLimit(e.target.value)} placeholder="5000" /></div>
                </div>
                <div className="border-t px-5 py-3.5 bg-gray-50 rounded-b-2xl flex flex-wrap justify-end gap-3">
                  <button onClick={() => setShowCreate(false)} className="btn-secondary text-sm whitespace-nowrap shrink-0">取消</button>
                  <button onClick={doCreate} className="btn-primary text-sm">创建</button>
                </div>
              </div>
            </div>
          )}

          {/* Expense modal */}
          {cost.dialog}
          {showExpense && (
            <div role="dialog" aria-modal="true" aria-label={editingItem ? "编辑备用金开销" : "添加备用金开销"} className="modal-overlay z-50" onClick={() => { if (!expenseBusy) { setShowExpense(false); setReceiptFile(null); } }}>
              <div className="bg-white rounded-2xl w-full max-w-md max-h-[90dvh] flex flex-col overflow-hidden shadow-2xl" onClick={e => e.stopPropagation()}>
                <div className="bg-blue-600 text-white px-5 py-3.5 rounded-t-2xl flex items-center gap-2 shrink-0"><FileText size={18} /><h2 className="font-semibold">{editingItem ? "编辑开销" : "添加开销"} - {expenseAccount?.employee_name}</h2><button disabled={expenseBusy} onClick={() => { setShowExpense(false); setReceiptFile(null); }} className="ml-auto text-blue-200 hover:text-white text-lg leading-none">&times;</button></div>
                <div className="p-5 space-y-3 overflow-y-auto min-h-0">
                  <div className="grid grid-cols-2 gap-2">
                    <div className="bg-blue-50 rounded-lg p-2.5 text-center"><div className="text-[10px] text-blue-500">累计拨付</div><div className="text-sm font-bold text-blue-700">{fmtMoney(expenseAccount?.total_topped_up, expenseAccount?.currency)}</div></div>
                    <div className="bg-gray-50 rounded-lg p-2.5 text-center"><div className="text-[10px] text-gray-400">可用余额</div><div className="text-sm font-bold text-gray-700">{fmtMoney(Math.max(0, (expenseAccount?.available ?? expenseAccount?.current_balance ?? 0)), expenseAccount?.currency)}</div></div>
                  </div>
                  <div><label className="form-label">日期</label><input type="date" className="form-input" value={itemForm.expense_date} onChange={e => setItemForm({ ...itemForm, expense_date: e.target.value })} /></div>
                  <div><label className="form-label">类别</label><select className="form-input" value={itemForm.category} onChange={e => setItemForm({ ...itemForm, category: e.target.value })}><option>耗材</option><option>交通费</option><option>餐饮</option><option>办公用品</option><option>维修</option><option>其他</option></select></div>
                  <div className="grid grid-cols-2 gap-3">
                    <div><label className="form-label">金额</label><input type="number" className="form-input" value={itemForm.amount} onChange={e => setItemForm({ ...itemForm, amount: e.target.value === "" ? "" : +e.target.value })} /></div>
                    <div><label className="form-label">币种</label><select disabled={!!editingItem} className="form-input" value={itemForm.currency} onChange={e => setItemForm({ ...itemForm, currency: e.target.value })}><option value="THB">THB 泰铢</option><option value="CNY">CNY 人民币</option></select></div>
                  </div>
                  {cost.fields}
                  <div><label className="form-label">说明</label><input className="form-input" value={itemForm.description} onChange={e => setItemForm({ ...itemForm, description: e.target.value })} /></div>
                  <div><label className="form-label" htmlFor="receiptFileInput4">凭证照片（必填）</label>
                    {editingItem?.receipt && <p className="text-xs text-gray-500 mb-1">已有凭证会保留，选择新照片才替换。<button type="button" className="text-blue-600 ml-2" onClick={() => setPreviewUrl(editingItem.receipt)}>查看当前凭证</button></p>}
                    <div className="border-2 border-dashed border-gray-200 rounded-lg p-3 text-center hover:border-blue-400 transition-colors cursor-pointer" onClick={() => document.getElementById("receiptFileInput4")?.click()}>
                      {receiptFile ? <div className="flex items-center gap-2 text-sm text-blue-600"><Image size={16} />{receiptFile.name}</div> : <div className="text-gray-400 text-sm"><Camera size={22} className="mx-auto mb-1 text-gray-300" />点击上传截图</div>}
                      <input id="receiptFileInput4" type="file" accept="image/*" disabled={expenseBusy} className="hidden" onChange={e => setReceiptFile(e.target.files?.[0] || null)} />
                    </div>
                    <div className="flex gap-3 text-xs mt-2"><button type="button" disabled={expenseBusy} onClick={() => document.getElementById("receiptCameraInput4")?.click()} className="text-blue-600">拍照</button><button type="button" disabled={expenseBusy} onClick={() => document.getElementById("receiptFileInput4")?.click()} className="text-blue-600">相册 / 文件</button></div>
                    <input id="receiptCameraInput4" aria-label="拍摄开销凭证" type="file" accept="image/*" capture="environment" disabled={expenseBusy} className="hidden" onChange={e => setReceiptFile(e.target.files?.[0] || null)} />
                    <p className="mt-1 text-xs text-gray-500">必须上传凭证，没有凭证不能报销。照片不超过10MB。</p>
                  </div>
                </div>
                <div className="border-t px-5 py-3.5 bg-gray-50 rounded-b-2xl flex flex-wrap justify-end gap-3 shrink-0">
                  <button disabled={expenseBusy} onClick={() => { setShowExpense(false); setReceiptFile(null); }} className="btn-secondary text-sm whitespace-nowrap shrink-0">取消</button>
                  <button disabled={expenseBusy} onClick={()=>doAddExpense()} className="btn-primary text-sm">{expenseBusy ? "保存中..." : "保存"}</button>
                </div>
              </div>
            </div>
          )}
        </>
      )}

      {/* Top-up modal */}
      {showTopUp && (
        <div className="modal-overlay z-50" onClick={() => setShowTopUp(false)}>
          <div className="bg-white rounded-2xl w-full max-w-sm shadow-2xl max-h-[90dvh] overflow-y-auto" onClick={e => e.stopPropagation()}>
            <div className="bg-green-600 text-white px-5 py-3.5 rounded-t-2xl flex items-center gap-2"><ArrowUp size={18} /><h2 className="font-semibold">充值备用金</h2><button onClick={() => setShowTopUp(false)} className="ml-auto text-green-200 hover:text-white text-lg leading-none">&times;</button></div>
            <div className="p-5 space-y-4">
              <div className="bg-green-50 rounded-lg p-3">
                <div className="text-xs text-green-600 mb-1">{topUpAccount?.employee_name}</div>
                <div className="flex items-center justify-between text-sm"><span className="text-gray-500">当前余额</span><span className="font-bold text-green-700">{fmtMoney(topUpAccount?.available ?? topUpAccount?.current_balance, topUpAccount?.currency)}</span></div>
                <div className="flex items-center justify-between text-sm mt-1"><span className="text-gray-500">账户上限</span><span className="font-medium text-gray-700">{fmtMoney(topUpAccount?.fund_limit || 5000, topUpAccount?.currency)}</span></div>{!isAdmin && (<div className="mt-3"><label className="form-label text-xs">充值事由</label><input className="form-input text-sm" value={topUpReason} onChange={e => setTopUpReason(e.target.value)} placeholder="请输入充值原因" /></div>)}
              </div>
              <div><label className="form-label">充值金额</label><input type="number" className="form-input text-lg font-bold" value={topUpAmount} onChange={e => setTopUpAmount(e.target.value)} placeholder="输入金额" autoFocus readOnly={rechargeReviewId !== null} /></div>
              {isAdmin && <>
                <div><label className="form-label">拨付日期</label><input aria-label="拨付日期" type="date" className="form-input" value={topUpDate} onChange={e => setTopUpDate(e.target.value)} /></div>
                <div><label className="form-label">公司付款账户</label><select aria-label="公司付款账户" className="form-input" value={paymentAccountId} onChange={e => setPaymentAccountId(e.target.value)}><option value="">请选择备用金拨付账户</option>{paymentAccounts.map(a => <option key={a.id} value={a.id}>{a.account_name}（{fmtMoney(a.current_balance, a.currency)}）</option>)}</select>
                {!paymentAccounts.length && <p className="text-xs text-red-500 mt-1">没有同币种可用账户，请先到收款账户中建立或启用账户</p>}</div>
              </>}
            </div>
            <div className="border-t px-5 py-3.5 bg-gray-50 rounded-b-2xl flex flex-wrap justify-end gap-3">
              <button onClick={() => setShowTopUp(false)} className="btn-secondary text-sm whitespace-nowrap shrink-0">取消</button>
              {isAdmin&&<p role="alert" className="order-first w-full text-sm text-red-600">{balanceWarningText(paymentAccounts.find((a:any)=>String(a.id)===paymentAccountId)?.current_balance,topUpAmount)}</p>}
              <button onClick={doTopUp} disabled={topUpBusy || (isAdmin && !paymentAccounts.length)} className="btn-primary text-sm whitespace-nowrap shrink-0 bg-green-600 hover:bg-green-700">{topUpBusy ? "提交中…" : "确认充值"}</button>
            </div>
          </div>
        </div>
      )}


      {/* ========== REVIEW TAB ========== */}
      {tab === "review" && (
        <>
          {/* Sub-tabs */}
          <div className="flex items-center gap-1 mb-4 bg-white rounded-xl p-1 shadow-sm border border-gray-100 w-fit">
            <button onClick={() => setReviewTab("expense")}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-all flex items-center gap-1.5 ${reviewTab === "expense" ? "bg-blue-600 text-white shadow-sm" : "text-gray-500 hover:text-gray-700"}`}>
              <ClipboardCheck size={15} />开销审核
              {reviewData.length > 0 && <span className={`ml-1 px-1.5 py-0.5 rounded-full text-[11px] font-bold ${reviewTab === "expense" ? "bg-blue-500 text-white" : "bg-red-500 text-white"}`}>{reviewData.length}</span>}
            </button>
            <button onClick={() => setReviewTab("recharge")}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-all flex items-center gap-1.5 ${reviewTab === "recharge" ? "bg-blue-600 text-white shadow-sm" : "text-gray-500 hover:text-gray-700"}`}>
              <CreditCard size={15} />充值申请
              {rechargeData.length > 0 && <span className={`ml-1 px-1.5 py-0.5 rounded-full text-[11px] font-bold ${reviewTab === "recharge" ? "bg-blue-500 text-white" : "bg-red-500 text-white"}`}>{rechargeData.length}</span>}
            </button>
          </div>

          {/* Expenses Review */}
          {reviewTab === "expense" && (
          <div>
          <div className="mb-4 text-sm text-gray-400">{reviewData.length} 条待审核</div>

          {/* 筛选栏 */}
          <div className="bg-white rounded-xl shadow-sm border border-gray-100 px-5 py-3 mb-4">
            <div className="flex items-center gap-3 flex-wrap">
              <div className="flex items-center gap-1.5">
                <label className="text-xs text-gray-500 whitespace-nowrap">员工</label>
                <select className="form-input text-sm py-1.5 w-36" value={selEmployee} onChange={e => setSelEmployee(e.target.value)}>
                  <option value="">全部</option>
                  {reviewEmployees.map((e: any) => <option key={e.id} value={e.id}>{e.name}</option>)}
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
                  <option value="">全部</option><option value="THB">THB</option><option value="CNY">CNY</option>
                </select>
              </div>
              <button onClick={loadReviews} className="btn-primary text-sm flex items-center gap-1 py-1.5"><Search size={14} />查询</button>
              {selectedIds.size > 0 && (
                <div className="flex items-center gap-2 ml-auto">
                  <button onClick={() => doReview("approve")} className="btn-primary text-sm bg-green-600 hover:bg-green-700 flex items-center gap-1"><CheckC size={15} />通过所选 ({selectedIds.size})</button>
                  <button onClick={() => doReview("reject")} className="btn-secondary text-sm text-red-600 border-red-300 hover:bg-red-50 flex items-center gap-1"><XCircle size={15} />驳回所选</button>
                  <input className="form-input text-sm py-1 w-36" placeholder="驳回原因" value={rejectRemark} onChange={e => setRejectRemark(e.target.value)} />
                </div>
              )}
            </div>
          </div>

          {/* 审核表格 */}
          <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
            {reviewLoading ? (
              <div className="flex items-center justify-center h-40 text-gray-400"><div className="animate-spin w-5 h-5 border-2 border-blue-600 border-t-transparent rounded-full mr-2" />加载中...</div>
            ) : reviewData.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16 text-gray-400"><FileText size={44} className="text-gray-200 mb-3" /><span className="text-sm">暂无待审核记录</span></div>
            ) : (
              <div className="overflow-x-auto touch-pan-x">
                <table className="w-full text-sm min-w-[900px]">
                  <thead>
                    <tr className="border-b bg-gray-50">
                      <th className="text-left px-2 py-3 w-10"><input type="checkbox" checked={selectedIds.size === reviewData.length && reviewData.length > 0} onChange={toggleAllReview} className="rounded" /></th>
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
                    {reviewData.map((row: any) => (
                      <tr key={row.id} className={`border-b hover:bg-gray-50/50 ${selectedIds.has(row.id) ? "bg-blue-50" : ""}`}>
                        <td className="px-2 py-3"><input type="checkbox" checked={selectedIds.has(row.id)} onChange={() => toggleOneReview(row.id)} className="rounded" /></td>
                        <td className="px-3 py-3 font-medium text-gray-800">{row.employee_name}</td>
                        <td className="px-3 py-3 text-gray-500">{row.warehouse_name}</td>
                        <td className="px-3 py-3 text-right text-gray-500">{fmtMoney(row.fund_limit || 5000, row.fund_currency)}</td>
                        <td className="px-3 py-3 text-gray-500">{row.receive_date?.slice(0, 10) || "-"}</td>
                        <td className="px-3 py-3">{row.expense_date?.slice(0, 10)}</td>
                        <td className="px-3 py-3">{row.category}</td>
                        <td className="px-3 py-3 text-right font-medium">{row.currency === "CNY" ? "¥" : "฿"}{row.amount?.toLocaleString()}</td>
                        <td className="px-3 py-3 text-center"><span className={`px-1.5 py-0.5 rounded text-xs ${row.currency === "CNY" ? "bg-red-50 text-red-600" : "bg-blue-50 text-blue-600"}`}>{row.currency || "THB"}</span></td>
                        <td className="px-3 py-3 text-gray-600 max-w-[140px] truncate">{row.description}</td>
                        <td className="px-3 py-3 text-center">
                          {row.receipt ? (
                            <button onClick={() => setPreviewUrl(row.receipt)} className="text-blue-500 hover:text-blue-700" title="点击查看凭证"><Eye size={16} /></button>
                          ) : <span className="text-gray-300">-</span>}
                        </td>
                        <td className="px-3 py-3 text-center"><span className="px-2 py-0.5 rounded-full text-xs bg-yellow-50 text-yellow-700 font-medium">待审核</span></td>
                        <td className="px-3 py-3 text-center">
                          <div className="flex items-center justify-center gap-1.5">
                            <button onClick={() => approveOne(row.id)} className="p-1 rounded hover:bg-green-50 text-green-600 transition-colors" title="通过"><CheckC size={16} /></button>
                            <button onClick={() => rejectOne(row.id)} className="p-1 rounded hover:bg-red-50 text-red-500 transition-colors" title="驳回"><XCircle size={16} /></button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
          </div>
          )}

          {/* Recharge Requests Review */}
          {reviewTab === "recharge" && (
            <div>
              <div className="bg-white rounded-xl shadow-sm border border-gray-100 px-5 py-3 mb-4">
                <div className="text-sm text-gray-500">{rechargeData.length} 条待审核充值申请</div>
              </div>
              <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
                {rechargeLoading ? (
                  <div className="flex items-center justify-center h-24 text-gray-400">
                    <div className="animate-spin w-5 h-5 border-2 border-blue-600 border-t-transparent rounded-full mr-2" />加载中...
                  </div>
                ) : rechargeData.length === 0 ? (
                  <div className="text-center py-12 text-gray-400 text-sm">暂无待审核的充值申请</div>
                ) : (
                  <div className="overflow-x-auto touch-pan-x">
                    <table className="w-full text-sm min-w-[900px]">
                      <thead>
                        <tr className="border-b bg-gray-50">
                          <th className="text-left px-3 py-3 font-medium text-gray-500">申请人</th>
                          <th className="text-right px-3 py-3 font-medium text-gray-500">申请金额</th>
                          <th className="text-right px-3 py-3 font-medium text-gray-500">当前余额</th>
                          <th className="text-left px-3 py-3 font-medium text-gray-500">事由</th>
                          <th className="text-left px-3 py-3 font-medium text-gray-500">申请时间</th>
                          <th className="text-center px-3 py-3 font-medium text-gray-500">状态</th>
                          <th className="text-center px-3 py-3 font-medium text-gray-500 w-24">操作</th>
                        </tr>
                      </thead>
                      <tbody>
                        {rechargeData.map((r: any) => (
                          <tr key={r.id} className="border-b hover:bg-gray-50/50">
                            <td className="px-3 py-3 font-medium text-gray-800">{r.applicant_name}</td>
                            <td className="px-3 py-3 text-right font-medium text-green-700">+{fmtMoney(r.amount, r.currency)}</td>
                            <td className="px-3 py-3 text-right text-gray-500">{fmtMoney(r.current_balance, r.currency)}</td>
                            <td className="px-3 py-3 text-gray-600 max-w-[200px] truncate">{r.reason || "-"}</td>
                            <td className="px-3 py-3 text-gray-500">{r.created_at ? new Date(r.created_at).toLocaleString("zh-CN") : "-"}</td>
                            <td className="px-3 py-3 text-center">
                              <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${r.status === "pending" ? "bg-yellow-50 text-yellow-700" : r.status === "approved" ? "bg-green-50 text-green-700" : "bg-red-50 text-red-600"}`}>
                                {r.status === "pending" ? "待审核" : r.status === "approved" ? "已通过" : "已驳回"}
                              </span>
                            </td>
                            <td className="px-3 py-3 text-center">
                              {r.status === "pending" && (
                                <div className="flex items-center justify-center gap-1.5">
                                  <button onClick={() => approveRecharge(r.id)} className="p-1 rounded hover:bg-green-50 text-green-600" title="通过"><CheckC size={16} /></button>
                                  <button onClick={() => rejectRecharge(r.id)} className="p-1 rounded hover:bg-red-50 text-red-500" title="驳回"><XCircle size={16} /></button>
                                </div>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </div>
          )}

        </>
      )}
      {previewUrl && <div role="dialog" aria-modal="true" aria-label="开销凭证大图" className="modal-overlay z-[120]" onClick={() => setPreviewUrl(null)}>
        <div className="bg-white rounded-2xl w-full max-w-2xl max-h-[90dvh] overflow-auto shadow-2xl" onClick={e => e.stopPropagation()}>
          <div className="flex items-center justify-between px-5 py-3 border-b"><h3 className="font-semibold text-gray-700 flex items-center gap-2"><Image size={18} />凭证查看</h3><div className="flex items-center gap-3"><a href={previewUrl} target="_blank" rel="noreferrer" className="text-sm text-blue-600">查看原图</a><button aria-label="关闭凭证大图" onClick={() => setPreviewUrl(null)} className="text-gray-400 hover:text-gray-600"><X size={20} /></button></div></div>
          <div className="p-4 flex items-center justify-center bg-gray-100"><img src={previewUrl} alt="开销凭证" className="max-w-full max-h-[70vh] object-contain rounded" /></div>
        </div>
      </div>}
      {voidTarget && <div role="dialog" aria-modal="true" aria-label="作废备用金开销" className="modal-overlay z-[120]" onClick={() => { if (!voidBusy) setVoidTarget(null); }}><div className="bg-white rounded-2xl w-full max-w-md max-h-[90dvh] overflow-y-auto p-5 space-y-4" onClick={e => e.stopPropagation()}>
        <h3 className="font-semibold">确认作废这条开销？</h3><p className="text-sm">开销 #{voidTarget.item.id} · {fmtMoney(voidTarget.item.amount, voidTarget.item.currency)}</p><p className="text-sm text-gray-500">作废后记录保留，不再计入备用金台账。已审核通过的开销不能作废。</p>
        <label className="block text-sm">作废原因（必填）<textarea aria-label="开销作废原因" className="form-input mt-1" rows={3} maxLength={500} disabled={voidBusy} value={voidReason} onChange={e => setVoidReason(e.target.value)} /></label>
        <div className="flex justify-end gap-3"><button type="button" disabled={voidBusy} className="btn-secondary" onClick={() => setVoidTarget(null)}>取消</button><button type="button" disabled={voidBusy} className="btn-primary" onClick={doVoidExpense}>{voidBusy ? "作废中..." : "确认作废"}</button></div>
      </div></div>}
    </>
  );
}

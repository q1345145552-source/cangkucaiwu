"use client";
import { useEffect, useState } from "react";
import { api, getToken } from "@/lib/api";
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
  const [showExpense, setShowExpense] = useState(false);
  const [expenseAccount, setExpenseAccount] = useState<any>(null);
  const [itemForm, setItemForm] = useState({ expense_date: new Date().toISOString().slice(0, 10), category: "耗材", amount: "", currency: "THB", description: "" });
  const [receiptFile, setReceiptFile] = useState<File | null>(null);

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
  }

  async function doCreate() {
    if (!newEmpId) { toast("error", "请选择员工"); return; }
    try {
      const r = await api.post("/expense-fund/accounts", { employee_id: +newEmpId, fund_limit: newLimit ? +newLimit : undefined });
      toast("success", r.message || "创建成功");
      setShowCreate(false); setNewEmpId(""); setNewLimit("");
      loadAll();
    } catch (err: any) { toast("error", err.message || "创建失败"); }
  }

  function openTopUp(acc: any) { setTopUpAccount(acc); setTopUpAmount(""); setTopUpReason(""); setShowTopUp(true); }
  async function doTopUp() {
    if (!topUpAccount || !topUpAmount) return;
    try {
      if (isAdmin) {
        // 管理员直接充值
        const r = await api.post(`/expense-fund/accounts/${topUpAccount.id}/topup`, { amount: +topUpAmount });
        toast("success", r.message || "充值成功");
      } else {
        // 财务提交充值申请
        const r = await api.post("/expense-fund/recharge/request", { amount: +topUpAmount, reason: topUpReason });
        toast("success", r.message || "充值申请已提交");
      }
      setShowTopUp(false); setTopUpAmount(""); setTopUpReason(""); setTopUpReason("");
      loadAccounts();
      if (expandedId === topUpAccount.id) toggleExpand(topUpAccount);
    } catch (err: any) { toast("error", err.message || "充值失败"); }
  }

  function openExpense(acc: any) {
    setExpenseAccount(acc);
    setItemForm({ expense_date: new Date().toISOString().slice(0, 10), category: "耗材", amount: "", currency: "THB", description: "" });
    setReceiptFile(null);
    setShowExpense(true);
  }
  async function doAddExpense() {
    if (!expenseAccount) return;
    try {
      const res = await api.post<any>(`/expense-fund/accounts/${expenseAccount.id}/items`, { ...itemForm, amount: itemForm.amount || 0, currency: itemForm.currency });
      if (receiptFile && res.id) {
        const fd = new FormData(); fd.append("file", receiptFile);
        await fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1"}/expense-fund/accounts/${expenseAccount.id}/items/${res.id}/upload-receipt`, {
          method: "POST", headers: { "Authorization": `Bearer ${getToken()}` }, body: fd,
        });
      }
      toast("success", "开销添加成功");
      setShowExpense(false);
      if (expandedId === expenseAccount.id) toggleExpand(expenseAccount);
    } catch (err: any) { toast("error", err.message || "添加失败"); }
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

  async function doReview(action: "approve" | "reject") {
    if (selectedIds.size === 0) { toast("error", "请先勾选要审核的记录"); return; }
    try {
      await api.post("/expense-fund/review/batch", { item_ids: Array.from(selectedIds), action, remark: action === "reject" ? rejectRemark : undefined });
      toast("success", action === "approve" ? "已批量通过" : "已批量驳回");
      setRejectRemark(""); loadReviews();
    } catch (err: any) { toast("error", err.message || "审核失败"); }
  }

  async function approveOne(id: number) {
    try {
      await api.post("/expense-fund/review/batch", { item_ids: [id], action: "approve" });
      toast("success", "已通过"); loadReviews();
    } catch (err: any) { toast("error", err.message || "审核失败"); }
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
    try {
      await api.post("/expense-fund/recharge/review", { request_id: reqId, action: "approve" });
      toast("success", "充值申请已通过");
      loadRechargeRequests();
    } catch (err: any) { toast("error", err.message || "审核失败"); }
  }
  function rejectRecharge(reqId: number) {
    const reason = prompt("请输入驳回原因");
    if (reason === null) return;
    (async () => {
      try {
        await api.post("/expense-fund/recharge/review", { request_id: reqId, action: "reject", remark: reason });
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
  const totalBalance = accounts.reduce((s: number, a: any) => s + (a.current_balance || 0), 0);
  const totalSpent = accounts.reduce((s: number, a: any) => s + (a.total_spent || 0), 0);
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
              <div className="text-2xl font-bold text-blue-700">฿{totalBalance.toLocaleString()}</div>
            </div>
            <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-4">
              <div className="flex items-center gap-2 text-xs text-gray-400 mb-2"><TrendingUp size={14} />累计开销</div>
              <div className="text-2xl font-bold text-yellow-700">฿{totalSpent.toLocaleString()}</div>
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
              <table className="w-full text-sm">
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
                    const accSpent = accItems.reduce((s: number, i: any) => s + (i.amount || 0), 0);
                    const accAvailable = Math.max(0, (acc.current_balance || 0) - accSpent);
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
                          <td className="px-4 py-3 text-right font-mono text-sm">฿{(acc.total_topped_up || 0).toLocaleString()}</td>
                          <td className="px-4 py-3 text-right font-mono text-sm text-yellow-700">฿{accSpent.toLocaleString()}</td>
                          <td className={`px-4 py-3 text-right font-mono text-sm font-semibold ${accAvailable <= 0 ? "text-red-600" : "text-green-700"}`}>฿{accAvailable.toLocaleString()}</td>
                          <td className="px-4 py-3 text-right font-mono text-sm text-gray-500">฿{(acc.fund_limit || 5000).toLocaleString()}</td>
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
                                <table className="w-full text-xs">
                                  <thead>
                                    <tr className="border-b bg-gray-100/50">
                                      <th className="text-left px-2 py-1.5 text-gray-500">日期</th>
                                      <th className="text-left px-2 py-1.5 text-gray-500">类别</th>
                                      <th className="text-right px-2 py-1.5 text-gray-500">金额</th>
                                      <th className="text-center px-2 py-1.5 text-gray-500 w-12">币种</th>
                                      <th className="text-left px-2 py-1.5 text-gray-500">说明</th>
                                      <th className="text-center px-2 py-1.5 text-gray-500">审核</th>
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {accItems.map((it: any) => (
                                      <tr key={it.id} className="border-b border-gray-100">
                                        <td className="px-2 py-1.5">{it.expense_date?.slice(0, 10)}</td>
                                        <td className="px-2 py-1.5">{it.category}</td>
                                        <td className="px-2 py-1.5 text-right font-mono">{it.currency === "CNY" ? "¥" : "฿"}{it.amount?.toLocaleString()}</td>
                                        <td className="px-2 py-1.5 text-center"><span className={`px-1 py-0.5 rounded text-[10px] ${it.currency === "CNY" ? "bg-red-50 text-red-600" : "bg-blue-50 text-blue-600"}`}>{it.currency || "THB"}</span></td>
                                        <td className="px-2 py-1.5 text-gray-500">{it.description}</td>
                                        <td className="px-2 py-1.5 text-center">
                                          <span className={`px-1.5 py-0.5 rounded text-[10px] ${it.review_status === "approved" ? "bg-green-50 text-green-600" : it.review_status === "rejected" ? "bg-red-50 text-red-600" : "bg-yellow-50 text-yellow-600"}`}>
                                            {it.review_status === "approved" ? "已通过" : it.review_status === "rejected" ? "已驳回" : "待审核"}
                                          </span>
                                        </td>
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                              )}
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
                                          <span className="font-medium text-green-700">+฿{r.amount?.toLocaleString()}</span>
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
                <div className="border-t px-5 py-3.5 bg-gray-50 rounded-b-2xl flex justify-end gap-3">
                  <button onClick={() => setShowCreate(false)} className="btn-secondary text-sm">取消</button>
                  <button onClick={doCreate} className="btn-primary text-sm">创建</button>
                </div>
              </div>
            </div>
          )}

          {/* Top-up modal */}
          {showTopUp && (
            <div className="modal-overlay z-50" onClick={() => setShowTopUp(false)}>
              <div className="bg-white rounded-2xl w-full max-w-sm shadow-2xl" onClick={e => e.stopPropagation()}>
                <div className="bg-green-600 text-white px-5 py-3.5 rounded-t-2xl flex items-center gap-2"><ArrowUp size={18} /><h2 className="font-semibold">充值备用金</h2><button onClick={() => setShowTopUp(false)} className="ml-auto text-green-200 hover:text-white text-lg leading-none">&times;</button></div>
                <div className="p-5 space-y-4">
                  <div className="bg-green-50 rounded-lg p-3">
                    <div className="text-xs text-green-600 mb-1">{topUpAccount?.employee_name}</div>
                    <div className="flex items-center justify-between text-sm"><span className="text-gray-500">当前余额</span><span className="font-bold text-green-700">฿{(topUpAccount?.current_balance || 0).toLocaleString()}</span></div>
                    <div className="flex items-center justify-between text-sm mt-1"><span className="text-gray-500">账户上限</span><span className="font-medium text-gray-700">฿{(topUpAccount?.fund_limit || 5000).toLocaleString()}</span></div>{!isAdmin && (<div className="mt-3"><label className="form-label text-xs">充值事由</label><input className="form-input text-sm" value={topUpReason} onChange={e => setTopUpReason(e.target.value)} placeholder="请输入充值原因" /></div>)}
                  </div>
                  <div><label className="form-label">充值金额</label><input type="number" className="form-input text-lg font-bold" value={topUpAmount} onChange={e => setTopUpAmount(e.target.value)} placeholder="输入金额" autoFocus /></div>
                </div>
                <div className="border-t px-5 py-3.5 bg-gray-50 rounded-b-2xl flex justify-end gap-3">
                  <button onClick={() => setShowTopUp(false)} className="btn-secondary text-sm">取消</button>
                  <button onClick={doTopUp} className="btn-primary text-sm bg-green-600 hover:bg-green-700">确认充值</button>
                </div>
              </div>
            </div>
          )}

          {/* Expense modal */}
          {showExpense && (
            <div className="modal-overlay z-50" onClick={() => { setShowExpense(false); setReceiptFile(null); }}>
              <div className="bg-white rounded-2xl w-full max-w-md shadow-2xl" onClick={e => e.stopPropagation()}>
                <div className="bg-blue-600 text-white px-5 py-3.5 rounded-t-2xl flex items-center gap-2"><FileText size={18} /><h2 className="font-semibold">添加开销 - {expenseAccount?.employee_name}</h2><button onClick={() => { setShowExpense(false); setReceiptFile(null); }} className="ml-auto text-blue-200 hover:text-white text-lg leading-none">&times;</button></div>
                <div className="p-5 space-y-3">
                  <div className="grid grid-cols-2 gap-2">
                    <div className="bg-blue-50 rounded-lg p-2.5 text-center"><div className="text-[10px] text-blue-500">账户余额</div><div className="text-sm font-bold text-blue-700">฿{(expenseAccount?.current_balance || 0).toLocaleString()}</div></div>
                    <div className="bg-gray-50 rounded-lg p-2.5 text-center"><div className="text-[10px] text-gray-400">可用余额</div><div className="text-sm font-bold text-gray-700">฿{Math.max(0, (expenseAccount?.current_balance || 0) - (expenseAccount?.total_spent || 0)).toLocaleString()}</div></div>
                  </div>
                  <div><label className="form-label">日期</label><input type="date" className="form-input" value={itemForm.expense_date} onChange={e => setItemForm({ ...itemForm, expense_date: e.target.value })} /></div>
                  <div><label className="form-label">类别</label><select className="form-input" value={itemForm.category} onChange={e => setItemForm({ ...itemForm, category: e.target.value })}><option>耗材</option><option>交通费</option><option>餐饮</option><option>办公用品</option><option>维修</option><option>其他</option></select></div>
                  <div className="grid grid-cols-2 gap-3">
                    <div><label className="form-label">金额</label><input type="number" className="form-input" value={itemForm.amount} onChange={e => setItemForm({ ...itemForm, amount: e.target.value === "" ? "" : +e.target.value })} /></div>
                    <div><label className="form-label">币种</label><select className="form-input" value={itemForm.currency} onChange={e => setItemForm({ ...itemForm, currency: e.target.value })}><option value="THB">THB 泰铢</option><option value="CNY">CNY 人民币</option></select></div>
                  </div>
                  <div><label className="form-label">说明</label><input className="form-input" value={itemForm.description} onChange={e => setItemForm({ ...itemForm, description: e.target.value })} /></div>
                  <div><label className="form-label">凭证截图（非必填）</label>
                    <div className="border-2 border-dashed border-gray-200 rounded-lg p-3 text-center hover:border-blue-400 transition-colors cursor-pointer" onClick={() => document.getElementById("receiptFileInput4")?.click()}>
                      {receiptFile ? <div className="flex items-center gap-2 text-sm text-blue-600"><Image size={16} />{receiptFile.name}</div> : <div className="text-gray-400 text-sm"><Camera size={22} className="mx-auto mb-1 text-gray-300" />点击上传截图</div>}
                      <input id="receiptFileInput4" type="file" accept="image/*" className="hidden" onChange={e => setReceiptFile(e.target.files?.[0] || null)} />
                    </div>
                  </div>
                </div>
                <div className="border-t px-5 py-3.5 bg-gray-50 rounded-b-2xl flex justify-end gap-3">
                  <button onClick={() => { setShowExpense(false); setReceiptFile(null); }} className="btn-secondary text-sm">取消</button>
                  <button onClick={doAddExpense} className="btn-primary text-sm">保存</button>
                </div>
              </div>
            </div>
          )}
        </>
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
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
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
                        <td className="px-3 py-3 text-right text-gray-500">฿{(row.fund_limit || 5000).toLocaleString()}</td>
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
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
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
                            <td className="px-3 py-3 text-right font-medium text-green-700">+฿{r.amount?.toLocaleString()}</td>
                            <td className="px-3 py-3 text-right text-gray-500">฿{(r.current_balance || 0).toLocaleString()}</td>
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

          {/* Receipt preview modal */}
          {previewUrl && (
            <div className="modal-overlay z-50" onClick={() => setPreviewUrl(null)}>
              <div className="bg-white rounded-2xl max-w-2xl max-h-[85vh] overflow-auto shadow-2xl" onClick={e => e.stopPropagation()}>
                <div className="flex items-center justify-between px-5 py-3 border-b">
                  <h3 className="font-semibold text-gray-700 flex items-center gap-2"><Image size={18} />凭证查看</h3>
                  <button onClick={() => setPreviewUrl(null)} className="text-gray-400 hover:text-gray-600"><X size={20} /></button>
                </div>
                <div className="p-4 flex items-center justify-center bg-gray-100"><img src={previewUrl} alt="凭证" className="max-w-full max-h-[70vh] object-contain rounded" /></div>
              </div>
            </div>
          )}
        </>
      )}
    </>
  );
}

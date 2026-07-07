"use client";
import { useEffect, useState } from "react";
import { api, getToken } from "@/lib/api";
import { useToast } from "@/components/ui/Toast";
import { useRouter } from "next/navigation";
import { useAuth } from "@/hooks/useAuth";
import { Plus, Package, Clock, Users, MapPin, TrendingUp, TrendingDown, Ban, X, CheckCircle, ChevronDown, ChevronUp, Truck, ShoppingCart, DollarSign, Calendar } from "lucide-react";

const STATUS_CN: Record<string, string> = {
  open: "开放中", closed: "已截止", completed: "已完成", cancelled: "已取消",
};
const STATUS_COLOR: Record<string, string> = {
  open: "bg-green-50 text-green-700 border-green-200",
  closed: "bg-yellow-50 text-yellow-700 border-yellow-200",
  completed: "bg-blue-50 text-blue-700 border-blue-200",
  cancelled: "bg-gray-100 text-gray-500 border-gray-200",
};
const STATUS_BG: Record<string, string> = {
  open: "bg-green-600", closed: "bg-yellow-600", completed: "bg-blue-600", cancelled: "bg-gray-400",
};

export default function GroupOrderPage() {
  const router = useRouter(); const { user } = useAuth(); const { toast } = useToast();
  const [orders, setOrders] = useState<any[]>([]);
  const [history, setHistory] = useState<any[]>([]);
  const [tab, setTab] = useState<"active" | "history">("active");
  const [loading, setLoading] = useState(false);

  // Create form
  const [showCreate, setShowCreate] = useState(false);
  const [createForm, setCreateForm] = useState({ item_name: "", specification: "", target_quantity: "", target_price: "", deadline: "", reason: "" });

  // Join modal
  const [showJoin, setShowJoin] = useState(false);
  const [joinTarget, setJoinTarget] = useState<any>(null);
  const [joinForm, setJoinForm] = useState({ quantity: "", delivery_address: "", agreed_rules: false });

  // Detail modal
  const [showDetail, setShowDetail] = useState(false);
  const [detail, setDetail] = useState<any>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  // Complete modal
  const [showComplete, setShowComplete] = useState(false);
  const [completeTarget, setCompleteTarget] = useState<any>(null);
  const [completeForm, setCompleteForm] = useState({ final_price: "", final_supplier: "", logistics_fee: "" });

  // Cancel modal
  const [showCancel, setShowCancel] = useState(false);
  const [cancelTarget, setCancelTarget] = useState<any>(null);
  const [cancelReason, setCancelReason] = useState("");

  // Expanded history items
  const [expandedHistory, setExpandedHistory] = useState<Set<number>>(new Set());

  useEffect(() => { if (!getToken()) router.push("/login"); load(); }, [tab]);

  async function load() {
    setLoading(true);
    try {
      if (tab === "history") {
        const r = await api.get<any>("/group-order/history?page_size=100");
        setHistory(r.data || []);
      } else {
        const r = await api.get<any>("/group-order?page_size=100");
        setOrders(r.data || []);
      }
    } catch (err) { console.error("加载失败:", err); }
    setLoading(false);
  }

  async function handleCreate() {
    if (!createForm.item_name || !createForm.target_quantity || !createForm.target_price || !createForm.deadline) {
      toast("error", "请填写完整信息"); return;
    }
    try {
      await api.post("/group-order", {
        ...createForm,
        target_quantity: Number(createForm.target_quantity),
        target_price: Number(createForm.target_price),
      });
      toast("success", "拼单发起成功");
      setShowCreate(false);
      setCreateForm({ item_name: "", specification: "", target_quantity: "", target_price: "", deadline: "", reason: "" });
      load();
    } catch (err: any) { toast("error", err.message || "发起失败"); }
  }

  function openJoin(order: any) {
    setJoinTarget(order);
    setJoinForm({ quantity: "", delivery_address: "", agreed_rules: false });
    setShowJoin(true);
  }

  async function handleJoin() {
    if (!joinForm.quantity || Number(joinForm.quantity) <= 0) { toast("error", "请输入有效数量"); return; }
    if (!joinForm.agreed_rules) { toast("error", "请先确认拼单规则"); return; }
    try {
      await api.post(`/group-order/${joinTarget.id}/join`, {
        quantity: Number(joinForm.quantity),
        delivery_address: joinForm.delivery_address,
        agreed_rules: true,
      });
      toast("success", "参与成功");
      setShowJoin(false); load();
    } catch (err: any) { toast("error", err.message || "参与失败"); }
  }

  async function openDetail(orderId: number) {
    setDetailLoading(true); setShowDetail(true);
    try {
      const r = await api.get<any>(`/group-order/${orderId}`);
      setDetail(r);
    } catch (err: any) { toast("error", "加载详情失败"); setShowDetail(false); }
    setDetailLoading(false);
  }

  async function handleClose(orderId: number) {
    try {
      const r = await api.put<any>(`/group-order/${orderId}/close`, {});
      toast("success", r.summary ? `已截止，共 ${r.summary.total_quantity} 件` : "截至成功");
      load();
    } catch (err: any) { toast("error", err.message || "操作失败"); }
  }

  function openComplete(order: any) {
    setCompleteTarget(order);
    setCompleteForm({ final_price: "", final_supplier: "", logistics_fee: "" });
    setShowComplete(true);
  }

  async function handleComplete() {
    if (!completeForm.final_price) { toast("error", "请输入最终成交单价"); return; }
    try {
      await api.put(`/group-order/${completeTarget.id}/complete`, {
        final_price: Number(completeForm.final_price),
        final_supplier: completeForm.final_supplier,
        logistics_fee: Number(completeForm.logistics_fee) || 0,
      });
      toast("success", "采购完成");
      setShowComplete(false); load();
    } catch (err: any) { toast("error", err.message || "操作失败"); }
  }

  function openCancel(order: any) {
    setCancelTarget(order); setCancelReason("");
    setShowCancel(true);
  }

  async function handleCancel() {
    if (!cancelReason.trim()) { toast("error", "请填写取消原因"); return; }
    try {
      await api.put(`/group-order/${cancelTarget.id}/cancel`, { reason: cancelReason });
      toast("success", "拼单已取消");
      setShowCancel(false); load();
    } catch (err: any) { toast("error", err.message || "操作失败"); }
  }

  const isSuperAdmin = user?.role === "super_admin";
  const isAdmin = user?.role === "super_admin" || user?.role === "warehouse_admin";

  return (
    <>
      {/* Page header */}
      <div className="flex items-center gap-3 mb-5">
        <div className="w-9 h-9 rounded-xl bg-orange-100 flex items-center justify-center">
          <ShoppingCart size={20} className="text-orange-600" />
        </div>
        <div className="flex-1">
          <h1 className="page-title">拼单管理</h1>
          <p className="text-xs text-gray-400 mt-0.5">跨仓库拼单采购，降低成本</p>
        </div>
        <div className="flex items-center gap-2">
          <div className="bg-white rounded-lg shadow-sm border p-0.5 flex">
            <button onClick={() => setTab("active")} className={`px-3.5 py-1.5 rounded text-sm font-medium transition-colors ${tab === "active" ? "bg-blue-600 text-white shadow-sm" : "text-gray-500 hover:text-gray-700"}`}>进行中</button>
            <button onClick={() => setTab("history")} className={`px-3.5 py-1.5 rounded text-sm font-medium transition-colors ${tab === "history" ? "bg-blue-600 text-white shadow-sm" : "text-gray-500 hover:text-gray-700"}`}>历史记录</button>
          </div>
          {isAdmin && (
            <button onClick={() => setShowCreate(true)} className="btn-primary flex items-center gap-1.5 text-sm">
              <Plus size={16} />发起拼单
            </button>
          )}
        </div>
      </div>

      {/* ========== ACTIVE TAB ========== */}
      {tab === "active" && (
        <>
          {loading ? (
            <div className="flex items-center justify-center py-16 text-gray-400">
              <div className="animate-spin w-6 h-6 border-2 border-blue-600 border-t-transparent rounded-full mr-2" />加载中...
            </div>
          ) : orders.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-gray-400 bg-white rounded-2xl shadow-sm border">
              <Package size={44} className="text-gray-200 mb-3" />
              <span className="text-sm">暂无进行中的拼单</span>
              {isAdmin && <span className="text-xs mt-1">点击右上角"发起拼单"创建新拼单</span>}
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {orders.map((o: any) => {
                const pct = Math.min(100, Math.round((o.current_quantity || 0) / o.target_quantity * 100));
                return (
                  <div key={o.id} className="bg-white rounded-2xl shadow-sm border border-gray-100 hover:shadow-md transition-all overflow-hidden">
                    {/* Status bar */}
                    <div className={`h-1 ${STATUS_BG[o.status] || "bg-gray-400"}`} />
                    <div className="p-5">
                      {/* Header */}
                      <div className="flex items-start justify-between mb-3">
                        <div className="flex-1 min-w-0">
                          <h3 className="font-semibold text-gray-800 truncate">{o.item_name}</h3>
                          {o.specification && <p className="text-xs text-gray-400 mt-0.5 truncate">{o.specification}</p>}
                        </div>
                        <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border ml-2 shrink-0 ${STATUS_COLOR[o.status] || "bg-gray-100 text-gray-500"}`}>
                          {STATUS_CN[o.status] || o.status}
                        </span>
                      </div>

                      {/* Info */}
                      <div className="space-y-2 text-sm text-gray-500 mb-3">
                        <div className="flex items-center gap-1.5">
                          <MapPin size={13} className="text-gray-300 shrink-0" />
                          <span className="truncate">发起仓库: {o.warehouse_name}</span>
                        </div>
                        <div className="flex items-center gap-1.5">
                          <Users size={13} className="text-gray-300 shrink-0" />
                          <span>{o.participant_warehouse_count || 0} 个仓库参与</span>
                        </div>
                        <div className="flex items-center gap-1.5">
                          <DollarSign size={13} className="text-gray-300 shrink-0" />
                          <span>目标单价: ฿{(o.target_price || 0).toLocaleString()}</span>
                        </div>
                        <div className="flex items-center gap-1.5">
                          <Calendar size={13} className="text-gray-300 shrink-0" />
                          <span>截止: {o.deadline?.slice(0, 10)}</span>
                        </div>
                      </div>

                      {/* Progress */}
                      <div className="mb-4">
                        <div className="flex justify-between text-xs mb-1.5">
                          <span className="font-medium text-gray-600">{o.current_quantity || 0} / {o.target_quantity} 件</span>
                          <span className={`font-semibold ${pct >= 100 ? "text-green-600" : "text-blue-600"}`}>{pct}%</span>
                        </div>
                        <div className="w-full bg-gray-100 rounded-full h-2.5 overflow-hidden">
                          <div className={`h-full rounded-full transition-all duration-500 ${pct >= 100 ? "bg-green-500" : "bg-blue-500"}`} style={{ width: `${pct}%` }} />
                        </div>
                      </div>

                      {/* Actions */}
                      <div className="flex gap-2">
                        <button onClick={() => openDetail(o.id)} className="flex-1 btn-secondary text-xs py-1.5">
                          查看详情
                        </button>
                        {o.status === "open" && user?.role !== "staff" && (
                          <button onClick={(e) => { e.stopPropagation(); openJoin(o); }} className="flex-1 bg-green-600 hover:bg-green-700 text-white rounded-lg text-xs py-1.5 font-medium transition-colors">
                            参与拼单
                          </button>
                        )}
                        {isSuperAdmin && o.status === "open" && (
                          <button onClick={(e) => { e.stopPropagation(); handleClose(o.id); }} className="flex-1 bg-yellow-500 hover:bg-yellow-600 text-white rounded-lg text-xs py-1.5 font-medium transition-colors">
                            截止
                          </button>
                        )}
                        {isSuperAdmin && o.status === "closed" && (
                          <>
                            <button onClick={() => openComplete(o)} className="flex-1 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-xs py-1.5 font-medium transition-colors">
                              完成采购
                            </button>
                            <button onClick={() => openCancel(o)} className="w-8 h-8 flex items-center justify-center border border-red-200 text-red-500 hover:bg-red-50 rounded-lg transition-colors" title="取消拼单">
                              <Ban size={14} />
                            </button>
                          </>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </>
      )}

      {/* ========== HISTORY TAB ========== */}
      {tab === "history" && (
        <>
          {loading ? (
            <div className="flex items-center justify-center py-16 text-gray-400">
              <div className="animate-spin w-6 h-6 border-2 border-blue-600 border-t-transparent rounded-full mr-2" />加载中...
            </div>
          ) : history.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-gray-400 bg-white rounded-2xl shadow-sm border">
              <Clock size={44} className="text-gray-200 mb-3" />
              <span className="text-sm">暂无历史拼单</span>
            </div>
          ) : (
            <div className="space-y-3">
              {history.map((h: any) => {
                const isExpanded = expandedHistory.has(h.id);
                const savings = h.savings || 0;
                return (
                  <div key={h.id} className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
                    <div className={`h-1 ${STATUS_BG[h.status] || "bg-gray-400"}`} />
                    <div className="p-5">
                      <div className="flex items-start justify-between">
                        <div className="flex-1">
                          <div className="flex items-center gap-2 mb-1">
                            <h3 className="font-semibold text-gray-800">{h.item_name}</h3>
                            <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium border ${STATUS_COLOR[h.status] || "bg-gray-100"}`}>
                              {STATUS_CN[h.status] || h.status}
                            </span>
                          </div>
                          <p className="text-xs text-gray-400">{h.specification || ""}</p>
                        </div>
                        <button onClick={() => {
                          const next = new Set(expandedHistory);
                          isExpanded ? next.delete(h.id) : next.add(h.id);
                          setExpandedHistory(next);
                        }} className="text-gray-400 hover:text-gray-600 transition-colors p-1">
                          {isExpanded ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
                        </button>
                      </div>

                      {/* Summary row */}
                      <div className="flex items-center gap-4 mt-3 text-sm">
                        <div className="flex items-center gap-1 text-gray-500"><MapPin size={13} />{h.warehouse_name}</div>
                        <div className="flex items-center gap-1 text-gray-500"><Package size={13} />{h.total_quantity || 0} 件</div>
                        <div className="flex items-center gap-1 text-gray-500"><Users size={13} />{h.participant_warehouse_count || 0} 仓库</div>
                        <div className="flex items-center gap-1 font-semibold text-blue-700"><DollarSign size={13} />฿{(h.final_price || 0).toLocaleString()}/件</div>
                        {savings > 0 && (
                          <div className="flex items-center gap-1 text-green-700 font-medium"><TrendingDown size={13} />省 ฿{savings.toLocaleString()}</div>
                        )}
                      </div>

                      {/* Expanded detail */}
                      {isExpanded && (
                        <div className="mt-4 pt-4 border-t border-gray-100 space-y-3">
                          {/* Participants table */}
                          {h.participants?.length > 0 && (
                            <div>
                              <h4 className="text-xs font-semibold text-gray-500 mb-2 flex items-center gap-1"><Users size={12} />参与仓库明细</h4>
                              <table className="w-full text-sm">
                                <thead>
                                  <tr className="border-b bg-gray-50 text-xs text-gray-400">
                                    <th className="text-left py-2 px-2">仓库</th>
                                    <th className="text-right py-2 px-2">数量</th>
                                    <th className="text-left py-2 px-2">收货地址</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {h.participants.map((p: any) => (
                                    <tr key={p.id} className="border-b border-gray-50">
                                      <td className="py-2 px-2 text-gray-700">{p.warehouse_name}</td>
                                      <td className="py-2 px-2 text-right font-mono text-gray-700">{p.quantity}</td>
                                      <td className="py-2 px-2 text-xs text-gray-400">{p.delivery_address || "-"}</td>
                                    </tr>
                                  ))}
                                  <tr className="bg-gray-50 font-semibold">
                                    <td className="py-2 px-2 text-gray-600">合计</td>
                                    <td className="py-2 px-2 text-right text-gray-800">{h.total_quantity || 0} 件</td>
                                    <td></td>
                                  </tr>
                                </tbody>
                              </table>
                            </div>
                          )}

                          {/* Finance details */}
                          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                            <div className="bg-blue-50 rounded-xl p-3">
                              <div className="text-[10px] text-blue-500 mb-0.5">总成交金额</div>
                              <div className="text-sm font-bold text-blue-700">฿{(h.total_amount || 0).toLocaleString()}</div>
                            </div>
                            <div className="bg-green-50 rounded-xl p-3">
                              <div className="text-[10px] text-green-500 mb-0.5">供应商</div>
                              <div className="text-sm font-bold text-green-700 truncate">{h.final_supplier || "-"}</div>
                            </div>
                            <div className="bg-orange-50 rounded-xl p-3">
                              <div className="text-[10px] text-orange-500 mb-0.5">物流费</div>
                              <div className="text-sm font-bold text-orange-700">฿{(h.logistics_fee || 0).toLocaleString()}</div>
                            </div>
                            <div className="bg-purple-50 rounded-xl p-3">
                              <div className="text-[10px] text-purple-500 mb-0.5">物流分摊/仓</div>
                              <div className="text-sm font-bold text-purple-700">฿{(h.logistics_per_warehouse || 0).toLocaleString()}</div>
                            </div>
                            {savings > 0 && (
                              <div className="bg-emerald-50 rounded-xl p-3 col-span-2 md:col-span-4">
                                <div className="flex items-center gap-1.5 text-xs text-emerald-600">
                                  <TrendingDown size={14} />
                                  <span>节省金额: 目标价(฿{h.target_price?.toLocaleString()}) - 成交价(฿{h.final_price?.toLocaleString()}) × {h.total_quantity}件 = <strong>฿{savings.toLocaleString()}</strong></span>
                                </div>
                              </div>
                            )}
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </>
      )}

      {/* ========== CREATE MODAL ========== */}
      {showCreate && (
        <div className="modal-overlay" onClick={() => setShowCreate(false)}>
          <div className="bg-white rounded-xl w-full max-w-lg shadow-2xl" onClick={e => e.stopPropagation()}>
            <div className="bg-blue-600 text-white px-6 py-4 rounded-t-xl flex items-center gap-3">
              <Plus size={20} /><h2 className="text-lg font-semibold">发起拼单</h2>
              <div className="flex-1" /><button onClick={() => setShowCreate(false)} className="text-blue-200 hover:text-white text-xl leading-none">&times;</button>
            </div>
            <div className="p-6 space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="col-span-2"><label className="form-label">物品名称 <span className="text-red-400">*</span></label><input className="form-input" value={createForm.item_name} onChange={e => setCreateForm({ ...createForm, item_name: e.target.value })} placeholder="如: 快递袋" /></div>
                <div className="col-span-2"><label className="form-label">规格</label><input className="form-input" value={createForm.specification} onChange={e => setCreateForm({ ...createForm, specification: e.target.value })} placeholder="如: 一打80个" /></div>
                <div><label className="form-label">目标数量 <span className="text-red-400">*</span></label><input type="number" className="form-input" value={createForm.target_quantity} onChange={e => setCreateForm({ ...createForm, target_quantity: e.target.value })} placeholder="100" min="1" /></div>
                <div><label className="form-label">目标单价 <span className="text-red-400">*</span></label><input type="number" className="form-input" value={createForm.target_price} onChange={e => setCreateForm({ ...createForm, target_price: e.target.value })} placeholder="5.00" min="0" step="0.01" /></div>
                <div className="col-span-2"><label className="form-label">截止时间 <span className="text-red-400">*</span></label><input type="datetime-local" className="form-input" value={createForm.deadline} onChange={e => setCreateForm({ ...createForm, deadline: e.target.value })} /></div>
                <div className="col-span-2"><label className="form-label">发起原因</label><textarea className="form-input" rows={2} value={createForm.reason} onChange={e => setCreateForm({ ...createForm, reason: e.target.value })} placeholder="说明为什么要发起此拼单" /></div>
              </div>
            </div>
            <div className="border-t px-6 py-4 bg-gray-50 rounded-b-xl flex justify-end gap-3">
              <button onClick={() => setShowCreate(false)} className="btn-secondary min-w-[80px]">取消</button>
              <button onClick={handleCreate} className="btn-primary min-w-[80px]">发起拼单</button>
            </div>
          </div>
        </div>
      )}

      {/* ========== JOIN MODAL ========== */}
      {showJoin && joinTarget && (
        <div className="modal-overlay" onClick={() => setShowJoin(false)}>
          <div className="bg-white rounded-xl w-full max-w-md shadow-2xl" onClick={e => e.stopPropagation()}>
            <div className="bg-green-600 text-white px-6 py-4 rounded-t-xl flex items-center gap-3">
              <ShoppingCart size={20} /><h2 className="text-lg font-semibold">参与拼单</h2>
              <div className="flex-1" /><button onClick={() => setShowJoin(false)} className="text-green-200 hover:text-white text-xl leading-none">&times;</button>
            </div>
            <div className="p-6 space-y-4">
              {/* Target info */}
              <div className="bg-gray-50 rounded-xl p-4 space-y-2">
                <div className="flex justify-between text-sm">
                  <span className="text-gray-500">物品</span>
                  <span className="font-semibold text-gray-800">{joinTarget.item_name}</span>
                </div>
                {joinTarget.specification && (
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-500">规格</span>
                    <span className="text-gray-700">{joinTarget.specification}</span>
                  </div>
                )}
                <div className="flex justify-between text-sm">
                  <span className="text-gray-500">目标单价</span>
                  <span className="font-semibold text-blue-700">฿{(joinTarget.target_price || 0).toLocaleString()}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-500">当前进度</span>
                  <span className="font-semibold">{joinTarget.current_quantity || 0} / {joinTarget.target_quantity} 件</span>
                </div>
                <div className="w-full bg-gray-200 rounded-full h-2 mt-1">
                  <div className="bg-green-500 h-2 rounded-full transition-all" style={{ width: `${Math.min(100, Math.round((joinTarget.current_quantity || 0) / joinTarget.target_quantity * 100))}%` }} />
                </div>
              </div>

              {/* Form */}
              <div className="space-y-3">
                <div>
                  <label className="form-label">参与数量 <span className="text-red-400">*</span></label>
                  <input type="number" className="form-input" value={joinForm.quantity} onChange={e => setJoinForm({ ...joinForm, quantity: e.target.value })} placeholder="请输入采购数量" min="1" />
                </div>
                <div>
                  <label className="form-label">收货地址</label>
                  <input className="form-input" value={joinForm.delivery_address} onChange={e => setJoinForm({ ...joinForm, delivery_address: e.target.value })} placeholder="请输入收货地址" />
                </div>
              </div>

              {/* Rules checkbox */}
              <label className="flex items-start gap-3 cursor-pointer bg-amber-50 border border-amber-200 rounded-xl p-3">
                <input type="checkbox" checked={joinForm.agreed_rules} onChange={e => setJoinForm({ ...joinForm, agreed_rules: e.target.checked })} className="mt-0.5 w-4 h-4 rounded accent-green-600" />
                <div className="text-xs text-gray-600 leading-relaxed">
                  <span className="font-semibold text-amber-800">拼单规则确认</span>
                  <p className="mt-0.5">确认参与后不可中途退出。强行退出者下次禁止参与。最终采购价与目标价不一致时拼单可能取消。物流费按参与方数量均摊。</p>
                </div>
              </label>
            </div>
            <div className="border-t px-6 py-4 bg-gray-50 rounded-b-xl flex justify-end gap-3">
              <button onClick={() => setShowJoin(false)} className="btn-secondary min-w-[80px]">取消</button>
              <button onClick={handleJoin} className="btn-primary min-w-[80px] bg-green-600 hover:bg-green-700">确认参与</button>
            </div>
          </div>
        </div>
      )}

      {/* ========== DETAIL MODAL ========== */}
      {showDetail && (
        <div className="modal-overlay" onClick={() => { setShowDetail(false); setDetail(null); }}>
          <div className="bg-white rounded-xl w-full max-w-xl max-h-[80vh] overflow-auto shadow-2xl" onClick={e => e.stopPropagation()}>
            <div className="bg-gray-800 text-white px-6 py-4 rounded-t-xl flex items-center gap-3 sticky top-0 z-10">
              <Package size={20} /><h2 className="text-lg font-semibold">拼单详情</h2>
              <div className="flex-1" /><button onClick={() => { setShowDetail(false); setDetail(null); }} className="text-gray-400 hover:text-white text-xl leading-none">&times;</button>
            </div>
            {detailLoading ? (
              <div className="flex items-center justify-center py-16 text-gray-400">
                <div className="animate-spin w-6 h-6 border-2 border-blue-600 border-t-transparent rounded-full mr-2" />加载中...
              </div>
            ) : detail ? (
              <div className="p-6 space-y-5">
                {/* Basic info */}
                <div className="grid grid-cols-2 gap-3">
                  <div className="bg-gray-50 rounded-xl p-3"><div className="text-[10px] text-gray-400">物品名称</div><div className="text-sm font-semibold text-gray-800">{detail.item_name}</div></div>
                  <div className="bg-gray-50 rounded-xl p-3"><div className="text-[10px] text-gray-400">状态</div>
                    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border ${STATUS_COLOR[detail.status] || ""}`}>{STATUS_CN[detail.status] || detail.status}</span>
                  </div>
                  <div className="bg-gray-50 rounded-xl p-3"><div className="text-[10px] text-gray-400">发起仓库</div><div className="text-sm font-semibold text-gray-800">{detail.warehouse_name}</div></div>
                  <div className="bg-gray-50 rounded-xl p-3"><div className="text-[10px] text-gray-400">参与仓库数</div><div className="text-sm font-semibold text-gray-800">{detail.participant_warehouse_count || 0}</div></div>
                  <div className="bg-gray-50 rounded-xl p-3"><div className="text-[10px] text-gray-400">目标数量</div><div className="text-sm font-semibold text-gray-800">{detail.target_quantity} 件</div></div>
                  <div className="bg-gray-50 rounded-xl p-3"><div className="text-[10px] text-gray-400">目标单价</div><div className="text-sm font-semibold text-blue-700">฿{(detail.target_price || 0).toLocaleString()}</div></div>
                  {detail.specification && (
                    <div className="bg-gray-50 rounded-xl p-3 col-span-2"><div className="text-[10px] text-gray-400">规格</div><div className="text-sm font-semibold text-gray-800">{detail.specification}</div></div>
                  )}
                  {detail.reason && (
                    <div className="bg-gray-50 rounded-xl p-3 col-span-2"><div className="text-[10px] text-gray-400">发起原因</div><div className="text-sm text-gray-600">{detail.reason}</div></div>
                  )}
                </div>

                {/* Progress */}
                <div>
                  <div className="flex justify-between text-xs mb-1.5">
                    <span className="font-medium text-gray-600">{detail.current_quantity || 0} / {detail.target_quantity} 件</span>
                    <span className="font-semibold">{Math.min(100, Math.round((detail.current_quantity || 0) / detail.target_quantity * 100))}%</span>
                  </div>
                  <div className="w-full bg-gray-100 rounded-full h-3 overflow-hidden">
                    <div className="bg-blue-500 h-full rounded-full transition-all" style={{ width: `${Math.min(100, Math.round((detail.current_quantity || 0) / detail.target_quantity * 100))}%` }} />
                  </div>
                </div>

                {/* Participants table */}
                <div>
                  <h4 className="text-sm font-semibold text-gray-700 mb-2 flex items-center gap-1.5"><Users size={14} />参与仓库</h4>
                  {detail.participants?.length > 0 ? (
                    <table className="w-full text-sm">
                      <thead><tr className="bg-gray-50 text-xs text-gray-400"><th className="text-left py-2.5 px-3">仓库</th><th className="text-right py-2.5 px-3">数量</th><th className="text-left py-2.5 px-3">收货地址</th></tr></thead>
                      <tbody>
                        {detail.participants.map((p: any) => (
                          <tr key={p.id} className="border-b border-gray-50">
                            <td className="py-2.5 px-3 text-gray-700">{p.warehouse_name}</td>
                            <td className="py-2.5 px-3 text-right font-mono text-gray-700">{p.quantity}</td>
                            <td className="py-2.5 px-3 text-xs text-gray-400">{p.delivery_address || "-"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  ) : (
                    <p className="text-sm text-gray-400 text-center py-6">暂无参与仓库</p>
                  )}
                </div>
              </div>
            ) : null}
          </div>
        </div>
      )}

      {/* ========== COMPLETE MODAL ========== */}
      {showComplete && completeTarget && (
        <div className="modal-overlay" onClick={() => setShowComplete(false)}>
          <div className="bg-white rounded-xl w-full max-w-md shadow-2xl" onClick={e => e.stopPropagation()}>
            <div className="bg-blue-600 text-white px-6 py-4 rounded-t-xl flex items-center gap-3">
              <CheckCircle size={20} /><h2 className="text-lg font-semibold">完成采购</h2>
              <div className="flex-1" /><button onClick={() => setShowComplete(false)} className="text-blue-200 hover:text-white text-xl leading-none">&times;</button>
            </div>
            <div className="p-6 space-y-4">
              <div className="bg-blue-50 rounded-xl p-3 text-sm text-blue-800">
                <strong>{completeTarget.item_name}</strong> — 目标 {completeTarget.target_quantity} 件，已凑 {completeTarget.current_quantity || 0} 件
              </div>
              <div className="space-y-3">
                <div><label className="form-label">最终成交单价 <span className="text-red-400">*</span></label><input type="number" className="form-input" value={completeForm.final_price} onChange={e => setCompleteForm({ ...completeForm, final_price: e.target.value })} placeholder="实际成交单价" min="0" step="0.01" /></div>
                <div><label className="form-label">供应商名称</label><input className="form-input" value={completeForm.final_supplier} onChange={e => setCompleteForm({ ...completeForm, final_supplier: e.target.value })} placeholder="最终供应商" /></div>
                <div><label className="form-label">物流费用</label><input type="number" className="form-input" value={completeForm.logistics_fee} onChange={e => setCompleteForm({ ...completeForm, logistics_fee: e.target.value })} placeholder="总物流费" min="0" step="0.01" /></div>
              </div>
            </div>
            <div className="border-t px-6 py-4 bg-gray-50 rounded-b-xl flex justify-end gap-3">
              <button onClick={() => setShowComplete(false)} className="btn-secondary min-w-[80px]">取消</button>
              <button onClick={handleComplete} className="btn-primary min-w-[80px]">确认完成</button>
            </div>
          </div>
        </div>
      )}

      {/* ========== CANCEL MODAL ========== */}
      {showCancel && cancelTarget && (
        <div className="modal-overlay" onClick={() => setShowCancel(false)}>
          <div className="bg-white rounded-xl w-full max-w-md shadow-2xl" onClick={e => e.stopPropagation()}>
            <div className="bg-red-600 text-white px-6 py-4 rounded-t-xl flex items-center gap-3">
              <Ban size={20} /><h2 className="text-lg font-semibold">取消拼单</h2>
              <div className="flex-1" /><button onClick={() => setShowCancel(false)} className="text-red-200 hover:text-white text-xl leading-none">&times;</button>
            </div>
            <div className="p-6 space-y-4">
              <div className="bg-red-50 rounded-xl p-3 text-sm text-red-700">
                确认取消 <strong>{cancelTarget.item_name}</strong> 拼单？此操作不可撤销，所有参与仓库将收到通知。
              </div>
              <div>
                <label className="form-label">取消原因 <span className="text-red-400">*</span></label>
                <textarea className="form-input" rows={3} value={cancelReason} onChange={e => setCancelReason(e.target.value)} placeholder="请填写取消原因，将通知到所有参与仓库" />
              </div>
            </div>
            <div className="border-t px-6 py-4 bg-gray-50 rounded-b-xl flex justify-end gap-3">
              <button onClick={() => setShowCancel(false)} className="btn-secondary min-w-[80px]">返回</button>
              <button onClick={handleCancel} className="bg-red-600 hover:bg-red-700 text-white px-5 py-2 rounded-lg text-sm font-medium min-w-[80px] transition-colors">确认取消</button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

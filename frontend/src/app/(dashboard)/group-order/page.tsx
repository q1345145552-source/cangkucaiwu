"use client";
import { useEffect, useState } from "react";
import { api, getToken } from "@/lib/api";
import { useI18n } from "@/hooks/useI18n";
import { useToast } from "@/components/ui/Toast";
import { useRouter } from "next/navigation";
import { useAuth } from "@/hooks/useAuth";

export default function GroupOrderPage() {
  const { t } = useI18n(); const router = useRouter(); const { user } = useAuth();
  const { toast } = useToast();
  const [orders, setOrders] = useState<any[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ item_name: "", target_quantity: "", target_price: "", deadline: "", reason: "" });
  const [selected, setSelected] = useState<any>(null);
  const [participants, setParticipants] = useState<any[]>([]);
  const [history, setHistory] = useState<any[]>([]);
  const [tab, setTab] = useState<"active"|"history">("active");
  const [loading, setLoading] = useState(false);

  useEffect(() => { if (!getToken()) router.push("/login"); load(); }, [tab]);

  async function load() {
    setLoading(true);
    try {
      if (tab === "history") {
        const r = await api.get<any>("/group-order/history"); setHistory(r.data);
      } else {
        const r = await api.get<any>("/group-order?page_size=100");
        setOrders(r.data);
      }
    } catch (err) { console.error("加载失败:", err); }
    setLoading(false);
  }

  async function handleCreate() {
    if (!confirm("确认发起拼单？规则：参与后不可中途退出。")) return;
    try {
      await api.post("/group-order", { ...form, target_quantity: form.target_quantity || 0, target_price: form.target_price || 0 });
      toast("success", "发起成功");
      setShowForm(false); load();
    } catch (err: any) { toast("error", err.message || "发起失败"); }
  }

  async function handleJoin(orderId: number) {
    if (!confirm("参与拼单规则：\n1. 确认后不可中途退出\n2. 强行退出者下次禁止参与\n3. 最终采购价与目标价不一致时拼单取消\n4. 物流费按参与方数量均摊\n\n同意以上规则？")) return;
    const qty = prompt("参与数量:"); 
    if (qty) { try { await api.post(`/group-order/${orderId}/join`, { quantity: +qty, agreed_rules: true });
      toast("success", "参与成功"); load(); } catch (err: any) { toast("error", err.message || "参与失败"); } }
  }

  async function viewParticipants(order: any) {
    setSelected(order);
    const r = await api.get<any>(`/group-order/${order.id}/participants`);
    setParticipants(r.data);
  }

  async function handleClose(orderId: number) {
    try { await api.put(`/group-order/${orderId}/close`, {});
      toast("success", "关闭成功"); load(); } catch (err: any) { toast("error", err.message || "操作失败"); }
  }

  async function handleComplete(orderId: number) {
    const price = prompt("最终成交单价:"); const supplier = prompt("供应商名称:");
    if (price) { try { await api.put(`/group-order/${orderId}/complete`, { final_price: +price, final_supplier: supplier || "" });
      toast("success", "完成成功"); load(); } catch (err: any) { toast("error", err.message || "操作失败"); } }
  }

  const statusColors: any = { open: "text-green-600", closed: "text-yellow-600", completed: "text-blue-600", cancelled: "text-gray-400" };

  return (
    <>
      <div className="page-header">
        <h1 className="page-title">{t("group_order")}</h1>
        <div className="flex gap-2">
          <div className="bg-white rounded-lg p-1 flex">
            <button onClick={() => setTab("active")} className={`px-3 py-1 rounded text-sm ${tab==="active"?"bg-primary text-white":""}`}>进行中</button>
            <button onClick={() => setTab("history")} className={`px-3 py-1 rounded text-sm ${tab==="history"?"bg-primary text-white":""}`}>历史</button>
          </div>
          {(user?.role === "super_admin" || user?.role === "warehouse_admin") && (
            <button onClick={() => setShowForm(true)} className="btn-primary">发起拼单</button>
          )}
        </div>
      </div>

      {loading ? <div className="text-center py-8 text-gray-400">加载中...</div> : tab === "active" && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {orders.map((o: any) => (
            <div key={o.id} className="bg-white rounded-xl shadow-sm p-4" onClick={() => viewParticipants(o)}>
              <div className="flex justify-between mb-2">
                <h3 className="font-semibold">{o.item_name}</h3>
                <span className={`text-xs ${statusColors[o.status]}`}>{o.status}</span>
              </div>
              <div className="text-sm text-gray-500 space-y-1">
                <div>目标: {o.current_quantity}/{o.target_quantity} 件 (单价 ¥{o.target_price})</div>
                <div>截止: {o.deadline?.slice(0,10)}</div>
                <div>进度: <div className="w-full bg-gray-200 rounded-full h-2 mt-1"><div className="bg-primary h-2 rounded-full" style={{width: `${Math.min(100, o.current_quantity/o.target_quantity*100)}%`}} /></div></div>
              </div>
              <div className="flex gap-2 mt-3">
                {o.status === "open" && user?.role !== "staff" && (
                  <button onClick={(e) => { e.stopPropagation(); handleJoin(o.id); }} className="bg-green-500 text-white px-3 py-1 rounded text-xs">参与</button>
                )}
                {user?.role === "super_admin" && o.status === "open" && (
                  <button onClick={(e) => { e.stopPropagation(); handleClose(o.id); }} className="border px-3 py-1 rounded text-xs">截止</button>
                )}
                {user?.role === "super_admin" && o.status === "closed" && (
                  <button onClick={(e) => { e.stopPropagation(); handleComplete(o.id); }} className="bg-blue-500 text-white px-3 py-1 rounded text-xs">完成采购</button>
                )}
              </div>
            </div>
          ))}
          {orders.length === 0 && <div className="col-span-3 text-gray-400 text-center py-8">暂无拼单</div>}
        </div>
      )}

      {tab === "history" && (
        <div className="space-y-3">
          {history.map((h: any) => (
            <div key={h.id} className="bg-white rounded-xl p-4 shadow-sm">
              <div className="font-semibold">{h.item_name}</div>
              <div className="text-sm text-gray-500">成交价: ¥{h.final_price} | 供应商: {h.final_supplier} | 物流费: ¥{h.logistics_fee || 0}</div>
            </div>
          ))}
        </div>
      )}

      {selected && (
        <div className="modal-overlay"><div className="bg-white rounded-xl p-6 w-96 max-h-[70vh] overflow-auto">
          <h2 className="font-semibold mb-3">{selected.item_name} - 参与列表</h2>
          <table className="w-full text-sm"><thead><tr className="border-b"><th className="text-left py-1">仓库</th><th>数量</th><th>地址</th></tr></thead>
            <tbody>{participants.map((p: any) => (<tr key={p.id} className="border-b"><td className="py-1">{p.warehouse_name}</td><td>{p.quantity}</td><td className="text-xs text-gray-400">{p.delivery_address}</td></tr>))}</tbody></table>
          <div className="mt-2 text-sm text-gray-500">合计: {participants.reduce((s: number, p: any) => s + p.quantity, 0)} 件</div>
          <button onClick={() => setSelected(null)} className="mt-4 px-4 py-2 border rounded text-sm">关闭</button>
        </div></div>
      )}

      {showForm && (
        <div className="modal-overlay"><div className="bg-white rounded-xl p-6 w-96">
          <h2 className="font-semibold mb-4">发起拼单</h2>
          <div className="space-y-3">
            <div><label className="form-label">物品名称</label><input className="form-input" value={form.item_name} onChange={e=>setForm({...form,item_name:e.target.value})} /></div>
            <div><label className="form-label">目标数量</label><input type="number" className="form-input" value={form.target_quantity} onChange={e=>setForm({...form,target_quantity:e.target.value===""?"":+e.target.value})} /></div>
            <div><label className="form-label">目标单价</label><input type="number" className="form-input" value={form.target_price} onChange={e=>setForm({...form,target_price:e.target.value===""?"":+e.target.value})} /></div>
            <div><label className="form-label">截止时间</label><input type="datetime-local" className="form-input" value={form.deadline} onChange={e=>setForm({...form,deadline:e.target.value})} /></div>
            <div><label className="form-label">原因说明</label><input className="form-input" value={form.reason} onChange={e=>setForm({...form,reason:e.target.value})} /></div>
          </div>
          <div className="flex justify-end gap-3 mt-6"><button onClick={()=>setShowForm(false)} className="btn-secondary">取消</button><button onClick={handleCreate} className="px-4 py-2 bg-primary text-white rounded text-sm">发起</button></div>
        </div></div>
      )}
    </>
  );
}

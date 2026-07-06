"use client";
import { useEffect, useState } from "react";
import { api, getToken } from "@/lib/api";
import { useI18n } from "@/hooks/useI18n";
import { useToast } from "@/components/ui/Toast";
import { useRouter } from "next/navigation";
import { useAuth } from "@/hooks/useAuth";
import { Package, ShoppingCart, Check, X } from "lucide-react";

export default function MarketPage() {
  const { t } = useI18n(); const router = useRouter(); const { user } = useAuth();
  const { toast } = useToast();
  const [items, setItems] = useState<any[]>([]); const [reviews, setReviews] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ name: "", quantity: 1, price: 0, description: "" });
  const [tab, setTab] = useState<"all"|"review">("all");
  const [search, setSearch] = useState("");

  useEffect(() => { if (!getToken()) router.push("/login"); load(); }, [tab, search]);

  async function load() {
    setLoading(true);
    try {
      if (tab === "review" && user?.role === "super_admin") {
        const r = await api.get<any>("/market/review-list"); setReviews(r.data);
      } else {
        const r = await api.get<any>(`/market?page_size=100&search=${search}`); setItems(r.data);
      }
    } catch (err) { console.error("加载失败:", err); }
    setLoading(false);
  }

  async function handleCreate() {
    try {
      await api.post("/market", form);
      toast("success", "上架成功");
    setShowForm(false); setForm({ name: "", quantity: 1, price: 0, description: "" }); load();
    } catch (err: any) { toast("error", "上架失败"); }
  }

  async function handleReview(itemId: number, status: string) {
    try {
      await api.put(`/market/${itemId}/review`, { status });
      toast("success", "审核完成");
      load();
    } catch (err: any) { toast("error", "审核失败"); }
  }

  async function handlePurchase(itemId: number) {
    const contact = prompt("请输入联系方式:");
    if (contact) { try {
      await api.post(`/market/${itemId}/purchase`, { contact_info: contact });
      toast("success", "购买申请已发送"); alert("购买申请已提交");
    } catch (err: any) { toast("error", "操作失败"); } }
  }

  async function handleConfirm(itemId: number) {
    try {
      await api.put(`/market/${itemId}/confirm`, {});
      toast("success", "确认成功");
      load();
    } catch (err: any) { toast("error", "操作失败"); }
  }

  const statusColors: any = { pending: "bg-yellow-100 text-yellow-700", approved: "bg-green-100 text-green-700", rejected: "bg-red-100 text-red-700", sold: "bg-gray-100 text-gray-600" };

  return (
    <>
      <div className="page-header">
        <h1 className="page-title">{t("market")}</h1>
        <div className="flex gap-2">
          {user?.role === "super_admin" && (
            <button onClick={() => setTab(tab === "review" ? "all" : "review")}
                    className={`px-4 py-2 rounded-lg text-sm ${tab==="review" ? "bg-orange-500 text-white" : "border"}`}>
              {tab==="review" ? "返回" : "待审核"}
            </button>
          )}
          {(user?.role === "super_admin" || user?.role === "warehouse_admin") && (
            <button onClick={() => setShowForm(true)} className="btn-primary">上架商品</button>
          )}
        </div>
      </div>

      {tab === "all" && <input placeholder="搜索..." className="border rounded-lg px-3 py-2 mb-4 w-64 text-sm" value={search} onChange={e => { setSearch(e.target.value); }} />}

      {/* Review tab */}
      {tab === "review" && (
        <div className="grid gap-4">
          {reviews.map((i: any) => (
            <div key={i.id} className="bg-white rounded-xl p-4 shadow-sm flex items-center justify-between">
              <div>
                <div className="font-semibold">{i.name}</div>
                <div className="text-sm text-gray-500">{i.warehouse_name} | 数量:{i.quantity} | 价格:{i.price === 0 ? "无偿" : `¥${i.price}`}</div>
                <div className="text-sm text-gray-400">{i.description}</div>
              </div>
              <div className="flex gap-2">
                <button onClick={() => handleReview(i.id, "approved")} className="bg-green-500 text-white px-3 py-1 rounded text-sm"><Check size={16}/></button>
                <button onClick={() => handleReview(i.id, "rejected")} className="bg-red-500 text-white px-3 py-1 rounded text-sm"><X size={16}/></button>
              </div>
            </div>
          ))}
          {reviews.length === 0 && <div className="text-gray-400 text-center py-8">暂无待审核商品</div>}
        </div>
      )}

      {/* Market grid */}
      {tab === "all" && (
        loading ? <div className="text-center py-8 text-gray-400">加载中...</div> : <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {items.map((i: any) => (
            <div key={i.id} className="bg-white rounded-xl shadow-sm overflow-hidden">
              <div className="h-40 bg-gray-100 flex items-center justify-center">
                {i.image ? <img src={i.image} alt={i.name} className="w-full h-full object-cover" /> : <Package size={48} className="text-gray-300" />}
              </div>
              <div className="p-4">
                <div className="flex justify-between items-start mb-2">
                  <div>
                    <h3 className="font-semibold">{i.name}</h3>
                    <div className="text-xs text-gray-400">{i.warehouse_name}</div>
                  </div>
                  <span className={`px-2 py-0.5 rounded text-xs ${statusColors[i.status] || ""}`}>
                    {i.status === "approved" ? "可购买" : i.status === "sold" ? "已售" : i.status}
                  </span>
                </div>
                <div className="text-sm text-gray-500 mb-3">数量: {i.quantity} | {i.price === 0 ? "无偿" : `¥${i.price.toLocaleString()}`}</div>
                <div className="text-xs text-gray-400 mb-3 line-clamp-2">{i.description}</div>
                {i.status === "approved" && user?.role !== "staff" && (
                  <button onClick={() => handlePurchase(i.id)} className="w-full bg-primary text-white py-1.5 rounded text-sm flex items-center justify-center gap-1">
                    <ShoppingCart size={14} /> 购买
                  </button>
                )}
                {(user?.role === "super_admin" || user?.warehouse_id === i.warehouse_id) && i.status === "approved" && (
                  <button onClick={() => handleConfirm(i.id)} className="w-full mt-1 border border-green-500 text-green-600 py-1.5 rounded text-sm">确认交易完成</button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {showForm && (
        <div className="modal-overlay"><div className="bg-white rounded-xl p-6 w-96">
          <h2 className="font-semibold mb-4">上架商品</h2>
          <div className="space-y-3">
            <div><label className="form-label">物品名称</label><input className="form-input" value={form.name} onChange={e=>setForm({...form,name:e.target.value})} /></div>
            <div><label className="form-label">数量</label><input type="number" className="form-input" value={form.quantity} onChange={e=>setForm({...form,quantity:+e.target.value})} /></div>
            <div><label className="form-label">价格 (0=无偿)</label><input type="number" className="form-input" value={form.price} onChange={e=>setForm({...form,price:+e.target.value})} /></div>
            <div><label className="form-label">描述</label><textarea className="form-input" rows={3} value={form.description} onChange={e=>setForm({...form,description:e.target.value})} /></div>
          </div>
          <div className="flex justify-end gap-3 mt-6"><button onClick={()=>setShowForm(false)} className="px-4 py-2 border rounded">取消</button><button onClick={handleCreate} className="px-4 py-2 bg-primary text-white rounded">上架</button></div>
        </div></div>
      )}
    </>
  );
}

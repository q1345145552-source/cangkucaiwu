"use client";
import ActionGate from "@/components/permissions/ActionGate";
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
  const isSuperAdmin = (user as { role?: string } | null)?.role === "super_admin";
  const [warehouses, setWarehouses] = useState<{id:number;name:string}[]>([]);
  const [imageUploading, setImageUploading] = useState(false);
  const [items, setItems] = useState<any[]>([]); const [reviews, setReviews] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ name: "", quantity: 1, price: "" as string | number, description: "", warehouse_id: "", image: "" });
  const [tab, setTab] = useState<"all"|"review">("all");
  const [search, setSearch] = useState("");

  useEffect(() => { if (!getToken()) router.push("/login"); load(); }, [tab, search]);
  useEffect(() => {
    if (isSuperAdmin) api.get<any>("/warehouses").then(r => {
      const options = (r.data || []).filter((w: any) => w.is_active);
      setWarehouses(options);
      setForm(old => ({...old, warehouse_id: old.warehouse_id || String(options[0]?.id || "")}));
    }).catch(() => toast("error", "发布来源仓库加载失败"));
  }, [isSuperAdmin]);

  async function load() {
    setLoading(true);
    try {
      if (tab === "review" && isSuperAdmin) {
        const r = await api.get<any>("/market/review-list"); setReviews(r.data);
      } else {
        const r = await api.get<any>(`/market?page_size=100&search=${encodeURIComponent(search)}`); setItems(r.data);
      }
    } catch (err) { console.error("加载失败:", err); }
    setLoading(false);
  }

  async function handleCreate() {
    if (!form.warehouse_id) { toast("error", "请选择发布来源仓库"); return; }
    try {
      await api.post("/market", { ...form, warehouse_id: Number(form.warehouse_id), price: form.price || 0, image: form.image || null });
      toast("success", "上架成功");
    setShowForm(false); setForm(old => ({ name: "", quantity: 1, price: "", description: "", warehouse_id: old.warehouse_id, image: "" })); load();
    } catch (err: any) { toast("error", err.message || "上架失败"); }
  }

  async function uploadImage(file?: File) {
    if (!file) return;
    if (!form.warehouse_id) { toast("error", "请选择发布来源仓库"); return; }
    setImageUploading(true);
    try {
      const data = new FormData(); data.append("file", file); data.append("warehouse_id", form.warehouse_id);
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "/api/v1"}/market/image`, {method:"POST", headers:{Authorization:`Bearer ${getToken()}`}, body:data});
      const image = await response.json();
      if (!response.ok) throw new Error(image.detail || "商品图片上传失败");
      setForm(old => ({...old, image: image.path}));
    } catch (err: any) { toast("error", err.message || "商品图片上传失败"); }
    finally { setImageUploading(false); }
  }

  async function handleReview(itemId: number, status: string) {
    try {
      await api.put(`/market/${itemId}/review`, { status });
      toast("success", "审核完成");
      load();
    } catch (err: any) { toast("error", err.message || "审核失败"); }
  }

  async function handlePurchase(itemId: number) {
    const contact = prompt("请输入联系方式:");
    if (contact) { try {
      await api.post(`/market/${itemId}/purchase`, { contact_info: contact });
      toast("success", "购买申请已发送"); alert("购买申请已提交");
    } catch (err: any) { toast("error", err.message || "操作失败"); } }
  }

  async function handleConfirm(itemId: number) {
    try {
      await api.put(`/market/${itemId}/confirm`, {});
      toast("success", "确认成功");
      load();
    } catch (err: any) { toast("error", err.message || "操作失败"); }
  }

  const statusColors: any = { pending: "bg-yellow-100 text-yellow-700", approved: "bg-green-100 text-green-700", rejected: "bg-red-100 text-red-700", sold: "bg-gray-100 text-gray-600" };

  return (
    <>
      <div className="page-header">
        <h1 className="page-title">{t("market")}</h1>
        <div className="flex gap-2">
          {isSuperAdmin && (
            <button onClick={() => setTab(tab === "review" ? "all" : "review")}
                    className={`px-4 py-2 rounded-lg text-sm ${tab==="review" ? "bg-orange-500 text-white" : "border"}`}>
              {tab==="review" ? "返回" : "待审核"}
            </button>
          )}
          {isSuperAdmin && (
            <ActionGate anyOf={["market.create_item"]}><button onClick={() => setShowForm(true)} className="btn-primary">上架商品</button></ActionGate>
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
                <div className="text-sm text-gray-500">{i.warehouse_name} | 数量:{i.quantity} | 价格:{i.price === 0 ? "无偿" : `฿${i.price}`}</div>
                <div className="text-sm text-gray-400">{i.description}</div>
              </div>
              <div className="flex gap-2">
                <ActionGate anyOf={["market.review_item#approve"]}><button onClick={() => handleReview(i.id, "approved")} className="bg-green-500 text-white px-3 py-1 rounded text-sm"><Check size={16}/></button></ActionGate>
                <ActionGate anyOf={["market.review_item#approve"]}><button onClick={() => handleReview(i.id, "rejected")} className="bg-red-500 text-white px-3 py-1 rounded text-sm"><X size={16}/></button></ActionGate>
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
                <div className="text-sm text-gray-500 mb-3">数量: {i.quantity} | {i.price === 0 ? "无偿" : `฿${i.price.toLocaleString()}`}</div>
                <div className="text-xs text-gray-400 mb-3 line-clamp-2">{i.description}</div>
                {i.status === "approved" && !isSuperAdmin && (
                  <ActionGate anyOf={["market.purchase#operate"]}><button onClick={() => handlePurchase(i.id)} className="w-full bg-primary text-white py-1.5 rounded text-sm flex items-center justify-center gap-1">
                    <ShoppingCart size={14} /> 购买
                  </button></ActionGate>
                )}
                {isSuperAdmin && i.status === "approved" && (
                  <ActionGate anyOf={["market.confirm_trade#operate"]}><button onClick={() => handleConfirm(i.id)} className="w-full mt-1 border border-green-500 text-green-600 py-1.5 rounded text-sm">确认交易完成</button></ActionGate>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {showForm && (
        <div className="modal-overlay"><div className="bg-white rounded-xl p-6 w-96 max-h-[90vh] overflow-y-auto">
          <h2 className="font-semibold mb-4">上架商品</h2>
          <div className="space-y-3">
            <div><label className="form-label">发布来源仓库（各仓均可见）</label><select className="form-input" value={form.warehouse_id} onChange={e=>setForm({...form,warehouse_id:e.target.value})}><option value="">请选择来源仓库</option>{warehouses.map(w=><option key={w.id} value={w.id}>{w.name}</option>)}</select></div>
            <div><label className="form-label">物品名称</label><input className="form-input" value={form.name} onChange={e=>setForm({...form,name:e.target.value})} /></div>
            <div><label className="form-label">数量</label><input type="number" className="form-input" value={form.quantity} onChange={e=>setForm({...form,quantity:+e.target.value})} /></div>
            <div><label className="form-label">价格 (0=无偿)</label><input type="number" className="form-input" value={form.price} onChange={e=>setForm({...form,price:e.target.value===""?"":+e.target.value})} /></div>
            <div><label className="form-label">描述</label><textarea className="form-input" rows={3} value={form.description} onChange={e=>setForm({...form,description:e.target.value})} /></div>
            <div><label className="form-label">商品图片（可选）</label><input type="file" accept="image/png,image/jpeg,image/webp" disabled={imageUploading} onChange={e=>uploadImage(e.target.files?.[0])} />{imageUploading && <p className="text-sm">图片上传中...</p>}{form.image && <img src={"/"+form.image.replace(/^\//,"")} alt="商品图片" className="mt-2 h-24 object-contain" />}</div>
          </div>
          <div className="flex justify-end gap-3 mt-6"><button onClick={()=>setShowForm(false)} className="px-4 py-2 border rounded" data-modal-close="true">取消</button><ActionGate anyOf={["market.create_item#operate"]}><button onClick={handleCreate} disabled={imageUploading} className="px-4 py-2 bg-primary text-white rounded">上架</button></ActionGate></div>
        </div></div>
      )}
    </>
  );
}

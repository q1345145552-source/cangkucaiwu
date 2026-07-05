"use client";
import { useEffect, useState } from "react";
import DataTable from "@/components/common/DataTable";
import { api, getToken } from "@/lib/api";
import { useI18n } from "@/hooks/useI18n";
import { useToast } from "@/components/ui/Toast";
import { useAuth } from "@/hooks/useAuth";
import { useRouter } from "next/navigation";
import { Sparkles, Eye, TrendingUp, Scale, Plus, Trash2 } from "lucide-react";

const DEFAULT_CATEGORIES = ["耗材商", "物流"];

export default function SuppliersPage() {
  const { t } = useI18n();
  const { toast } = useToast(); const { user } = useAuth(); const router = useRouter();
  const [data, setData] = useState<any[]>([]); const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [showForm, setShowForm] = useState(false);
  const [categories, setCategories] = useState<any[]>([]);
  const [filterCat, setFilterCat] = useState(0);
  const [form, setForm] = useState({ name: "", contact_person: "", contact_info: "", address: "", payment_terms: "", cooperation_content: "", settlement_cycle: "", category_id: 0 });
  const [aiResult, setAiResult] = useState("");
  const [procurement, setProcurement] = useState<any[]>([]);
  const [showProcurement, setShowProcurement] = useState(false);
  const [detail, setDetail] = useState<any>(null);
  // Product management
  const [products, setProducts] = useState<any[]>([]);
  const [showProducts, setShowProducts] = useState(false);
  const [productSupplierId, setProductSupplierId] = useState(0);
  const [productForm, setProductForm] = useState({ product_name: "", spec: "", unit_price: 0, unit: "个", remark: "" });
  // Compare
  const [compareData, setCompareData] = useState<any[]>([]);
  const [showCompare, setShowCompare] = useState(false);
  const [compareProduct, setCompareProduct] = useState("");
  const [compareSpec, setCompareSpec] = useState("");
  const [compareCat, setCompareCat] = useState(0);
  const [aiCompareResult, setAiCompareResult] = useState("");
  // New category
  const [newCatName, setNewCatName] = useState("");

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

  async function loadCategories() {
    try { const r = await api.get<any>("/suppliers/categories"); setCategories(r.data); } catch {}
  }

  async function handleCreate() {
    try {
      const payload: any = { ...form };
      if (!payload.category_id) delete payload.category_id;
      await api.post("/suppliers", payload);
      toast("success", "创建成功"); setShowForm(false); load();
    } catch (err: any) { toast("error", err.message || "创建失败"); }
  }

  async function aiEvaluate(sid: number) {
    setAiResult("评估中...");
    try { const r = await api.get<any>(`/suppliers/${sid}/ai-evaluation`); setAiResult(r.result || r.error || "评估完成"); }
    catch(e: any) { setAiResult(e.message); }
  }

  async function viewDetail(sid: number) {
    try {
      const r = await api.get<any>(`/suppliers/${sid}`);
      const prods = await api.get<any>(`/suppliers/${sid}/products`);
      setDetail({ ...r, products: prods.data });
    } catch {}
  }

  // ─── Product management ───
  async function openProducts(sid: number) {
    setProductSupplierId(sid);
    try { const r = await api.get<any>(`/suppliers/${sid}/products`); setProducts(r.data); } catch { setProducts([]); }
    setShowProducts(true);
  }

  async function addProduct() {
    try {
      await api.post(`/suppliers/${productSupplierId}/products`, productForm);
      toast("success", "产品添加成功");
      const r = await api.get<any>(`/suppliers/${productSupplierId}/products`); setProducts(r.data);
      setProductForm({ product_name: "", spec: "", unit_price: 0, unit: "个", remark: "" });
    } catch (err: any) { toast("error", "添加失败"); }
  }

  async function deleteProduct(pid: number) {
    try {
      await api.delete(`/suppliers/${productSupplierId}/products/${pid}`);
      toast("success", "已删除");
      const r = await api.get<any>(`/suppliers/${productSupplierId}/products`); setProducts(r.data);
    } catch { toast("error", "删除失败"); }
  }

  // ─── Compare ───
  async function doCompare() {
    try {
      let url = `/suppliers/compare-prices?product_name=${encodeURIComponent(compareProduct)}`;
      if (compareSpec) url += `&spec=${encodeURIComponent(compareSpec)}`;
      if (compareCat) url += `&category_id=${compareCat}`;
      const r = await api.get<any>(url);
      setCompareData(r.data);
    } catch { setCompareData([]); }
  }

  async function doAiCompare() {
    setAiCompareResult("分析中...");
    try {
      const r = await api.post("/suppliers/ai-compare", { compare_data: compareData });
      setAiCompareResult(r.result || "分析完成");
    } catch (e: any) { setAiCompareResult(e.message); }
  }

  async function addCategory() {
    if (!newCatName.trim()) return;
    try {
      await api.post(`/suppliers/categories?name=${encodeURIComponent(newCatName.trim())}`);
      toast("success", "类别已添加");
      setNewCatName(""); loadCategories();
    } catch { toast("error", "添加失败"); }
  }

  return (
    <>
      <div className="flex justify-between mb-4 flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <h1 className="text-xl font-bold">{t("suppliers")}</h1>
          <select value={filterCat} onChange={e => { setFilterCat(+e.target.value); setPage(1); }}
            className="border rounded px-3 py-1.5 text-sm">
            <option value={0}>全部类别</option>
            {categories.map((c: any) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </div>
        <div className="flex gap-2 flex-wrap">
          {(user?.role === "super_admin" || user?.role === "warehouse_admin") && (
            <>
              <button onClick={() => { setShowCompare(true); doCompare(); }} className="border px-3 py-2 rounded text-sm flex items-center gap-1"><Scale size={16}/>比价</button>
              <button onClick={async () => { try { const r = await api.get<any>("/suppliers/procurement-summary"); setProcurement(r.data); setShowProcurement(true); } catch {} }}
                className="border px-3 py-2 rounded text-sm flex items-center gap-1"><TrendingUp size={16}/>采购汇总</button>
              <button onClick={()=>setShowForm(true)} className="bg-primary text-white px-4 py-2 rounded-lg text-sm">新建供应商</button>
            </>
          )}
        </div>
      </div>
      {loading ? <div className="text-center py-8 text-gray-400">加载中...</div> : <DataTable columns={[
        { key: "name", label: "名称" },
        { key: "category_name", label: "类别", render: (v:any)=>v||"-" },
        { key: "contact_person", label: "联系人" },
        { key: "contact_info", label: "联系方式" },
        { key: "settlement_cycle", label: "结算周期", render: (v:any)=>v||"-" },
        { key: "id", label: "操作", render: (_:any, row:any) => (
          <div className="flex gap-2 flex-wrap">
            <button onClick={()=>aiEvaluate(row.id)} className="text-primary flex items-center gap-1 text-xs"><Sparkles size={12}/>评估</button>
            <button onClick={()=>viewDetail(row.id)} className="text-blue-500 flex items-center gap-1 text-xs"><Eye size={12}/>详情</button>
            <button onClick={()=>openProducts(row.id)} className="text-green-600 flex items-center gap-1 text-xs"><Plus size={12}/>产品</button>
          </div>
        )},
      ]} data={data} total={total} page={page} pageSize={20} onPageChange={setPage} />}
      
      {/* AI Result Modal */}
      {aiResult && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center" onClick={()=>setAiResult("")}>
          <div className="bg-white rounded-xl p-6 w-[600px] max-h-[70vh] overflow-auto" onClick={e=>e.stopPropagation()}>
            <h2 className="font-semibold mb-3">AI 供应商评估</h2>
            <div className="text-sm whitespace-pre-wrap text-gray-700">{aiResult}</div>
            <button onClick={()=>setAiResult("")} className="mt-4 px-4 py-2 border rounded text-sm">关闭</button>
          </div></div>
      )}

      {/* Detail Modal */}
      {detail && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center" onClick={()=>setDetail(null)}>
          <div className="bg-white rounded-xl p-6 w-[500px] max-h-[80vh] overflow-auto" onClick={e=>e.stopPropagation()}>
            <h2 className="font-semibold mb-4">{detail.name} 详细信息</h2>
            <div className="space-y-2 text-sm">
              <div><span className="text-gray-500">类别:</span> {detail.category_name||"-"}</div>
              <div><span className="text-gray-500">联系人:</span> {detail.contact_person||"-"}</div>
              <div><span className="text-gray-500">联系方式:</span> {detail.contact_info||"-"}</div>
              <div><span className="text-gray-500">地址:</span> {detail.address||"-"}</div>
              <div><span className="text-gray-500">付款条件:</span> {detail.payment_terms||"-"}</div>
              <div><span className="text-gray-500">合作内容:</span> {detail.cooperation_content||"-"}</div>
              <div><span className="text-gray-500">结算周期:</span> {detail.settlement_cycle||"-"}</div>
              {detail.products && detail.products.length > 0 && (
                <div><span className="text-gray-500 font-medium">产品清单:</span>
                  <table className="w-full mt-1 text-xs border"><thead><tr className="bg-gray-100"><th>产品</th><th>规格</th><th>单价</th></tr></thead>
                    <tbody>{detail.products.map((p:any)=><tr key={p.id} className="border-t"><td className="p-1">{p.product_name}</td><td>{p.spec||"-"}</td><td>{p.unit_price}{p.unit}</td></tr>)}</tbody></table>
                </div>
              )}
            </div>
            <button onClick={()=>setDetail(null)} className="mt-4 px-4 py-2 border rounded text-sm">关闭</button>
          </div></div>
      )}

      {/* Procurement Modal */}
      {showProcurement && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center" onClick={()=>setShowProcurement(false)}>
          <div className="bg-white rounded-xl p-6 w-[600px] max-h-[70vh] overflow-auto" onClick={e=>e.stopPropagation()}>
            <h2 className="font-semibold mb-3">多仓采购汇总</h2>
            {procurement.length === 0 ? <div className="text-gray-400 text-sm py-4">暂无数据</div> : procurement.map((r: any) => (
              <div key={r.supplier_id} className="mb-4 p-3 bg-gray-50 rounded">
                <div className="font-medium">{r.supplier_name}</div>
                <div className="text-xs text-gray-500">总采购额: {(r.grand_total || 0).toLocaleString()}</div>
                {r.warehouses.map((w: any) => (
                  <div key={w.warehouse_id} className="ml-4 text-xs text-gray-600">- {w.warehouse_name}: {(w.total_amount || 0).toLocaleString()}</div>
                ))}
              </div>
            ))}
            <button onClick={() => setShowProcurement(false)} className="mt-4 px-4 py-2 border rounded text-sm">关闭</button>
          </div></div>
      )}

      {/* Products Modal */}
      {showProducts && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center" onClick={()=>setShowProducts(false)}>
          <div className="bg-white rounded-xl p-6 w-[550px] max-h-[80vh] overflow-auto" onClick={e=>e.stopPropagation()}>
            <h2 className="font-semibold mb-4">产品管理</h2>
            <div className="grid grid-cols-5 gap-2 mb-4 p-3 bg-gray-50 rounded">
              <input className="border rounded px-2 py-1.5 text-sm" placeholder="产品名" value={productForm.product_name} onChange={e=>setProductForm({...productForm,product_name:e.target.value})} />
              <input className="border rounded px-2 py-1.5 text-sm" placeholder="规格" value={productForm.spec} onChange={e=>setProductForm({...productForm,spec:e.target.value})} />
              <input type="number" className="border rounded px-2 py-1.5 text-sm" placeholder="单价" value={productForm.unit_price||""} onChange={e=>setProductForm({...productForm,unit_price:+e.target.value})} />
              <input className="border rounded px-2 py-1.5 text-sm" placeholder="单位" value={productForm.unit} onChange={e=>setProductForm({...productForm,unit:e.target.value})} />
              <button onClick={addProduct} className="bg-green-600 text-white rounded px-2 py-1.5 text-sm">+添加</button>
            </div>
            {products.length === 0 ? <div className="text-gray-400 text-sm py-4 text-center">暂无产品</div> : (
              <table className="w-full text-sm"><thead><tr className="bg-gray-100"><th className="p-2 text-left">产品</th><th>规格</th><th>单价</th><th>单位</th><th></th></tr></thead>
                <tbody>{products.map((p:any)=><tr key={p.id} className="border-t"><td className="p-2">{p.product_name}</td><td>{p.spec||"-"}</td><td>{p.unit_price}</td><td>{p.unit}</td>
                  <td><button onClick={()=>deleteProduct(p.id)} className="text-red-500 text-xs"><Trash2 size={14}/></button></td></tr>)}</tbody></table>
            )}
            <button onClick={()=>setShowProducts(false)} className="mt-4 px-4 py-2 border rounded text-sm">关闭</button>
          </div></div>
      )}

      {/* Compare Modal */}
      {showCompare && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center" onClick={()=>setShowCompare(false)}>
          <div className="bg-white rounded-xl p-6 w-[750px] max-h-[85vh] overflow-auto" onClick={e=>e.stopPropagation()}>
            <h2 className="font-semibold mb-4 flex items-center gap-2"><Scale size={20}/>供应商比价</h2>
            <div className="flex gap-2 mb-4 flex-wrap">
              <input className="border rounded px-3 py-2 text-sm flex-1 min-w-[150px]" placeholder="产品名称" value={compareProduct} onChange={e=>setCompareProduct(e.target.value)} />
              <input className="border rounded px-3 py-2 text-sm flex-1 min-w-[150px]" placeholder="规格（可选）" value={compareSpec} onChange={e=>setCompareSpec(e.target.value)} />
              <select className="border rounded px-3 py-2 text-sm" value={compareCat} onChange={e=>setCompareCat(+e.target.value)}>
                <option value={0}>全部类别</option>
                {categories.map((c:any)=><option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
              <button onClick={doCompare} className="bg-primary text-white px-4 py-2 rounded text-sm">查询</button>
            </div>
            {compareData.length === 0 ? <div className="text-gray-400 text-sm py-4 text-center">请输入产品名称查询</div> : (
              <>
                <table className="w-full text-sm mb-4"><thead><tr className="bg-gray-100"><th className="p-2 text-left">排名</th><th>供应商</th><th>类别</th><th>产品</th><th>规格</th><th>单价</th></tr></thead>
                  <tbody>{compareData.map((r:any,i:number)=><tr key={i} className={`border-t ${i===0?"bg-green-50":""}`}>
                    <td className="p-2 font-bold">{i+1}</td><td>{r.supplier_name}</td><td>{r.category_name||"-"}</td><td>{r.product_name}</td><td>{r.spec||"-"}</td>
                    <td className="font-semibold text-green-700">{r.unit_price}{r.unit}</td></tr>)}</tbody></table>
                <button onClick={doAiCompare} className="bg-purple-600 text-white px-4 py-2 rounded text-sm flex items-center gap-1 mb-4"><Sparkles size={16}/>AI比价分析</button>
                {aiCompareResult && <div className="bg-purple-50 rounded-lg p-4 text-sm whitespace-pre-wrap">{aiCompareResult}</div>}
              </>
            )}
            <button onClick={()=>setShowCompare(false)} className="mt-4 px-4 py-2 border rounded text-sm">关闭</button>
          </div></div>
      )}

      {/* Create Supplier Form */}
      {showForm && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center" onClick={()=>setShowForm(false)}>
          <div className="bg-white rounded-xl p-6 w-[500px] max-h-[85vh] overflow-auto" onClick={e=>e.stopPropagation()}>
            <h2 className="font-semibold mb-4">新建供应商</h2>
            <div className="grid grid-cols-2 gap-3">
              <div><label className="text-sm">名称</label><input className="border rounded px-3 py-2 w-full" value={form.name} onChange={e=>setForm({...form,name:e.target.value})} /></div>
              <div><label className="text-sm">类别</label>
                <select className="border rounded px-3 py-2 w-full" value={form.category_id} onChange={e=>setForm({...form,category_id:+e.target.value})}>
                  <option value={0}>选择类别</option>
                  {categories.map((c:any)=><option key={c.id} value={c.id}>{c.name}</option>)}
                </select>
              </div>
              <div><label className="text-sm">联系人</label><input className="border rounded px-3 py-2 w-full" value={form.contact_person} onChange={e=>setForm({...form,contact_person:e.target.value})} /></div>
              <div><label className="text-sm">联系方式</label><input className="border rounded px-3 py-2 w-full" value={form.contact_info} onChange={e=>setForm({...form,contact_info:e.target.value})} /></div>
              <div><label className="text-sm">地址</label><input className="border rounded px-3 py-2 w-full" value={form.address} onChange={e=>setForm({...form,address:e.target.value})} /></div>
              <div><label className="text-sm">付款条件</label><input className="border rounded px-3 py-2 w-full" value={form.payment_terms} onChange={e=>setForm({...form,payment_terms:e.target.value})} /></div>
              <div><label className="text-sm">结算周期</label><input className="border rounded px-3 py-2 w-full" value={form.settlement_cycle} onChange={e=>setForm({...form,settlement_cycle:e.target.value})} placeholder="如: 月结30天" /></div>
            </div>
            <div className="mt-3"><label className="text-sm">合作内容</label><textarea className="border rounded px-3 py-2 w-full" rows={2} value={form.cooperation_content} onChange={e=>setForm({...form,cooperation_content:e.target.value})} /></div>
            <div className="mt-3 flex items-center gap-2">
              <input className="border rounded px-3 py-2 text-sm flex-1" placeholder="自定义新类别" value={newCatName} onChange={e=>setNewCatName(e.target.value)} />
              <button onClick={addCategory} className="px-3 py-2 bg-gray-100 rounded text-sm">+添加类别</button>
            </div>
            <div className="flex justify-end gap-3 mt-6"><button onClick={()=>setShowForm(false)} className="px-4 py-2 border rounded">取消</button><button onClick={handleCreate} className="px-4 py-2 bg-primary text-white rounded">保存</button></div>
          </div></div>
      )}
    </>
  );
}

"use client";
import { useEffect, useState, useRef } from "react";
import DataTable from "@/components/common/DataTable";
import { api, getToken } from "@/lib/api";
import { useI18n } from "@/hooks/useI18n";
import { useToast } from "@/components/ui/Toast";
import { useAuth } from "@/hooks/useAuth";
import { useRouter } from "next/navigation";
import { Sparkles, Eye, TrendingUp, Scale, Plus, Trash2, Download, Upload } from "lucide-react";

export default function SuppliersPage() {
  const { t } = useI18n();
  const { toast } = useToast(); const { user } = useAuth(); const router = useRouter();
  const [data, setData] = useState<any[]>([]); const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [showForm, setShowForm] = useState(false);
  const [categories, setCategories] = useState<any[]>([]);
  const [filterCat, setFilterCat] = useState(1);
  const [form, setForm] = useState({ name: "", contact_person: "", contact_info: "", address: "", payment_terms: "", cooperation_content: "", settlement_cycle: "", category_id: 0 });
  const [aiResult, setAiResult] = useState("");
  const [procurement, setProcurement] = useState<any>(null);
  const [showProcurement, setShowProcurement] = useState(false);
  const [detail, setDetail] = useState<any>(null);
  // Products
  const [products, setProducts] = useState<any[]>([]);
  const [showProducts, setShowProducts] = useState(false);
  const [productSupplierId, setProductSupplierId] = useState(0);
  const [productForm, setProductForm] = useState({ product_name: "", spec: "", spec_price: 0, unit_price: 0, unit: "个", remark: "" });
  // Logistics prices
  const [logisticsPrices, setLogisticsPrices] = useState<any[]>([]);
  const [showLogistics, setShowLogistics] = useState(false);
  const [logisticsSupplierId, setLogisticsSupplierId] = useState(0);
  const [logisticsForm, setLogisticsForm] = useState({ transport_method: "陆运", cargo_type: "普货", origin_warehouse: "深圳仓", price_per_cbm: 0, estimated_days: "", currency: "人民币" });
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
  const [importMode, setImportMode] = useState<"products"|"logistics">("products");
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
  function downloadTemplate(mode: string) {
    window.open(`/api/v1/suppliers/import-template/${mode}`, "_blank");
  }

  async function handleImport() {
    const file = fileInputRef.current?.files?.[0];
    if (!file) { toast("error", "请选择文件"); return; }
    const token = getToken();
    const fd = new FormData(); fd.append("file", file);
    try {
      const res = await fetch(`/api/v1/suppliers/import/${importMode}`, { method: "POST", headers: { "Authorization": `Bearer ${token}` }, body: fd });
      const r = await res.json();
      if (res.ok) toast("success", r.message || "导入成功"); else toast("error", r.detail || "导入失败");
      load();
    } catch { toast("error", "导入失败"); }
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  // ─── Products ───
  async function openProducts(sid: number) {
    setProductSupplierId(sid);
    try { const r = await api.get<any>(`/suppliers/${sid}/products`); setProducts(r.data); } catch { setProducts([]); }
    setShowProducts(true);
  }
  async function addProduct() {
    try { await api.post(`/suppliers/${productSupplierId}/products`, productForm); toast("success", "产品添加成功");
      const r = await api.get<any>(`/suppliers/${productSupplierId}/products`); setProducts(r.data);
      setProductForm({ product_name: "", spec: "", spec_price: 0, unit_price: 0, unit: "个", remark: "" });
    } catch (err: any) { toast("error", "添加失败"); }
  }
  async function deleteProduct(pid: number) {
    try { await api.delete(`/suppliers/${productSupplierId}/products/${pid}`); toast("success", "已删除");
      const r = await api.get<any>(`/suppliers/${productSupplierId}/products`); setProducts(r.data);
    } catch { toast("error", "删除失败"); }
  }

  // ─── Logistics Prices ───
  async function openLogistics(sid: number) {
    setLogisticsSupplierId(sid);
    try { const r = await api.get<any>(`/suppliers/${sid}/logistics-prices`); setLogisticsPrices(r.data); } catch { setLogisticsPrices([]); }
    setShowLogistics(true);
  }
  async function addLogisticsPrice() {
    try { await api.post(`/suppliers/${logisticsSupplierId}/logistics-prices`, logisticsForm); toast("success", "报价添加成功");
      const r = await api.get<any>(`/suppliers/${logisticsSupplierId}/logistics-prices`); setLogisticsPrices(r.data);
      setLogisticsForm({ transport_method: "陆运", cargo_type: "普货", origin_warehouse: "深圳仓", price_per_cbm: 0, estimated_days: "", currency: "人民币" });
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
      const r = await api.post("/suppliers/ai-compare", { compare_data: compareData, mode: compareMode });
      setAiCompareResult(r.result || "分析完成");
    } catch (e: any) { setAiCompareResult(e.message); }
  }

  async function addCategory() {
    if (!newCatName.trim()) return;
    try { await api.post(`/suppliers/categories?name=${encodeURIComponent(newCatName.trim())}`); toast("success", "类别已添加"); setNewCatName(""); loadCategories(); }
    catch { toast("error", "添加失败"); }
  }

  async function viewDetail(sid: number) {
    try { const r = await api.get<any>(`/suppliers/${sid}`); setDetail(r); } catch {}
  }

  async function deleteSupplier(sid: number) {
    if (!confirm("确定要删除该供应商吗？")) return;
    try { await api.delete(`/suppliers/${sid}`); toast("success", "已删除"); load(); }
    catch (err: any) { toast("error", err.message || "删除失败"); }
  }

  const isAdmin = user?.role === "super_admin" || user?.role === "warehouse_admin";

  return (
    <>
      <div className="flex justify-between mb-4 flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <h1 className="text-xl font-bold mr-2">{t("suppliers")}</h1>
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
          {isAdmin && (
            <>
              {/* Import dropdown */}
              <div className="relative group">
                <button className="border px-3 py-2 rounded text-sm flex items-center gap-1"><Upload size={16}/>批量导入</button>
                <div className="absolute right-0 top-full mt-1 bg-white border rounded-lg shadow-lg z-40 w-48 hidden group-hover:block py-1">
                  <button onClick={() => { setImportMode("products"); fileInputRef.current?.click(); }} className="w-full text-left px-3 py-2 text-sm hover:bg-gray-50">导入耗材产品</button>
                  <button onClick={() => { setImportMode("logistics"); fileInputRef.current?.click(); }} className="w-full text-left px-3 py-2 text-sm hover:bg-gray-50">导入物流价格</button>
                  <div className="border-t my-1" />
                  <button onClick={() => downloadTemplate("products")} className="w-full text-left px-3 py-2 text-sm hover:bg-gray-50 flex items-center gap-1"><Download size={14}/>耗材模板</button>
                  <button onClick={() => downloadTemplate("logistics")} className="w-full text-left px-3 py-2 text-sm hover:bg-gray-50 flex items-center gap-1"><Download size={14}/>物流模板</button>
                </div>
              </div>
              <input ref={fileInputRef} type="file" accept=".xlsx,.xls" onChange={handleImport} className="hidden" />
              <button onClick={() => { setCompareMode("product"); setShowCompare(true); }}
                className="border px-3 py-2 rounded text-sm flex items-center gap-1"><Scale size={16}/>比价</button>
              <button onClick={async () => { try { const r = await api.get<any>("/suppliers/procurement-summary"); setProcurement(r); setShowProcurement(true); } catch {} }}
                className="border px-3 py-2 rounded text-sm flex items-center gap-1"><TrendingUp size={16}/>采购汇总</button>
              <button onClick={() => { setForm({...form, category_id: filterCat}); setShowForm(true); }} className="bg-primary text-white px-4 py-2 rounded-lg text-sm">新建供应商</button>
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
          <div className="flex gap-2 flex-wrap">
            {row.category_name === "耗材商" && (
              <button onClick={()=>openProducts(row.id)} className="text-green-600 flex items-center gap-1 text-xs"><Plus size={12}/>产品</button>
            )}
            {row.category_name === "物流" && (
              <button onClick={()=>openLogistics(row.id)} className="text-orange-600 flex items-center gap-1 text-xs"><TrendingUp size={12}/>物流</button>
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
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center" onClick={()=>setShowProducts(false)}>
          <div className="bg-white rounded-xl p-6 w-[600px] max-h-[80vh] overflow-auto" onClick={e=>e.stopPropagation()}>
            <h2 className="font-semibold mb-4">产品管理</h2>
            <div className="grid grid-cols-5 gap-2 mb-4 p-3 bg-gray-50 rounded">
              <input className="border rounded px-2 py-1.5 text-sm" placeholder="产品名" value={productForm.product_name} onChange={e=>setProductForm({...productForm,product_name:e.target.value})} />
              <input className="border rounded px-2 py-1.5 text-sm" placeholder="产品规格" value={productForm.spec} onChange={e=>setProductForm({...productForm,spec:e.target.value})} />
              <input type="number" className="border rounded px-2 py-1.5 text-sm" placeholder="规格报价" value={productForm.spec_price||""} onChange={e=>setProductForm({...productForm,spec_price:+e.target.value})} />
              <input type="number" className="border rounded px-2 py-1.5 text-sm" placeholder="单价" value={productForm.unit_price||""} onChange={e=>setProductForm({...productForm,unit_price:+e.target.value})} />
              <button onClick={addProduct} className="bg-green-600 text-white rounded px-2 py-1.5 text-sm">+添加</button>
            </div>
            {products.length === 0 ? <div className="text-gray-400 text-sm py-4 text-center">暂无产品</div> : (
              <table className="w-full text-sm"><thead><tr className="bg-gray-100"><th className="p-2 text-left">产品名</th><th>产品规格</th><th>规格报价</th><th>单价</th><th></th></tr></thead>
                <tbody>{products.map((p:any)=><tr key={p.id} className="border-t"><td className="p-2">{p.product_name}</td><td>{p.spec||"-"}</td><td>{p.spec_price != null ? p.spec_price : "-"}</td><td>{p.unit_price}</td>
                  <td><button onClick={()=>deleteProduct(p.id)} className="text-red-500 text-xs"><Trash2 size={14}/></button></td></tr>)}</tbody></table>
            )}
            <button onClick={()=>setShowProducts(false)} className="mt-4 px-4 py-2 border rounded text-sm">关闭</button>
          </div></div>
      )}

      {/* Logistics Prices Modal */}
      {showLogistics && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center" onClick={()=>setShowLogistics(false)}>
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
            <div className="grid grid-cols-4 gap-2 mb-4 p-3 bg-gray-50 rounded">
              <div><label className="text-xs text-gray-500">单价(元/方)</label><input type="number" className="border rounded px-2 py-1.5 text-sm w-full" value={logisticsForm.price_per_cbm||""} onChange={e=>setLogisticsForm({...logisticsForm,price_per_cbm:+e.target.value})} /></div>
              <div><label className="text-xs text-gray-500">时效</label><input className="border rounded px-2 py-1.5 text-sm w-full" placeholder="如 5-7天" value={logisticsForm.estimated_days} onChange={e=>setLogisticsForm({...logisticsForm,estimated_days:e.target.value})} /></div>
              <div><label className="text-xs text-gray-500">币种</label><input className="border rounded px-2 py-1.5 text-sm w-full" value={logisticsForm.currency} onChange={e=>setLogisticsForm({...logisticsForm,currency:e.target.value})} /></div>
              <button onClick={addLogisticsPrice} className="bg-green-600 text-white rounded px-2 py-1.5 text-sm self-end">+添加</button>
            </div>
            {logisticsPrices.length === 0 ? <div className="text-gray-400 text-sm py-4 text-center">暂无报价</div> : (
              <table className="w-full text-sm"><thead><tr className="bg-gray-100"><th className="p-2 text-left">运输方式</th><th>货物类型</th><th>发货仓库</th><th>单价(元/方)</th><th>时效</th><th></th></tr></thead>
                <tbody>{logisticsPrices.map((p:any)=><tr key={p.id} className="border-t"><td className="p-2">{p.transport_method}</td><td>{p.cargo_type}</td><td>{p.origin_warehouse}</td><td>{p.price_per_cbm}</td><td>{p.estimated_days||"-"}</td>
                  <td><button onClick={()=>deleteLogisticsPrice(p.id)} className="text-red-500 text-xs"><Trash2 size={14}/></button></td></tr>)}</tbody></table>
            )}
            <button onClick={()=>setShowLogistics(false)} className="mt-4 px-4 py-2 border rounded text-sm">关闭</button>
          </div></div>
      )}

      {/* Compare Modal */}
      {showCompare && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center" onClick={()=>setShowCompare(false)}>
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
                <button onClick={()=>doCompare("product")} className="bg-primary text-white px-4 py-2 rounded text-sm">查询</button>
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
                <button onClick={()=>doCompare("logistics")} className="bg-primary text-white px-4 py-2 rounded text-sm">查询</button>
              </div>
            )}

            {compareData.length === 0 ? <div className="text-gray-400 text-sm py-4 text-center">请填写查询条件</div> : (
              <>
                {compareMode === "product" ? (
                  <table className="w-full text-sm mb-4"><thead><tr className="bg-gray-100"><th className="p-2 text-left">排名</th><th>供应商</th><th>类别</th><th>产品</th><th>规格</th><th>规格报价</th><th>单价</th></tr></thead>
                    <tbody>{compareData.map((r:any,i:number)=><tr key={i} className={`border-t ${i===0?"bg-green-50":""}`}>
                      <td className="p-2 font-bold">{i+1}</td><td>{r.supplier_name}</td><td>{r.category_name||"-"}</td><td>{r.product_name}</td><td>{r.spec||"-"}</td>
                      <td className="text-sm">{r.spec_price != null ? r.spec_price + (r.unit||"") : "-"}</td>
                      <td className="font-semibold text-green-700">{r.unit_price}{r.unit}</td></tr>)}</tbody></table>
                ) : (
                  <table className="w-full text-sm mb-4"><thead><tr className="bg-gray-100"><th className="p-2 text-left">排名</th><th>供应商</th><th>运输</th><th>货物</th><th>发货仓</th><th>单价(元/方)</th><th>最低消费</th><th>时效</th><th>备注</th></tr></thead>
                    <tbody>{compareData.map((r:any,i:number)=><tr key={i} className={`border-t ${i===0?"bg-green-50":""}`}>
                      <td className="p-2 font-bold">{i+1}</td><td>{r.supplier_name}</td><td>{r.transport_method}</td><td>{r.cargo_type}</td>
                      <td>{r.origin_warehouse}</td><td className="font-semibold text-green-700">{r.price_per_cbm}</td>
                      <td className="text-xs">{r.min_cbm}方起 / ¥{r.min_amount}</td><td>{r.estimated_days||"-"}</td>
                      <td className="text-xs text-orange-600">{r.price_note}{r.heavy_cargo_warning&&<><br/>{r.heavy_cargo_warning}</>}</td></tr>)}</tbody></table>
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
            </div>
            <button onClick={()=>setDetail(null)} className="mt-4 px-4 py-2 border rounded text-sm">关闭</button>
          </div></div>
      )}

      {/* Procurement Modal */}
      {showProcurement && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center" onClick={()=>setShowProcurement(false)}>
          <div className="bg-white rounded-xl w-[92vw] max-w-6xl max-h-[90vh] overflow-auto p-6" onClick={e=>e.stopPropagation()}>
            <div className="flex justify-between items-center mb-6">
              <h2 className="text-xl font-bold">采购汇总报表</h2>
              <button onClick={()=>setShowProcurement(false)} className="px-4 py-2 border rounded-lg text-sm hover:bg-gray-50">关闭</button>
            </div>

            {/* 顶部总览卡片 */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
              <div className="bg-gradient-to-br from-blue-500 to-blue-600 text-white rounded-xl p-5 shadow">
                <div className="text-sm opacity-80 mb-1">本月采购总支出</div>
                <div className="text-2xl font-bold">¥{(procurement?.overview?.month_total || 0).toLocaleString()}</div>
                {procurement?.overview?.pct_change != null && (
                  <div className={`text-xs mt-2 flex items-center gap-1 ${(procurement?.overview?.pct_change>=0) ? "text-green-200" : "text-red-200"}`}>
                    {(procurement?.overview?.pct_change >= 0) ? "↑" : "↓"} 较上月 {Math.abs(procurement.overview.pct_change)}%
                  </div>
                )}
              </div>
              {Object.entries(procurement?.overview?.cat_spending || {}).map(([cat, amt]: [string, any]) => (
                <div key={cat} className={`rounded-xl p-5 shadow text-white ${cat==="耗材商" ? "bg-gradient-to-br from-emerald-500 to-emerald-600" : "bg-gradient-to-br from-orange-500 to-orange-600"}`}>
                  <div className="text-sm opacity-80 mb-1">{cat}采购</div>
                  <div className="text-2xl font-bold">¥{(amt || 0).toLocaleString()}</div>
                  <div className="text-xs mt-2 opacity-70">占比 {procurement?.overview?.month_total > 0 ? Math.round((amt || 0) / procurement.overview.month_total * 100) : 0}%</div>
                </div>
              ))}
            </div>

            {/* 主体两栏 */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* 左侧：供应商排名 */}
              <div>
                <h3 className="font-semibold mb-3 text-base flex items-center gap-2">📊 供应商支出排名</h3>
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
                          <div className="font-semibold text-sm">¥{(r.month_amount || 0).toLocaleString()}</div>
                          <div className="text-xs text-gray-400">累计 ¥{(r.total_amount || 0).toLocaleString()}</div>
                        </div>
                      </div>
                    ))}
                </div>
              </div>

              {/* 右侧：产品比价汇总 + 省钱提示 */}
              <div>
                <h3 className="font-semibold mb-3 text-base flex items-center gap-2">💰 产品比价一览</h3>
                <div className="space-y-2 max-h-[200px] overflow-auto mb-4">
                  {(procurement?.product_compare || []).length === 0 ? <div className="text-gray-400 text-sm py-4">暂无产品数据</div> :
                    (procurement?.product_compare || []).map((p: any) => (
                      <div key={p.product_name + p.spec} className="flex items-center gap-3 p-3 bg-gray-50 rounded-lg text-sm">
                        <div className="flex-1">
                          <span className="font-medium">{p.product_name}</span>
                          <span className="text-gray-400 ml-1">{p.spec || ""}</span>
                          <span className="text-xs text-gray-400 ml-2">{p.supplier_count}家供应商</span>
                        </div>
                        <div className="text-right text-xs">
                          <div>最低 <span className="text-green-600 font-semibold">¥{p.min_price}</span> <span className="text-gray-400">({p.min_supplier})</span></div>
                          <div>最高 <span className="text-red-500">¥{p.max_price}</span></div>
                        </div>
                      </div>
                    ))}
                </div>

                {/* 省钱提示 */}
                {(procurement?.savings_tips || []).length > 0 && (
                  <>
                    <h3 className="font-semibold mb-3 text-base flex items-center gap-2">💡 省钱建议</h3>
                    <div className="space-y-2 max-h-[180px] overflow-auto">
                      {(procurement?.savings_tips || []).map((t: any, i: number) => (
                        <div key={i} className="p-3 bg-amber-50 border border-amber-200 rounded-lg text-sm">
                          <div className="flex items-start gap-2">
                            <span className="text-amber-500 mt-0.5">💡</span>
                            <div>
                              <span className="font-medium">{t.product_name}{t.spec ? ` (${t.spec})` : ""}</span>
                              <span className="text-gray-600 ml-1">当前最便宜 <span className="text-green-600 font-semibold">{t.cheapest_supplier} ¥{t.cheapest_price}</span></span>
                              <div className="text-xs text-gray-500 mt-1">比最贵供应商省 ¥{t.savings_per_unit}/件</div>
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

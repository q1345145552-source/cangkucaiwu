"use client";
import ActionGate from "@/components/permissions/ActionGate";
import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { api, warehouseRequestHeaders } from '@/lib/api';
import { useSupplierAccess } from '@/hooks/useSupplierAccess';
import SkuProductMapping from '@/components/SkuProductMapping';
import { downloadExcel, checkExcel } from '@/lib/excelImport';
import ProductImportDialog from '@/components/ProductImportDialog';
import StructuredSpecifications, { SpecificationSummary } from '@/components/StructuredSpecifications';
import { specDraft, readSpecDraft, type SpecNode, type SpecAttributes } from '@/lib/specifications';

type Sku = { id: number; code: string; name: string; attributes: SpecAttributes; base_unit: string; category_id: number | null; active: boolean; version: string };
type Supplier = { id: number; name: string };
type Tag = { id: number; name: string; active: boolean; version: string };
type Product = { id: number; product_name: string; spec: string | null; unit: string | null; unit_price: number; currency: string; standard_sku_id?: number | null; mapping_status?: string; mapping_label?: string; sku_snapshot?: { code: string } | null };
type Reference = { categories: { id: number; name: string; active: boolean }[]; units: { code: string; label: string }[] };
const blank = () => ({ code: '', name: '', specifications: [] as SpecNode[], base_unit: 'piece', category_id: '', active: true });

export default function SupplierSkus() {
  const access = useSupplierAccess(), { scope } = access;
  const canRead = access.can('sku_catalog'), canManage = access.can('sku_catalog_manage') && canRead, hasSuppliers = access.can('suppliers');
  const liveScope = useRef(scope); liveScope.current = scope;
  const catalogSequence = useRef(0), productsSequence = useRef(0), suppliersSequence = useRef(0), saving = useRef(false);
  const supplierRef = useRef('');
  const [rows, setRows] = useState<Sku[]>([]), [reference, setReference] = useState<Reference>({ categories: [], units: [] }), [tags, setTags] = useState<Tag[]>([]);
  const [suppliers, setSuppliers] = useState<Supplier[]>([]), [products, setProducts] = useState<Product[]>([]), [supplierId, setSupplierId] = useState('');
  const [catalogLoaded, setCatalogLoaded] = useState(''), [productsLoaded, setProductsLoaded] = useState(''), [suppliersLoaded, setSuppliersLoaded] = useState('');
  const [catalogDenied, setCatalogDenied] = useState(false);
  const [catalogError, setCatalogError] = useState(''), [productsError, setProductsError] = useState(''), [suppliersError, setSuppliersError] = useState(''), [actionError, setActionError] = useState('');
  const [notice, setNotice] = useState(''), [busy, setBusy] = useState(false), [editing, setEditing] = useState<Sku | null>(null), [showForm, setShowForm] = useState(false), [form, setForm] = useState(blank);
  const [search, setSearch] = useState(''), [status, setStatus] = useState('all'), [mappingFilter, setMappingFilter] = useState('all');
  const [tagName, setTagName] = useState(''), [assignment, setAssignment] = useState<{ tag_ids: number[]; version: string }>({ tag_ids: [], version: '' });
  const [mappingId, setMappingId] = useState(0), [report, setReport] = useState<{ message: string; data: { product_id: number; product_name: string; candidates: { code: string }[] }[] } | null>(null), [importFile, setImportFile] = useState<File | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const sameScope = (expected: string, headers: string) => expected === liveScope.current && headers === JSON.stringify(warehouseRequestHeaders());

  async function load() {
    const seq = ++catalogSequence.current, expected = scope, headers = JSON.stringify(warehouseRequestHeaders());
    setCatalogError(''); setCatalogDenied(false); setCatalogLoaded('');
    try {
      const [catalog, ref, tagRows] = await Promise.all([api.get<{ data: Sku[] }>('/sku-catalog?include_inactive=true'), api.get<Reference>('/sku-catalog/reference'), api.get<{ data: Tag[] }>('/sku-catalog/tags')]);
      if (seq === catalogSequence.current && sameScope(expected, headers)) { setRows(catalog.data); setReference(ref); setTags(tagRows.data); setCatalogLoaded(expected); }
    } catch (error) { if (seq === catalogSequence.current && sameScope(expected, headers)) { setCatalogDenied(error instanceof Error && 'status' in error && error.status === 403); setCatalogError(error instanceof Error ? error.message : '目录读取失败'); } }
  }
  async function loadSuppliers() {
    const seq = ++suppliersSequence.current, expected = scope, headers = JSON.stringify(warehouseRequestHeaders());
    setSuppliersError(''); setSuppliersLoaded('');
    try { const value = await api.get<{ data: Supplier[] }>('/suppliers?page_size=200'); if (seq === suppliersSequence.current && sameScope(expected, headers)) { setSuppliers(value.data); setSuppliersLoaded(expected); } }
    catch (error) { if (seq === suppliersSequence.current && sameScope(expected, headers)) setSuppliersError(error instanceof Error ? error.message : '供应商读取失败'); }
  }
  async function loadProducts() {
    const seq = ++productsSequence.current, selected = supplierRef.current, expected = scope, headers = JSON.stringify(warehouseRequestHeaders());
    setProductsError(''); setProductsLoaded('');
    if (!selected) { setProducts([]); return; }
    try {
      const [productRows, assigned] = await Promise.all([api.get<{ data: Product[] }>(`/suppliers/${selected}/products`), api.get<{ tag_ids: number[]; version: string }>(`/sku-catalog/suppliers/${selected}/tags`)]);
      if (seq === productsSequence.current && selected === supplierRef.current && sameScope(expected, headers)) { setProducts(productRows.data); setAssignment(assigned); setProductsLoaded(`${expected}:${selected}`); }
    } catch (error) { if (seq === productsSequence.current && selected === supplierRef.current && sameScope(expected, headers)) setProductsError(error instanceof Error ? error.message : '供应商产品读取失败'); }
  }
  useEffect(() => {
    setRows([]); setTags([]); setProducts([]); setSuppliers([]); supplierRef.current = ''; setSupplierId(''); setReport(null); setShowForm(false); setMappingId(0); setImportFile(null); setNotice(''); setActionError(''); setSearch(''); setMappingFilter('all'); setStatus('all');
    catalogSequence.current++; productsSequence.current++; suppliersSequence.current++; setCatalogLoaded(''); setProductsLoaded(''); setSuppliersLoaded('');
    if (canRead) { void load(); if (hasSuppliers) void loadSuppliers(); }
    return () => { catalogSequence.current++; productsSequence.current++; suppliersSequence.current++; };
  }, [canRead, hasSuppliers, scope]);
  useEffect(() => { setProducts([]); setAssignment({ tag_ids: [], version: '' }); if (canRead && hasSuppliers) void loadProducts(); return () => { productsSequence.current++; }; }, [supplierId, scope, canRead, hasSuppliers]);
  function chooseSupplier(value: string) { productsSequence.current++; supplierRef.current = value; setSupplierId(value); setProducts([]); setProductsLoaded(''); setProductsError(''); setMappingFilter('all'); }
  function edit(row: Sku) { setEditing(row); setForm({ code: row.code, name: row.name, specifications: specDraft(row.attributes), base_unit: row.base_unit, category_id: row.category_id ? String(row.category_id) : '', active: row.active }); setActionError(''); setShowForm(true); }
  async function save() {
    if (saving.current) return;
    saving.current = true; setBusy(true); setActionError(''); const expected = scope, headers = JSON.stringify(warehouseRequestHeaders());
    try {
      const body = { code: form.code, name: form.name, attributes: readSpecDraft(form.specifications, true), base_unit: form.base_unit, category_id: form.category_id ? Number(form.category_id) : null, active: form.active, ...(editing ? { expected_version: editing.version } : {}) };
      if (editing) await api.put(`/sku-catalog/${editing.id}`, body); else await api.post('/sku-catalog', body);
      if (!sameScope(expected, headers)) return;
      setShowForm(false); setNotice('标准SKU已保存。历史采购记录保持原样，已有产品关联如需更新请重新核对。'); await load(); await loadProducts();
    } catch (error) { if (sameScope(expected, headers)) setActionError(error instanceof Error ? error.message : 'SKU保存失败'); }
    finally { saving.current = false; setBusy(false); }
  }
  async function newTag() { const expected = scope; try { await api.post('/sku-catalog/tags', { name: tagName, active: true }); if (expected !== liveScope.current) return; setTagName(''); await load(); } catch (error) { if (expected === liveScope.current) setActionError(error instanceof Error ? error.message : '标签保存失败'); } }
  async function toggleTag(tag: Tag) { const expected = scope; try { await api.put(`/sku-catalog/tags/${tag.id}`, { name: tag.name, active: !tag.active, expected_version: tag.version }); if (expected === liveScope.current) await load(); } catch (error) { if (expected === liveScope.current) setActionError(error instanceof Error ? error.message : '标签更新失败'); } }
  async function saveTags() { const expected = scope, selected = supplierRef.current; try { await api.put(`/sku-catalog/suppliers/${selected}/tags`, { tag_ids: assignment.tag_ids, expected_version: assignment.version }); if (expected === liveScope.current && selected === supplierRef.current) { setNotice('本仓标签已保存，共享分类未修改'); await loadProducts(); } } catch (error) { if (expected === liveScope.current && selected === supplierRef.current) setActionError(error instanceof Error ? error.message : '标签关联失败'); } }

  if (access.loading) return <section className="card p-4"><h1 className="page-title">标准SKU目录</h1><p role="status">正在核对访问权限…</p></section>;
  if (access.error) return <section className="card p-4 space-y-3"><h1 className="page-title">标准SKU目录</h1><p role="alert">权限读取失败：{access.error}</p><button className="btn-secondary" onClick={access.retry}>重试读取权限</button></section>;
  if (!canRead) return <section className="card p-4"><h1 className="page-title">标准SKU目录</h1><p role="alert">需要标准SKU目录权限；目录查看与管理权限分别授权。</p></section>;
  const ready = catalogLoaded === scope, productsReady = productsLoaded === `${scope}:${supplierId}`;
  const visibleRows = ready ? rows : [], visibleProducts = productsReady ? products : [];
  const filteredRows = visibleRows.filter(row => (status === 'all' || row.active === (status === 'active')) && `${row.code} ${row.name}`.toLowerCase().includes(search.trim().toLowerCase()));
  const isUnmapped = (product: Product) => product.mapping_status === 'unmapped' || product.standard_sku_id == null;
  const filteredProducts = visibleProducts.filter(product => mappingFilter === 'all' || (mappingFilter === 'unmapped' ? isUnmapped(product) : !isUnmapped(product)));
  return <div className="space-y-4 min-w-0">
    <header className="flex flex-wrap justify-between gap-3"><div><h1 className="page-title">标准SKU目录</h1><p className="text-sm text-gray-600">标准SKU定义耗材规格与基本单位；供应商产品保留各家的名称和报价，通过人工关联对应。</p></div><div className="flex flex-wrap gap-2">{access.can('inventory') && <Link href="/inventory" className="btn-secondary">查看耗材库存</Link>}{canManage && <ActionGate anyOf={["sku_catalog.create"]}><button className="btn-primary" disabled={!ready} onClick={() => { setEditing(null); setForm(blank()); setActionError(''); setShowForm(true); }}>新建标准SKU</button></ActionGate>}</div></header>
    {!canManage && <p className="text-amber-700">只读模式；修改目录还需要独立的标准SKU管理权限。</p>}
    {actionError && <p role="alert" className="text-red-700 break-words">{actionError}</p>}{notice && <p role="status" className="text-green-700">{notice}</p>}
    {ready && !rows.length && <section className="card p-4 space-y-2 border-blue-200"><h2 className="font-semibold">尚未建立标准SKU</h2><p className="text-sm">先新建耗材的标准规格，再选择供应商产品进行关联；最后由管理员在库存页核实并确认真实期初。</p>{!canManage && <p className="text-sm">请联系有标准SKU管理权限的同事建档。</p>}</section>}
    <section className="card overflow-hidden" aria-label="标准SKU列表"><div className="p-4 flex flex-wrap gap-3 items-end"><h2 className="font-semibold self-center">标准SKU（仓库耗材目录）</h2><label className="text-sm">搜索<input aria-label="搜索标准SKU" className="form-input" placeholder="编码或名称" value={search} onChange={e => setSearch(e.target.value)} /></label><label className="text-sm">状态<select aria-label="标准SKU状态筛选" className="form-input" value={status} onChange={e => setStatus(e.target.value)}><option value="all">全部</option><option value="active">启用</option><option value="inactive">停用</option></select></label><span className="text-sm text-gray-600">{ready ? `${filteredRows.length} 项` : '数量待读取'}</span></div>
      {catalogError && <div role="alert" className="p-4 text-red-700">{catalogDenied ? '无权限查看标准SKU' : '目录加载失败'}：{catalogError} <button className="btn-secondary" onClick={() => void load()}>重试加载目录</button></div>}
      <div className="overflow-x-auto"><table className="w-full text-sm min-w-[680px]"><thead className="bg-gray-50 text-left"><tr><th className="p-3">SKU编码</th><th className="p-3">耗材名称</th><th className="p-3">规格</th><th className="p-3">基本单位</th><th className="p-3">状态</th><th className="p-3">操作</th></tr></thead><tbody>{filteredRows.map(row => <tr className="border-t align-top" key={row.id}><td className="p-3 font-medium">{row.code}</td><td className="p-3">{row.name}</td><td className="p-3 max-w-xs"><SpecificationSummary value={row.attributes} /></td><td className="p-3">{reference.units.find(unit => unit.code === row.base_unit)?.label || row.base_unit}</td><td className="p-3">{row.active ? '启用' : '已停用'}</td><td className="p-3">{canManage && <ActionGate anyOf={["sku_catalog.update"]}><button className="btn-secondary" aria-label={`编辑SKU ${row.code}`} onClick={() => edit(row)}>编辑 / 停用</button></ActionGate>}</td></tr>)}{!filteredRows.length && <tr><td colSpan={6} className="p-8 text-center text-gray-600">{!ready ? catalogError ? '未能读取目录，请重试。' : <span role="status">标准SKU读取中…</span> : !rows.length ? '尚未建立标准SKU，请先新建。供应商产品仍可在下方查看。' : '当前筛选无记录。'}</td></tr>}</tbody></table></div>
    </section>
    {hasSuppliers ? <section id="supplier-products" className="card p-4 space-y-3" aria-label="供应商产品与标准SKU关联"><h2 className="font-semibold">供应商产品（报价与关联）</h2><p className="text-sm text-gray-600">选择供应商查看其产品。未映射表示尚未关联标准SKU，不代表产品不存在。</p>
      <label className="block text-sm">选择本仓供应商<select aria-label="目录供应商" className="form-input" value={supplierId} disabled={suppliersLoaded !== scope} onChange={e => chooseSupplier(e.target.value)}><option value="">请选择供应商；多供应商导入可保持不选</option>{suppliersLoaded === scope && suppliers.map(supplier => <option value={supplier.id} key={supplier.id}>{supplier.name}</option>)}</select></label>
      {suppliersError && <p role="alert" className="text-red-700">供应商加载失败：{suppliersError} <button className="btn-secondary" onClick={() => void loadSuppliers()}>重试读取供应商</button></p>}
      <div className="flex flex-wrap gap-3 items-center"><button className="btn-secondary" onClick={async () => { try { await downloadExcel('/suppliers/import-template/products', 'products_import_template.xlsx'); } catch (error) { setActionError(error instanceof Error ? error.message : '模板下载失败'); } }}>下载产品模板.xlsx</button><label className="btn-secondary cursor-pointer">导入供应商产品<input ref={fileInput} type="file" accept=".xlsx" aria-label="导入产品Excel" className="sr-only" onChange={e => { const file = e.target.files?.[0]; e.target.value = ''; if (file) try { checkExcel(file); setImportFile(file); } catch (error) { setActionError(error instanceof Error ? error.message : '文件无法导入'); } }} /></label></div>
      {productsError && <p role="alert" className="text-red-700">供应商产品加载失败：{productsError} <button className="btn-secondary" onClick={() => void loadProducts()}>重试读取供应商产品</button></p>}
      {productsReady && <div className="flex flex-wrap gap-3 items-center"><p className="text-sm">供应商产品 {visibleProducts.length} 条 · 未映射 {visibleProducts.filter(isUnmapped).length} 条</p><label className="text-sm">关联状态<select aria-label="供应商产品关联筛选" className="form-input" value={mappingFilter} onChange={e => setMappingFilter(e.target.value)}><option value="all">全部</option><option value="unmapped">未映射</option><option value="linked">已有关联（含待核对）</option></select></label></div>}
      <div className="overflow-x-auto"><table className="w-full text-sm min-w-[640px]"><thead className="bg-gray-50 text-left"><tr><th className="p-3">供应商产品</th><th className="p-3">原规格 / 报价单位</th><th className="p-3">单价</th><th className="p-3">关联状态</th><th className="p-3">操作</th></tr></thead><tbody>{filteredProducts.map(product => <tr key={product.id} className="border-t"><td className="p-3">{product.product_name}</td><td className="p-3">{product.spec || '规格未填'} · {product.unit || '单位未知'}</td><td className="p-3">{product.unit_price} {product.currency}</td><td className="p-3"><span className={isUnmapped(product) ? 'text-amber-800 bg-amber-50 rounded px-2 py-1' : 'text-blue-700'}>{product.mapping_label || (isUnmapped(product) ? '未映射 / 待关联' : '已有历史关联，待核对')}</span><p>{product.sku_snapshot?.code || ''}</p></td><td className="p-3"><button className="btn-secondary" aria-label={`核对产品 ${product.id}`} onClick={() => setMappingId(product.id)}>{canManage ? '查看 / 人工映射' : '查看映射'}</button></td></tr>)}{!filteredProducts.length && <tr><td colSpan={5} className="p-6 text-center text-gray-600">{!supplierId ? '请选择供应商查看产品。' : productsError ? '未能读取产品，请重试。' : !productsReady ? <span role="status">供应商产品读取中…</span> : products.length ? '当前筛选无记录。' : '该供应商尚无产品，可录入或导入其报价。'}</td></tr>}</tbody></table></div>
      <details className="border rounded p-3"><summary className="cursor-pointer font-medium">仓内标签与旧产品核对</summary><div className="space-y-3 mt-3"><p className="text-sm">标签只用于本仓分类，不改历史供应商档案。</p>{canManage && <div className="flex gap-2"><input aria-label="新仓内标签" className="form-input min-w-0" maxLength={50} value={tagName} onChange={e => setTagName(e.target.value)} /><ActionGate anyOf={["sku_catalog.create_tag#operate"]}><button className="btn-secondary shrink-0" disabled={!tagName.trim()} onClick={newTag}>新建标签</button></ActionGate></div>}<div className="flex flex-wrap gap-2">{tags.map(tag => <div className="border rounded p-2" key={tag.id}>{tag.name} {!tag.active && '（停用）'} {canManage && <ActionGate anyOf={["sku_catalog.update_tag#operate"]}><button aria-label={`${tag.active ? '停用' : '启用'}标签 ${tag.name}`} onClick={() => toggleTag(tag)} className="text-blue-600">{tag.active ? '停用' : '启用'}</button></ActionGate>}</div>)}</div>{supplierId && canManage && productsReady && <div className="border rounded p-3 space-y-2"><p>当前供应商的仓内标签：</p>{tags.map(tag => <label className="flex gap-2" key={tag.id}><input type="checkbox" checked={assignment.tag_ids.includes(tag.id)} disabled={!tag.active && !assignment.tag_ids.includes(tag.id)} onChange={e => setAssignment({ ...assignment, tag_ids: e.target.checked ? [...assignment.tag_ids, tag.id] : assignment.tag_ids.filter(id => id !== tag.id) })} />{tag.name}</label>)}<ActionGate anyOf={["sku_catalog.assign_tags#operate"]}><button className="btn-secondary" onClick={saveTags}>保存供应商标签</button></ActionGate></div>}<button className="btn-secondary" onClick={async () => { const expected = scope; try { const result = await api.get<typeof report>('/sku-catalog/history-candidates'); if (expected === liveScope.current) setReport(result); } catch (error) { if (expected === liveScope.current) setActionError(error instanceof Error ? error.message : '旧产品核对读取失败'); } }}>只读扫描旧产品候选</button>{report && <div className="text-sm"><p>{report.message}；共 {report.data.length} 条未映射产品</p>{report.data.map(product => <p key={product.product_id}>#{product.product_id} {product.product_name}：{product.candidates.map(candidate => candidate.code).join('、') || '没有可靠候选，待人工核对'}</p>)}</div>}</div></details>
    </section> : <section className="card p-4"><h2 className="font-semibold">供应商产品</h2><p className="text-sm">查看供应商产品和人工关联另需供应商管理权限。</p></section>}
    <details className="card p-4"><summary className="cursor-pointer font-medium">SKU与关联使用帮助</summary><div className="mt-3 space-y-2 text-sm text-gray-600"><p>标准SKU是仓库统一的耗材规格；供应商产品是各商家的产品名称和报价。同名不自动合并，确认规格后再人工关联。</p><p>模板规格列可留空；导入后可使用普通表单核实材质、尺寸、包装和换算，不需要编写规格代码。</p><p>目录变更不会改写历史采购。已有关联可能需要按新版规格重新核对；未知的包装换算保持空白。</p><p>库存数量需要管理员核实真实期初；库存金额仍待配置，不在这里填写汇率或计价政策。</p></div></details>
    {showForm && <div className="modal-overlay z-50"><div role="dialog" aria-modal="true" aria-label="标准SKU编辑" className="bg-white rounded-xl w-full max-w-xl max-h-[90dvh] flex flex-col"><h2 className="p-4 border-b font-semibold">{editing ? '编辑 / 停用标准SKU' : '新建标准SKU'}</h2><div className="p-4 overflow-y-auto min-h-0 space-y-3"><label className="block">SKU编码<input aria-label="SKU编码" className="form-input" maxLength={64} value={form.code} onChange={e => setForm({ ...form, code: e.target.value })} /></label><label className="block">显示名称<input aria-label="SKU显示名称" className="form-input" maxLength={200} value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} /></label><label className="block">基本单位<select aria-label="SKU基本单位" className="form-input" value={form.base_unit} onChange={e => setForm({ ...form, base_unit: e.target.value })}>{reference.units.map(unit => <option value={unit.code} key={unit.code}>{unit.label} ({unit.code})</option>)}</select></label><label className="block">统一分类（只读参考）<select aria-label="SKU统一分类" className="form-input" value={form.category_id} onChange={e => setForm({ ...form, category_id: e.target.value })}><option value="">未分类</option>{reference.categories.filter(category => category.active || String(category.id) === form.category_id).map(category => <option key={category.id} value={category.id}>{category.name}{!category.active && '（已停用）'}</option>)}</select></label><StructuredSpecifications label="SKU规格" value={form.specifications} onChange={specifications => setForm({ ...form, specifications })} /><label className="flex gap-2"><input type="checkbox" checked={form.active} onChange={e => setForm({ ...form, active: e.target.checked })} />目录启用（取消仅停用，不删除历史）</label>{actionError && <p role="alert" className="text-red-700">{actionError}</p>}</div><div className="p-4 border-t flex justify-end gap-3"><button className="btn-secondary" disabled={busy} onClick={() => setShowForm(false)}>取消</button><ActionGate anyOf={["sku_catalog.update#operate","sku_catalog.create#operate"]}><button className="btn-primary" disabled={busy} onClick={save}>保存SKU</button></ActionGate></div></div></div>}
    {mappingId > 0 && <SkuProductMapping productId={mappingId} canEdit={canManage && hasSuppliers} onClose={() => setMappingId(0)} onDone={() => { setNotice('人工映射已保存并留痕；历史订单未修改'); void loadProducts(); }} />}
    {importFile && <ProductImportDialog canMap={canManage && hasSuppliers} file={importFile} supplierName={suppliers.find(supplier => String(supplier.id) === supplierId)?.name} supplierId={supplierId ? Number(supplierId) : undefined} onClose={() => { setImportFile(null); if (fileInput.current) fileInput.current.value = ''; }} onImported={result => { setNotice(result.message); void loadProducts(); }} />}
  </div>;
}

"use client";
import ActionGate from "@/components/permissions/ActionGate";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { useMenuPermission } from "@/hooks/useMenuPermission";
import { useToast } from "@/components/ui/Toast";

const today = () => new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Bangkok", year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());
const symbol = (currency: string) => currency === "CNY" ? "¥" : "฿";
const blank = () => ({ credit_id: "", ship_date: today(), order_count: "1", amount: "", currency: "THB", order_no: "", remark: "", request_key: crypto.randomUUID() });
type Shipment = { id: number; credit_customer_id: number; customer_id: number; customer_name: string; ship_date: string; order_count: number | null; amount: number; currency: string; order_no: string | null; remark: string | null; status: string; entrant_id: number; created_at: string; void_reason: string | null };

export default function CreditShipments({ onChanged, onSource }: { onChanged: () => void; onSource: (row: Shipment) => void }) {
  const writable = useMenuPermission("credit"), { toast } = useToast();
  const [records, setRecords] = useState<Shipment[]>([]), [total, setTotal] = useState(0), [page, setPage] = useState(1);
  const [filters, setFilters] = useState({ month: today().slice(0, 7), currency: "", customer_id: "", status: "" });
  const [totals, setTotals] = useState<Record<string, { record_count: number; order_count: number; unknown_order_count_records: number; amount: number }>>({});
  const [options, setOptions] = useState<any[]>([]), [error, setError] = useState(""), [loading, setLoading] = useState(false), [revision, setRevision] = useState(0);
  const [form, setForm] = useState<ReturnType<typeof blank> | null>(null), [editing, setEditing] = useState<Shipment | null>(null), [saving, setSaving] = useState(false);
  const [selected, setSelected] = useState<Shipment | null>(null), [voidFor, setVoidFor] = useState<Shipment | null>(null), [reason, setReason] = useState("");
  const busy = useRef(false), request = useRef(0);
  async function loadOptions() {
    const result: any[] = []; let p = 1, count = 1;
    while (result.length < count) { const r = await api.get<any>(`/credit?page=${p++}&page_size=200`); result.push(...r.data); count = r.total; if (!r.data.length) break; }
    setOptions(result); return result;
  }
  useEffect(() => { loadOptions().catch(() => setOptions([])); }, [revision]);
  useEffect(() => {
    const key = ++request.current; setLoading(true); setError(""); setRecords([]); setTotals({});
    const query = new URLSearchParams({ page: String(page), page_size: "20" });
    Object.entries(filters).forEach(([k, v]) => { if (v) query.set(k, v); });
    api.get<any>(`/credit/shipments?${query}`).then(r => { if (request.current === key) { setRecords(r.data); setTotal(r.total); setTotals(r.totals_by_currency); } })
      .catch(e => { if (request.current === key) setError(e.message); }).finally(() => { if (request.current === key) setLoading(false); });
    return () => { request.current++; };
  }, [filters, page, revision]);
  const changeFilter = (key: keyof typeof filters, value: string) => { setPage(1); setFilters(f => ({ ...f, [key]: value })); };
  async function openForm(row?: Shipment) {
    try { await loadOptions(); setEditing(row || null); setForm(row ? { ...blank(), credit_id: String(row.credit_customer_id), ship_date: row.ship_date, order_count: row.order_count == null ? "" : String(row.order_count), amount: String(row.amount), currency: row.currency, order_no: row.order_no || "", remark: row.remark || "" } : blank()); }
    catch (e: any) { toast("error", e.message); }
  }
  async function save() {
    if (!form || busy.current) return;
    if (!form.credit_id || !form.ship_date || !Number.isInteger(+form.order_count) || +form.order_count <= 0 || +form.amount <= 0 || !form.amount) { toast("error", "请选择账期客户并填写日期、正整数订单数及应收运费"); return; }
    busy.current = true; setSaving(true);
    try {
      const payload = { ship_date: form.ship_date, order_count: +form.order_count, amount: form.amount, currency: form.currency, order_no: form.order_no || null, remark: form.remark || null };
      if (editing) await api.put(`/credit/${form.credit_id}/shipment/${editing.id}`, payload);
      else await api.post(`/credit/${form.credit_id}/shipment`, { ...payload, request_key: form.request_key });
      toast("success", editing ? "发货记录已更新" : "发货已登记，仅增加应收，未记实收"); setForm(null); setSelected(null); setRevision(n => n + 1); onChanged();
    } catch (e: any) { toast("error", e.message); }
    finally { busy.current = false; setSaving(false); }
  }
  async function voidRecord() {
    if (!voidFor || busy.current) return;
    if (!reason.trim()) { toast("error", "请填写作废原因"); return; }
    busy.current = true; setSaving(true);
    try { await api.post(`/credit/${voidFor.credit_customer_id}/shipment/${voidFor.id}/void`, { reason }); toast("success", "发货记录已作废，历史记录保留"); setVoidFor(null); setSelected(null); setRevision(n => n + 1); onChanged(); }
    catch (e: any) { toast("error", e.message); } finally { busy.current = false; setSaving(false); }
  }
  return <section className="card mb-5 p-4" aria-label="客户发货记录">
    <div className="flex flex-wrap items-center justify-between gap-2 mb-3"><h2 className="font-semibold">客户发货记录</h2>{writable && <ActionGate anyOf={["credit.create_shipment"]}><button className="btn-primary text-sm" onClick={() => openForm()}>登记发货</button></ActionGate>}</div>
    <p className="text-xs text-gray-500 mb-3">发货形成应收，实际收款请登记回款。先为本仓客户开通账期，再选择对应账户；不按名称自动关联。</p>
    <div className="flex flex-wrap gap-2 mb-3">
      <input aria-label="发货月份" className="form-input w-40" type="month" value={filters.month} onChange={e => changeFilter("month", e.target.value)} />
      <select aria-label="发货客户筛选" className="form-input w-44" value={filters.customer_id} onChange={e => changeFilter("customer_id", e.target.value)}><option value="">全部本仓客户</option>{options.map(o => <option key={o.id} value={o.customer_id}>{o.customer_name}</option>)}</select>
      <select aria-label="发货币种筛选" className="form-input w-32" value={filters.currency} onChange={e => changeFilter("currency", e.target.value)}><option value="">全部币种</option><option value="THB">泰铢</option><option value="CNY">人民币</option></select>
      <select aria-label="发货状态筛选" className="form-input w-32" value={filters.status} onChange={e => changeFilter("status", e.target.value)}><option value="">全部状态</option><option value="active">有效</option><option value="voided">已作废</option></select>
    </div>
    {Object.entries(totals).map(([currency, t]) => <p key={currency} className="text-sm mb-2">{currency === "CNY" ? "人民币" : "泰铢"}：{t.record_count}条发货记录 · {t.order_count}单 · 应收运费 {symbol(currency)}{t.amount.toLocaleString()}{t.unknown_order_count_records > 0 && `（另有${t.unknown_order_count_records}条历史订单数未知）`}</p>)}
    {error ? <div role="alert" className="text-red-600">{error}<button className="btn-secondary ml-2" onClick={() => setRevision(n => n + 1)}>重试</button></div> : loading ? <p>加载中…</p> : <>
      <p className="text-xs text-gray-400 mb-2 sm:hidden">左右滑动可查看运费和操作</p><div className="overflow-x-auto"><table className="w-full text-sm min-w-[680px]"><thead><tr><th className="text-left">日期 / 客户</th><th>记录编号</th><th>订单数</th><th>应收运费</th><th>状态</th><th>操作</th></tr></thead><tbody>
        {records.map(row => <tr key={row.id} className={`border-t ${row.status === "voided" ? "text-gray-400" : ""}`}><td className="py-3">{row.ship_date}<br />{row.customer_name}</td><td className="text-center">#{row.id}</td><td className="text-center">{row.order_count ?? "未知"}</td><td className="text-center">{symbol(row.currency)}{row.amount.toLocaleString()}</td><td className="text-center">{row.status === "voided" ? "已作废" : "有效"}</td><td className="text-center"><button className="btn-secondary btn-xs" onClick={() => setSelected(row)}>详情</button>{writable && row.status !== "voided" && <><ActionGate anyOf={["credit.create_shipment"]}><button className="btn-secondary btn-xs ml-1" onClick={() => openForm(row)}>编辑</button></ActionGate><button className="btn-danger btn-xs ml-1" onClick={() => { setVoidFor(row); setReason(""); }}>作废</button></>}</td></tr>)}
        {!records.length && <tr><td colSpan={6} className="text-center py-5 text-gray-400">暂无发货记录</td></tr>}
      </tbody></table></div>
      <div className="flex gap-3 items-center justify-end mt-3 text-sm"><span>共{total}条记录</span><button className="btn-secondary" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>上一页</button><span>{page}</span><button className="btn-secondary" disabled={page * 20 >= total} onClick={() => setPage(p => p + 1)}>下一页</button></div>
    </>}
    {form && <div className="modal-overlay" role="dialog" aria-label={editing ? "编辑发货" : "登记发货"}><div className="modal-sm p-5 max-h-[90dvh] overflow-y-auto">
      <h2 className="text-lg font-semibold mb-4">{editing ? "编辑发货" : "登记发货"}</h2>
      <label className="form-label">账期客户</label><select aria-label="发货账期客户" className="form-input mb-3" value={form.credit_id} disabled={!!editing || saving} onChange={e => { const o = options.find(o => o.id === +e.target.value); setForm({ ...form, credit_id: e.target.value, currency: o?.currency || "THB" }); }}><option value="">请选择本仓账期客户</option>{options.filter(o => o.status === "active" || o.id === +form.credit_id).map(o => <option key={o.id} value={o.id}>{o.customer_name} · {o.currency}</option>)}</select>
      <p className="text-xs text-gray-500 mb-3">没有对应客户时，先在客户档案建档，再开通本仓账期。</p>
      <label className="form-label">业务日期</label><input aria-label="发货业务日期" type="date" className="form-input mb-3" value={form.ship_date} disabled={saving} onChange={e => setForm({ ...form, ship_date: e.target.value })} />
      <label className="form-label">订单数（不是发货记录条数）</label><input aria-label="发货订单数" className="form-input mb-3" type="number" min="1" step="1" value={form.order_count} disabled={saving} onChange={e => setForm({ ...form, order_count: e.target.value })} />
      <label className="form-label">应收运费 · {form.currency}</label><input aria-label="发货应收运费" className="form-input mb-3" type="number" min="0.01" step="0.01" value={form.amount} disabled={saving} onChange={e => setForm({ ...form, amount: e.target.value })} />
      <label className="form-label">订单号 / 批次参考（选填）</label><input aria-label="发货订单号" className="form-input mb-3" maxLength={100} value={form.order_no} disabled={saving} onChange={e => setForm({ ...form, order_no: e.target.value })} />
      <label className="form-label">备注（选填）</label><textarea aria-label="发货备注" className="form-input mb-3" maxLength={500} value={form.remark} disabled={saving} onChange={e => setForm({ ...form, remark: e.target.value })} />
      <p className="text-xs text-gray-500 mb-4">只登记应收，不记收入、不扣账户、不生成资金流水。已有回款的账期不能修改或作废发货。</p>
      <div className="flex justify-end gap-2"><button className="btn-secondary" disabled={saving} onClick={() => setForm(null)} data-modal-close="true">取消</button><ActionGate anyOf={["credit.update_shipment#operate","credit.create_shipment#operate"]}><button className="btn-primary" disabled={saving} onClick={save}>{saving ? "保存中…" : "保存发货"}</button></ActionGate></div>
    </div></div>}
    {selected && <div className="modal-overlay" role="dialog" aria-label="发货详情"><div className="modal-sm p-5 max-h-[90dvh] overflow-y-auto space-y-3"><h2 className="font-semibold">发货记录 #{selected.id}</h2><p>{selected.customer_name} · {selected.ship_date}</p><p>{selected.order_count ?? "未知"}单 · {symbol(selected.currency)}{selected.amount.toLocaleString()}</p><p>订单号：{selected.order_no || "—"}</p><p>备注：{selected.remark || "—"}</p><p>录入账号 #{selected.entrant_id} · {selected.created_at}</p><p>状态：{selected.status === "voided" ? `已作废 · ${selected.void_reason}` : "有效"}</p><div className="flex justify-end gap-2"><button className="btn-secondary" onClick={() => { onSource(selected); setSelected(null); }}>查看账期来源</button><button className="btn-primary" onClick={() => setSelected(null)} data-modal-close="true">关闭</button></div></div></div>}
    {voidFor && <div className="modal-overlay" role="dialog" aria-label="作废发货"><div className="modal-sm p-5 max-h-[90dvh] overflow-y-auto"><h2 className="font-semibold mb-3">作废发货 #{voidFor.id}</h2><p className="text-sm mb-3">作废后不再计入应收，记录和原因保留，不改钱包。已有回款的账期不能作废。</p><textarea aria-label="发货作废原因" className="form-input mb-3" placeholder="必填作废原因" maxLength={500} value={reason} disabled={saving} onChange={e => setReason(e.target.value)} /><div className="flex justify-end gap-2"><button className="btn-secondary" disabled={saving} onClick={() => setVoidFor(null)} data-modal-close="true">取消</button><ActionGate anyOf={["credit.void_shipment#operate"]}><button className="btn-danger" disabled={saving} onClick={voidRecord}>确认作废</button></ActionGate></div></div></div>}
  </section>;
}

"use client";
import ActionGate from "@/components/permissions/ActionGate";
import { useEffect, useState } from "react";
import { useI18n } from "@/hooks/useI18n";
import { useToast } from "@/components/ui/Toast";
import { api, getToken } from "@/lib/api";
import { useRouter } from "next/navigation";
import DataTable from "@/components/common/DataTable";
import SearchableSelect from "@/components/ui/SearchableSelect";
import { Upload, Plus } from "lucide-react";

function nowThaiMinute() {
  const parts = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Bangkok", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).formatToParts(new Date());
  const part = (type: string) => parts.find(p => p.type === type)?.value || "";
  return `${part("year")}-${part("month")}-${part("day")}T${part("hour")}:${part("minute")}`;
}
function manualTimeError(value: string) {
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(value)) return "请填写完整日期和时间，不能只填时分";
  if (value < "2020-01-01T00:00") return "时间不能早于2020年";
  if (value > nowThaiMinute()) return "不能选择未来时间，最多到当前这一分钟";
  return "";
}

const API_URL = process.env.NEXT_PUBLIC_API_URL || "/api/v1";

export default function RechargePage() {
  const { t } = useI18n();
  const { toast } = useToast(); const router = useRouter();
  const [data, setData] = useState<any[]>([]); const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState("");
  const [customers, setCustomers] = useState<any[]>([]);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [saving, setSaving] = useState(false);
  // 编辑 / 删除 / 历史
  const [editingRow, setEditingRow] = useState<any>(null);
  const [editForm, setEditForm] = useState({ customer_id: 0, declare_date: "", amount: "" as string | number, currency: "THB", payment_method: "", remark: "" });
  const [editScreenshotFile, setEditScreenshotFile] = useState<File | null>(null);
  const [deletingRow, setDeletingRow] = useState<any>(null);
  const [voidReason, setVoidReason] = useState("");
  const [voiding, setVoiding] = useState(false);
  const [historyRow, setHistoryRow] = useState<any>(null);
  const [historyData, setHistoryData] = useState<any[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);

  const [form, setForm] = useState({
    customer_id: 0, declare_date: nowThaiMinute(),
    amount: "" as string | number, currency: "THB", payment_method: "",
  });

  useEffect(() => { if (!getToken()) router.push("/login"); load(); loadCustomers(); }, [page, statusFilter]);

  async function load() {
    try { const res = await api.get<any>(`/recharge?page=${page}&page_size=20${statusFilter ? `&status=${statusFilter}` : ""}`); setData(res.data); setTotal(res.total); } catch {}
  }

  async function loadCustomers() {
    try { const r = await api.get<any>("/customers?page_size=99999"); setCustomers(r.data); } catch {}
  }

  const customerOptions = customers.map((c: any) => ({
    value: c.id,
    label: c.company_name || "",
    searchText: `${c.company_name || ""} ${c.customer_code || ""}`,
  }));

  function handleCustomerChange(cid: number) {
    const customer = customers.find(c => c.id === cid);
    if (customer) {
      setForm({
        ...form,
        customer_id: cid,
        currency: customer.default_currency || "THB",
        payment_method: customer.default_payment_method || "",
      });
    } else {
      setForm({ ...form, customer_id: cid, currency: "THB", payment_method: "" });
    }
  }

  async function handleCreate() {
    const timeError = manualTimeError(form.declare_date);
    if (timeError) { toast("error", timeError); return; }
    if (!form.customer_id) { toast("error", "请选择客户"); return; }
    if (!form.amount) { toast("error", "请填写金额"); return; }
    setSaving(true);
    try {
      const res = await api.post<any>("/recharge", {
        customer_id: form.customer_id,
        declare_date: form.declare_date,
        amount: +form.amount,
        currency: form.currency,
        payment_method: form.payment_method,
      });
      const rechargeId = res.id;

      if (selectedFile && rechargeId) {
        setUploading(true);
        const fd = new FormData();
        fd.append("recharge_id", String(rechargeId));
        fd.append("file", selectedFile);
        const upRes = await fetch(`${API_URL}/upload/recharge-screenshot`, {
          method: "POST",
          headers: { "Authorization": `Bearer ${getToken()}` },
          body: fd,
        });
        const upJson = await upRes.json().catch(() => ({}));
        setUploading(false);
        if (!upRes.ok) {
          throw new Error(upJson.detail || "截图上传失败，请重新上传");
        }
      }

      toast("success", "申报成功");
      setSelectedFile(null);
      setForm({ customer_id: 0, declare_date: nowThaiMinute(), amount: "", currency: "THB", payment_method: "" });
      load();
    } catch (err: any) { toast("error", err.message || "申报失败"); }
    setSaving(false);
  }

  // ===== 编辑 / 删除 / 历史 =====
  function openEdit(row: any) {
    setEditingRow(row);
    setEditForm({
      customer_id: row.customer_id || 0,
      declare_date: row.declare_date?.replace(" ", "T").slice(0, 16) || "",
      amount: String(row.amount || ""),
      currency: row.currency || "THB",
      payment_method: row.payment_method || "",
      remark: row.remark || "",
    });
    setEditScreenshotFile(null);
  }

  async function handleEditSave() {
    const timeError = manualTimeError(editForm.declare_date);
    if (timeError) { toast("error", timeError); return; }
    if (!editForm.customer_id) { toast("error", "请选择客户"); return; }
    if (!editForm.amount) { toast("error", "请填写金额"); return; }
    try {
      await api.put(`/recharge/${editingRow.id}`, {
        customer_id: editForm.customer_id,
        declare_date: editForm.declare_date,
        amount: +editForm.amount,
        currency: editForm.currency,
        payment_method: editForm.payment_method,
        remark: editForm.remark,
      });
      if (editScreenshotFile) {
        const fd = new FormData();
        fd.append("recharge_id", String(editingRow.id));
        fd.append("file", editScreenshotFile);
        const upRes = await fetch(`${API_URL}/upload/recharge-screenshot`, {
          method: "POST", headers: { Authorization: `Bearer ${getToken()}` }, body: fd,
        });
        const upJson = await upRes.json().catch(() => ({}));
        if (!upRes.ok) {
          throw new Error(upJson.detail || "截图上传失败，请重新上传");
        }
      }
      toast("success", "更新成功");
      setEditingRow(null);
      load();
    } catch (err: any) { toast("error", err.message || "更新失败"); }
  }

  async function handleDelete() {
    if (!voidReason.trim()) { toast("error", "请填写作废原因"); return; }
    if (voiding) return;
    setVoiding(true);
    try {
      await api.delete(`/recharge/${deletingRow.id}`, { reason: voidReason.trim() });
      toast("success", "申报已作废，记录保留，可在“已作废”筛选中查看");
      setDeletingRow(null);
      setVoidReason("");
      load();
    } catch (err: any) { toast("error", err.message || "作废失败"); }
    finally { setVoiding(false); }
  }

  async function openHistory(row: any) {
    setHistoryRow(row);
    setHistoryLoading(true);
    setHistoryData([]);
    try {
      const r = await api.get<any>(`/history?module=recharge&record_id=${row.id}&page_size=100`);
      setHistoryData(r.data || []);
    } catch {}
    setHistoryLoading(false);
  }

  const opTypeLabel = (op: string) => op === "create" ? "新建" : op === "edit" ? "编辑" : op === "delete" ? "删除" : op === "void" ? "作废" : op;
  const opTypeColor = (op: string) => op === "create" ? "bg-green-100 text-green-700" : op === "edit" ? "bg-blue-100 text-blue-700" : "bg-red-100 text-red-700";

  function renderData(obj: any): string {
    if (!obj) return "-";
    if (typeof obj === "object") {
      const labels: Record<string, string> = { is_voided: "作废状态", voided_at: "作废时间", voided_by: "作废人编号", voided_by_name: "作废人", void_reason: "作废原因" };
      return Object.entries(obj).map(([k, v]) => `${labels[k] || k}: ${k === "is_voided" ? (v ? "已作废" : "正常") : k === "voided_at" && typeof v === "string" ? new Date(v).toLocaleString("zh-CN", { timeZone: "Asia/Bangkok" }) : typeof v === "object" ? JSON.stringify(v) : v}`).join("，");
    }
    return String(obj);
  }

  const columns = [
    { key: "customer_name", label: "客户", cellClassName: "max-w-[110px] md:max-w-[180px]",
      render: (v: string) => <div className="line-clamp-2 break-all leading-snug">{v}</div> },
    { key: "declare_date", label: "申报日期", render: (v: string) => v?.slice(0, 10) },
    { key: "amount", label: "金额", align: "right" as const, render: (v: number, row: any) => <span className={row.is_voided ? "text-gray-400 line-through" : ""}>{v?.toLocaleString()}</span> },
    { key: "currency", label: "币种", hideOnMobile: true },
    { key: "payment_method", label: "付款方式", hideOnMobile: true, render: (v: string) => {
      const map: Record<string, string> = { alipay: "支付宝", wechat: "微信", bank_transfer: "银行转账", company_account: "公户" };
      return map[v] || v || "-";
    }},
    { key: "screenshot", label: "截图", render: (v: string, row: any) => v ? (
      <div className="flex items-center gap-1.5">
        <span className="bg-green-100 text-green-700 px-1.5 py-0.5 rounded text-xs">已上传</span>
        <a href={"/"+v} target="_blank" className="text-blue-600 text-xs hover:underline">查看</a>
      </div>
    ) : (
      <div className="flex items-center gap-1.5">
        <span className="bg-red-100 text-red-600 px-1.5 py-0.5 rounded text-xs">未上传</span>
        {!row.is_voided && <button onClick={() => {
          const inp = document.createElement('input'); inp.type = 'file'; inp.accept = 'image/png,image/jpeg,image/jpg,image/webp';
          inp.onchange = async (e: any) => {
            const file = e.target.files?.[0]; if (!file) return;
            const fd = new FormData(); fd.append('recharge_id', String(row.id)); fd.append('file', file);
            try {
              const upRes = await fetch(API_URL + '/upload/recharge-screenshot', { method: 'POST', headers: { Authorization: 'Bearer ' + getToken() }, body: fd });
              const upJson = await upRes.json().catch(() => ({}));
              if (!upRes.ok) { toast("error", upJson.detail || "截图补传失败"); return; }
              toast("success", "截图补传成功"); load();
            } catch { toast("error", "补传失败"); }
          }; inp.click();
        }} className="text-blue-600 text-xs hover:underline">补传</button>}
      </div>
    ) },
    { key: "match_status", label: "匹配状态", hideOnMobile: true, render: (v: string) => {
      const colors: any = { matched: "bg-green-100 text-green-700", unmatched: "bg-orange-100 text-orange-600", voided: "bg-gray-200 text-gray-500" };
      const labels: any = { matched: "已匹配", unmatched: "未匹配", voided: "已作废" };
      return <span className={`px-2 py-0.5 rounded text-xs font-medium ${colors[v]||""}`}>{labels[v]||v}</span>;
    }},
    { key: "declarer_name", label: "申报人", hideOnMobile: true },
    { key: "id", label: "操作", render: (_: any, row: any) => (
      <div className="flex items-center gap-2">
        {!row.is_voided && <><ActionGate anyOf={["recharge.edit_recharge"]}><button onClick={() => openEdit(row)} className="text-blue-600 hover:underline text-xs">编辑</button></ActionGate>
        <button onClick={() => { setVoidReason(""); setDeletingRow(row); }} className="text-red-500 hover:underline text-xs">作废</button></>}
        {row.is_voided && <span title={row.void_reason || ""} className="text-xs text-gray-500">已作废</span>}
        <button onClick={() => openHistory(row)} className="text-gray-500 hover:underline text-xs">历史</button>
      </div>
    ) },
  ];

  return (
    <>
      <h1 className="page-title mb-4">充值申报</h1>

      {/* 顶部直接操作区 */}
      <div className="card mb-5 p-5">
        <div className="flex items-center gap-2 mb-4 text-sm font-semibold text-gray-600">
          <Plus size={18} className="text-blue-600" /> 新建充值申报
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-6 gap-3 items-end">
          <div>
            <label className="form-label">客户</label>
            <SearchableSelect value={form.customer_id} options={customerOptions} onChange={(v) => handleCustomerChange(Number(v))} placeholder="选择客户（可搜索）" />
          </div>
          <div>
            <label className="form-label">申报时间</label>
            <input type="datetime-local" step="60" min="2020-01-01T00:00" max={nowThaiMinute()} aria-label="申报时间" className="form-input min-h-[44px]" value={form.declare_date} onChange={e => setForm({ ...form, declare_date: e.target.value })} />
          </div>
          <div>
            <label className="form-label">金额</label>
            <input type="number" step="0.01" className="form-input" value={form.amount} onChange={e => setForm({ ...form, amount: e.target.value === "" ? "" : +e.target.value })} />
          </div>
          <div>
            <label className="form-label">币种</label>
            <select className="form-input" value={form.currency} onChange={e => setForm({ ...form, currency: e.target.value })}>
              <option value="THB">泰铢 (THB)</option>
              <option value="CNY">人民币 (CNY)</option>
            </select>
          </div>
          <div>
            <label className="form-label">付款方式</label>
            <select className="form-input" value={form.payment_method} onChange={e => setForm({ ...form, payment_method: e.target.value })}>
              <option value="">未设置</option>
              <option value="alipay">支付宝</option>
              <option value="wechat">微信</option>
              <option value="bank_transfer">银行转账</option>
              <option value="company_account">公户</option>
            </select>
          </div>
          <div>
            <label className="form-label">截图 <span className="text-gray-400 font-normal text-xs">非必填</span></label>
            <div className="flex items-center gap-2 min-h-[44px] sm:min-h-[42px]">
              <input type="file" accept="image/png,image/jpeg,image/jpg,image/webp" onChange={(e) => setSelectedFile(e.target.files?.[0] || null)}
                className="text-xs text-gray-500 w-full min-w-0 file:mr-2 file:py-1 file:px-2 file:rounded file:border-0 file:text-xs file:bg-blue-50 file:text-blue-700" />
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3 mt-4 pt-3 border-t">
          <ActionGate anyOf={["recharge.create_recharge#operate"]}><button onClick={handleCreate} disabled={saving || uploading} className="btn-primary h-10 flex items-center gap-1.5 min-w-[120px] justify-center">
            {saving ? "保存中..." : uploading ? "上传中..." : <><Upload size={16} />提交申报</>}
          </button></ActionGate>
          <span className="text-xs text-gray-400">选择客户后，币种和付款方式自动填入客户默认值，可手动修改</span>
        </div>
      </div>

      {/* 申报列表 */}
      <label className="mb-3 flex flex-wrap items-center gap-2 text-sm text-gray-600">申报状态
        <select aria-label="申报状态" className="form-input w-auto min-h-11" value={statusFilter} onChange={event => { setPage(1); setStatusFilter(event.target.value); }}>
          <option value="">正常申报（默认）</option><option value="unmatched">未匹配</option><option value="matched">已匹配</option><option value="voided">已作废</option>
        </select>
      </label>
      <DataTable columns={columns} data={data} total={total} page={page} pageSize={20} onPageChange={setPage} rowClassName={row => row.is_voided ? "bg-gray-50 text-gray-400" : ""} />

      {/* 编辑弹窗 */}
      {editingRow && (
        <div className="modal-overlay z-50" >
          <div className="bg-white rounded-2xl w-full max-w-md shadow-2xl" onClick={e => e.stopPropagation()}>
            <div className="bg-blue-600 text-white px-6 py-4 rounded-t-2xl flex items-center gap-3">
              <h2 className="text-lg font-semibold">编辑充值申报</h2>
              <button onClick={() => setEditingRow(null)} className="ml-auto text-blue-200 hover:text-white text-xl leading-none" data-modal-close="true">&times;</button>
            </div>
            <div className="p-6 space-y-4">
              <div><label className="form-label">客户</label><SearchableSelect value={editForm.customer_id} options={customerOptions} onChange={(v) => setEditForm({ ...editForm, customer_id: Number(v) })} placeholder="选择客户（可搜索）" /></div>
              <div><label className="form-label">申报时间</label><input type="datetime-local" step="60" min="2020-01-01T00:00" max={nowThaiMinute()} aria-label="编辑申报时间" className="form-input min-h-[44px]" value={editForm.declare_date} onChange={e => setEditForm({ ...editForm, declare_date: e.target.value })} /></div>
              <div className="grid grid-cols-2 gap-3">
                <div><label className="form-label">金额</label><input type="number" step="0.01" className="form-input" value={editForm.amount} onChange={e => setEditForm({ ...editForm, amount: e.target.value === "" ? "" : +e.target.value })} /></div>
                <div><label className="form-label">币种</label><select className="form-input" value={editForm.currency} onChange={e => setEditForm({ ...editForm, currency: e.target.value })}><option value="THB">泰铢 (THB)</option><option value="CNY">人民币 (CNY)</option></select></div>
              </div>
              <div><label className="form-label">付款方式</label><select className="form-input" value={editForm.payment_method} onChange={e => setEditForm({ ...editForm, payment_method: e.target.value })}><option value="">未设置</option><option value="alipay">支付宝</option><option value="wechat">微信</option><option value="bank_transfer">银行转账</option><option value="company_account">公户</option></select></div>
              <div><label className="form-label">备注</label><input className="form-input" value={editForm.remark} onChange={e => setEditForm({ ...editForm, remark: e.target.value })} /></div>
              <div>
                <label className="form-label">截图（可选，替换）</label>
                <input type="file" accept="image/png,image/jpeg,image/jpg,image/webp" onChange={e => setEditScreenshotFile(e.target.files?.[0] || null)} className="text-xs text-gray-500 file:mr-2 file:py-1 file:px-2 file:rounded file:border-0 file:text-xs file:bg-blue-50 file:text-blue-700" />
                {editingRow.screenshot && !editScreenshotFile && <div className="mt-1 text-xs text-gray-400">已有截图 <a href={"/"+editingRow.screenshot} target="_blank" className="text-blue-500 hover:underline">查看</a></div>}
              </div>
            </div>
            <div className="border-t px-6 py-4 bg-gray-50 rounded-b-2xl flex justify-end gap-3">
              <button onClick={() => setEditingRow(null)} className="btn-secondary" data-modal-close="true">取消</button>
              <ActionGate anyOf={["recharge.edit_recharge#operate"]}><button onClick={handleEditSave} className="btn-primary">保存</button></ActionGate>
            </div>
          </div>
        </div>
      )}

      {/* 删除确认 */}
      {deletingRow && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-[70] p-4"  data-modal-overlay="true">
          <div role="dialog" aria-modal="true" aria-label="作废申报" className="bg-white rounded-2xl p-6 w-full max-w-sm shadow-2xl max-h-[85vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
            <h3 className="font-semibold text-lg mb-2">作废申报</h3>
            <p className="text-sm text-gray-500 mb-4">这条记录不会删除，只是不再参与对账和申报汇总。作废后可在“已作废”筛选中查看，操作会留下修改日志。</p>
            <label className="mb-4 block text-sm text-gray-600">作废原因 <span className="text-red-500">*</span>
              <textarea aria-label="作废原因" required maxLength={500} rows={3} className="form-input mt-1" value={voidReason} onChange={event => setVoidReason(event.target.value)} />
            </label>
            <div className="flex justify-end gap-3">
              <button onClick={() => setDeletingRow(null)} disabled={voiding} className="btn-secondary min-h-11" data-modal-close="true">取消</button>
              <ActionGate anyOf={["recharge.delete_recharge#operate"]}><button onClick={handleDelete} disabled={voiding} className="min-h-11 bg-red-500 text-white px-4 py-2 rounded-lg text-sm disabled:opacity-50">{voiding ? "作废中…" : "确认作废"}</button></ActionGate>
            </div>
          </div>
        </div>
      )}

      {/* 历史弹窗 */}
      {historyRow && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-[70] p-4"  data-modal-overlay="true">
          <div className="bg-white rounded-2xl w-full max-w-lg max-h-[80vh] overflow-y-auto shadow-2xl" onClick={e => e.stopPropagation()}>
            <div className="bg-gray-800 text-white px-6 py-4 rounded-t-2xl flex items-center gap-3 sticky top-0">
              <h2 className="text-lg font-semibold">变更历史</h2>
              <button onClick={() => setHistoryRow(null)} className="ml-auto text-gray-300 hover:text-white text-xl leading-none" data-modal-close="true">&times;</button>
            </div>
            <div className="p-5 space-y-3">
              {historyLoading ? (
                <div className="text-center py-8 text-gray-400">加载中...</div>
              ) : historyData.length === 0 ? (
                <div className="text-center py-8 text-gray-400 text-sm">暂无变更记录</div>
              ) : historyData.map((h: any) => (
                <div key={h.id} className="border rounded-lg p-3">
                  <div className="flex items-center gap-2 mb-1.5">
                    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${opTypeColor(h.operation_type)}`}>{opTypeLabel(h.operation_type)}</span>
                    <span className="text-xs text-gray-500">{h.operator_name || "-"} · {h.created_at ? new Date(h.created_at).toLocaleString("zh-CN", { timeZone: "Asia/Bangkok" }) : "-"}</span>
                  </div>
                  {h.before_data && (
                    <div className="text-xs text-gray-500 mb-1"><span className="text-gray-400">修改前：</span>{renderData(h.before_data)}</div>
                  )}
                  {h.after_data && (
                    <div className="text-xs text-gray-600"><span className="text-gray-400">修改后：</span>{renderData(h.after_data)}</div>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </>
  );
}

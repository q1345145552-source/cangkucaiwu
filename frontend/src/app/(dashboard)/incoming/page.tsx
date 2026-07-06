"use client";
import { useEffect, useState } from "react";
import { useToast } from "@/components/ui/Toast";
import { api, getToken } from "@/lib/api";
import { useRouter } from "next/navigation";
import { Download, Upload, Plus } from "lucide-react";
import DataTable from "@/components/common/DataTable";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

export default function IncomingPage() {
  const { toast } = useToast(); const router = useRouter();
  const [data, setData] = useState<any[]>([]); const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [customers, setCustomers] = useState<any[]>([]);
  const [saving, setSaving] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);

  const today = new Date().toISOString().slice(0, 10);
  const [form, setForm] = useState({
    received_date: today, amount: "", currency: "THB",
    payer_name: "", payment_method: "银行转账", remark: ""
  });

  useEffect(() => { if (!getToken()) router.push("/login"); load(); loadCustomers(); }, [page]);

  async function load() {
    setLoading(true);
    try {
      const res = await api.get<any>(`/incoming?page=${page}&page_size=20`);
      setData(res.data); setTotal(res.total);
    } catch {}
    setLoading(false);
  }

  async function loadCustomers() {
    try { const r = await api.get<any>("/customers?page_size=200"); setCustomers(r.data); } catch {}
  }

  async function handleCreate() {
    if (!form.payer_name) { toast("error", "请选择付款方"); return; }
    if (!form.amount) { toast("error", "请填写金额"); return; }

    setSaving(true);
    try {
      const res = await api.post<any>("/incoming", {
        received_date: form.received_date,
        amount: +form.amount,
        currency: form.currency,
        payer_name: form.payer_name,
        payment_method: form.payment_method,
        remark: form.remark,
      });
      // Upload screenshot if selected
      if (selectedFile && res.id) {
        const fd = new FormData();
        fd.append("recharge_id", String(res.id));
        fd.append("file", selectedFile);
        await fetch(`${API_URL}/upload/recharge-screenshot`, {
          method: "POST",
          headers: { "Authorization": `Bearer ${getToken()}` },
          body: fd,
        });
      }
      toast("success", "录入成功");
      setForm({ received_date: today, amount: "", currency: "THB", payer_name: "", payment_method: "银行转账", remark: "" });
      setSelectedFile(null);
      load();
    } catch (err: any) { toast("error", err.message || "录入失败"); }
    setSaving(false);
  }

  const columns = [
    { key: "received_date", label: "到账日期", render: (v: string) => v?.slice(0, 10) },
    { key: "amount", label: "金额", align: "right" as const, render: (v: number) => v?.toLocaleString() },
    { key: "currency", label: "币种" },
    { key: "payer_name", label: "付款方" },
    { key: "payment_method", label: "付款方式", render: (v: string) => v || "-" },
    { key: "match_status", label: "匹配状态", render: (v: string) => {
      const map: any = { matched: "已匹配", unmatched: "未匹配" };
      const color: any = { matched: "bg-green-100 text-green-700", unmatched: "bg-orange-100 text-orange-600" };
      return <span className={`px-2 py-0.5 rounded text-xs font-medium ${color[v]||""}`}>{map[v]||v}</span>;
    }},
    { key: "entrant_name", label: "录入人" },
  ];

  return (
    <>
      <h1 className="page-title mb-4">到账流水</h1>

      {/* 顶部行内录入区 */}
      <div className="card mb-5 p-5">
        <div className="flex items-center gap-2 mb-4 text-sm font-semibold text-gray-600">
          <Plus size={18} className="text-green-600" /> 录入到账流水
        </div>
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 items-end">
          <div>
            <label className="form-label">到账日期</label>
            <input type="date" className="form-input" value={form.received_date} onChange={e => setForm({ ...form, received_date: e.target.value })} />
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
            <label className="form-label">付款方</label>
            <select className="form-input" value={form.payer_name} onChange={e => setForm({ ...form, payer_name: e.target.value })}>
              <option value="">选择客户</option>
              {customers.map((c: any) => <option key={c.id} value={c.company_name}>{c.company_name}</option>)}
            </select>
          </div>
          <div>
            <label className="form-label">付款方式</label>
            <select className="form-input" value={form.payment_method} onChange={e => setForm({ ...form, payment_method: e.target.value })}>
              <option value="银行转账">银行转账</option>
              <option value="支付宝">支付宝</option>
              <option value="微信">微信</option>
              <option value="PromptPay">PromptPay</option>
            </select>
          </div>
          <div>
            <label className="form-label">备注</label>
            <input className="form-input" value={form.remark} onChange={e => setForm({ ...form, remark: e.target.value })} placeholder="可选" />
          </div>
        </div>

        <div className="flex items-center gap-3 mt-4 pt-3 border-t">
          <div className="flex items-center gap-2">
            <label className="form-label mb-0 whitespace-nowrap">截图 <span className="text-gray-400 font-normal text-xs">非必填</span></label>
            <input type="file" accept="image/png,image/jpeg,image/jpg" onChange={(e) => setSelectedFile(e.target.files?.[0] || null)}
              className="text-xs text-gray-500 file:mr-2 file:py-1 file:px-2 file:rounded file:border-0 file:text-xs file:bg-green-50 file:text-green-700" />
          </div>
          <button onClick={handleCreate} disabled={saving} className="btn-primary h-10 flex items-center gap-1.5 min-w-[100px] justify-center">
            {saving ? "录入中..." : <><Upload size={16} />录入</>}
          </button>
        </div>
      </div>

      {/* 操作按钮行 */}
      <div className="flex items-center gap-3 mb-4">
        <button onClick={() => {
          const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";
          fetch(`${API}/incoming/template`, { headers: { "Authorization": `Bearer ${getToken()}` } })
            .then(res => res.blob()).then(blob => {
              const a = document.createElement("a"); a.href = window.URL.createObjectURL(blob);
              a.download = "incoming_template.xlsx"; a.click();
            });
        }} className="btn-secondary flex items-center gap-1 h-9"><Download size={14} />下载模板</button>
        <button onClick={() => {
          const input = document.createElement('input'); input.type = 'file'; input.accept = '.xlsx,.xls';
          input.onchange = async (e: any) => {
            const file = e.target.files?.[0]; if (!file) return;
            alert('Excel导入功能：请确保文件包含 received_date, amount, currency, payer_name 列');
          }; input.click();
        }} className="btn-secondary h-9">批量导入Excel</button>
      </div>

      {loading ? <div className="text-center py-8 text-gray-400">加载中...</div> : (
        <DataTable columns={columns} data={data} total={total} page={page} pageSize={20} onPageChange={setPage} />
      )}
    </>
  );
}

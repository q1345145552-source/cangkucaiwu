"use client";
import { useEffect, useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import { useI18n } from "@/hooks/useI18n";
import { api, getToken } from "@/lib/api";
import { useRouter } from "next/navigation";
import DataTable from "@/components/common/DataTable";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

export default function RechargePage() {
  const { t } = useI18n(); const { user } = useAuth(); const router = useRouter();
  const [data, setData] = useState<any[]>([]); const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1); const [showForm, setShowForm] = useState(false);
  const [customers, setCustomers] = useState<any[]>([]);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [form, setForm] = useState({ customer_id: 0, declare_date: "", amount: 0, currency: "THB", payment_method: "", transaction_no: "", remark: "" });

  useEffect(() => { if (!getToken()) router.push("/login"); load(); loadCustomers(); }, [page]);

  async function load() {
    const res = await api.get<any>(`/recharge?page=${page}&page_size=20`);
    setData(res.data); setTotal(res.total);
  }

  async function loadCustomers() {
    try { const r = await api.get<any>("/customers?page_size=100"); setCustomers(r.data); } catch {}
  }

  async function handleCreate() {
    const res = await api.post<any>("/recharge", form);
    const rechargeId = res.id;

    if (selectedFile) {
      setUploading(true);
      const token = getToken();
      const fd = new FormData();
      fd.append("recharge_id", String(rechargeId));
      fd.append("file", selectedFile);
      try {
        const uploadRes = await fetch(`${API_URL}/upload/recharge-screenshot`, {
          method: "POST",
          headers: { "Authorization": `Bearer ${token}` },
          body: fd,
        });
        if (uploadRes.ok) {
          const result = await uploadRes.json();
          console.log("Screenshot uploaded:", result.path);
        }
      } catch (err) {
        console.error("Upload failed:", err);
      }
      setUploading(false);
    }

    setShowForm(false);
    setSelectedFile(null);
    setForm({ customer_id: 0, declare_date: "", amount: 0, currency: "THB", payment_method: "", transaction_no: "", remark: "" });
    load();
  }

  const columns = [
    { key: "customer_name", label: "客户" },
    { key: "declare_date", label: "申报日期", render: (v: string) => v?.slice(0,10) },
    { key: "amount", label: "金额" },
    { key: "currency", label: "币种" },
    { key: "payment_method", label: "付款方式" },
    { key: "screenshot", label: "截图", render: (v: string) => v ? <a href={"http://localhost:8000/"+v} target="_blank" className="text-primary text-xs">查看</a> : "-" },
    { key: "match_status", label: "匹配状态", render: (v: string) => {
      const colors: any = { matched: "text-green-600", unmatched: "text-orange-600" };
      return <span className={colors[v] || ""}>{v === "matched" ? "已匹配" : "未匹配"}</span>;
    }},
    { key: "declarer_name", label: "申报人" },
  ];

  return (
    <>
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-bold">{t("recharge")}</h1>
        <button onClick={() => setShowForm(true)} className="bg-primary text-white px-4 py-2 rounded-lg text-sm">新建申报</button>
      </div>
      <DataTable columns={columns} data={data} total={total} page={page} pageSize={20} onPageChange={setPage} />
      {showForm && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center">
          <div className="bg-white rounded-xl w-full max-w-md p-6 max-h-[90vh] overflow-y-auto">
            <h2 className="text-lg font-semibold mb-4">新建充值申报</h2>
            <div className="space-y-3">
              <div><label className="block text-sm mb-1">客户</label><select className="border rounded px-3 py-2 w-full" value={form.customer_id} onChange={e => setForm({...form, customer_id: +e.target.value})}><option value={0}>选择客户</option>{customers.map((c: any) => <option key={c.id} value={c.id}>{c.company_name}</option>)}</select></div>
              <div><label className="block text-sm mb-1">申报日期</label><input type="date" className="border rounded px-3 py-2 w-full" value={form.declare_date} onChange={e => setForm({...form, declare_date: e.target.value})} /></div>
              <div><label className="block text-sm mb-1">金额</label><input type="number" step="0.01" className="border rounded px-3 py-2 w-full" value={form.amount} onChange={e => setForm({...form, amount: +e.target.value})} /></div>
              <div><label className="block text-sm mb-1">币种</label><select className="border rounded px-3 py-2 w-full" value={form.currency} onChange={e => setForm({...form, currency: e.target.value})}><option value="THB">THB</option><option value="CNY">CNY</option></select></div>
              <div><label className="block text-sm mb-1">付款方式</label><select className="border rounded px-3 py-2 w-full" value={form.payment_method} onChange={e => setForm({...form, payment_method: e.target.value})}><option value="">选择</option><option value="alipay">支付宝</option><option value="wechat">微信</option><option value="bank_transfer">银行转账</option></select></div>
              <div><label className="block text-sm mb-1">交易单号</label><input className="border rounded px-3 py-2 w-full" value={form.transaction_no} onChange={e => setForm({...form, transaction_no: e.target.value})} /></div>
              <div><label className="block text-sm mb-1">备注</label><input className="border rounded px-3 py-2 w-full" value={form.remark} onChange={e => setForm({...form, remark: e.target.value})} /></div>
              <div>
                <label className="block text-sm mb-1">付款截图</label>
                <input type="file" accept="image/png,image/jpeg,image/jpg" onChange={(e) => setSelectedFile(e.target.files?.[0] || null)} className="border rounded px-3 py-2 w-full text-sm" />
                <div className="text-xs text-gray-400 mt-1">截图非必填，支持 PNG/JPG 格式</div>
              </div>
            </div>
            <div className="flex justify-end gap-3 mt-6">
              <button onClick={() => setShowForm(false)} className="px-4 py-2 border rounded-lg text-sm">取消</button>
              <button onClick={handleCreate} disabled={uploading} className="px-4 py-2 bg-primary text-white rounded-lg text-sm disabled:opacity-50">
                {uploading ? "上传中..." : "保存"}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

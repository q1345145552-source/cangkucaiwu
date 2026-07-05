"use client";
import { useEffect, useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import { useI18n } from "@/hooks/useI18n";
import { useToast } from "@/components/ui/Toast";
import { api, getToken } from "@/lib/api";
import { useRouter } from "next/navigation";
import DataTable from "@/components/common/DataTable";

export default function IncomingPage() {
  const { t } = useI18n();
  const { toast } = useToast(); const { user } = useAuth(); const router = useRouter();
  const [data, setData] = useState<any[]>([]); const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1); const [showForm, setShowForm] = useState(false);
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState({ received_date: "", amount: 0, currency: "THB", payer_name: "", payment_method: "", remark: "" });

  useEffect(() => { if (!getToken()) router.push("/login"); load(); }, [page]);

  async function load() {
    setLoading(true);
    try {
      const res = await api.get<any>(`/incoming?page=${page}&page_size=20`);
      setData(res.data); setTotal(res.total);
    } catch {}
    setLoading(false);
  }

  async function handleCreate() {
    await api.post("/incoming", form);
    setShowForm(false); load();
  }

  const columns = [
    { key: "received_date", label: "到账日期", render: (v: string) => v?.slice(0,10) },
    { key: "amount", label: "金额" },
    { key: "currency", label: "币种" },
    { key: "payer_name", label: "付款方" },
    { key: "payment_method", label: "付款方式" },
    { key: "match_status", label: "匹配状态" },
    { key: "entrant_name", label: "录入人" },
  ];

  return (
    <>
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-bold">{t("incoming")}</h1>
        <button onClick={() => setShowForm(true)} className="bg-primary text-white px-4 py-2 rounded-lg text-sm">录入到账</button>
        <button onClick={() => {
          const input = document.createElement('input'); input.type = 'file'; input.accept = '.xlsx,.xls';
          input.onchange = async (e: any) => {
            const file = e.target.files?.[0]; if (!file) return;
            alert('Excel导入功能：请确保文件包含 received_date, amount, currency, payer_name 列');
          }; input.click();
        }} className="border px-4 py-2 rounded-lg text-sm">批量导入Excel</button>
      </div>
      {loading ? (
        <div className="text-center py-8 text-gray-400">加载中...</div>
      ) : (
        <DataTable columns={columns} data={data} total={total} page={page} pageSize={20} onPageChange={setPage} />
      )}
      {showForm && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center">
          <div className="bg-white rounded-xl w-full max-w-md p-6">
            <h2 className="text-lg font-semibold mb-4">录入到账流水</h2>
            <div className="space-y-3">
              <div><label className="block text-sm mb-1">到账日期</label><input type="date" className="border rounded px-3 py-2 w-full" value={form.received_date} onChange={e => setForm({...form, received_date: e.target.value})} /></div>
              <div><label className="block text-sm mb-1">金额</label><input type="number" step="0.01" className="border rounded px-3 py-2 w-full" value={form.amount} onChange={e => setForm({...form, amount: +e.target.value})} /></div>
              <div><label className="block text-sm mb-1">币种</label><select className="border rounded px-3 py-2 w-full" value={form.currency} onChange={e => setForm({...form, currency: e.target.value})}><option value="THB">THB</option><option value="CNY">CNY</option></select></div>
              <div><label className="block text-sm mb-1">付款方</label><input className="border rounded px-3 py-2 w-full" value={form.payer_name} onChange={e => setForm({...form, payer_name: e.target.value})} /></div>
              <div><label className="block text-sm mb-1">备注</label><input className="border rounded px-3 py-2 w-full" value={form.remark} onChange={e => setForm({...form, remark: e.target.value})} /></div>
            </div>
            <div className="flex justify-end gap-3 mt-6">
              <button onClick={() => setShowForm(false)} className="px-4 py-2 border rounded-lg text-sm">取消</button>
              <button onClick={handleCreate} className="px-4 py-2 bg-primary text-white rounded-lg text-sm">保存</button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

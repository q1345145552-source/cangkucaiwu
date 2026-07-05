"use client";
import { useEffect, useState } from "react";
import DataTable from "@/components/common/DataTable";
import { api, getToken } from "@/lib/api";
import { useI18n } from "@/hooks/useI18n";
import { useToast } from "@/components/ui/Toast";
import { useRouter } from "next/navigation";

export default function PayablePage() {
  const { t } = useI18n();
  const { toast } = useToast(); const router = useRouter();
  const [data, setData] = useState<any[]>([]); const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1); const [showForm, setShowForm] = useState(false);
  const [suppliers, setSuppliers] = useState<any[]>([]);
  const [cashflow, setCashflow] = useState(0);
  const [form, setForm] = useState({ supplier_id: 0, bill_number: "", bill_date: "", due_date: "", amount: 0, currency: "THB", remark: "" });

  useEffect(() => { if (!getToken()) router.push("/login"); load(); loadSuppliers(); loadCashflow(); }, [page]);

  async function load() {
    const r = await api.get<any>(`/payable?page=${page}&page_size=25`);
    setData(r.data); setTotal(r.total);
  }
  async function loadSuppliers() { try { const r = await api.get<any>("/suppliers?page_size=100"); setSuppliers(r.data); } catch {} }
  async function loadCashflow() { try { const r = await api.get<any>("/payable/cashflow-prediction"); setCashflow(r.total_pending_payable); } catch {} }

  async function handleCreate() {
    try {
      await api.post("/payable", form);
      toast("success", "创建成功");
      setShowForm(false); load();
    } catch (err: any) { toast("error", "创建失败"); } loadCashflow();
  }
  async function handlePay(billId: number) {
    await api.put(`/payable/${billId}/pay`, {});
    load(); loadCashflow();
  }

  const statusColors: any = { pending: "text-yellow-600", paid: "text-green-600", partially_paid: "text-blue-600", overdue: "text-red-600" };

  return (
    <>
      <div className="flex justify-between mb-4">
        <div><h1 className="text-xl font-bold">{t("payable")}</h1>
          <div className="text-sm text-gray-500 mt-1">待付总额: <span className="text-red-600 font-semibold">¥{cashflow.toLocaleString()}</span></div></div>
        <button onClick={()=>setShowForm(true)} className="bg-primary text-white px-4 py-2 rounded-lg text-sm">新建账单</button>
      </div>
      <DataTable columns={[
        { key: "supplier_name", label: "供应商" }, { key: "bill_number", label: "账单编号" },
        { key: "bill_date", label: "账单日期", render: (v:any)=>v?.slice(0,10) },
        { key: "due_date", label: "到期日", render: (v:any)=>v?.slice(0,10) },
        { key: "amount", label: "金额" }, { key: "paid_amount", label: "已付" },
        { key: "status", label: "状态", render: (v:any)=><span className={statusColors[v]||""}>{v}</span> },
        { key: "id", label: "操作", render: (_:any, row:any) => row.status !== "paid" ? <button onClick={()=>handlePay(row.id)} className="text-primary text-xs">付款</button> : null },
      ]} data={data} total={total} page={page} pageSize={25} onPageChange={setPage} />
      {showForm && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center"><div className="bg-white rounded-xl p-6 w-96">
          <h2 className="font-semibold mb-4">新建应付账单</h2>
          <div className="space-y-3">
            <div><label className="text-sm">供应商</label><select className="border rounded px-3 py-2 w-full" value={form.supplier_id} onChange={e=>setForm({...form,supplier_id:+e.target.value})}><option>选择</option>{suppliers.map((s:any)=><option key={s.id} value={s.id}>{s.name}</option>)}</select></div>
            <div><label className="text-sm">账单编号</label><input className="border rounded px-3 py-2 w-full" value={form.bill_number} onChange={e=>setForm({...form,bill_number:e.target.value})} /></div>
            <div><label className="text-sm">账单日期</label><input type="date" className="border rounded px-3 py-2 w-full" value={form.bill_date} onChange={e=>setForm({...form,bill_date:e.target.value})} /></div>
            <div><label className="text-sm">到期日期</label><input type="date" className="border rounded px-3 py-2 w-full" value={form.due_date} onChange={e=>setForm({...form,due_date:e.target.value})} /></div>
            <div><label className="text-sm">金额</label><input type="number" className="border rounded px-3 py-2 w-full" value={form.amount} onChange={e=>setForm({...form,amount:+e.target.value})} /></div>
          </div>
          <div className="flex justify-end gap-3 mt-6"><button onClick={()=>setShowForm(false)} className="px-4 py-2 border rounded text-sm">取消</button><button onClick={handleCreate} className="px-4 py-2 bg-primary text-white rounded text-sm">保存</button></div>
        </div></div>
      )}
    </>
  );
}

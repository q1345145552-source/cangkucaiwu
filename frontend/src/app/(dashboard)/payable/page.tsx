"use client";
import { useEffect, useState, useRef } from "react";
import DataTable from "@/components/common/DataTable";
import { api, getToken } from "@/lib/api";
import { useI18n } from "@/hooks/useI18n";
import { useToast } from "@/components/ui/Toast";
import { useRouter } from "next/navigation";
import { Upload, AlertTriangle } from "lucide-react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

export default function PayablePage() {
  const { t } = useI18n();
  const { toast } = useToast(); const router = useRouter();
  const [data, setData] = useState<any[]>([]); const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1); const [showForm, setShowForm] = useState(false);
  const [suppliers, setSuppliers] = useState<any[]>([]);
  const [cashflow, setCashflow] = useState(0);
  const [form, setForm] = useState({ supplier_id: 0, bill_number: "", bill_date: "", due_date: "", amount: 0, confirmed_amount: 0, payment_commitment_days: 0, currency: "THB", remark: "", is_fund_linked: "" });
  const [payAmounts, setPayAmounts] = useState<Record<number, number>>({});
  const [voucherFile, setVoucherFile] = useState<File | null>(null);
  const [payingBillId, setPayingBillId] = useState(0);
  const [showPayModal, setShowPayModal] = useState(false);

  useEffect(() => { if (!getToken()) router.push("/login"); load(); loadSuppliers(); loadCashflow(); }, [page]);

  async function load() {
    setLoading(true);
    try {
      const r = await api.get<any>(`/payable?page=${page}&page_size=25`);
      setData(r.data); setTotal(r.total);
    } catch (err) { console.error("加载失败:", err); }
    setLoading(false);
  }
  async function loadSuppliers() { try { const r = await api.get<any>("/suppliers?page_size=100"); setSuppliers(r.data); } catch {} }
  async function loadCashflow() { try { const r = await api.get<any>("/payable/cashflow-prediction"); setCashflow(r.total_pending_payable); } catch {} }

  async function handleCreate() {
    try {
      const res = await api.post<any>("/payable", form);
      if (res.has_diff) { toast("success", "账单创建成功，已标记对账差异"); }
      else { toast("success", "创建成功"); }
      setShowForm(false); load(); loadCashflow();
    } catch (err: any) { toast("error", err.message || "创建失败"); }
  }

  function openPayModal(billId: number, amount: number, paidAmount: number) {
    setPayAmounts(prev => ({ ...prev, [billId]: amount - paidAmount }));
    setPayingBillId(billId);
    setVoucherFile(null);
    setShowPayModal(true);
  }

  async function handlePay() {
    const payAmount = payAmounts[payingBillId] || 0;
    try {
      const token = getToken();
      await fetch(`${API_URL}/payable/${payingBillId}/pay?paid_amount=${payAmount}`, {
        method: "PUT", headers: { "Authorization": `Bearer ${token}` },
      });
      
      if (voucherFile) {
        const token = getToken();
        const fd = new FormData();
        fd.append("file", voucherFile);
        const uploadRes = await fetch(`${API_URL}/payable/${payingBillId}/upload-voucher`, {
          method: "POST", headers: { "Authorization": `Bearer ${token}` }, body: fd,
        });
        if (uploadRes.ok) toast("success", "付款成功，凭证已上传");
        else toast("success", "付款成功");
      } else {
        toast("success", "付款成功");
      }
      setShowPayModal(false); load(); loadCashflow();
    } catch (err: any) { toast("error", "付款失败"); }
  }

  const statusColors: any = { pending: "text-yellow-600", paid: "text-green-600", partially_paid: "text-blue-600", overdue: "text-red-600" };

  return (
    <>
      <div className="flex justify-between mb-4">
        <div><h1 className="text-xl font-bold">{t("payable")}</h1>
          <div className="text-sm text-gray-500 mt-1">待付总额: <span className="text-red-600 font-semibold">{(cashflow||0).toLocaleString()}</span></div></div>
        <button onClick={()=>setShowForm(true)} className="bg-primary text-white px-4 py-2 rounded-lg text-sm">新建账单</button>
      </div>
      {loading ? <div className="text-center py-8 text-gray-400">加载中...</div> : <DataTable columns={[
        { key: "supplier_name", label: "供应商" }, { key: "bill_number", label: "账单编号" },
        { key: "bill_date", label: "账单日期", render: (v:any)=>v?.slice(0,10) },
        { key: "due_date", label: "到期日", render: (v:any)=>v?.slice(0,10) },
        { key: "amount", label: "金额", render: (v:any, row:any) => {
          const diff = row.confirmed_amount && row.confirmed_amount !== row.amount;
          return <span>{v?.toLocaleString()} {diff && <AlertTriangle size={12} className="inline text-orange-500 ml-1" title={`供应商确认: ${row.confirmed_amount}`}/>}</span>
        }},
        { key: "paid_amount", label: "已付", render: (v:any)=>v?.toLocaleString() },
        { key: "status", label: "状态", render: (v:any)=><span className={statusColors[v]||""}>{v}</span> },
        { key: "payment_commitment_days", label: "承诺天数", render: (v:any)=>v ? `${v}天` : "-" },
        { key: "is_fund_linked", label: "备用金", render: (v:any)=>v ? <span className="text-purple-600 text-xs">备用金垫付</span> : "-" },
        { key: "payment_voucher", label: "凭证", render: (v:any)=>v ? <span className="text-green-600 text-xs">已上传</span> : "-" },
        { key: "id", label: "操作", render: (_:any, row:any) => row.status !== "paid" ? <button onClick={()=>openPayModal(row.id, row.amount, row.paid_amount)} className="text-primary text-xs">付款</button> : <span className="text-gray-400 text-xs">已付</span> },
      ]} data={data} total={total} page={page} pageSize={25} onPageChange={setPage} />}
      
      {showForm && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center"><div className="bg-white rounded-xl p-6 w-[500px] max-h-[85vh] overflow-auto">
          <h2 className="font-semibold mb-4">新建应付账单</h2>
          <div className="grid grid-cols-2 gap-3">
            <div><label className="text-sm">供应商</label><select className="border rounded px-3 py-2 w-full" value={form.supplier_id} onChange={e=>setForm({...form,supplier_id:+e.target.value})}><option>选择</option>{suppliers.map((s:any)=><option key={s.id} value={s.id}>{s.name}</option>)}</select></div>
            <div><label className="text-sm">账单编号</label><input className="border rounded px-3 py-2 w-full" value={form.bill_number} onChange={e=>setForm({...form,bill_number:e.target.value})} /></div>
            <div><label className="text-sm">账单日期</label><input type="date" className="border rounded px-3 py-2 w-full" value={form.bill_date} onChange={e=>setForm({...form,bill_date:e.target.value})} /></div>
            <div><label className="text-sm">到期日期</label><input type="date" className="border rounded px-3 py-2 w-full" value={form.due_date} onChange={e=>setForm({...form,due_date:e.target.value})} /></div>
            <div><label className="text-sm">金额</label><input type="number" className="border rounded px-3 py-2 w-full" value={form.amount} onChange={e=>setForm({...form,amount:+e.target.value})} /></div>
            <div><label className="text-sm">供应商确认金额</label><input type="number" className="border rounded px-3 py-2 w-full" value={form.confirmed_amount} onChange={e=>setForm({...form,confirmed_amount:+e.target.value})} placeholder="不一致时自动标差异" /></div>
            <div><label className="text-sm">付款承诺天数</label><input type="number" className="border rounded px-3 py-2 w-full" value={form.payment_commitment_days} onChange={e=>setForm({...form,payment_commitment_days:+e.target.value})} /></div>
          </div>
          <div className="mt-3 flex items-center gap-2">
            <input type="checkbox" id="fund_linked" checked={form.is_fund_linked === "yes"} onChange={e=>setForm({...form,is_fund_linked: e.target.checked ? "yes" : ""})} />
            <label htmlFor="fund_linked" className="text-sm">备用金垫付</label>
          </div>
          <div className="flex justify-end gap-3 mt-6"><button onClick={()=>setShowForm(false)} className="px-4 py-2 border rounded text-sm">取消</button><button onClick={handleCreate} className="px-4 py-2 bg-primary text-white rounded text-sm">保存</button></div>
        </div></div>
      )}

      {showPayModal && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center"><div className="bg-white rounded-xl p-6 w-96">
          <h2 className="font-semibold mb-4">付款</h2>
          <div><label className="text-sm">付款金额</label><input type="number" className="border rounded px-3 py-2 w-full" value={payAmounts[payingBillId]||0} onChange={e=>setPayAmounts(prev=>({...prev,[payingBillId]:+e.target.value}))} /></div>
          <div className="mt-3"><label className="text-sm">上传凭证 (非必填)</label><input type="file" accept="image/*" onChange={e=>setVoucherFile(e.target.files?.[0]||null)} className="border rounded px-3 py-2 w-full text-sm" /></div>
          <div className="flex justify-end gap-3 mt-6"><button onClick={()=>setShowPayModal(false)} className="px-4 py-2 border rounded text-sm">取消</button><button onClick={handlePay} className="px-4 py-2 bg-primary text-white rounded text-sm">确认付款</button></div>
        </div></div>
      )}
    </>
  );
}

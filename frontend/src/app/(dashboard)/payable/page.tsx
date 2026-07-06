"use client";
import { useEffect, useState, useRef } from "react";
import DataTable from "@/components/common/DataTable";
import { api, getToken } from "@/lib/api";
import { useI18n } from "@/hooks/useI18n";
import { useToast } from "@/components/ui/Toast";
import { useRouter } from "next/navigation";
import { Upload, AlertTriangle, DollarSign, Clock, CheckCircle, AlertCircle } from "lucide-react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

export default function PayablePage() {
  const { t } = useI18n();
  const { toast } = useToast(); const router = useRouter();
  const [data, setData] = useState<any[]>([]); const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1); const [showForm, setShowForm] = useState(false);
  const [suppliers, setSuppliers] = useState<any[]>([]);
  const [stats, setStats] = useState<any>(null);
  const [form, setForm] = useState({ supplier_id: 0, bill_number: "", bill_date: "", due_date: "", amount: 0, confirmed_amount: 0, payment_commitment_days: 0, currency: "THB", detail: "", remark: "", is_fund_linked: "" });
  const [billFile, setBillFile] = useState<File | null>(null);
  const [payAmounts, setPayAmounts] = useState<Record<number, number>>({});
  const [voucherFile, setVoucherFile] = useState<File | null>(null);
  const [payingBillId, setPayingBillId] = useState(0);
  const [payingRow, setPayingRow] = useState<any>(null);
  const [payMethod, setPayMethod] = useState("银行转账");
  const [showPayModal, setShowPayModal] = useState(false);

  useEffect(() => { if (!getToken()) router.push("/login"); load(); loadSuppliers(); loadStats(); }, [page]);

  async function load() {
    setLoading(true);
    try { const r = await api.get<any>(`/payable?page=${page}&page_size=25`); setData(r.data); setTotal(r.total); }
    catch (err) { console.error("加载失败:", err); }
    setLoading(false);
  }
  async function loadSuppliers() { try { const r = await api.get<any>("/suppliers?page_size=100"); setSuppliers(r.data); } catch {} }
  async function loadStats() { try { const r = await api.get<any>("/payable/stats"); setStats(r); } catch {} }

  async function handleCreate() {
    try {
      const res = await api.post<any>("/payable", form);
      // Upload bill attachment if exists
      if (billFile && res.id) {
        const fd = new FormData(); fd.append("file", billFile);
        await fetch(`${API_URL}/payable/${res.id}/upload-attachment`, {
          method: "POST", headers: { "Authorization": `Bearer ${getToken()}` }, body: fd,
        });
      }
      toast("success", res.has_diff ? "账单创建成功，已标记对账差异" : "创建成功");
      setShowForm(false); setBillFile(null); setForm({ supplier_id: 0, bill_number: "", bill_date: "", due_date: "", amount: 0, confirmed_amount: 0, payment_commitment_days: 0, currency: "THB", detail: "", remark: "", is_fund_linked: "" });
      load(); loadStats();
    } catch (err: any) { toast("error", err.message || "创建失败"); }
  }

  function openPayModal(row: any) {
    const remaining = row.amount - row.paid_amount;
    setPayAmounts(prev => ({ ...prev, [row.id]: remaining > 0 ? remaining : 0 }));
    setPayingBillId(row.id);
    setPayingRow(row);
    setVoucherFile(null);
    setShowPayModal(true);
  }

  async function handlePay() {
    const payAmount = payAmounts[payingBillId] || 0;
    try {
      await fetch(`${API_URL}/payable/${payingBillId}/pay?paid_amount=${payAmount}&payment_method=${payMethod}`, {
        method: "PUT", headers: { "Authorization": `Bearer ${getToken()}` },
      });
      if (voucherFile) {
        const fd = new FormData(); fd.append("file", voucherFile);
        await fetch(`${API_URL}/payable/${payingBillId}/upload-voucher`, {
          method: "POST", headers: { "Authorization": `Bearer ${getToken()}` }, body: fd,
        });
      }
      toast("success", "付款成功");
      setShowPayModal(false); load(); loadStats();
    } catch { toast("error", "付款失败"); }
  }

  const statusColors: any = { pending: "text-yellow-600", paid: "text-green-600", partially_paid: "text-blue-600", overdue: "text-red-600" };

  return (
    <>
      <h1 className="page-title mb-5">{t("payable")}</h1>

      {/* 总览看板 */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-5">
        <div className="card bg-gradient-to-br from-blue-500 to-blue-600 text-white border-0">
          <div className="flex items-center gap-2 mb-1"><DollarSign size={18} /><span className="text-sm opacity-80">本月应付</span></div>
          <div className="text-2xl font-bold">¥{(stats?.month_total || 0).toLocaleString()}</div>
        </div>
        <div className="card bg-gradient-to-br from-red-500 to-red-600 text-white border-0">
          <div className="flex items-center gap-2 mb-1"><AlertCircle size={18} /><span className="text-sm opacity-80">逾期未付</span></div>
          <div className="text-2xl font-bold">¥{(stats?.overdue_total || 0).toLocaleString()}</div>
        </div>
        <div className="card bg-gradient-to-br from-green-500 to-green-600 text-white border-0">
          <div className="flex items-center gap-2 mb-1"><CheckCircle size={18} /><span className="text-sm opacity-80">本月已付</span></div>
          <div className="text-2xl font-bold">¥{(stats?.month_paid || 0).toLocaleString()}</div>
        </div>
        <div className="card bg-gradient-to-br from-orange-500 to-orange-600 text-white border-0">
          <div className="flex items-center gap-2 mb-1"><Clock size={18} /><span className="text-sm opacity-80">本月未付</span></div>
          <div className="text-2xl font-bold">¥{(stats?.month_unpaid || 0).toLocaleString()}</div>
        </div>
      </div>

      {/* 按供应商汇总 */}
      {(stats?.supplier_summary || []).length > 0 && (
        <div className="card mb-5">
          <h3 className="card-title">按供应商汇总（本月）</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {stats.supplier_summary.map((s: any) => (
              <div key={s.supplier_id} className="p-3 bg-gray-50 rounded-lg flex items-center justify-between cursor-pointer hover:bg-blue-50 transition-colors"
                onClick={() => router.push(`/payable?supplier_id=${s.supplier_id}`)}>
                <div>
                  <div className="font-medium text-sm">{s.supplier_name}</div>
                  <div className="text-xs text-gray-400">{s.bill_count}笔账单</div>
                </div>
                <div className="text-right text-xs">
                  <div>应付 <span className="font-medium">¥{s.total_amount.toLocaleString()}</span></div>
                  <div>已付 <span className="text-green-600">¥{s.paid_amount.toLocaleString()}</span></div>
                  <div>未付 <span className="text-red-500">¥{s.unpaid_amount.toLocaleString()}</span></div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 操作栏 + 表格 */}
      <div className="flex justify-end mb-4">
        <button onClick={()=>setShowForm(true)} className="btn-primary">新建账单</button>
      </div>
      {loading ? <div className="text-center py-8 text-gray-400">加载中...</div> : <DataTable columns={[
        { key: "supplier_name", label: "供应商" },
        { key: "bill_number", label: "账单编号" },
        { key: "bill_date", label: "账单日期", render: (v:any)=>v?.slice(0,10) },
        { key: "due_date", label: "到期日", render: (v:any)=>v?.slice(0,10) },
        { key: "amount", label: "金额", align: "right", render: (v:any, row:any) => {
          const diff = row.confirmed_amount && row.confirmed_amount !== row.amount;
          return <span>{v?.toLocaleString()} {diff && <AlertTriangle size={12} className="inline text-orange-500 ml-1" title={`供应商确认: ${row.confirmed_amount}`}/>}</span>
        }},
        { key: "paid_amount", label: "已付", align: "right", render: (v:any)=>v?.toLocaleString() },
        { key: "status", label: "状态", render: (v:any)=><span className={statusColors[v]||""}>{v}</span> },
        { key: "detail", label: "明细", render: (v:any)=>v ? <span className="text-xs text-gray-500 max-w-32 truncate block" title={v}>{v.length>12?v.slice(0,12)+"...":v}</span> : "-" },
        { key: "bill_attachment", label: "附件", render: (v:any)=>v ? <span className="text-green-600 text-xs">已上传</span> : "-" },
        { key: "payment_voucher", label: "凭证", render: (v:any)=>v ? <span className="text-green-600 text-xs">已上传</span> : "-" },
        { key: "id", label: "操作", render: (_:any, row:any) => row.status !== "paid" ? <button onClick={()=>openPayModal(row)} className="btn-primary btn-xs">付款</button> : <span className="text-gray-400 text-xs">已付</span> },
      ]} data={data} total={total} page={page} pageSize={25} onPageChange={setPage} />}
      
      {/* 新建账单弹窗 */}
      {showForm && (
        <div className="modal-overlay" onClick={()=>setShowForm(false)}>
          <div className="bg-white rounded-xl w-full max-w-lg max-h-[90vh] overflow-auto" onClick={e=>e.stopPropagation()}>
            <div className="modal-header"><h2 className="modal-title">新建应付账单</h2><button onClick={()=>setShowForm(false)} className="btn-secondary btn-sm">取消</button></div>
            <div className="modal-body">
              <div className="form-grid">
                <div className="form-group"><label className="form-label">供应商</label><select className="form-input" value={form.supplier_id} onChange={e=>setForm({...form,supplier_id:+e.target.value})}><option value={0}>选择</option>{suppliers.map((s:any)=><option key={s.id} value={s.id}>{s.name}</option>)}</select></div>
                <div className="form-group"><label className="form-label">账单编号</label><input className="form-input" value={form.bill_number} onChange={e=>setForm({...form,bill_number:e.target.value})} /></div>
                <div className="form-group"><label className="form-label">账单日期</label><input type="date" className="form-input" value={form.bill_date} onChange={e=>setForm({...form,bill_date:e.target.value})} /></div>
                <div className="form-group"><label className="form-label">到期日期</label><input type="date" className="form-input" value={form.due_date} onChange={e=>setForm({...form,due_date:e.target.value})} /></div>
                <div className="form-group"><label className="form-label">金额</label><input type="number" className="form-input" value={form.amount} onChange={e=>setForm({...form,amount:+e.target.value})} /></div>
                <div className="form-group"><label className="form-label">供应商确认金额</label><input type="number" className="form-input" value={form.confirmed_amount} onChange={e=>setForm({...form,confirmed_amount:+e.target.value})} placeholder="不一致时自动标差异" /></div>
                <div className="form-group"><label className="form-label">付款承诺天数</label><input type="number" className="form-input" value={form.payment_commitment_days} onChange={e=>setForm({...form,payment_commitment_days:+e.target.value})} /></div>
              </div>
              <div className="form-group"><label className="form-label">费用明细</label><textarea className="form-input" rows={2} value={form.detail} onChange={e=>setForm({...form,detail:e.target.value})} placeholder="如：纸箱500个x8元=4000元" /></div>
              <div className="form-group"><label className="form-label">备注</label><input className="form-input" value={form.remark} onChange={e=>setForm({...form,remark:e.target.value})} /></div>
              <div className="form-group"><label className="form-label">上传账单附件</label><input type="file" accept=".pdf,.jpg,.jpeg,.png,.xlsx,.xls" onChange={e=>setBillFile(e.target.files?.[0]||null)} className="form-input text-sm" /></div>
              <div className="flex items-center gap-2 mt-2">
                <input type="checkbox" id="fund_linked" checked={form.is_fund_linked === "yes"} onChange={e=>setForm({...form,is_fund_linked: e.target.checked ? "yes" : ""})} />
                <label htmlFor="fund_linked" className="text-sm">备用金垫付</label>
              </div>
            </div>
            <div className="modal-footer">
              <button onClick={()=>setShowForm(false)} className="btn-secondary">取消</button>
              <button onClick={handleCreate} className="btn-primary">保存</button>
            </div>
          </div></div>
      )}

      {/* 付款弹窗 */}
      {showPayModal && payingRow && (
        <div className="modal-overlay" onClick={()=>setShowPayModal(false)}>
          <div className="bg-white rounded-xl w-full max-w-md max-h-[85vh] overflow-auto" onClick={e=>e.stopPropagation()}>
            <div className="modal-header"><h2 className="modal-title">付款</h2></div>
            <div className="modal-body space-y-4">
              {/* 付款信息 */}
              <div className="bg-gray-50 rounded-lg p-4 grid grid-cols-2 gap-3 text-sm">
                <div><span className="text-gray-400">应付总额</span><div className="font-semibold text-lg">¥{payingRow.amount.toLocaleString()}</div></div>
                <div><span className="text-gray-400">已付金额</span><div className="font-semibold text-lg text-green-600">¥{payingRow.paid_amount.toLocaleString()}</div></div>
                <div><span className="text-gray-400">本次付款</span><div className="font-semibold text-lg text-blue-600">¥{(payAmounts[payingBillId]||0).toLocaleString()}</div></div>
                <div><span className="text-gray-400">付款后余额</span><div className={`font-semibold text-lg ${(payingRow.amount - payingRow.paid_amount - (payAmounts[payingBillId]||0)) > 0 ? "text-orange-600" : "text-green-600"}`}>¥{(payingRow.amount - payingRow.paid_amount - (payAmounts[payingBillId]||0)).toLocaleString()}</div></div>
              </div>
              <div className="form-group"><label className="form-label">付款金额</label><input type="number" className="form-input" value={payAmounts[payingBillId]||0} onChange={e=>setPayAmounts(prev=>({...prev,[payingBillId]:+e.target.value}))} /></div>
              <div className="form-group"><label className="form-label">付款方式</label><select className="form-input" value={payMethod} onChange={e=>setPayMethod(e.target.value)}><option>银行转账</option><option>现金</option><option>支票</option><option>PromptPay</option><option>其他</option></select></div>
              <div className="form-group"><label className="form-label">上传付款凭证（非必填）</label><input type="file" accept="image/*" onChange={e=>setVoucherFile(e.target.files?.[0]||null)} className="form-input text-sm" /></div>
            </div>
            <div className="modal-footer">
              <button onClick={()=>setShowPayModal(false)} className="btn-secondary">取消</button>
              <button onClick={handlePay} className="btn-primary">确认付款</button>
            </div>
          </div></div>
      )}
    </>
  );
}

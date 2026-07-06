"use client";
import { useEffect, useState, useRef } from "react";
import DataTable from "@/components/common/DataTable";
import { api, getToken } from "@/lib/api";
import { useI18n } from "@/hooks/useI18n";
import { useToast } from "@/components/ui/Toast";
import { useRouter } from "next/navigation";
import { Upload, AlertTriangle, DollarSign, Clock, CheckCircle, AlertCircle, FileText, Receipt, Download } from "lucide-react";

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
  const [showExport, setShowExport] = useState(false);
  const [exportFilters, setExportFilters] = useState({ supplier_id: 0, start_date: "", end_date: "" });
  const [payAmounts, setPayAmounts] = useState<Record<number, number>>({});
  const [voucherFile, setVoucherFile] = useState<File | null>(null);
  const [payingBillId, setPayingBillId] = useState(0);
  const [payingRow, setPayingRow] = useState<any>(null);
  const [payMethod, setPayMethod] = useState("银行转账");
  const [showPayModal, setShowPayModal] = useState(false);

  async function downloadExport(type: string) {
    const params = new URLSearchParams();
    if (exportFilters.supplier_id) params.set("supplier_id", String(exportFilters.supplier_id));
    if (exportFilters.start_date) params.set("start_date", exportFilters.start_date);
    if (exportFilters.end_date) params.set("end_date", exportFilters.end_date);
    const qs = params.toString() ? "?" + params.toString() : "";
    const url = `${API_URL}/payable/${type}${qs}`;
    
    const res = await fetch(url, { headers: { "Authorization": `Bearer ${getToken()}` } });
    const blob = await res.blob();
    const a = document.createElement("a"); a.href = window.URL.createObjectURL(blob);
    a.download = `${type}.xlsx`; a.click();
  }

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

      {/* 导出筛选 + 操作栏 */}
      <div className="card mb-4 p-4">
        <div className="flex items-end gap-3 flex-wrap">
          <div className="flex-1 min-w-[120px]"><label className="form-label">供应商</label>
            <select className="form-input" value={exportFilters.supplier_id} onChange={e=>setExportFilters({...exportFilters,supplier_id:+e.target.value})}>
              <option value={0}>全部供应商</option>
              {suppliers.map((s:any)=><option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </div>
          <div className="w-[130px]"><label className="form-label">开始日期</label>
            <input type="date" className="form-input" value={exportFilters.start_date} onChange={e=>setExportFilters({...exportFilters,start_date:e.target.value})} />
          </div>
          <div className="w-[130px]"><label className="form-label">结束日期</label>
            <input type="date" className="form-input" value={exportFilters.end_date} onChange={e=>setExportFilters({...exportFilters,end_date:e.target.value})} />
          </div>
          <div className="relative">
            <button onClick={()=>setShowExport(!showExport)} className="btn-secondary flex items-center gap-1 h-[42px]"><Download size={16}/>导出</button>
            {showExport && (
              <div className="absolute right-0 top-full mt-1 bg-white border rounded-lg shadow-lg z-40 w-44 py-1">
                <button onClick={()=>{ downloadExport("batch-export"); setShowExport(false); }}
                  className="w-full text-left px-3 py-2 text-sm hover:bg-gray-50">导出待付账单</button>
                <button onClick={()=>{ downloadExport("supplier-statement"); setShowExport(false); }}
                  className="w-full text-left px-3 py-2 text-sm hover:bg-gray-50">导出供应商对账单</button>
              </div>
            )}
          </div>
          <div className="flex-1" />
          <button onClick={()=>setShowForm(true)} className="btn-primary h-[42px]">新建账单</button>
        </div>
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
          <div className="bg-white rounded-xl w-full max-w-lg max-h-[90vh] overflow-auto shadow-2xl" onClick={e=>e.stopPropagation()}>
            {/* 蓝条标题 */}
            <div className="bg-blue-600 text-white px-6 py-4 rounded-t-xl flex items-center gap-3">
              <FileText size={22} />
              <div><h2 className="text-lg font-semibold">新建应付账单</h2><div className="text-xs text-blue-100 mt-0.5">录入供应商账单信息</div></div>
              <button onClick={()=>setShowForm(false)} className="ml-auto text-blue-200 hover:text-white"><span className="text-xl leading-none">&times;</span></button>
            </div>

            <div className="p-6 space-y-5">
              {/* 第一组：基本信息 */}
              <div>
                <div className="flex items-center gap-2 mb-3 text-sm font-medium text-gray-500 uppercase tracking-wide">基本信息</div>
                <div className="form-grid">
                  <div className="form-group"><label className="form-label">供应商</label><select className="form-input" value={form.supplier_id} onChange={e=>setForm({...form,supplier_id:+e.target.value})}><option value={0}>选择</option>{suppliers.map((s:any)=><option key={s.id} value={s.id}>{s.name}</option>)}</select></div>
                  <div className="form-group"><label className="form-label">账单编号</label><input className="form-input" value={form.bill_number} onChange={e=>setForm({...form,bill_number:e.target.value})} /></div>
                  <div className="form-group"><label className="form-label">账单日期</label><input type="date" className="form-input" value={form.bill_date} onChange={e=>setForm({...form,bill_date:e.target.value})} /></div>
                  <div className="form-group"><label className="form-label">到期日期</label><input type="date" className="form-input" value={form.due_date} onChange={e=>setForm({...form,due_date:e.target.value})} /></div>
                </div>
              </div>

              <div className="border-t" />

              {/* 第二组：金额信息 */}
              <div>
                <div className="flex items-center gap-2 mb-3 text-sm font-medium text-gray-500 uppercase tracking-wide">金额信息</div>
                <div className="form-grid">
                  <div className="form-group"><label className="form-label">金额</label><input type="number" className="form-input" value={form.amount} onChange={e=>setForm({...form,amount:+e.target.value})} /></div>
                  <div className="form-group"><label className="form-label">供应商确认金额</label><input type="number" className="form-input" value={form.confirmed_amount} onChange={e=>setForm({...form,confirmed_amount:+e.target.value})} placeholder="差异自动标记" /></div>
                  <div className="form-group col-span-2"><label className="form-label">付款承诺天数</label><input type="number" className="form-input" value={form.payment_commitment_days} onChange={e=>setForm({...form,payment_commitment_days:+e.target.value})} placeholder="账单收到后承诺多少天内付款" /></div>
                </div>
              </div>

              <div className="border-t" />

              {/* 第三组：补充信息 */}
              <div>
                <div className="flex items-center gap-2 mb-3 text-sm font-medium text-gray-500 uppercase tracking-wide">补充信息</div>
                <div className="space-y-3">
                  <div className="form-group"><label className="form-label">费用明细</label><textarea className="form-input" rows={2} value={form.detail} onChange={e=>setForm({...form,detail:e.target.value})} placeholder="如：纸箱500个x8元=4000元" /></div>
                  <div className="form-group"><label className="form-label">备注</label><input className="form-input" value={form.remark} onChange={e=>setForm({...form,remark:e.target.value})} /></div>
                  <div className="form-group">
                    <label className="form-label">上传账单附件</label>
                    <div className="border-2 border-dashed border-gray-200 rounded-lg p-4 text-center hover:border-blue-400 transition-colors">
                      <Upload size={24} className="mx-auto text-gray-300 mb-2" />
                      <input type="file" accept=".pdf,.jpg,.jpeg,.png,.xlsx,.xls" onChange={e=>setBillFile(e.target.files?.[0]||null)} className="text-sm text-gray-500 file:mr-4 file:py-1 file:px-3 file:rounded file:border-0 file:text-sm file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100" />
                      <div className="text-xs text-gray-400 mt-2">支持 PDF、图片、Excel，上传供应商发来的账单文件</div>
                    </div>
                  </div>
                </div>
              </div>

              <div className="flex items-center gap-2">
                <input type="checkbox" id="fund_linked" checked={form.is_fund_linked === "yes"} onChange={e=>setForm({...form,is_fund_linked: e.target.checked ? "yes" : ""})} />
                <label htmlFor="fund_linked" className="text-sm text-gray-600">备用金垫付</label>
              </div>
            </div>

            <div className="border-t px-6 py-4 bg-gray-50 rounded-b-xl flex justify-end gap-3">
              <button onClick={()=>setShowForm(false)} className="btn-secondary min-w-[80px]">取消</button>
              <button onClick={handleCreate} className="btn-primary min-w-[80px]">保存</button>
            </div>
          </div></div>
      )}

      {/* 付款弹窗 */}
      {showPayModal && payingRow && (
        <div className="modal-overlay" onClick={()=>setShowPayModal(false)}>
          <div className="bg-white rounded-xl w-full max-w-lg max-h-[85vh] overflow-auto shadow-2xl" onClick={e=>e.stopPropagation()}>
            {/* 绿色标题条 */}
            <div className="bg-green-600 text-white px-6 py-4 rounded-t-xl flex items-center gap-3">
              <Receipt size={22} />
              <div className="flex-1">
                <h2 className="text-lg font-semibold">付款</h2>
                <div className="text-xs text-green-100 mt-0.5">
                  账单编号：{payingRow.bill_number} · 供应商：{payingRow.supplier_name}
                </div>
              </div>
              <button onClick={()=>setShowPayModal(false)} className="text-green-200 hover:text-white"><span className="text-xl leading-none">&times;</span></button>
            </div>

            <div className="p-6 space-y-5">
              {/* 四张金额卡片 */}
              <div className="grid grid-cols-4 gap-3">
                <div className="bg-blue-50 rounded-lg p-3 text-center">
                  <div className="text-xs text-blue-500 mb-1">应付总额</div>
                  <div className="font-bold text-lg text-blue-700">¥{payingRow.amount.toLocaleString()}</div>
                </div>
                <div className="bg-green-50 rounded-lg p-3 text-center">
                  <div className="text-xs text-green-500 mb-1">已付金额</div>
                  <div className="font-bold text-lg text-green-700">¥{payingRow.paid_amount.toLocaleString()}</div>
                </div>
                <div className="bg-purple-50 rounded-lg p-3 text-center">
                  <div className="text-xs text-purple-500 mb-1">本次付款</div>
                  <div className="font-bold text-lg text-purple-700">¥{(payAmounts[payingBillId]||0).toLocaleString()}</div>
                </div>
                <div className={`rounded-lg p-3 text-center ${(payingRow.amount - payingRow.paid_amount - (payAmounts[payingBillId]||0)) > 0 ? "bg-orange-50" : "bg-green-100"}`}>
                  <div className={`text-xs mb-1 ${(payingRow.amount - payingRow.paid_amount - (payAmounts[payingBillId]||0)) > 0 ? "text-orange-500" : "text-green-600"}`}>付款后余额</div>
                  <div className={`font-bold text-lg ${(payingRow.amount - payingRow.paid_amount - (payAmounts[payingBillId]||0)) > 0 ? "text-orange-700" : "text-green-700"}`}>¥{(payingRow.amount - payingRow.paid_amount - (payAmounts[payingBillId]||0)).toLocaleString()}</div>
                </div>
              </div>

              <div className="border-t" />

              {/* 付款表单 */}
              <div className="form-grid">
                <div className="form-group"><label className="form-label">付款金额</label><input type="number" className="form-input text-lg font-semibold" value={payAmounts[payingBillId]||0} onChange={e=>setPayAmounts(prev=>({...prev,[payingBillId]:+e.target.value}))} /></div>
                <div className="form-group"><label className="form-label">付款方式</label><select className="form-input" value={payMethod} onChange={e=>setPayMethod(e.target.value)}><option>银行转账</option><option>现金</option><option>支票</option><option>PromptPay</option><option>其他</option></select></div>
              </div>
              <div className="form-group">
                <label className="form-label">上传付款凭证（非必填）</label>
                <div className="border-2 border-dashed border-gray-200 rounded-lg p-4 text-center hover:border-green-400 transition-colors">
                  <Upload size={24} className="mx-auto text-gray-300 mb-2" />
                  <input type="file" accept="image/*" onChange={e=>setVoucherFile(e.target.files?.[0]||null)} className="text-sm text-gray-500 file:mr-4 file:py-1 file:px-3 file:rounded file:border-0 file:text-sm file:bg-green-50 file:text-green-700 hover:file:bg-green-100" />
                  <div className="text-xs text-gray-400 mt-2">可选，上传转账截图或回单</div>
                </div>
              </div>
            </div>

            <div className="border-t px-6 py-4 bg-gray-50 rounded-b-xl flex justify-end gap-3">
              <button onClick={()=>setShowPayModal(false)} className="btn-secondary min-w-[80px]">取消</button>
              <button onClick={handlePay} className="btn-primary min-w-[80px]">确认付款</button>
            </div>
          </div></div>
      )}
    </>
  );
}

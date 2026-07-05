"use client";
import { useEffect, useState } from "react";
import DataTable from "@/components/common/DataTable";
import { api, getToken } from "@/lib/api";
import { useI18n } from "@/hooks/useI18n";
import { useToast } from "@/components/ui/Toast";
import { useRouter } from "next/navigation";

export default function PaymentPlansPage() {
  const { t } = useI18n();
  const { toast } = useToast(); const router = useRouter();
  const [plans, setPlans] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [bills, setBills] = useState<any[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ plan_name: "", planned_date: "", bill_ids: [] as number[], remark: "" });
  const [selectedBills, setSelectedBills] = useState<number[]>([]);

  useEffect(() => { if (!getToken()) router.push("/login"); load(); loadBills(); }, []);

  async function load() {
    setLoading(true);
    try {
      const r = await api.get<any>("/payable/plans"); setPlans(r.data);
    } catch (err) { console.error("加载失败:", err); }
    setLoading(false);
  }
  async function loadBills() { const r = await api.get<any>("/payable?page_size=100&status=pending"); setBills(r.data); }

  function toggleBill(id: number) {
    setSelectedBills(prev => prev.includes(id) ? prev.filter(x=>x!==id) : [...prev, id]);
  }

  async function handleCreate() {
    try {
      await api.post("/payable/plans", { ...form, bill_ids: selectedBills });
      toast("success", "创建成功");
      setShowForm(false); load();
    } catch (err: any) { toast("error", "创建失败"); }
  }

  return (
    <>
      <div className="flex justify-between mb-4"><h1 className="text-xl font-bold">付款计划管理</h1>
        <button onClick={()=>setShowForm(true)} className="bg-primary text-white px-4 py-2 rounded text-sm">新建计划</button>
      </div>
      {loading ? <div className="text-center py-8 text-gray-400">加载中...</div> : <DataTable columns={[
        { key: "plan_name", label: "计划名称" },
        { key: "planned_date", label: "计划日期", render: (v:any)=>v?.slice(0,10) },
        { key: "total_amount", label: "金额" },
        { key: "status", label: "状态" },
      ]} data={plans} total={plans.length} page={1} pageSize={100} onPageChange={()=>{}} />}
      {showForm && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center"><div className="bg-white rounded-xl p-6 w-[600px] max-h-[80vh] overflow-auto">
          <h2 className="font-semibold mb-4">新建付款计划</h2>
          <div className="space-y-3">
            <div><input className="border rounded px-3 py-2 w-full text-sm" placeholder="计划名称" value={form.plan_name} onChange={e=>setForm({...form,plan_name:e.target.value})} /></div>
            <div><input type="date" className="border rounded px-3 py-2 w-full text-sm" value={form.planned_date} onChange={e=>setForm({...form,planned_date:e.target.value})} /></div>
            <div className="text-sm font-medium">选择待付账单:</div>
            {bills.map((b:any) => (
              <div key={b.id} className="flex items-center gap-3 py-1">
                <input type="checkbox" checked={selectedBills.includes(b.id)} onChange={()=>toggleBill(b.id)} />
                <span className="text-sm">{b.supplier_name} - {b.bill_number}</span>
                <span className="text-xs text-gray-500">¥{b.amount} ({b.status})</span>
              </div>
            ))}
            <div className="text-sm text-gray-500">已选: {selectedBills.length} 条, 合计 ¥{bills.filter(b=>selectedBills.includes(b.id)).reduce((s,b)=>s+b.amount,0).toLocaleString()}</div>
          </div>
          <div className="flex justify-end gap-3 mt-6"><button onClick={()=>setShowForm(false)} className="px-4 py-2 border rounded">取消</button><button onClick={handleCreate} className="px-4 py-2 bg-primary text-white rounded">保存</button></div>
        </div></div>
      )}
    </>
  );
}

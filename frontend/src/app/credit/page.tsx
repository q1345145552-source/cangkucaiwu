"use client";
import { useEffect, useState } from "react";
import DashboardLayout from "@/components/layout/DashboardLayout";
import DataTable from "@/components/common/DataTable";
import { api, getToken } from "@/lib/api";
import { useI18n } from "@/hooks/useI18n";
import { useRouter } from "next/navigation";

export default function CreditPage() {
  const { t } = useI18n(); const router = useRouter();
  const [data, setData] = useState<any[]>([]); const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1); const [db, setDb] = useState<any>({});
  const [alerts, setAlerts] = useState<any[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [customers, setCustomers] = useState<any[]>([]);
  const [form, setForm] = useState({ customer_id: 0, credit_limit: 0, repayment_day: 15 });
  const [detail, setDetail] = useState<any>(null);

  useEffect(() => { if (!getToken()) router.push("/login"); load(); loadDashboard(); loadCustomers(); loadAlerts(); }, [page]);

  async function load() {
    const r = await api.get<any>(`/credit?page=${page}&page_size=20`);
    setData(r.data); setTotal(r.total);
  }
  async function loadDashboard() { try { setDb(await api.get<any>("/credit/dashboard")); } catch {} }
  async function loadCustomers() { try { const r = await api.get<any>("/customers?page_size=100"); setCustomers(r.data); } catch {} }
  async function loadAlerts() { try { const r = await api.get<any>("/credit/alerts"); setAlerts(r.data); } catch {} }

  async function handleCreate() {
    await api.post("/credit", form);
    setShowForm(false); load(); loadDashboard();
  }
  async function viewDetail(id: number) {
    setDetail(await api.get<any>(`/credit/${id}/detail`));
  }

  return (
    <DashboardLayout>
      <div className="flex justify-between mb-4"><h1 className="text-xl font-bold">{t("credit")}</h1>
        <button onClick={()=>setShowForm(true)} className="bg-primary text-white px-4 py-2 rounded-lg text-sm">新建账期客户</button>
      </div>

      {/* Dashboard cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
        <div className="bg-white rounded-xl p-4 shadow-sm"><div className="text-2xl font-bold text-blue-600">¥{(db.total_debt||0).toLocaleString()}</div><div className="text-xs text-gray-500">总欠款</div></div>
        <div className="bg-white rounded-xl p-4 shadow-sm"><div className="text-2xl font-bold text-gray-700">¥{(db.total_credit_limit||0).toLocaleString()}</div><div className="text-xs text-gray-500">总额度</div></div>
        <div className="bg-white rounded-xl p-4 shadow-sm"><div className="text-2xl font-bold">{db.utilization_rate||0}%</div><div className="text-xs text-gray-500">利用率</div></div>
        <div className="bg-red-50 rounded-xl p-4"><div className="text-2xl font-bold text-red-600">{db.overdue_count||0}</div><div className="text-xs text-gray-500">逾期客户</div></div>
      </div>

      {/* Alerts */}
      {alerts.length > 0 && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4 mb-4">
          <h3 className="font-semibold text-red-700 mb-2">⚠️ 逾期预警</h3>
          {alerts.map((a: any) => (
            <div key={a.id} className="text-sm text-red-600">{a.customer_name} - 逾期{a.overdue_days}天 - ¥{a.current_debt?.toLocaleString()}</div>
          ))}
        </div>
      )}

      <DataTable onRowClick={(row:any)=>viewDetail(row.id)} columns={[
        { key: "customer_name", label: "客户" }, { key: "credit_limit", label: "额度" },
        { key: "current_debt", label: "当前欠款" }, { key: "overdue_days", label: "逾期天数" },
        { key: "repayment_day", label: "还款日" }, { key: "status", label: "状态" },
      ]} data={data} total={total} page={page} pageSize={20} onPageChange={setPage} />

      {detail && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center"><div className="bg-white rounded-xl p-6 w-[500px] max-h-[80vh] overflow-auto">
          <h2 className="font-semibold mb-2">{detail.customer_name}</h2>
          <div className="text-sm text-gray-500 mb-4">额度: ¥{detail.credit_limit?.toLocaleString()} | 欠款: ¥{(detail.current_debt||0).toLocaleString()} | 逾期: {detail.overdue_days||0}天</div>
          <h3 className="text-sm font-semibold mb-2">还款记录</h3>
          <table className="w-full text-sm"><thead><tr className="border-b"><th className="text-left py-1">日期</th><th>金额</th><th>备注</th></tr></thead>
            <tbody>{detail.repayments?.map((r:any)=>(<tr key={r.id} className="border-b"><td className="py-1">{r.repayment_date?.slice(0,10)}</td><td>¥{r.amount}</td><td>{r.remark}</td></tr>))}</tbody></table>
          <button onClick={()=>setDetail(null)} className="mt-4 px-4 py-2 border rounded text-sm">关闭</button>
        </div></div>
      )}

      {showForm && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center"><div className="bg-white rounded-xl p-6 w-96">
          <h2 className="font-semibold mb-4">新建账期客户</h2>
          <div className="space-y-3">
            <div><label className="text-sm">客户</label><select className="border rounded px-3 py-2 w-full" value={form.customer_id} onChange={e=>setForm({...form,customer_id:+e.target.value})}><option>选择</option>{customers.map((c:any)=><option key={c.id} value={c.id}>{c.company_name}</option>)}</select></div>
            <div><label className="text-sm">信用额度</label><input type="number" className="border rounded px-3 py-2 w-full" value={form.credit_limit} onChange={e=>setForm({...form,credit_limit:+e.target.value})} /></div>
            <div><label className="text-sm">还款日(每月)</label><input type="number" min={1} max={31} className="border rounded px-3 py-2 w-full" value={form.repayment_day} onChange={e=>setForm({...form,repayment_day:+e.target.value})} /></div>
          </div>
          <div className="flex justify-end gap-3 mt-6"><button onClick={()=>setShowForm(false)} className="px-4 py-2 border rounded text-sm">取消</button><button onClick={handleCreate} className="px-4 py-2 bg-primary text-white rounded text-sm">保存</button></div>
        </div></div>
      )}
    </DashboardLayout>
  );
}

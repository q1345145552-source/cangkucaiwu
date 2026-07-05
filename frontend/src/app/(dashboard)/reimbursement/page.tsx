"use client";
import { useEffect, useState } from "react";
import DataTable from "@/components/common/DataTable";
import { api, getToken } from "@/lib/api";
import { useI18n } from "@/hooks/useI18n";
import { useRouter } from "next/navigation";

export default function ReimbursementPage() {
  const { t } = useI18n(); const router = useRouter();
  const [data, setData] = useState<any[]>([]); const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1); const [showForm, setShowForm] = useState(false);
  const [items, setItems] = useState<any[]>([]);
  const [form, setForm] = useState({ submit_date: "", currency: "THB" });
  const [detail, setDetail] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => { if (!getToken()) router.push("/login"); load(); }, [page]);

  async function load() {
    setLoading(true);
    try {
      const r = await api.get<any>(`/reimbursement?page=${page}&page_size=20`);
      setData(r.data); setTotal(r.total);
    } catch (err) { console.error("加载失败:", err); }
    setLoading(false);
  }

  function addLine() { setItems([...items, { category: "", amount: 0, description: "" }]); }
  function updateLine(i: number, f: string, v: any) {
    const n = [...items]; (n[i] as any)[f] = v; setItems(n);
  }

  async function handleCreate() {
    await api.post("/reimbursement", { items, ...form });
    setShowForm(false); setItems([]); load();
  }

  async function viewDetail(id: number) {
    const r = await api.get<any>(`/reimbursement/${id}`);
    setDetail(r);
  }

  const statusColors: any = { pending: "text-yellow-600", approved: "text-green-600", rejected: "text-red-600", paid: "text-blue-600", partially_approved: "text-orange-600" };

  return (
    <>
      <div className="flex justify-between mb-4"><h1 className="text-xl font-bold">{t("reimbursement")}</h1>
        <button onClick={() => { setItems([{category:"",amount:0,description:""}]); setShowForm(true); }} className="bg-primary text-white px-4 py-2 rounded-lg text-sm">新建报销</button>
      </div>
      {loading ? <div className="text-center py-8 text-gray-400">加载中...</div> : <DataTable onRowClick={(row:any) => viewDetail(row.id)} columns={[
        { key: "employee_name", label: "报销人" }, { key: "submit_date", label: "提交日期", render: (v:any)=>v?.slice(0,10) },
        { key: "total_amount", label: "金额" }, { key: "currency", label: "币种" },
        { key: "status", label: "状态", render: (v:any) => <span className={statusColors[v]||""}>{v}</span> },
      ]} data={data} total={total} page={page} pageSize={20} onPageChange={setPage} />}

      {detail && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center"><div className="bg-white rounded-xl p-6 w-[500px] max-h-[80vh] overflow-auto">
          <h2 className="font-semibold mb-4">报销详情</h2>
          <div className="text-sm text-gray-500 mb-2">状态: <span className={statusColors[detail.status]}>{detail.status}</span> | 总额: ¥{detail.total_amount}</div>
          <table className="w-full text-sm"><thead><tr className="border-b"><th className="text-left py-1">类别</th><th>金额</th><th>说明</th><th>审核</th></tr></thead>
            <tbody>{detail.items?.map((i: any) => (
              <tr key={i.id} className="border-b"><td className="py-1">{i.category}</td><td>¥{i.amount}</td><td>{i.description}</td><td>{i.review_status}</td></tr>
            ))}</tbody></table>
          <button onClick={()=>setDetail(null)} className="mt-4 px-4 py-2 border rounded text-sm">关闭</button>
        </div></div>
      )}

      {showForm && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center"><div className="bg-white rounded-xl p-6 w-[550px] max-h-[85vh] overflow-auto">
          <h2 className="font-semibold mb-4">新建报销单</h2>
          <div className="flex gap-3 mb-4">
            <input type="date" className="border rounded px-3 py-2" value={form.submit_date} onChange={e=>setForm({...form,submit_date:e.target.value})} />
            <select className="border rounded px-3 py-2" value={form.currency} onChange={e=>setForm({...form,currency:e.target.value})}>
              <option value="THB">THB</option><option value="CNY">CNY</option></select>
          </div>
          {items.map((item, i) => (
            <div key={i} className="flex gap-2 mb-2">
              <input className="border rounded px-2 py-1 w-28 text-sm" placeholder="类别" value={item.category} onChange={e=>updateLine(i,"category",e.target.value)} />
              <input type="number" className="border rounded px-2 py-1 w-24 text-sm" placeholder="金额" value={item.amount} onChange={e=>updateLine(i,"amount",+e.target.value)} />
              <input className="border rounded px-2 py-1 flex-1 text-sm" placeholder="说明" value={item.description} onChange={e=>updateLine(i,"description",e.target.value)} />
            </div>
          ))}
          <button onClick={addLine} className="text-sm text-primary mb-4">+ 添加明细行</button>
          <div className="flex justify-end gap-3">
            <button onClick={()=>setShowForm(false)} className="px-4 py-2 border rounded text-sm">取消</button>
            <button onClick={handleCreate} className="px-4 py-2 bg-primary text-white rounded text-sm">提交</button>
          </div>
        </div></div>
      )}
    </>
  );
}

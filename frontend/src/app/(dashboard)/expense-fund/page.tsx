"use client";
import { useEffect, useState } from "react";
import DataTable from "@/components/common/DataTable";
import { api, getToken } from "@/lib/api";
import { useI18n } from "@/hooks/useI18n";
import { useRouter } from "next/navigation";

export default function ExpenseFundPage() {
  const { t } = useI18n(); const router = useRouter();
  const [data, setData] = useState<any[]>([]); const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ receive_date: "", amount: 0, purpose: "" });
  const [selectedFund, setSelectedFund] = useState<any>(null);
  const [items, setItems] = useState<any[]>([]);
  const [itemForm, setItemForm] = useState({ expense_date: "", category: "", amount: 0, description: "" });
  const [balance, setBalance] = useState<any[]>([]);

  useEffect(() => { if (!getToken()) router.push("/login"); load(); loadBalance(); }, [page]);

  async function load() {
    const r = await api.get<any>(`/expense-fund?page=${page}&page_size=20`);
    setData(r.data); setTotal(r.total);
  }
  async function loadBalance() {
    try { const r = await api.get<any>("/expense-fund/balance"); setBalance(r.data); } catch {}
  }
  async function handleCreate() {
    await api.post("/expense-fund", form);
    setShowForm(false); setForm({ receive_date: "", amount: 0, purpose: "" }); load(); loadBalance();
  }
  async function selectFund(fund: any) {
    setSelectedFund(fund);
    const r = await api.get<any>(`/expense-fund/${fund.id}/items`);
    setItems(r.data);
  }
  async function addItem() {
    await api.post(`/expense-fund/${selectedFund.id}/items`, itemForm);
    setItemForm({ expense_date: "", category: "", amount: 0, description: "" });
    selectFund(selectedFund);
    loadBalance();
  }

  return (
    <>
      <div className="flex justify-between mb-4"><h1 className="text-xl font-bold">{t("expense_fund")}</h1>
        <button onClick={() => setShowForm(true)} className="bg-primary text-white px-4 py-2 rounded-lg text-sm">新建领用</button>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
        {balance.map((b: any) => (
          <div key={b.fund_id} className="bg-white rounded-xl p-4 shadow-sm">
            <div className="text-sm text-gray-500">{b.employee_name}</div>
            <div className="text-2xl font-bold text-blue-600">¥{b.remaining_balance?.toLocaleString()}</div>
            <div className="text-xs text-gray-400">总额: ¥{b.total_amount?.toLocaleString()}</div>
          </div>
        ))}
      </div>
      <DataTable columns={[
        { key: "employee_name", label: "领用人" }, { key: "receive_date", label: "领用日期", render: (v:any)=>v?.slice(0,10) },
        { key: "amount", label: "金额" }, { key: "purpose", label: "用途" },
        { key: "remaining_balance", label: "余额" }, { key: "status", label: "状态" },
      ]} data={data} total={total} page={page} pageSize={20} onPageChange={setPage}
        onRowClick={selectFund}
      />
      {selectedFund && (
        <div className="mt-6 bg-white rounded-xl p-4 shadow-sm">
          <h3 className="font-semibold mb-3">开销明细</h3>
          <table className="w-full text-sm"><thead><tr className="border-b"><th className="text-left py-2">日期</th><th>类别</th><th>金额</th><th>说明</th><th>审核</th></tr></thead>
            <tbody>{items.map((i: any) => (
              <tr key={i.id} className="border-b"><td className="py-2">{i.expense_date?.slice(0,10)}</td><td>{i.category}</td><td>¥{i.amount}</td><td>{i.description}</td><td>{i.review_status}</td></tr>
            ))}</tbody></table>
          <div className="flex gap-2 mt-3">
            <input type="date" className="border rounded px-2 py-1 text-sm" value={itemForm.expense_date} onChange={e=>setItemForm({...itemForm,expense_date:e.target.value})} />
            <input className="border rounded px-2 py-1 text-sm w-32" placeholder="类别" value={itemForm.category} onChange={e=>setItemForm({...itemForm,category:e.target.value})} />
            <input type="number" className="border rounded px-2 py-1 text-sm w-24" placeholder="金额" value={itemForm.amount} onChange={e=>setItemForm({...itemForm,amount:+e.target.value})} />
            <input className="border rounded px-2 py-1 text-sm flex-1" placeholder="说明" value={itemForm.description} onChange={e=>setItemForm({...itemForm,description:e.target.value})} />
            <button onClick={addItem} className="bg-primary text-white px-3 py-1 rounded text-sm">添加</button>
          </div>
        </div>
      )}
      {showForm && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center"><div className="bg-white rounded-xl p-6 w-96">
          <h2 className="font-semibold mb-4">备用金领用</h2>
          <div className="space-y-3">
            <div><label className="text-sm">领用日期</label><input type="date" className="border rounded px-3 py-2 w-full" value={form.receive_date} onChange={e=>setForm({...form,receive_date:e.target.value})} /></div>
            <div><label className="text-sm">金额</label><input type="number" className="border rounded px-3 py-2 w-full" value={form.amount} onChange={e=>setForm({...form,amount:+e.target.value})} /></div>
            <div><label className="text-sm">用途</label><input className="border rounded px-3 py-2 w-full" value={form.purpose} onChange={e=>setForm({...form,purpose:e.target.value})} /></div>
          </div>
          <div className="flex justify-end gap-3 mt-6">
            <button onClick={()=>setShowForm(false)} className="px-4 py-2 border rounded">取消</button>
            <button onClick={handleCreate} className="px-4 py-2 bg-primary text-white rounded">保存</button>
          </div>
        </div></div>
      )}
    </>
  );
}

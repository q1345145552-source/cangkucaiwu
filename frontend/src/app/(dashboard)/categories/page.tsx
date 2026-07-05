"use client";
import { useEffect, useState } from "react";
import { api, getToken } from "@/lib/api";
import { useI18n } from "@/hooks/useI18n";
import { useRouter } from "next/navigation";

export default function CategoriesPage() {
  const { t } = useI18n(); const router = useRouter();
  const [cats, setCats] = useState<any[]>([]);
  const [tab, setTab] = useState("income");
  const [name, setName] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => { if (!getToken()) router.push("/login"); load(); }, [tab]);

  async function load() {
    setLoading(true);
    try {
      const r = await api.get<any>(`/income-expense/categories?type=${tab}`); setCats(r.data);
    } catch (err) { console.error("加载失败:", err); }
    setLoading(false);
  }
  async function add() { await api.post("/income-expense/categories", { type: tab, name }); setName(""); load(); }

  return (
    <>
      <h1 className="text-xl font-bold mb-4">收支类别管理</h1>
      <div className="flex gap-2 mb-4">
        <button onClick={()=>setTab("income")} className={`px-4 py-1.5 rounded text-sm ${tab==="income"?"bg-green-500 text-white":"border"}`}>收入类别</button>
        <button onClick={()=>setTab("expense")} className={`px-4 py-1.5 rounded text-sm ${tab==="expense"?"bg-red-500 text-white":"border"}`}>支出类别</button>
      </div>
      <div className="flex gap-2 mb-4">
        <input className="border rounded px-3 py-2 text-sm w-64" placeholder="新类别名称" value={name} onChange={e=>setName(e.target.value)} />
        <button onClick={add} className="bg-primary text-white px-4 py-2 rounded text-sm">添加</button>
      </div>
      {loading ? <div className="text-center py-8 text-gray-400">加载中...</div> : <div className="bg-white rounded-xl shadow-sm p-4">
        {cats.map((c:any) => <div key={c.id} className="flex justify-between py-2 border-b text-sm"><span>{c.name}</span><span className={`px-2 py-0.5 rounded text-xs ${c.status==="active"?"bg-green-100 text-green-700":"bg-gray-100"}`}>{c.status}</span></div>)}
      </div>}
    </>
  );
}

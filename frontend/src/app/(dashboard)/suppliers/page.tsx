"use client";
import { useEffect, useState } from "react";
import DataTable from "@/components/common/DataTable";
import { api, getToken } from "@/lib/api";
import { useI18n } from "@/hooks/useI18n";
import { useAuth } from "@/hooks/useAuth";
import { useRouter } from "next/navigation";
import { Sparkles } from "lucide-react";

export default function SuppliersPage() {
  const { t } = useI18n(); const { user } = useAuth(); const router = useRouter();
  const [data, setData] = useState<any[]>([]); const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ name: "", contact_person: "", contact_info: "", address: "", payment_terms: "" });
  const [aiResult, setAiResult] = useState("");

  useEffect(() => { if (!getToken()) router.push("/login"); load(); }, [page]);

  async function load() { const r = await api.get<any>(`/suppliers?page=${page}&page_size=20`); setData(r.data); setTotal(r.total); }
  async function handleCreate() { await api.post("/suppliers", form); setShowForm(false); load(); }

  async function aiEvaluate(sid: number) {
    setAiResult("评估中...");
    try { const r = await api.get<any>(`/suppliers/${sid}/ai-evaluation`); setAiResult(r.result || r.error || "评估完成"); }
    catch(e: any) { setAiResult(e.message); }
  }

  return (
    <>
      <div className="flex justify-between mb-4">
        <h1 className="text-xl font-bold">{t("suppliers")}</h1>
        {(user?.role === "super_admin" || user?.role === "warehouse_admin") && (
          <button onClick={()=>setShowForm(true)} className="bg-primary text-white px-4 py-2 rounded-lg text-sm">新建供应商</button>
        )}
      </div>
      <DataTable columns={[
        { key: "name", label: "名称" }, { key: "contact_person", label: "联系人" },
        { key: "contact_info", label: "联系方式" }, { key: "payment_terms", label: "付款条件" },
        { key: "id", label: "AI评估", render: (_:any, row:any) => (
          <button onClick={()=>aiEvaluate(row.id)} className="text-primary flex items-center gap-1 text-xs"><Sparkles size={12}/>评估</button>
        )},
      ]} data={data} total={total} page={page} pageSize={20} onPageChange={setPage} />
      {aiResult && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center"><div className="bg-white rounded-xl p-6 w-[500px] max-h-[70vh] overflow-auto">
          <h2 className="font-semibold mb-3">AI 供应商评估</h2>
          <div className="text-sm whitespace-pre-wrap text-gray-700">{aiResult}</div>
          <button onClick={()=>setAiResult("")} className="mt-4 px-4 py-2 border rounded text-sm">关闭</button>
        </div></div>
      )}
      {showForm && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center"><div className="bg-white rounded-xl p-6 w-96">
          <h2 className="font-semibold mb-4">新建供应商</h2>
          <div className="space-y-3">
            <div><label className="text-sm">名称</label><input className="border rounded px-3 py-2 w-full" value={form.name} onChange={e=>setForm({...form,name:e.target.value})} /></div>
            <div><label className="text-sm">联系人</label><input className="border rounded px-3 py-2 w-full" value={form.contact_person} onChange={e=>setForm({...form,contact_person:e.target.value})} /></div>
            <div><label className="text-sm">联系方式</label><input className="border rounded px-3 py-2 w-full" value={form.contact_info} onChange={e=>setForm({...form,contact_info:e.target.value})} /></div>
            <div><label className="text-sm">地址</label><input className="border rounded px-3 py-2 w-full" value={form.address} onChange={e=>setForm({...form,address:e.target.value})} /></div>
          </div>
          <div className="flex justify-end gap-3 mt-6"><button onClick={()=>setShowForm(false)} className="px-4 py-2 border rounded">取消</button><button onClick={handleCreate} className="px-4 py-2 bg-primary text-white rounded">保存</button></div>
        </div></div>
      )}
    </>
  );
}

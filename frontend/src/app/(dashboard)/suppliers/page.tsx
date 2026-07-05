"use client";
import { useEffect, useState } from "react";
import DataTable from "@/components/common/DataTable";
import { api, getToken } from "@/lib/api";
import { useI18n } from "@/hooks/useI18n";
import { useToast } from "@/components/ui/Toast";
import { useAuth } from "@/hooks/useAuth";
import { useRouter } from "next/navigation";
import { Sparkles, Eye, TrendingUp } from "lucide-react";

export default function SuppliersPage() {
  const { t } = useI18n();
  const { toast } = useToast(); const { user } = useAuth(); const router = useRouter();
  const [data, setData] = useState<any[]>([]); const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ name: "", contact_person: "", contact_info: "", address: "", payment_terms: "", cooperation_content: "", settlement_cycle: "" });
  const [aiResult, setAiResult] = useState("");
  const [procurement, setProcurement] = useState<any[]>([]);
  const [showProcurement, setShowProcurement] = useState(false);
  const [detail, setDetail] = useState<any>(null);

  useEffect(() => { if (!getToken()) router.push("/login"); load(); }, [page]);

  async function load() { setLoading(true); try { const r = await api.get<any>(`/suppliers?page=${page}&page_size=20`); setData(r.data); setTotal(r.total); } catch (err) { console.error('加载失败:', err); } setLoading(false); }
  async function handleCreate() { try { await api.post("/suppliers", form); toast("success", "创建成功"); setShowForm(false); load(); } catch (err: any) { toast("error", "创建失败"); } }

  async function aiEvaluate(sid: number) {
    setAiResult("评估中...");
    try { const r = await api.get<any>(`/suppliers/${sid}/ai-evaluation`); setAiResult(r.result || r.error || "评估完成"); }
    catch(e: any) { setAiResult(e.message); }
  }

  async function viewDetail(sid: number) {
    try { const r = await api.get<any>(`/suppliers/${sid}`); setDetail(r); } catch {}
  }

  return (
    <>
      <div className="flex justify-between mb-4">
        <h1 className="text-xl font-bold">{t("suppliers")}</h1>
        <div className="flex gap-2">
          {(user?.role === "super_admin" || user?.role === "warehouse_admin") && (
            <>
              <button onClick={async () => { try { const r = await api.get<any>("/suppliers/procurement-summary"); setProcurement(r.data); setShowProcurement(true); } catch {} }} 
                className="border px-4 py-2 rounded-lg text-sm flex items-center gap-1"><TrendingUp size={16}/>采购汇总</button>
              <button onClick={()=>setShowForm(true)} className="bg-primary text-white px-4 py-2 rounded-lg text-sm">新建供应商</button>
            </>
          )}
        </div>
      </div>
      {loading ? <div className="text-center py-8 text-gray-400">加载中...</div> : <DataTable columns={[
        { key: "name", label: "名称" }, { key: "contact_person", label: "联系人" },
        { key: "contact_info", label: "联系方式" }, { key: "settlement_cycle", label: "结算周期", render: (v:any)=>v||"-" },
        { key: "id", label: "操作", render: (_:any, row:any) => (
          <div className="flex gap-2">
            <button onClick={()=>aiEvaluate(row.id)} className="text-primary flex items-center gap-1 text-xs"><Sparkles size={12}/>评估</button>
            <button onClick={()=>viewDetail(row.id)} className="text-blue-500 flex items-center gap-1 text-xs"><Eye size={12}/>详情</button>
          </div>
        )},
      ]} data={data} total={total} page={page} pageSize={20} onPageChange={setPage} />}
      
      {aiResult && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center"><div className="bg-white rounded-xl p-6 w-[600px] max-h-[70vh] overflow-auto">
          <h2 className="font-semibold mb-3">{aiResult.startsWith("[") ? "采购汇总" : "AI 供应商评估"}</h2>
          <div className="text-sm whitespace-pre-wrap text-gray-700">{aiResult}</div>
          <button onClick={()=>setAiResult("")} className="mt-4 px-4 py-2 border rounded text-sm">关闭</button>
        </div></div>
      )}

      {detail && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center"><div className="bg-white rounded-xl p-6 w-[500px] max-h-[80vh] overflow-auto">
          <h2 className="font-semibold mb-4">{detail.name} 详细信息</h2>
          <div className="space-y-2 text-sm">
            <div><span className="text-gray-500">联系人:</span> {detail.contact_person||"-"}</div>
            <div><span className="text-gray-500">联系方式:</span> {detail.contact_info||"-"}</div>
            <div><span className="text-gray-500">地址:</span> {detail.address||"-"}</div>
            <div><span className="text-gray-500">付款条件:</span> {detail.payment_terms||"-"}</div>
            <div><span className="text-gray-500">合作内容:</span> {detail.cooperation_content||"-"}</div>
            <div><span className="text-gray-500">结算周期:</span> {detail.settlement_cycle||"-"}</div>
            {detail.history_notes && (
              <div><span className="text-gray-500">历史记录:</span> <pre className="text-xs bg-gray-50 p-2 rounded mt-1">{JSON.stringify(detail.history_notes, null, 2)}</pre></div>
            )}
            {detail.ai_evaluation && (
              <div><span className="text-gray-500">AI评估:</span> <div className="text-xs bg-gray-50 p-2 rounded mt-1 whitespace-pre-wrap">{typeof detail.ai_evaluation === 'object' ? JSON.stringify(detail.ai_evaluation, null, 2) : detail.ai_evaluation}</div></div>
            )}
          </div>
          <button onClick={()=>setDetail(null)} className="mt-4 px-4 py-2 border rounded text-sm">关闭</button>
        </div></div>
      )}

      {showProcurement && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center"><div className="bg-white rounded-xl p-6 w-[600px] max-h-[70vh] overflow-auto">
          <h2 className="font-semibold mb-3">多仓采购汇总</h2>
          {procurement.length === 0 ? <div className="text-gray-400 text-sm py-4">暂无数据</div> : procurement.map((r: any) => (
            <div key={r.supplier_id} className="mb-4 p-3 bg-gray-50 rounded">
              <div className="font-medium">{r.supplier_name}</div>
              <div className="text-xs text-gray-500">总采购额: {(r.grand_total || 0).toLocaleString()}</div>
              {r.warehouses.map((w: any) => (
                <div key={w.warehouse_id} className="ml-4 text-xs text-gray-600">- {w.warehouse_name}: {(w.total_amount || 0).toLocaleString()}</div>
              ))}
            </div>
          ))}
          <button onClick={() => setShowProcurement(false)} className="mt-4 px-4 py-2 border rounded text-sm">关闭</button>
        </div></div>
      )}
      {showForm && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center"><div className="bg-white rounded-xl p-6 w-[500px] max-h-[85vh] overflow-auto">
          <h2 className="font-semibold mb-4">新建供应商</h2>
          <div className="grid grid-cols-2 gap-3">
            <div><label className="text-sm">名称</label><input className="border rounded px-3 py-2 w-full" value={form.name} onChange={e=>setForm({...form,name:e.target.value})} /></div>
            <div><label className="text-sm">联系人</label><input className="border rounded px-3 py-2 w-full" value={form.contact_person} onChange={e=>setForm({...form,contact_person:e.target.value})} /></div>
            <div><label className="text-sm">联系方式</label><input className="border rounded px-3 py-2 w-full" value={form.contact_info} onChange={e=>setForm({...form,contact_info:e.target.value})} /></div>
            <div><label className="text-sm">地址</label><input className="border rounded px-3 py-2 w-full" value={form.address} onChange={e=>setForm({...form,address:e.target.value})} /></div>
            <div><label className="text-sm">付款条件</label><input className="border rounded px-3 py-2 w-full" value={form.payment_terms} onChange={e=>setForm({...form,payment_terms:e.target.value})} /></div>
            <div><label className="text-sm">结算周期</label><input className="border rounded px-3 py-2 w-full" value={form.settlement_cycle} onChange={e=>setForm({...form,settlement_cycle:e.target.value})} placeholder="如: 月结30天" /></div>
          </div>
          <div className="mt-3"><label className="text-sm">合作内容</label><textarea className="border rounded px-3 py-2 w-full" rows={2} value={form.cooperation_content} onChange={e=>setForm({...form,cooperation_content:e.target.value})} /></div>
          <div className="flex justify-end gap-3 mt-6"><button onClick={()=>setShowForm(false)} className="px-4 py-2 border rounded">取消</button><button onClick={handleCreate} className="px-4 py-2 bg-primary text-white rounded">保存</button></div>
        </div></div>
      )}
    </>
  );
}

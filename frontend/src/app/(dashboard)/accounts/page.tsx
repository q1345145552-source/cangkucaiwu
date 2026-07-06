"use client";
import { useEffect, useState } from "react";
import DataTable from "@/components/common/DataTable";
import { api, getToken } from "@/lib/api";
import { useI18n } from "@/hooks/useI18n";
import { useToast } from "@/components/ui/Toast";
import { useAuth } from "@/hooks/useAuth";
import { useRouter } from "next/navigation";

export default function AccountsPage() {
  const { t } = useI18n();
  const { toast } = useToast(); const { user } = useAuth(); const router = useRouter();
  const [data, setData] = useState<any[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState({ account_name: "", account_type: "bank", account_number: "", opening_balance: 0 });

  useEffect(() => { if (!getToken()) router.push("/login"); load(); }, []);

  async function load() {
    setLoading(true);
    try {
      const r = await api.get<any>("/accounts"); setData(r.data);
    } catch {}
    setLoading(false);
  }

  async function handleCreate() { try { await api.post("/accounts", form); toast("success", "创建成功"); setShowForm(false); load(); } catch (err: any) { toast("error", "创建失败"); } }

  return (
    <>
      <div className="page-header">
        <h1 className="page-title">{t("accounts")}</h1>
        {(user?.role === "super_admin" || user?.role === "warehouse_admin") && (
          <button onClick={() => setShowForm(true)} className="btn-primary">新建账户</button>
        )}
      </div>
      {loading ? (
        <div className="text-center py-8 text-gray-400">加载中...</div>
      ) : (
        <DataTable columns={[
          { key: "account_name", label: "账户名称" }, { key: "account_type", label: "类型" },
          { key: "account_number", label: "账号" }, { key: "opening_balance", label: "月初余额" },
        ]} data={data} total={data.length} page={1} pageSize={100} onPageChange={()=>{}} />
      )}
      {showForm && (
        <div className="modal-overlay"><div className="bg-white rounded-xl p-6 w-96">
          <h2 className="font-semibold mb-4">新建收款账户</h2>
          <div className="space-y-3">
            <div><label className="form-label">账户名称</label><input className="form-input" value={form.account_name} onChange={e=>setForm({...form,account_name:e.target.value})} /></div>
            <div><label className="form-label">类型</label><select className="form-input" value={form.account_type} onChange={e=>setForm({...form,account_type:e.target.value})}><option value="bank">银行</option><option value="alipay">支付宝</option><option value="wechat">微信</option></select></div>
            <div><label className="form-label">账号</label><input className="form-input" value={form.account_number} onChange={e=>setForm({...form,account_number:e.target.value})} /></div>
            <div><label className="form-label">月初余额</label><input type="number" className="form-input" value={form.opening_balance} onChange={e=>setForm({...form,opening_balance:+e.target.value})} /></div>
          </div>
          <div className="flex justify-end gap-3 mt-6"><button onClick={()=>setShowForm(false)} className="px-4 py-2 border rounded">取消</button><button onClick={handleCreate} className="px-4 py-2 bg-primary text-white rounded">保存</button></div>
        </div></div>
      )}
    </>
  );
}

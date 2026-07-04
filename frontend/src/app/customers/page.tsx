"use client";
import { useEffect, useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import { useI18n } from "@/hooks/useI18n";
import { api, getToken } from "@/lib/api";
import { useRouter } from "next/navigation";
import DashboardLayout from "@/components/layout/DashboardLayout";
import DataTable from "@/components/common/DataTable";
import FormModal from "@/components/common/FormModal";

export default function CustomersPage() {
  const { t } = useI18n();
  const { user } = useAuth();
  const router = useRouter();
  const [data, setData] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ customer_code: "", company_name: "", contact_person: "", contact_info: "", credit_status: false, credit_limit: 0, remark: "" });

  useEffect(() => { if (!getToken()) router.push("/login"); }, []);

  async function load() {
    const res = await api.get<any>(`/customers?page=${page}&page_size=20&search=${search}`);
    setData(res.data); setTotal(res.total);
  }

  useEffect(() => { load(); }, [page, search]);

  async function handleCreate() {
    await api.post("/customers", form);
    setShowForm(false); setForm({ customer_code: "", company_name: "", contact_person: "", contact_info: "", credit_status: false, credit_limit: 0, remark: "" });
    load();
  }

  const columns = [
    { key: "customer_code", label: "客户编号" },
    { key: "company_name", label: "公司名称" },
    { key: "contact_person", label: "联系人" },
    { key: "contact_info", label: "联系方式" },
    { key: "credit_status", label: "账期客户", render: (v: boolean) => v ? "是" : "否" },
    { key: "credit_limit", label: "额度" },
  ];

  return (
    <DashboardLayout>
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-bold">{t("customers")}</h1>
        {(user?.role === "super_admin" || user?.role === "warehouse_admin") && (
          <button onClick={() => setShowForm(true)} className="bg-primary text-white px-4 py-2 rounded-lg text-sm">{t("create")}</button>
        )}
      </div>
      <div className="mb-4"><input type="text" placeholder={t("search") + "..."} value={search} onChange={e => { setSearch(e.target.value); setPage(1); }} className="border rounded-lg px-3 py-2 w-64 text-sm" /></div>
      <DataTable columns={columns} data={data} total={total} page={page} pageSize={20} onPageChange={setPage} />
      {showForm && (
        <FormModal title="新建客户" onClose={() => setShowForm(false)} onSave={handleCreate}>
          <div className="space-y-3">
            <div><label className="block text-sm mb-1">客户编号</label><input className="border rounded px-3 py-2 w-full text-sm" value={form.customer_code} onChange={e => setForm({...form, customer_code: e.target.value})} /></div>
            <div><label className="block text-sm mb-1">公司名称</label><input className="border rounded px-3 py-2 w-full text-sm" value={form.company_name} onChange={e => setForm({...form, company_name: e.target.value})} /></div>
            <div><label className="block text-sm mb-1">联系人</label><input className="border rounded px-3 py-2 w-full text-sm" value={form.contact_person} onChange={e => setForm({...form, contact_person: e.target.value})} /></div>
            <div><label className="block text-sm mb-1">联系方式</label><input className="border rounded px-3 py-2 w-full text-sm" value={form.contact_info} onChange={e => setForm({...form, contact_info: e.target.value})} /></div>
            <div className="flex items-center gap-2"><input type="checkbox" checked={form.credit_status} onChange={e => setForm({...form, credit_status: e.target.checked})} /><span className="text-sm">账期客户</span></div>
            {form.credit_status && <div><label className="block text-sm mb-1">额度</label><input type="number" className="border rounded px-3 py-2 w-full text-sm" value={form.credit_limit} onChange={e => setForm({...form, credit_limit: +e.target.value})} /></div>}
            <div><label className="block text-sm mb-1">备注</label><input className="border rounded px-3 py-2 w-full text-sm" value={form.remark} onChange={e => setForm({...form, remark: e.target.value})} /></div>
          </div>
        </FormModal>
      )}
    </DashboardLayout>
  );
}

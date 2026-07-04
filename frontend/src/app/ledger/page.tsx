"use client";
import { useEffect, useState } from "react";
import DashboardLayout from "@/components/layout/DashboardLayout";
import DataTable from "@/components/common/DataTable";
import { api, getToken } from "@/lib/api";
import { useI18n } from "@/hooks/useI18n";
import { useRouter } from "next/navigation";

export default function LedgerPage() {
  const { t } = useI18n(); const router = useRouter();
  const [data, setData] = useState<any[]>([]); const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1); const [month, setMonth] = useState("");

  useEffect(() => { if (!getToken()) router.push("/login"); load(); }, [page, month]);

  async function load() {
    const r = await api.get<any>(`/income-expense/ledger?page=${page}&page_size=30${month?"&month="+month:""}`);
    setData(r.data); setTotal(r.total);
  }

  return (
    <DashboardLayout>
      <div className="flex justify-between mb-4"><h1 className="text-xl font-bold">资金流水总览</h1>
        <input type="month" value={month} onChange={e=>{setMonth(e.target.value);setPage(1);}} className="border rounded px-3 py-2 text-sm" />
      </div>
      <DataTable columns={[
        { key: "date", label: "日期", render: (v:any)=>v?.slice(0,10) },
        { key: "type", label: "类型", render: (v:any)=><span className={v==="income"?"text-green-600":"text-red-600"}>{v==="income"?"收款":"付款"}</span> },
        { key: "amount", label: "金额" }, { key: "currency", label: "币种" },
        { key: "remark", label: "备注" }, { key: "source", label: "来源" },
      ]} data={data} total={total} page={page} pageSize={30} onPageChange={setPage} />
    </DashboardLayout>
  );
}

"use client";
import { useEffect, useState } from "react";
import DataTable from "@/components/common/DataTable";
import { api, getToken } from "@/lib/api";
import { useI18n } from "@/hooks/useI18n";
import { useRouter } from "next/navigation";
import { Download } from "lucide-react";

export default function AuditLogsPage() {
  const { t } = useI18n(); const router = useRouter();
  const [logs, setLogs] = useState<any[]>([]); const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1); const [date, setDate] = useState("");

  useEffect(() => { if (!getToken()) router.push("/login"); load(); }, [page, date]);

  async function load() {
    try { const r = await api.get<any>(`/settings/logs?page=${page}&page_size=20${date?"&date="+date:""}`); setLogs(r.data); setTotal(r.total); }
    catch { setLogs([]); setTotal(0); }
  }

  async function backup() {
    const token = getToken();
    window.open(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1"}/settings/backup`, "_blank");
  }

  return (
    <>
      <div className="flex justify-between mb-4">
        <h1 className="text-xl font-bold">操作日志 & 数据备份</h1>
        <button onClick={backup} className="flex items-center gap-1 bg-green-500 text-white px-4 py-2 rounded text-sm"><Download size={14}/> 备份全部数据</button>
      </div>
      <div className="mb-4"><input type="date" value={date} onChange={e=>{setDate(e.target.value);setPage(1);}} className="border rounded px-3 py-2 text-sm" /></div>
      <DataTable columns={[
        { key: "user_name", label: "操作人" }, { key: "action_type", label: "操作类型" },
        { key: "module", label: "模块" }, { key: "created_at", label: "时间", render: (v:any)=>v?.slice(0,19) },
      ]} data={logs} total={total} page={page} pageSize={20} onPageChange={setPage} />
    </>
  );
}

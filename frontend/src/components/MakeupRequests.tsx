"use client";
import ActionGate from "@/components/permissions/ActionGate";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
interface MakeupRequest {id: number; employee_id: number; date: string; sessions: number[]; reason: string; status: string;}
export default function MakeupRequests({personal}: {personal: boolean}) {
  const {user} = useAuth();
  const [rows, setRows] = useState<MakeupRequest[]>([]);
  const [date, setDate] = useState(""); const [reason, setReason] = useState("");
  const [session, setSession] = useState(1); const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  async function load() {const r=await api.get<{data:MakeupRequest[]}>(`/clock-in/makeup-requests${personal ? "?view=self" : ""}`);setRows(r.data);}
  useEffect(() => {load().catch(e=>setMessage(e.message));}, [personal,user?.id]);
  async function submit(id?:number) {
    setBusy(true);
    try {
      if(id) await api.post(`/clock-in/makeup-requests/${id}/approve`,{});
      else await api.post("/clock-in/makeup-requests?view=self",{date,sessions:[session],reason});
      setMessage(id ? "已处理" : "申请已提交，等待独立主管或管理员处理");await load();
    }catch(e){setMessage(e instanceof Error?e.message:"操作失败");}finally{setBusy(false);}
  }
  return <section className="card p-4 my-4 space-y-3"><h2 className="font-semibold">补卡申请</h2>
    {personal && <div className="flex flex-wrap gap-2"><input aria-label="补卡日期" type="date" className="form-input min-h-11" value={date} onChange={e=>setDate(e.target.value)}/><select aria-label="补卡时段" className="form-input min-h-11" value={session} onChange={e=>setSession(Number(e.target.value))}>{[1,2,3,4].map(s=><option key={s} value={s}>时段 {s}</option>)}</select><input aria-label="补卡原因" className="form-input min-h-11" value={reason} onChange={e=>setReason(e.target.value)} placeholder="补卡原因"/><ActionGate anyOf={["clock_in.approve_makeup_request#approve"]}><button disabled={busy} onClick={()=>submit()} className="btn-primary min-h-11">提交补卡申请</button></ActionGate></div>}
    <p role="status">{message}</p>
    <div className="overflow-auto">{rows.map(r=><div className="flex gap-3 items-center py-2" key={r.id}><span>员工 {r.employee_id} · {r.date} · {r.reason} · {r.status}</span>{!personal && r.status==="pending" && r.employee_id!==user?.self_employee_id && r.employee_id!==user?.attendance_employee_id && <ActionGate anyOf={["clock_in.approve_makeup_request#approve"]}><button disabled={busy} className="btn-primary min-h-11" onClick={()=>submit(r.id)}>批准补卡</button></ActionGate>}</div>)}</div>
  </section>;
}

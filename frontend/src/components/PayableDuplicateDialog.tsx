"use client";
import { useState } from "react";
import Link from "next/link";
import { fmtMoney } from "@/lib/currency";
import { billStatus } from "@/components/ProcurementInfo";

export type DuplicateConfirmation={candidate_ids:number[];reason:string};
export default function PayableDuplicateDialog({challenge,onClose,onConfirm}:{challenge:any;onClose:()=>void;onConfirm:(data:DuplicateConfirmation)=>Promise<void>}) {
  const [reason,setReason]=useState(""),[saving,setSaving]=useState(false),[error,setError]=useState("");
  async function confirm(){
    if(!reason.trim()){setError("请填写本次继续登记的原因");return;}
    if(saving)return;setSaving(true);
    try{await onConfirm({candidate_ids:challenge.candidates.map((c:any)=>c.id),reason});}finally{setSaving(false);}
  }
  return <div className="modal-overlay z-[90]"><div role="dialog" aria-label="应付重复核对" className="bg-white rounded-xl w-full max-w-xl max-h-[90vh] flex flex-col">
    <h2 className="font-semibold p-4 border-b">{challenge.hard_duplicate ? "同一发票不能重复登记" : "疑似重复，请核对本次业务"}</h2>
    <div className="p-4 overflow-auto space-y-3 text-sm"><p>{challenge.message}</p>
      {(challenge.candidates || []).map((c:any)=><div className="border p-3 rounded" key={c.id}>
        <Link href={`/payable?bill_id=${c.id}`} target="_blank" className="text-blue-600 underline">账单 #{c.id} · {c.bill_number}</Link>
        <p>{c.bill_date?.slice(0,10)} · {fmtMoney(c.amount,c.currency)} · {billStatus[c.status] || c.status || "未记录"}</p>
        <p>{c.reasons.join("；")}</p>
      </div>)}
      {!challenge.hard_duplicate && <><label className="form-label" htmlFor="duplicate-reason">本次继续登记的原因（必填）</label><textarea id="duplicate-reason" className="form-input" maxLength={1000} value={reason} onChange={e=>setReason(e.target.value)}/><p>仅说明本次业务，不会让原单或以后同号账单永久免检。操作者、时间和上述对象会留痕。</p></>}
      {error && <p role="alert" className="text-red-600">{error}</p>}
    </div><div className="p-4 border-t flex gap-3 justify-end"><button className="btn-secondary" onClick={onClose} disabled={saving}>返回核对</button>{!challenge.hard_duplicate && <button className="btn-primary" disabled={saving} onClick={confirm}>说明后继续登记</button>}</div>
  </div></div>;
}

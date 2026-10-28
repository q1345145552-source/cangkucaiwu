"use client";
import ActionGate from "@/components/permissions/ActionGate";
import { useEffect, useState, useRef } from "react";
import { warehouseRequestHeaders } from "@/lib/api";
import { fmtMoney } from "@/lib/currency";

const states:Record<string,string>={matched:"一致",different:"有差异",unknown:"依据未知",not_applicable:"不适用",valid:"本次复核有效",stale:"复核已失效，需重新复核",not_reviewed:"尚未复核"};
const thaiTime=(value:string)=>value ? new Date(value).toLocaleString("zh-CN",{timeZone:"Asia/Bangkok"})+"（泰国时间）" : "时间未记录";

export function ThreeWayMatch({value}:{value:any}) {
  if(!value)return null;
  return <section aria-label="三单匹配" className="border rounded p-3 space-y-2 text-sm">
    <h3 className="font-semibold">采购 · 收货 · 应付匹配</h3>
    <p>业务类型：{value.kind_label} · 结果：{states[value.status] || "待核实"}</p>
    <p>采购与应付数量：{states[value.quantity_match]} · 收货数量：{states[value.receipt_quantity_match]}</p>
    <p>账单总金额：{states[value.amount_match]} · 结构化行金额：{states[value.line_amount_match]}</p>
    <p>{value.policy?.strict ? "严格收货付款上限已开启" : "严格校验未开启，沿用原付款规则"}；原有待老板确认限制始终保留。</p>
    {value.payment_cap!=null && <p>按已记录实收可核对金额：{fmtMoney(value.payment_cap,value.currency)}</p>}
    {(value.notes || []).map((note:string,i:number)=><p key={i} className="text-amber-800">{note}</p>)}
    <p className={value.review_status==="stale" ? "text-red-600 font-medium" : ""}>{states[value.review_status]}</p>
    {value.review && <div><p>复核人：{value.review.operator_name} · {thaiTime(value.review.confirmed_at)}</p><p>原因：{value.review.reason}</p><p className="text-xs break-all">快照：{value.review.snapshot_hash}</p></div>}
    {!!value.review_history?.length && <details><summary>查看历次复核与失效记录（{value.review_history.length}条）</summary>
      {value.review_history.map((h:any)=><div className="border-t py-2" key={h.id}><p>{h.action==="match_confirm" ? "老板复核" : "旧复核失效"} · {h.operator_name} · {thaiTime(h.created_at)}</p><p>{h.data?.reason}</p></div>)}
    </details>}
    <p className="text-xs text-gray-500">已付款历史保持原样；此处展示依据和差异，不重算或撤销付款。</p>
  </section>;
}

export function ReceiptHistory({order}:{order:any}) {
  const [preview,setPreview]=useState<{url:string;type:string}|null>(null),[error,setError]=useState("");
  const selectedOrder=useRef(order.id);
  useEffect(()=>{selectedOrder.current=order.id;setPreview(null);setError("");},[order.id]);
  useEffect(()=>()=>{if(preview)URL.revokeObjectURL(preview.url);},[preview]);
  async function photo(id:number) {
    setError("");
    try{
      const orderId=order.id,headers=warehouseRequestHeaders();
      const r=await fetch(`/api/v1/suppliers/purchase-orders/${orderId}/receipts/${id}/photo`,{headers});
      if(!r.ok){const body=await r.json();throw Error(body.detail || "照片读取失败");}
      const blob=await r.blob();
      if(selectedOrder.current!==orderId || JSON.stringify(headers)!==JSON.stringify(warehouseRequestHeaders()))throw Error("账号、仓库或采购单已变化，请重新查看照片");
      setPreview({url:URL.createObjectURL(blob),type:blob.type});
    }catch(e:any){setError(e.message || "照片读取失败");}
  }
  return <section aria-label="收货批次历史" className="border rounded p-3 space-y-3 text-sm">
    <h3 className="font-semibold">收货批次历史</h3>
    {order.receipt_baseline && <div className="bg-amber-50 p-2 rounded"><p>{order.receipt_baseline.note}</p>
      {order.receipt_baseline.source==="legacy_recorded_fields" && <p>历史基数：{order.items?.map((it:any)=>`${it.product_name} ${it.historical_received_quantity ?? "未知"}${it.unit || "（单位未记录）"}`).join("；")}</p>}
      {order.receipt_baseline.photo_path && <ActionGate anyOf={["suppliers.upload_purchase_receipt"]}><button className="text-blue-600 underline" onClick={()=>photo(0)}>查看历史基数照片</button></ActionGate>}
    </div>}
    {(order.receipt_issues || []).map((s:string)=><p className="text-red-600" key={s}>{s}</p>)}
    {!order.receipt_batches?.length ? <p>暂无新收货批次，没有补造历史事件。</p> : order.receipt_batches.map((batch:any)=><div className="border rounded p-3 space-y-1 target:bg-blue-50" key={batch.id} id={`receipt-event-${batch.id}`}>
      <p className="font-medium">批次 #{batch.id} · {batch.operator_name} · {thaiTime(batch.received_at)}</p>
      {batch.items.map((it:any)=><p key={it.line_id}>{it.product_name} {it.spec || ""} · 本次 {it.quantity}{it.unit || "（单位未记录）"}<span className="block text-xs text-gray-500 break-all">行编号：{it.line_id}</span></p>)}
      <p>备注：{batch.remark || "未填写"}</p><p className="text-xs break-all">请求编号：{batch.request_key}</p>
      <ActionGate anyOf={["suppliers.upload_purchase_receipt"]}><button className="text-blue-600 underline" onClick={()=>photo(batch.id)}>查看批次{batch.id}照片</button></ActionGate>
    </div>)}
    {error && <p role="alert" className="text-red-600">{error}</p>}
    {preview && <div className="modal-overlay z-[95]" onClick={()=>setPreview(null)}><div role="dialog" aria-label="到货照片" className="bg-white rounded p-3 max-w-[95vw] max-h-[90vh] overflow-auto" onClick={e=>e.stopPropagation()}><button className="btn-secondary mb-2" onClick={()=>setPreview(null)}>关闭照片</button>{preview.type.includes("pdf") ? <a href={preview.url} target="_blank" rel="noreferrer">打开PDF凭证</a> : <img className="max-w-full" src={preview.url} alt="本批到货照片"/>}</div></div>}
  </section>;
}

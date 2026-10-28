"use client";
import ActionGate from "@/components/permissions/ActionGate";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { useMenuPermission } from "@/hooks/useMenuPermission";
import { useToast } from "@/components/ui/Toast";

export type ReceivablePosition = { currency: string; shipped: number; received: number; applied: number; outstanding: number; prepayment: number };
const money = (v: number, cur: string) => `${cur === "CNY" ? "¥" : cur === "THB" ? "฿" : cur + " "}${v.toLocaleString("zh-CN",{minimumFractionDigits:2,maximumFractionDigits:2})}`;

export function ReceivableSummary({ positions }: { positions: Record<string, ReceivablePosition> }) {
  return <div className="space-y-1">{Object.entries(positions || {}).map(([cur,p]) => <div key={cur} className="text-xs whitespace-nowrap">尚欠 <span className="text-red-600">{money(p.outstanding,cur)}</span> · 预收 <span className="text-green-700">{money(p.prepayment,cur)}</span></div>)}</div>;
}

export default function CustomerReceivable({ customerId, onChanged }: { customerId: number; onChanged?: () => void }) {
  const canLink = useMenuPermission("credit"), { toast } = useToast();
  const [data,setData] = useState<any>(null), [error,setError] = useState(""), [month,setMonth] = useState(""), [revision,setRevision] = useState(0);
  const [linking,setLinking] = useState(false), [receipts,setReceipts] = useState<any[]>([]), [selected,setSelected] = useState(""), [saving,setSaving] = useState(false), [source,setSource] = useState<any>(null);
  const request=useRef(0), linkRequest=useRef(0), busy=useRef(false);
  useEffect(() => { setLinking(false);setReceipts([]);setSelected("");linkRequest.current++;return()=>{linkRequest.current++;}; },[customerId]);
  useEffect(() => {
    const id=++request.current;setData(null);setError("");setSource(null);
    api.get<any>(`/customers/${customerId}/receivables${month ? `?month=${month}` : ""}`).then(r=>{if(id===request.current)setData(r);}).catch(e=>{if(id===request.current)setError(e.message);});
    return()=>{request.current++;};
  },[customerId,month,revision]);
  async function openLink() {
    const generation=++linkRequest.current;setLinking(true);setReceipts([]);setSelected("");
    try {
      const rows:any[]=[];let page=1,total=1;
      while(rows.length<total){const r=await api.get<any>(`/incoming?eligible_for_customer_id=${customerId}&page=${page++}&page_size=200`);rows.push(...r.data);total=r.total;if(!r.data.length)break;}
      if(generation===linkRequest.current)setReceipts(rows.filter(r=>!r.customer_identity_conflict));
    }catch(e:any){if(generation===linkRequest.current){toast("error",e.message);setLinking(false);}}
  }
  async function saveLink() {
    if(busy.current)return;
    if(!selected){toast("error","请选择实际到账记录");return;}
    busy.current=true;setSaving(true);
    try{const r=await api.post<any>(`/customers/${customerId}/receipts/link`,{incoming_flow_id:+selected});toast("success",r.message);setLinking(false);setRevision(n=>n+1);onChanged?.();}
    catch(e:any){toast("error",e.message);}finally{busy.current=false;setSaving(false);}
  }
  return <section aria-label="客户应收实收预收对账" className="space-y-4">
    <div className="flex flex-wrap items-center gap-2 justify-between"><h3 className="font-semibold">客户应收、实收与预收</h3>{canLink&&<button className="btn-secondary text-sm" onClick={openLink}>关联已有到账</button>}</div>
    <div className="flex flex-wrap gap-2 items-center"><label className="text-sm" htmlFor={`receivable-month-${customerId}`}>截至月份</label><input id={`receivable-month-${customerId}`} aria-label="客户对账截至月份" className="form-input w-40" type="month" value={month} onChange={e=>setMonth(e.target.value)}/><button className="btn-secondary text-xs" onClick={()=>setMonth("")}>全部已登记日期</button></div>
    <p className="text-xs text-gray-500">{month ? "金额为截至该月末的累计余额，下方仅列该月明细；期初来自之前有来源的发货与实收。" : "金额来自全部已登记发货与唯一实际到账，各币种独立。"} 充值申报不是实收；不按名字猜客户，不逐票猜核销。</p>
    {error?<div role="alert" className="text-red-600">{error}<button className="btn-secondary ml-2" onClick={()=>setRevision(n=>n+1)}>重试</button></div>:!data?<p>加载对账中…</p>:<>
      {data.needs_review&&<div className="bg-amber-50 border border-amber-200 rounded p-3 text-sm"><p className="font-semibold">历史数据待核对</p><p>以下金额未自动补期初、未当作新的实收或可用预收，旧记录保留；当前数字仅是可核实来源的对账结果。</p>{data.review_items.map((r:any,i:number)=><p key={i}>#{r.source_id} · {money(r.amount,r.currency)} · {r.message}</p>)}</div>}
      {Object.entries(data.by_currency || {}).map(([cur,p]:[string,any])=><div key={cur} className="border rounded-xl p-3 space-y-3">
        <h4 className="font-semibold">{cur==="CNY"?"人民币":cur==="THB"?"泰铢":cur}</h4>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">{[["发货应收",p.shipped],["实际已收",p.received],["已核销",p.applied],["尚欠",p.outstanding],["预收可用",p.prepayment]].map(([label,v])=><div key={String(label)} className="bg-gray-50 rounded p-2"><div className="text-xs text-gray-500">{label}</div><div className="font-semibold">{money(Number(v),cur)}</div></div>)}</div>
        <p className="text-xs text-gray-500">{month&&`期初：${p.opening_signed_balance>=0?"尚欠":"预收"} ${money(Math.abs(p.opening_signed_balance),cur)}；本月发货 ${money(p.period_shipped,cur)}，本月实收 ${money(p.period_received,cur)}。`} 已核销为发货应收和实收较小值；余额不会同时记成核销和预收。</p>
        <div className="overflow-x-auto"><table className="w-full text-xs min-w-[620px]"><thead><tr><th className="text-left">业务日期</th><th>来源</th><th>发货应收</th><th>实际到账</th><th>当时尚欠</th><th>当时预收</th></tr></thead><tbody>{(p.events||[]).map((e:any)=><tr className="border-t" key={`${e.source}-${e.source_id}`}><td className="py-2">{e.date}</td><td className="text-center"><button className="text-blue-600 underline" onClick={()=>setSource(e)}>{e.source==="shipment"?"发货":"到账"} #{e.source_id}</button></td><td className="text-center">{e.source==="shipment"?money(e.amount,cur):"—"}</td><td className="text-center">{e.source!=="shipment"?money(e.amount,cur):"—"}</td><td className="text-center">{money(e.outstanding_after,cur)}</td><td className="text-center">{money(e.prepayment_after,cur)}</td></tr>)}{!p.events?.length&&<tr><td className="text-center py-3" colSpan={6}>所选范围暂无明细</td></tr>}</tbody></table></div>
      </div>)}
      {source&&<div className="bg-blue-50 rounded-lg p-3 text-sm space-y-2" aria-label="客户对账来源详情"><p>来源：{source.source==="shipment"?"原账期发货记录":"原实际到账流水"} #{source.source_id}</p><p>客户 #{data.customer_id} · 仓库 #{source.warehouse_id} · {source.date} · {money(source.amount,source.currency)}</p>{source.credit_id&&<p>账期账户 #{source.credit_id} · 订单数 {source.order_count??"未知"} · 参考 {source.order_no||"—"}</p>}<p>备注：{source.remark||"—"}</p><button className="btn-secondary text-xs" onClick={()=>setSource(null)}>收起来源</button></div>}
    </>}
    {linking&&<div className="border rounded-xl p-3 bg-gray-50 space-y-3" aria-label="关联客户实际到账"><h4 className="font-semibold">明确客户实际到账</h4><p className="text-xs">只选择本仓未归属或已归属本客户的实际到账。按编号确认，不按付款方名称推断；已归属其他客户不能改绑。关联不会再次入账。</p><select aria-label="待关联实际到账" className="form-input" value={selected} disabled={saving} onChange={e=>setSelected(e.target.value)}><option value="">请选择实际到账</option>{receipts.map(r=><option key={r.id} value={r.id}>#{r.id} · {r.received_date.slice(0,10)} · {r.payer_name||"未填付款方"} · {money(r.amount,r.currency)}</option>)}</select>{!receipts.length&&<p className="text-xs text-gray-500">暂无可关联到账；新收款请到到账流水登记，勿把申报当成到账。</p>}<div className="flex justify-end gap-2"><button className="btn-secondary" disabled={saving} onClick={()=>setLinking(false)}>取消关联</button><ActionGate anyOf={["customers.link_customer_receipt#operate"]}><button className="btn-primary" disabled={saving} onClick={saveLink}>{saving?"关联中…":"确认关联到账"}</button></ActionGate></div></div>}
  </section>;
}

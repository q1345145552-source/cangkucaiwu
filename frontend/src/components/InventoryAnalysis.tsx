'use client';
import {useEffect,useRef,useState} from 'react';
import Link from 'next/link';
import {api,warehouseRequestHeaders} from '@/lib/api';
import {useAuth} from '@/hooks/useAuth';
const API_URL=process.env.NEXT_PUBLIC_API_URL||'/api/v1';
const states:Record<string,string>={attention:'待核实',normal:'未触发',unavailable:'不可判断',info:'情况说明'};
const currentMonth=()=>new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Bangkok',year:'numeric',month:'2-digit'}).format(new Date());
export default function InventoryAnalysis({revision=0}:{revision?:number}){
  const {user}=useAuth() as {user:{role:string}|null};const allowed=user?.role==='warehouse_admin',scope=JSON.stringify(warehouseRequestHeaders());
  const [month,setMonth]=useState(currentMonth),[applied,setApplied]=useState(currentMonth),[data,setData]=useState<any>(null),[loaded,setLoaded]=useState(''),[error,setError]=useState(''),[downloading,setDownloading]=useState(false);const seq=useRef(0);
  useEffect(()=>{setMonth(currentMonth());setApplied(currentMonth());},[scope]);
  useEffect(()=>{const id=++seq.current;setData(null);setLoaded('');setError('');if(!allowed)return;
    api.get<any>(`/inventory/analysis?month=${applied}`).then(r=>{if(id===seq.current&&scope===JSON.stringify(warehouseRequestHeaders())){setData(r);setLoaded(scope);}}).catch(e=>{if(id===seq.current&&scope===JSON.stringify(warehouseRequestHeaders()))setError(e.message||'库存分析读取失败，未显示成0');});return()=>{seq.current++;};
  },[scope,allowed,applied,revision]);
  async function download(){const expected=scope;setDownloading(true);setError('');try{
    const r=await fetch(`${API_URL}/inventory/analysis/export?month=${applied}`,{headers:warehouseRequestHeaders()});
    if(!r.ok){const b=await r.json();throw Error(typeof b.detail==='string'?b.detail:'库存分析导出失败');}
    const blob=await r.blob();if(expected!==JSON.stringify(warehouseRequestHeaders()))return;
    const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=`库存用量-${applied}.csv`;a.click();URL.revokeObjectURL(url);
  }catch(e:any){if(expected===JSON.stringify(warehouseRequestHeaders()))setError(e.message||'库存分析导出失败');}finally{if(expected===JSON.stringify(warehouseRequestHeaders()))setDownloading(false);}}
  if(!allowed)return null;const visible=loaded===scope?data:null;
  return <section className="card p-4 space-y-3 min-w-0"><div className="flex flex-wrap gap-3 items-center"><h2 className="font-semibold">库存盘点、提醒与用量分析</h2><Link className="text-blue-700 underline" href="/suppliers/risk">老板采购风险看板</Link></div>
    <form className="flex flex-wrap gap-3 items-end" onSubmit={e=>{e.preventDefault();setApplied(month);}}><label>月份<input aria-label="库存分析月份" className="form-input" type="month" required value={month} onChange={e=>setMonth(e.target.value)}/></label><button className="btn-secondary">查询库存分析</button><button type="button" className="btn-secondary" disabled={!visible||downloading} onClick={download}>导出库存用量明细</button></form>
    {error&&<p role="alert" className="text-red-600 break-words">{error}</p>}
    {visible?<><p className="text-sm">{visible.date_basis}</p><p className="text-sm">{visible.notice}</p><p className="text-sm">同仓同月订单量：{visible.order_volume.order_count??'未知'} · {visible.order_volume.reason}；未映射采购行：{visible.unmapped_purchase_lines}，未猜配到SKU。</p>
      {visible.data.map((r:any)=><article key={r.account_id} className="border rounded p-3 space-y-2 text-sm break-words"><h3 className="font-semibold">{r.sku.code} · {r.sku.name} / {r.unit_label}</h3><p>月初{r.opening_quantity??'未知'} · 订购{r.ordered_quantity}（不当作入库） · 净实收{r.received_quantity} · 净领用{r.net_issued_quantity} · 盘点调整{r.stocktake_adjustment} · 月末/当前{r.closing_quantity??'未知'}</p><p className={r.low_stock_state==='attention'?'text-amber-800':''}>安全库存：{r.minimum_quantity??'未配置'} · {states[r.low_stock_state]} · {r.low_stock_reason}</p><p>用量：{states[r.usage_state]} · {r.usage_explanation}。收货/净领用{r.receipt_usage_ratio??'不可算'}，阈值{r.configured_ratio??'未配置'}。备货说明：{r.stockpiling_note||'未填写'}</p><p>单票耗材成本：{r.cost.available?JSON.stringify(r.cost.per_order_by_currency):'不可算'} · {r.cost.reason}</p><p>{r.cost.note}</p><p>本月原流水：{r.movement_ids.map((id:number)=>`#${id}`).join('、')||'无已知变动'}</p></article>)}{!visible.data.length&&<p>暂无本仓库存台账；不代表真实库存为0。</p>}
    </>:!error&&<p>库存分析读取中</p>}
  </section>;
}

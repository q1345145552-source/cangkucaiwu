"use client";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";

const amount=(n:number,cur:string)=>`${cur==="CNY"?"¥":cur==="THB"?"฿":cur+" "}${n.toLocaleString("zh-CN",{minimumFractionDigits:2,maximumFractionDigits:2})}`;
const statusNames:Record<string,string>={confirmed:"已确认",approved:"已通过",partially_approved:"部分通过",paid:"已付款",fund_linked:"关联备用金",completed:"已完成",pending:"待付款",overdue:"逾期未付",partially_paid:"部分付款",period_unverified:"归期待核对"};
const sourceNames:Record<string,string>={payroll:"工资单",reimbursement:"报销单",payable:"应付账单",expense_approval:"费用审批",fund_item:"备用金开销",manual_expense:"手工支出"};
export default function OperatingReport({ startDate,endDate }:{startDate:string;endDate:string}) {
  const [options,setOptions]=useState<any[]>([]);
  const [data,setData]=useState<any>(null),[error,setError]=useState(""),[revision,setRevision]=useState(0);
  const [customer,setCustomer]=useState(""),[currency,setCurrency]=useState(""),[shipPage,setShipPage]=useState(1),[costPage,setCostPage]=useState(1),[source,setSource]=useState<any>(null);
  const generation=useRef(0);
  useEffect(()=>{
    const change=()=>{generation.current++;setData(null);setSource(null);setOptions([]);setCustomer("");setShipPage(1);setCostPage(1);setRevision(n=>n+1);};
    window.addEventListener("warehouse-changed",change);window.addEventListener("auth-user-refreshed",change);
    return()=>{window.removeEventListener("warehouse-changed",change);window.removeEventListener("auth-user-refreshed",change);};
  },[]);
  useEffect(()=>{
    const id=++generation.current;setData(null);setError("");setSource(null);
    const q=new URLSearchParams({start_date:startDate,end_date:endDate,shipment_page:String(shipPage),cost_page:String(costPage),page_size:"20"});
    if(customer)q.set("customer_id",customer);if(currency)q.set("currency",currency);
    api.get<any>(`/reports/operations?${q}`).then(r=>{if(id===generation.current){setData(r);setOptions(r.customer_options||[]);}}).catch(e=>{if(id===generation.current)setError(e.message||"经营报表加载失败");});
    return()=>{generation.current++;};
  },[startDate,endDate,customer,currency,shipPage,costPage,revision]);
  useEffect(()=>{setShipPage(1);setCostPage(1);},[startDate,endDate,customer,currency]);
  function pager(group:any,set:(n:number)=>void){return <div className="flex flex-wrap items-center justify-end gap-3 p-3 text-sm"><span>共 {group.total} 条</span><button className="btn-secondary" disabled={group.page<=1} onClick={()=>set(group.page-1)}>上一页</button><span>{group.page}</span><button className="btn-secondary" disabled={group.page*group.page_size>=group.total} onClick={()=>set(group.page+1)}>下一页</button></div>;}
  return <section aria-label="独立经营报表" className="space-y-4">
    <div className="flex flex-wrap gap-3 items-center justify-between"><h2 className="text-lg font-semibold">经营情况（独立）</h2><div className="flex flex-wrap gap-2">
      <select aria-label="经营报表客户" className="form-input w-44" value={customer} onChange={e=>setCustomer(e.target.value)}><option value="">全部本仓客户</option>{options.map((c:any)=><option key={c.id} value={c.id}>#{c.id} {c.name}</option>)}</select>
      <select aria-label="经营报表币种" className="form-input w-32" value={currency} onChange={e=>setCurrency(e.target.value)}><option value="">全部币种</option><option value="THB">泰铢</option><option value="CNY">人民币</option></select>
    </div></div>
    <p className="text-sm text-gray-600">{startDate} 至 {endDate} · 按发货业务日期查看，各币种独立；实际到账另列，不再记一次发货收入。</p>
    {error?<div role="alert" className="bg-red-50 p-4 rounded-xl text-red-700">{error}<button className="underline ml-3" onClick={()=>setRevision(n=>n+1)}>重试</button></div>:!data?<p role="status">经营报表加载中…</p>:<>
      <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 space-y-2"><strong>利润暂不可计算</strong><p className="text-sm">成本所属期间和完整性尚未确认。未找到成本不等于成本为零，也不能用发货金额减钱包付款额冒称经营利润。</p>{data.cost_gaps.map((s:string)=><p className="text-xs text-amber-900" key={s}>{s}</p>)}</div>
      {data.currencies.map((b:any)=><div key={b.currency} className="border rounded-xl bg-white p-4 space-y-3" aria-label={`${b.currency}经营情况`}><h3 className="font-semibold">{b.currency==="THB"?"泰铢":b.currency==="CNY"?"人民币":b.currency}</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">{[["本期发货金额",b.shipment_income],["本期实际到账",b.actual_receipts],["期末尚欠",b.receivable_asof],["期末预收",b.prepayment_asof]].map(([label,n])=><div key={String(label)} className="bg-gray-50 rounded-lg p-3"><div className="text-xs text-gray-500">{label}</div><strong>{amount(Number(n),b.currency)}</strong></div>)}</div>
        <p className="text-sm">可核实归集成本：未建立完整口径 · 经营利润：暂不可计算</p>
        <p className="text-xs text-gray-500">{b.shipment_records}条发货记录 · {b.order_count}单{b.unknown_order_count_records>0?`（${b.unknown_order_count_records}条历史记录单数未知）`:""} · 尚欠与预收累计至{endDate}。</p>
        <details><summary className="cursor-pointer text-sm text-blue-700">发货与实际到账趋势</summary><div className="overflow-x-auto"><table className="w-full min-w-[440px] text-xs"><thead><tr><th className="text-left py-2">业务日期</th><th>发货金额</th><th>实际到账</th></tr></thead><tbody>{b.daily.map((d:any)=><tr className="border-t" key={d.date}><td className="py-2">{d.date}</td><td className="text-center">{amount(d.shipment_income,b.currency)}</td><td className="text-center">{amount(d.actual_receipts,b.currency)}</td></tr>)}</tbody></table>{!b.daily.length&&<p className="text-gray-500 py-2">所选范围暂无发货或明确客户到账</p>}</div></details>
        {data.wallet&&<div className="border-t pt-3 text-sm"><strong>公司钱包对照（实际收付）</strong><p>收入 {amount(data.wallet.income_by_currency[b.currency]||0,b.currency)} · 支出 {amount(data.wallet.expense_by_currency[b.currency]||0,b.currency)} · 净收支 {amount(data.wallet.net_by_currency[b.currency]||0,b.currency)}</p><p className="text-xs text-gray-500">净收支不是经营利润；{data.wallet_scope_note}</p></div>}
      </div>)}
      {!data.wallet&&<p className="bg-blue-50 rounded-xl p-3 text-sm">{data.wallet_scope_note}</p>}
      {!!data.review_items.length&&<details className="bg-amber-50 border rounded-xl p-4"><summary className="cursor-pointer font-semibold">历史待核对（{data.review_items.length}条）</summary>{data.review_items.map((r:any,i:number)=><p className="text-sm mt-2" key={i}>客户 #{r.customer_id} · 来源 #{r.source_id} · {amount(r.amount,r.currency)} · {r.message}</p>)}</details>}
      <div className="bg-white border rounded-xl overflow-hidden" aria-label="经营发货明细"><h3 className="font-semibold p-4">有效发货来源</h3><div className="overflow-x-auto"><table className="text-sm w-full min-w-[650px]"><thead className="bg-gray-50"><tr>{["日期","客户","来源","订单数","应收运费"].map(h=><th className="p-3 text-left" key={h}>{h}</th>)}</tr></thead><tbody>{data.shipments.data.map((r:any)=><tr className="border-t" key={r.source_id}><td className="p-3">{r.date}</td><td className="p-3">#{r.customer_id} {r.customer_name}</td><td className="p-3"><button className="text-blue-600 underline" onClick={()=>setSource({...r,source:"shipment"})}>发货 #{r.source_id}</button></td><td className="p-3">{r.order_count??"未知"}</td><td className="p-3">{amount(r.amount,r.currency)}</td></tr>)}</tbody></table>{!data.shipments.data.length&&<p className="p-4 text-gray-500">暂无有效发货</p>}</div>{pager(data.shipments,setShipPage)}</div>
      <div className="bg-white border rounded-xl overflow-hidden" aria-label="待归集成本线索"><h3 className="font-semibold p-4">待归集单据线索</h3><p className="text-xs text-gray-500 px-4 pb-3">{data.reference_basis} 这里只展示原单据金额和状态，不计入已确认经营成本。</p><div className="overflow-x-auto"><table className="text-sm w-full min-w-[760px]"><thead className="bg-gray-50"><tr>{["参考日期","原单据","单据金额（非归集成本）","原状态","尚缺依据"].map(h=><th className="p-3 text-left" key={h}>{h}</th>)}</tr></thead><tbody>{data.cost_references.data.map((r:any)=><tr className="border-t" key={`${r.source}-${r.source_id}`}><td className="p-3">{r.reference_date||"日期待核对"}</td><td className="p-3"><button className="text-blue-600 underline" onClick={()=>setSource(r)}>{sourceNames[r.source]||r.source} #{r.source_id}</button></td><td className="p-3">{amount(r.nominal_amount,r.currency)}</td><td className="p-3">{statusNames[r.status]||"状态待核对"}</td><td className="p-3 max-w-64">{r.date_basis}</td></tr>)}</tbody></table>{!data.cost_references.data.length&&<p className="p-4 text-gray-500">此范围没有可列出的线索，不表示成本为零。{customer&&"成本未建立客户分配，请切换全部客户查看仓库线索。"}</p>}</div>{pager(data.cost_references,setCostPage)}</div>
      {source&&<div aria-label="经营报表来源详情" className="bg-blue-50 border rounded-xl p-4 text-sm space-y-2"><strong>{source.source==="shipment"?"原发货":sourceNames[source.source]} #{source.source_id}</strong><p>仓库 #{source.warehouse_id} · {source.date||source.reference_date} · {amount(source.amount??source.nominal_amount,source.currency)}</p>{source.customer_id&&<p>客户 #{source.customer_id} · {source.customer_name}</p>}{source.salary_period&&<p>原工资期间：{source.salary_period} · 原结算起止：{source.settle_start_date||"未记录"} 至 {source.settle_end_date||"未记录"}</p>}{source.date_basis&&<p>{source.date_basis}</p>}<p>只读核对原编号，不新增付款、分摊或成本。</p><button className="btn-secondary text-xs" onClick={()=>setSource(null)}>收起来源</button></div>}
    </>}
  </section>;
}

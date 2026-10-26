"use client";
import { useEffect,useState } from "react";
import { api,warehouseRequestHeaders } from "@/lib/api";
import { fmtMoney } from "@/lib/currency";
const labels:Record<string,string>={payable:'应付账款',approval:'费用审批',fund_item:'备用金开销',expense:'运营支出',pending:'待处理',approved:'已通过',paid:'已付款',voided:'已作废',rejected:'已驳回',completed:'已完成（历史）',partially_paid:'部分付款',overdue:'逾期'};

function OriginVoucher({value,source,id}:{value:any;source:string;id:string}){
  const [preview,setPreview]=useState(''),[type,setType]=useState(''),[error,setError]=useState('');
  let paths:string[]=[];try{paths=Array.isArray(value)?value:typeof value==='string'&&value.startsWith('[')?JSON.parse(value):value?[value]:[];}catch{paths=[];}
  useEffect(()=>()=>{if(preview)URL.revokeObjectURL(preview);},[preview]);
  async function open(index:number){try{setError('');const scope=JSON.stringify(warehouseRequestHeaders());const response=await fetch(`${process.env.NEXT_PUBLIC_API_URL||'/api/v1'}/expense-identities/${encodeURIComponent(source)}/${encodeURIComponent(id)}?voucher_index=${index}`,{headers:warehouseRequestHeaders()});if(!response.ok)throw Error('原单凭证读取失败');const blob=await response.blob();if(scope!==JSON.stringify(warehouseRequestHeaders()))throw Error('账号或仓库已变化，请重新打开原单');setPreview(URL.createObjectURL(blob));setType(blob.type);}catch(e:any){setError(e.message);}}
  return <section><h2 className="font-medium">原单凭证</h2>{paths.length?paths.map((p,i)=><button className="btn-secondary mr-2" key={i} onClick={()=>open(i)}>查看凭证 {i+1}</button>):<p>原单未记录凭证</p>}{error&&<p role="alert" className="text-red-600">{error}</p>}{preview&&(type.includes('pdf')?<a className="text-blue-600" href={preview} target="_blank" rel="noreferrer">打开原单PDF</a>:<img className="max-w-full max-h-[70vh]" src={preview} alt="原单凭证"/>)}</section>;
}
export default function CostOrigin({params}:{params:{source:string;id:string}}){
  const [data,setData]=useState<any>(null),[error,setError]=useState("");
  const scope=JSON.stringify(warehouseRequestHeaders());
  useEffect(()=>{let current=true;setData(null);setError('');api.get<any>(`/expense-identities/${params.source}/${params.id}`).then(r=>{if(current&&scope===JSON.stringify(warehouseRequestHeaders()))setData(r);}).catch(e=>{if(current)setError(e.message);});return()=>{current=false;};},[params.source,params.id,scope]);
  if(error)return <p role="alert" className="text-red-600">{error}</p>;if(!data)return <p>读取原单…</p>;
  return <article className="card p-4 space-y-3"><h1 className="text-lg font-semibold">{data.label} #{data.id} · 费用来源核对</h1><p>{data.message}</p><p>日期：{data.document.expense_date} · {fmtMoney(data.document.amount,data.document.currency)} · {labels[data.document.source_state]||data.document.source_state}</p><p>{data.document.number} {data.document.description}</p><p>原费用来源：{data.origin?`${labels[data.origin.source]||data.origin.source} #${data.origin.id}`:"历史未记录"}</p>{data.identity?.cost_payment_unknown&&<p className="text-amber-700">历史付款情况待核实，未当作零付款释放发票身份。</p>}{data.identity?.invoice_identity&&<div className="break-all"><p>开票方：{data.identity.invoice_identity.issuer_identifier}</p><p>系列：{data.identity.invoice_identity.series}</p><p>号码：{data.identity.invoice_identity.number}</p></div>}<OriginVoucher key={scope} value={data.document.voucher} source={params.source} id={params.id}/><p>本页只读，不生成新费用或付款。</p></article>;
}

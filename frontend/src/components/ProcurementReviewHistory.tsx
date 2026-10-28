"use client";
import {useEffect,useRef,useState} from 'react';
import {useSearchParams} from 'next/navigation';
import {api} from '@/lib/api';
import {useAuth} from '@/hooks/useAuth';
import {controlScope,controlDownload} from '@/lib/procurementControlRequest';
const labels:Record<string,string>={pending:'待处理',cleared:'已核实无问题',follow_up:'需跟进'};
function monthNow(){const p=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Bangkok',year:'numeric',month:'2-digit'}).formatToParts(new Date());return p.find(x=>x.type==='year')!.value+'-'+p.find(x=>x.type==='month')!.value;}
export default function ProcurementReviewHistory(){
 const {user}=useAuth() as {user:{role:string}|null};const allowed=user?.role==='warehouse_admin',scope=controlScope(),params=useSearchParams();
 const initial=params.get('month')||monthNow();const [month,setMonth]=useState(initial),[applied,setApplied]=useState(initial),[page,setPage]=useState(1),[data,setData]=useState<any>(null),[loaded,setLoaded]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false);const sequence=useRef(0),query=new URLSearchParams({month:applied,all_scopes:'true'}).toString();
 useEffect(()=>{const id=++sequence.current;setData(null);setLoaded('');setError('');if(!allowed)return;
  api.get<any>(`/supplier-risk/reviews?${query}&page=${page}&page_size=20`).then(r=>{if(id===sequence.current&&controlScope()===scope){setData(r);setLoaded(scope);}}).catch(e=>{if(id===sequence.current&&controlScope()===scope)setError(e.message||'历史读取失败');});return()=>{sequence.current++;};},[query,page,scope,allowed]);
 async function download(){setBusy(true);try{await controlDownload(`/supplier-risk/reviews/export?${query}`,`采购复核历史-${applied}.csv`,scope);}catch(e:any){if(controlScope()===scope)setError(e.message);}finally{setBusy(false);}}
 if(!allowed)return <p>仅仓库管理员可以查看复核历史。</p>;
 const visible=loaded===scope?data:null;
 return <section className="space-y-4"><div className="flex flex-wrap gap-3 items-center"><h1 className="page-title">采购复核历史</h1></div><p>历史结论与当时证据原样保存，不代表当前证据仍有效，也不是业务例外授权。同月不同筛选范围分别记录。</p>
 <form className="card p-4 flex flex-wrap gap-3 items-end" onSubmit={e=>{e.preventDefault();setPage(1);setApplied(month);}}><label>月份<input aria-label="复核历史月份" className="form-input" type="month" required value={month} onChange={e=>setMonth(e.target.value)}/></label><button className="btn-primary">查询复核历史</button><button className="btn-secondary" type="button" disabled={!visible||busy} onClick={download}>导出本月全部复核历史</button></form>
 {error&&<p role="alert" className="text-red-600">{error}</p>}{visible?<><p>共{visible.total}条历史，包含本月所有复核筛选范围。</p><div className="space-y-3">{visible.data.map((r:any)=><article className="card p-4 space-y-2 text-sm min-w-0 break-words" key={r.id}><h2 className="font-semibold">复核 #{r.id} · {r.snapshot.label} · {labels[r.conclusion]}</h2><p>操作者 #{r.reviewer_id} · {new Date(r.created_at).toLocaleString('zh-CN',{timeZone:'Asia/Bangkok'})}（泰国时间）</p><p>原因：{r.reason}</p><p>范围 {r.month} · 供应商 {r.scope.supplier_id??'全部'} · 采购人 {r.scope.orderer_id??'全部'} · 币种 {r.scope.currency??'分别列出'}</p><p>规则版本 {r.rule_version}</p><details><summary>查看当时证据</summary><pre className="whitespace-pre-wrap break-all text-xs">{JSON.stringify(r.snapshot,null,2)}</pre></details></article>)}</div>{!visible.data.length&&<p>本月暂无复核历史。</p>}<div className="flex gap-2"><button className="btn-secondary" disabled={page<=1} onClick={()=>setPage(p=>p-1)}>上一页</button><span>第{page}页</span><button className="btn-secondary" disabled={page*20>=visible.total} onClick={()=>setPage(p=>p+1)}>下一页</button></div></>:!error&&<p>读取中</p>}</section>;
}

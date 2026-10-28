"use client";
import ActionGate from "@/components/permissions/ActionGate";
import {useEffect,useRef,useState} from 'react';
import {api} from '@/lib/api';
import {useAuth} from '@/hooks/useAuth';
import {registrationDraft} from '@/lib/registrationRequest';
import {controlScope,controlMutation} from '@/lib/procurementControlRequest';
const labels:Record<string,string>={pending:'待处理',cleared:'已核实无问题',follow_up:'需跟进'};
const thai=(v:string)=>new Date(v).toLocaleString('zh-CN',{timeZone:'Asia/Bangkok'})+'（泰国时间）';
export default function ProcurementRiskReview({signalId,query,onSaved}:{signalId:string;query:string;onSaved:()=>void}){
 const {user}=useAuth() as {user:{role:string}|null};const allowed=user?.role==='warehouse_admin',scope=controlScope(),resource=signalId+':'+query;const sequence=useRef(0);
 const [record,setRecord]=useState<any>(null),[loaded,setLoaded]=useState(''),[conclusion,setConclusion]=useState('pending'),[reason,setReason]=useState(''),[prepared,setPrepared]=useState<any>(null),[locked,setLocked]=useState(false),[error,setError]=useState(''),[busy,setBusy]=useState(false),[message,setMessage]=useState('');
 async function load(fresh=false){
  const id=++sequence.current,expected=scope;setError('');
  try{const r=await api.get<any>(`/supplier-risk/signals/${signalId}?${query}`);if(id!==sequence.current||controlScope()!==expected)return;
   if(!r.data?.review?.evidence_version)throw Error('复核依据读取不完整，请重新读取');
   const draft=registrationDraft('risk_review',resource),restore=draft&&(!fresh||draft.unknown)?draft:null;
   setRecord(r.data);setLoaded(expected);setPrepared(restore?restore.payload:{expected_evidence_version:r.data.review.evidence_version,expected_latest_review_id:r.data.review.latest_review_id});setConclusion(restore?restore.payload.conclusion:r.data.review.status);setReason(restore?restore.payload.review_reason:'');setLocked(!!restore?.unknown);
   if(restore?.unknown)setMessage('已恢复原复核请求及证据版本，请沿用原请求重试。');
  }catch(e:any){if(id===sequence.current&&controlScope()===expected)setError(e.message||'复核详情读取失败');}
 }
 useEffect(()=>{setRecord(null);setLoaded('');setError('');setMessage('');if(allowed)load();return()=>{sequence.current++;};},[signalId,query,scope,allowed]);
 async function submit(){
  if(!reason.trim()){setError('请填写复核原因');return;}if(!record||loaded!==scope)return;setBusy(true);setError('');
  try{const result=await controlMutation('risk_review',resource,{...prepared,conclusion,review_reason:reason},`/supplier-risk/signals/${signalId}/reviews?${query}`,'POST',scope);
   if(controlScope()===scope){setMessage(result.message||'复核已追加保存');await load(true);onSaved();}
  }catch(e:any){if(controlScope()===scope){setError(e.message);setLocked(!!registrationDraft('risk_review',resource)?.unknown);}}finally{setBusy(false);}
 }
 if(!allowed)return <p>仅仓库管理员可以复核采购线索。</p>;
 return <section aria-label="老板复核" className="border rounded p-3 space-y-3 text-sm min-w-0 break-words"><h3 className="font-semibold">老板复核</h3><p>结论仅对本仓、本月、本规则、当前筛选范围和这一版证据有效。不是采购例外授权，不改金额、不处罚。</p>
 {error&&<p role="alert" className="text-red-600">{error}</p>}{message&&<p role="status">{message}</p>}
 {record&&loaded===scope?<><p className={record.review.stale?'text-amber-800 font-semibold':''}>当前复核：{record.review.message}</p><p>范围：{record.review.scope.month} · 供应商 {record.review.scope.supplier_id??'全部'} · 采购人 {record.review.scope.orderer_id??'全部'} · 币种 {record.review.scope.currency??'分别列出'}</p>
 <details className="break-all"><summary>查看证据版本</summary><p>{record.review.evidence_version}</p><p>上一复核编号 {record.review.latest_review_id||'无'}</p></details>
 <label className="block">复核结论<select aria-label="老板复核结论" className="form-input" value={conclusion} disabled={locked||busy} onChange={e=>setConclusion(e.target.value)}>{Object.entries(labels).map(([k,v])=><option key={k} value={k} disabled={k==='cleared'&&record.state==='unavailable'}>{v}</option>)}</select></label>
 {record.state==='unavailable'&&<p>当前依据不足，不能记为已核实无问题；可记录需跟进并说明待补资料。</p>}
 <label className="block">原因（必填）<textarea aria-label="老板复核原因" className="form-input" value={reason} disabled={locked||busy} onChange={e=>setReason(e.target.value)}/></label>
 <div className="flex flex-wrap gap-2"><ActionGate anyOf={["procurement_risk.save_review"]}><button className="btn-primary" disabled={busy||(!locked&&conclusion==='cleared'&&record.state==='unavailable')} onClick={submit}>保存老板复核</button></ActionGate><button className="btn-secondary" disabled={busy} onClick={()=>load(true)}>重新读取证据</button></div>
 <h4 className="font-semibold">不可覆盖的复核历史（{record.review.history.length}条）</h4>
 {record.review.history.map((h:any)=><article className="border-t pt-2 space-y-1" key={h.id}><p>复核 #{h.id} · {labels[h.conclusion]} · 操作者 #{h.reviewer_id} · {thai(h.created_at)}</p><p>原因：{h.reason}</p><p>规则版本：{h.rule_version}</p><details><summary>查看当时证据快照</summary><pre className="whitespace-pre-wrap break-all text-xs">{JSON.stringify(h.snapshot,null,2)}</pre></details></article>)}
 {!record.review.history.length&&<p>尚无复核记录。</p>}</>:!error&&<p>读取复核依据中</p>}
 </section>;
}

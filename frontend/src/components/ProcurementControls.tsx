"use client";
import {useEffect,useRef,useState} from 'react';
import Link from 'next/link';
import {api} from '@/lib/api';
import {useAuth} from '@/hooks/useAuth';
import {registrationDraft} from '@/lib/registrationRequest';
import {controlScope,controlFields,controlMutation} from '@/lib/procurementControlRequest';
const actionLabels:Record<string,string>={approve:'人工审批通过',reject:'人工审批驳回',receive:'登记实际收货'};
const statuses:Record<string,string>={active:'待使用',used:'已使用',revoked:'已撤销'};
const thai=(v:string)=>v?new Date(v).toLocaleString('zh-CN',{timeZone:'Asia/Bangkok'}):'未记录';
const thaiInput=(v:string)=>v?new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Bangkok',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(new Date(v)).replace(' ','T'):'';
export default function ProcurementControls(){
 const {user}=useAuth() as {user:{role:string;id?:number}|null};const allowed=user?.role==='warehouse_admin',scope=controlScope();const sequence=useRef(0),listSequence=useRef(0),contextSequence=useRef(0);
 const [loaded,setLoaded]=useState(''),[current,setCurrent]=useState<any>(null),[approve,setApprove]=useState(false),[receive,setReceive]=useState(false),[version,setVersion]=useState(''),[why,setWhy]=useState(''),[policyLocked,setPolicyLocked]=useState(false);
 const [error,setError]=useState(''),[message,setMessage]=useState(''),[busy,setBusy]=useState('');
 const [po,setPo]=useState(''),[operator,setOperator]=useState(''),[action,setAction]=useState('receive'),[ctx,setCtx]=useState<any>(null),[expiry,setExpiry]=useState(''),[grantWhy,setGrantWhy]=useState(''),[grantLocked,setGrantLocked]=useState(false);
 const [list,setList]=useState<any[]>([]),[page,setPage]=useState(1),[total,setTotal]=useState(0),[listPo,setListPo]=useState('');
 const [revoke,setRevoke]=useState<any>(null),[revokeWhy,setRevokeWhy]=useState('');
 const resource=()=>`${po}:${action}:${operator}`;
 async function loadExceptions(p=1,selectedPo=listPo){
  const expected=scope,id=++listSequence.current;const r=await api.get<any>(`/supplier-controls/exceptions?page=${p}&page_size=20${selectedPo?'&po_id='+encodeURIComponent(selectedPo):''}`);
  if(controlScope()===expected&&id===listSequence.current){setList(r.data);setTotal(r.total);setPage(p);setListPo(selectedPo);}
 }
 async function loadPolicy(fresh=false){
  const expected=scope,id=++sequence.current;setError('');
  try{const r=await api.get<any>('/supplier-controls/policy');if(controlScope()!==expected||id!==sequence.current)return;
   const draft=registrationDraft('duty_policy','current');const restore=draft&&(!fresh||draft.unknown)?draft:null;
   setCurrent(r);setLoaded(expected);setApprove(restore?restore.payload.no_self_approve:r.no_self_approve);setReceive(restore?restore.payload.no_self_receive:r.no_self_receive);setVersion(restore?restore.payload.expected_version:r.version);setWhy(restore?restore.payload.change_reason:'');setPolicyLocked(!!restore?.unknown);
   if(restore?.unknown)setMessage('已恢复原配置请求，结果待核对。请沿用原参数重试，不能另建请求。');
  }catch(e:any){if(controlScope()===expected)setError(e.message||'配置读取失败');}
 }
 useEffect(()=>{setCurrent(null);setLoaded('');setCtx(null);setList([]);setPo('');setOperator('');setGrantLocked(false);setGrantWhy('');setExpiry('');setPolicyLocked(false);setError('');setMessage('');setRevoke(null);if(allowed){loadPolicy();loadExceptions(1,'').catch(e=>{if(controlScope()===scope)setError(e.message);});}return()=>{sequence.current++;listSequence.current++;contextSequence.current++;};},[scope,allowed]);
 async function savePolicy(){
  if(!why.trim()){setError('请填写配置变更原因');return;}setBusy('policy');setError('');
  try{const r=await controlMutation('duty_policy','current',{no_self_approve:approve,no_self_receive:receive,expected_version:version,change_reason:why},'/supplier-controls/policy','PUT',scope);if(controlScope()===scope){setMessage(r.message||'配置已保存');await loadPolicy(true);}}
  catch(e:any){if(controlScope()===scope){setError(e.message);setPolicyLocked(!!registrationDraft('duty_policy','current')?.unknown);}}finally{setBusy('');}
 }
 async function loadContext(fresh=false){
  setError('');setCtx(null);const expected=scope,id=++contextSequence.current;
  try{if(!/^[1-9]\d*$/.test(po)||!/^[1-9]\d*$/.test(operator))throw Error('请填写本仓采购单编号和操作者账号编号');
   const r=await api.get<any>(`/supplier-controls/orders/${po}/context?action=${action}&operator_id=${operator}`);if(controlScope()!==expected||id!==contextSequence.current)return;controlFields(r);
   const draft=registrationDraft('duty_grant',resource()),restore=draft&&(!fresh||draft.unknown)?draft:null;
   setCtx(r);setGrantLocked(!!restore?.unknown);setExpiry(restore?thaiInput(restore.payload.expires_at):'');setGrantWhy(restore?restore.payload.grant_reason:'');
   if(restore?.unknown)setMessage('已恢复原授权请求，重试使用原版本、到期时间和原因。');
   await loadExceptions(1,po);
  }catch(e:any){if(controlScope()===expected)setError(e.message||'职责上下文读取失败');}
 }
 async function saveGrant(){
  setError('');setBusy('grant');
  try{if(!ctx||ctx.purchase_order_id!==Number(po)||ctx.operator_id!==Number(operator)||ctx.action!==action)throw Error('请先载入当前采购、动作和操作者的上下文');
   const draft=registrationDraft('duty_grant',resource());if(!expiry||!grantWhy.trim())throw Error('请填写明确到期时间和授权原因');
   const payload=draft?.unknown?draft.payload:{po_id:ctx.purchase_order_id,action,operator_id:ctx.operator_id,...controlFields(ctx),expires_at:new Date(expiry+':00+07:00').toISOString(),grant_reason:grantWhy};
   const r=await controlMutation('duty_grant',resource(),payload,'/supplier-controls/exceptions','POST',scope);
   if(controlScope()===scope){setMessage(`一次性例外 #${r.data.id} 已保存；仍须原业务权限。`);setGrantLocked(false);await loadExceptions(1,po);}
  }catch(e:any){if(controlScope()===scope){setError(e.message);setGrantLocked(!!registrationDraft('duty_grant',resource())?.unknown);}}finally{setBusy('');}
 }
 function openRevoke(row:any){try{const draft=registrationDraft('duty_revoke',row.id);setRevoke(row);setRevokeWhy(draft?.payload.revoke_reason||'');}catch(e:any){setError(e.message);}}
 async function revokeGrant(){if(!revokeWhy.trim()){setError('请填写撤销原因');return;}setBusy('revoke');try{await controlMutation('duty_revoke',revoke.id,{revoke_reason:revokeWhy},`/supplier-controls/exceptions/${revoke.id}/revoke`,'POST',scope);if(controlScope()===scope){setRevoke(null);setMessage('授权已撤销');await loadExceptions();}}catch(e:any){if(controlScope()===scope)setError(e.message);}finally{setBusy('');}}
 if(!allowed)return <section className="card p-4"><h1 className="page-title">采购职责与例外</h1><p>仅仓库管理员可以管理。</p></section>;
 return <section className="space-y-4"><div className="flex flex-wrap items-center gap-3"><h1 className="page-title">采购职责与例外</h1><Link href="/suppliers/risk" className="text-blue-600 underline">返回风险看板</Link></div>
 {error&&<p role="alert" className="text-red-600">{error}</p>}{message&&<p role="status" className="text-blue-800">{message}</p>}
 {current&&loaded===scope?<><div className="card p-4 space-y-3 text-sm"><h2 className="font-semibold">本仓职责开关</h2><p>{current.scope}</p><p>当前版本：第{current.revision}版</p>
 <label className="flex gap-2"><input aria-label="采购人不可自批" type="checkbox" checked={approve} disabled={policyLocked||!!busy} onChange={e=>setApprove(e.target.checked)}/>采购人不可自批（人工通过和驳回）</label>
 <label className="flex gap-2"><input aria-label="采购人不可自收" type="checkbox" checked={receive} disabled={policyLocked||!!busy} onChange={e=>setReceive(e.target.checked)}/>采购人不可自收（实际收货登记）</label>
 <label className="block">变更原因<textarea aria-label="职责配置变更原因" className="form-input" value={why} disabled={policyLocked} onChange={e=>setWhy(e.target.value)}/></label>
 <div className="flex flex-wrap gap-2"><button className="btn-primary" disabled={!!busy} onClick={savePolicy}>保存职责配置</button><button className="btn-secondary" disabled={!!busy} onClick={()=>loadPolicy(true)}>重新读取配置</button></div></div>
 <div className="card p-4 space-y-3 text-sm"><h2 className="font-semibold">明确授权一次例外</h2><p>老板本人也不天然豁免。例外绑定采购、动作、操作者、配置和业务版本；成功一次、到期、撤销或依据变化后不能再用。复核结论不是例外。</p>
 <div className="grid gap-3 sm:grid-cols-2"><label>采购单编号<input aria-label="例外采购单编号" className="form-input" type="number" min="1" value={po} disabled={grantLocked} onChange={e=>setPo(e.target.value)}/></label><label>操作者账号编号<input aria-label="例外操作者编号" className="form-input" type="number" min="1" value={operator} disabled={grantLocked} onChange={e=>setOperator(e.target.value)}/></label>
 <label>动作<select aria-label="例外动作" className="form-input" value={action} disabled={grantLocked} onChange={e=>setAction(e.target.value)}>{Object.entries(actionLabels).map(([k,v])=><option key={k} value={k}>{v}</option>)}</select></label></div>
 <button className="btn-secondary" disabled={!!busy} onClick={()=>loadContext(true)}>载入职责上下文</button>
 {ctx&&<div className="space-y-2"><p>采购 {ctx.order_number} · 原采购人 #{ctx.creator_id??'未知'} · 指定操作者 #{ctx.operator_id} · {actionLabels[ctx.action]}</p><p>{ctx.unknown_creator?'原采购人未知，不能授权':ctx.needs_exception?'当前需要明确例外':'开关未启用或不是本人，无需本人例外'}</p><details className="break-all"><summary>查看绑定版本</summary><p>配置 {ctx.policy_version}</p><p>业务 {ctx.business_version}</p></details>
 <label className="block">到期时间（泰国时间，必填）<input aria-label="例外到期时间" className="form-input" type="datetime-local" value={expiry} disabled={grantLocked} onChange={e=>setExpiry(e.target.value)}/></label><label className="block">授权原因<textarea aria-label="例外授权原因" className="form-input" value={grantWhy} disabled={grantLocked} onChange={e=>setGrantWhy(e.target.value)}/></label><button className="btn-primary" disabled={!!busy||(!grantLocked&&(ctx.unknown_creator||!ctx.needs_exception))} onClick={saveGrant}>授权一次例外</button></div>}</div>
 <div className="card p-4 space-y-3 text-sm"><h2 className="font-semibold">例外授权记录</h2><p>{listPo?`当前采购 #${listPo}`:'本仓全部采购'} · 共{total}条</p><button className="btn-secondary" onClick={()=>loadExceptions(1,'').catch(e=>{if(controlScope()===scope)setError(e.message);})}>查看全部授权</button>
 {list.map(row=><article className="border rounded p-3 space-y-1 break-words" key={row.id}><p>例外 #{row.id} · 采购 #{row.purchase_order_id} · {actionLabels[row.action]} · 操作者 #{row.operator_id}</p><p>{statuses[row.status]}{row.status==='active'&&!row.effective?'（绑定已失效，不可使用）':''} · 到期 {thai(row.expires_at)}</p><p>授权人 #{row.granted_by} · {thai(row.created_at)}</p><p>授权原因：{row.reason}</p>{row.revoke_reason&&<p>撤销人 #{row.revoked_by} · {thai(row.revoked_at)} · 原因 {row.revoke_reason}</p>}{row.status==='active'&&<button className="text-red-700 underline" onClick={()=>openRevoke(row)}>撤销例外 #{row.id}</button>}</article>)}
 {!list.length&&<p>本仓当前筛选暂无授权。</p>}<div className="flex gap-2"><button className="btn-secondary" disabled={page<=1} onClick={()=>loadExceptions(page-1).catch(e=>{if(controlScope()===scope)setError(e.message);})}>上一页</button><span>第{page}页</span><button className="btn-secondary" disabled={page*20>=total} onClick={()=>loadExceptions(page+1).catch(e=>{if(controlScope()===scope)setError(e.message);})}>下一页</button></div>
 {revoke&&<div role="dialog" aria-label="撤销一次性例外" className="border rounded p-3 space-y-2"><p>撤销例外 #{revoke.id}，不会撤回已执行业务。</p><textarea aria-label="例外撤销原因" className="form-input" value={revokeWhy} onChange={e=>setRevokeWhy(e.target.value)}/><div className="flex gap-2"><button className="btn-secondary" disabled={!!busy} onClick={()=>setRevoke(null)}>取消</button><button className="btn-primary" disabled={!!busy} onClick={revokeGrant}>确认撤销例外</button></div></div>}</div></>:!error&&<p>读取中</p>}
 </section>;
}

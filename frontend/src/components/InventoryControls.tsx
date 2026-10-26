'use client';
import {useEffect,useRef,useState} from 'react';
import {api} from '@/lib/api';
import {inventoryScope,submitInventory} from '@/lib/inventoryRequest';
import {registrationDraft} from '@/lib/registrationRequest';

const thai=(v:string)=>new Date(v).toLocaleString('zh-CN',{timeZone:'Asia/Bangkok'});
export default function InventoryControls({account,owner,onSaved}:{account:any;owner:boolean;onSaved:(message:string)=>void}){
  const scope=inventoryScope(),serial=useRef(0),formSerial=useRef(0);
  const [data,setData]=useState<any>(null),[loaded,setLoaded]=useState(''),[page,setPage]=useState(1);
  const [error,setError]=useState(''),[form,setForm]=useState<any>(null),[busy,setBusy]=useState(false),[revision,setRevision]=useState(0);
  useEffect(()=>{setPage(1);setForm(null);setBusy(false);formSerial.current++;},[scope,account.id,owner]);
  useEffect(()=>{const id=++serial.current;setData(null);setLoaded('');setError('');
    Promise.all([api.get<any>(`/inventory/counts?account_id=${account.id}&page=${page}&page_size=20`),api.get<any>(`/inventory/accounts/${account.id}/controls`)]).then(([counts,controls])=>{
      if(id===serial.current&&inventoryScope()===scope){setData({counts,controls});setLoaded(scope);}
    }).catch(e=>{if(id===serial.current&&inventoryScope()===scope)setError(e.message||'盘点与提醒设置读取失败');});
    return()=>{serial.current++;};
  },[scope,account.id,page,revision]);
  async function open(kind:string,count?:any,decision?:string){
    const id=++formSerial.current,expected=scope;setError('');
    try{
      let value:any={kind,scope:expected,reason:'',amount:'',locked:false};
      if(kind==='count'){
        const current=await api.get<any>(`/inventory/accounts/${account.id}`);
        value={...value,account:current.account,resource:`/inventory/accounts/${account.id}/counts`};
      }else if(kind==='controls')value={...value,controls:data.controls,minimum:data.controls.minimum_quantity??'',ratio:data.controls.receipt_usage_ratio??'',note:data.controls.stockpiling_note,resource:`/inventory/accounts/${account.id}/controls`};
      else value={...value,count,decision,resource:`/inventory/counts/${count.id}/review`};
      if(id!==formSerial.current||inventoryScope()!==expected)return;
      const draft=registrationDraft('inventory',value.resource);
      setForm(draft?.unknown?{...value,locked:true,payload:draft.payload}:value);
    }catch(e:any){if(id===formSerial.current&&inventoryScope()===expected)setError(e.message||'当前库存读取失败');}
  }
  async function save(){
    if(!form||busy)return;const original=form,expected=form.scope;setError('');
    try{
      if(!form.locked&&!form.reason.trim())throw Error('请填写盘点、审核或配置原因');
      const payload=form.locked?form.payload:form.kind==='count'?{counted_quantity:form.amount,expected_version:form.account.version,count_reason:form.reason}:
        form.kind==='controls'?{minimum_quantity:form.minimum.trim()||null,receipt_usage_ratio:form.ratio.trim()||null,stockpiling_note:form.note,expected_version:form.controls.version,change_reason:form.reason}:
        {decision:form.decision,expected_count_version:form.count.version,review_reason:form.reason};
      setBusy(true);const r=await submitInventory(form.resource,payload,expected);
      if(inventoryScope()!==expected)return;setForm(null);setRevision(v=>v+1);onSaved(r.message);
    }catch(e:any){if(inventoryScope()===expected){setError(e.message||'盘点操作失败');const d=registrationDraft('inventory',original.resource);if(d?.unknown)setForm({...original,locked:true,payload:d.payload});}}
    finally{if(inventoryScope()===expected)setBusy(false);}
  }
  const visible=loaded===scope?data:null;
  const update=(values:any)=>setForm((old:any)=>({...old,...values}));
  return <section className="border-t pt-4 space-y-3 min-w-0"><h3 className="font-semibold">盘点与安全库存 · {account.sku.code} / {account.base_unit}</h3>
    <p className="text-sm">实盘先登记，老板填审核原因后才生成调整流水。登记后有任何库存变动，须驳回旧盘点并重新盘，不直接覆盖余额。</p>
    {error&&<p role="alert" className="text-red-600 break-words">{error}</p>}
    {visible?<><p className="text-sm">安全下限：{visible.controls.minimum_quantity??'未配置'} · 收货/净领用比阈值：{visible.controls.receipt_usage_ratio??'未配置'}。备货说明：{visible.controls.stockpiling_note||'未填写'}</p>
      <div className="flex flex-wrap gap-2"><button className="btn-secondary" disabled={!account.opening_confirmed} onClick={()=>open('count')}>登记本次实盘</button>{owner&&<button className="btn-secondary" onClick={()=>open('controls')}>设置安全库存与用量阈值</button>}</div>
      {visible.counts.data.map((c:any)=><article className="border rounded p-3 space-y-2 text-sm break-words" key={c.id}><p>盘点 #{c.id} · {c.status==='pending'?'待审核':c.status==='approved'?'已审核并调整':'已驳回'} · 账面{c.book_quantity} · 实盘{c.counted_quantity} · 差异{c.difference} {account.unit_label}</p><p>登记人 {c.creator_name} · {thai(c.counted_at)}（泰国时间） · 原因：{c.reason}</p>{c.reviewed_at&&<p>审核人 {c.reviewer_name} · {thai(c.reviewed_at)} · 审核原因：{c.review_reason} · 调整流水 #{c.adjustment_id??'无'}</p>}{owner&&c.status==='pending'&&<div className="flex flex-wrap gap-3"><button className="btn-primary" onClick={()=>open('review',c,'approve')}>审核调整 #{c.id}</button><button className="btn-secondary" onClick={()=>open('review',c,'reject')}>驳回盘点 #{c.id}</button></div>}</article>)}
      {!visible.counts.data.length&&<p>暂无盘点记录；未从历史数据补造。</p>}<div className="flex gap-3"><button className="btn-secondary" disabled={page<=1} onClick={()=>setPage(v=>v-1)}>盘点上一页</button><span>共{visible.counts.total}条</span><button className="btn-secondary" disabled={page*20>=visible.counts.total} onClick={()=>setPage(v=>v+1)}>盘点下一页</button></div>
    </>:!error&&<p>盘点读取中</p>}
    {form&&form.scope===scope&&<div className="modal-overlay z-[80]" onClick={()=>!busy&&setForm(null)}><div role="dialog" aria-label="盘点与提醒登记" className="bg-white rounded-xl p-5 w-[560px] max-w-[95vw] max-h-[85vh] overflow-auto space-y-3" onClick={e=>e.stopPropagation()}>
      <h3 className="font-semibold">{form.locked?'核对原盘点/配置请求':form.kind==='count'?'登记本次实盘':form.kind==='controls'?'安全库存与用量阈值':form.decision==='approve'?'审核盘点并生成调整':'驳回盘点'}</h3>{error&&<p role="alert" className="text-red-600 break-words">{error}</p>}
      {form.locked?<div className="space-y-2"><p className="text-amber-800">原请求结果待核对，内容与编号已保留。请沿用原请求核对，不能另记一次。</p><p>原实盘数量：{form.payload.counted_quantity??'按原审核/配置'}</p><p>原原因：{form.payload.count_reason||form.payload.review_reason||form.payload.change_reason}</p></div>:<>
        {form.kind==='count'&&<><p>当前账面{form.account.available_quantity} {account.unit_label}；保存账面版本、实盘数量和登记时点，审核前不改库存。</p><label className="block">实盘数量<input aria-label="实盘数量" className="form-input" inputMode="decimal" value={form.amount} onChange={e=>update({amount:e.target.value})}/></label></>}
        {form.kind==='controls'&&<><label className="block">安全库存下限（空为未配置）<input aria-label="安全库存下限" className="form-input" inputMode="decimal" value={form.minimum} onChange={e=>update({minimum:e.target.value})}/></label><label className="block">收货/净领用比阈值（大于1，空为未配置）<input aria-label="收货用量比阈值" className="form-input" inputMode="decimal" value={form.ratio} onChange={e=>update({ratio:e.target.value})}/></label><label className="block">备货计划或核实说明<textarea aria-label="备货说明" className="form-input" value={form.note} maxLength={1000} onChange={e=>update({note:e.target.value})}/></label><p className="text-sm">仅核实线索，不把买多认定回扣。提醒按各仓SKU基本单位，不跨单位或币种相加。</p></>}
        {form.kind==='review'&&<p>盘点 #{form.count.id}：原账面{form.count.book_quantity}，实盘{form.count.counted_quantity}，差异{form.count.difference}。{form.decision==='approve'?'将新增调整流水，库存变过须重新盘。':'只留驳回记录，库存不变。'}</p>}
        <label className="block">原因（必填）<textarea aria-label="盘点或审核原因" className="form-input" value={form.reason} maxLength={1000} onChange={e=>update({reason:e.target.value})}/></label>
      </>}
      <div className="flex flex-wrap gap-3 justify-end sticky bottom-0 bg-white pt-3"><button className="btn-secondary" disabled={busy} onClick={()=>setForm(null)}>取消盘点操作</button><button className="btn-primary" disabled={busy} onClick={save}>{busy?'保存中...':form.locked?'沿用原盘点请求重试':'确认盘点操作'}</button></div>
    </div></div>}
  </section>;
}

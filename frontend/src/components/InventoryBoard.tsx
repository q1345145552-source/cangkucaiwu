'use client';
import {useEffect,useRef,useState} from 'react';
import Link from 'next/link';
import {api} from '@/lib/api';
import {useAuth} from '@/hooks/useAuth';
import {useMenuPermission} from '@/hooks/useMenuPermission';
import {registrationDraft} from '@/lib/registrationRequest';
import {inventoryScope,pendingInventoryRequests,submitInventory} from '@/lib/inventoryRequest';

const kinds:Record<string,string>={opening:'确认真实期初',issue:'领用出库',return:'退回原领用',receipt:'采购收货入库',reversal:'反向冲销',reverse:'反向冲销',resolve:'核对收货入库',policy:'库存策略',retry:'核对原登记结果'};
const thai=(v:string)=>new Date(v).toLocaleString('zh-CN',{timeZone:'Asia/Bangkok'});
function startToday(){const p=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Bangkok',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date());return ['year','month','day'].map(k=>p.find(x=>x.type===k)!.value).join('-')+'T00:00';}

export default function InventoryBoard(){
  const {user}=useAuth() as {user:{id:number;role:string}|null};
  const permission=useMenuPermission('inventory'),canViewSource=useMenuPermission('suppliers');
  const allowed=!!user&&['warehouse_admin','supervisor','staff'].includes(user.role)&&permission,owner=user?.role==='warehouse_admin';
  const scope=inventoryScope(),sequence=useRef(0),detailSequence=useRef(0),formSequence=useRef(0);
  const [loaded,setLoaded]=useState(''),[data,setData]=useState<any>(null),[catalog,setCatalog]=useState<any[]>([]),[pending,setPending]=useState<any>(null);
  const [page,setPage]=useState(1),[pendingPage,setPendingPage]=useState(1),[filter,setFilter]=useState(''),[applied,setApplied]=useState('');
  const [error,setError]=useState(''),[message,setMessage]=useState(''),[detail,setDetail]=useState<any>(null),[detailLoaded,setDetailLoaded]=useState(''),[detailPage,setDetailPage]=useState(1);
  const [form,setForm]=useState<any>(null),[busy,setBusy]=useState(false),[drafts,setDrafts]=useState<any[]>([]),[draftScope,setDraftScope]=useState(''),[revision,setRevision]=useState(0);
  const query=new URLSearchParams({page:String(page),page_size:'20',...(applied?{sku_id:applied}:{})}).toString();
  function readDrafts(){try{setDrafts(pendingInventoryRequests());setDraftScope(scope);}catch(e:any){setDrafts([]);setDraftScope('');setError(e.message);}}
  useEffect(()=>{setFilter('');setApplied('');setPage(1);setPendingPage(1);setCatalog([]);setPending(null);setDrafts([]);setMessage('');},[scope]);
  useEffect(()=>{
    const id=++sequence.current;setData(null);setLoaded('');setError('');setDetail(null);setForm(null);detailSequence.current++;formSequence.current++;
    if(!allowed){setCatalog([]);setPending(null);setDrafts([]);return;}
    readDrafts();
    Promise.all([api.get<any>(`/inventory?${query}`),api.get<any>('/inventory/catalog'),api.get<any>(`/inventory/pending-receipts?page=${pendingPage}&page_size=20`)]).then(([a,b,c])=>{
      if(id===sequence.current&&inventoryScope()===scope){setData(a);setCatalog(b.data);setPending(c);setLoaded(scope);}
    }).catch(e=>{if(id===sequence.current&&inventoryScope()===scope)setError(e.message||'库存读取失败，未将失败显示为零');});
    return()=>{sequence.current++;};
  },[scope,allowed,owner,query,pendingPage,revision]);

  async function showDetail(id:number,p=1){
    const seq=++detailSequence.current,expected=scope;setError('');setDetail(null);setDetailLoaded('');
    try{const r=await api.get<any>(`/inventory/accounts/${id}?page=${p}&page_size=20`);if(seq===detailSequence.current&&inventoryScope()===expected){setDetail(r);setDetailLoaded(expected);setDetailPage(p);}}
    catch(e:any){if(seq===detailSequence.current&&inventoryScope()===expected)setError(e.message||'库存流水读取失败');}
  }
  function restore(resource:string){
    const draft=registrationDraft('inventory',resource);
    if(!draft)throw Error('原请求已不存在，请重新读取库存核对');
    setForm({kind:'retry',resource,scope,payload:draft.payload,locked:true,reason:'',amount:''});
  }
  async function openForm(kind:string,account?:any,movement?:any,source?:any){
    const seq=++formSequence.current,expected=scope;setError('');setMessage('');
    try{
      let value:any={kind,scope:expected,amount:'',reason:'',locked:false};
      if(kind==='opening'){
        if(account)account=(await api.get<any>(`/inventory/accounts/${account.id}`)).account;
        const options=(await api.get<any>('/inventory/catalog')).data;
        value={...value,options,sku_id:String(account?.sku_id||options[0]?.id||''),account:account||null,at:startToday(),confirmed:false};
        const chosen=options.find((x:any)=>x.id===Number(value.sku_id));
        value.unit=account?.base_unit||chosen?.base_unit||'';
        value.version=account?.version||chosen?.opening_target.version;
        value.resource=`/inventory/openings?sku_id=${value.sku_id}&base_unit=${value.unit}`;
      }else if(kind==='policy'){
        const policy=await api.get<any>('/inventory/policy');value={...value,policy,method:policy.valuation_method,resource:'/inventory/policy'};
      }else if(kind==='resolve'){
        value={...value,source,options:(await api.get<any>('/inventory/catalog')).data,sku_id:'',factor:'',resource:`/inventory/pending-receipts/${source.id}/resolve`};
      }else{
        const fresh=await api.get<any>(`/inventory/accounts/${account.id}`);
        value={...value,account:fresh.account,movement,resource:kind==='issue'?`/inventory/accounts/${account.id}/issues`:`/inventory/movements/${movement.id}/${kind==='return'?'returns':'reverse'}`};
      }
      if(seq!==formSequence.current||inventoryScope()!==expected)return;
      const draft=registrationDraft('inventory',value.resource);
      if(draft?.unknown){restore(value.resource);return;}
      setForm(value);
    }catch(e:any){if(seq===formSequence.current&&inventoryScope()===expected)setError(e.message||'当前库存上下文读取失败');}
  }
  function update(values:any){setForm((old:any)=>({...old,...values}));}
  function selectOpening(id:string){
    const chosen=form.options.find((x:any)=>x.id===Number(id));if(!chosen)return;
    update({sku_id:id,unit:chosen.base_unit,version:chosen.opening_target.version,resource:`/inventory/openings?sku_id=${id}&base_unit=${chosen.base_unit}`});
  }
  async function save(){
    if(!form||busy)return;
    const original=form,expected=form.scope;setError('');
    try{
      let payload:any;
      if(form.locked)payload=form.payload;
      else{
        if(!form.reason.trim())throw Error('请填写原因或用途');
        if(form.kind==='opening'){
          if(!form.sku_id||!form.confirmed)throw Error('请选择SKU并明确确认真实期初，不能从采购历史推算');
          if(!form.at)throw Error('请填写真实期初基准时间');
          payload={sku_id:Number(form.sku_id),base_unit:form.unit,opening_quantity:form.amount,occurred_at:new Date(form.at+':00+07:00').toISOString(),confirmed:true,expected_version:form.version,change_reason:form.reason};
        }else if(form.kind==='issue')payload={issued_quantity:form.amount,expected_version:form.account.version,purpose:form.reason};
        else if(form.kind==='return')payload={returned_quantity:form.amount,expected_version:form.account.version,return_reason:form.reason};
        else if(form.kind==='reverse')payload={expected_version:form.account.version,reverse_reason:form.reason};
        else if(form.kind==='resolve'){
          if(!form.sku_id)throw Error('请选择按原始证据核实的SKU');
          payload={sku_id:Number(form.sku_id),expected_sku_version:form.options.find((s:any)=>s.id===Number(form.sku_id)).version,base_unit_factor:form.factor,expected_source_fingerprint:form.source.source_fingerprint,confirmation_reason:form.reason};
        }else payload={valuation_method:form.method,expected_version:form.policy.version,change_reason:form.reason};
      }
      setBusy(true);const r=await submitInventory(form.resource,payload,expected);
      if(inventoryScope()!==expected)return;
      setForm(null);setDetail(null);setMessage(r.message||'库存登记成功');readDrafts();setRevision(v=>v+1);
    }catch(e:any){if(inventoryScope()===expected){setError(e.message||'库存登记失败');const d=registrationDraft('inventory',original.resource);if(d?.unknown)setForm({...original,locked:true,payload:d.payload});readDrafts();}}
    finally{setBusy(false);}
  }
  if(!allowed)return <section className="card p-4"><h1 className="page-title">耗材库存</h1><p>无此操作权限，或权限清单尚未加载。仅当前仓有库存权限的管理账号可访问。</p></section>;
  const visible=loaded===scope?data:null,visibleDetail=detailLoaded===scope?detail:null,visibleCatalog=loaded===scope?catalog:[],visibleDrafts=draftScope===scope?drafts:[];
  return <section className="space-y-4 min-w-0"><div className="flex flex-wrap gap-3 items-center"><h1 className="page-title">耗材库存</h1>{canViewSource&&<Link href="/suppliers" className="text-blue-700 underline">供应商管理</Link>}</div>
    <p className="text-sm">各仓、各SKU、各基本单位分开。真实期初未确认时，不把已知收货当作当前库存；仅记录耗材数量，不新增资金支出或费用。金额待配置。</p>
    {error&&<p role="alert" className="text-red-600 break-words">{error}</p>}{message&&<p role="status" className="text-blue-800">{message}</p>}
    {visibleDrafts.length>0&&<div className="card p-4 space-y-2"><h2 className="font-semibold">待核对的原登记</h2><p className="text-sm">可能已经保存。请沿用原请求核对，不能改内容另记一笔。</p>{visibleDrafts.map(d=><button key={d.resource} className="btn-secondary mr-2 mb-2" onClick={()=>restore(d.resource)}>沿用原请求核对 · {d.payload.sku_id?`SKU #${d.payload.sku_id}`:'库存记录'} · {d.payload.opening_quantity||d.payload.issued_quantity||d.payload.returned_quantity||'原操作'}</button>)}</div>}
    <form className="card p-4 flex flex-wrap gap-3 items-end" onSubmit={e=>{e.preventDefault();setPage(1);setApplied(filter);}}><label>SKU<select aria-label="库存SKU筛选" className="form-input" value={filter} onChange={e=>setFilter(e.target.value)}><option value="">本仓全部</option>{visibleCatalog.map(s=><option key={s.id} value={s.id}>{s.code} · {s.name}</option>)}</select></label><button className="btn-primary">查询库存</button>{owner&&<><button type="button" className="btn-secondary" onClick={()=>openForm('opening')}>确认真实期初</button><button type="button" className="btn-secondary" onClick={()=>openForm('policy')}>库存策略</button></>}</form>
    {visible?<><p className="text-sm">{visible.policy.note}</p><div className="grid gap-3 lg:grid-cols-2">{visible.data.map((a:any)=><article key={a.id} className="card p-4 space-y-2 min-w-0 break-words"><h2 className="font-semibold">{a.sku.code} · {a.sku.name}</h2><p>基本单位：{a.unit_label}（{a.base_unit}）</p><p className="font-semibold">可用数量：{a.available_quantity===null?'待确认真实期初':a.available_quantity}</p>{a.available_quantity===null&&<p>已知变动：{a.recorded_quantity} {a.unit_label}（不是完整现存量）</p>}<p className="text-sm text-gray-600">{a.note} · 金额：待配置</p><div className="flex flex-wrap gap-2"><button className="btn-secondary" onClick={()=>showDetail(a.id)}>查看流水 · {a.sku.code} / {a.base_unit}</button>{a.opening_confirmed?<button className="btn-primary" onClick={()=>openForm('issue',a)}>领用 · {a.sku.code} / {a.base_unit}</button>:owner&&<button className="btn-primary" onClick={()=>openForm('opening',a)}>确认期初 · {a.sku.code} / {a.base_unit}</button>}</div></article>)}</div>{!visible.data.length&&<p>本仓当前筛选暂无库存台账；不会从历史采购生成期初。</p>}<div className="flex flex-wrap gap-3"><button className="btn-secondary" disabled={page<=1} onClick={()=>setPage(p=>p-1)}>库存上一页</button><span>第{page}页 · 共{visible.total}项（不同单位不混加）</span><button className="btn-secondary" disabled={page*20>=visible.total} onClick={()=>setPage(p=>p+1)}>库存下一页</button></div></>:!error&&<p>库存读取中</p>}
    {visible&&pending&&<div className="card p-4 space-y-3"><h2 className="font-semibold">收货待核对（{pending.total}行）</h2><p className="text-sm">缺少原冻结SKU或单位换算时保留来源，未猜配、未算入库存。这里只列本功能上线后的新收货，历史收货不补录。</p>{pending.data.map((p:any)=><article key={p.id} className="border rounded p-3 space-y-2 text-sm break-words"><p>收货批次 #{p.receipt_event_id} · 采购 #{p.purchase_order_id} · {p.source_snapshot.item.product_name} · 本次{p.original_quantity}{p.original_unit||'原单位未知'}</p><p>{p.pending_reason}</p>{owner&&<button className="btn-secondary" onClick={()=>openForm('resolve',undefined,undefined,p)}>按证据核对入库 #{p.id}</button>}</article>)}{!pending.data.length&&<p>暂无待核对收货。</p>}<div className="flex gap-2"><button className="btn-secondary" disabled={pendingPage<=1} onClick={()=>setPendingPage(p=>p-1)}>待核对上一页</button><button className="btn-secondary" disabled={pendingPage*20>=pending.total} onClick={()=>setPendingPage(p=>p+1)}>待核对下一页</button></div></div>}
    {visibleDetail&&<div className="card p-4 space-y-3 min-w-0"><div className="flex flex-wrap gap-3 justify-between"><h2 className="font-semibold">库存流水 · {visibleDetail.account.sku.code} / {visibleDetail.account.base_unit}</h2><button className="btn-secondary" onClick={()=>{detailSequence.current++;setDetail(null);}}>关闭库存流水</button></div><p className="text-xs text-gray-600">{visibleDetail.balance_after_basis}</p>{visibleDetail.data.map((m:any)=><article key={m.id} className="border rounded p-3 space-y-2 text-sm break-words"><p className="font-semibold">流水 #{m.id} · {kinds[m.kind]} · {m.quantity} {visibleDetail.account.unit_label} · {m.status==='reversed'?'已冲销，原流水保留':'有效'}</p><p>发生 {thai(m.occurred_at)} · 操作人 {m.operator_name} · 登记 {thai(m.created_at)}（泰国时间）</p><p>原因：{m.reason} · 登记后已知累计 {m.balance_after} · 成本金额：待配置</p>{m.reference_id&&<p>关联原领用 #{m.reference_id}</p>}{m.reverses_id&&<p>冲销原流水 #{m.reverses_id}</p>}{m.source_type==='purchase_receipt'&&<p>原收货批次 #{m.source_id} · 采购 #{m.source_snapshot.purchase_order_id} · {canViewSource?<Link href={`/suppliers/purchase-orders/${m.source_snapshot.purchase_order_id}`} className="text-blue-700 underline">查看原采购</Link>:'原采购读取另需供应商权限'}</p>}<div className="flex flex-wrap gap-2">{m.kind==='issue'&&m.status==='active'&&<button className="btn-secondary" onClick={()=>openForm('return',visibleDetail.account,m)}>退回领用 #{m.id}</button>}{owner&&m.status==='active'&&['issue','receipt','return'].includes(m.kind)&&<button className="text-red-700 underline" onClick={()=>openForm('reverse',visibleDetail.account,m)}>冲销流水 #{m.id}</button>}</div></article>)}<div className="flex gap-3"><button className="btn-secondary" disabled={detailPage<=1} onClick={()=>showDetail(visibleDetail.account.id,detailPage-1)}>流水上一页</button><span>共{visibleDetail.total}条</span><button className="btn-secondary" disabled={detailPage*20>=visibleDetail.total} onClick={()=>showDetail(visibleDetail.account.id,detailPage+1)}>流水下一页</button></div></div>}
    {form&&form.scope===scope&&<div className="modal-overlay z-[70]" onClick={()=>!busy&&setForm(null)}><div role="dialog" aria-label={kinds[form.kind]} className="bg-white rounded-xl p-5 w-[560px] max-w-[95vw] max-h-[85vh] overflow-auto space-y-3" onClick={e=>e.stopPropagation()}><h2 className="font-semibold">{kinds[form.kind]}</h2>{error&&<p role="alert" className="text-red-600 break-words">{error}</p>}
      {form.locked?<div className="space-y-2 text-sm"><p className="text-amber-800">原登记结果待核对，原内容和编号已保留。请沿用原请求重试，不重复登记。</p><p>原数量：{form.payload.opening_quantity||form.payload.issued_quantity||form.payload.returned_quantity||form.payload.base_unit_factor||'按原操作'}</p><p>原原因：{form.payload.change_reason||form.payload.purpose||form.payload.return_reason||form.payload.reverse_reason||form.payload.confirmation_reason}</p></div>:<>
        {form.kind==='opening'&&<><p className="text-sm">仅录入真实核实的期初。基准时间不得晚于首笔库存变动；确认后不能覆盖修改，后续差异走盘点调整。</p><label className="block">SKU<select aria-label="期初SKU" className="form-input" value={form.sku_id} disabled={!!form.account} onChange={e=>selectOpening(e.target.value)}>{form.options.map((s:any)=><option key={s.id} value={s.id}>{s.code} · {s.name}</option>)}</select></label><p>基本单位：{form.unit}（独立台账，不自动换算）</p><label className="block">真实期初基准时间（泰国时间）<input aria-label="期初基准时间" className="form-input" type="datetime-local" value={form.at} onChange={e=>update({at:e.target.value})}/></label><label className="flex gap-2"><input aria-label="明确确认真实期初" type="checkbox" checked={form.confirmed} onChange={e=>update({confirmed:e.target.checked})}/>我已核实真实期初，不从采购历史推算</label></>}
        {['issue','return','reverse'].includes(form.kind)&&<p className="text-sm">{form.account.sku.code} · 基本单位 {form.account.base_unit} · 当前可用 {form.account.available_quantity??'期初未确认'}。{form.kind==='reverse'?'将新增反向流水并保留原记录，不撤销采购实收或资金。':'发生时间按本次保存记录，不回写历史。'}</p>}
        {['opening','issue','return'].includes(form.kind)&&<label className="block">数量<input aria-label="库存登记数量" className="form-input" type="text" inputMode="decimal" value={form.amount} onChange={e=>update({amount:e.target.value})}/></label>}
        {form.kind==='resolve'&&<><p className="text-sm">本次实际收到{form.source.original_quantity}{form.source.original_unit||'原单位未知'}。请按原始证据明确选择SKU和基本单位换算，不猜配或覆盖采购快照。</p><label className="block">核实后的SKU<select aria-label="核对收货SKU" className="form-input" value={form.sku_id} onChange={e=>update({sku_id:e.target.value})}><option value="">请选择</option>{form.options.map((s:any)=><option key={s.id} value={s.id}>{s.code} · {s.name} / {s.base_unit}</option>)}</select></label><label className="block">每原单位等于多少基本单位<input aria-label="核实基本单位换算" className="form-input" type="text" inputMode="decimal" value={form.factor} onChange={e=>update({factor:e.target.value})}/></label></>}
        {form.kind==='policy'&&<><p className="text-sm">本轮尚未配置FIFO/均价和真实入库成本。两种模式均仅记录数量，金额留空，不影响资金支出。</p><select aria-label="库存计价状态" className="form-input" value={form.method} onChange={e=>update({method:e.target.value})}><option value="unconfigured">计价待配置</option><option value="quantity_only">明确仅数量台账</option></select></>}
        <label className="block">原因或用途（必填）<textarea aria-label="库存登记原因" className="form-input" value={form.reason} onChange={e=>update({reason:e.target.value})} maxLength={1000}/></label>
      </>}
      <div className="flex flex-wrap gap-3 justify-end sticky bottom-0 bg-white pt-3"><button className="btn-secondary" disabled={busy} onClick={()=>setForm(null)}>取消库存登记</button><button className="btn-primary" disabled={busy} onClick={save}>{busy?'登记中...':form.locked?'沿用原请求重试':'确认库存登记'}</button></div>
    </div></div>}
  </section>;
}

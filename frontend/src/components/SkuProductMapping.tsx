"use client";
import ActionGate from "@/components/permissions/ActionGate";
import { useEffect,useState,useRef } from "react";
import { api,warehouseRequestHeaders } from "@/lib/api";
import { registrationDraft,submitRegistration } from "@/lib/registrationRequest";
import StructuredSpecifications, { SpecificationSummary } from "@/components/StructuredSpecifications";
import { specDraft,readSpecDraft,type SpecNode } from "@/lib/specifications";

export default function SkuProductMapping({productId,canEdit,onClose,onDone}:{productId:number;canEdit:boolean;onClose:()=>void;onDone:()=>void}) {
 const [data,setData]=useState<any>(null),[skus,setSkus]=useState<any[]>([]),[selected,setSelected]=useState(''),[attrs,setAttrs]=useState<SpecNode[]>([]),[factor,setFactor]=useState(''),[reason,setReason]=useState('');
 const [error,setError]=useState(''),[busy,setBusy]=useState(false),[pending,setPending]=useState<any>(null),[history,setHistory]=useState<any[]>([]);
 const scope=JSON.stringify(warehouseRequestHeaders()),sequence=useRef(0),liveProduct=useRef(productId),liveScope=useRef(scope),saving=useRef(false);
 liveProduct.current=productId;liveScope.current=scope;
 useEffect(()=>{let current=true;setData(null);setError('');setPending(null);setSelected('');setHistory([]);setSkus([]);setAttrs([]);setFactor('');setReason('');++sequence.current;
  try{const draft=registrationDraft('sku_mapping',productId);if(draft?.unknown)setPending(draft);}catch(e:any){setError(e.message);}
  Promise.all([api.get<any>(`/sku-catalog/products/${productId}/candidates`),api.get<any>('/sku-catalog')]).then(([p,s])=>{
   if(current&&scope===JSON.stringify(warehouseRequestHeaders())){setData(p);setSkus(s.data);setAttrs(specDraft(p.catalog_attributes));}
  }).catch(e=>{if(current&&scope===JSON.stringify(warehouseRequestHeaders()))setError(e.message);});return()=>{current=false;};
 },[productId,scope]);
 async function find(){const expected=scope,selectedProduct=productId,requestId=++sequence.current;try{setError('');const parsed=readSpecDraft(attrs);const q=parsed?'?confirmed_attributes='+encodeURIComponent(JSON.stringify(parsed)):'';const p=await api.get<any>(`/sku-catalog/products/${productId}/candidates${q}`);if(requestId===sequence.current&&expected===liveScope.current&&selectedProduct===liveProduct.current&&scope===JSON.stringify(warehouseRequestHeaders()))setData(p);}catch(e:any){if(requestId===sequence.current&&expected===liveScope.current&&selectedProduct===liveProduct.current)setError(e.message||'请核对产品规格');}}
 async function save(){if(saving.current)return;saving.current=true;const expected=scope,selectedProduct=productId;setBusy(true);setError('');try{
  if(!pending&&!reason.trim())throw Error('请填写映射核对依据');
  const sku=skus.find(s=>String(s.id)===selected);
  const payload=pending?.payload||{sku_id:sku?.id||null,expected_product_version:data.product_version,expected_sku_version:sku?.version||null,
   confirmed_attributes:readSpecDraft(attrs),base_unit_factor:factor||null,reason:reason.trim()};
  await submitRegistration<any>('sku_mapping',productId,payload,key=>api.post(`/sku-catalog/products/${productId}/mapping`,{...payload,request_key:key}));if(expected===liveScope.current&&selectedProduct===liveProduct.current&&scope===JSON.stringify(warehouseRequestHeaders())){onDone();onClose();}
 }catch(e:any){if(expected===liveScope.current&&selectedProduct===liveProduct.current){setError(e.message||'映射未完成');const draft=registrationDraft('sku_mapping',productId);setPending(draft?.unknown?draft:null);}}finally{saving.current=false;setBusy(false);}}
 return <div className="modal-overlay z-[70]" ><div onClick={e=>e.stopPropagation()} role="dialog" aria-modal="true" aria-label="产品SKU人工映射" className="bg-white rounded-xl w-full max-w-2xl max-h-[90vh] flex flex-col">
  <div className="p-4 border-b"><h2 className="font-semibold">产品SKU人工映射</h2><p className="text-sm">{data?.product_name} · 原规格 {data?.spec||'未填'} · 原单位 {data?.unit||'未知'}</p></div>
  <div className="p-4 overflow-y-auto min-h-0 space-y-3 text-sm">
   {pending&&<p role="status" className="text-amber-700">上一映射结果待确认。请原请求重试，不能改内容另建。</p>}
   <p>名称不是SKU身份。尺寸、材质、包装逐项核对；一箱多少个未知时留空，不自动换算。</p>
   <StructuredSpecifications label="产品核实规格" value={attrs} onChange={setAttrs} disabled={!canEdit||!!pending}/>
   <button className="btn-secondary" disabled={!!pending} onClick={find}>查找候选</button>
   {data?.multiple_candidates&&<p className="text-amber-700">有多个候选，请人工选定，不会自动合并。</p>}
   {(data?.candidates||[]).map((c:any)=><div className="border rounded p-3 break-words" key={c.id}><strong>{c.code} · {c.name}</strong><p>基本单位 {c.base_unit}；命中：{c.matched_fields.join('、')||'无'}</p><SpecificationSummary value={c.attributes}/>{c.differences.map((d:string)=><p key={d} className="text-amber-700">{d}</p>)}</div>)}
   {!data?.candidates?.length&&<p>没有可靠候选；可在目录中人工选定并核实规格，也可保持未映射。</p>}
   <label className="block">人工选择SKU<select aria-label="人工选择SKU" className="form-input" value={selected} disabled={!canEdit||!!pending} onChange={e=>setSelected(e.target.value)}><option value="">明确保持未映射</option>{skus.map(s=><option key={s.id} value={s.id}>{s.code} · {s.name} · {s.base_unit}</option>)}</select></label>
   {selected&&<div className="border rounded p-2"><p className="text-sm font-medium">所选SKU规格</p><SpecificationSummary value={skus.find(s=>String(s.id)===selected)?.attributes}/></div>}
   <label className="block">每原单位含基本单位数（未知留空）<input aria-label="基本单位换算数" className="form-input" type="number" min="0" step="any" value={factor} disabled={!canEdit||!!pending} onChange={e=>setFactor(e.target.value)}/></label>
   <label className="block">映射核对依据（必填）<textarea aria-label="映射核对依据" className="form-input" maxLength={1000} value={reason} disabled={!canEdit||!!pending} onChange={e=>setReason(e.target.value)}/></label>
   <button className="btn-secondary" onClick={async()=>{try{const result=await api.get<any>(`/sku-catalog/products/${productId}/mapping-history`);if(productId===liveProduct.current&&scope===liveScope.current&&scope===JSON.stringify(warehouseRequestHeaders()))setHistory(result.data);}catch(e:any){if(productId===liveProduct.current&&scope===liveScope.current&&scope===JSON.stringify(warehouseRequestHeaders()))setError(e.message);}}}>查看映射历史</button>
   {history.map(h=><div className="border rounded p-2" key={h.id}>{h.operator_name} · {h.created_at}<p>{h.before?.sku_snapshot?.code||'未映射'} → {h.after?.sku_snapshot?.code||'未映射'}；{h.reason}</p></div>)}
   {error&&<p role="alert" className="text-red-600">{error}</p>}
  </div><div className="p-4 border-t flex justify-end gap-3"><button className="btn-secondary" disabled={busy} onClick={onClose} data-modal-close="true">关闭</button>{canEdit&&<ActionGate anyOf={["sku_catalog.mapping#operate"]}><button className="btn-primary" disabled={busy||!data} onClick={save}>{pending?'重试原映射请求':'确认人工映射'}</button></ActionGate>}</div>
 </div></div>;
}

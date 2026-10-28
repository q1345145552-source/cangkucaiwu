"use client";
import { useState } from "react";
// For existing extensible attributes (SKU attributes, quote fees), not internal object IDs.
export default function StructuredFields({value,onChange}:{value:unknown;onChange:(v:Record<string,unknown>)=>void}) {
 const entries=value && typeof value==="object" && !Array.isArray(value) ? value as Record<string,unknown> : {};
 const [key,setKey]=useState("");
 return <div className="space-y-2">{Object.entries(entries).map(([name,v])=><div key={name} className="border rounded p-2 space-y-2">
  <label className="block">{name}<select className="form-input" aria-label={`${name}的类型`} value={typeof v === "object"?"object":typeof v} onChange={e=>onChange({...entries,[name]:e.target.value==="number"?0:e.target.value==="boolean"?false:e.target.value==="object"?{}:""})}><option value="string">文字</option><option value="number">数值</option><option value="boolean">是否</option><option value="object">分项</option></select></label>
  {typeof v==="object" ? <StructuredFields value={v} onChange={next=>onChange({...entries,[name]:next})}/> : typeof v==="boolean" ? <select aria-label={name} className="form-input" value={String(v)} onChange={e=>onChange({...entries,[name]:e.target.value==="true"})}><option value="false">否</option><option value="true">是</option></select> : <input aria-label={name} className="form-input" type={typeof v==="number"?"number":"text"} step="any" value={String(v??"")} onChange={e=>onChange({...entries,[name]:typeof v==="number"?Number(e.target.value):e.target.value})}/>}
  <button type="button" className="btn-secondary min-h-[44px]" onClick={()=>onChange(Object.fromEntries(Object.entries(entries).filter(([k])=>k!==name)))}>移除 {name}</button>
 </div>)}<div className="flex gap-2"><input aria-label="新增项目名称" className="form-input" value={key} onChange={e=>setKey(e.target.value)} placeholder="项目名称"/><button type="button" className="btn-secondary min-h-[44px]" disabled={!key.trim() || Object.hasOwn(entries,key.trim())} onClick={()=>{onChange({...entries,[key.trim()]:""});setKey("");}}>添加项目</button></div></div>;
}

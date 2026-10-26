"use client";
import { useEffect,useState } from "react";
import { ApiError,warehouseRequestHeaders } from "@/lib/api";
import { registrationDraft,submitRegistration } from "@/lib/registrationRequest";

export default function ProductImportDialog({file,supplierId,canMap=false,onClose,onImported}:{file:File;supplierId?:number;canMap?:boolean;onClose:()=>void;onImported:(v:any)=>void}){
 const [preview,setPreview]=useState<any>(null),[choices,setChoices]=useState<Record<number,any>>({}),[ack,setAck]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState(''),[pending,setPending]=useState<any>(null);
 const scope=JSON.stringify(warehouseRequestHeaders()),resource=supplierId||0;
 const endpoint=supplierId?`/suppliers/${supplierId}/import/products`:'/suppliers/import/products';
 async function send(mode:string,payload?:any,key?:string){const fd=new FormData();fd.append('file',file);fd.append('mode',mode);if(payload){fd.append('preview_version',payload.preview_version);fd.append('choices',JSON.stringify(payload.choices));fd.append('request_key',key!);}
  const r=await fetch((process.env.NEXT_PUBLIC_API_URL||'/api/v1')+endpoint,{method:'POST',headers:warehouseRequestHeaders(),body:fd});const value=await r.json();if(!r.ok)throw new ApiError(r.status,value.detail||'导入未完成');return value;}
 function adopt(value:any){setPreview(value);setAck(false);setChoices(Object.fromEntries(value.rows.map((r:any)=>[r.row_number,{row_number:r.row_number,decision:'unmapped',confirmed:true,reason:'',attrsText:r.catalog_attributes?JSON.stringify(r.catalog_attributes):'',base_unit_factor:r.factor||''}])));}
 useEffect(()=>{let current=true;setError('');setPreview(null);setPending(null);setAck(false);
  try{const draft=registrationDraft('product_import',resource);if(draft?.unknown){const meta=draft.payload.file_meta;if(meta.name!==file.name||meta.size!==file.size||meta.lastModified!==file.lastModified)throw Error('请重新选择上一笔原文件；服务器也会校验原文件内容，不会重复导入');setPending(draft);setPreview(draft.payload.preview);return()=>{current=false;};}}
  catch(e:any){setError(e.message);return()=>{current=false;};}
  send('preview').then(v=>{if(current&&scope===JSON.stringify(warehouseRequestHeaders()))adopt(v);}).catch(e=>{if(current)setError(e.message);});return()=>{current=false;};
 },[file,resource,scope]);
 function change(row:number,patch:any){setChoices(previous=>({...previous,[row]:{...previous[row],...patch}}));setAck(false);}
 async function confirm(){if(busy)return;setBusy(true);setError('');try{
  if(!pending&&!ack)throw Error('请先逐行核对并勾选确认');
  const selected=Object.values(choices).map((c:any)=>{const {attrsText,...rest}=c;return {...rest,confirmed_attributes:c.decision==='map'&&attrsText.trim()?JSON.parse(attrsText):null};});
  const payload=pending?.payload||{file_meta:{name:file.name,size:file.size,lastModified:file.lastModified},preview_version:preview.preview_version,choices:selected,preview};
  const result=await submitRegistration<any>('product_import',resource,payload,key=>send('confirm',payload,key));onImported(result);onClose();
 }catch(e:any){setError(e.message||'导入未完成');if(e.detail?.code==='product_import_preview_changed')adopt(e.detail.preview);const draft=registrationDraft('product_import',resource);setPending(draft?.unknown?draft:null);}finally{setBusy(false);}}
 return <div className="modal-overlay z-[80]"><div role="dialog" aria-modal="true" aria-label="产品Excel预览与确认" className="bg-white rounded-xl w-full max-w-4xl max-h-[90vh] flex flex-col">
  <div className="p-4 border-b"><h2 className="font-semibold">产品Excel预览与确认</h2><p className="text-sm break-all">{file.name} · 尚未确认的预览不会写入产品</p></div>
  <div className="p-4 overflow-y-auto min-h-0 space-y-3 text-sm">
   <p>支持旧模板。逐行选择保持未映射或人工映射；整批成功或整批不导入，不覆盖旧报价。</p>{!canMap&&<p>当前只能保持未映射导入；人工映射另需标准SKU目录和标准SKU管理权限。</p>}
   {pending&&<p role="status" className="text-amber-700">上次导入结果待确认，只允许用原文件、原选择、原请求重试。</p>}
   {preview?.errors?.map((e:any,i:number)=><p role="alert" key={i} className="text-red-600">第{e.row_number}行：{e.message}</p>)}
   {(preview?.rows||[]).map((row:any)=><div className="border rounded p-3 space-y-2" key={row.row_number}><strong>第{row.row_number}行 · {row.product_name||'解析失败'}</strong><p>{row.supplier_name} · {row.spec||'规格未知'} · {row.unit||'单位未知'} · {row.unit_price} {row.currency}</p>
    {(row.candidates||[]).map((c:any)=><div key={c.id} className="text-xs border rounded p-2 min-w-0 break-words"><p>{c.code} · {c.name}；命中{c.matched_fields.join('、')||'无'}</p><p>{c.differences.join('；')}</p><pre className="whitespace-pre-wrap break-all">{JSON.stringify(c.attributes)}</pre></div>)}
    {!pending&&!row.errors.length&&<><label className="block">第{row.row_number}行选择<select aria-label={`第${row.row_number}行映射选择`} className="form-input" value={choices[row.row_number]?.sku_id||''} onChange={e=>{const c=row.candidates.find((v:any)=>String(v.id)===e.target.value);change(row.row_number,{decision:c?'map':'unmapped',sku_id:c?.id||null,expected_sku_version:c?.version||null});}}><option value="">明确保持未映射</option>{row.candidates.map((c:any)=><option key={c.id} value={c.id} disabled={!canMap||!c.can_map}>{c.code} · {c.name}{!c.can_map?'（规格不一致，不能映射）':''}</option>)}</select></label>
     {choices[row.row_number]?.decision==='map'&&<><label className="block">本行核实规格JSON<textarea aria-label={`第${row.row_number}行核实规格JSON`} className="form-input" value={choices[row.row_number]?.attrsText||''} onChange={e=>change(row.row_number,{attrsText:e.target.value})}/></label><label className="block">本行映射依据<input aria-label={`第${row.row_number}行映射依据`} className="form-input" value={choices[row.row_number]?.reason||''} onChange={e=>change(row.row_number,{reason:e.target.value})}/></label><label className="block">基本单位换算数（未知留空）<input aria-label={`第${row.row_number}行换算数`} className="form-input" value={choices[row.row_number]?.base_unit_factor||''} onChange={e=>change(row.row_number,{base_unit_factor:e.target.value})}/></label></>}
    </>}
   </div>)}
   {!pending&&preview?.valid&&<label className="flex gap-2"><input type="checkbox" checked={ack} onChange={e=>setAck(e.target.checked)}/>已逐行核对，按上述选择整批导入</label>}
   {error&&<p role="alert" className="text-red-600">{error}</p>}
  </div><div className="p-4 border-t flex justify-end gap-3"><button className="btn-secondary" disabled={busy} onClick={onClose}>关闭</button><button className="btn-primary" disabled={busy||!preview||!pending&&(!preview.valid||!ack)} onClick={confirm}>{pending?'原文件原请求重试':'确认整批导入'}</button></div>
 </div></div>;
}

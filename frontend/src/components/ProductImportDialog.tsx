"use client";
import { useEffect,useState,useRef } from "react";
import { warehouseRequestHeaders } from "@/lib/api";
import { checkExcel,excelResponse,importScope } from "@/lib/excelImport";
import { registrationDraft,submitRegistration,acceptProductImportRejection } from "@/lib/registrationRequest";
import StructuredSpecifications, { SpecificationSummary } from "@/components/StructuredSpecifications";
import { specDraft,readSpecDraft } from "@/lib/specifications";

export default function ProductImportDialog({file,supplierId,supplierName,canMap=false,onClose,onImported}:{file:File;supplierId?:number;supplierName?:string;canMap?:boolean;onClose:()=>void;onImported:(v:any)=>void}){
 const [preview,setPreview]=useState<any>(null),[choices,setChoices]=useState<Record<number,any>>({}),[ack,setAck]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState(''),[pending,setPending]=useState<any>(null);
 const scope=importScope(),resource=supplierId||0;
 const originalScope=useRef(scope).current,locked=useRef(false),generation=useRef(0);
 const [previewFor,setPreviewFor]=useState<{file:File;resource:number}|null>(null);
 const matchesPreview=previewFor!==null&&previewFor.file===file&&previewFor.resource===resource;
 const endpoint=supplierId?`/suppliers/${supplierId}/import/products`:'/suppliers/import/products';
 async function send(mode:string,payload?:any,key?:string){if(originalScope!==importScope())throw Error('仓库或账号已切换，请关闭旧预览重新选文件');checkExcel(file);const fd=new FormData();fd.append('file',file);fd.append('mode',mode);if(payload){fd.append('preview_version',payload.preview_version);fd.append('choices',JSON.stringify(payload.choices));fd.append('request_key',key!);}
  const r=await fetch((process.env.NEXT_PUBLIC_API_URL||'/api/v1')+endpoint,{method:'POST',headers:warehouseRequestHeaders(),body:fd});const result=await excelResponse(r);if(mode==='confirm'&&(result.mode!=='confirmed'||!(result.imported>0)||result.errors?.length))throw Error('未取得完整保存结果，请沿用原请求核对');return result;}
 const validRows=(preview?.rows||[]).filter((r:any)=>!r.skipped&&!r.errors?.length);
 const validCount=preview?.valid_count??validRows.length;
 const skippedCount=preview?.skipped_count??0;
 const totalRows=preview?.total_rows??(preview?.rows||[]).length;
 function adopt(value:any){setPreviewFor({file,resource});setPreview(value);setAck(false);setChoices(Object.fromEntries(value.rows.filter((r:any)=>!r.skipped&&!r.errors?.length).map((r:any)=>[r.row_number,{row_number:r.row_number,decision:'unmapped',confirmed:true,reason:'',specifications:specDraft(r.catalog_attributes),base_unit_factor:r.factor||''}])));}
 useEffect(()=>{let current=true;generation.current++;setError('');setPreviewFor(null);setPreview(null);setPending(null);setAck(false);
  const name=file.name.toLowerCase();
  if(!name.endsWith('.xlsx')){setError(name.endsWith('.xls')?'请另存为 xlsx 格式':'仅支持 xlsx 格式，请使用产品导入模板');return()=>{current=false;};}
  if(!file.size){setError('文件为空，请选择包含表头和数据的 xlsx 文件');return()=>{current=false;};}
  if(file.size>2*1024*1024){setError('请选择2MB以内的xlsx文件');return()=>{current=false;};}
  try{const draft=registrationDraft('product_import',resource);if(draft?.unknown){const meta=draft.payload.file_meta;if(meta.name!==file.name||meta.size!==file.size||meta.lastModified!==file.lastModified)throw Error('请重新选择上一笔原文件；服务器也会校验原文件内容，不会重复导入');setPending(draft);setPreviewFor({file,resource});setPreview(draft.payload.preview);return()=>{current=false;};}}
  catch(e:any){setError(e.message);return()=>{current=false;};}
  send('preview').then(v=>{if(current&&scope===importScope())adopt(v);}).catch(e=>{if(current)setError(e.message);});return()=>{current=false;};
 },[file,resource,scope]);
 useEffect(()=>{const timer=setInterval(()=>{if(originalScope!==importScope()){setPreview(null);setPending(null);setAck(false);setError('仓库或账号已切换，请关闭旧预览重新选文件');}},300);return()=>clearInterval(timer);},[originalScope]);
 function change(row:number,patch:any){setChoices(previous=>({...previous,[row]:{...previous[row],...patch}}));setAck(false);}
 async function confirm(){if(locked.current)return;locked.current=true;const startedGeneration=generation.current;setBusy(true);setError('');try{
  if(originalScope!==importScope())throw Error('仓库或账号已切换，请重新预览');
  if(!matchesPreview)throw Error('文件或入口已变化，请重新预览并确认');
  if(!pending&&!ack)throw Error('请先逐行核对并勾选确认');
  if(!pending&&(!preview?.valid||!validCount))throw Error('没有可确认的有效产品行，请修正文件后重新预览');
  const selected=Object.values(choices).map((c:any)=>{const {specifications,...rest}=c;return {...rest,confirmed_attributes:c.decision==='map'?readSpecDraft(specifications||[]):null};});
  const payload=pending?.payload||{file_meta:{name:file.name,size:file.size,lastModified:file.lastModified},preview_version:preview.preview_version,choices:selected,preview};
  const result=await submitRegistration<any>('product_import',resource,payload,key=>send('confirm',payload,key));if(originalScope===importScope()&&startedGeneration===generation.current){onImported(result);onClose();}
 }catch(e:any){setError(e.message||'导入未完成');if(originalScope===importScope()&&startedGeneration===generation.current){if(e.detail?.code==='product_import_preview_changed'){try{acceptProductImportRejection(resource,e.detail);adopt(e.detail.preview);}catch(proofError:any){setError(proofError.message);}}const draft=registrationDraft('product_import',resource);setPending(draft?.unknown?draft:null);}}finally{locked.current=false;setBusy(false);}}
 return <div className="modal-overlay z-[80]"><div role="dialog" aria-modal="true" aria-label="产品Excel预览与确认" className="bg-white rounded-xl w-full max-w-4xl max-h-[90vh] flex flex-col">
  <div className="p-4 border-b"><h2 className="font-semibold">产品Excel预览与确认</h2><p className="text-sm break-all">{file.name} · 尚未确认的预览不会写入产品</p></div>
  <div className="p-4 overflow-y-auto min-h-0 space-y-3 text-sm">
   <p>当前供应商：{supplierId?`${supplierName||'供应商'}（编号${supplierId}）`:'本仓多供应商，按文件名称严格核对'}。仅支持.xlsx；.xls请另存为.xlsx，不能只改扩展名。</p>   <p>仅支持xlsx，可沿用旧模板。示例行及通用入口无法匹配的供应商行会跳过；有效行逐行核对后整批导入。已有产品新增一条报价，不合并、不覆盖旧报价。</p>{!canMap&&<p>当前只能保持未映射导入；人工映射另需标准SKU目录和标准SKU管理权限。</p>}
   {preview&&<div role="status" className="rounded bg-blue-50 p-3"><strong>一共读到 {totalRows} 行，其中有效 {validCount} 行，跳过 {skippedCount} 行</strong><p>{preview.message}</p></div>}
   {pending&&<p role="status" className="text-amber-700">上次导入结果待确认，只允许用原文件、原选择、原请求重试。</p>}
   {(preview?.skipped_rows||[]).map((r:any)=><p key={r.row_number} className={r.blocking?'text-red-600':'text-amber-700'}>第{r.row_number}行：{r.message}{r.blocking?'；请修正后重新预览，当前整批未导入':''}</p>)}
   {preview?.errors?.map((e:any,i:number)=><p role="alert" key={i} className="text-red-600">第{e.row_number}行：{e.message}</p>)}
   {(preview?.rows||[]).map((row:any)=><div className="border rounded p-3 space-y-2" key={row.row_number}><strong>第{row.row_number}行 · {row.product_name||'解析失败'}</strong><p>{row.supplier_name} · {row.spec||'规格未知'} · {row.unit||'单位未知'} · {row.unit_price} {row.currency}</p>
    {(row.candidates||[]).map((c:any)=><div key={c.id} className="text-xs border rounded p-2 min-w-0 break-words"><p>{c.code} · {c.name}；命中{c.matched_fields.join('、')||'无'}</p><p>{c.differences.join('；')}</p><SpecificationSummary value={c.attributes}/></div>)}
    {(row.warnings||[]).map((message:string)=><p key={message} className="text-amber-700">{message}</p>)}
    {!pending&&!row.skipped&&!row.errors.length&&<><label className="block">第{row.row_number}行选择<select aria-label={`第${row.row_number}行映射选择`} className="form-input" value={choices[row.row_number]?.sku_id||''} onChange={e=>{const c=row.candidates.find((v:any)=>String(v.id)===e.target.value);change(row.row_number,{decision:c?'map':'unmapped',sku_id:c?.id||null,expected_sku_version:c?.version||null});}}><option value="">明确保持未映射</option>{row.candidates.map((c:any)=><option key={c.id} value={c.id} disabled={!canMap||!c.can_map}>{c.code} · {c.name}{!c.can_map?'（规格不一致，不能映射）':''}</option>)}</select></label>
     {choices[row.row_number]?.decision==='map'&&<><StructuredSpecifications label={`第${row.row_number}行核实规格`} value={choices[row.row_number]?.specifications||[]} onChange={specifications=>change(row.row_number,{specifications})}/><label className="block">本行映射依据<input aria-label={`第${row.row_number}行映射依据`} className="form-input" value={choices[row.row_number]?.reason||''} onChange={e=>change(row.row_number,{reason:e.target.value})}/></label><label className="block">基本单位换算数（未知留空）<input aria-label={`第${row.row_number}行换算数`} className="form-input" value={choices[row.row_number]?.base_unit_factor||''} onChange={e=>change(row.row_number,{base_unit_factor:e.target.value})}/></label></>}
    </>}
   </div>)}
   {!pending&&preview?.valid&&<label className="flex gap-2"><input type="checkbox" checked={ack} onChange={e=>setAck(e.target.checked)}/>已逐行核对，按上述选择整批导入</label>}
   {error&&<p role="alert" className="text-red-600">{error}</p>}
 </div><div className="p-4 border-t flex justify-end gap-3"><button className="btn-secondary" disabled={busy} onClick={onClose}>关闭</button><button className="btn-primary" disabled={busy||!matchesPreview||!preview||!pending&&(!preview.valid||!validCount||!ack)} onClick={confirm}>{pending?'原文件原请求重试':`确认导入 ${validCount} 条`}</button></div>
 </div></div>;
}

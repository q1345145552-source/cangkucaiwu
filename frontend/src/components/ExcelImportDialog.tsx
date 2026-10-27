"use client";
import { useEffect,useRef,useState } from 'react';
import { warehouseRequestHeaders } from '@/lib/api';
import { registrationDraft,submitRegistration } from '@/lib/registrationRequest';
import { checkExcel,excelApi,excelResponse,importScope } from '@/lib/excelImport';

export default function ExcelImportDialog({file,endpoint,title,resource=0,onClose,onImported}:{file:File;endpoint:string;title:string;resource?:number;onClose:()=>void;onImported:(value:any)=>void}) {
 const [preview,setPreview]=useState<any>(null),[pending,setPending]=useState<any>(null),[error,setError]=useState(''),[ack,setAck]=useState(false),[busy,setBusy]=useState(false);
 const labels:Record<string,string>={supplier_name:'供应商',supplier_id:'供应商编号',transport_method:'运输方式',cargo_type:'货物类型',origin_warehouse:'发货仓库',price_per_cbm:'单价',estimated_days:'时效',currency:'币种',received_date:'到账日期',amount:'金额',account_id:'收款账户编号',payer_name:'付款方',payment_method:'付款方式',remark:'备注',customer_id:'客户编号'};
 const locked=useRef(false),scope=useRef(importScope()).current,kind=`excel:${endpoint}`;
 async function send(mode:string,payload?:any,key?:string){
  if(scope!==importScope())throw Error('仓库或账号已切换，请关闭旧预览并重新选文件');
  checkExcel(file);const fd=new FormData();fd.append('file',file);fd.append('mode',mode);
  if(payload){fd.append('preview_version',payload.preview_version);fd.append('request_key',key!);}
  const result=await excelResponse(await fetch(excelApi+endpoint,{method:'POST',headers:warehouseRequestHeaders(),body:fd}));
  if(mode==='confirm'&&(result.mode!=='confirmed'||result.errors?.length||!(result.imported>0||result.existing>0)))throw Error('未取得完整保存结果，请保留原请求核对');
  return result;
 }
 useEffect(()=>{let active=true;
  try{checkExcel(file);const draft=registrationDraft(kind,resource);if(draft?.unknown){const m=draft.payload.file_meta;if(m.name!==file.name||m.size!==file.size||m.lastModified!==file.lastModified)throw Error('上一请求结果待确认，请选择原文件后用原请求重试');setPreview(draft.payload.preview);setPending(draft);return;}
   send('preview').then(v=>{if(active&&scope===importScope())setPreview(v);}).catch(e=>{if(active)setError(e.message);});
  }catch(e:any){setError(e.message);}return()=>{active=false;};
 },[file]);
 useEffect(()=>{const timer=setInterval(()=>{if(scope!==importScope()){setPreview(null);setPending(null);setAck(false);setError('仓库或账号已切换，请关闭旧预览并重新选文件');}},300);return()=>clearInterval(timer);},[scope]);
 async function confirm(){if(locked.current)return;locked.current=true;setBusy(true);setError('');try{
  if(scope!==importScope())throw Error('仓库或账号已切换，请重新预览');
  if(!pending&&(!ack||!preview?.valid))throw Error('请先核对有效预览并明确确认');
  const payload=pending?.payload||{file_meta:{name:file.name,size:file.size,lastModified:file.lastModified},preview_version:preview.preview_version,preview};
  const result=await submitRegistration<any>(kind,resource,payload,key=>send('confirm',payload,key));
  if(scope!==importScope())return;
  if(result.mode!=='confirmed'||result.errors?.length||!(result.imported>0||result.existing>0))throw Error('未取得完整保存结果，请保留原请求核对');
  onImported(result);onClose();
 }catch(e:any){setError(e.message||'保存未完成');if(scope===importScope()){const draft=registrationDraft(kind,resource);setPending(draft?.unknown?draft:null);}}finally{locked.current=false;setBusy(false);}}
 return <div className="modal-overlay z-[80]"><div role="dialog" aria-modal="true" aria-label={title} className="bg-white rounded-xl w-full max-w-3xl max-h-[90dvh] flex flex-col"><div className="p-4 border-b"><h2 className="font-semibold">{title}</h2><p className="text-sm break-all">{file.name} · 仅支持.xlsx，最多500行、20列、2MB；不接受公式</p></div><div className="p-4 overflow-auto min-h-0 space-y-3 text-sm">
  <p>预览不会保存；错误行必须全部修正后重新选文件。{endpoint.startsWith('/incoming')?'收款账户须由文件明确填写，不自动选择。':'供应商名称必须与当前入口一致，不覆盖旧报价。'}</p>
  {pending&&<p role="status" className="text-amber-700">保存结果待确认，仅允许原文件、原请求安全重试。</p>}
  {preview&&<p role="status">{preview.message} · 有效数据 {preview.rows?.length||0} 条</p>}
  {preview?.errors?.map((e:any,i:number)=><p role="alert" className="text-red-600 break-words" key={i}>第{e.row_number}行：{e.message}</p>)}
  {preview?.rows?.map((row:any)=><div className="border rounded p-2 break-all" key={row.row_number}>第{row.row_number}行：{Object.entries(row).filter(([k])=>k!=='row_number').map(([k,v])=>`${labels[k]||k}: ${v??'—'}`).join(' · ')}</div>)}
  {preview?.valid&&!pending&&<label className="flex gap-2"><input type="checkbox" checked={ack} onChange={e=>setAck(e.target.checked)}/>已逐行核对，确认整批保存</label>}
  {error&&<p role="alert" className="text-red-600 break-words">{error}</p>}
 </div><div className="p-4 border-t flex flex-wrap justify-end gap-3"><button className="btn-secondary" disabled={busy} onClick={onClose}>关闭 / 重新选文件</button><button className="btn-primary" disabled={busy||!preview||!pending&&(!ack||!preview.valid)} onClick={confirm}>{busy?'保存中…':pending?'原请求重试':'确认整批保存'}</button></div></div></div>;
}

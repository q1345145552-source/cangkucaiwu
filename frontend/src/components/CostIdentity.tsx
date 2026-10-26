"use client";
import { useEffect,useRef,useState } from "react";
import Link from "next/link";
import { api,warehouseRequestHeaders } from "@/lib/api";
import { fmtMoney } from "@/lib/currency";

export type CostValue={supplier_id:number;invoice:{issuer_identifier:string;series:string;number:string;verified:boolean}};
export type CostConfirmation={candidate_refs:string[];version:string;reason:string;target_ref?:string};
export const emptyCost=():CostValue=>({supplier_id:0,invoice:{issuer_identifier:"",series:"",number:"",verified:false}});
export function CostIdentityFields({value,onChange,withSupplier=true}:{value:CostValue;onChange:(v:CostValue)=>void;withSupplier?:boolean}) {
  const [suppliers,setSuppliers]=useState<any[]>([]),[error,setError]=useState("");
  const scope=JSON.stringify(warehouseRequestHeaders());
  useEffect(()=>{let current=true;setSuppliers([]);setError("");api.get<any>("/expense-identities/suppliers").then(r=>{if(current&&scope===JSON.stringify(warehouseRequestHeaders()))setSuppliers(r.data);}).catch(e=>{if(current)setError(e.message);});return()=>{current=false;};},[scope]);
  return <fieldset className="border rounded p-3 space-y-2 text-sm"><legend>供应商与发票核对（无法核实可留空）</legend>
    {withSupplier && <label className="block">本仓供应商<select aria-label="费用供应商" className="form-input" value={value.supplier_id} onChange={e=>onChange({...value,supplier_id:Number(e.target.value)})}><option value={0}>未核实／未选择</option>{suppliers.map(s=><option key={s.id} value={s.id}>{s.name}</option>)}</select></label>}
    {error && <p role="alert" className="text-red-600">{error}</p>}
    {([['issuer_identifier','开票方官方识别号'],['series','发票类型／系列'],['number','完整发票号码']] as const).map(([key,label])=><label className="block" key={key}>{label}<input className="form-input" aria-label={label} maxLength={150} value={value.invoice[key]} onChange={e=>onChange({...value,invoice:{...value.invoice,[key]:e.target.value,verified:false}})}/></label>)}
    <label className="flex gap-2"><input type="checkbox" checked={value.invoice.verified} onChange={e=>onChange({...value,invoice:{...value.invoice,verified:e.target.checked}})}/>已逐项核对原票身份；同金额不代表同一张票</label>
  </fieldset>;
}

export function CostDuplicateDialog({challenge,onClose,onConfirm}:{challenge:any;onClose:()=>void;onConfirm:(v:CostConfirmation)=>Promise<void>}) {
  const [reason,setReason]=useState(""),[busy,setBusy]=useState(false),[error,setError]=useState("");
  const blocked=!!(challenge.hard_duplicate||challenge.permission_required);
  async function confirm(){if(!reason.trim()){setError("请填写本次继续登记的原因");return;}if(busy)return;setBusy(true);try{await onConfirm({candidate_refs:challenge.candidates.map((v:any)=>v.ref),version:challenge.version,reason,target_ref:challenge.target_ref});}finally{setBusy(false);}}
  return <div className="modal-overlay z-[100]"><div role="dialog" aria-modal="true" aria-label="跨渠道费用核对" className="bg-white rounded-xl w-full max-w-xl max-h-[90vh] flex flex-col">
    <h2 className="font-semibold p-4 border-b">{challenge.permission_required?"需有原单权限的人员核查":challenge.hard_duplicate?"同一发票不能重复登记":"跨渠道疑似费用，请核对"}</h2>
    <div className="p-4 overflow-y-auto min-h-0 space-y-3 text-sm"><p>{challenge.message}</p>
      {(challenge.candidates||[]).map((c:any)=><div key={c.ref} className="border rounded p-3"><Link href={c.href} target="_blank" className="text-blue-600 underline">查看原单：{c.source_label} #{c.id}</Link><p>{c.date} · {fmtMoney(c.amount,c.currency)} · {c.status}</p><p>{c.reason}</p>{c.source_deleted&&<p>原行已删除，已付发票身份仍保留。</p>}</div>)}
      {!blocked&&<label className="block">本次继续登记原因（必填）<textarea aria-label="跨渠道继续登记原因" className="form-input" maxLength={1000} value={reason} onChange={e=>setReason(e.target.value)}/></label>}
      {error&&<p role="alert" className="text-red-600">{error}</p>}
    </div><div className="border-t p-4 flex justify-end gap-3"><button className="btn-secondary" disabled={busy} onClick={onClose}>返回核对</button>{!blocked&&<button className="btn-primary" disabled={busy} onClick={confirm}>说明后继续登记</button>}</div>
  </div></div>;
}

export function useCostIdentity() {
  const [value,setValue]=useState<CostValue>(emptyCost),[challenge,setChallenge]=useState<any>(null);
  const loading=useRef(0);
  function reset(v?:CostValue){loading.current++;setValue(v||emptyCost());setChallenge(null);}
  async function edit(source:string,id:number){const version=++loading.current,scope=JSON.stringify(warehouseRequestHeaders());const result=await api.get<any>(`/expense-identities/${source}/${id}`);if(version!==loading.current||scope!==JSON.stringify(warehouseRequestHeaders()))return;const v=result.identity;setValue({supplier_id:v?.supplier_id||0,invoice:v?.invoice_identity?{...v.invoice_identity,verified:true}:emptyCost().invoice});}
  function payload(v=value){const inv=v.invoice,filled=inv.issuer_identifier||inv.series||inv.number;if(filled&&!inv.verified)throw Error("请先核对完整发票身份，无法核实请清空身份字段");if(inv.verified&&(!v.supplier_id||!inv.issuer_identifier.trim()||!inv.series.trim()||!inv.number.trim()))throw Error("请选择本仓供应商并填写完整发票身份");return {supplier_id:v.supplier_id||null,invoice_identity:inv.verified?inv:null};}
  function capture(error:any,retry:(v:CostConfirmation)=>Promise<void>){if(['cost_invoice_duplicate','cost_duplicate_confirmation','cost_duplicate_restricted'].includes(error.detail?.code)){setChallenge({detail:error.detail,retry});return true;}return false;}
  const dialog=challenge&&<CostDuplicateDialog challenge={challenge.detail} onClose={()=>setChallenge(null)} onConfirm={async data=>{const retry=challenge.retry;setChallenge(null);await retry(data);}}/>;
  return {value,setValue,reset,edit,payload,capture,dialog,fields:<CostIdentityFields value={value} onChange={setValue}/>};
}

"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { fmtMoney } from "@/lib/currency";
import { ThreeWayMatch } from "@/components/PurchaseReceiptInfo";
import { billStatus } from "@/components/ProcurementInfo";
import { uploadPayableVoucher, payableScope, PayableVoucherTask } from "@/lib/payablePayment";
import { useMenuPermission } from "@/hooks/useMenuPermission";
import { useAuth } from "@/hooks/useAuth";

export default function PayableDetail({ billId, revision, onClose, onPay, onConfirm }: { billId:number; revision:number; onClose:()=>void; onPay:(bill:any)=>void; onConfirm?:(id:number)=>Promise<void> }) {
  const [bill,setBill]=useState<any>(null), [error,setError]=useState(""), [reload,setReload]=useState(0);
  const [fileTask,setFileTask]=useState<PayableVoucherTask|null>(null), [saving,setSaving]=useState(false), [notice,setNotice]=useState("");
  const { user }=useAuth() as {user:{role:string} | null}; const permission=useMenuPermission("payable");
  const canWrite=permission && ["warehouse_admin","supervisor"].includes(user?.role || "");
  useEffect(()=>{let active=true;setBill(null);setError("");
    api.get<any>(`/payable/${billId}/detail`).then(x=>{if(active)setBill(x);}).catch(e=>{if(active)setError(e.message || "账单加载失败");});
    return()=>{active=false;};
  },[billId,revision,reload]);
  async function upload(){if(!fileTask || fileTask.billId!==billId)return;setSaving(true);setNotice("");
    try{await uploadPayableVoucher(fileTask.billId,fileTask.file,fileTask.scope);setNotice("账单级凭证已上传，没有再次付款");setFileTask(null);setReload(n=>n+1);}
    catch(e:any){setNotice(`凭证上传失败：${e.message}，付款记录不变`);}finally{setSaving(false);}}
  return <div className="modal-overlay z-[70]" onClick={onClose}><div role="dialog" aria-label="应付详情" className="bg-white rounded-xl w-full max-w-3xl max-h-[90vh] flex flex-col" onClick={e=>e.stopPropagation()}>
    <div className="p-4 border-b flex justify-between"><h2 className="font-semibold">应付详情 {bill?.bill_number || `#${billId}`}</h2><button onClick={onClose}>关闭</button></div>
    <div className="p-4 overflow-auto space-y-4 text-sm">
      {error ? <p role="alert" className="text-red-600">{error} <button onClick={()=>setReload(n=>n+1)}>重试</button></p> : !bill ? <p>加载中</p> : <>
        <p>供应商：{bill.supplier_name} · 状态：{billStatus[bill.status] || bill.status}</p>
        <p>应付总额 {fmtMoney(bill.amount,bill.currency)} · 累计已付 {bill.paid_amount == null ? "未记录" : fmtMoney(bill.paid_amount,bill.currency)} · 剩余应付 {bill.remaining_amount == null ? "待核对" : fmtMoney(bill.remaining_amount,bill.currency)}</p>
        {bill.need_boss_confirm === "true" && <p className="text-red-600">待老板确认收货差异，暂不能付款</p>}
        {canWrite && user?.role === "warehouse_admin" && bill.need_boss_confirm === "true" && bill.status !== "voided" && onConfirm && <button className="btn-primary" onClick={()=>onConfirm(bill.id)}>确认收货差异</button>}
        {bill.purchase_order_id ? <Link className="text-blue-600 underline" href={`/suppliers/purchase-orders/${bill.purchase_order_id}`}>查看关联采购单 {bill.purchase_order_number}</Link> : <p>未关联采购单（手动账单）</p>}
        {(bill.warnings || []).map((w:string)=><p role="alert" className="text-red-600" key={w}>{w}</p>)}
        {bill.invoice_identity && <p>已核实发票：{bill.invoice_identity.issuer_identifier} · {bill.invoice_identity.series} · {bill.invoice_identity.number}</p>}
        {bill.duplicate_confirmation && <section className="border rounded p-3"><h3 className="font-semibold">本次疑似重复核对留痕</h3><p>{bill.duplicate_confirmation.operator_name} · {new Date(bill.duplicate_confirmation.confirmed_at).toLocaleString("zh-CN",{timeZone:"Asia/Bangkok"})}（泰国时间）</p><p>原因：{bill.duplicate_confirmation.reason}</p><p>核对账单：{bill.duplicate_confirmation.candidate_ids.map((id:number)=>`#${id}`).join("、")}</p><p className="text-xs text-gray-500">仅限本次，不豁免后续登记。</p></section>}
        <ThreeWayMatch value={bill.matching}/>
        <h3 className="font-semibold">逐笔实际付款（不补造历史）</h3>
        {bill.payments.length ? bill.payments.map((p:any)=><div key={p.id} className="border rounded-lg p-3 space-y-1" aria-label={`付款记录${p.id}`}>
          <p>#{p.id} · {fmtMoney(p.amount,p.currency)} · {p.account_name}</p>
          <p>{p.paid_at ? new Date(p.paid_at).toLocaleString("zh-CN",{timeZone:"Asia/Bangkok"}) : "时间未记录"}（泰国时间）</p>
          <p>{p.payment_method || "付款方式未记录"} · 操作人：{p.operator_name}</p>
        </div>) : <p>暂无逐笔付款记录</p>}
        <p>逐笔合计：{fmtMoney(bill.recorded_payment_total,bill.currency)}</p>
        {bill.legacy_paid_amount == null ? <p className="text-red-600">历史累计无法确定，请核对</p> : bill.legacy_paid_amount > 0 && <p className="text-amber-700">历史累计 {fmtMoney(bill.legacy_paid_amount,bill.currency)}，缺逐笔明细；已包含在累计已付中，不再相加</p>}
        <section className="border-t pt-3 space-y-2"><p>{bill.voucher_scope}</p>
          {bill.payment_voucher ? <a className="text-blue-600 underline" href={bill.payment_voucher} target="_blank" rel="noreferrer">查看账单级付款凭证</a> : <p>尚无账单级付款凭证</p>}
          {canWrite && <><input key={billId} aria-label="重传账单级凭证" type="file" accept="image/*" onChange={e=>{try{const file=e.target.files?.[0];setFileTask(file ? {billId,file,scope:payableScope()} : null);}catch(e:any){setNotice(e.message);}}}/><button className="btn-secondary" disabled={fileTask?.billId!==billId || saving} onClick={upload}>仅上传／重传凭证</button></>}
          {notice && <p role="status">{notice}</p>}
        </section>
        {canWrite && bill.paid_amount != null && !["paid","voided"].includes(bill.status) && bill.need_boss_confirm !== "true" && <button className="btn-primary" onClick={()=>onPay(bill)}>付款</button>}
      </>}
    </div>
  </div></div>;
}

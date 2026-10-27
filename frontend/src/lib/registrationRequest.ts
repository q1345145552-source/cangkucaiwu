import { getActiveWarehouseId } from "@/lib/api";

type Draft = { key:string; payload:any; unknown:boolean };
const running=new Map<string,Promise<any>>();
function slot(kind:string,resource:string|number) {
  const user=JSON.parse(localStorage.getItem("user") || "{}");
  const warehouse=getActiveWarehouseId() || user.warehouse_id;
  if(!user.id || !warehouse || warehouse==="all")throw Error("请先选择单个仓库");
  return `supplier-registration:${user.id}:${warehouse}:${kind}:${resource}`;
}
export function registrationDraft(kind:string,resource:string|number=0):Draft|null {
  const saved=sessionStorage.getItem(slot(kind,resource));
  if(!saved)return null;
  const result=JSON.parse(saved);
  if(!result.key || !result.payload)throw Error("登记请求草稿异常，请先核对原单");
  return result;
}
// Only a locked server rejection proving this exact request did not create an order can unfreeze it.
// Retain its key: a competing replay can therefore never create a second order.
export function acceptQuotePreviewRejection(resource:string|number,detail:any):void {
  const id=slot('purchase_order',resource),draft=registrationDraft('purchase_order',resource);
  if(running.has(id) || !draft || detail?.code!=='quote_preview_changed' || detail.not_created!==true || detail.request_key!==draft.key)
    throw Error('尚未取得原请求未创建采购的明确结果，请先核对原单');
  sessionStorage.setItem(id,JSON.stringify({...draft,unknown:false}));
}
// Only a warehouse-locked exact-key rejection may release an uncertain duty request.
export function acceptDutyRejection(kind:string,resource:string|number,detail:any):void {
  if(!['duty_approve','duty_reject','purchase_receipt','duty_policy','duty_grant','risk_review'].includes(kind))throw Error('职责请求类型不正确');
  const id=slot(kind,resource),draft=registrationDraft(kind,resource);
  if(running.has(id)||!draft||detail?.code!=='procurement_duty_changed'||detail.not_executed!==true||detail.request_key!==draft.key)
    throw Error('尚未取得原职责请求未执行的明确结果，请沿用原请求核对');
  sessionStorage.setItem(id,JSON.stringify({...draft,unknown:false}));
}
// Only the exact warehouse-locked nonexecution proof releases an uncertain stock request.
export function acceptInventoryRejection(resource:string,detail:any):void {
  const id=slot('inventory',resource),draft=registrationDraft('inventory',resource);
  if(running.has(id)||!draft||detail?.code!=='inventory_changed'||detail.not_executed!==true||detail.request_key!==draft.key)
    throw Error('尚未取得原库存请求未执行的明确结果，请沿用原请求核对');
  sessionStorage.setItem(id,JSON.stringify({...draft,unknown:false}));
}
export async function submitRegistration<T>(kind:string,resource:string|number,payload:any,send:(key:string)=>Promise<T>):Promise<T> {
  const id=slot(kind,resource),previous=registrationDraft(kind,resource);
  if(running.has(id)){
    if(JSON.stringify(previous?.payload)!==JSON.stringify(payload))throw Error("原登记正在提交，请勿同时更改内容另行提交");
    return running.get(id)!;
  }
  if(previous?.unknown && JSON.stringify(previous.payload)!==JSON.stringify(payload))throw Error("上一登记结果待核对，请恢复原内容和原附件重试；未新增第二笔");
  const draft:Draft={key:previous?.key || crypto.randomUUID(),payload,unknown:previous?.unknown || false};
  try{sessionStorage.setItem(id,JSON.stringify(draft));}catch{throw Error("无法保存登记请求编号，请恢复浏览器存储后重试");}
  const task=(async()=>{
    try{
      const result:any=await send(draft.key);
      if(result.id || result.order?.id)sessionStorage.removeItem(id);
      else if(!result.need_confirm && !result.need_reason)throw Error("登记返回未完整，请沿用原请求重试");
      return result;
    }catch(e:any){
      draft.unknown=previous?.unknown || !(e.status>=400 && e.status<500 && e.status!==408);
      sessionStorage.setItem(id,JSON.stringify(draft));
      if(draft.unknown && !e.status)throw Error(`${e.message || "网络中断"}；登记结果待核对，原请求编号已保留`);
      throw e;
    }
  })();
  running.set(id,task);
  try{return await task;}finally{if(running.get(id)===task)running.delete(id);}
}


// Only an under-lock server proof that this exact Excel request has not committed can
// unfreeze its payload. Keep the key so competing retries cannot create a second batch.
export function acceptExcelImportRejection(kind:string,resource:string|number,detail:any):void {
  const id=slot(kind,resource),draft=registrationDraft(kind,resource);
  if(!kind.startsWith('excel:') || running.has(id) || !draft || detail?.code!=='excel_import_not_saved' || detail.not_created!==true || detail.request_key!==draft.key)
    throw Error('尚未取得原导入请求未保存的明确结果，请保留原请求核对');
  sessionStorage.setItem(id,JSON.stringify({...draft,unknown:false}));
}

// A product import can release an uncertain payload only after the warehouse-locked
// backend has checked this exact key and proved there is no committed operation.
export function acceptProductImportRejection(resource:string|number,detail:any):void {
  const id=slot('product_import',resource),draft=registrationDraft('product_import',resource);
  if(running.has(id)||!draft||detail?.code!=='product_import_preview_changed'||detail.not_created!==true||detail.request_key!==draft.key)
    throw Error('尚未取得原产品导入请求未保存的明确结果，请保留原请求核对');
  sessionStorage.setItem(id,JSON.stringify({...draft,unknown:false}));
}

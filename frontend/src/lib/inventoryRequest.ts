import {ApiError,getActiveWarehouseId,warehouseRequestHeaders} from '@/lib/api';
import {registrationDraft,submitRegistration,acceptInventoryRejection} from '@/lib/registrationRequest';

const API_URL=process.env.NEXT_PUBLIC_API_URL||'/api/v1';
export const inventoryScope=()=>JSON.stringify(warehouseRequestHeaders());
export function inventoryMethod(resource:string){
  if(resource==='/inventory/policy')return 'PUT';
  if(/^\/inventory\/accounts\/\d+\/controls$/.test(resource))return 'PUT';
  if(/^\/inventory\/(accounts\/\d+\/counts|counts\/\d+\/review)$/.test(resource))return 'POST';
  if(/^\/inventory\/(openings\?sku_id=\d+&base_unit=[a-z]+|accounts\/\d+\/issues|movements\/\d+\/(returns|reverse)|pending-receipts\/\d+\/resolve)$/.test(resource))return 'POST';
  throw Error('库存请求来源不正确，请核对原记录');
}
export function pendingInventoryRequests(){
  const user=JSON.parse(localStorage.getItem('user')||'{}'),wid=getActiveWarehouseId()||user.warehouse_id;
  if(!user.id||!wid||wid==='all')return [];
  const prefix=`supplier-registration:${user.id}:${wid}:inventory:`,result=[];
  for(let i=0;i<sessionStorage.length;i++){
    const key=sessionStorage.key(i);if(!key?.startsWith(prefix))continue;
    const resource=key.slice(prefix.length);inventoryMethod(resource);
    const draft=registrationDraft('inventory',resource);
    if(draft?.unknown)result.push({resource,...draft});
  }
  return result;
}
export async function submitInventory(resource:string,payload:any,scope:string){
  const method=inventoryMethod(resource);
  if(inventoryScope()!==scope)throw Error('账号或仓库已变化，请重新打开；未提交');
  const headers=warehouseRequestHeaders();
  try{return await submitRegistration<any>('inventory',resource,payload,async key=>{
    if(inventoryScope()!==scope)throw Error('账号或仓库已变化，未发送原库存请求');
    const response=await fetch(`${API_URL}${resource}`,{method,headers:{...headers,'Content-Type':'application/json'},body:JSON.stringify({...payload,request_key:key})});
    const result=await response.json();
    if(inventoryScope()!==scope)throw Error('账号或仓库已变化，原库存结果待核对，请回原仓沿用原请求重试');
    if(!response.ok)throw new ApiError(response.status,result.detail||'库存登记失败');
    if(!result.id)throw Error('库存登记返回不完整，请沿用原请求重试');
    return result;
  });}catch(e:any){
    if(e.detail?.code==='inventory_changed')acceptInventoryRejection(resource,e.detail);
    throw e;
  }
}

import {ApiError,warehouseRequestHeaders} from '@/lib/api';
import {submitRegistration,acceptDutyRejection} from '@/lib/registrationRequest';
const API_URL=process.env.NEXT_PUBLIC_API_URL||'/api/v1';
export const controlScope=()=>JSON.stringify(warehouseRequestHeaders());
export function controlFields(value:any){
  if(!/^[a-f0-9]{64}$/.test(value?.policy_version||'')||!/^[a-f0-9]{64}$/.test(value?.business_version||''))throw Error('职责上下文读取不完整，请重新打开');
  return {expected_policy_version:value.policy_version,expected_business_version:value.business_version};
}
export async function controlMutation(kind:string,resource:string|number,payload:any,endpoint:string,method:string,scope:string,proof:any={}){
  if(controlScope()!==scope)throw Error('账号或仓库已变化，请重新打开；未提交');
  const headers=warehouseRequestHeaders();
  try{return await submitRegistration<any>(kind,resource,payload,async key=>{
    if(controlScope()!==scope)throw Error('账号或仓库已变化，未发送原请求');
    const response=await fetch(`${API_URL}${endpoint}`,{method,headers:{...headers,'Content-Type':'application/json'},body:JSON.stringify({...payload,...proof,request_key:key})});
    const result=await response.json();
    if(controlScope()!==scope)throw Error('账号或仓库已变化，原请求结果待核对，请返回原仓沿用原请求重试');
    if(!response.ok)throw new ApiError(response.status,result.detail||'操作失败');
    const id=result.id||result.data?.id||result.duty_execution_id||result.payable_bill_id;
    if(!id)throw Error('操作返回不完整，请沿用原请求重试');
    return {...result,id};
  });}catch(e:any){
    if(e.detail?.code==='procurement_duty_changed')acceptDutyRejection(kind,resource,e.detail);
    throw e;
  }
}
export async function controlDownload(endpoint:string,filename:string,scope:string){
  if(controlScope()!==scope)throw Error('账号或仓库已变化，请重新读取');
  const response=await fetch(`${API_URL}${endpoint}`,{headers:warehouseRequestHeaders()});
  if(!response.ok){const data=await response.json();throw new ApiError(response.status,data.detail||'导出失败');}
  const blob=await response.blob();if(controlScope()!==scope)throw Error('账号或仓库已变化，未展示原仓文件');
  const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=filename;a.click();URL.revokeObjectURL(url);
}

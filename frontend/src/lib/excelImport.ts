import { ApiError, warehouseRequestHeaders } from '@/lib/api';
export const excelApi = process.env.NEXT_PUBLIC_API_URL || '/api/v1';
export function importScope() { return JSON.stringify([warehouseRequestHeaders(),localStorage.getItem('user')]); }
export function readableError(value:any):string {
 if(typeof value==='string')return value;
 if(Array.isArray(value))return value.map(readableError).join('；');
 if(value && typeof value==='object')return [value.message || value.msg, value.row_number?`第${value.row_number}行`:null,value.errors?readableError(value.errors):null].filter(Boolean).join('：') || '请求内容不符合要求，请检查模板与权限';
 return '操作未完成，请重试';
}
export async function excelResponse(response:Response) {
 const text=await response.text();let value:any;
 try{value=JSON.parse(text);}catch{throw new ApiError(response.ok?502:response.status,`服务返回异常（HTTP ${response.status}），请保留原请求重试`);}
 if(!response.ok){const detail=value.detail || value;throw new ApiError(response.status,typeof detail==='object'&&!Array.isArray(detail)?{...detail,message:readableError(detail)}:readableError(detail));}
 return value;
}
export function checkExcel(file:File) {
 if(!file.name.toLowerCase().endsWith('.xlsx'))throw Error('仅支持.xlsx；.xls请在Excel中另存为.xlsx，不能只改扩展名');
 if(!file.size || file.size>2*1024*1024)throw Error('请选择非空且2MB以内的.xlsx文件');
}
export async function downloadExcel(path:string,name:string) {
 const response=await fetch(excelApi+path,{headers:warehouseRequestHeaders()});
 if(!response.ok){await excelResponse(response);return;}
 if(!response.headers.get('content-type')?.includes('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'))throw Error('模板响应类型异常，未保存文件');
 const blob=await response.blob();const signature=new Uint8Array(await blob.slice(0,4).arrayBuffer());
 if(signature[0]!==80 || signature[1]!==75)throw Error('模板内容异常，未保存文件');
 const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=name;a.click();URL.revokeObjectURL(url);
}

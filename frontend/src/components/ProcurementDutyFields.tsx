'use client';
export default function ProcurementDutyFields({value,onChange,onRefresh}:{value:any;onChange:(v:any)=>void;onRefresh:()=>void}){
 if(!value)return <p role="alert">职责上下文未读取，请重新打开。</p>;
 return <div className="border rounded p-3 space-y-2 text-sm break-words">
  <p>采购人账号 #{value.ctx.creator_id??'未知'} · 当前操作账号 #{value.ctx.operator_id}</p>
  <p>{value.ctx.unknown_creator?'采购人无法判断，不能在启用职责规则后操作':value.ctx.needs_exception?'本人操作需要老板明确授予一次性例外；老板本人也不自动豁免':'仍须满足原有业务权限和确认规则'}</p>
  {value.locked&&<p role="alert" className="text-amber-800">原请求结果待核对，已保留原编号和职责版本；请沿用原内容与原附件重试。</p>}
  <label className="block">一次性例外授权编号（需要时填写）<input aria-label="一次性例外授权编号" className="form-input" type="number" min="1" step="1" disabled={value.locked} value={value.exception} onChange={e=>onChange({...value,exception:e.target.value})}/></label>
  <button type="button" className="text-blue-700 underline" onClick={onRefresh}>{value.locked?'恢复原请求':'重新读取当前职责版本'}</button>
  <p className="text-xs text-gray-500">授权须由老板在“采购职责与例外”中明确登记，匹配本仓、本单、本动作、本账号和当前版本，只能执行一次。</p>
 </div>;
}

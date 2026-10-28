"use client";
import { supplierCategoryChoiceVisible } from "@/lib/supplierFeatures";
import { useEffect, useState, useRef } from "react";
import { api, getToken, getActiveWarehouseId } from "@/lib/api";
export interface Selector { field: string; entity: string; parent?: string | null; discriminator?: string | null }
interface Choice { id: number | string; label: string; status?: string }
export default function ActionObjectSelect({ module, action, selector, parentId, documentType, value, onChange, required, label, onVersions }: {
  module: string; action: string; selector: Selector; parentId?: unknown; documentType?: unknown; value: unknown;
  onChange: (v: unknown) => void; required?: boolean; label: string; onVersions:(v:Record<string,unknown>)=>void;
}) {
  const [search, setSearch] = useState(""), [page, setPage] = useState(1);
  const [rows, setRows] = useState<Choice[]>([]), [more, setMore] = useState(false), [error, setError] = useState("");
  const [facts,setFacts] = useState<Record<string,unknown>>({});
  const versionsCallback=useRef(onVersions);
  versionsCallback.current=onVersions;
  const selectRef=useRef<HTMLSelectElement>(null);
  const [verifiedSelection,setVerifiedSelection]=useState("");
  const selectionKey=JSON.stringify([action,selector.field,parentId,documentType,value]);
  useEffect(()=>{ selectRef.current?.setCustomValidity(value && verifiedSelection!==selectionKey ? "请等待选中单据核对完成；读取失败时请重新选择" : ""); },[value,verifiedSelection,selectionKey]);
  const previousParent=useRef(parentId), previousType=useRef(documentType);
  useEffect(()=>{ if (previousParent.current !== parentId || previousType.current !== documentType) { previousParent.current=parentId; previousType.current=documentType; onChange(undefined); } },[parentId,documentType,onChange]);
  const [loading, setLoading] = useState(false), [picked, setPicked] = useState<Choice>();
  useEffect(() => { setPage(1); setRows([]); setPicked(undefined); }, [action, selector.field, parentId, documentType]);
  useEffect(() => {
    let active = true;
    const token = getToken(), warehouse = getActiveWarehouseId();
    setRows([]); setMore(false); setError("");
    if ((selector.parent && !parentId) || (selector.discriminator && !documentType)) return;
    setLoading(true);
    const timer = setTimeout(() => {
      const query = new URLSearchParams({ action, field:selector.field, page:String(page), search });
      if (parentId) query.set("parent_id",String(parentId));
      if (documentType) query.set("document_type",String(documentType));
      api.get<{data:Choice[];has_more:boolean}>(`/access/choices/${module}?${query}`).then(r => {
        if (active && getToken() === token && getActiveWarehouseId() === warehouse) { setRows(r.data.filter(item=>supplierCategoryChoiceVisible(selector.entity,item.id))); setMore(r.has_more); }
      }).catch((e: unknown) => { if (active) setError(e instanceof Error ? e.message : "读取候选项失败"); })
        .finally(() => { if (active) setLoading(false); });
    }, 180);
    return () => { active = false; clearTimeout(timer); };
  }, [module, action, selector.field, selector.parent, parentId, documentType, page, search]);
  useEffect(()=>{
    let active=true;setFacts({});setVerifiedSelection("");
    if (!value || (selector.parent && !parentId) || (selector.discriminator && !documentType)) return;
    const token=getToken(),warehouse=getActiveWarehouseId();
    const query=new URLSearchParams({action,field:selector.field,selected_id:String(value)});
    if (parentId) query.set("parent_id",String(parentId));
      if (documentType) query.set("document_type",String(documentType));
    api.get<{context?:Record<string,unknown>;versions?:Record<string,unknown>;data:Choice[]}>(`/access/choices/${module}?${query}`).then(r=>{
      if (active && token===getToken() && warehouse===getActiveWarehouseId()) { if(!supplierCategoryChoiceVisible(selector.entity,value)){setPicked(undefined);setError("物流类型入口已关闭，历史分类保持原样");return;} setFacts(r.context || {}); setPicked(r.data[0]); versionsCallback.current(r.versions || {}); setVerifiedSelection(selectionKey); }
    }).catch((e:unknown)=>{ if(active) setError(e instanceof Error?e.message:"无法核对选中记录"); });
    return ()=>{active=false;};
  },[module,action,selector.field,selector.parent,parentId,documentType,value,selectionKey]);
  const factLabels:Record<string,string>={order_number:"采购单号",quantity:"采购数量",received_quantity:"已收数量",declaration_id:"充值申报编号",flow_id:"到账编号",reconciliation_month:"对账月份",match_status:"匹配状态",amount_diff:"金额差额",handling_note:"处理说明",sessions:"时段",period:"期间",status:"状态",net_pay:"本次实发工资",disbursed:"已发放",settle_start_date:"结算开始",settle_end_date:"结算结束",submit_date:"申请日期",total_amount:"合计金额",currency:"币种",category:"类别",amount:"金额",description:"说明",review_status:"审核状态",purpose:"用途",expense_date:"开销日期",reason:"原因",bill_number:"账单编号",paid_amount:"已付金额",due_date:"期限",plan_name:"计划名称",planned_date:"计划日期",leave_date:"请假日期",leave_type:"请假类型",hours:"时数",date:"日期",start_time:"开始时间",end_time:"结束时间",actual_hours:"实际时数",confirmed:"已确认",order_no:"采购单号",book_quantity:"账面数量",counted_quantity:"实盘数量",counted_at:"盘点日期",base_unit:"单位",recorded_quantity:"账面数量",revision:"当前版本",product_name:"商品",spec:"规格",unit:"单位",valid_from:"有效期开始",valid_to:"有效期结束",tiers:"报价档位",fees:"费用条件"};
  const statuses:Record<string,string>={pending:"待处理",approved:"已批准",rejected:"已驳回",verified:"已核验",paid:"已付款",partially_paid:"部分付款",confirmed:"已确认",active:"有效",voided:"已作废",executed:"已执行",personal:"事假",sick:"病假",annual:"年假"};
  const options = picked && !rows.some(r => r.id === picked.id) ? [picked,...rows] : rows;
  return <div className="space-y-2">
    <input className="form-input" aria-label={`搜索${label}`} placeholder={`搜索${label}`} value={search} onChange={e => { setSearch(e.target.value); setPage(1); }} />
    <select ref={selectRef} className="form-input" aria-label={label} required={required} value={String(value ?? "")} disabled={(!!selector.parent && !parentId) || (!!selector.discriminator && !documentType)} onChange={e => { setVerifiedSelection(""); setFacts({}); const choice=options.find(r=>String(r.id)===e.target.value); setPicked(choice); onChange(choice?.id); }}>
      <option value="">{selector.parent && !parentId ? "请先选择所属单据" : loading ? "正在读取…" : "请选择"}</option>
      {options.map(r => <option key={r.id} value={r.id}>{r.label}{r.status ? ` · ${statuses[r.status] || r.status}` : ""}</option>)}
    </select>
    <div className="flex gap-3 items-center"><button type="button" className="btn-secondary min-h-[44px]" disabled={page === 1 || loading} onClick={()=>setPage(p=>p-1)}>上一页</button><span>第 {page} 页</span><button type="button" className="btn-secondary min-h-[44px]" disabled={!more || loading} onClick={()=>setPage(p=>p+1)}>下一页</button></div>
    {!!value && verifiedSelection!==selectionKey && <p role="status">正在核对选中单据；核对完成后才能提交。</p>}
    {!!Object.keys(facts).length && <dl className="rounded bg-gray-50 p-3 text-sm">{Object.entries(facts).map(([key,v])=><div key={key} className="flex gap-3"><dt>{factLabels[key] || key}</dt><dd>{v===null?"未填":typeof v==="boolean"?(v?"是":"否"):typeof v==="object" ? JSON.stringify(v) : statuses[String(v)] || String(v)}</dd></div>)}</dl>}
    {error && <p role="alert">{error}</p>}
  </div>;
}

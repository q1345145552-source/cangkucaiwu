"use client";
import { supplierActionEntryVisible } from "@/lib/supplierFeatures";
import { useEffect, useState, useCallback, type FormEvent } from "react";
import { api, getToken, getActiveWarehouseId, warehouseRequestHeaders } from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import { hasAction, type ActionTier } from "@/hooks/useActionPermission";
import ActionObjectSelect, { type Selector } from "./ActionObjectSelect";
import StructuredFields from "./StructuredFields";
interface Schema { encoding?: string; selector?: Selector; type?: string; title?: string; format?: string; enum?: (string | number)[]; default?: unknown; properties?: Record<string, Schema>; required?: string[]; items?: Schema; anyOf?: Schema[]; allOf?: Schema[] }
interface Parameter { name: string; in: "path" | "query"; required?: boolean; schema: Schema }
interface Contract { label: string; method: string; path: string; parameters: Parameter[]; body: Schema; media: string }
interface Action { id: string; module_key: string; grant_modules?: string[]; tier: ActionTier; mode: string; form?: Contract; variants?: { field: string; values: Record<string, { tier: ActionTier }> } }
interface FieldContext { action: Action; parameters: Values; body: Values; siblings?: Values; applyVersions:(v:Values)=>void }
type Values = Record<string, unknown>;
const labels: Record<string, string> = { po_id:"采购单", product_id:"商品", quote_id:"报价", sku_id:"SKU", exception_id:"例外授权", line_id:"采购明细", file:"照片或文件", files:"附件", issued_quantity:"领用数量", returned_quantity:"退回数量", counted_quantity:"实盘数量", purpose:"用途", count_reason:"盘点原因", return_reason:"退回原因", change_reason:"变更原因", review_reason:"核验原因", reverse_reason:"冲销原因", supplier_id:"供应商", customer_id:"客户", user_id:"账号", operator_id:"办理人", payer_id:"垫款人", id:"记录编号", employee_id:"员工", account_id:"账户", payment_account_id:"付款账户", record_id:"记录", fund_id:"备用金账户", request_id:"申请编号", leave_id:"请假记录", employee_ids:"员工名单", record_ids:"记录编号列表", item_ids:"明细编号列表", end_date:"截止日期", start_date:"开始日期", leave_date:"请假日期", leave_type:"请假类型", hours:"时数", date:"日期", remark:"备注", reason:"原因", amount:"金额", description:"说明", name:"名称", status:"状态", action:"办理步骤", funding_source:"资金来源", currency:"币种", payment_date:"付款日期", receive_date:"到账日期", signature_base64:"签收凭证", payment_method:"付款方式", warehouse_id:"所属仓库", payroll_id:"工资记录", reimb_id:"报销单", advance_id:"预支单", bill_id:"应付单", plan_id:"付款计划", type:"类型", request_key:"业务请求标识", expense_date:"开销日期", category:"类别", items:"明细", dates:"日期列表", phone:"联系电话", address:"地址", actual_hours:"实际时数", assignments:"人员记录", task_id:"加班任务", reviewed_amount:"审核金额" };
function shape(schema: Schema): Schema { return schema.anyOf?.find(s => s.type !== "null") || schema.allOf?.[0] || schema; }
function Field({ name, schema: original, value, onChange, required, context }: { name: string; schema: Schema; value: unknown; onChange: (value: unknown) => void; required?: boolean; context: FieldContext }) {
  const schema = shape(original), label = schema.title && /[\u4e00-\u9fff]/.test(schema.title) ? schema.title : labels[name] || schema.title || name;
  if (name === "request_key") return null;
  if (schema.type === "object" || schema.properties) {
    const values = value && typeof value === "object" ? value as Values : {};
    if (!schema.properties || !Object.keys(schema.properties).length) return <fieldset className="space-y-2 border rounded p-3"><legend>{label}</legend><StructuredFields value={value} onChange={onChange}/></fieldset>;
    return <fieldset className="space-y-2 border rounded p-3"><legend>{label}</legend>{Object.entries(schema.properties || {}).map(([key, s]) => <Field key={key} name={key} schema={s} value={values[key]} required={schema.required?.includes(key)} context={{...context,siblings:values,applyVersions:incoming=>{
      const allowed=Object.fromEntries(Object.entries(incoming).filter(([key])=>key.startsWith("expected_") && schema.properties?.[key]));
      if(Object.keys(allowed).length) onChange({...values,...allowed});
    }}} onChange={v => onChange({ ...values, [key]: v })} />)}</fieldset>;
  }
  if (schema.type === "array") {
    const values = Array.isArray(value) ? value as unknown[] : [];
    return <fieldset className="border rounded p-3 space-y-2"><legend>{label}{required ? " *" : ""}</legend>{values.map((v, i) => <div key={i}><Field name={name} schema={schema.items || { type:"string" }} value={v} onChange={next => onChange(values.map((old,n) => n === i ? next : old))} context={context} /><button type="button" className="btn-secondary" onClick={() => onChange(values.filter((_, n) => n !== i))}>移除此项</button></div>)}<button type="button" className="btn-secondary" onClick={() => onChange([...values, undefined])}>添加一项</button></fieldset>;
  }
  if (name.startsWith("expected_") && name.endsWith("version")) return <p className="text-sm">记录版本：{value ? "已读取，提交时将再次核对" : "请先选择记录"}</p>;
  const selector = schema.selector || original.selector;
  const parent = selector?.parent;
  const parentId = parent?.startsWith("path:") || parent?.startsWith("query:") ? context.parameters[parent.split(":")[1]]
    : parent?.includes(".[]") ? context.siblings?.[parent.split(".").at(-1) || ""] : parent ? context.body[parent.split(":")[1]] : undefined;
  return <label className="block text-sm">{label}{required ? " *" : "（可空）"}
    {selector ? <ActionObjectSelect module={context.action.module_key} action={context.action.id} selector={selector} parentId={parentId} documentType={selector.discriminator ? context.siblings?.[selector.discriminator] : undefined} value={value} onChange={onChange} required={required} label={label} onVersions={context.applyVersions} />
      : name === "signature_base64" ? <input className="form-input" type="file" accept="image/*" required={required} onChange={e => { const file=e.target.files?.[0]; if (!file) { onChange(undefined); return; } const reader=new FileReader(); reader.onload=()=>onChange(reader.result); reader.readAsDataURL(file); }} />
      : schema.format === "binary" ? <input className="form-input" type="file" required={required} onChange={e => onChange(e.target.files?.[0])} />
      : schema.type === "boolean" ? <select className="form-input" value={value === undefined ? "" : String(value)} required={required} onChange={e => onChange(e.target.value === "" ? undefined : e.target.value === "true")}><option value="">请选择</option><option value="true">是</option><option value="false">否</option></select>
      : schema.enum ? <select className="form-input" required={required} value={String(value ?? "")} onChange={e => onChange(e.target.value === "" ? undefined : schema.type === "integer" ? Number(e.target.value) : e.target.value)}><option value="">请选择</option>{schema.enum.map(v => <option key={String(v)} value={v}>{String(v)}</option>)}</select>
      : <input className="form-input" aria-label={label} type={schema.format === "date" ? "date" : schema.format === "date-time" ? "datetime-local" : ["number","integer"].includes(schema.type || "") ? "number" : "text"} step={schema.type === "integer" ? "1" : "any"} required={required} value={String(value ?? "")} onChange={e => onChange(e.target.value === "" ? undefined : ["number","integer"].includes(schema.type || "") ? Number(e.target.value) : e.target.value)} />}
  </label>;
}
export default function MinimalActionWorkspace({ modules }: { modules: string[] }) {
  const { user } = useAuth();
  const [actions, setActions] = useState<Action[]>([]), [selected, setSelected] = useState(""), [values, setValues] = useState<Values>({}), [parameters, setParameters] = useState<Values>({}), [message, setMessage] = useState(""), [busy, setBusy] = useState(false);
  const moduleKey = modules.join(",");
  useEffect(() => { let active = true; api.get<{ routes: Action[] }>(`/access/catalog?role=${user?.role || "staff"}`).then(data => { if (active) setActions(data.routes.filter(r => supplierActionEntryVisible(r.id) && r.mode === "business" && r.form && (r.grant_modules || [r.module_key]).some(m => modules.includes(m)) && r.tier !== "view" && hasAction(user,r.id))); }).catch((e: unknown) => { if (active) setMessage(e instanceof Error ? e.message : "读取办理事项失败"); }); return () => { active = false; }; }, [user, moduleKey]); // eslint-disable-line react-hooks/exhaustive-deps
  const action = actions.find(a => a.id === selected), form = action?.form;
  useEffect(()=>{ if (form?.body.properties?.request_key) setValues(old=>({...old,request_key:crypto.randomUUID()})); },[form]);
  useEffect(() => { setSelected(""); setValues({}); setParameters({}); setMessage(""); }, [user]);
  const applyVersions=useCallback((incoming:Values)=>{
    const allowed=Object.fromEntries(Object.entries(incoming).filter(([key])=>key.startsWith("expected_") && form?.body.properties?.[key]));
    if (Object.keys(allowed).length) setValues(old=>({...old,...allowed}));
  },[form]);
  async function submit(event: FormEvent) {
    event.preventDefault(); if (!action || !form || !hasAction(user,action.id)) return;
    setBusy(true); setMessage(""); const token = getToken(), warehouse = getActiveWarehouseId();
    try {
      let endpoint = form.path; const query = new URLSearchParams();
      for (const p of form.parameters) { const v = parameters[p.name]; if (p.in === "path") endpoint = endpoint.replace(`{${p.name}}`,encodeURIComponent(String(v ?? ""))); else if (v !== undefined) query.set(p.name,String(v)); }
      if (query.size) endpoint += `?${query}`;
      const headers = warehouseRequestHeaders(); let body: BodyInit | undefined;
      if (form.media === "multipart/form-data") { const data = new FormData(); for (const [key,value] of Object.entries(values)) if (value !== undefined) {
        if (Array.isArray(value) && form.body.properties?.[key]?.encoding !== "json-string") value.forEach(item => data.append(key,item instanceof File ? item : typeof item === "object" ? JSON.stringify(item) : String(item)));
        else data.append(key,value instanceof File ? value : typeof value === "object" ? JSON.stringify(value) : String(value));
      } body = data; }
      else if (form.media === "application/x-www-form-urlencoded") { const data=new URLSearchParams(); for (const [key,value] of Object.entries(values)) if (value !== undefined) { if (Array.isArray(value)) value.forEach(v=>data.append(key,String(v))); else data.append(key,String(value)); } headers["Content-Type"]=form.media; body=data; }
      else { headers["Content-Type"] = "application/json"; body = JSON.stringify(values); }
      if (["GET","HEAD"].includes(form.method)) body=undefined;
      const response = await fetch(`/api/v1${endpoint}`, { method:form.method, headers, body });
      if (getToken() !== token || warehouse !== getActiveWarehouseId()) throw new Error("账号或仓库已切换，请重新办理");
      const result: { message?: string; detail?: string | { message?: string } } = await response.json();
      if (!response.ok) { if (response.status === 403) window.dispatchEvent(new Event("permissions-changed")); throw new Error(typeof result.detail === "string" ? result.detail : result.detail?.message || "提交被拒绝，请核对授权、填写内容及单据状态"); }
      setMessage(result.message || "办理成功"); setSelected(""); setValues({}); setParameters({});
    } catch (e: unknown) { setMessage(e instanceof Error ? e.message : "办理失败"); } finally { setBusy(false); }
  }
  return <section className="max-w-2xl bg-white rounded-xl p-5 space-y-4"><h1 className="text-xl font-bold">办理事项</h1><p className="text-sm text-gray-600">当前授权允许办理，不包含完整列表查看。请先选择事项及所属单据，再填写办理信息。提交仍会核对当前授权、单据状态和本人限制。</p>
    <label className="block">选择事项<select className="form-input" value={selected} onChange={e => { setSelected(e.target.value); setValues({}); setParameters({}); setMessage(""); }}><option value="">请选择</option>{actions.map(a => <option key={a.id} value={a.id}>{a.form?.label}</option>)}</select></label>
    {form && action && <form onSubmit={submit} className="space-y-3">{form.parameters.map(p => <Field key={p.name} name={p.name} schema={p.schema} required={p.required} value={parameters[p.name]} context={{action,parameters,body:values,applyVersions}} onChange={v => { setParameters(old => ({ ...old,[p.name]:v })); if (p.in === "path") setValues(form.body.properties?.request_key ? {request_key:crypto.randomUUID()} : {}); }} />)}
      {Object.entries(form.body.properties || {}).map(([key,schema]) => action.variants?.field === key ? <label key={key} className="block">办理步骤<select className="form-input" required value={String(values[key] || "")} onChange={e => setValues(old => ({ ...old,[key]:e.target.value }))}><option value="">请选择</option>{Object.entries(action.variants.values).filter(([,v]) => hasAction(user,action.id,v.tier)).map(([v]) => <option key={v} value={v}>{{verify:"核验",approve:"批准",reject:"驳回"}[v] || v}</option>)}</select></label> : <Field key={key} name={key} schema={schema} required={form.body.required?.includes(key)} value={values[key]} context={{action,parameters,body:values,applyVersions}} onChange={v => setValues(old => ({ ...old,[key]:v }))} />)}
      <button type="submit" className="btn-primary min-h-[44px]" disabled={busy}>{busy ? "正在提交…" : "确认提交"}</button></form>}
    <p role="status">{message}</p>{!actions.length && <p>当前没有可办理的管理动作。员工本人事项请从员工自助入口办理。</p>}
  </section>;
}

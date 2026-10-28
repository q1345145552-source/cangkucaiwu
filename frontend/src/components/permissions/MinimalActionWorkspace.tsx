"use client";
import { useEffect, useState, type FormEvent } from "react";
import { api, getToken, getActiveWarehouseId, warehouseRequestHeaders } from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import { hasAction, type ActionTier } from "@/hooks/useActionPermission";
interface Schema { type?: string; title?: string; format?: string; enum?: (string | number)[]; default?: unknown; properties?: Record<string, Schema>; required?: string[]; items?: Schema; anyOf?: Schema[]; allOf?: Schema[] }
interface Parameter { name: string; in: "path" | "query"; required?: boolean; schema: Schema }
interface Contract { label: string; method: string; path: string; parameters: Parameter[]; body: Schema; media: string }
interface Action { id: string; module_key: string; grant_modules?: string[]; tier: ActionTier; mode: string; form?: Contract; variants?: { field: string; values: Record<string, { tier: ActionTier }> } }
interface Choice { id: number; label: string; status?: string; date?: string; employee_id?: number }
type Values = Record<string, unknown>;
const labels: Record<string, string> = { id:"记录编号", employee_id:"员工", account_id:"账户", payment_account_id:"付款账户", record_id:"记录", fund_id:"备用金账户", request_id:"申请编号", leave_id:"请假记录", employee_ids:"员工名单", record_ids:"记录编号列表", item_ids:"明细编号列表", end_date:"截止日期", start_date:"开始日期", leave_date:"请假日期", leave_type:"请假类型", hours:"时数", date:"日期", remark:"备注", reason:"原因", amount:"金额", description:"说明", name:"名称", status:"状态", action:"办理步骤", funding_source:"资金来源", currency:"币种", payment_date:"付款日期", receive_date:"到账日期", signature_base64:"签收凭证", payment_method:"付款方式", warehouse_id:"所属仓库", payroll_id:"工资记录", reimb_id:"报销单", advance_id:"预支单", bill_id:"应付单", plan_id:"付款计划", type:"类型", request_key:"业务请求标识", expense_date:"开销日期", category:"类别", items:"明细", dates:"日期列表", phone:"联系电话", address:"地址", actual_hours:"实际时数", assignments:"人员记录", task_id:"加班任务", reviewed_amount:"审核金额" };
function shape(schema: Schema): Schema { return schema.anyOf?.find(s => s.type !== "null") || schema.allOf?.[0] || schema; }
function Field({ name, schema: original, value, onChange, required, choices }: { name: string; schema: Schema; value: unknown; onChange: (value: unknown) => void; required?: boolean; choices: Choice[] }) {
  const schema = shape(original), label = labels[name] || schema.title || name;
  if (schema.type === "object" || schema.properties) {
    const values = value && typeof value === "object" ? value as Values : {};
    return <fieldset className="space-y-2 border rounded p-3"><legend>{label}</legend>{Object.entries(schema.properties || {}).map(([key, s]) => <Field key={key} name={key} schema={s} value={values[key]} required={schema.required?.includes(key)} choices={choices} onChange={v => onChange({ ...values, [key]: v })} />)}</fieldset>;
  }
  if (schema.type === "array") {
    const values = Array.isArray(value) ? value as unknown[] : [];
    return <fieldset className="border rounded p-3 space-y-2"><legend>{label}{required ? " *" : ""}</legend>{values.map((v, i) => <div key={i}><Field name={name.replace(/s$/, "")} schema={schema.items || { type:"string" }} value={v} onChange={next => onChange(values.map((old,n) => n === i ? next : old))} choices={choices} /><button type="button" className="btn-secondary" onClick={() => onChange(values.filter((_, n) => n !== i))}>移除此项</button></div>)}<button type="button" className="btn-secondary" onClick={() => onChange([...values, undefined])}>添加一项</button></fieldset>;
  }
  const selectChoices = name.endsWith("_id") && name !== "warehouse_id" ? choices : [];
  return <label className="block text-sm">{label}{required ? " *" : "（可空）"}
    {schema.format === "binary" ? <input className="form-input" type="file" required={required} onChange={e => onChange(e.target.files?.[0])} />
      : schema.type === "boolean" ? <select className="form-input" value={value === undefined ? "" : String(value)} required={required} onChange={e => onChange(e.target.value === "" ? undefined : e.target.value === "true")}><option value="">请选择</option><option value="true">是</option><option value="false">否</option></select>
      : schema.enum ? <select className="form-input" required={required} value={String(value ?? "")} onChange={e => onChange(schema.type === "integer" ? Number(e.target.value) : e.target.value)}><option value="">请选择</option>{schema.enum.map(v => <option key={String(v)} value={v}>{String(v)}</option>)}</select>
      : selectChoices.length ? <select className="form-input" required={required} value={String(value ?? "")} onChange={e => onChange(e.target.value ? Number(e.target.value) : undefined)}><option value="">请选择记录</option>{selectChoices.map(c => <option key={c.id} value={c.id}>{c.label} · {c.id} {c.status || ""} {c.date || ""}</option>)}</select>
      : <input className="form-input" aria-label={label} type={schema.format === "date" ? "date" : ["number","integer"].includes(schema.type || "") ? "number" : "text"} step={schema.type === "integer" ? "1" : "any"} required={required} value={String(value ?? "")} onChange={e => onChange(e.target.value === "" ? undefined : ["number","integer"].includes(schema.type || "") ? Number(e.target.value) : e.target.value)} />}
  </label>;
}
export default function MinimalActionWorkspace({ modules }: { modules: string[] }) {
  const { user } = useAuth();
  const [actions, setActions] = useState<Action[]>([]), [selected, setSelected] = useState(""), [values, setValues] = useState<Values>({}), [parameters, setParameters] = useState<Values>({}), [choices, setChoices] = useState<Choice[]>([]), [accountChoices, setAccountChoices] = useState<Choice[]>([]), [employeeChoices, setEmployeeChoices] = useState<Choice[]>([]), [message, setMessage] = useState(""), [busy, setBusy] = useState(false);
  const moduleKey = modules.join(",");
  useEffect(() => { let active = true; api.get<{ routes: Action[] }>(`/access/catalog?role=${user?.role || "staff"}`).then(data => { if (active) setActions(data.routes.filter(r => r.mode === "business" && r.form && (r.grant_modules || [r.module_key]).some(m => modules.includes(m)) && r.tier !== "view" && hasAction(user,r.id))); }).catch((e: unknown) => { if (active) setMessage(e instanceof Error ? e.message : "读取办理事项失败"); }); return () => { active = false; }; }, [user, moduleKey]); // eslint-disable-line react-hooks/exhaustive-deps
  const action = actions.find(a => a.id === selected), form = action?.form;
  useEffect(() => { let active = true; setChoices([]); setAccountChoices([]); setEmployeeChoices([]);
    if (action) for (const kind of ["accounts", "employees"] as const) api.get<{data:Choice[]}>(`/access/choices/${action.module_key}?kind=${kind}`).then(r => { if (active) (kind === "accounts" ? setAccountChoices : setEmployeeChoices)(r.data); }).catch(() => {});
    if (action) api.get<{ data: Choice[] }>(`/access/choices/${action.module_key}`).then(r => { if (active) setChoices(r.data); }).catch(() => {}); return () => { active = false; }; }, [action]);
  async function submit(event: FormEvent) {
    event.preventDefault(); if (!action || !form || !hasAction(user,action.id)) return;
    setBusy(true); setMessage(""); const token = getToken(), warehouse = getActiveWarehouseId();
    try {
      let endpoint = form.path; const query = new URLSearchParams();
      for (const p of form.parameters) { const v = parameters[p.name]; if (p.in === "path") endpoint = endpoint.replace(`{${p.name}}`,encodeURIComponent(String(v ?? ""))); else if (v !== undefined) query.set(p.name,String(v)); }
      if (query.size) endpoint += `?${query}`;
      const headers = warehouseRequestHeaders(); let body: BodyInit;
      if (form.media === "multipart/form-data" || form.media === "application/x-www-form-urlencoded") { const data = new FormData(); for (const [key,value] of Object.entries(values)) if (value !== undefined) data.append(key,value instanceof File ? value : typeof value === "object" ? JSON.stringify(value) : String(value)); body = data; }
      else { headers["Content-Type"] = "application/json"; body = JSON.stringify(values); }
      const response = await fetch(`/api/v1${endpoint}`, { method:form.method, headers, body });
      if (getToken() !== token || warehouse !== getActiveWarehouseId()) throw new Error("账号或仓库已切换，请重新办理");
      const result: { message?: string; detail?: string | { message?: string } } = await response.json();
      if (!response.ok) { if (response.status === 403) window.dispatchEvent(new Event("permissions-changed")); throw new Error(typeof result.detail === "string" ? result.detail : result.detail?.message || "提交被拒绝，请核对授权、填写内容及单据状态"); }
      setMessage(result.message || "办理成功");
    } catch (e: unknown) { setMessage(e instanceof Error ? e.message : "办理失败"); } finally { setBusy(false); }
  }
  return <section className="max-w-2xl bg-white rounded-xl p-5 space-y-4"><h1 className="text-xl font-bold">办理事项</h1><p className="text-sm text-gray-600">当前授权允许办理，不包含完整列表查看。这里只提供必要的编号、名称和状态；金额、凭证和审批条件仍由原业务核对。提交前请确认选中记录和填写内容。</p>
    <label className="block">选择事项<select className="form-input" value={selected} onChange={e => { setSelected(e.target.value); setValues({}); setParameters({}); setMessage(""); }}><option value="">请选择</option>{actions.map(a => <option key={a.id} value={a.id}>{a.form?.label}</option>)}</select></label>
    {form && action && <form onSubmit={submit} className="space-y-3">{form.parameters.map(p => <Field key={p.name} name={p.name} schema={p.schema} required={p.required} value={parameters[p.name]} choices={p.name === "employee_id" ? employeeChoices : ["payment_account_id", "account_id"].includes(p.name) ? accountChoices : choices} onChange={v => setParameters(old => ({ ...old,[p.name]:v }))} />)}
      {Object.entries(form.body.properties || {}).map(([key,schema]) => action.variants?.field === key ? <label key={key} className="block">办理步骤<select className="form-input" required value={String(values[key] || "")} onChange={e => setValues(old => ({ ...old,[key]:e.target.value }))}><option value="">请选择</option>{Object.entries(action.variants.values).filter(([,v]) => hasAction(user,action.id,v.tier)).map(([v]) => <option key={v} value={v}>{{verify:"核验",approve:"批准",reject:"驳回"}[v] || v}</option>)}</select></label> : <Field key={key} name={key} schema={schema} required={form.body.required?.includes(key)} value={values[key]} choices={key === "employee_id" ? employeeChoices : ["payment_account_id", "account_id"].includes(key) ? accountChoices : choices} onChange={v => setValues(old => ({ ...old,[key]:v }))} />)}
      <button type="submit" className="btn-primary min-h-[44px]" disabled={busy}>{busy ? "正在提交…" : "确认提交"}</button></form>}
    <p role="status">{message}</p>{!actions.length && <p>当前没有可办理的管理动作。员工本人事项请从员工自助入口办理。</p>}
  </section>;
}

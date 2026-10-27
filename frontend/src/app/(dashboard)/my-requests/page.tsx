"use client";
import { useEffect, useState } from "react";
import { api, warehouseRequestHeaders } from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
interface RequestRow { id: number; status: string; total_amount?: number; amount?: number; }
interface Source {id:number; name:string; currency:string;}
interface Fund { id: number; currency: string; current_balance: number; }
export default function MyRequestsPage() {
  const { user } = useAuth();
  const [rows, setRows] = useState<RequestRow[]>([]);
  const [debts, setDebts] = useState<RequestRow[]>([]);
  const [funds, setFunds] = useState<Fund[]>([]);
  const [amount, setAmount] = useState("");
  const [reason, setReason] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [receipt, setReceipt] = useState<File | null>(null);
  const [sources, setSources] = useState<{accounts:Source[];funds:Source[];cash_advances:Source[]}>({accounts:[],funds:[],cash_advances:[]});
  const [source, setSource] = useState("");
  const [kind, setKind] = useState("reimbursement");
  async function load() {
    const [r, d, f, choices] = await Promise.all([
      api.get<{data: RequestRow[]}>("/reimbursement?view=self"),
      api.get<{data: RequestRow[]}>("/employee-advances/my-debt"),
      api.get<{data: Fund[]}>("/expense-fund/accounts?view=self"),
      api.get<{accounts:Source[];funds:Source[];cash_advances:Source[]}>("/employee-advances/funding-options?view=self"),
    ]);
    setRows(r.data); setDebts(d.data); setFunds(f.data); setSources(choices);
  }
  useEffect(() => { load().catch(e => setMessage(e.message)); }, [user?.id]);
  async function submit() {
    setBusy(true); setMessage("");
    try {
      const value = Number(amount);
      if (!(value > 0) || !reason.trim()) throw new Error("请填写有效金额和说明");
      const date = new Date().toLocaleDateString("en-CA", {timeZone: "Asia/Bangkok"});
      if (kind === "reimbursement") {
        await api.post("/reimbursement?view=self", {submit_date: date, items: [{category: "其他", amount: value, description: reason}]});
      } else if (kind === "advance") {
        const [funding_source, key] = source.split(":"); const id = Number(key);
        if (!id || !user?.self_employee_id) throw new Error("请明确选择资金来源，并确认本人档案有效");
        const choices = funding_source === "company_account" ? sources.accounts : funding_source === "expense_fund" ? sources.funds : sources.cash_advances;
        const selected = choices.find(a=>a.id===id);
        if (!selected) throw new Error("所选资金来源已变更，请重新选择");
        const field = funding_source === "company_account" ? "payment_account_id" : funding_source === "expense_fund" ? "fund_account_id" : "cash_advance_id";
        await api.post("/employee-advances?view=self", {employee_id:user.self_employee_id,amount:value,advance_date:date,remark:reason,funding_source,currency:selected.currency,[field]:id});
      } else if (kind === "recharge") {
        await api.post("/expense-fund/recharge/request?view=self", {amount: value, reason});
      } else {
        const fund = funds[0];
        if (!fund || !receipt) throw new Error("请先有本人备用金账户，并上传凭证");
        const data = new FormData(); data.append("file", receipt);
        const response = await fetch(`/api/v1/expense-fund/accounts/${fund.id}/upload-receipt?view=self`, {method: "POST", headers: warehouseRequestHeaders(), body: data});
        const result: {receipt?: string; detail?: string} = await response.json();
        if (!response.ok || !result.receipt) throw new Error(result.detail || "凭证上传失败");
        await api.post(`/expense-fund/accounts/${fund.id}/items?view=self`, {expense_date: date, category: "其他", amount: value, currency: fund.currency, description: reason, receipt: result.receipt, request_key: crypto.randomUUID()});
      }
      setMessage("申请已保存，资金批准和执行由独立授权人员办理"); setAmount(""); setReason(""); await load();
    } catch (e) { setMessage(e instanceof Error ? e.message : "申请失败"); }
    finally { setBusy(false); }
  }
  return <div className="space-y-4 max-w-3xl">
    <h1 className="text-xl font-bold">我的申请与欠款</h1>
    <p className="text-sm text-gray-500">仅显示本人资料。申请不会自动批准或付款。</p>
    <section className="card p-4 space-y-3">
      <select aria-label="申请类型" className="form-input min-h-11" value={kind} onChange={e => setKind(e.target.value)}><option value="advance">本人预支申请</option><option value="reimbursement">本人报销</option><option value="recharge">备用金补充申请</option><option value="expense">本人备用金开销</option></select>
      {kind === "advance" && <select aria-label="预支资金来源" className="form-input min-h-11" value={source} onChange={e=>setSource(e.target.value)}><option value="">请选择资金来源</option>{sources.accounts.map(a=><option key={`a${a.id}`} value={`company_account:${a.id}`}>{a.name} · {a.currency}</option>)}{sources.funds.map(a=><option key={`f${a.id}`} value={`expense_fund:${a.id}`}>{a.name} · {a.currency}</option>)}{sources.cash_advances.map(a=><option key={`c${a.id}`} value={`cash_advance:${a.id}`}>{a.name} · {a.currency}</option>)}</select>}
      <input aria-label="金额" className="form-input min-h-11" type="number" value={amount} onChange={e => setAmount(e.target.value)} placeholder="金额"/>
      <input aria-label="说明" className="form-input min-h-11" value={reason} onChange={e => setReason(e.target.value)} placeholder="说明"/>
      {kind === "expense" && <input aria-label="开销凭证" type="file" accept="image/*" onChange={e => setReceipt(e.target.files?.[0] || null)}/>}
      <button className="btn-primary min-h-11" disabled={busy} onClick={submit}>提交本人申请</button>
      <p role="status">{message}</p>
    </section>
    <section className="card p-4"><h2>本人报销</h2>{rows.map(r => <p key={r.id}>#{r.id} · {r.total_amount} · {r.status}</p>)}</section>
    <section className="card p-4"><h2>本人欠款</h2>{debts.map(r => <p key={r.id}>#{r.id} · {r.amount} · {r.status}</p>)}</section>
    <section className="card p-4"><h2>本人备用金</h2>{funds.map(f => <p key={f.id}>{f.current_balance} {f.currency}</p>)}</section>
  </div>;
}

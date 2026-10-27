"use client";
import { balanceWarningText,confirmBalanceWarning } from "@/lib/balanceWarning";
import { useEffect, useState } from "react";
import { api, getActiveWarehouseId, getToken } from "@/lib/api";
import { useToast } from "@/components/ui/Toast";

export interface PaymentReimbursement { id: number; employee_name?: string; total_amount: number; currency: string; is_fund_linked?: string }
interface Account { id: number; account_name: string; account_type: string; currency: string; current_balance: number }
interface Advance { id: number; payer_name: string; currency: string; outstanding_amount: number; available_amount: number }
const money = (v: number) => Number(v || 0).toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export default function ReimbursementPaymentModal({ reimbursement, onClose, onSuccess }: { reimbursement: PaymentReimbursement; onClose: () => void; onSuccess: () => void }) {
  const { toast } = useToast();
  const linked = reimbursement.is_fund_linked === "1";
  const [source, setSource] = useState(linked ? "expense_fund" : "company_account");
  const [accounts, setAccounts] = useState<Account[]>([]), [advances, setAdvances] = useState<Advance[]>([]);
  const [accountId, setAccountId] = useState(""), [advanceId, setAdvanceId] = useState("");
  const [method, setMethod] = useState("cash"), [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(true), [error, setError] = useState("");
  const [fund,setFund]=useState<{current_balance:number;debit_amount:number}|null>(null);
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    let active = true;
    api.get<{ accounts: Account[]; cash_advances: Advance[];fund?:{current_balance:number;debit_amount:number}|null }>(`/reimbursement/payment-sources?reimbursement_id=${reimbursement.id}`).then(result => {
      if (!active) return;
      setAccounts(result.accounts); setAdvances(result.cash_advances);setFund(result.fund||null);
      const preferred = result.accounts.find(a => a.account_type === "cash" || a.account_name.includes("现金")) || result.accounts[0];
      if (preferred) setAccountId(String(preferred.id));
    }).catch((err: any) => { if (active) setError(err.message || "加载付款来源失败"); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [reimbursement.id]);

  async function submit() {
    if (saving || loading || error) return;
    if (source !== "expense_fund" && !file) { toast("error", "请上传付款凭证"); return; }
    if (source === "company_account" && !accounts.some(a => String(a.id) === accountId)) { toast("error", "请选择付款账户"); return; }
    if (source === "cash_advance") {
      const advance = advances.find(a => String(a.id) === advanceId);
      if (!advance) { toast("error", "请选择报销垫款单"); return; }
      if (Number(reimbursement.total_amount) > Number(advance.available_amount)) { toast("error", "垫款单剩余金额不足"); return; }
    }
    setSaving(true);
    try {
      if(source==='company_account'||source==='expense_fund'){
        const fresh=await api.get<any>(`/reimbursement/payment-sources?reimbursement_id=${reimbursement.id}`);
        setFund(fresh.fund||null);setAccounts(fresh.accounts);
        const account=fresh.accounts.find((a:any)=>String(a.id)===accountId);
        if(source==='company_account'&&!account)throw Error('付款账户已变化，请重新选择');
        if(!confirmBalanceWarning(source==='company_account'?account.current_balance:fresh.fund?.current_balance,source==='company_account'?reimbursement.total_amount:fresh.fund?.debit_amount))return;
      }
      let payment_voucher_path = null;
      if (source !== "expense_fund" && file) {
        const body = new FormData(); body.append("file", file); body.append("reimbursement_id", String(reimbursement.id));
        const headers: Record<string, string> = { Authorization: `Bearer ${getToken()}` };
        const warehouse = getActiveWarehouseId(); if (warehouse) headers["X-Warehouse-ID"] = warehouse;
        const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "/api/v1"}/reimbursement/payment-voucher`, { method: "POST", headers, body });
        const upload = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(upload.detail || "付款凭证上传失败");
        payment_voucher_path = upload.path;
      }
      await api.post(`/reimbursement/${reimbursement.id}/pay`, { funding_source: source,
        payment_account_id: source === "company_account" ? Number(accountId) : null,
        cash_advance_id: source === "cash_advance" ? Number(advanceId) : null,
        payment_method: source === "expense_fund" ? "cash" : method, payment_voucher_path });
      toast("success", source === "expense_fund" ? "已确认备用金扣款，不重复记成本和资金" : source === "cash_advance" ? "付款成功，已记录垫款使用，公司归还时记支出" : "付款成功，成本、账户和资金流水已同步");
      onSuccess(); onClose();
    } catch (err: any) { toast("error", err.message || "付款失败"); }
    finally { setSaving(false); }
  }
  const unavailable = source === "company_account" ? !accounts.length : source === "cash_advance" ? !advances.length : false;
  return <div role="dialog" aria-modal="true" aria-labelledby="reimbursement-pay-title" className="fixed inset-0 z-[110] bg-black/40 flex items-center justify-center p-3">
    <form onSubmit={e => { e.preventDefault(); void submit(); }} className="bg-white rounded-2xl w-full max-w-lg max-h-[90dvh] flex flex-col overflow-hidden">
      <h2 id="reimbursement-pay-title" className="font-semibold px-5 py-4 border-b shrink-0">报销付款 #{reimbursement.id}</h2>
      <div className="p-5 overflow-y-auto min-h-0 space-y-4">
        <div className="bg-gray-50 rounded-lg p-3 text-sm space-y-1"><p>报销人：{reimbursement.employee_name || "—"}</p><p>合计金额：<strong>{money(reimbursement.total_amount)} {reimbursement.currency}</strong></p><p>关联备用金：{linked ? "是（新建报销时已扣款）" : "否"}</p></div>
        <fieldset disabled={saving} className="space-y-4 min-w-0">
          <div><p className="text-sm mb-2">资金来源</p><div className="flex flex-wrap gap-3 text-sm">
            {[['company_account', '公司账户'], ['cash_advance', '垫款单'], ['expense_fund', '备用金扣款']].map(([key, label]) => <label key={key} className="flex items-center gap-1"><input type="radio" name="reimbursement-source" value={key} checked={source === key} disabled={linked ? key !== "expense_fund" : key === "expense_fund"} onChange={() => setSource(key)} />{label}</label>)}
          </div></div>
          {source === "company_account" && <div><label className="block text-sm">付款账户<select aria-label="付款账户" className="form-input mt-1" value={accountId} onChange={e => setAccountId(e.target.value)}><option value="">请选择付款账户</option>{accounts.map(a => <option key={a.id} value={a.id}>{a.account_name} · 余额 {money(a.current_balance)} {a.currency}</option>)}</select></label>{!loading && !error && !accounts.length && <p className="text-sm text-red-600 mt-2">还没有可用同币种账户，请先到收款账户里建立或启用</p>}</div>}
          {source === "cash_advance" && <div><label className="block text-sm">报销垫款单<select aria-label="报销垫款单" className="form-input mt-1" value={advanceId} onChange={e => setAdvanceId(e.target.value)}><option value="">请选择报销垫款单</option>{advances.map(a => <option key={a.id} value={a.id}>#{a.id} {a.payer_name} · 未还 {money(a.outstanding_amount)} · 可用 {money(a.available_amount)} {a.currency}</option>)}</select></label>{!loading && !error && !advances.length && <p className="text-sm text-red-600 mt-2">没有已确认且尚未还清的同币种垫款单</p>}<p className="text-xs text-amber-700 mt-2">本次只记录垫款使用，不记公司支出、不扣公司账户、不新增流水；公司归还垫款当天才记支出。剩余未还金额不因报销减少。</p></div>}
          {source === "expense_fund" ? <p className="text-sm text-purple-700 bg-purple-50 rounded-lg p-3">从员工备用金余额里扣，不再需要公司账户。原扣款不重复执行，不新增成本或资金流水。</p> : <>
            <label className="block text-sm">付款方式<select className="form-input mt-1" value={method} onChange={e => setMethod(e.target.value)}><option value="cash">现金</option><option value="transfer">转账</option></select></label>
            <label className="block text-sm">付款凭证（必填）<input aria-label="付款凭证" type="file" accept="image/png,image/jpeg,image/webp" className="block w-full mt-2 text-sm" onChange={e => setFile(e.target.files?.[0] || null)} />{file && <span className="text-xs text-gray-500 break-all">{file.name}</span>}</label>
          </>}
        </fieldset>
        <p role="alert" className="text-sm text-red-600">{source==='company_account'?balanceWarningText(accounts.find(a=>String(a.id)===accountId)?.current_balance,reimbursement.total_amount):source==='expense_fund'?balanceWarningText(fund?.current_balance,fund?.debit_amount):null}</p>
        {loading && <p className="text-sm text-gray-500">正在加载付款来源…</p>}{error && <p className="text-sm text-red-600" role="alert">{error}</p>}
      </div>
      <div className="px-5 py-4 border-t flex justify-end gap-3 shrink-0"><button type="button" disabled={saving} onClick={onClose} className="btn-secondary">取消</button><button type="submit" disabled={saving || loading || !!error || unavailable} className="btn-primary">{saving ? "付款中…" : "确认付款"}</button></div>
    </form>
  </div>;
}

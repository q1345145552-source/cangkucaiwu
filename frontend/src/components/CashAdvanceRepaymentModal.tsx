"use client";
import { useEffect, useState } from "react";
import { api, getActiveWarehouseId, getToken } from "@/lib/api";
import { useToast } from "@/components/ui/Toast";

export interface RepaymentAdvance {
  id: number; payer_name: string; amount: number; repaid_amount: number; outstanding_amount: number; currency: string;
}
interface Account { id: number; account_name: string; account_type: string; currency: string; current_balance: number }
const money = (value: number) => value.toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const today = () => new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Bangkok", year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());

export default function CashAdvanceRepaymentModal({ advance, onClose, onSuccess }: { advance: RepaymentAdvance; onClose: () => void; onSuccess: () => void }) {
  const { toast } = useToast();
  const [accounts, setAccounts] = useState<Account[]>([]), [loading, setLoading] = useState(true), [loadError, setLoadError] = useState(false);
  const [amount, setAmount] = useState(""), [accountId, setAccountId] = useState("");
  const [date, setDate] = useState(today), [method, setMethod] = useState("cash"), [description, setDescription] = useState("");
  const [file, setFile] = useState<File | null>(null), [saving, setSaving] = useState(false);
  const [requestKey] = useState(() => crypto.randomUUID());
  useEffect(() => {
    let active = true;
    api.get<{ data: Account[] }>("/cash-advances/repayment-accounts").then(result => {
      if (!active) return;
      const list = result.data.filter(account => account.currency.toUpperCase() === advance.currency);
      setAccounts(list);
      const preferred = list.find(account => account.account_type === "cash" || account.account_name.includes("现金")) || list[0];
      if (preferred) setAccountId(String(preferred.id));
    }).catch((err: any) => { if (active) { setLoadError(true); toast("error", err.message || "加载归还账户失败"); } })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  async function submit() {
    if (saving) return;
    if (!Number.isFinite(Number(amount)) || Number(amount) <= 0) { toast("error", "归还金额必须大于零"); return; }
    if (Number(amount) > advance.outstanding_amount) { toast("error", "不能超过剩余未还"); return; }
    if (!date) { toast("error", "请选择归还日期"); return; }
    if (!accountId) { toast("error", "请选择归还账户"); return; }
    if (!file) { toast("error", "请上传归还凭证照片"); return; }
    setSaving(true);
    try {
      const body = new FormData(); body.append("file", file);
      const headers: Record<string, string> = { Authorization: `Bearer ${getToken()}` };
      const warehouse = getActiveWarehouseId(); if (warehouse) headers["X-Warehouse-ID"] = warehouse;
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "/api/v1"}/cash-advances/repayment-voucher`, { method: "POST", headers, body });
      const upload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(upload.detail || "凭证照片上传失败");
      await api.post(`/cash-advances/${advance.id}/repayments`, { repayment_date: date, amount, account_id: Number(accountId),
        payment_method: method, voucher_path: upload.path, description: description.trim() || null, request_key: requestKey });
      toast("success", "归还成功，已记资金流水，不计入成本"); onSuccess(); onClose();
    } catch (err: any) { toast("error", err.message || "归还失败"); }
    finally { setSaving(false); }
  }
  const selected = accounts.find(account => String(account.id) === accountId);
  const currencyLabel = advance.currency === "CNY" ? "人民币" : "泰铢";
  return <div role="dialog" aria-modal="true" aria-labelledby="repayment-title" className="fixed inset-0 z-[110] bg-black/40 flex items-center justify-center p-3">
    <form onSubmit={event => { event.preventDefault(); void submit(); }} className="bg-white rounded-2xl w-full max-w-lg max-h-[90dvh] flex flex-col overflow-hidden">
      <h2 id="repayment-title" className="font-semibold px-5 py-4 border-b shrink-0">归还垫款 #{advance.id}</h2>
      <div className="p-5 space-y-4 overflow-y-auto min-h-0">
        <div className="bg-gray-50 rounded-lg p-3 text-sm space-y-1"><p>垫款人：{advance.payer_name}</p><p>垫款 {money(advance.amount)} · 已还 {money(advance.repaid_amount)}</p><p>剩余未还 <strong>{money(advance.outstanding_amount)}</strong> {currencyLabel}</p></div>
        <fieldset disabled={saving} className="space-y-4 min-w-0">
          <label className="block text-sm">归还日期<input type="date" className="form-input mt-1" value={date} onChange={event => setDate(event.target.value)} /></label>
          <div><div className="flex justify-between mb-1"><label htmlFor="repayment-amount" className="text-sm">本次金额</label><button type="button" className="text-sm text-blue-600" onClick={() => setAmount(String(advance.outstanding_amount))}>全额归还</button></div><input id="repayment-amount" type="number" step="0.01" className="form-input" value={amount} onChange={event => setAmount(event.target.value)} /></div>
          <label className="block text-sm">归还账户<select aria-label="归还账户" className="form-input mt-1" value={accountId} disabled={loading} onChange={event => setAccountId(event.target.value)}><option value="">请选择归还账户</option>{accounts.map(account => <option key={account.id} value={account.id}>{account.account_name} · 余额 {money(account.current_balance)} {account.currency}</option>)}</select></label>
          {loading ? <p className="text-xs text-gray-500">正在加载账户...</p> : loadError ? <p className="text-sm text-red-600">账户加载失败，请关闭后重试</p> : !accounts.length && <p className="text-sm text-red-600">还没有可用{currencyLabel}账户，请先到收款账户里建一个</p>}
          {selected && <p className="text-xs text-gray-500">当前账户余额：{money(selected.current_balance)} {currencyLabel}</p>}
          <label className="block text-sm">付款方式<select className="form-input mt-1" value={method} onChange={event => setMethod(event.target.value)}><option value="cash">现金</option><option value="transfer">转账</option></select></label>
          <label className="block text-sm">归还凭证照片（必填）<input aria-label="归还凭证照片" type="file" accept="image/png,image/jpeg,image/webp" className="block w-full mt-2 text-sm" onChange={event => setFile(event.target.files?.[0] || null)} />{file && <span className="block mt-1 break-all text-gray-500">{file.name}</span>}</label>
          <label className="block text-sm">归还说明<textarea className="form-input mt-1" rows={3} maxLength={2000} value={description} onChange={event => setDescription(event.target.value)} /></label>
        </fieldset>
      </div>
      <div className="px-5 py-4 border-t flex justify-end gap-3 shrink-0"><button type="button" disabled={saving} onClick={onClose} className="btn-secondary">取消</button><button type="submit" disabled={saving || loading || loadError || !accounts.length} className="btn-primary">{saving ? "归还中..." : "确认归还"}</button></div>
    </form>
  </div>;
}

"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

export default function WalletAccountSelect({ value, onChange, currency = "THB", label = "付款账户" }: {
  value: number; onChange: (id: number) => void; currency?: string; label?: string;
}) {
  const [accounts, setAccounts] = useState<any[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let active = true;
    api.get<any>("/accounts").then(r => { if (active) setAccounts(r.data || []); })
      .catch(() => { if (active) setError("账户加载失败，请关闭后重试"); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);
  const available = accounts.filter(a => a.status !== "inactive" && (a.currency || "THB") === currency);
  useEffect(() => {
    if (loading) return;
    if (!available.some(a => a.id === value)) {
      const first = available.find(a => a.account_type === "cash") || available.find(a => /现金/.test(a.account_name)) || available[0];
      onChange(first?.id || 0);
    }
  }, [accounts, currency, loading]);
  return <div className="form-group">
    <label className="form-label">{label} <span className="text-red-500">*</span></label>
    <select className="form-input" aria-label={label} value={value} onChange={e => onChange(+e.target.value)} disabled={loading || !!error}>
      <option value={0}>{loading ? "加载中…" : "请选择账户"}</option>
      {available.map(a => <option key={a.id} value={a.id}>{a.account_name}（{currency}）</option>)}
    </select>
    {!loading && (error || available.length === 0) && <p className="text-xs text-red-600 mt-1">{error || "没有可用的同币种账户，请先到收款账户里新建"}</p>}
  </div>;
}

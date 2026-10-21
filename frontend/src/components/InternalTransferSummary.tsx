import { fmtMoney } from "@/lib/currency";

export interface TransferSummary {
  by_currency: Record<string, number>;
  count_by_currency: Record<string, number>;
  scope_label: string;
}

export default function InternalTransferSummary({ data }: { data?: TransferSummary }) {
  if (!data) return null;
  return <div aria-label="内部转账（不计入收支）" className="my-3 rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm text-slate-700">
    <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
      <strong>内部转账 <span className="font-normal">（不计入收支）</span></strong>
      {Array.from(new Set(["THB", "CNY", ...Object.keys(data.by_currency)])).map(currency => <span key={currency} className="whitespace-nowrap">
        {currency} {fmtMoney(data.by_currency[currency] || 0, currency)}（{data.count_by_currency[currency] || 0}笔）
      </span>)}
    </div>
    <p className="mt-1 text-xs text-slate-500">{data.scope_label}；每笔只计一次，不计入收入、支出、净收支或成本。</p>
  </div>;
}

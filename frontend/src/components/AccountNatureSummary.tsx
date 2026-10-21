"use client";

export type AccountNatureBalance = {
  cash_balance: number; corporate_balance: number; classified_wallet_balance: number;
  unclassified_balance: number; unclassified_account_count: number;
  wallet_total_complete: boolean; wallet_actual_balance: number | null; all_account_balance: number;
};

export default function AccountNatureSummary({ balances }: { balances: Record<string, AccountNatureBalance> }) {
  if (!Object.keys(balances).length) return null;
  const amount = (value: number, currency: string) => `${currency === "THB" ? "฿" : currency === "CNY" ? "¥" : currency + " "}${value.toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  return <section aria-label="老板钱包账户余额" className="card p-4 mb-4">
    <h2 className="font-semibold mb-1">老板钱包余额</h2>
    <p className="text-xs text-gray-500 mb-3">现金户和企业户都属于老板钱包，按真实账户余额相加，各币种分开。包含停用账户的余额；备用金另记台账，不在本组重复相加。</p>
    <div className="grid gap-3 md:grid-cols-2">
      {Object.entries(balances).map(([currency, group]) => <div key={currency} aria-label={`${currency}账户性质汇总`} className="border rounded-xl p-3 space-y-2">
        <h3 className="text-sm font-semibold">{currency === "THB" ? "泰铢" : currency === "CNY" ? "人民币" : currency}（{currency}）</h3>
        <p className="text-sm">现金户 {amount(group.cash_balance, currency)} ＋ 企业户 {amount(group.corporate_balance, currency)}</p>
        <p className="font-semibold">{group.wallet_total_complete ? "老板钱包实际余额" : "已分类钱包小计"} {amount(group.wallet_total_complete ? group.wallet_actual_balance! : group.classified_wallet_balance, currency)}</p>
        {group.unclassified_account_count > 0 && <div className="text-sm text-amber-800 bg-amber-50 rounded-lg p-2">
          <p>未分类账户余额 {amount(group.unclassified_balance, currency)}（{group.unclassified_account_count} 户）</p>
          <p>存在未分类账户，完整老板钱包余额尚未确认。</p>
          <p>全部收款账户余额 {amount(group.all_account_balance, currency)}，请先确认旧账户性质。</p>
        </div>}
      </div>)}
    </div>
  </section>;
}

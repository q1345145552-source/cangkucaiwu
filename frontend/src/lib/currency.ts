// 币种符号与格式化工具（不做换算，按记录币种显示）
export function currencySymbol(c?: string): string {
  if (c === "CNY") return "¥";
  if (c === "THB") return "฿";
  return "";
}

export function fmtMoney(amount?: number, currency?: string): string {
  return `${currencySymbol(currency)}${(amount ?? 0).toLocaleString()}`;
}

// 把 {THB: x, CNY: y} 格式化成 "฿x + ¥y"
export function fmtMoneyByCurrency(map?: Record<string, number>): string {
  const parts: string[] = [];
  for (const [c, v] of Object.entries(map || {})) {
    if (v) parts.push(fmtMoney(v, c));
  }
  return parts.length ? parts.join(" + ") : "-";
}

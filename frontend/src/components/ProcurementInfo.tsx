"use client";
import Link from "next/link";
import { fmtMoney } from "@/lib/currency";

export const billStatus: Record<string,string> = { pending:"待付", paid:"已付清", partially_paid:"部分付款", overdue:"逾期", voided:"已作废" };
export function LinkedPayable({ order }: { order: any }) {
  const b = order.bill;
  return <section className="rounded-lg border p-3 text-sm space-y-2" aria-label="关联应付">
    <h3 className="font-semibold">关联应付账单</h3>
    {b ? <>
      <Link className="text-blue-600 underline" href={`/payable?bill_id=${b.id}`}>查看应付 {b.bill_number}</Link>
      <p>账单状态：{billStatus[b.status] || b.status || "状态未记录"}{b.need_boss_confirm === "true" ? "；待老板确认收货差异" : ""}</p>
      <p>应付总额 {fmtMoney(b.amount,b.currency)} · 累计已付 {b.paid_amount == null ? "未记录" : fmtMoney(b.paid_amount,b.currency)} · 剩余应付 {b.remaining_amount == null ? "待核对" : fmtMoney(b.remaining_amount,b.currency)}</p>
      {(b.warnings || []).map((w:string) => <p key={w} className="text-red-600">{w}</p>)}
    </> : <p className="text-amber-700">{order.bill_message || "关联信息未取得，请重试"}</p>}
  </section>;
}
export function PurchaseQuantities({ order }: { order: any }) {
  return <div className="overflow-x-auto"><table className="w-full text-sm min-w-[680px]">
    <thead><tr>{["产品","规格","订购数量","当前已记录实收","数量差异","单价","小计"].map(x => <th className="p-2 text-left" key={x}>{x}</th>)}</tr></thead>
    <tbody>{(order.items || []).map((it:any,i:number) => <tr className="border-t" key={i}>
      <td className="p-2">{it.product_name || "产品未记录"}</td><td className="p-2">{it.spec || "—"}</td>
      <td className="p-2">{it.quantity ?? "未记录"}</td><td className="p-2">{it.received_quantity ?? "尚未记录实收"}</td><td className="p-2">{it.diff_quantity ?? "尚未记录差异"}</td>
      <td className="p-2">{it.unit_price == null ? "未记录" : fmtMoney(it.unit_price,order.currency)}</td><td className="p-2">{it.subtotal == null ? "未记录" : fmtMoney(it.subtotal,order.currency)}</td>
    </tr>)}</tbody>
  </table>{!order.items?.length && <p>采购明细未记录</p>}</div>;
}

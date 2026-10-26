"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { LinkedPayable, PurchaseQuantities } from "@/components/ProcurementInfo";
import { fmtMoney } from "@/lib/currency";

export default function PurchaseOrderPage({params}:{params:{id:string}}) {
  const [order,setOrder]=useState<any>(null),[error,setError]=useState("");
  useEffect(()=>{let active=true;setOrder(null);setError("");api.get<any>(`/suppliers/purchase-orders/${params.id}`)
    .then(x=>{if(active)setOrder(x);}).catch(e=>{if(active)setError(e.message || "采购单读取失败");});return()=>{active=false;};},[params.id]);
  return <div className="card p-4 space-y-4"><h1 className="page-title">采购单详情 {order?.order_number}</h1>
    {error ? <p role="alert" className="text-red-600">{error}</p> : !order ? <p>加载中</p> : <>
      <p>供应商：{order.supplier_name} · 币种：{order.currency}</p>
      <p>采购状态：{({pending:"待审批",confirmed:"已生效",rejected:"已驳回"} as Record<string,string>)[order.status] || order.status || "未记录"}</p>
      <p>收货状态：{({not_received:"未收货",received:"已收货",partially_received:"收货有差异"} as Record<string,string>)[order.receipt_status] || "尚未记录收货"}</p>
      <PurchaseQuantities order={order}/><p>采购总额：{fmtMoney(order.total_amount,order.currency)}</p><LinkedPayable order={order}/>
      <p className="text-xs text-gray-500">此页仅查看，不自动收货、确认或付款</p>
    </>}
    <Link className="text-blue-600" href="/payable">返回应付账款</Link>
  </div>;
}

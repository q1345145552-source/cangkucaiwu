"use client";
const columns=[['origin','起点'],['destination','终点'],['transport_method','运输方式'],['quantity_from','重量或体积起'],['quantity_to','重量或体积止'],['pricing_unit','计量单位'],['unit_price','单价'],['currency','币种'],['transit_days','时效天数'],['minimum_charge','最低收费'],['remark','备注']];
export default function SupplierRouteQuoteTable({rows}:{rows:any[]}){
 return <section className="mt-5 space-y-2"><h3 className="font-medium">路线报价（kg / 方 / 件独立计量）</h3><p className="text-xs text-gray-500">保留原始计量单位、区间和最低收费；不套用旧每方报价计算，不自动换算或覆盖旧报价。</p><div className="overflow-x-auto touch-pan-x"><table className="w-full text-sm min-w-[1000px]"><thead><tr>{columns.map(([key,label])=><th key={key} className="p-2 text-left">{label}</th>)}</tr></thead><tbody>{rows.map(row=><tr key={row.id} className="border-t">{columns.map(([key])=><td className="p-2" key={key}>{row[key]??'—'}</td>)}</tr>)}</tbody></table>{!rows.length&&<p className="text-sm text-gray-500 p-3">暂无路线报价，可使用独立物流模板导入</p>}</div></section>;
}

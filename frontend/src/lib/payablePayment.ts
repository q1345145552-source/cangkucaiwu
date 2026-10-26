import { getActiveWarehouseId, warehouseRequestHeaders } from "@/lib/api";

type Payload = { paid_amount: number; account_id: number; payment_method: string };
const flights = new Map<string, Promise<any>>();
export type PayableScope = { userId: number; warehouseId: string };
export type PayableVoucherTask = { billId: number; file: File; scope: PayableScope };
export function payableScope(): PayableScope {
  const user = JSON.parse(localStorage.getItem("user") || "{}");
  const warehouseId = String(getActiveWarehouseId() || user.warehouse_id || "");
  if (!user.id || !warehouseId || warehouseId === "all") throw Error("请选择单个仓库后操作");
  return { userId: user.id, warehouseId };
}
function sameScope(a: PayableScope, b: PayableScope) {
  return a.userId === b.userId && a.warehouseId === b.warehouseId;
}
function slot(billId: number) {
  const user = JSON.parse(localStorage.getItem("user") || "{}");
  return `payable-payment:${user.id}:${getActiveWarehouseId() || user.warehouse_id}:${billId}`;
}
export function pendingPayablePayment(billId: number): { key: string; payload: Payload } | null {
  const raw = sessionStorage.getItem(slot(billId));
  if (!raw) return null;
  const op = JSON.parse(raw);
  if (!op.key || !op.payload || !(op.payload.paid_amount > 0) || !op.payload.account_id) throw Error("付款请求草稿异常，请先核对记录");
  return op;
}
export function payableHeaders(scope?: PayableScope) {
  if (scope && !sameScope(scope, payableScope())) throw Error("请切回原账号和原仓库后仅重传凭证");
  const headers = warehouseRequestHeaders();
  if (scope) headers["X-Warehouse-ID"] = scope.warehouseId;
  return headers;
}
export async function submitPayablePayment(billId: number, payload: Payload) {
  const storage = slot(billId), prior = pendingPayablePayment(billId);
  if (prior && JSON.stringify(prior.payload) !== JSON.stringify(payload)) throw Error("上一笔付款结果待确认，请恢复原金额、账户和方式重试");
  const op = prior || { key: crypto.randomUUID(), payload };
  try { sessionStorage.setItem(storage, JSON.stringify(op)); }
  catch { throw Error("无法保存付款请求编号，请恢复浏览器存储后重试"); }
  const running = flights.get(storage); if (running) return running;
  const headers = payableHeaders();
  const task = (async () => {
    const params = new URLSearchParams({ ...Object.fromEntries(Object.entries(payload).map(([k,v]) => [k,String(v)])), request_key: op.key });
    let response: Response;
    try { response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "/api/v1"}/payable/${billId}/pay?${params}`, { method: "PUT", headers }); }
    catch { throw Error("付款结果待确认，原请求编号已保留，请恢复网络后重试同一笔"); }
    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      // A denied retry cannot prove that the earlier unknown attempt did not commit.
      if (!prior && [400,403,404,422].includes(response.status)) sessionStorage.removeItem(storage);
      throw Error(err.detail || "付款结果待确认，请用同一请求重试");
    }
    let result: any;
    try { result = await response.json(); } catch { throw Error("付款结果待确认，返回内容未完整收到，请重试同一请求"); }
    if (!result.payment_id) throw Error("付款结果待确认，请用同一请求重试");
    sessionStorage.removeItem(storage);
    return result;
  })();
  flights.set(storage, task);
  try { return await task; } finally { if (flights.get(storage) === task) flights.delete(storage); }
}

export async function uploadPayableVoucher(billId: number, file: File, scope?: PayableScope) {
  const body = new FormData(); body.append("file", file);
  const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "/api/v1"}/payable/${billId}/upload-voucher`, { method: "POST", headers: payableHeaders(scope), body });
  const result = await response.json().catch(() => ({}));
  if (!response.ok) throw Error(result.detail || "凭证上传失败");
  return result;
}

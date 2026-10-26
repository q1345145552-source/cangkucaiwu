import { getToken, getActiveWarehouseId,ApiError } from "@/lib/api";

export type WalletOperationKind = "income" | "expense" | "transfer";
type Payload = Record<string, any>;
type Operation = { key: string; payload: Payload };
const inFlight = new Map<string, Promise<any>>();

function storageKey(kind: WalletOperationKind) {
  const user = JSON.parse(localStorage.getItem("user") || "{}");
  return `wallet-operation:${user.id || "unknown"}:${getActiveWarehouseId() || user.warehouse_id || "default"}:${kind}`;
}

export function pendingWalletOperation(kind: WalletOperationKind): Operation | null {
  const raw = sessionStorage.getItem(storageKey(kind));
  if (!raw) return null;
  try {
    const op = JSON.parse(raw);
    if (!/^[A-Za-z0-9_-]{1,64}$/.test(op.key) || !op.payload || typeof op.payload !== "object") throw Error();
    return op;
  } catch { throw new Error("上次收付草稿无法读取，请先核对记录后处理浏览器存储"); }
}

function normalized(kind: WalletOperationKind, source: Payload) {
  const keys = kind === "transfer" ? ["from_account_id", "to_account_id", "amount", "transfer_date", "remark"]
    : ["category_id", "account_id", "customer_id", "supplier_id", "amount", "currency", `${kind}_date`, "remark", "voucher",...(kind==="expense"?["invoice_identity"]:[])];
  const payload: Payload = {};
  for (const key of keys) if (source[key] !== undefined && source[key] !== null) {
    payload[key] = key==="invoice_identity" ? JSON.stringify(source[key]) : ["amount", "category_id", "account_id", "customer_id", "supplier_id", "from_account_id", "to_account_id"].includes(key) ? Number(source[key]) : source[key];
  }
  return payload;
}

function remember(kind: WalletOperationKind, payload: Payload) {
  const prior = pendingWalletOperation(kind);
  if (prior && JSON.stringify(prior.payload) !== JSON.stringify(payload)) {
    throw new Error("上一笔收付结果待确认，请重新打开录入弹窗恢复原内容重试");
  }
  const op = prior || { key: crypto.randomUUID(), payload };
  try { sessionStorage.setItem(storageKey(kind), JSON.stringify(op)); }
  catch { throw new Error("无法保存本次收付请求编号，请恢复浏览器存储后重试"); }
  return op;
}

function forget(kind: WalletOperationKind, key: string) {
  if (pendingWalletOperation(kind)?.key === key) sessionStorage.removeItem(storageKey(kind));
}

export async function submitWalletOperation(kind: WalletOperationKind, source: Payload, files: File[] = [],costConfirmation?:any) {
  const payload = normalized(kind, source);
  if(kind==="expense"&&files.length)payload.attachments=files.map(f=>({name:f.name,size:f.size,lastModified:f.lastModified}));
  const op = remember(kind, payload); // Persist before sending money; uncertain retries reuse the key.
  const originalScope=storageKey(kind);
  const flightKey = storageKey(kind) + ":" + op.key;
  const running = inFlight.get(flightKey);
  if (running) return running;
  const task = (async () => {
    const headers: Record<string, string> = {};
    const token = getToken(); if (token) headers.Authorization = `Bearer ${token}`;
    const warehouse = getActiveWarehouseId(); if (warehouse !== null) headers["X-Warehouse-ID"] = warehouse;
    let body: FormData | string;
    if (kind === "expense") {
      const form = new FormData();
      Object.entries(payload).filter(([key])=>key!=="attachments").forEach(([key, value]) => form.append(key, String(value)));
      if(costConfirmation)form.append("cost_confirmation",JSON.stringify(costConfirmation));
      form.append("request_key", op.key); files.forEach(file => form.append("files", file)); body = form;
    } else { headers["Content-Type"] = "application/json"; body = JSON.stringify({ ...payload, request_key: op.key }); }
    const path = kind === "transfer" ? "/accounts/transfers" : `/income-expense/${kind}`;
    const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "/api/v1"}${path}`, { method: "POST", headers, body });
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      if ([400, 422].includes(response.status) || (response.status===409&&String(error.detail?.code||"").startsWith("cost_"))) forget(kind, op.key);
      throw new ApiError(response.status,error.detail || "收付款未完成，请重试同一笔");
    }
    const result = await response.json();
    if(kind==="expense"&&originalScope!==storageKey(kind))throw Error("账号或仓库已变化，请回到原仓核对原登记；原请求已保留");
    forget(kind, op.key);
    return result;
  })();
  inFlight.set(flightKey, task);
  try { return await task; }
  finally { if (inFlight.get(flightKey) === task) inFlight.delete(flightKey); }
}

const API_URL = process.env.NEXT_PUBLIC_API_URL || "/api/v1";

export interface MessageResponse {
  message?: string;
}

export class ApiError extends Error {
  constructor(public status:number, public detail:any) {
    super(typeof detail === "string" ? detail : detail?.message || `HTTP ${status}`);
  }
}

let token: string | null = null;
let lastDeniedAction = "";
if (typeof window !== "undefined") {
  token = localStorage.getItem("token");
}

export function setToken(t: string) {
  token = t;
  if (typeof window !== "undefined") {
    localStorage.setItem("token", t);
  }
}

export function getToken(): string | null {
  if (typeof window !== "undefined") token = localStorage.getItem("token");
  return token;
}

export function clearToken() {
  token = null;
  if (typeof window !== "undefined") {
    localStorage.removeItem("token");
    localStorage.removeItem("user");
    localStorage.removeItem("activeWarehouseId");
    sessionStorage.removeItem("activeWarehouseId");
    sessionStorage.removeItem("activeWarehouseToken");
  }
}

// Active warehouse management
export const getActiveWarehouseId: () => string | null = (() => {
  if (typeof window !== "undefined") localStorage.removeItem("activeWarehouseId");
  return () => {
    if (typeof window !== "undefined") {
      const warehouse = sessionStorage.getItem("activeWarehouseId");
      if (warehouse === null) return null;
      let belongsToCachedUser = true;
      try {
        const cached = JSON.parse(localStorage.getItem("user") || "null");
        // Cached membership may only discard a selection; the server still authorizes every request.
        if (warehouse !== "all" && Array.isArray(cached?.warehouses)) {
          belongsToCachedUser = cached.warehouses.some((item: { id: number }) => String(item.id) === warehouse);
        }
      } catch { belongsToCachedUser = false; }
      if (sessionStorage.getItem("activeWarehouseToken") !== getToken() || !belongsToCachedUser) {
        sessionStorage.removeItem("activeWarehouseId");
        sessionStorage.removeItem("activeWarehouseToken");
        return null;
      }
      return warehouse;
    }
    return null;
  };
})();

// Native downloads and FormData requests need the same selected warehouse as JSON requests.
export function warehouseRequestHeaders(): Record<string, string> {
  const headers: Record<string, string> = { Authorization: `Bearer ${getToken()}` };
  const warehouse = getActiveWarehouseId();
  if (warehouse !== null) headers["X-Warehouse-ID"] = warehouse;
  return headers;
}

export function setActiveWarehouseId(id: string | number | null) {
  if (typeof window !== "undefined") {
    getActiveWarehouseId();
    if (id !== null && id !== undefined) {
      sessionStorage.setItem("activeWarehouseId", String(id));
      sessionStorage.setItem("activeWarehouseToken", getToken() || "");
    } else {
      sessionStorage.removeItem("activeWarehouseId");
      sessionStorage.removeItem("activeWarehouseToken");
    }
  }
}

// 全局错误事件，Toast 组件可监听
export function showGlobalToast(type: "success" | "error", message: string) {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent("global-toast", { detail: { type, message } }));
  }
}

async function request<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  const requestToken = getToken();
  if (requestToken) {
    headers["Authorization"] = `Bearer ${requestToken}`;
  }
  // 告知后端当前语言，后端据此返回对应语言的提示消息
  if (typeof window !== "undefined") {
    let labor = false;
    try { labor = JSON.parse(localStorage.getItem("user") || "{}").role === "warehouse_labor"; } catch {}
    const personal = ["/clock-in", "/my-payslip", "/my-attendance", "/my-overtime", "/my-leave"].includes(window.location.pathname)
      || (["/attendance", "/overtime"].includes(window.location.pathname) && labor);
    headers["X-Language"] = (personal ? localStorage.getItem("employee-locale") || (localStorage.getItem("locale") === "th" ? "th" : "my") : localStorage.getItem("locale")) || "zh";
  }
  // Add X-Warehouse-ID header (including "all" for total warehouse mode)
  const whId = getActiveWarehouseId();
  if (whId !== null) {
    headers["X-Warehouse-ID"] = whId;
  }
  const requestWarehouse = getActiveWarehouseId();
  const res = await fetch(`${API_URL}${endpoint}`, { ...options, headers });
  if (requestToken !== getToken() || requestWarehouse !== getActiveWarehouseId()) throw new ApiError(409, "账号或仓库已切换，请重新加载");
  if (res.status === 401) {
    clearToken();
    if (typeof window !== "undefined") {
      window.location.href = "/login";
    }
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Request failed" }));
    if (res.status === 403 && err.detail?.required_tier && typeof window !== "undefined") {
      const denied = `${requestToken}:${err.detail.action}:${err.detail.required_tier}`;
      if (denied !== lastDeniedAction) { lastDeniedAction = denied; window.dispatchEvent(new Event("permissions-changed")); }
    }
    let msg = err.detail || `HTTP ${res.status}`;
    if (Array.isArray(err.detail)) {
      msg = err.detail.map((e: any) => {
        const field = e.loc ? e.loc[e.loc.length - 1] : "";
        return field ? `${field}: ${e.msg}` : e.msg;
      }).join("; ");
    }
    throw new ApiError(res.status,Array.isArray(err.detail) ? msg : err.detail || msg);
  }
  const result = await res.json();
  if (requestToken !== getToken() || requestWarehouse !== getActiveWarehouseId()) throw new ApiError(409, "账号或仓库已切换，请重新加载");
  return result;
}

export const api = {
  get: <T>(endpoint: string) => request<T>(endpoint),
  post: <T>(endpoint: string, data?: unknown) =>
    request<T>(endpoint, { method: "POST", body: JSON.stringify(data) }),
  put: <T>(endpoint: string, data?: unknown) =>
    request<T>(endpoint, { method: "PUT", body: JSON.stringify(data) }),
  delete: <T>(endpoint: string, data?: unknown) =>
    request<T>(endpoint, { method: "DELETE", body: data === undefined ? undefined : JSON.stringify(data) }),
};

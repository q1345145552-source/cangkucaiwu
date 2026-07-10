const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

let token: string | null = null;
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
  return token;
}

export function clearToken() {
  token = null;
  if (typeof window !== "undefined") {
    localStorage.removeItem("token");
    localStorage.removeItem("user");
    localStorage.removeItem("activeWarehouseId");
  }
}

// Active warehouse management
export function getActiveWarehouseId(): string | null {
  if (typeof window !== "undefined") {
    return localStorage.getItem("activeWarehouseId");
  }
  return null;
}

export function setActiveWarehouseId(id: string | number | null) {
  if (typeof window !== "undefined") {
    if (id !== null && id !== undefined) {
      localStorage.setItem("activeWarehouseId", String(id));
    } else {
      localStorage.removeItem("activeWarehouseId");
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
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  // Add X-Warehouse-ID header (including "all" for total warehouse mode)
  const whId = getActiveWarehouseId();
  if (whId !== null) {
    headers["X-Warehouse-ID"] = whId;
  }
  const res = await fetch(`${API_URL}${endpoint}`, { ...options, headers });
  if (res.status === 401) {
    clearToken();
    if (typeof window !== "undefined") {
      window.location.href = "/login";
    }
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Request failed" }));
    let msg = err.detail || `HTTP ${res.status}`;
    if (Array.isArray(err.detail)) {
      msg = err.detail.map((e: any) => {
        const field = e.loc ? e.loc[e.loc.length - 1] : "";
        return field ? `${field}: ${e.msg}` : e.msg;
      }).join("; ");
    }
    throw new Error(msg);
  }
  return res.json();
}

export const api = {
  get: <T>(endpoint: string) => request<T>(endpoint),
  post: <T>(endpoint: string, data?: unknown) =>
    request<T>(endpoint, { method: "POST", body: JSON.stringify(data) }),
  put: <T>(endpoint: string, data?: unknown) =>
    request<T>(endpoint, { method: "PUT", body: JSON.stringify(data) }),
  delete: <T>(endpoint: string) =>
    request<T>(endpoint, { method: "DELETE" }),
};

"use client";
import { createContext, useContext, useState, useEffect, useRef, type ReactNode } from "react";
import { isAuthUser, type AuthUser, type LoginResponse } from "@/types/auth";
import { useRouter } from "next/navigation";
import { api, setToken, clearToken, getToken, setActiveWarehouseId } from "@/lib/api";

interface AuthContextValue {
  user: AuthUser | null;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  isAuthenticated: boolean;
  loading: boolean;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);
  const verifiedToken = useRef<string | null>(null);
  const sessionEpoch = useRef(0);
  const router = useRouter();

  function updateIdentity(next: AuthUser | null, token: string | null) {
    verifiedToken.current = next ? token : null;
    setUser(next);
    if (next) localStorage.setItem("user", JSON.stringify(next));
  }

  useEffect(() => {
    // Cached role/menu grants are not authorization. Wait for a live /me response.
    let active = true;
    let requestVersion = 0;
    let publishing = false;
    const publishIdentity = (next: AuthUser | null, token: string | null) => {
      updateIdentity(next, token);
      publishing = true;
      try {
        window.dispatchEvent(new CustomEvent("auth-user-refreshed", { detail: next }));
      } finally {
        publishing = false;
      }
    };
    const refresh = (event: Event) => {
      if (publishing || !("detail" in event)) return;
      const refreshed: unknown = event.detail;
      if (refreshed === null || isAuthUser(refreshed)) {
        ++requestVersion;
        const token = getToken();
        updateIdentity(refreshed?.is_active && token ? refreshed : null, token);
        setLoading(false);
      }
    };
    const refreshFromServer = async (invalidate: boolean, refreshAttachment = true) => {
      const token = getToken();
      const epoch = sessionEpoch.current;
      const version = ++requestVersion;
      const isCurrent = () => active && version === requestVersion
        && epoch === sessionEpoch.current && token === getToken();
      // A normal focus check keeps the verified page mounted, including file inputs
      // and previews. Explicit permission/account changes still invalidate at once.
      if (invalidate || !token || verifiedToken.current !== token) publishIdentity(null, null);
      if (!token) { setLoading(false); return; }
      try {
        const fresh = await api.get<AuthUser>("/auth/me");
        if (!isCurrent()) return;
        if (!isAuthUser(fresh) || !fresh.is_active) { publishIdentity(null, null); return; }
        if (refreshAttachment) await api.post("/auth/attachment-session", {});
        if (isCurrent()) publishIdentity(fresh, token);
      } catch {
        if (isCurrent()) publishIdentity(null, null);
      } finally {
        if (isCurrent()) setLoading(false);
      }
    };
    const onFocus = () => { void refreshFromServer(false); };
    const onPermissionsChanged = () => { void refreshFromServer(true); };
    const onStorage = (event: StorageEvent) => { if (event.key === "token" || event.key === "permissions-revision" || event.key === null) void refreshFromServer(true); };
    window.addEventListener("storage", onStorage);
    window.addEventListener("focus", onFocus);
    window.addEventListener("permissions-changed", onPermissionsChanged);
    window.addEventListener("auth-user-refreshed", refresh);
    void refreshFromServer(true, false);
    return () => { active = false; ++requestVersion; window.removeEventListener("auth-user-refreshed", refresh); window.removeEventListener("storage", onStorage); window.removeEventListener("focus", onFocus);
      window.removeEventListener("permissions-changed", onPermissionsChanged); };
  }, []);

  async function doLogin(username: string, password: string) {
    const epoch = ++sessionEpoch.current;
    const res = await api.post<LoginResponse>("/auth/login", { username, password });
    if (epoch !== sessionEpoch.current) return;
    setToken(res.access_token);
    setActiveWarehouseId(null);
    localStorage.setItem("warehouses", JSON.stringify(res.warehouses || []));
    
    const u: AuthUser = {
      id: res.user_id,
      username: res.username,
      display_name: res.display_name,
      role: res.role,
      warehouse_id: res.warehouse_id,
      warehouse_name: res.warehouse_name,
      warehouses: res.warehouses || [],
      extra_permissions: res.extra_permissions || [],
      action_access: res.action_access,
      is_active: true,
      attendance_enabled: !!res.attendance_enabled,
      attendance_employee_id: res.attendance_employee_id,
      self_employee_id: res.self_employee_id,
    };
    updateIdentity(u, res.access_token);
    window.dispatchEvent(new CustomEvent("auth-user-refreshed", { detail: u }));
    
    const warehouses = res.warehouses || [];
    if (res.role === "warehouse_labor") {
      if (warehouses.length > 0) setActiveWarehouseId(warehouses[0].id);
      router.push("/clock-in");
    } else if (res.role === "super_admin") {
      if (warehouses.length > 0) setActiveWarehouseId(warehouses[0].id);
      router.push("/dashboard");
    } else if (res.role === "supervisor" && warehouses.length === 1) {
      setActiveWarehouseId(warehouses[0].id);
      router.push("/dashboard");
    } else {
      router.push("/select-warehouse");
    }
  }

  async function doLogout() {
    const epoch = ++sessionEpoch.current;
    await api.post("/auth/attachment-session", { clear: true }).catch(() => {});
    if (epoch !== sessionEpoch.current) return;
    clearToken();
    updateIdentity(null, null);
    window.dispatchEvent(new CustomEvent("auth-user-refreshed", { detail: null }));
    router.push("/login");
  }

  return (
    <AuthContext.Provider value={{ user, login: doLogin, logout: doLogout, isAuthenticated: !!user, loading }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}

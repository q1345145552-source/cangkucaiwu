"use client";
import { createContext, useContext, useState, useEffect, type ReactNode } from "react";
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
  const router = useRouter();

  useEffect(() => {
    // Cached role/menu grants are not authorization. Wait for a live /me response.
    let active = true;
    const requestedToken = getToken();
    if (requestedToken) api.get<AuthUser>("/auth/me").then(fresh => {
      if (active && requestedToken === getToken() && isAuthUser(fresh)) { setUser(fresh); localStorage.setItem("user", JSON.stringify(fresh)); }
    }).catch(() => { if (active && requestedToken === getToken()) setUser(null); }).finally(() => { if (active) setLoading(false); });
    else setLoading(false);
    const refresh = (event: Event) => {
      if (!("detail" in event)) return;
      const refreshed: unknown = event.detail;
      if (refreshed === null || isAuthUser(refreshed)) setUser(refreshed);
    };
    const refreshFromServer = () => {
      const token = getToken();
      setUser(null);
      window.dispatchEvent(new CustomEvent("auth-user-refreshed", { detail: null }));
      if (!token) return;
      api.get<AuthUser>("/auth/me").then(async fresh => {
        await api.post("/auth/attachment-session", {});
        if (active && token === getToken() && isAuthUser(fresh)) {
          setUser(fresh); localStorage.setItem("user", JSON.stringify(fresh));
          window.dispatchEvent(new CustomEvent("auth-user-refreshed", { detail: fresh }));
        }
      }).catch(() => { if (active && token === getToken()) setUser(null); });
    };
    const onStorage = (event: StorageEvent) => { if (event.key === "token" || event.key === null) refreshFromServer(); };
    window.addEventListener("storage", onStorage);
    window.addEventListener("focus", refreshFromServer);
    window.addEventListener("auth-user-refreshed", refresh);
    return () => { active = false; window.removeEventListener("auth-user-refreshed", refresh); window.removeEventListener("storage", onStorage); window.removeEventListener("focus", refreshFromServer); };
  }, []);

  async function doLogin(username: string, password: string) {
    const res = await api.post<LoginResponse>("/auth/login", { username, password });
    setToken(res.access_token);
    
    if (res.warehouses && res.warehouses.length > 0) {
      localStorage.setItem("warehouses", JSON.stringify(res.warehouses));
      setActiveWarehouseId(res.warehouses[0].id);
    }
    
    const u: AuthUser = {
      id: res.user_id,
      username: res.username,
      display_name: res.display_name,
      role: res.role,
      warehouse_id: res.warehouse_id,
      warehouse_name: res.warehouse_name,
      warehouses: res.warehouses || [],
      extra_permissions: res.extra_permissions || [],
      is_active: true,
      attendance_enabled: !!res.attendance_enabled,
      attendance_employee_id: res.attendance_employee_id,
      self_employee_id: res.self_employee_id,
    };
    setUser(u);
    localStorage.setItem("user", JSON.stringify(u));
    
    // 仓库劳工默认进打卡页，其他人进仪表盘
    if (res.role === "warehouse_labor") {
      router.push("/clock-in");
    } else {
      router.push("/dashboard");
    }
  }

  async function doLogout() {
    await api.post("/auth/attachment-session", { clear: true }).catch(() => {});
    clearToken();
    setUser(null);
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

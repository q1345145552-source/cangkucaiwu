"use client";
import { createContext, useContext, useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { api, setToken, clearToken, getToken, setActiveWarehouseId } from "@/lib/api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  useEffect(() => {
    const saved = localStorage.getItem("user");
    if (saved && getToken()) {
      try { setUser(JSON.parse(saved)); } catch {}
    }
    setLoading(false);
  }, []);

  async function doLogin(username, password) {
    const res = await api.post("/auth/login", { username, password });
    setToken(res.access_token);
    
    if (res.warehouses && res.warehouses.length > 0) {
      localStorage.setItem("warehouses", JSON.stringify(res.warehouses));
      setActiveWarehouseId(res.warehouses[0].id);
    }
    
    const u = {
      id: res.user_id,
      username: res.username,
      display_name: res.display_name,
      role: res.role,
      warehouse_id: res.warehouse_id,
      warehouse_name: res.warehouse_name,
      warehouses: res.warehouses || [],
      extra_permissions: res.extra_permissions || [],
      is_active: true,
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

  function doLogout() {
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

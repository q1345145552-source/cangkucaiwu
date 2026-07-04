"use client";
import { createContext, useContext, useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { api, setToken, clearToken, getToken } from "@/lib/api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  useEffect(() => {
    const saved = localStorage.getItem("user");
    if (saved && getToken()) {
      setUser(JSON.parse(saved));
    }
    setLoading(false);
  }, []);

  async function doLogin(username, password) {
    const res = await api.post("/auth/login", { username, password });
    setToken(res.access_token);
    const u = {
      id: res.user_id,
      username: res.username,
      display_name: res.display_name,
      role: res.role,
      warehouse_id: res.warehouse_id,
      warehouse_name: res.warehouse_name,
      is_active: true,
    };
    setUser(u);
    localStorage.setItem("user", JSON.stringify(u));
    router.push("/dashboard");
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

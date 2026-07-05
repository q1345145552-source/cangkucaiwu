"use client";
import { useState, useEffect } from "react";
import { useAuth } from "@/hooks/useAuth";
import { useI18n } from "@/hooks/useI18n";
import { Lock, User, Wifi, WifiOff } from "lucide-react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

export default function LoginPage() {
  const { login } = useAuth();
  const { t, toggleLocale, locale } = useI18n();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [apiStatus, setApiStatus] = useState<"checking" | "ok" | "error">("checking");

  useEffect(() => {
    // Check backend connectivity on page load
    fetch("/health")
      .then(r => r.json())
      .then(d => setApiStatus(d.status === "ok" ? "ok" : "error"))
      .catch(() => setApiStatus("error"));
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await login(username, password);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setError(msg || t("login_error"));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-blue-50 to-indigo-100 p-4">
      <div className="w-full max-w-md">
        <div className="mb-8 text-center">
          <h1 className="text-2xl font-bold text-gray-800">{t("app_name")}</h1>
          <p className="mt-2 text-sm text-gray-500">ระบบจัดการการเงินคลังสินค้าต่างประเทศ</p>
        </div>

        <form onSubmit={handleSubmit} className="rounded-2xl bg-white p-8 shadow-lg">
          <h2 className="mb-6 text-xl font-semibold text-gray-700">{t("login")}</h2>

          {apiStatus === "error" && (
            <div className="mb-4 rounded-lg bg-red-50 p-3 text-sm text-red-600 flex items-center gap-2">
              <WifiOff size={16} />
              <span>无法连接后端服务，请确认 Docker 容器已启动</span>
            </div>
          )}

          {error && (
            <div className="mb-4 rounded-lg bg-red-50 p-3 text-sm text-red-600">{error}</div>
          )}

          <div className="mb-4">
            <label className="mb-1 block text-sm font-medium text-gray-600">{t("username")}</label>
            <div className="flex items-center rounded-lg border border-gray-300 px-3 py-2 focus-within:ring-2 focus-within:ring-primary">
              <User className="mr-2 h-4 w-4 text-gray-400" />
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="w-full outline-none"
                placeholder={t("username")}
                required
              />
            </div>
          </div>

          <div className="mb-6">
            <label className="mb-1 block text-sm font-medium text-gray-600">{t("password")}</label>
            <div className="flex items-center rounded-lg border border-gray-300 px-3 py-2 focus-within:ring-2 focus-within:ring-primary">
              <Lock className="mr-2 h-4 w-4 text-gray-400" />
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full outline-none"
                placeholder={t("password")}
                required
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={loading || apiStatus === "error"}
            className="w-full rounded-lg bg-primary py-2.5 text-white font-medium hover:bg-primary-dark disabled:opacity-50 transition-colors"
          >
            {loading ? "登录中..." : t("login_btn")}
          </button>

          <div className="mt-3 text-center">
            <span className="inline-flex items-center gap-1 text-xs text-gray-400">
              {apiStatus === "checking" && <span>检测服务连接中...</span>}
              {apiStatus === "ok" && <><Wifi size={12} className="text-green-500" /> 服务已连接</>}
              {apiStatus === "error" && <><WifiOff size={12} className="text-red-500" /> 服务未连接</>}
            </span>
          </div>
        </form>

        <button
          onClick={toggleLocale}
          className="mt-4 w-full text-center text-sm text-gray-400 hover:text-gray-600"
        >
          {t("switch_lang")}
        </button>

        <div className="mt-2 text-center text-xs text-gray-300">
          默认账号: admin / admin123
        </div>
      </div>
    </div>
  );
}

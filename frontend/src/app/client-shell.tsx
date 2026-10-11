"use client";
import { useEffect } from "react";
import { AuthProvider } from "@/hooks/useAuth";
import { ToastProvider } from "@/components/ui/Toast";
import DashboardLayout from "@/components/layout/DashboardLayout";
import { usePathname } from "next/navigation";

export default function ClientShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const isLogin = pathname === "/login";

  // 首屏加载画面：代码加载完成后淡出并移除（打开/刷新时出现，内部导航不会重复出现）
  useEffect(() => {
    const splash = document.getElementById("app-splash");
    if (splash) {
      splash.style.animation = "none"; // 关闭 CSS 兜底动画，改由 JS 控制淡出
      splash.style.transition = "opacity 0.35s ease";
      requestAnimationFrame(() => {
        splash.style.opacity = "0";
      });
      const t = setTimeout(() => splash.remove(), 400);
      return () => clearTimeout(t);
    }
  }, []);

  // 注册 Service Worker（仅 https，本地 http 跳过；失败静默，不弹错）
  useEffect(() => {
    if (typeof window === "undefined") return;
    if (window.location.protocol !== "https:") return;
    if (!("serviceWorker" in navigator)) return;
    const register = () => {
      navigator.serviceWorker.register("/sw.js").catch(() => {});
    };
    if (document.readyState === "complete") {
      register();
    } else {
      window.addEventListener("load", register, { once: true });
    }
  }, []);

  // 拦掉安卓 Chrome 底部自动弹出的「安装应用」提示条（菜单里手动安装不受影响）
  useEffect(() => {
    const handler = (e: Event) => {
      e.preventDefault();
    };
    window.addEventListener("beforeinstallprompt", handler);
    return () => window.removeEventListener("beforeinstallprompt", handler);
  }, []);

  return (
    <AuthProvider>
      <ToastProvider>
        {isLogin ? (
          children
        ) : (
          <DashboardLayout>{children}</DashboardLayout>
        )}
      </ToastProvider>
    </AuthProvider>
  );
}

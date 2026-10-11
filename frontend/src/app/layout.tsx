import type { Metadata, Viewport } from "next";
import "./globals.css";
import ClientShell from "./client-shell";

export const metadata: Metadata = {
  title: "海外仓财务管理系统",
  description: "海外仓财务管理系统",
  manifest: "/manifest.json",
  icons: {
    icon: [
      { url: "/favicon.ico" },
      { url: "/icon-192.png", sizes: "192x192", type: "image/png" },
      { url: "/icon-512.png", sizes: "512x512", type: "image/png" },
    ],
    apple: [
      { url: "/icon-192.png", sizes: "192x192", type: "image/png" },
    ],
  },
  appleWebApp: {
    capable: true,
    title: "仓储财务",
    statusBarStyle: "default",
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#2563eb" },
    { media: "(prefers-color-scheme: dark)", color: "#1e40af" },
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh">
      <body className="min-h-screen bg-gray-50">
        {/* 首屏加载画面：打开应用/刷新时显示，客户端加载完成后由 client-shell 淡出 */}
        <div id="app-splash" className="app-splash" aria-hidden="true">
          <div className="app-splash-title">海外仓财务管理系统</div>
          <div className="app-splash-spinner" />
        </div>
        <ClientShell>{children}</ClientShell>
      </body>
    </html>
  );
}

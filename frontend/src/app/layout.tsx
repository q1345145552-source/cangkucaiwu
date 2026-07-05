"use client";
import "./globals.css";
import { AuthProvider } from "@/hooks/useAuth";
import DashboardLayout from "@/components/layout/DashboardLayout";
import { usePathname } from "next/navigation";

export default function RootLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const isLogin = pathname === "/login";

  return (
    <html lang="zh">
      <body className="min-h-screen bg-gray-50">
        <AuthProvider>
          {isLogin ? (
            children
          ) : (
            <DashboardLayout>{children}</DashboardLayout>
          )}
        </AuthProvider>
      </body>
    </html>
  );
}

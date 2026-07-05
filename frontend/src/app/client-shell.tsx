"use client";
import { AuthProvider } from "@/hooks/useAuth";
import { ToastProvider } from "@/components/ui/Toast";
import DashboardLayout from "@/components/layout/DashboardLayout";
import { usePathname } from "next/navigation";

export default function ClientShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const isLogin = pathname === "/login";

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

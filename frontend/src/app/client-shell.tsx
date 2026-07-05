"use client";
import { AuthProvider } from "@/hooks/useAuth";
import DashboardLayout from "@/components/layout/DashboardLayout";
import { usePathname } from "next/navigation";

export default function ClientShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const isLogin = pathname === "/login";

  return (
    <AuthProvider>
      {isLogin ? (
        children
      ) : (
        <DashboardLayout>{children}</DashboardLayout>
      )}
    </AuthProvider>
  );
}

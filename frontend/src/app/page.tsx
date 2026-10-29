"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { getActiveWarehouseId, getToken, setActiveWarehouseId } from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";

export default function Home() {
  const router = useRouter();
  const { user, loading } = useAuth();
  useEffect(() => {
    if (loading) return;
    if (!user) {
      if (getToken() && getActiveWarehouseId() !== null) {
        setActiveWarehouseId(null);
        window.location.replace("/");
      } else router.replace("/login");
      return;
    }
    if (user.role === "super_admin") { router.replace("/dashboard"); return; }
    if (user.role === "warehouse_labor") {
      if (user.warehouses.length === 1 && getActiveWarehouseId() !== String(user.warehouses[0].id)) setActiveWarehouseId(user.warehouses[0].id);
      router.replace("/clock-in");
    } else if (user.role === "supervisor" && user.warehouses.length === 1) {
      setActiveWarehouseId(user.warehouses[0].id);
      router.replace("/dashboard");
    } else router.replace("/select-warehouse");
  }, [router, user, loading]);
  return <div className="flex h-screen items-center justify-center">Loading...</div>;
}

"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/hooks/useAuth";
import { getActiveWarehouseId, getToken, setActiveWarehouseId } from "@/lib/api";
import WarehouseCards from "@/components/WarehouseCards";
import { WarehouseOverviewEntry } from "@/components/WarehouseOverview";

export default function SelectWarehousePage() {
  const { user, loading, logout } = useAuth();
  const router = useRouter();
  useEffect(() => {
    if (loading) return;
    if (!user) {
      if (getToken() && getActiveWarehouseId() !== null) {
        setActiveWarehouseId(null);
        window.location.replace("/select-warehouse");
      } else router.replace("/login");
    } else if (user.role === "warehouse_labor") router.replace("/clock-in");
    else if (user.role === "super_admin") router.replace("/dashboard");
  }, [user, loading, router]);
  if (loading || !user || user.role === "warehouse_labor" || user.role === "super_admin") return <p role="status">正在核实登录…</p>;
  return (
    <>
    <header className="mb-4 flex min-h-[64px] items-center justify-between gap-3 border-b border-gray-200 bg-white px-4 py-3 text-gray-900">
      <span className="min-w-0 break-words">{user.display_name || user.username}</span>
      <button type="button" onClick={() => { void logout(); }} className="min-h-[44px] shrink-0 rounded-lg border border-gray-300 px-4 text-blue-700">退出登录</button>
    </header>
    <section>
      <div className="relative">
        <h1 className="mb-6 text-2xl font-bold text-gray-900">请选择要进入的仓库</h1>
        <WarehouseOverviewEntry />
      </div>
      <WarehouseCards />
    </section>
    </>
  );
}

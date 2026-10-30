"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { ArrowUpRight, LayoutGrid } from "lucide-react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/hooks/useAuth";
import { getActiveWarehouseId, getToken, setActiveWarehouseId } from "@/lib/api";
import WarehouseCards from "@/components/WarehouseCards";
import { WarehouseOverviewEntry } from "@/components/WarehouseOverview";
import CreateWarehouseDialog from "@/components/CreateWarehouseDialog";

interface WarehouseItem { id: number; name: string; code: string }

export default function SelectWarehousePage() {
  const { user, loading, logout } = useAuth();
  const router = useRouter();
  const [warehouses, setWarehouses] = useState<WarehouseItem[]>([]);
  const [createOpen, setCreateOpen] = useState(false);
  const [refreshCards, setRefreshCards] = useState(0);
  const isAdmin = user?.role === "warehouse_admin";
  const onWarehousesLoaded = useCallback((items: { warehouse_id: number; warehouse_name: string; warehouse_code: string }[]) =>
    setWarehouses(items.map(item => ({ id: item.warehouse_id, name: item.warehouse_name, code: item.warehouse_code }))), []);
  const onCreated = useCallback(() => {
    setCreateOpen(false);
    setRefreshCards(value => value + 1);
  }, []);
  const goManage = useCallback((id: number) => {
    setActiveWarehouseId(id);
    window.location.assign("/warehouses");
  }, []);
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
      {isAdmin ? <div className="mb-6">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <h1 className="text-2xl font-bold text-gray-900">请选择要进入的仓库</h1>
          <div className="grid grid-cols-2 gap-2 sm:flex sm:shrink-0">
            <button type="button" onClick={() => setCreateOpen(true)} className="min-h-[44px] rounded-lg border border-gray-300 bg-white px-3 text-sm font-medium text-blue-700 hover:bg-blue-50">新建仓库</button>
            {warehouses.length > 0 && <button type="button" onClick={() => goManage(warehouses[0].id)} className="min-h-[44px] rounded-lg border border-gray-300 bg-white px-3 text-sm font-medium text-blue-700 hover:bg-blue-50">仓库管理</button>}
          </div>
        </div>
        <div className="relative h-11"><WarehouseOverviewEntry /></div>
      </div> : <div className="relative">
        <h1 className="mb-6 text-2xl font-bold text-gray-900">请选择要进入的仓库</h1>
        <WarehouseOverviewEntry />
      </div>}
      <WarehouseCards refreshKey={refreshCards} onWarehousesLoaded={onWarehousesLoaded}
        onCreate={isAdmin ? () => setCreateOpen(true) : undefined}
        onManage={isAdmin ? goManage : undefined}
        renderOverview={({ warehouseCount, pendingCount }) => user.role === "warehouse_admin" ? (
        <Link href="/warehouse-overview" prefetch={false}
          className="flex min-h-[372px] min-w-0 flex-col justify-between rounded-2xl border border-blue-200 bg-gradient-to-br from-blue-50 via-white to-indigo-50 p-6 text-slate-900 shadow-sm transition-[transform,box-shadow,border-color] duration-200 [@media(hover:hover)_and_(pointer:fine)]:hover:-translate-y-0.5 [@media(hover:hover)_and_(pointer:fine)]:hover:border-blue-300 [@media(hover:hover)_and_(pointer:fine)]:hover:shadow-lg focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600 motion-reduce:transform-none motion-reduce:transition-none sm:min-h-[352px]">
          <div>
            <span className="mb-5 flex h-14 w-14 items-center justify-center rounded-2xl border border-white bg-white/80 text-blue-600 shadow-sm">
              <LayoutGrid aria-hidden="true" className="h-7 w-7" strokeWidth={1.75} />
            </span>
            <h2 className="text-2xl font-bold tracking-tight">全部仓总览</h2>
            <p className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-2 text-sm text-slate-500">
              <span>共 <span className="font-mono font-semibold text-slate-700">{warehouseCount}</span> 个仓</span>
              {pendingCount > 0 && <span className="rounded-full bg-red-100 px-2.5 py-1 text-xs font-semibold text-red-700">待办 {pendingCount} 条</span>}
            </p>
          </div>
          <span className="mt-8 inline-flex items-center gap-2 text-sm font-semibold text-blue-700">查看全部仓库 <ArrowUpRight aria-hidden="true" className="h-4 w-4" /></span>
        </Link>
      ) : null} />
    </section>
    {isAdmin && createOpen && <CreateWarehouseDialog onClose={() => setCreateOpen(false)} onCreated={onCreated} />}
    </>
  );
}

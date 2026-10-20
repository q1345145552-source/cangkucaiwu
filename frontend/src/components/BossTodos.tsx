"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import { api } from "@/lib/api";

type TodoData = { advances: { count: number; items: unknown[] }; overtime: { count: number; items: unknown[] } };

export default function BossTodos() {
  const { user } = useAuth() as { user: any };
  const enabled = ["warehouse_admin", "supervisor", "staff"].includes(user?.role);
  const [data, setData] = useState<TodoData | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!enabled) return;
    let active = true, sequence = 0;
    async function refresh() {
      const request = ++sequence;
      try {
        const result = await api.get<TodoData>("/dashboard/boss-todos");
        if (active && request === sequence) { setData(result); setError(""); }
      } catch (err: any) {
        if (active && request === sequence) setError(err.message || "待办加载失败");
      }
    }
    const visible = () => { if (document.visibilityState === "visible") refresh(); };
    const warehouseChanged = () => { setData(null); setError(""); return refresh(); };
    refresh();
    window.addEventListener("focus", refresh);
    window.addEventListener("pageshow", refresh);
    window.addEventListener("warehouse-changed", warehouseChanged);
    window.addEventListener("auth-user-refreshed", warehouseChanged);
    document.addEventListener("visibilitychange", visible);
    return () => {
      active = false;
      window.removeEventListener("focus", refresh);
      window.removeEventListener("pageshow", refresh);
      window.removeEventListener("warehouse-changed", warehouseChanged);
      window.removeEventListener("auth-user-refreshed", warehouseChanged);
      document.removeEventListener("visibilitychange", visible);
    };
  }, [enabled, user?.id]);
  if (!enabled) return null;
  return <section aria-label="老板待办" className="bg-white rounded-xl border p-4 sm:p-5">
    <h2 className="text-lg font-semibold mb-3">待办（即时）</h2>
    {error ? <p role="alert" className="text-red-600 text-sm">{error}</p> : !data ? <p className="text-gray-500 text-sm">待办加载中...</p> : <>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <Link href="/employee-advances?approval_status=pending" className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-amber-900 hover:bg-amber-100">待批预支 <strong>{data.advances.count}</strong> 笔 <span className="float-right">查看 →</span></Link>
        <Link href="/overtime?pending_verification=true" className="rounded-lg border border-blue-200 bg-blue-50 p-4 text-blue-900 hover:bg-blue-100">待核实加班 <strong>{data.overtime.count}</strong> 条 <span className="float-right">查看 →</span></Link>
      </div>
      {data.advances.count === 0 && data.overtime.count === 0 && <p className="mt-3 text-gray-500 text-sm">暂无待办</p>}
    </>}
  </section>;
}

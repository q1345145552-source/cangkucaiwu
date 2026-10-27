"use client";
import { ReactNode, useEffect, useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import { getActiveWarehouseId } from "@/lib/api";

/** Financial forms and fetched capabilities never survive an account/warehouse switch. */
export default function FinancialIdentityBoundary({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const [warehouse, setWarehouse] = useState(() => getActiveWarehouseId());
  useEffect(() => {
    const refresh = () => setWarehouse(getActiveWarehouseId());
    window.addEventListener("warehouse-changed", refresh);
    window.addEventListener("storage", refresh);
    return () => { window.removeEventListener("warehouse-changed", refresh); window.removeEventListener("storage", refresh); };
  }, []);
  if (!user) return <p className="text-gray-500">正在核实当前账号…</p>;
  return <div key={`${user.id}:${user.role}:${warehouse}:${JSON.stringify(user.extra_permissions)}`}>{children}</div>;
}

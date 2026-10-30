"use client";
import { useEffect, useState } from "react";
import { getActiveWarehouseId, getToken } from "@/lib/api";
import type { AuthUser } from "@/types/auth";

/** Refreshing the same verified identity must not discard unfinished forms. */
export function useFormScope(user: AuthUser | null): string {
  const [warehouse, setWarehouse] = useState(getActiveWarehouseId);
  useEffect(() => {
    const refresh = () => setWarehouse(getActiveWarehouseId());
    window.addEventListener("warehouse-changed", refresh);
    window.addEventListener("storage", refresh);
    return () => {
      window.removeEventListener("warehouse-changed", refresh);
      window.removeEventListener("storage", refresh);
    };
  }, []);
  // Compare actual account/warehouse/grants, rather than each /auth/me object.
  return JSON.stringify([getToken(), warehouse, user?.id, user?.role,
    user?.warehouse_id, user?.is_active, user?.extra_permissions, user?.action_access]);
}

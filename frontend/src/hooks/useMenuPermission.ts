"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";

interface MenuPermission {
  menu_key: string;
  label: string;
  selectable: boolean;
  roles?: string[];
}

interface PermissionUser {
  id?: number;
  role: string;
  extra_permissions?: string[];
}

export function hasMenuPermission(user: PermissionUser | null, menuKey: string, permissions: MenuPermission[]): boolean {
  if (!user) return false;
  if (user.role === "warehouse_admin") return true;
  // Platform administration does not grant warehouse business actions. Use the
  // same backend catalogue that retains its explicit market/settings exceptions.
  if (user.role === "super_admin") return permissions.some(item => item.menu_key === menuKey && item.roles?.includes("super_admin"));
  if (user.role !== "supervisor" && user.role !== "staff") return false;
  const permission = permissions.find(item => item.menu_key === menuKey && item.selectable);
  return !!permission && (user.extra_permissions || []).includes(permission.label);
}

// 按菜单键取后端的权限名；清单未加载或获取失败时不显示写操作。
export function useMenuPermission(menuKey: string): boolean {
  const { user } = useAuth() as { user: PermissionUser | null };
  const [permissions, setPermissions] = useState<MenuPermission[]>([]);
  useEffect(() => {
    let active = true;
    setPermissions([]);
    if (user?.role === "supervisor" || user?.role === "staff" || user?.role === "super_admin") {
      api.get<MenuPermission[]>("/users/permissions")
        .then(items => { if (active) setPermissions(items); })
        .catch(() => { if (active) setPermissions([]); });
    }
    return () => { active = false; };
  }, [user?.id, user?.role]);
  return hasMenuPermission(user, menuKey, permissions);
}

// Round-four action ceilings supplement menu visibility; server guards remain authoritative.
export function useBusinessAction(menuKey: string, action: "bookkeeping" | "rules"): boolean {
  const { user } = useAuth();
  const menu = useMenuPermission(menuKey);
  return menu && (user?.role === "warehouse_admin" || (action === "bookkeeping" && user?.role === "staff"));
}

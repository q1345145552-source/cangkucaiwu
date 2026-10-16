"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";

interface MenuPermission {
  menu_key: string;
  label: string;
  selectable: boolean;
}

interface PermissionUser {
  id?: number;
  role: string;
  extra_permissions?: string[];
}

export function hasMenuPermission(user: PermissionUser | null, menuKey: string, permissions: MenuPermission[]): boolean {
  if (!user) return false;
  if (user.role === "warehouse_admin" || user.role === "super_admin") return true;
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
    if (user?.role === "supervisor" || user?.role === "staff") {
      api.get<MenuPermission[]>("/users/permissions")
        .then(items => { if (active) setPermissions(items); })
        .catch(() => { if (active) setPermissions([]); });
    }
    return () => { active = false; };
  }, [user?.id, user?.role]);
  return hasMenuPermission(user, menuKey, permissions);
}

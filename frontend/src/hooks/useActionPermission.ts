"use client";
import { useAuth } from "@/hooks/useAuth";
import type { AuthUser } from "@/types/auth";
export type ActionTier = "view" | "operate" | "approve";

export function hasAction(user: AuthUser | null, action: string, tier?: ActionTier): boolean {
  return !!user?.action_access?.actions.some(item => item.id === action && (!tier || item.tier === tier));
}
export function useActionPermission(action: string, tier?: ActionTier): boolean {
  const { user } = useAuth();
  return hasAction(user, action, tier);
}
export function useTierPermission(module: string, tier: ActionTier): boolean {
  const { user } = useAuth();
  if (!user || user.action_access?.version === "invalid") return false;
  if (user.role === "warehouse_admin" || user.role === "super_admin") {
    return !!user.action_access?.actions.some(item => item.module === module && item.tier === tier);
  }
  return !!user.action_access?.grants.includes(`${module}:${tier}`);
}

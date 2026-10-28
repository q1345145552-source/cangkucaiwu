"use client";
import type { ReactNode } from "react";
import { useAuth } from "@/hooks/useAuth";
import { hasAction, type ActionTier } from "@/hooks/useActionPermission";
export default function ActionGate({ action, tier, anyOf, children }: { action?: string; tier?: ActionTier; anyOf?: string[]; children: ReactNode }) {
  const { user } = useAuth();
  const choices = anyOf || (action ? [`${action}${tier ? `#${tier}` : ""}`] : []);
  const allowed = choices.some(value => { const [id, lane] = value.split("#"); return hasAction(user, id, lane as ActionTier | undefined); });
  return allowed ? <>{children}</> : null;
}

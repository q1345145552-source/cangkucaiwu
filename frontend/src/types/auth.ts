export type UserRole = "super_admin" | "warehouse_admin" | "supervisor" | "staff" | "warehouse_labor";

export interface AuthWarehouse {
  id: number;
  name: string;
  code: string;
}

export interface AuthUser {
  id: number;
  username: string;
  display_name: string | null;
  role: UserRole;
  warehouse_id: number | null;
  warehouse_name: string | null;
  warehouses: AuthWarehouse[];
  extra_permissions: string[];
  is_active: boolean;
  attendance_enabled: boolean;
  attendance_employee_id: number | null;
}

export interface LoginResponse extends Omit<AuthUser, "id" | "is_active"> {
  access_token: string;
  token_type: "bearer";
  user_id: number;
}

const roles: readonly string[] = ["super_admin", "warehouse_admin", "supervisor", "staff", "warehouse_labor"];
function record(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
function identifier(value: unknown): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value > 0;
}
function nullableId(value: unknown): value is number | null {
  return value === null || identifier(value);
}
function nullableText(value: unknown): value is string | null {
  return value === null || typeof value === "string";
}
function warehouse(value: unknown): value is AuthWarehouse {
  return record(value) && identifier(value.id) && typeof value.name === "string" && typeof value.code === "string";
}

// Cached JSON and browser events are untrusted shapes; invalid values never become an authenticated user.
export function isAuthUser(value: unknown): value is AuthUser {
  return record(value) && identifier(value.id) && typeof value.username === "string"
    && nullableText(value.display_name) && typeof value.role === "string" && roles.includes(value.role)
    && nullableId(value.warehouse_id) && nullableText(value.warehouse_name)
    && Array.isArray(value.warehouses) && value.warehouses.every(warehouse)
    && Array.isArray(value.extra_permissions) && value.extra_permissions.every(p => typeof p === "string")
    && typeof value.is_active === "boolean" && typeof value.attendance_enabled === "boolean"
    && nullableId(value.attendance_employee_id);
}

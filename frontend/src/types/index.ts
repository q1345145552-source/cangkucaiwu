export interface User {
  id: number;
  username: string;
  display_name: string;
  role: "super_admin" | "warehouse_admin" | "staff";
  warehouse_id: number | null;
  warehouse_name: string | null;
  is_active: boolean;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user_id: number;
  username: string;
  display_name: string;
  role: string;
  warehouse_id: number | null;
  warehouse_name: string | null;
}

export interface DashboardStats {
  total_recharge_month: number;
  total_incoming_month: number;
  unmatched_count: number;
  pending_market_review: number;
  pending_group_orders: number;
}

from pydantic import BaseModel

class DashboardStats(BaseModel):
    total_recharge_month: float = 0
    total_incoming_month: float = 0
    unmatched_count: int = 0
    pending_market_review: int = 0
    pending_group_orders: int = 0

class WarehouseSummary(BaseModel):
    warehouse_id: int
    warehouse_name: str
    recharge_total: float = 0
    incoming_total: float = 0
    unmatched_count: int = 0

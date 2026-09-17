from sqlalchemy import Column, Integer, Date, DateTime, Float, ForeignKey, UniqueConstraint
from sqlalchemy.sql import func
from app.database import Base


class EfficiencyOrderCount(Base):
    """人效管理 - 管理员按天录入的整仓订单数（每天一条，可修改）。"""
    __tablename__ = "efficiency_daily_orders"
    __table_args__ = (
        UniqueConstraint("warehouse_id", "date", name="uq_efficiency_daily_wh_date"),
    )

    id = Column(Integer, primary_key=True, index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)  # 日期，每天一条
    order_count = Column(Integer, nullable=False, default=0)
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class EfficiencyManualHour(Base):
    """人效管理 - 管理员手动补录的工时（针对 1/3 次打卡无法计算的待补天）。"""
    __tablename__ = "efficiency_manual_hours"
    __table_args__ = (
        UniqueConstraint("employee_id", "date", name="uq_manual_hours_emp_date"),
    )

    id = Column(Integer, primary_key=True, index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    hours = Column(Float, nullable=False, default=0)
    operator_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

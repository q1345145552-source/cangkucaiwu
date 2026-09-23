from sqlalchemy import Column, Integer, String, DateTime, Float, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class SalaryTemplate(Base):
    """薪资模板（每仓库独立）。type: hourly/daily/monthly；amount: hourly/daily=日薪, monthly=月薪。"""
    __tablename__ = "salary_templates"

    id = Column(Integer, primary_key=True, index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    type = Column(String(20), nullable=False, default="daily")  # hourly / daily / monthly
    amount = Column(Float, nullable=False)
    overtime_half_hour_fee = Column(Float, default=0)
    is_active = Column(Boolean, default=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    employees = relationship("Employee", back_populates="salary_template")

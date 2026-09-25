from sqlalchemy import Column, Integer, String, DateTime, Float, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class DeductionTemplate(Base):
    """考勤扣款模板（每仓库独立）。各字段为「时薪/日薪的倍数」，0 表示不扣该项。"""
    __tablename__ = "deduction_templates"

    id = Column(Integer, primary_key=True, index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    late_half_multiplier = Column(Float, default=0.5)   # 迟到半小时扣：时薪倍数
    late_one_multiplier = Column(Float, default=1.0)    # 迟到1小时扣：时薪倍数
    late_half_threshold = Column(String(5), default="09:05")  # 迟到半小时红线
    late_one_threshold = Column(String(5), default="09:31")   # 迟到1小时红线
    early_half_multiplier = Column(Float, default=0.5)  # 早退半小时扣：时薪倍数
    early_one_multiplier = Column(Float, default=1.0)   # 早退1小时扣：时薪倍数
    early_half_threshold = Column(String(5), default="17:30")  # 早退半小时红线
    early_one_threshold = Column(String(5), default="17:00")   # 早退1小时红线
    absence_extra_multiplier = Column(Float, default=0.5)  # 旷工额外罚：日薪倍数
    is_active = Column(Boolean, default=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    employees = relationship("Employee", back_populates="deduction_template")

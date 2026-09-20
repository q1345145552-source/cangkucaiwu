from sqlalchemy import Column, Integer, String, DateTime, Float, ForeignKey, Date, Boolean
from sqlalchemy.sql import func
from app.database import Base

class ClockInRecord(Base):
    __tablename__ = "clock_in_records"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=True)
    clock_date = Column(Date, nullable=False, index=True)
    session = Column(Integer, nullable=False, default=1)
    clocked_in_at = Column(DateTime(timezone=True), server_default=func.now())
    photo_path = Column(String(500), nullable=True)
    status = Column(String(20), default="normal")
    penalty_amount = Column(Float, default=0)
    remark = Column(String(200), nullable=True)
    # 补卡标记（管理员/主管代补）
    is_makeup = Column(Boolean, default=False, comment="补卡标记")
    makeup_by = Column(Integer, ForeignKey("users.id"), nullable=True, comment="补卡人")
    makeup_at = Column(DateTime(timezone=True), nullable=True, comment="补卡操作时间")
    makeup_reason = Column(String(500), nullable=True, comment="补卡原因")

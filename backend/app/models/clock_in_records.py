from sqlalchemy import Column, Integer, String, DateTime, Float, ForeignKey, Date
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

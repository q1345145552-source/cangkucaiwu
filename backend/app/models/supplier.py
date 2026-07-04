from sqlalchemy import Column, Integer, String, DateTime, Float, ForeignKey, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base

class Supplier(Base):
    __tablename__ = "suppliers"

    id = Column(Integer, primary_key=True, index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=True, index=True)
    name = Column(String(200), nullable=False)
    contact_person = Column(String(100), nullable=True)
    contact_info = Column(String(200), nullable=True)
    address = Column(String(300), nullable=True)
    payment_terms = Column(String(100), nullable=True)
    ai_evaluation = Column(JSON, nullable=True, comment="DeepSeek AI评估结果")
    ai_evaluated_at = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(String(5), default="true")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    payable_bills = relationship("PayableBill", back_populates="supplier")

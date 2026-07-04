from sqlalchemy import Column, Integer, String, DateTime, Float, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
import enum

class GroupOrderStatus(str, enum.Enum):
    OPEN = "open"
    CLOSED = "closed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

class GroupOrder(Base):
    __tablename__ = "group_orders"

    id = Column(Integer, primary_key=True, index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False, index=True)
    item_name = Column(String(200), nullable=False)
    specification = Column(String(500), nullable=True)
    target_quantity = Column(Integer, nullable=False)
    target_price = Column(Float, nullable=False)
    deadline = Column(DateTime, nullable=False)
    reason = Column(String(500), nullable=True)
    status = Column(String(20), default=GroupOrderStatus.OPEN.value)
    final_price = Column(Float, nullable=True)
    final_supplier = Column(String(200), nullable=True)
    logistics_fee = Column(Float, nullable=True)
    initiator_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    completed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    initiator = relationship("User", foreign_keys=[initiator_id])
    participants = relationship("GroupOrderParticipant", back_populates="group_order")

class GroupOrderParticipant(Base):
    __tablename__ = "group_order_participants"

    id = Column(Integer, primary_key=True, index=True)
    group_order_id = Column(Integer, ForeignKey("group_orders.id"), nullable=False, index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    delivery_address = Column(String(300), nullable=True)
    agreed_rules = Column(Boolean, default=False)
    is_banned = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    group_order = relationship("GroupOrder", back_populates="participants")
    warehouse = relationship("Warehouse", foreign_keys=[warehouse_id])

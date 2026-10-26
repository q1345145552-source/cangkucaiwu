"""Immutable receipt batches. IDs are stable sources for future inventory integration."""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, JSON, UniqueConstraint
from sqlalchemy.sql import func
from app.database import Base


class PurchaseReceiptEvent(Base):
    __tablename__ = 'purchase_receipt_events'
    __table_args__ = (UniqueConstraint('warehouse_id', 'purchase_order_id', 'request_key', name='uq_purchase_receipt_operation'),)
    id = Column(Integer, primary_key=True)
    warehouse_id = Column(Integer, ForeignKey('warehouses.id'), nullable=False, index=True)
    purchase_order_id = Column(Integer, ForeignKey('purchase_orders.id'), nullable=False, index=True)
    request_key = Column(String(100), nullable=False)
    request_fingerprint = Column(String(64), nullable=False)
    items = Column(JSON, nullable=False)
    photo_path = Column(String(500), nullable=False)
    operator_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    operator_name = Column(String(100), nullable=False)
    received_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    remark = Column(String(1000), nullable=True)
    source = Column(String(40), nullable=False, default='purchase_receive')
    status = Column(String(20), nullable=False, default='active')

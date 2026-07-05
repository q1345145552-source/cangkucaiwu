from sqlalchemy import Column, Integer, String, DateTime, Float, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
import enum

class CreditStatus(str, enum.Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    CANCELLED = "cancelled"

class CreditCustomer(Base):
    __tablename__ = "credit_customers"

    id = Column(Integer, primary_key=True, index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    credit_limit = Column(Float, nullable=False)
    current_debt = Column(Float, nullable=True, comment="系统自动计算：sum(shipments) - sum(repayments)")
    overdue_days = Column(Integer, nullable=True, comment="系统自动计算：距最后发货/还款天数")
    repayment_day = Column(Integer, nullable=True, comment="每月还款日(1-31)")
    status = Column(String(20), default=CreditStatus.ACTIVE.value)
    remark = Column(String(500), nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    customer = relationship("Customer", foreign_keys=[customer_id])
    repayments = relationship("CreditRepayment", back_populates="credit_customer")
    shipments = relationship("CreditShipment", back_populates="credit_customer")

class CreditShipment(Base):
    __tablename__ = "credit_shipments"

    id = Column(Integer, primary_key=True, index=True)
    credit_customer_id = Column(Integer, ForeignKey("credit_customers.id"), nullable=False, index=True)
    ship_date = Column(DateTime, nullable=False)
    order_no = Column(String(100), nullable=True)
    amount = Column(Float, nullable=False)
    remark = Column(String(500), nullable=True)
    entrant_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    credit_customer = relationship("CreditCustomer", back_populates="shipments")

class CreditRepayment(Base):
    __tablename__ = "credit_repayments"

    id = Column(Integer, primary_key=True, index=True)
    credit_customer_id = Column(Integer, ForeignKey("credit_customers.id"), nullable=False, index=True)
    repayment_date = Column(DateTime, nullable=False)
    amount = Column(Float, nullable=False)
    remark = Column(String(500), nullable=True)
    recorded_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    credit_customer = relationship("CreditCustomer", back_populates="repayments")

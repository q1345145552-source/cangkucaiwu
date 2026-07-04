from sqlalchemy import Column, Integer, String, DateTime, Float, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
import enum

class FundStatus(str, enum.Enum):
    ACTIVE = "active"
    RETURNED = "returned"
    PARTIALLY_RETURNED = "partially_returned"

class ReviewStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"

class ReviewAction(str, enum.Enum):
    EMPLOYEE_PAY = "employee_pay"
    DEDUCT_NEXT = "deduct_next"

class ExpenseFund(Base):
    __tablename__ = "expense_funds"

    id = Column(Integer, primary_key=True, index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False, index=True)
    employee_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    receive_date = Column(DateTime, nullable=False)
    amount = Column(Float, nullable=False)
    purpose = Column(String(500), nullable=False)
    expected_return_date = Column(DateTime, nullable=True)
    status = Column(String(30), default=FundStatus.ACTIVE.value)
    remaining_balance = Column(Float, default=0)
    alert_threshold = Column(Float, default=500)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    employee = relationship("User", foreign_keys=[employee_id])
    items = relationship("ExpenseFundItem", back_populates="fund")

class ExpenseFundItem(Base):
    __tablename__ = "expense_fund_items"

    id = Column(Integer, primary_key=True, index=True)
    fund_id = Column(Integer, ForeignKey("expense_funds.id"), nullable=False, index=True)
    expense_date = Column(DateTime, nullable=False)
    category = Column(String(100), nullable=False)
    amount = Column(Float, nullable=False)
    description = Column(String(500), nullable=False)
    receipt = Column(String(500), nullable=True)
    review_status = Column(String(20), default=ReviewStatus.PENDING.value)
    review_remark = Column(String(500), nullable=True)
    review_action = Column(String(20), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    fund = relationship("ExpenseFund", back_populates="items")

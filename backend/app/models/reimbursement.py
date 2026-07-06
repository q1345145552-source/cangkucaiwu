from sqlalchemy import Column, Integer, String, DateTime, Float, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
import enum

class ReimbStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    PARTIALLY_APPROVED = "partially_approved"
    REJECTED = "rejected"
    PAID = "paid"
    FUND_LINKED = "fund_linked"

class Reimbursement(Base):
    __tablename__ = "reimbursements"

    id = Column(Integer, primary_key=True, index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False, index=True)
    employee_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    submit_date = Column(DateTime, nullable=False)
    total_amount = Column(Float, nullable=False)
    currency = Column(String(5), nullable=False, default="THB")
    status = Column(String(30), default=ReimbStatus.PENDING.value)
    reviewer_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    review_remark = Column(String(500), nullable=True)
    paid_at = Column(DateTime(timezone=True), nullable=True)
    payment_method = Column(String(20), nullable=True, comment="bank_transfer/cash")
    is_fund_linked = Column(String(5), default="0", comment="1=关联备用金扣款")
    fund_item_id = Column(Integer, nullable=True, comment="关联的备用金开销记录ID")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    employee = relationship("User", foreign_keys=[employee_id])
    reviewer = relationship("User", foreign_keys=[reviewer_id])
    items = relationship("ReimbursementItem", back_populates="reimbursement")

class ReimbursementItem(Base):
    __tablename__ = "reimbursement_items"

    id = Column(Integer, primary_key=True, index=True)
    reimbursement_id = Column(Integer, ForeignKey("reimbursements.id"), nullable=False, index=True)
    category = Column(String(100), nullable=False)
    amount = Column(Float, nullable=False)
    description = Column(String(500), nullable=True)
    receipt = Column(String(500), nullable=True)
    review_status = Column(String(20), default="pending")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    reimbursement = relationship("Reimbursement", back_populates="items")

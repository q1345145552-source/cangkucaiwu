from sqlalchemy import Column, Integer, String, DateTime, Float, ForeignKey, Boolean, Numeric, true
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
import enum

class FundStatus(str, enum.Enum):
    ACTIVE = "active"
    RETURNED = "returned"
    SETTLED = "settled"
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
    fund_number = Column(String(30), nullable=True, unique=True, index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False, index=True)
    employee_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    receive_date = Column(DateTime, nullable=False)
    amount = Column(Float, nullable=False)
    currency = Column(String(5), default="THB")
    purpose = Column(String(500), nullable=False)
    expected_return_date = Column(DateTime, nullable=True)
    status = Column(String(30), default=FundStatus.ACTIVE.value)
    remaining_balance = Column(Float, default=0)
    fund_limit = Column(Float, default=5000)
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
    currency = Column(String(5), default="THB")
    description = Column(String(500), nullable=False)
    receipt = Column(String(500), nullable=True)
    review_status = Column(String(20), default=ReviewStatus.PENDING.value)
    review_remark = Column(String(500), nullable=True)
    review_action = Column(String(20), nullable=True)
    # 新开销只记台账；迁移显式保留旧开销原有的成本展示口径。
    cost_record_only = Column(Boolean, nullable=False, default=True, server_default=true())
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    fund = relationship("ExpenseFund", back_populates="items")


class ExpenseFundDisbursement(Base):
    """逐笔拨付事实；不再用备用金账户的累计金额冒充每次付款。"""
    __tablename__ = "expense_fund_disbursements"

    id = Column(Integer, primary_key=True, index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False, index=True)
    fund_id = Column(Integer, ForeignKey("expense_funds.id"), nullable=False, index=True)
    amount = Column(Numeric(14, 2), nullable=False)
    currency = Column(String(5), nullable=False)
    disbursed_date = Column(DateTime, nullable=False)
    payment_account_id = Column(Integer, ForeignKey("payment_accounts.id"), nullable=False, index=True)
    account_name = Column(String(100), nullable=False)
    expense_record_id = Column(Integer, ForeignKey("expense_records.id"), nullable=False, unique=True, index=True)
    recharge_request_id = Column(Integer, ForeignKey("fund_recharge_requests.id"), nullable=True, unique=True, index=True)
    operator_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    operator_name = Column(String(100), nullable=False)
    remark = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class SystemSetting(Base):
    __tablename__ = "system_settings"

    id = Column(Integer, primary_key=True, index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False)
    key = Column(String(100), nullable=False)
    value = Column(String(500), nullable=True)
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now())


class FundRechargeRequest(Base):
    """备用金充值申请 - 财务提交 → 管理员审核"""
    __tablename__ = "fund_recharge_requests"

    id = Column(Integer, primary_key=True, index=True)
    fund_id = Column(Integer, ForeignKey("expense_funds.id"), nullable=False, index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False, index=True)
    applicant_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    amount = Column(Float, nullable=False)
    reason = Column(String(500), nullable=True)
    status = Column(String(20), default="pending")  # pending / approved / rejected
    reviewer_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    review_remark = Column(String(500), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    fund = relationship("ExpenseFund", foreign_keys=[fund_id])
    applicant = relationship("User", foreign_keys=[applicant_id])
    reviewer = relationship("User", foreign_keys=[reviewer_id])

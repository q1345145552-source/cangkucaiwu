from enum import Enum
from sqlalchemy import Column, Integer, String, DateTime, Float, ForeignKey, Date, Boolean, false, and_, or_
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class AdvanceApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


ADVANCE_APPROVAL_LABELS = {
    AdvanceApprovalStatus.PENDING.value: "待审批",
    AdvanceApprovalStatus.APPROVED.value: "已通过",
    AdvanceApprovalStatus.REJECTED.value: "已驳回",
}


class EmployeeAdvance(Base):
    """员工工资预支记录"""
    __tablename__ = "employee_advances"

    id = Column(Integer, primary_key=True, index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False, index=True)
    amount = Column(Float, nullable=False)
    currency = Column(String(5), default="THB")
    advance_date = Column(Date, nullable=False, index=True)
    period = Column(String(7), nullable=False, index=True)  # YYYY-MM
    half = Column(String(20), nullable=False, default="first_half")  # first_half / second_half
    source = Column(String(20), nullable=False, default="supervisor")  # supervisor / fund
    fund_account_id = Column(Integer, ForeignKey("expense_funds.id"), nullable=True)
    # NULL 保留旧记录，不推断旧付款账户或补记资金。
    funding_source = Column(String(20), nullable=True)  # company_account / cash_advance / expense_fund
    cash_advance_id = Column(Integer, ForeignKey("cash_advances.id"), nullable=True)
    payment_account_id = Column(Integer, ForeignKey("payment_accounts.id"), nullable=True)
    remark = Column(String(500), nullable=True)
    operator_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    deducted_amount = Column(Float, default=0)
    status = Column(String(20), default="unpaid")  # unpaid / partial / deducted / voided
    voided_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    voided_at = Column(DateTime(timezone=True), nullable=True)
    void_reason = Column(String(500), nullable=True)
    approval_status = Column(String(20), nullable=False, default=AdvanceApprovalStatus.APPROVED.value, server_default="approved")
    reviewer_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    reject_reason = Column(String(500), nullable=True)
    # 只对上线后新建的预支记支出；历史待审批记录以后通过也不补账。
    expense_tracking_enabled = Column(Boolean, nullable=False, default=False, server_default=false())
    expense_record_id = Column(Integer, ForeignKey("expense_records.id"), nullable=True, unique=True, index=True)
    fund_item_id = Column(Integer, ForeignKey("expense_fund_items.id"), nullable=True, unique=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    employee = relationship("Employee", foreign_keys=[employee_id])
    operator = relationship("User", foreign_keys=[operator_id])
    fund_account = relationship("ExpenseFund", foreign_keys=[fund_account_id])

    @property
    def is_voided(self):
        return self.status == "voided" or self.voided_at is not None

    @classmethod
    def not_voided(cls):
        return and_(cls.voided_at.is_(None), or_(cls.status.is_(None), cls.status != "voided"))

from sqlalchemy import Column, Integer, String, Text, DateTime, Float, ForeignKey, Date
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class ExpenseApproval(Base):
    """费用审批（每仓库独立）。金额超门槛走审批，不超门槛直接完成并生成运营支出。"""
    __tablename__ = "expense_approvals"

    id = Column(Integer, primary_key=True, index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False, index=True)
    applicant_id = Column(Integer, ForeignKey("users.id"), nullable=False, comment="申请人")
    amount = Column(Float, nullable=False)
    currency = Column(String(5), default="THB")
    purpose = Column(String(500), nullable=False, comment="用途说明")
    expense_date = Column(Date, nullable=False, index=True)
    voucher_path = Column(String(500), nullable=True, comment="凭证照片")
    payment_method = Column(String(20), nullable=False, default="cash", comment="alipay/wechat/bank_transfer/company_account/cash")
    fund_source = Column(String(20), nullable=False, default="company", comment="fund=备用金 company=公司账户")
    status = Column(String(20), nullable=False, default="pending", comment="pending/approved/paid/rejected/completed")
    approver_id = Column(Integer, ForeignKey("users.id"), nullable=True, comment="审批人")
    approved_at = Column(DateTime(timezone=True), nullable=True)
    approval_note = Column(String(500), nullable=True, comment="审批备注")
    payer_id = Column(Integer, ForeignKey("users.id"), nullable=True, comment="付款人")
    paid_at = Column(DateTime(timezone=True), nullable=True)
    payment_voucher = Column(String(500), nullable=True, comment="付款凭证")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    applicant = relationship("User", foreign_keys=[applicant_id])
    approver = relationship("User", foreign_keys=[approver_id])
    payer = relationship("User", foreign_keys=[payer_id])

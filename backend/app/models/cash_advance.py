"""个人替公司垫款的债务登记；不产生工资扣款、成本或资金流水。"""
from sqlalchemy import Column, Integer, String, Date, DateTime, Numeric, ForeignKey, CheckConstraint, Index, UniqueConstraint
from app.database import Base
from app.core.timezone import thai_now


PURPOSE_LABELS = {"salary": "工资", "purchase": "采购", "expense": "费用", "other": "其他"}
STATUS_LABELS = {"pending": "待确认", "confirmed": "已确认", "rejected": "已驳回", "repaid": "已归还"}


class CashAdvance(Base):
    __tablename__ = "cash_advances"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_cash_advances_amount"),
        CheckConstraint("repaid_amount >= 0 AND repaid_amount <= amount", name="ck_cash_advances_repaid"),
        CheckConstraint("purpose IN ('salary','purchase','expense','other')", name="ck_cash_advances_purpose"),
        CheckConstraint("status IN ('pending','confirmed','rejected','repaid')", name="ck_cash_advances_status"),
        Index("ix_cash_advances_warehouse_date", "warehouse_id", "advance_date"),
    )
    id = Column(Integer, primary_key=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False)
    payer_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    payer_name = Column(String(100), nullable=False)
    advance_date = Column(Date, nullable=False)
    amount = Column(Numeric(14, 2), nullable=False)
    currency = Column(String(10), nullable=False, default="THB", server_default="THB")
    purpose = Column(String(20), nullable=False)
    description = Column(String(2000), nullable=True)
    voucher_path = Column(String(500), nullable=True)
    status = Column(String(20), nullable=False, default="pending", server_default="pending")
    repaid_amount = Column(Numeric(14, 2), nullable=False, default=0, server_default="0")
    created_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_by_name = Column(String(100), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=thai_now)
    reviewed_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_by_name = Column(String(100), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    reject_reason = Column(String(500), nullable=True)
    amount_difference_note = Column(String(2000), nullable=True)


class CashAdvanceDocument(Base):
    """垫款用途的单据快照；关联本身不代表已付款，也不占用垫款额度。"""
    __tablename__ = "cash_advance_documents"
    __table_args__ = (
        UniqueConstraint("cash_advance_id", "document_type", "document_id", name="uq_cash_advance_document"),
        CheckConstraint("document_type IN ('payroll','payable','reimbursement','employee_advance')", name="ck_cash_advance_document_type"),
        Index("ix_cash_advance_documents_advance", "cash_advance_id"),
    )
    id = Column(Integer, primary_key=True)
    cash_advance_id = Column(Integer, ForeignKey("cash_advances.id"), nullable=False)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False)
    document_type = Column(String(30), nullable=False)
    document_id = Column(Integer, nullable=False)
    document_number = Column(String(100), nullable=False)
    title = Column(String(300), nullable=False)
    document_date = Column(Date, nullable=True)
    amount = Column(Numeric(14, 2), nullable=False)
    currency = Column(String(10), nullable=False)

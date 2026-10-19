"""垫款归还是公司实际付款与按用途支出的唯一来源。"""
from sqlalchemy import Column, Integer, String, Date, DateTime, Numeric, ForeignKey, CheckConstraint, Index, UniqueConstraint
from app.database import Base
from app.core.timezone import thai_now


class CashAdvanceRepayment(Base):
    __tablename__ = "cash_advance_repayments"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_cash_repayments_amount"),
        CheckConstraint("status IN ('active','revoked')", name="ck_cash_repayments_status"),
        CheckConstraint("payment_method IN ('cash','transfer')", name="ck_cash_repayments_method"),
        Index("ix_cash_repayments_warehouse_date", "warehouse_id", "repayment_date"),
        Index("ix_cash_repayments_advance", "cash_advance_id"),
        Index("ix_cash_repayments_account", "account_id"),
        UniqueConstraint("warehouse_id", "request_key", name="uq_cash_repayment_request"),
    )
    id = Column(Integer, primary_key=True)
    cash_advance_id = Column(Integer, ForeignKey("cash_advances.id"), nullable=False)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False)
    repayment_date = Column(Date, nullable=False)
    amount = Column(Numeric(14, 2), nullable=False)
    account_id = Column(Integer, ForeignKey("payment_accounts.id"), nullable=False)
    account_name = Column(String(100), nullable=False)
    currency = Column(String(10), nullable=False)
    payment_method = Column(String(20), nullable=False)
    voucher_path = Column(String(500), nullable=False)
    description = Column(String(2000), nullable=True)
    request_key = Column(String(64), nullable=True)
    created_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_by_name = Column(String(100), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=thai_now)
    status = Column(String(20), nullable=False, default="active", server_default="active")
    revoked_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    revoked_by_name = Column(String(100), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    revoke_reason = Column(String(500), nullable=True)

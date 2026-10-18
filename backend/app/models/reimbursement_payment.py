"""报销付款凭据与资金流水；撤销留存记录，不推断历史付款账户。"""
from sqlalchemy import Column, Integer, String, DateTime, Numeric, ForeignKey, JSON, CheckConstraint, Index, text
from app.database import Base


class ReimbursementPayment(Base):
    __tablename__ = "reimbursement_payments"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_reimb_payment_amount"),
        CheckConstraint("funding_source IN ('company_account','cash_advance','expense_fund')", name="ck_reimb_payment_source"),
        CheckConstraint("status IN ('active','revoked')", name="ck_reimb_payment_status"),
        Index("ix_reimb_payment_warehouse_date", "warehouse_id", "paid_at"),
        Index("ix_reimb_payment_advance", "cash_advance_id"),
        Index("ix_reimb_payment_account", "payment_account_id"),
        Index("uq_reimb_payment_active", "reimbursement_id", unique=True,
            postgresql_where=text("status = 'active'"), sqlite_where=text("status = 'active'")),
    )
    id = Column(Integer, primary_key=True)
    reimbursement_id = Column(Integer, ForeignKey("reimbursements.id"), nullable=False)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False)
    amount = Column(Numeric(14, 2), nullable=False)
    currency = Column(String(10), nullable=False)
    funding_source = Column(String(30), nullable=False)
    payment_account_id = Column(Integer, ForeignKey("payment_accounts.id"), nullable=True)
    account_name = Column(String(100), nullable=True)
    cash_advance_id = Column(Integer, ForeignKey("cash_advances.id"), nullable=True)
    payment_method = Column(String(20), nullable=True)
    voucher_path = Column(String(500), nullable=True)
    expense_record_id = Column(Integer, nullable=True)  # 留存原成本编号，撤销删除成本后仍可审计
    previous_status = Column(String(30), nullable=False)
    paid_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    paid_by_name = Column(String(100), nullable=False)
    paid_at = Column(DateTime(timezone=True), nullable=False)
    status = Column(String(20), nullable=False, default="active", server_default="active")
    revoked_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    revoked_by_name = Column(String(100), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    revoke_reason = Column(String(500), nullable=True)
    fund_id = Column(Integer, ForeignKey("expense_funds.id", ondelete="SET NULL"), nullable=True)
    fund_item_snapshot = Column(JSON, nullable=True)

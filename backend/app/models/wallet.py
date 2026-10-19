"""逐笔实际收付和内部调拨；历史累计付款保留在原表，不猜补明细。"""
from sqlalchemy import Column, Integer, String, Date, DateTime, Numeric, ForeignKey, CheckConstraint
from app.database import Base
from app.core.timezone import thai_now


class PayablePayment(Base):
    __tablename__ = "payable_payments"
    __table_args__ = (CheckConstraint("amount > 0", name="ck_payable_payment_positive"),)
    id = Column(Integer, primary_key=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False, index=True)
    bill_id = Column(Integer, ForeignKey("payable_bills.id"), nullable=False, index=True)
    account_id = Column(Integer, ForeignKey("payment_accounts.id"), nullable=False)
    amount = Column(Numeric(18, 2), nullable=False)
    currency = Column(String(10), nullable=False)
    request_key = Column(String(64), nullable=True, unique=True)
    paid_at = Column(DateTime(timezone=True), nullable=False, default=thai_now)
    payment_method = Column(String(50))
    operator_id = Column(Integer, ForeignKey("users.id"), nullable=False)


class AccountTransfer(Base):
    __tablename__ = "account_transfers"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_transfer_positive"),
        CheckConstraint("from_account_id != to_account_id", name="ck_transfer_different_accounts"),
    )
    id = Column(Integer, primary_key=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False, index=True)
    from_account_id = Column(Integer, ForeignKey("payment_accounts.id"), nullable=False)
    to_account_id = Column(Integer, ForeignKey("payment_accounts.id"), nullable=False)
    request_key = Column(String(64), nullable=False, unique=True)
    transfer_date = Column(Date, nullable=False)
    amount = Column(Numeric(18, 2), nullable=False)
    currency = Column(String(10), nullable=False)
    remark = Column(String(500))
    operator_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=thai_now)

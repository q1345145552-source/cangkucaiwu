from sqlalchemy import Column, Integer, String, DateTime, Float, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
import enum

class CurrencyEnum(str, enum.Enum):
    THB = "THB"
    CNY = "CNY"

class MatchStatus(str, enum.Enum):
    UNMATCHED = "unmatched"
    MATCHED = "matched"

class ReconMatchStatus(str, enum.Enum):
    MATCHED = "matched"
    UNMATCHED = "unmatched"
    MANUAL_MATCHED = "manual_matched"

class RechargeDeclaration(Base):
    __tablename__ = "recharge_declarations"

    id = Column(Integer, primary_key=True, index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    declare_date = Column(DateTime, nullable=False)
    amount = Column(Float, nullable=False)
    currency = Column(String(10), nullable=False, default=CurrencyEnum.THB.value)
    payment_method = Column(String(30), nullable=True, comment="alipay/wechat/bank_transfer")
    payment_time = Column(DateTime, nullable=True)
    transaction_no = Column(String(100), nullable=True)
    account_tail = Column(String(10), nullable=True)
    screenshot = Column(String(500), nullable=True)
    remark = Column(String(500), nullable=True)
    declarer_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    match_status = Column(String(20), nullable=False, default=MatchStatus.UNMATCHED.value)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    warehouse = relationship("Warehouse", back_populates="recharge_declarations")
    customer = relationship("Customer", back_populates="recharge_declarations")
    declarer = relationship("User", foreign_keys=[declarer_id])

class IncomingFlow(Base):
    __tablename__ = "incoming_flows"

    id = Column(Integer, primary_key=True, index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False, index=True)
    received_date = Column(DateTime, nullable=False)
    amount = Column(Float, nullable=False)
    currency = Column(String(10), nullable=False, default=CurrencyEnum.THB.value)
    payer_name = Column(String(200), nullable=True)
    payment_method = Column(String(30), nullable=True)
    remark = Column(String(500), nullable=True)
    entrant_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    match_status = Column(String(20), nullable=False, default=MatchStatus.UNMATCHED.value)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    warehouse = relationship("Warehouse", back_populates="incoming_flows")
    entrant = relationship("User", foreign_keys=[entrant_id])

class ReconciliationResult(Base):
    __tablename__ = "reconciliation_results"

    id = Column(Integer, primary_key=True, index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False, index=True)
    reconciliation_month = Column(String(7), nullable=False, comment="YYYY-MM")
    declaration_id = Column(Integer, ForeignKey("recharge_declarations.id"), nullable=True)
    flow_id = Column(Integer, ForeignKey("incoming_flows.id"), nullable=True)
    match_status = Column(String(20), nullable=False, default=ReconMatchStatus.UNMATCHED.value)
    amount_diff = Column(Float, default=0)
    handling_note = Column(String(500), nullable=True)
    confirmed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    confirmed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    declaration = relationship("RechargeDeclaration", foreign_keys=[declaration_id])
    flow = relationship("IncomingFlow", foreign_keys=[flow_id])
    confirmer = relationship("User", foreign_keys=[confirmed_by])

class ExchangeRate(Base):
    __tablename__ = "exchange_rates"

    id = Column(Integer, primary_key=True, index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=True, index=True)
    effective_from = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    from_currency = Column(String(5), nullable=False)
    to_currency = Column(String(5), nullable=False)
    rate = Column(Float, nullable=False)
    set_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

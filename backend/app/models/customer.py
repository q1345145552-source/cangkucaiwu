from sqlalchemy import Column, Integer, String, DateTime, Boolean, Float, ForeignKey, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base

class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False, index=True)
    customer_code = Column(String(50), nullable=False)
    company_name = Column(String(200), nullable=False)
    contact_person = Column(String(100), nullable=True)
    contact_info = Column(String(200), nullable=True)
    credit_status = Column(Boolean, default=False)
    credit_limit = Column(Float, default=0)
    remark = Column(String(500), nullable=True)
    tags = Column(JSON, nullable=True, comment="退款次数、赔付金额等统计数据")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    warehouse = relationship("Warehouse", back_populates="customers")
    recharge_declarations = relationship("RechargeDeclaration", back_populates="customer")

class PaymentAccount(Base):
    __tablename__ = "payment_accounts"

    id = Column(Integer, primary_key=True, index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False, index=True)
    account_name = Column(String(100), nullable=False)
    account_type = Column(String(20), nullable=False, comment="alipay/wechat/bank")
    account_number = Column(String(100), nullable=False)
    opening_balance = Column(Float, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    warehouse = relationship("Warehouse", back_populates="payment_accounts")

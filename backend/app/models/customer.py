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
    line_id = Column(String(100), nullable=True, comment="LINE账号")
    cargo_type = Column(String(50), nullable=True, comment="常用货品类型: general/sensitive/brand")
    logistics_channel = Column(String(100), nullable=True, comment="常用物流渠道")
    total_shipments = Column(Integer, default=0, comment="累计发货单数")
    total_shipping_cost = Column(Float, default=0, comment="累计发货运费")
    last_ship_date = Column(DateTime, nullable=True, comment="最近发货日期")
    debt_amount = Column(Float, default=0, comment="欠款金额")
    registration_date = Column(DateTime(timezone=True), server_default=func.now(), comment="注册日期")
    default_currency = Column(String(5), nullable=True, default="THB", comment="默认币种")
    default_payment_method = Column(String(30), nullable=True, comment="默认付款方式: alipay/wechat/bank_transfer")
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
    bank_name = Column(String(200), nullable=True, comment="开户银行")
    branch_name = Column(String(200), nullable=True, comment="开户支行")
    account_holder = Column(String(100), nullable=True, comment="账户持有人")
    currency = Column(String(10), nullable=True, default="THB", comment="币种")
    status = Column(String(10), nullable=True, default="active", comment="状态: active/inactive")
    remark = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    warehouse = relationship("Warehouse", back_populates="payment_accounts")

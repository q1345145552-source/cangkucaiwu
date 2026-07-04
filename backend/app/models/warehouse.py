from sqlalchemy import Column, Integer, String, DateTime, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base

class Warehouse(Base):
    __tablename__ = "warehouses"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True)
    name_th = Column(String(100), nullable=True)
    code = Column(String(20), nullable=False, unique=True)
    address = Column(String(255), nullable=True)
    contact_person = Column(String(100), nullable=True)
    contact_phone = Column(String(50), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    users = relationship("User", back_populates="warehouse", foreign_keys="User.warehouse_id")
    customers = relationship("Customer", back_populates="warehouse")
    payment_accounts = relationship("PaymentAccount", back_populates="warehouse")
    recharge_declarations = relationship("RechargeDeclaration", back_populates="warehouse")
    incoming_flows = relationship("IncomingFlow", back_populates="warehouse")

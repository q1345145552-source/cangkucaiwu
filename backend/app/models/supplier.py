from sqlalchemy import Column, Integer, String, DateTime, Float, ForeignKey, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base

class SupplierCategory(Base):
    __tablename__ = "supplier_categories"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True)
    sort_order = Column(Integer, default=0)
    is_active = Column(String(5), default="true")

class Supplier(Base):
    __tablename__ = "suppliers"

    id = Column(Integer, primary_key=True, index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=True, index=True)
    category_id = Column(Integer, ForeignKey("supplier_categories.id"), nullable=True)
    name = Column(String(200), nullable=False)
    contact_person = Column(String(100), nullable=True)
    contact_info = Column(String(200), nullable=True)
    address = Column(String(300), nullable=True)
    payment_terms = Column(String(100), nullable=True)
    cooperation_content = Column(String(500), nullable=True, comment="合作内容")
    settlement_cycle = Column(String(100), nullable=True, comment="结算周期")
    history_notes = Column(JSON, nullable=True, comment="历史记录")
    ai_evaluation = Column(JSON, nullable=True, comment="DeepSeek AI评估结果")
    ai_evaluated_at = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(String(5), default="true")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    category = relationship("SupplierCategory")
    payable_bills = relationship("PayableBill", back_populates="supplier")
    products = relationship("SupplierProduct", back_populates="supplier", cascade="all, delete-orphan")

class SupplierProduct(Base):
    __tablename__ = "supplier_products"
    id = Column(Integer, primary_key=True, index=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=False, index=True)
    product_name = Column(String(200), nullable=False, comment="产品名称")
    spec = Column(String(300), nullable=True, comment="规格")
    unit_price = Column(Float, nullable=False, comment="单价")
    unit = Column(String(20), nullable=True, default="个", comment="单位")
    remark = Column(String(500), nullable=True, comment="备注")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    supplier = relationship("Supplier", back_populates="products")

class SupplierLogisticsPrice(Base):
    """物流供应商路线报价"""
    __tablename__ = "supplier_logistics_prices"
    id = Column(Integer, primary_key=True, index=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=False, index=True)
    route_name = Column(String(200), nullable=False, comment="路线名称，如 曼谷→龙仔厝")
    cargo_type = Column(String(100), nullable=False, comment="货物类型，如 普货/易碎品/大件")
    starting_price = Column(Float, nullable=False, default=0, comment="起步价")
    price_per_kg = Column(Float, nullable=False, comment="每公斤价格")
    estimated_days = Column(String(50), nullable=True, comment="预计时效，如 1-2天")
    remark = Column(String(300), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    supplier = relationship("Supplier", backref="logistics_prices")

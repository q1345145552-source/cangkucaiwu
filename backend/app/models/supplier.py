from sqlalchemy import Column, Integer, String, DateTime, Float, ForeignKey, JSON, Index, text, Boolean, Numeric
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
    default_currency = Column(String(10), nullable=True, default="THB", comment="默认币种: THB/CNY")
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
    spec_price = Column(Float, nullable=True, comment="规格报价，如一打80泰铢")
    unit_price = Column(Float, nullable=False, comment="单价，如1泰铢每个")
    currency = Column(String(10), nullable=True, default="THB", comment="币种: THB/CNY")
    unit = Column(String(20), nullable=True, default="个", comment="单位")
    remark = Column(String(500), nullable=True, comment="备注")
    standard_sku_id = Column(Integer, ForeignKey('standard_skus.id'), nullable=True)
    catalog_attributes = Column(JSON, nullable=True)
    base_unit_factor = Column(Numeric(20,8), nullable=True)
    sku_snapshot = Column(JSON, nullable=True)
    catalog_revision = Column(Integer, nullable=True, default=0)
    catalog_active = Column(Boolean, nullable=True, default=True)
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


# 替换旧的 SupplierLogisticsPrice（保留兼容，新功能用下表）
class SupplierCrossBorderPrice(Base):
    """跨境物流三维定价：运输方式×货物类型×发货仓库"""
    __tablename__ = "supplier_cross_border_prices"
    id = Column(Integer, primary_key=True, index=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=False, index=True)
    transport_method = Column(String(20), nullable=False, comment="运输方式：海运/陆运")
    cargo_type = Column(String(20), nullable=False, comment="货物类型：普货/商检货/敏感货")
    origin_warehouse = Column(String(20), nullable=False, comment="发货仓库：深圳仓/义乌仓/广州仓")
    price_per_cbm = Column(Float, nullable=False, comment="每立方米价格（人民币）")
    estimated_days = Column(String(30), nullable=True, comment="预计时效")
    currency = Column(String(10), nullable=False, default="CNY")
    remark = Column(String(300), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    supplier = relationship("Supplier", backref="cross_border_prices")



class PurchaseOrder(Base):
    __tablename__ = 'purchase_orders'
    from app.core.payable_constraints import GUARDS
    __table_args__ = tuple(Index(name, *columns, unique=True, postgresql_where=text(predicate), sqlite_where=text(predicate))
        for name, (table, columns, predicate) in GUARDS.items() if table == 'purchase_orders')
    id = Column(Integer, primary_key=True, index=True)
    warehouse_id = Column(Integer, ForeignKey('warehouses.id'), nullable=False, index=True)
    supplier_id = Column(Integer, ForeignKey('suppliers.id'), nullable=False)
    order_number = Column(String(50), nullable=False, unique=True, index=True)
    request_key = Column(String(100), nullable=True)
    request_fingerprint = Column(String(64), nullable=True)
    receipt_baseline = Column(JSON, nullable=True, comment='Original recorded receipt basis; never rebase from cumulative batch cache')
    total_amount = Column(Float, nullable=False)
    currency = Column(String(10), nullable=False, default='THB')
    items = Column(JSON, nullable=False)
    payable_bill_id = Column(Integer, ForeignKey('payable_bills.id'), nullable=True)
    status = Column(String(20), default='confirmed')  # pending / confirmed / rejected
    flow_status = Column(String(30), default='pending_confirmation', comment="流程状态: pending_confirmation/supplier_confirmed/shipped/arrived/completed")
    remark = Column(String(500), nullable=True)
    reject_reason = Column(String(500), nullable=True, comment="驳回原因")
    # 发送标记
    sent_at = Column(DateTime(timezone=True), nullable=True, comment="发送给供应商时间")
    sent_by = Column(Integer, ForeignKey('users.id'), nullable=True, comment="发送人")
    # 回执
    receipt_file = Column(String(500), nullable=True, comment="供应商回执照片路径")
    receipt_uploaded_by = Column(Integer, ForeignKey('users.id'), nullable=True, comment="回执上传人")
    receipt_uploaded_at = Column(DateTime(timezone=True), nullable=True, comment="回执上传时间")
    # 发货
    shipped_at = Column(DateTime(timezone=True), nullable=True, comment="发货时间")
    shipped_by = Column(Integer, ForeignKey('users.id'), nullable=True, comment="发货标记人")
    receipt_status = Column(String(20), default='not_received', comment="收货状态: not_received/received/partially_received")
    arrival_photo = Column(String(500), nullable=True, comment="到货照片路径")
    received_by = Column(Integer, ForeignKey('users.id'), nullable=True, comment="收货人")
    received_at = Column(DateTime(timezone=True), nullable=True, comment="收货时间")
    created_by = Column(Integer, ForeignKey('users.id'), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ProcurementPriceHistory(Base):
    """耗材采购价格历史：每次下单的每个产品记录一行，按 产品名+规格 形成价格历史。"""
    __tablename__ = "procurement_price_history"

    id = Column(Integer, primary_key=True, index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False, index=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=False)
    purchase_order_id = Column(Integer, ForeignKey("purchase_orders.id"), nullable=True)
    product_name = Column(String(200), nullable=False)
    spec = Column(String(300), nullable=True)
    unit_price = Column(Float, nullable=False)
    quantity = Column(Integer, default=1)
    currency = Column(String(10), nullable=True)
    unit = Column(String(20), nullable=True)
    sku_snapshot = Column(JSON, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    pricing_snapshot = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)


class ProcurementPriceAnomaly(Base):
    """耗材采购价格异常记录：下单价格高于历史均价一定比例时记录。"""
    __tablename__ = "procurement_price_anomalies"

    id = Column(Integer, primary_key=True, index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False, index=True)
    product_name = Column(String(200), nullable=False)
    spec = Column(String(300), nullable=True)
    purchase_price = Column(Float, nullable=False)
    historical_avg = Column(Float, nullable=False, default=0)
    exceed_percent = Column(Float, nullable=False, default=0)
    orderer_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    orderer_name = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)


class ProcurementNonLowestRecord(Base):
    """非最低价采购记录：所选供应商价格高于该产品最低报价，需填原因。"""
    __tablename__ = "procurement_non_lowest_records"

    id = Column(Integer, primary_key=True, index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False, index=True)
    product_name = Column(String(200), nullable=False)
    spec = Column(String(300), nullable=True)
    selected_supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=True)
    selected_supplier_name = Column(String(200), nullable=True)
    selected_price = Column(Float, nullable=False)
    lowest_supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=True)
    lowest_supplier_name = Column(String(200), nullable=True)
    lowest_price = Column(Float, nullable=False, default=0)
    price_diff = Column(Float, nullable=False, default=0)
    quantity = Column(Integer, default=1)
    reason = Column(String(500), nullable=True)
    orderer_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    orderer_name = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)


class SupplierRoutePrice(Base):
    """独立路线报价；不把kg/件价格写入旧每方报价，不改变旧报价计算。"""
    __tablename__ = 'supplier_route_prices'
    id = Column(Integer, primary_key=True, index=True)
    supplier_id = Column(Integer, ForeignKey('suppliers.id'), nullable=False, index=True)
    origin = Column(String(200), nullable=False)
    destination = Column(String(200), nullable=False)
    transport_method = Column(String(20), nullable=False)
    quantity_from = Column(Numeric(20, 6), nullable=False)
    quantity_to = Column(Numeric(20, 6), nullable=False)
    pricing_unit = Column(String(10), nullable=False)
    unit_price = Column(Numeric(20, 6), nullable=False)
    currency = Column(String(10), nullable=False)
    transit_days = Column(Integer, nullable=False)
    minimum_charge = Column(Numeric(20, 6), nullable=False)
    remark = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

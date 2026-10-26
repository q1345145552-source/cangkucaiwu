"""Quantity journals only. No inferred opening, valuation, cash or expense entries."""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Numeric, ForeignKey, JSON, UniqueConstraint, CheckConstraint
from sqlalchemy.sql import func
from app.database import Base


class InventoryAccount(Base):
    __tablename__ = 'inventory_accounts'
    __table_args__ = (
        UniqueConstraint('warehouse_id', 'sku_id', 'base_unit', name='uq_inventory_account_unit'),
        CheckConstraint('recorded_quantity >= 0', name='ck_inventory_nonnegative'),
    )
    id = Column(Integer, primary_key=True)
    warehouse_id = Column(Integer, ForeignKey('warehouses.id'), nullable=False, index=True)
    sku_id = Column(Integer, ForeignKey('standard_skus.id'), nullable=False)
    base_unit = Column(String(20), nullable=False)
    sku_snapshot = Column(JSON, nullable=False)
    recorded_quantity = Column(Numeric(24, 8), nullable=False, default=0)
    opening_confirmed = Column(Boolean, nullable=False, default=False)
    opening_at = Column(DateTime(timezone=True), nullable=True)
    revision = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class InventoryMovement(Base):
    __tablename__ = 'inventory_movements'
    __table_args__ = (
        UniqueConstraint('reverses_id', name='uq_inventory_reversal'),
        UniqueConstraint('account_id', 'opening_token', name='uq_inventory_opening'),
    )
    id = Column(Integer, primary_key=True)
    warehouse_id = Column(Integer, ForeignKey('warehouses.id'), nullable=False, index=True)
    account_id = Column(Integer, ForeignKey('inventory_accounts.id'), nullable=False, index=True)
    kind = Column(String(30), nullable=False)
    quantity = Column(Numeric(24, 8), nullable=False)
    balance_after = Column(Numeric(24, 8), nullable=False)
    opening_token = Column(String(20), nullable=True)
    reference_id = Column(Integer, ForeignKey('inventory_movements.id'), nullable=True)
    reverses_id = Column(Integer, ForeignKey('inventory_movements.id'), nullable=True)
    source_type = Column(String(40), nullable=False)
    source_id = Column(Integer, nullable=True)
    source_line_id = Column(String(100), nullable=True)
    source_snapshot = Column(JSON, nullable=False)
    occurred_at = Column(DateTime(timezone=True), nullable=False)
    reason = Column(String(1000), nullable=False)
    operator_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    operator_name = Column(String(100), nullable=False)
    status = Column(String(20), nullable=False, default='active')
    # Unknown cost is NULL, never a fabricated zero or today's quote price.
    cost_amount = Column(Numeric(24, 2), nullable=True)
    cost_currency = Column(String(10), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class InventoryReceiptLink(Base):
    __tablename__ = 'inventory_receipt_links'
    __table_args__ = (UniqueConstraint('warehouse_id', 'receipt_event_id', 'line_id', name='uq_inventory_receipt_line'),)
    id = Column(Integer, primary_key=True)
    warehouse_id = Column(Integer, ForeignKey('warehouses.id'), nullable=False, index=True)
    receipt_event_id = Column(Integer, ForeignKey('purchase_receipt_events.id'), nullable=False)
    purchase_order_id = Column(Integer, ForeignKey('purchase_orders.id'), nullable=False)
    line_id = Column(String(100), nullable=False)
    original_quantity = Column(Numeric(24, 8), nullable=False)
    original_unit = Column(String(20), nullable=True)
    source_fingerprint = Column(String(64), nullable=False)
    source_snapshot = Column(JSON, nullable=False)
    status = Column(String(20), nullable=False)  # pending / recorded / reversed
    pending_reason = Column(String(1000), nullable=True)
    movement_id = Column(Integer, ForeignKey('inventory_movements.id'), nullable=True)
    resolution = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class InventoryOperation(Base):
    __tablename__ = 'inventory_operations'
    __table_args__ = (UniqueConstraint('warehouse_id', 'operator_id', 'request_key', name='uq_inventory_operation'),)
    id = Column(Integer, primary_key=True)
    warehouse_id = Column(Integer, ForeignKey('warehouses.id'), nullable=False)
    operator_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    request_key = Column(String(100), nullable=False)
    request_fingerprint = Column(String(64), nullable=False)
    kind = Column(String(30), nullable=False)
    response = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class InventoryPolicy(Base):
    __tablename__ = 'inventory_policies'
    __table_args__ = (
        UniqueConstraint('warehouse_id', name='uq_inventory_policy_warehouse'),
        CheckConstraint("valuation_method IN ('unconfigured','quantity_only')", name='ck_inventory_valuation_method'),
    )
    id = Column(Integer, primary_key=True)
    warehouse_id = Column(Integer, ForeignKey('warehouses.id'), nullable=False)
    valuation_method = Column(String(30), nullable=False, default='unconfigured')
    revision = Column(Integer, nullable=False, default=1)
    updated_by = Column(Integer, ForeignKey('users.id'), nullable=False)
    reason = Column(String(1000), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class InventoryStocktake(Base):
    __tablename__ = 'inventory_stocktakes'
    __table_args__ = (
        CheckConstraint('counted_quantity >= 0 AND book_quantity >= 0', name='ck_inventory_count_nonnegative'),
        CheckConstraint("status IN ('pending','approved','rejected')", name='ck_inventory_count_status'),
        UniqueConstraint('adjustment_id', name='uq_inventory_count_adjustment'),
    )
    id = Column(Integer, primary_key=True)
    warehouse_id = Column(Integer, ForeignKey('warehouses.id'), nullable=False, index=True)
    account_id = Column(Integer, ForeignKey('inventory_accounts.id'), nullable=False, index=True)
    book_quantity = Column(Numeric(24, 8), nullable=False)
    counted_quantity = Column(Numeric(24, 8), nullable=False)
    account_version = Column(String(64), nullable=False)
    snapshot = Column(JSON, nullable=False)
    counted_at = Column(DateTime(timezone=True), nullable=False)
    reason = Column(String(1000), nullable=False)
    created_by = Column(Integer, ForeignKey('users.id'), nullable=False)
    creator_name = Column(String(100), nullable=False)
    status = Column(String(20), nullable=False, default='pending')
    reviewed_by = Column(Integer, ForeignKey('users.id'), nullable=True)
    reviewer_name = Column(String(100), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    review_reason = Column(String(1000), nullable=True)
    adjustment_id = Column(Integer, ForeignKey('inventory_movements.id'), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class InventoryControl(Base):
    __tablename__ = 'inventory_controls'
    __table_args__ = (
        UniqueConstraint('warehouse_id', 'account_id', name='uq_inventory_control_account'),
        CheckConstraint('minimum_quantity IS NULL OR minimum_quantity >= 0', name='ck_inventory_minimum'),
        CheckConstraint('receipt_usage_ratio IS NULL OR receipt_usage_ratio > 1', name='ck_inventory_usage_ratio'),
    )
    id = Column(Integer, primary_key=True)
    warehouse_id = Column(Integer, ForeignKey('warehouses.id'), nullable=False)
    account_id = Column(Integer, ForeignKey('inventory_accounts.id'), nullable=False)
    minimum_quantity = Column(Numeric(24, 8), nullable=True)
    receipt_usage_ratio = Column(Numeric(24, 8), nullable=True)
    stockpiling_note = Column(String(1000), nullable=False)
    reason = Column(String(1000), nullable=False)
    revision = Column(Integer, nullable=False, default=1)
    updated_by = Column(Integer, ForeignKey('users.id'), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

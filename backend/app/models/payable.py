from sqlalchemy import Column, Integer, String, DateTime, Float, ForeignKey, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
import enum

class PayableStatus(str, enum.Enum):
    PENDING = "pending"
    PAID = "paid"
    PARTIALLY_PAID = "partially_paid"
    OVERDUE = "overdue"

class PlanStatus(str, enum.Enum):
    PENDING = "pending"
    EXECUTED = "executed"
    CANCELLED = "cancelled"

class PayableBill(Base):
    __tablename__ = "payable_bills"

    id = Column(Integer, primary_key=True, index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False, index=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=False)
    bill_number = Column(String(50), nullable=False)
    bill_date = Column(DateTime, nullable=False)
    due_date = Column(DateTime, nullable=False)
    amount = Column(Float, nullable=False)
    currency = Column(String(5), nullable=False, default="THB")
    paid_amount = Column(Float, default=0)
    status = Column(String(30), default=PayableStatus.PENDING.value)
    confirmed_amount = Column(Float, nullable=True, comment="供应商确认金额，与amount不同时标差异")
    payment_commitment_days = Column(Integer, nullable=True, comment="付款承诺天数")
    payment_voucher = Column(String(500), nullable=True, comment="付款凭证截图路径")
    payment_method = Column(String(50), nullable=True, comment="付款方式：银行转账/现金/支票等")
    is_fund_linked = Column(String(10), nullable=True, comment="是否备用金关联标记")
    is_duplicate_warned = Column(String(10), nullable=True, comment="重复账单警告标记")
    detail = Column(String(1000), nullable=True, comment="费用明细")
    bill_attachment = Column(String(500), nullable=True, comment="账单附件路径")
    remark = Column(String(500), nullable=True)
    voucher = Column(String(500), nullable=True)
    paid_at = Column(DateTime(timezone=True), nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    supplier = relationship("Supplier", back_populates="payable_bills")

class PayablePlan(Base):
    __tablename__ = "payable_plans"

    id = Column(Integer, primary_key=True, index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False, index=True)
    plan_name = Column(String(200), nullable=False)
    planned_date = Column(DateTime, nullable=False)
    total_amount = Column(Float, nullable=False)
    status = Column(String(20), default=PlanStatus.PENDING.value)
    bill_ids = Column(JSON, nullable=True, comment="关联账单ID列表")
    detail = Column(String(1000), nullable=True, comment="费用明细")
    bill_attachment = Column(String(500), nullable=True, comment="账单附件路径")
    remark = Column(String(500), nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

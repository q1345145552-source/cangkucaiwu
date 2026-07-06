from sqlalchemy import Column, Integer, String, DateTime, Float, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
import enum

class IncomeExpenseType(str, enum.Enum):
    INCOME = "income"
    EXPENSE = "expense"

class CategoryStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"

class IncomeExpenseCategory(Base):
    __tablename__ = "income_expense_categories"

    id = Column(Integer, primary_key=True, index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False, index=True)
    type = Column(String(10), nullable=False)
    name = Column(String(100), nullable=False)
    sort_order = Column(Integer, default=0)
    category_group = Column(String(20), nullable=False, default="other")  # operating or other
    status = Column(String(20), default=CategoryStatus.ACTIVE.value)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class IncomeRecord(Base):
    __tablename__ = "income_records"

    id = Column(Integer, primary_key=True, index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False, index=True)
    category_id = Column(Integer, ForeignKey("income_expense_categories.id"), nullable=False)
    account_id = Column(Integer, ForeignKey("payment_accounts.id"), nullable=False)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    amount = Column(Float, nullable=False)
    currency = Column(String(5), nullable=False, default="THB")
    income_date = Column(DateTime, nullable=False)
    voucher = Column(String(500), nullable=True)
    remark = Column(String(500), nullable=True)
    confirmed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    category = relationship("IncomeExpenseCategory", foreign_keys=[category_id])
    account = relationship("PaymentAccount", foreign_keys=[account_id])
    customer = relationship("Customer", foreign_keys=[customer_id])

class ExpenseRecord(Base):
    __tablename__ = "expense_records"

    id = Column(Integer, primary_key=True, index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False, index=True)
    category_id = Column(Integer, ForeignKey("income_expense_categories.id"), nullable=False)
    account_id = Column(Integer, ForeignKey("payment_accounts.id"), nullable=False)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=True)
    amount = Column(Float, nullable=False)
    currency = Column(String(5), nullable=False, default="THB")
    expense_date = Column(DateTime, nullable=False)
    voucher = Column(String(500), nullable=True)
    remark = Column(String(500), nullable=True)
    approved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    category = relationship("IncomeExpenseCategory", foreign_keys=[category_id])
    account = relationship("PaymentAccount", foreign_keys=[account_id])
    supplier = relationship("Supplier", foreign_keys=[supplier_id])

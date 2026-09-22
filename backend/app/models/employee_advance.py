from sqlalchemy import Column, Integer, String, DateTime, Float, ForeignKey, Date, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class EmployeeAdvance(Base):
    """员工工资预支记录"""
    __tablename__ = "employee_advances"

    id = Column(Integer, primary_key=True, index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False, index=True)
    amount = Column(Float, nullable=False)
    currency = Column(String(5), default="THB")
    advance_date = Column(Date, nullable=False, index=True)
    period = Column(String(7), nullable=False, index=True)  # YYYY-MM
    half = Column(String(20), nullable=False, default="first_half")  # first_half / second_half
    source = Column(String(20), nullable=False, default="supervisor")  # supervisor / fund
    fund_account_id = Column(Integer, ForeignKey("expense_funds.id"), nullable=True)
    remark = Column(String(500), nullable=True)
    operator_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    deducted_amount = Column(Float, default=0)
    status = Column(String(20), default="unpaid")  # unpaid / partial / deducted
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    employee = relationship("Employee", foreign_keys=[employee_id])
    operator = relationship("User", foreign_keys=[operator_id])
    fund_account = relationship("ExpenseFund", foreign_keys=[fund_account_id])

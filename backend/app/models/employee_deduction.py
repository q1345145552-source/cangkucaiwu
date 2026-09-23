from sqlalchemy import Column, Integer, String, DateTime, Float, ForeignKey, Date
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class EmployeeDeduction(Base):
    """员工临时扣款记录（如罚款等，一次性扣款）。"""
    __tablename__ = "employee_deductions"

    id = Column(Integer, primary_key=True, index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False, index=True)
    amount = Column(Float, nullable=False)
    deduction_date = Column(Date, nullable=False, index=True)
    period = Column(String(7), nullable=False, index=True)  # YYYY-MM
    half = Column(String(20), nullable=False, default="first_half")  # first_half / second_half
    reason = Column(String(500), nullable=False)
    operator_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    employee = relationship("Employee", foreign_keys=[employee_id])
    operator = relationship("User", foreign_keys=[operator_id])


class EmployeeFixedDeduction(Base):
    """员工每月固定扣款项目（宿舍费、伙食费等，整月扣一次，在下半月周期扣全额）。"""
    __tablename__ = "employee_fixed_deductions"

    id = Column(Integer, primary_key=True, index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    amount = Column(Float, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    employee = relationship("Employee", foreign_keys=[employee_id])

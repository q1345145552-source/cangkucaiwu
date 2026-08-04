from sqlalchemy import Column, Integer, String, DateTime, Float, ForeignKey, Date, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class PayrollRecord(Base):
    """Monthly payroll record for each employee"""
    __tablename__ = "payroll_records"

    id = Column(Integer, primary_key=True, index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False, index=True)
    period = Column(String(7), nullable=False, index=True)  # YYYY-MM
    status = Column(String(20), nullable=False, default="pending")  # pending / confirmed
    disbursed = Column(Boolean, default=False)  # 已发放

    # Attendance breakdown
    total_days_in_month = Column(Integer, default=0)
    attendance_days = Column(Integer, default=0)
    leave_days = Column(Integer, default=0)
    rest_days = Column(Integer, default=0)
    absence_days = Column(Integer, default=0)

    # Salary components
    employee_status = Column(String(20), default="trial")  # trial / regular
    daily_wage = Column(Float, default=400)
    base_salary = Column(Float, default=12000)
    base_pay = Column(Float, default=0)

    # Additions
    overtime_pay = Column(Float, default=0)
    overtime_hours = Column(Float, default=0)

    # Deductions
    late_penalty = Column(Float, default=0)
    leave_deduction = Column(Float, default=0)
    absence_deduction = Column(Float, default=0)

    # Totals
    gross_pay = Column(Float, default=0)
    total_deductions = Column(Float, default=0)
    net_pay = Column(Float, default=0)

    detail = Column(String(3000), nullable=True)

    confirmed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    confirmed_at = Column(DateTime(timezone=True), nullable=True)

    # Disbursement tracking
    disbursed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    disbursed_at = Column(DateTime(timezone=True), nullable=True)
    signature_path = Column(String(500), nullable=True)  # 签字照片路径

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    employee = relationship("Employee", foreign_keys=[employee_id])
    confirm_user = relationship("User", foreign_keys=[confirmed_by])
    disburse_user = relationship("User", foreign_keys=[disbursed_by])

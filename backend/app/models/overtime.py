from sqlalchemy import Column, Integer, String, DateTime, Float, ForeignKey, Date, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class OvertimeTask(Base):
    __tablename__ = "overtime_tasks"

    id = Column(Integer, primary_key=True, index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    start_time = Column(String(5), nullable=False)  # HH:MM
    end_time = Column(String(5), nullable=False)  # HH:MM
    hours = Column(Float, nullable=False, default=0)
    hourly_rate = Column(Float, nullable=False, default=75)
    status = Column(String(20), nullable=False, default="pending")  # pending / completed
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    creator = relationship("User", foreign_keys=[created_by], backref="created_overtimes")
    assignments = relationship("OvertimeAssignment", back_populates="overtime_task", cascade="all, delete-orphan")


class OvertimeAssignment(Base):
    __tablename__ = "overtime_assignments"

    id = Column(Integer, primary_key=True, index=True)
    overtime_id = Column(Integer, ForeignKey("overtime_tasks.id"), nullable=False, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    confirmed = Column(Boolean, default=False)
    confirmed_at = Column(DateTime(timezone=True), nullable=True)
    earned_amount = Column(Float, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    overtime_task = relationship("OvertimeTask", back_populates="assignments")
    employee = relationship("Employee", foreign_keys=[employee_id])
    user = relationship("User", foreign_keys=[user_id])

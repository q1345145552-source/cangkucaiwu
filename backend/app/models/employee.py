from sqlalchemy import Column, Integer, String, DateTime, Float, ForeignKey, Boolean, Date, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base

class Employee(Base):
    __tablename__ = "employees"

    id = Column(Integer, primary_key=True, index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    position = Column(String(50), nullable=True, default="仓库劳工")
    myanmar_id = Column(String(50), nullable=True)
    address = Column(String(300), nullable=True)
    phone = Column(String(50), nullable=True)
    emergency_contact = Column(String(100), nullable=True)
    hire_date = Column(DateTime, nullable=True)
    status = Column(String(20), default="trial")
    daily_wage = Column(Float, nullable=True, default=400)
    base_salary = Column(Float, nullable=True, default=12000)
    remark = Column(String(500), nullable=True)

    # Photo
    photo_path = Column(String(500), nullable=True, comment="员工本人照片路径")

    # Passport & Work Permit (compliance)
    passport_number = Column(String(50), nullable=True, comment="护照号码")
    work_permit_number = Column(String(50), nullable=True, comment="工作证号码")
    passport_expiry = Column(Date, nullable=True, comment="护照有效期")
    work_permit_expiry = Column(Date, nullable=True, comment="工作证有效期")

    # Promotion (probation → regular)
    promotion_date = Column(Date, nullable=True, comment="转正日期")

    # Tags (comma-separated)
    tags = Column(Text, nullable=True, comment="标签，逗号分隔")

    # Link to login user account (formal relationship, not name matching)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, unique=True, comment="关联登录账号")

    resignation_date = Column(Date, nullable=True)
    resignation_reason = Column(String(50), nullable=True)
    resignation_note = Column(String(500), nullable=True)
    blacklisted = Column(Boolean, default=False)
    blacklist_reason = Column(String(500), nullable=True)

    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    warehouse = relationship("Warehouse", backref="employees")
    user = relationship("User", foreign_keys=[user_id], backref="employee_profile")

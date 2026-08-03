from sqlalchemy import Column, Integer, String, DateTime, Float, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base

class Employee(Base):
    __tablename__ = "employees"

    id = Column(Integer, primary_key=True, index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    position = Column(String(50), nullable=True, default="仓库劳工")
    myanmar_id = Column(String(50), nullable=True, comment="缅甸身份证号")
    address = Column(String(300), nullable=True)
    phone = Column(String(50), nullable=True)
    emergency_contact = Column(String(100), nullable=True, comment="紧急联系人")
    hire_date = Column(DateTime, nullable=True, comment="入职日期")
    status = Column(String(20), default="trial", comment="试用期trial/正式regular/已离职resigned")
    daily_wage = Column(Float, nullable=True, default=400, comment="日薪")
    base_salary = Column(Float, nullable=True, default=12000, comment="底薪")
    remark = Column(String(500), nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    warehouse = relationship("Warehouse", backref="employees")

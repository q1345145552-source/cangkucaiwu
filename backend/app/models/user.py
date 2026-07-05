from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
from app.core.permissions import Role

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    display_name = Column(String(100), nullable=False)
    role = Column(String(50), nullable=False, default=Role.STAFF.value)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=True)
    line_user_id = Column(String(100), nullable=True, unique=True)
    extra_permissions = Column(JSON, nullable=True, default=list)
    is_active = Column(Boolean, default=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    warehouse = relationship("Warehouse", back_populates="users", foreign_keys=[warehouse_id])
    creator = relationship("User", remote_side=[id], backref="created_users")

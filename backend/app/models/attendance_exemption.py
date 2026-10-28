from sqlalchemy import Column, Integer, String, Date, DateTime, ForeignKey, Index, text
from sqlalchemy.sql import func
from app.database import Base


class AttendanceExemption(Base):
    __tablename__ = 'attendance_exemptions'
    id = Column(Integer, primary_key=True)
    warehouse_id = Column(Integer, ForeignKey('warehouses.id'), nullable=False)
    date = Column(Date, nullable=False)
    reason = Column(String(500), nullable=False)
    created_by = Column(Integer, ForeignKey('users.id'), nullable=False)
    created_by_name = Column(String(100), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    status = Column(String(20), nullable=False, default='active', server_default='active')
    revoked_by = Column(Integer, ForeignKey('users.id'), nullable=True)
    revoked_by_name = Column(String(100))
    revoked_at = Column(DateTime(timezone=True))
    revoke_reason = Column(String(500))
    __table_args__ = (Index('uq_attendance_exemption_active', 'warehouse_id', 'date', unique=True,
                           postgresql_where=text("status = 'active'"), sqlite_where=text("status = 'active'")),)

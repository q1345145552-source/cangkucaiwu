from sqlalchemy import Column, Integer, String, DateTime, Float, ForeignKey, Date, Boolean, true
from sqlalchemy.sql import func
from app.database import Base


class ClockInMakeupBatch(Base):
    __tablename__ = "clock_in_makeup_batches"
    id = Column(Integer, primary_key=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False)
    clock_date = Column(Date, nullable=False)
    operator_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    operator_name = Column(String(100), nullable=False)
    operated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    reason = Column(String(500), nullable=False)
    created_count = Column(Integer, nullable=False, default=0, server_default="0")
    status = Column(String(20), nullable=False, default="active", server_default="active")
    revoked_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    revoked_by_name = Column(String(100), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)


class ClockInRecord(Base):
    __tablename__ = "clock_in_records"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=True)
    clock_date = Column(Date, nullable=False, index=True)
    session = Column(Integer, nullable=False, default=1)
    clocked_in_at = Column(DateTime(timezone=True), server_default=func.now())
    photo_path = Column(String(500), nullable=True)
    status = Column(String(20), default="normal")
    penalty_amount = Column(Float, default=0)
    remark = Column(String(200), nullable=True)
    # 补卡标记（管理员/主管代补）
    is_makeup = Column(Boolean, default=False, comment="补卡标记")
    makeup_counts_toward_limit = Column(Boolean, nullable=False, default=True, server_default=true(), comment="是否计入个人补卡额度")
    makeup_by = Column(Integer, ForeignKey("users.id"), nullable=True, comment="补卡人")
    makeup_at = Column(DateTime(timezone=True), nullable=True, comment="补卡操作时间")
    makeup_reason = Column(String(500), nullable=True, comment="补卡原因")
    makeup_batch_id = Column(Integer, ForeignKey("clock_in_makeup_batches.id"), nullable=True, comment="批量补卡批次；旧记录与单条补卡留空")

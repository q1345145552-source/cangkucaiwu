from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, JSON
from sqlalchemy.sql import func
from app.database import Base


class DataChangeHistory(Base):
    __tablename__ = "data_change_history"

    id = Column(Integer, primary_key=True, index=True)
    module = Column(String(50), nullable=False, index=True, comment="模块: recharge/reimbursement/expense")
    record_id = Column(Integer, nullable=False, index=True, comment="被修改记录的编号")
    operator_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    operator_name = Column(String(100), nullable=True, comment="操作人姓名（冗余存储，用户删除后仍可显示）")
    operation_type = Column(String(20), nullable=False, comment="create/edit/delete")
    before_data = Column(JSON, nullable=True, comment="修改前数据")
    after_data = Column(JSON, nullable=True, comment="修改后数据")
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

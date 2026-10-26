"""Explicit one-use authorizations, immutable action receipts and append-only risk reviews."""
from sqlalchemy import Column,Integer,String,DateTime,ForeignKey,JSON,UniqueConstraint
from sqlalchemy.sql import func
from app.database import Base

class ProcurementActionException(Base):
    __tablename__='procurement_action_exceptions'
    __table_args__=(UniqueConstraint('warehouse_id','granted_by','request_key',name='uq_procurement_exception_request'),)
    id=Column(Integer,primary_key=True)
    warehouse_id=Column(Integer,ForeignKey('warehouses.id'),nullable=False,index=True)
    purchase_order_id=Column(Integer,ForeignKey('purchase_orders.id'),nullable=False,index=True)
    action=Column(String(20),nullable=False)
    operator_id=Column(Integer,ForeignKey('users.id'),nullable=False)
    policy_version=Column(String(64),nullable=False)
    business_version=Column(String(64),nullable=False)
    request_key=Column(String(100),nullable=False)
    request_fingerprint=Column(String(64),nullable=False)
    granted_by=Column(Integer,ForeignKey('users.id'),nullable=False)
    reason=Column(String(1000),nullable=False)
    expires_at=Column(DateTime(timezone=True),nullable=False)
    created_at=Column(DateTime(timezone=True),nullable=False,server_default=func.now())
    status=Column(String(20),nullable=False,default='active')
    used_at=Column(DateTime(timezone=True),nullable=True)
    used_request_key=Column(String(100),nullable=True)
    revoked_by=Column(Integer,ForeignKey('users.id'),nullable=True)
    revoked_at=Column(DateTime(timezone=True),nullable=True)
    revoke_reason=Column(String(1000),nullable=True)

class ProcurementDutyExecution(Base):
    __tablename__='procurement_duty_executions'
    __table_args__=(UniqueConstraint('warehouse_id','action','operator_id','request_key',name='uq_procurement_duty_execution'),)
    id=Column(Integer,primary_key=True)
    warehouse_id=Column(Integer,ForeignKey('warehouses.id'),nullable=False,index=True)
    purchase_order_id=Column(Integer,ForeignKey('purchase_orders.id'),nullable=True,index=True)
    action=Column(String(20),nullable=False)
    operator_id=Column(Integer,ForeignKey('users.id'),nullable=False)
    request_key=Column(String(100),nullable=False)
    request_fingerprint=Column(String(64),nullable=False)
    policy_version=Column(String(64),nullable=False)
    exception_id=Column(Integer,ForeignKey('procurement_action_exceptions.id'),nullable=True)
    response=Column(JSON,nullable=False)
    created_at=Column(DateTime(timezone=True),nullable=False,server_default=func.now())

class ProcurementRiskReview(Base):
    __tablename__='procurement_risk_reviews'
    __table_args__=(UniqueConstraint('warehouse_id','reviewer_id','request_key',name='uq_procurement_risk_review_request'),)
    id=Column(Integer,primary_key=True)
    warehouse_id=Column(Integer,ForeignKey('warehouses.id'),nullable=False,index=True)
    month=Column(String(7),nullable=False,index=True)
    rule=Column(String(50),nullable=False)
    subject_key=Column(String(64),nullable=False,index=True)
    signal_id=Column(String(64),nullable=False)
    rule_version=Column(String(100),nullable=False)
    scope=Column(JSON,nullable=False)
    evidence_version=Column(String(64),nullable=False)
    snapshot=Column(JSON,nullable=False)
    conclusion=Column(String(20),nullable=False)
    reason=Column(String(1000),nullable=False)
    reviewer_id=Column(Integer,ForeignKey('users.id'),nullable=False)
    request_key=Column(String(100),nullable=False)
    request_fingerprint=Column(String(64),nullable=False)
    created_at=Column(DateTime(timezone=True),nullable=False,server_default=func.now())

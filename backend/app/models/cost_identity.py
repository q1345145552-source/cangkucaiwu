"""One expense origin, shared by its derived accounting rows; not another money ledger."""
from sqlalchemy import Column, Integer, String, Date, DateTime, Boolean, Numeric, JSON, ForeignKey, Index, text
from sqlalchemy.sql import func
from app.database import Base

GUARDS = {
    'uq_cost_origin': (['warehouse_id','source_type','source_id'], None),
    'uq_cost_active_invoice': (['warehouse_id','invoice_key'], "invoice_key IS NOT NULL AND active = true"),
    'uq_cost_request': (['warehouse_id','source_type','request_key'], 'request_key IS NOT NULL'),
}

class CostIdentity(Base):
    __tablename__ = 'cost_identities'
    __table_args__ = tuple(Index(name,*columns,unique=True,**(
        {'postgresql_where':text(predicate),'sqlite_where':text(predicate)} if predicate else {}))
        for name,(columns,predicate) in GUARDS.items())
    id=Column(Integer,primary_key=True)
    warehouse_id=Column(Integer,ForeignKey('warehouses.id'),nullable=False,index=True)
    source_type=Column(String(20),nullable=False)
    source_id=Column(Integer,nullable=False)
    supplier_id=Column(Integer,ForeignKey('suppliers.id'),nullable=True)
    invoice_identity=Column(JSON,nullable=True)
    invoice_key=Column(String(64),nullable=True)
    issuer_key=Column(String(64),nullable=True)
    amount=Column(Numeric(20,2),nullable=False)
    currency=Column(String(5),nullable=False)
    expense_date=Column(Date,nullable=False)
    active=Column(Boolean,nullable=False,default=False)
    paid_locked=Column(Boolean,nullable=False,default=False)
    payment_unknown=Column(Boolean,nullable=False,default=False)
    source_state=Column(String(30),nullable=True)
    source_deleted=Column(Boolean,nullable=False,default=False)
    version=Column(String(64),nullable=False)
    request_key=Column(String(100),nullable=True)
    request_fingerprint=Column(String(64),nullable=True)
    confirmation=Column(JSON,nullable=True)
    operator_id=Column(Integer,ForeignKey('users.id'),nullable=False)
    operator_name=Column(String(100),nullable=False)
    created_at=Column(DateTime(timezone=True),server_default=func.now())
    updated_at=Column(DateTime(timezone=True),server_default=func.now(),onupdate=func.now())

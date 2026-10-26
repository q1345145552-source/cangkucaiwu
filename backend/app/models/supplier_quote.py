"""Explicit quote identities and append-only revisions; no inferred historical terms."""
from sqlalchemy import Column,Integer,String,DateTime,ForeignKey,JSON,Index,CheckConstraint,Numeric
from sqlalchemy.sql import func
from app.database import Base

GUARDS={
 'uq_supplier_quote_code':('supplier_quotes',['warehouse_id','code']),
 'uq_supplier_quote_revision':('supplier_quote_revisions',['quote_id','revision']),
 'uq_supplier_quote_request':('supplier_quote_revisions',['warehouse_id','request_key']),
 'uq_supplier_quote_tier':('supplier_quote_tiers',['revision_id','min_quantity']),
}

class SupplierQuote(Base):
 __tablename__='supplier_quotes'
 __table_args__=(Index('uq_supplier_quote_code','warehouse_id','code',unique=True),CheckConstraint('current_revision > 0',name='ck_supplier_quote_current'))
 id=Column(Integer,primary_key=True)
 warehouse_id=Column(Integer,ForeignKey('warehouses.id'),nullable=False,index=True)
 product_id=Column(Integer,ForeignKey('supplier_products.id'),nullable=False,index=True)
 code=Column(String(64),nullable=False)
 current_revision=Column(Integer,nullable=False,default=1)
 created_at=Column(DateTime(timezone=True),server_default=func.now())

class SupplierQuoteRevision(Base):
 __tablename__='supplier_quote_revisions'
 __table_args__=(Index('uq_supplier_quote_revision','quote_id','revision',unique=True),Index('uq_supplier_quote_request','warehouse_id','request_key',unique=True),CheckConstraint('revision > 0',name='ck_supplier_quote_revision'))
 id=Column(Integer,primary_key=True)
 warehouse_id=Column(Integer,ForeignKey('warehouses.id'),nullable=False,index=True)
 quote_id=Column(Integer,ForeignKey('supplier_quotes.id'),nullable=False,index=True)
 revision=Column(Integer,nullable=False)
 request_key=Column(String(100),nullable=False)
 request_fingerprint=Column(String(64),nullable=False)
 content_fingerprint=Column(String(64),nullable=False)
 terms=Column(JSON,nullable=False)
 product_binding=Column(JSON,nullable=False)
 operator_id=Column(Integer,ForeignKey('users.id'),nullable=False)
 operator_name=Column(String(100),nullable=False)
 created_at=Column(DateTime(timezone=True),server_default=func.now())

class SupplierQuoteTier(Base):
 __tablename__='supplier_quote_tiers'
 __table_args__=(Index('uq_supplier_quote_tier','revision_id','min_quantity',unique=True),
  CheckConstraint('min_quantity > 0',name='ck_quote_tier_min'),CheckConstraint('max_quantity IS NULL OR max_quantity > min_quantity',name='ck_quote_tier_max'),CheckConstraint('unit_price > 0',name='ck_quote_tier_price'))
 id=Column(Integer,primary_key=True)
 revision_id=Column(Integer,ForeignKey('supplier_quote_revisions.id'),nullable=False,index=True)
 min_quantity=Column(Numeric(20,8),nullable=False)
 max_quantity=Column(Numeric(20,8),nullable=True)
 unit_price=Column(Numeric(20,8),nullable=False)

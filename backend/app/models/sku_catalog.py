"""Warehouse-owned standard catalog. Names and free text never identify a SKU."""
from sqlalchemy import Column,Integer,String,Boolean,JSON,DateTime,ForeignKey,Index
from sqlalchemy.sql import func
from app.database import Base

GUARDS={
    'uq_standard_sku_code':('standard_skus',['warehouse_id','code']),
    'uq_supplier_tag_name':('supplier_warehouse_tags',['warehouse_id','name']),
    'uq_supplier_tag_link':('supplier_tag_links',['warehouse_id','supplier_id','tag_id']),
    'uq_sku_mapping_request':('product_sku_mapping_events',['warehouse_id','request_key']),
    'uq_product_import_request':('product_import_operations',['warehouse_id','request_key']),
}

class StandardSKU(Base):
    __tablename__='standard_skus'
    __table_args__=(Index('uq_standard_sku_code','warehouse_id','code',unique=True),)
    id=Column(Integer,primary_key=True)
    warehouse_id=Column(Integer,ForeignKey('warehouses.id'),nullable=False,index=True)
    code=Column(String(64),nullable=False)
    name=Column(String(200),nullable=False)
    attributes=Column(JSON,nullable=False)
    base_unit=Column(String(20),nullable=False)
    category_id=Column(Integer,ForeignKey('supplier_categories.id'),nullable=True)
    active=Column(Boolean,nullable=False,default=True)
    revision=Column(Integer,nullable=False,default=1)
    created_by=Column(Integer,ForeignKey('users.id'),nullable=False)
    created_at=Column(DateTime(timezone=True),server_default=func.now())

class SupplierWarehouseTag(Base):
    __tablename__='supplier_warehouse_tags'
    __table_args__=(Index('uq_supplier_tag_name','warehouse_id','name',unique=True),)
    id=Column(Integer,primary_key=True)
    warehouse_id=Column(Integer,ForeignKey('warehouses.id'),nullable=False,index=True)
    name=Column(String(50),nullable=False)
    active=Column(Boolean,nullable=False,default=True)
    revision=Column(Integer,nullable=False,default=1)

class SupplierTagLink(Base):
    __tablename__='supplier_tag_links'
    __table_args__=(Index('uq_supplier_tag_link','warehouse_id','supplier_id','tag_id',unique=True),)
    id=Column(Integer,primary_key=True)
    warehouse_id=Column(Integer,ForeignKey('warehouses.id'),nullable=False,index=True)
    supplier_id=Column(Integer,ForeignKey('suppliers.id'),nullable=False,index=True)
    tag_id=Column(Integer,ForeignKey('supplier_warehouse_tags.id'),nullable=False)

class ProductSkuMappingEvent(Base):
    __tablename__='product_sku_mapping_events'
    __table_args__=(Index('uq_sku_mapping_request','warehouse_id','request_key',unique=True),)
    id=Column(Integer,primary_key=True)
    warehouse_id=Column(Integer,ForeignKey('warehouses.id'),nullable=False,index=True)
    product_id=Column(Integer,ForeignKey('supplier_products.id'),nullable=False,index=True)
    request_key=Column(String(100),nullable=False)
    request_fingerprint=Column(String(64),nullable=False)
    before=Column(JSON,nullable=True)
    after=Column(JSON,nullable=False)
    reason=Column(String(1000),nullable=False)
    operator_id=Column(Integer,ForeignKey('users.id'),nullable=False)
    operator_name=Column(String(100),nullable=False)
    created_at=Column(DateTime(timezone=True),server_default=func.now())

class ProductImportOperation(Base):
    __tablename__='product_import_operations'
    __table_args__=(Index('uq_product_import_request','warehouse_id','request_key',unique=True),)
    id=Column(Integer,primary_key=True)
    warehouse_id=Column(Integer,ForeignKey('warehouses.id'),nullable=False,index=True)
    request_key=Column(String(100),nullable=False)
    request_fingerprint=Column(String(64),nullable=False)
    result=Column(JSON,nullable=False)
    operator_id=Column(Integer,ForeignKey('users.id'),nullable=False)
    created_at=Column(DateTime(timezone=True),server_default=func.now())

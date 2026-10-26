"""Empty catalog and nullable historical references; never infer old SKU mappings."""
from sqlalchemy import inspect,text
from fastapi import HTTPException
from app.models.sku_catalog import StandardSKU,SupplierWarehouseTag,SupplierTagLink,ProductSkuMappingEvent,ProductImportOperation,GUARDS
from app.core.payable_constraints import canonical_predicate

COLUMNS={
 'supplier_products':{'standard_sku_id':'INTEGER REFERENCES standard_skus(id)','catalog_attributes':'JSON','base_unit_factor':'NUMERIC(20,8)',
  'sku_snapshot':'JSON','catalog_revision':'INTEGER','catalog_active':'BOOLEAN'},
 'procurement_price_history':{'currency':'VARCHAR(10)','unit':'VARCHAR(20)','sku_snapshot':'JSON'},
}
MODELS=(StandardSKU,SupplierWarehouseTag,SupplierTagLink,ProductSkuMappingEvent,ProductImportOperation)

async def ensure_catalog_guards(conn):
 def check(c):
  i=inspect(c);missing=[]
  for name,(table,cols) in GUARDS.items():
   indexes={v['name']:v for v in i.get_indexes(table)} if i.has_table(table) else {}
   v=indexes.get(name,{})
   options=v.get('dialect_options',{})
   predicate=options.get('postgresql_where',options.get('sqlite_where',''))
   if not v.get('unique') or v.get('column_names')!=cols or canonical_predicate(predicate):missing.append(name)
  for table,cols in COLUMNS.items():
   existing={v['name'] for v in i.get_columns(table)} if i.has_table(table) else set()
   missing.extend(table+'.'+col for col in cols if col not in existing)
  for model in MODELS:
   table=model.__table__
   if not i.has_table(table.name):continue
   existing={v['name'] for v in i.get_columns(table.name)}
   missing.extend(table.name+'.'+col.name for col in table.columns if col.name not in existing)
   actual=i.get_foreign_keys(table.name)
   for fk in table.foreign_keys:
    if not any(v['constrained_columns']==[fk.parent.name] and v['referred_table']==fk.column.table.name and v['referred_columns']==[fk.column.name] for v in actual):
     missing.append(table.name+'.'+fk.parent.name+'_foreign_key')
  if i.has_table('supplier_products'):
   fks=i.get_foreign_keys('supplier_products')
   if not any(v['constrained_columns']==['standard_sku_id'] and v['referred_table']=='standard_skus' and v['referred_columns']==['id'] for v in fks):missing.append('supplier_products.standard_sku_id_foreign_key')
  return missing
 missing=await conn.run_sync(check)
 if conn.dialect.name=='postgresql':
  valid=set((await conn.execute(text('SELECT c.relname FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=current_schema() AND i.indisvalid AND i.indisready'))).scalars())
  missing=sorted(set(missing)|(set(GUARDS)-valid))
 if missing:raise HTTPException(503,{'code':'sku_catalog_guards_missing','message':'标准SKU结构或唯一约束未就绪，已停止写入，请管理员核对迁移','missing':missing})

async def migrate_sku_catalog(conn):
 for model in MODELS:
  async with conn.begin_nested():await conn.run_sync(lambda c,m=model:m.__table__.create(c,checkfirst=True))
 for table,cols in COLUMNS.items():
  for col,kind in cols.items():
   async with conn.begin_nested():await conn.execute(text(f'ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} {kind}'))
 await ensure_catalog_guards(conn)
 print('标准SKU迁移 READY：空目录及映射事件、可空历史列；未猜配旧产品或改写旧报价')

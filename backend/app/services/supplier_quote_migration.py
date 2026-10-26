"""Empty, versioned quotes and nullable price evidence; historical prices stay unknown."""
import re
from sqlalchemy import inspect,text,CheckConstraint
from fastapi import HTTPException
from app.models.supplier_quote import SupplierQuote,SupplierQuoteRevision,SupplierQuoteTier,GUARDS
from app.core.payable_constraints import canonical_predicate

MODELS=(SupplierQuote,SupplierQuoteRevision,SupplierQuoteTier)
def check_text(value):
 return re.sub(r'::(?:numeric|integer)','',canonical_predicate(value))

async def ensure_quote_guards(conn):
 def check(c):
  i=inspect(c);missing=[]
  for name,(table,cols) in GUARDS.items():
   row=next((v for v in i.get_indexes(table) if v['name']==name),{}) if i.has_table(table) else {}
   if not row.get('unique') or row.get('column_names')!=cols or canonical_predicate(row.get('dialect_options',{}).get('postgresql_where','')):missing.append(name)
  for model in MODELS:
   table=model.__table__
   if not i.has_table(table.name):missing.append(table.name);continue
   cols={v['name'] for v in i.get_columns(table.name)}
   missing.extend(table.name+'.'+v.name for v in table.columns if v.name not in cols)
   actual=i.get_foreign_keys(table.name)
   for fk in table.foreign_keys:
    if not any(v['constrained_columns']==[fk.parent.name] and v['referred_table']==fk.column.table.name and v['referred_columns']==[fk.column.name] for v in actual):missing.append(table.name+'.'+fk.parent.name+'_fk')
   checks={v['name']:v['sqltext'] for v in i.get_check_constraints(table.name)}
   for constraint in table.constraints:
    if isinstance(constraint,CheckConstraint) and check_text(checks.get(constraint.name,''))!=check_text(str(constraint.sqltext)):missing.append(constraint.name)
  if not i.has_table('procurement_price_history') or 'pricing_snapshot' not in {v['name'] for v in i.get_columns('procurement_price_history')}:missing.append('procurement_price_history.pricing_snapshot')
  return missing
 missing=await conn.run_sync(check)
 if conn.dialect.name=='postgresql':
  valid=set((await conn.execute(text('SELECT c.relname FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=current_schema() AND i.indisvalid AND i.indisready'))).scalars())
  missing=sorted(set(missing)|(set(GUARDS)-valid))
 if missing:raise HTTPException(503,{'code':'supplier_quote_guards_missing','message':'报价结构或约束未就绪，已停止写入，请核对迁移','missing':missing})

async def migrate_supplier_quotes(conn):
 for model in MODELS:
  async with conn.begin_nested():await conn.run_sync(lambda c,m=model:m.__table__.create(c,checkfirst=True))
 async with conn.begin_nested():await conn.execute(text('ALTER TABLE procurement_price_history ADD COLUMN IF NOT EXISTS pricing_snapshot JSON'))
 await ensure_quote_guards(conn)
 print('数量阶梯报价迁移 READY：新增空报价版本及可空证据列，未推断或修改旧报价')

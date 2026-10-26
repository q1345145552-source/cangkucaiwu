"""Explicit-connection, read-only historical suggestions; never create mappings."""
import argparse,asyncio,json,os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sqlalchemy import inspect,text
from sqlalchemy.ext.asyncio import create_async_engine

async def audit(engine,warehouse_id):
 async with engine.connect() as conn:
  transaction=await conn.begin()
  try:
   if conn.dialect.name!='postgresql':raise RuntimeError('This read-only audit requires PostgreSQL')
   await conn.execute(text('SET TRANSACTION READ ONLY'))
   columns=await conn.run_sync(lambda c:{v['name'] for v in inspect(c).get_columns('supplier_products')})
   has_skus=await conn.run_sync(lambda c:inspect(c).has_table('standard_skus'))
   attrs='p.catalog_attributes' if 'catalog_attributes' in columns else 'NULL'
   mapped='p.standard_sku_id' if 'standard_sku_id' in columns else 'NULL'
   rows=(await conn.execute(text(f'SELECT p.id,p.product_name,p.spec,p.unit,{attrs} catalog_attributes,{mapped} standard_sku_id FROM supplier_products p JOIN suppliers s ON s.id=p.supplier_id WHERE s.warehouse_id=:wid ORDER BY p.id'),{'wid':warehouse_id})).mappings().all()
   skus=(await conn.execute(text('SELECT id,code,name,attributes,base_unit FROM standard_skus WHERE warehouse_id=:wid AND active=true ORDER BY id'),{'wid':warehouse_id})).mappings().all() if has_skus else []
   result=[]
   for row in rows:
    if row['standard_sku_id'] is not None:continue
    candidates=[]
    for sku in skus:
     exact=bool(row['catalog_attributes']) and row['catalog_attributes']==sku['attributes']
     same_name=row['product_name']==sku['name']
     if exact or same_name:candidates.append({'id':sku['id'],'code':sku['code'],'matched_fields':(['结构规格'] if exact else [])+(['显示名称'] if same_name else []),'auto_mapped':False})
    result.append({**dict(row),'candidates':candidates,'status':'待人工核对','unit_conversion':None,'note':'没有结构规格不能仅凭名称合并；单位换算未知不补零'})
   return {'warehouse_id':warehouse_id,'read_only':True,'catalog_table_present':has_skus,'unmapped_products':len(result),'data':result}
  finally:await transaction.rollback()

async def main():
 parser=argparse.ArgumentParser();parser.add_argument('--warehouse-id',type=int,required=True);args=parser.parse_args()
 url=os.environ.get('SKU_CATALOG_AUDIT_DATABASE_URL')
 if not url:raise SystemExit('Set explicit SKU_CATALOG_AUDIT_DATABASE_URL; no default or production fallback')
 if args.warehouse_id<=0:raise SystemExit('warehouse-id must be positive')
 engine=create_async_engine(url)
 try:print(json.dumps(await audit(engine,args.warehouse_id),ensure_ascii=False,default=str,indent=2))
 finally:await engine.dispose()
if __name__=='__main__':asyncio.run(main())

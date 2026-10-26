"""Run all supplier startup migrations together from a synthetic pre-batch schema."""
import asyncio,copy,json,os
from pathlib import Path
import pytest
from sqlalchemy import select,func,text
from sqlalchemy.sql.ddl import sort_tables
from app.database import Base
from app.models import User,PurchaseOrder,PayableBill,SystemSetting
from app.models.cost_identity import CostIdentity
from app.models.purchase_receipt import PurchaseReceiptEvent
from app.services.payable_dedup_migration import migrate_payable_dedup
from app.services.purchase_receipt_migration import migrate_purchase_receipts
from app.services.cost_identity_migration import migrate_cost_identities
from app.services.sku_catalog_migration import MODELS as CATALOG,COLUMNS as CATALOG_COLUMNS,migrate_sku_catalog
from app.services.supplier_quote_migration import MODELS as QUOTES,migrate_supplier_quotes
from app.services.procurement_control_migration import MODELS as DUTY,migrate_procurement_controls
from app.services.inventory_migration import MODELS as STOCK,migrate_inventory
from tests.test_supplier_workflow_round1 import setup
from tests.test_incoming_operations import environment,URL
pytestmark=pytest.mark.skipif(not URL,reason='Own disposable loopback PostgreSQL only')
MODELS=(CostIdentity,PurchaseReceiptEvent,*CATALOG,*QUOTES,*DUTY,*STOCK)
COLUMNS={
 'payable_bills':['invoice_identity','invoice_identity_key','create_request_key','create_request_fingerprint','duplicate_confirmation','matching_kind','match_lines','match_review','cost_identity_id'],
 'purchase_orders':['request_key','request_fingerprint','receipt_baseline'],
 'expense_approvals':['cost_identity_id'],'expense_fund_items':['cost_identity_id'],'expense_records':['cost_identity_id'],
 'supplier_products':list(CATALOG_COLUMNS['supplier_products']),
 'procurement_price_history':[*CATALOG_COLUMNS['procurement_price_history'],'pricing_snapshot'],
}
MIGRATIONS=(migrate_payable_dedup,migrate_purchase_receipts,migrate_cost_identities,migrate_sku_catalog,migrate_supplier_quotes,migrate_procurement_controls,migrate_inventory)
async def snapshot(conn):
 out={}
 new={m.__tablename__ for m in MODELS}
 for table in sorted(Base.metadata.tables.values(),key=lambda t:t.name):
  if table.name in new:continue
  rows=(await conn.execute(text(f'SELECT to_jsonb(t) AS value FROM "{table.name}" t'))).scalars().all()
  excluded=set(COLUMNS.get(table.name,[]))
  out[table.name]=sorted([{k:v for k,v in row.items()if k not in excluded}for row in rows],key=lambda r:json.dumps(r,sort_keys=True,default=str))
 return out
async def strip_new_schema(conn):
 for table,columns in COLUMNS.items():
  for col in columns:await conn.execute(text(f'ALTER TABLE "{table}" DROP COLUMN IF EXISTS "{col}"'))
 new={m.__tablename__ for m in MODELS}
 for table in reversed(sort_tables([m.__table__ for m in MODELS])):
  if table.name in new:await conn.run_sync(lambda c,t=table:t.drop(c,checkfirst=True))
async def verify(conn):
 for model in MODELS:assert(await conn.execute(select(func.count()).select_from(model))).scalar_one()==0,model.__tablename__
 for table,columns in COLUMNS.items():
  condition=' OR '.join(f'"{col}" IS NOT NULL'for col in columns)
  assert(await conn.execute(text(f'SELECT count(*) FROM "{table}" WHERE {condition}'))).scalar_one()==0,table
async def run_case(manager,tmp,mp,label):
 async with manager(tmp,mp)as(engine,f,c):
  async with engine.begin()as conn:
   before=await snapshot(conn);await strip_new_schema(conn)
   assert await snapshot(conn)==before
   runs=[]
   for iteration in(1,2):
    for migration in MIGRATIONS:
     result=await migration(conn)
     if migration==migrate_payable_dedup:assert result['ready'] and not result['blocked_indexes']
    assert await snapshot(conn)==before
    await verify(conn);runs.append({'iteration':iteration,'migrations':len(MIGRATIONS),'existing_data_unchanged':True,'new_tables_empty':len(MODELS)})
   try:
    async with conn.begin_nested():await conn.execute(text('SELECT 1/0'))
   except Exception:pass
   assert(await conn.execute(text('SELECT 1'))).scalar_one()==1
   value={'case':label,'runs':runs,'legacy_counts':{k:len(v)for k,v in before.items()if v},'savepoint_outer_transaction_survives':True}
   p=os.environ.get('SUPPLIER12_MIGRATION_REPORT')
   if p:
    file=Path(p);data=json.loads(file.read_text())if file.exists()else{};data[label]=value;file.write_text(json.dumps(data,ensure_ascii=False,indent=2))

def test_all_supplier_migrations_new_base_repeat_no_history_invention(tmp_path,monkeypatch):asyncio.run(run_case(environment,tmp_path,monkeypatch,'new_base'))
def test_all_supplier_migrations_existing_legacy_order_bill_grants_repeat_unchanged(tmp_path,monkeypatch):asyncio.run(run_case(setup,tmp_path,monkeypatch,'legacy_order_bill'))

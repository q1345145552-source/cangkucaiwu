"""Execute startup DDL/backfill on isolated embedded PostgreSQL, never production."""
import asyncio, os
from pathlib import Path
from types import SimpleNamespace
import pytest
from scripts.seed import _migrate_payroll_expense_link
from app.services.payroll_expense import backfill_payroll_categories
from tests.test_round12_migration_postgres import PostgreSQLConnection

pytestmark=pytest.mark.skipif(not os.environ.get('PGLITE_NODE'),reason='Set PGLITE_NODE and NODE_PATH for embedded PostgreSQL')

@pytest.mark.parametrize('fail',[None,'expense_record_id','expense_record_index'])
def test_old_schema_idempotence_savepoints_and_no_historical_expenses(fail):
 async def run():
  process=await asyncio.create_subprocess_exec(os.environ['PGLITE_NODE'],str(Path(__file__).with_name('postgres_bridge.cjs')),stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE)
  class Connection(PostgreSQLConnection):
   async def execute(self,statement,params=None):
    sql=str(statement)
    if self.fail_column and ((self.fail_column=='expense_record_id' and sql.startswith('ALTER TABLE payroll_records')) or (self.fail_column=='expense_record_index' and sql.startswith('CREATE UNIQUE INDEX'))):
     return await super().execute('ALTER TABLE deliberately_missing_table ADD COLUMN fail INTEGER')
    if params:
     sql=str(statement.bindparams(**params).compile(compile_kwargs={'literal_binds':True}))
    result=await super().execute(sql)
    return SimpleNamespace(rowcount=-1) if params else result
  conn=Connection(process)
  try:
   for sql in [
    'CREATE TABLE warehouses(id INTEGER PRIMARY KEY)',
    'INSERT INTO warehouses VALUES(1),(2)',
    'CREATE TABLE income_expense_categories(id SERIAL PRIMARY KEY,warehouse_id INTEGER REFERENCES warehouses(id),type TEXT,name TEXT,category_group TEXT,status TEXT,sort_order INTEGER)',
    "INSERT INTO income_expense_categories(warehouse_id,type,name,category_group,status) VALUES(1,'expense','员工工资','operating','active')",
    'CREATE TABLE expense_records(id INTEGER PRIMARY KEY,amount DOUBLE PRECISION)',
    'CREATE TABLE payroll_records(id INTEGER PRIMARY KEY,disbursed BOOLEAN,net_pay DOUBLE PRECISION)',
    'INSERT INTO payroll_records VALUES(1,true,1234.56),(2,false,99.99)',
   ]:await conn.execute(sql)
   original=await conn.execute('SELECT * FROM payroll_records ORDER BY id')
   await conn.execute('BEGIN');await conn.execute('CREATE TABLE earlier_migration_kept(id INTEGER)')
   conn.fail_column=fail
   await _migrate_payroll_expense_link(conn)
   assert conn.savepoints==2
   await conn.execute('SELECT * FROM earlier_migration_kept')
   conn.fail_column=None
   await _migrate_payroll_expense_link(conn)
   await _migrate_payroll_expense_link(conn)
   await backfill_payroll_categories(conn);await backfill_payroll_categories(conn)
   await conn.execute('COMMIT')
   rows=await conn.execute('SELECT * FROM payroll_records ORDER BY id')
   assert [{k:r[k] for k in original[0]} for r in rows]==original
   assert all(r['expense_record_id'] is None for r in rows)
   assert await conn.execute('SELECT * FROM expense_records')==[]
   categories=await conn.execute("SELECT warehouse_id,name,category_group,count(*) AS count FROM income_expense_categories GROUP BY warehouse_id,name,category_group ORDER BY warehouse_id")
   assert categories==[{'warehouse_id':i,'name':'员工工资','category_group':'operating','count':1} for i in (1,2)]
   await conn.execute('INSERT INTO expense_records VALUES(1,99.99)')
   await conn.execute('UPDATE payroll_records SET expense_record_id=1 WHERE id=2')
   await conn.execute('BEGIN');await _migrate_payroll_expense_link(conn);await backfill_payroll_categories(conn);await conn.execute('COMMIT')
   assert (await conn.execute('SELECT expense_record_id FROM payroll_records WHERE id=2'))[0]['expense_record_id']==1
   for expense_id in (999,1):
    with pytest.raises(RuntimeError):
     async with conn.begin_nested():
      await conn.execute(f'UPDATE payroll_records SET expense_record_id={expense_id} WHERE id=1')
   assert (await conn.execute('SELECT expense_record_id FROM payroll_records WHERE id=1'))[0]['expense_record_id'] is None
   print('PAYROLL_EXPENSE_PG',{'columns':rows,'categories':categories})
  finally:
   process.stdin.close();await process.wait()
 asyncio.run(run())

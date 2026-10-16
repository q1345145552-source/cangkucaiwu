"""Actual PostgreSQL DDL/backfill, repeated startup and per-column savepoint recovery."""
import asyncio,os,json
from pathlib import Path
import pytest
from scripts.seed import _migrate_advance_approval_columns
from tests.test_round12_migration_postgres import PostgreSQLConnection

pytestmark=pytest.mark.skipif(not os.environ.get('PGLITE_NODE'),reason='Set PGLITE_NODE and NODE_PATH for embedded PostgreSQL')
FIELDS=('approval_status','reviewer_id','reviewed_at','reject_reason')

@pytest.mark.parametrize('partial',[False,True])
@pytest.mark.parametrize('fail_column',[None,*FIELDS])
def test_actual_legacy_migration_and_idempotence(partial,fail_column):
 async def run():
  process=await asyncio.create_subprocess_exec(os.environ['PGLITE_NODE'],str(Path(__file__).with_name('postgres_bridge.cjs')),stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE)
  class Connection(PostgreSQLConnection):
   async def execute(self,statement):
    sql=str(statement)
    if fail_column and self.fail_column and sql.startswith('ALTER TABLE employee_advances ADD COLUMN') and f' {fail_column} ' in sql:
     return await super().execute('ALTER TABLE deliberately_missing_table ADD COLUMN fail INTEGER')
    return await super().execute(statement)
  conn=Connection(process)
  try:
   await conn.execute('CREATE TABLE users(id INTEGER PRIMARY KEY)')
   await conn.execute('INSERT INTO users VALUES(1)')
   await conn.execute('CREATE TABLE employee_advances(id INTEGER PRIMARY KEY, amount DOUBLE PRECISION, deducted_amount DOUBLE PRECISION, status TEXT)')
   await conn.execute("INSERT INTO employee_advances VALUES(1,100,0,'unpaid'),(2,200,50,'partial'),(3,300,300,'deducted')")
   if partial:await conn.execute('ALTER TABLE employee_advances ADD COLUMN approval_status VARCHAR(20)')
   before=await conn.execute('SELECT id,amount,deducted_amount,status FROM employee_advances ORDER BY id')
   await conn.execute('BEGIN')
   await conn.execute('CREATE TABLE prior_migration_survives(id INTEGER)')
   conn.fail_column=bool(fail_column)
   await _migrate_advance_approval_columns(conn)
   columns={r['column_name'] for r in await conn.execute("SELECT column_name FROM information_schema.columns WHERE table_name='employee_advances'")}
   expected=set(FIELDS)-({fail_column} if fail_column else set())
   if partial:expected.add('approval_status')
   assert expected<=columns
   assert conn.savepoints==5
   await conn.execute('SELECT * FROM prior_migration_survives')
   conn.fail_column=None
   await _migrate_advance_approval_columns(conn)
   await _migrate_advance_approval_columns(conn)
   await conn.execute('COMMIT')
   rows=await conn.execute('SELECT * FROM employee_advances ORDER BY id')
   assert len(rows)==len(before)==3
   for row,original in zip(rows,before):
    assert {k:row[k] for k in original}==original
    assert row['approval_status']=='approved'
    assert all(row[k] is None for k in FIELDS[1:])
   await conn.execute("UPDATE employee_advances SET approval_status='pending' WHERE id=1")
   await conn.execute("UPDATE employee_advances SET approval_status='rejected',reviewer_id=1,reviewed_at='2026-10-16 12:00+07',reject_reason='中文原因' WHERE id=2")
   new_state=await conn.execute('SELECT * FROM employee_advances ORDER BY id')
   await conn.execute('BEGIN')
   await _migrate_advance_approval_columns(conn)
   await conn.execute('COMMIT')
   assert await conn.execute('SELECT * FROM employee_advances ORDER BY id')==new_state
   if not partial:
    await conn.execute("INSERT INTO employee_advances(id,amount,status) VALUES(4,25,'unpaid')")
    assert (await conn.execute('SELECT approval_status FROM employee_advances WHERE id=4'))[0]['approval_status']=='approved'
   if not fail_column and not partial:print('ROUND17_POSTGRES_OLD_ROWS',json.dumps(rows,ensure_ascii=False))
  finally:
   process.stdin.close();await process.wait()
 asyncio.run(run())

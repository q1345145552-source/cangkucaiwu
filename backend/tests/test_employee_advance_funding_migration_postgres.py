"""资金来源可空迁移：真实PostgreSQL，幂等、局部失败恢复与老值保护。"""
import asyncio
import os
from pathlib import Path
import pytest
from scripts.seed import _migrate_employee_advance_funding
from tests.test_round12_migration_postgres import PostgreSQLConnection

pytestmark = pytest.mark.skipif(not os.environ.get('PGLITE_NODE'), reason='Requires embedded PostgreSQL')
FIELDS = ('funding_source', 'cash_advance_id', 'payment_account_id')


@pytest.mark.parametrize('partial', [False, True])
@pytest.mark.parametrize('failure', [None, *FIELDS])
def test_nullable_idempotent_savepoint_migration(partial, failure):
    async def run():
        process = await asyncio.create_subprocess_exec(os.environ['PGLITE_NODE'],
            str(Path(__file__).with_name('postgres_bridge.cjs')), stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE)
        conn = PostgreSQLConnection(process)
        try:
            await conn.execute('CREATE TABLE cash_advances(id INTEGER PRIMARY KEY)')
            await conn.execute('CREATE TABLE payment_accounts(id INTEGER PRIMARY KEY)')
            await conn.execute('CREATE TABLE employee_advances(id INTEGER PRIMARY KEY,amount NUMERIC,source TEXT,approval_status TEXT,status TEXT)')
            await conn.execute("INSERT INTO employee_advances VALUES(1,1000,'supervisor','approved','unpaid'),(2,2000,'fund','pending','unpaid'),(3,3000,'fund','rejected','voided')")
            before = await conn.execute('SELECT * FROM employee_advances ORDER BY id')
            if partial:
                await conn.execute('ALTER TABLE employee_advances ADD COLUMN funding_source VARCHAR(20)')
            await conn.execute('BEGIN')
            await conn.execute('CREATE TABLE preceding_migration_kept(id INTEGER)')
            real = conn.execute
            if failure:
                async def broken(statement):
                    return await real('SELECT * FROM deliberately_missing_table' if str(statement).startswith(
                        f'ALTER TABLE employee_advances ADD COLUMN IF NOT EXISTS {failure} ') else statement)
                conn.execute = broken
                with pytest.raises(RuntimeError):
                    await _migrate_employee_advance_funding(conn)
                conn.execute = real
                await conn.execute('SELECT * FROM preceding_migration_kept')
            await _migrate_employee_advance_funding(conn)
            await _migrate_employee_advance_funding(conn)
            await conn.execute('COMMIT')
            assert await conn.execute('SELECT id,amount,source,approval_status,status FROM employee_advances ORDER BY id') == before
            rows = await conn.execute('SELECT funding_source,cash_advance_id,payment_account_id FROM employee_advances')
            assert len(rows) == 3 and all(all(r[k] is None for k in FIELDS) for r in rows)
            await conn.execute("UPDATE employee_advances SET funding_source='company_account' WHERE id=1")
            saved = await conn.execute('SELECT * FROM employee_advances ORDER BY id')
            await conn.execute('BEGIN')
            await _migrate_employee_advance_funding(conn)
            await conn.execute('COMMIT')
            assert await conn.execute('SELECT * FROM employee_advances ORDER BY id') == saved
        finally:
            process.stdin.close()
            await process.wait()
    asyncio.run(run())

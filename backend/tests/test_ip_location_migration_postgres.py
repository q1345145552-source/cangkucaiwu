"""Real PostgreSQL: nullable columns, repeat startup and independent savepoints."""
import asyncio
import os
from pathlib import Path

import pytest

from scripts.seed import _migrate_audit_ip_location
from tests.test_round12_migration_postgres import PostgreSQLConnection

pytestmark = pytest.mark.skipif(not os.environ.get('PGLITE_NODE'), reason='Requires embedded PostgreSQL')
FIELDS = ('ip_country', 'ip_region', 'ip_city')


@pytest.mark.parametrize('failure', [None, *FIELDS])
@pytest.mark.parametrize('partial', [False, True])
def test_old_rows_nullable_idempotent_and_savepoint_failure(failure, partial):
    async def run():
        process = await asyncio.create_subprocess_exec(os.environ['PGLITE_NODE'], str(Path(__file__).with_name('postgres_bridge.cjs')),
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE)
        conn = PostgreSQLConnection(process)
        try:
            await conn.execute('CREATE TABLE audit_logs(id INTEGER PRIMARY KEY,ip_address TEXT,detail JSONB)')
            await conn.execute("INSERT INTO audit_logs VALUES(1,'172.18.0.5','{\"old\":true}')")
            if partial: await conn.execute('ALTER TABLE audit_logs ADD COLUMN ip_region VARCHAR(150)')
            before = await conn.execute('SELECT id,ip_address,detail FROM audit_logs')
            await conn.execute('BEGIN')
            await conn.execute('CREATE TABLE prior_migration_kept(id INTEGER)')
            real = conn.execute
            if failure:
                async def broken(statement):
                    return await real('SELECT * FROM deliberately_missing_table' if str(statement).startswith(
                        f'ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS {failure} ') else statement)
                conn.execute = broken
                with pytest.raises(RuntimeError): await _migrate_audit_ip_location(conn)
                conn.execute = real
                await conn.execute('SELECT * FROM prior_migration_kept')
            await _migrate_audit_ip_location(conn)
            await _migrate_audit_ip_location(conn)
            await conn.execute('COMMIT')
            assert await conn.execute('SELECT id,ip_address,detail FROM audit_logs') == before
            rows = await conn.execute('SELECT ip_country,ip_region,ip_city FROM audit_logs')
            assert rows == [dict.fromkeys(FIELDS)]
            await conn.execute("UPDATE audit_logs SET ip_country='泰国',ip_region='曼谷',ip_city='旺通朗'")
            saved = await conn.execute('SELECT * FROM audit_logs')
            await conn.execute('BEGIN')
            await _migrate_audit_ip_location(conn)
            await conn.execute('COMMIT')
            assert await conn.execute('SELECT * FROM audit_logs') == saved
        finally:
            process.stdin.close()
            await process.wait()
    asyncio.run(run())

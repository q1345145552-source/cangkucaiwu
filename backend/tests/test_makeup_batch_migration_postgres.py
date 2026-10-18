"""在嵌入式 PostgreSQL 验证批次表/关联列幂等DDL和保存点。"""
import asyncio
import os
from pathlib import Path
import pytest
from scripts.seed import _migrate_makeup_batches
from tests.test_round12_migration_postgres import PostgreSQLConnection

pytestmark = pytest.mark.skipif(not os.environ.get("PGLITE_NODE"), reason="Set PGLITE_NODE and NODE_PATH for embedded PostgreSQL")


@pytest.mark.parametrize("failure", [None, "table", "column", "records_index", "history_index"])
def test_table_column_indexes_and_legacy_rows(failure):
    async def run():
        process = await asyncio.create_subprocess_exec(os.environ["PGLITE_NODE"], str(Path(__file__).with_name("postgres_bridge.cjs")), stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE)
        class Connection(PostgreSQLConnection):
            async def execute(self, statement):
                prefixes = {"table": "CREATE TABLE IF NOT EXISTS clock_in_makeup_batches", "column": "ALTER TABLE clock_in_records", "records_index": "CREATE INDEX IF NOT EXISTS ix_clock_in_records", "history_index": "CREATE INDEX IF NOT EXISTS ix_clock_in_makeup_batches"}
                if self.fail_column and str(statement).startswith(prefixes[self.fail_column]):
                    return await super().execute("ALTER TABLE missing_table ADD COLUMN fail INTEGER")
                return await super().execute(statement)
        conn = Connection(process)
        try:
            await conn.execute("CREATE TABLE warehouses(id INTEGER PRIMARY KEY)")
            await conn.execute("CREATE TABLE users(id INTEGER PRIMARY KEY)")
            await conn.execute("INSERT INTO warehouses VALUES(1)")
            await conn.execute("INSERT INTO users VALUES(1)")
            await conn.execute("CREATE TABLE clock_in_records(id INTEGER PRIMARY KEY,user_id INTEGER,warehouse_id INTEGER,clock_date DATE,session INTEGER,is_makeup BOOLEAN,makeup_counts_toward_limit BOOLEAN NOT NULL DEFAULT true)")
            await conn.execute("INSERT INTO clock_in_records VALUES(1,1,1,'2026-10-16',1,true,true),(2,1,1,'2026-10-17',1,true,false)")
            await conn.execute("CREATE TABLE payroll_records(id INTEGER PRIMARY KEY,net_pay DOUBLE PRECISION)")
            await conn.execute("INSERT INTO payroll_records VALUES(1,400)")
            old = await conn.execute("SELECT * FROM clock_in_records ORDER BY id")
            await conn.execute("BEGIN")
            await conn.execute("CREATE TABLE previous_migration_kept(id INTEGER)")
            if failure:
                conn.fail_column = failure
                with pytest.raises(RuntimeError): await _migrate_makeup_batches(conn)
                await conn.execute("SELECT * FROM previous_migration_kept")
            conn.fail_column = None
            await _migrate_makeup_batches(conn)
            await _migrate_makeup_batches(conn)
            rows = await conn.execute("SELECT * FROM clock_in_records ORDER BY id")
            assert all(r["makeup_batch_id"] is None for r in rows)
            assert [{k: r[k] for k in old[0]} for r in rows] == old
            assert await conn.execute("SELECT * FROM clock_in_makeup_batches") == []
            await conn.execute("INSERT INTO clock_in_makeup_batches(warehouse_id,clock_date,operator_id,operator_name,reason,created_count) VALUES(1,'2026-10-18',1,'管理员','系统故障',1)")
            await conn.execute("INSERT INTO clock_in_records VALUES(3,1,1,'2026-10-18',1,true,false,1)")
            await conn.execute("UPDATE clock_in_makeup_batches SET status='revoked',revoked_by=1,revoked_by_name='管理员',revoked_at=now() WHERE id=1")
            batches = await conn.execute("SELECT * FROM clock_in_makeup_batches")
            await conn.execute("COMMIT")
            await conn.execute("BEGIN")
            await _migrate_makeup_batches(conn)
            await conn.execute("COMMIT")
            assert await conn.execute("SELECT * FROM clock_in_makeup_batches") == batches
            assert await conn.execute("SELECT * FROM payroll_records") == [{"id": 1, "net_pay": 400}]
            linked = await conn.execute("SELECT makeup_batch_id,makeup_counts_toward_limit FROM clock_in_records WHERE id=3")
            assert linked == [{"makeup_batch_id": 1, "makeup_counts_toward_limit": False}]
            indexes = await conn.execute("SELECT indexname FROM pg_indexes WHERE indexname IN ('ix_clock_in_records_makeup_batch_id','ix_clock_in_makeup_batches_warehouse_date')")
            assert len(indexes) == 2
            print("BATCH_SCHEMA", {"legacy_records": rows, "batch": batches[0], "failure_tested": failure})
        finally:
            process.stdin.close()
            await process.wait()
    asyncio.run(run())

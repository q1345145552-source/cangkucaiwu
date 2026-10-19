"""作废三列：真实 PostgreSQL 幂等DDL、逐列保存点和旧数据保护。"""
import asyncio
import os
from pathlib import Path

import pytest

from scripts.seed import _migrate_employee_advance_void_columns
from tests.test_round12_migration_postgres import PostgreSQLConnection

pytestmark = pytest.mark.skipif(not os.environ.get("PGLITE_NODE"), reason="Requires embedded PostgreSQL")
FIELDS = ("voided_by", "voided_at", "void_reason")


@pytest.mark.parametrize("failure", [None, *FIELDS])
@pytest.mark.parametrize("partial", [False, True])
def test_void_migration_is_idempotent_and_preserves_every_old_value(failure, partial):
    async def run():
        process = await asyncio.create_subprocess_exec(os.environ["PGLITE_NODE"],
            str(Path(__file__).with_name("postgres_bridge.cjs")), stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE)
        conn = PostgreSQLConnection(process)
        try:
            await conn.execute("CREATE TABLE users(id INTEGER PRIMARY KEY)")
            await conn.execute("INSERT INTO users VALUES(1)")
            await conn.execute("CREATE TABLE employee_advances(id INTEGER PRIMARY KEY,amount NUMERIC,status TEXT,approval_status TEXT)")
            await conn.execute("INSERT INTO employee_advances VALUES(1,1000,'unpaid','approved'),(2,2000,'partial','approved'),(3,3000,'unpaid','pending'),(4,4000,'unpaid','rejected')")
            if partial:
                await conn.execute("ALTER TABLE employee_advances ADD COLUMN void_reason VARCHAR(500)")
            before = await conn.execute("SELECT id,amount,status,approval_status FROM employee_advances ORDER BY id")
            await conn.execute("BEGIN")
            await conn.execute("CREATE TABLE earlier_migration_kept(id INTEGER)")
            real = conn.execute
            if failure:
                async def broken(statement):
                    return await real("SELECT * FROM deliberately_missing_table" if str(statement).startswith(
                        f"ALTER TABLE employee_advances ADD COLUMN IF NOT EXISTS {failure} ") else statement)
                conn.execute = broken
                with pytest.raises(RuntimeError):
                    await _migrate_employee_advance_void_columns(conn)
                conn.execute = real
                await conn.execute("SELECT * FROM earlier_migration_kept")
            await _migrate_employee_advance_void_columns(conn)
            await _migrate_employee_advance_void_columns(conn)
            await conn.execute("COMMIT")
            assert await conn.execute("SELECT id,amount,status,approval_status FROM employee_advances ORDER BY id") == before
            rows = await conn.execute("SELECT voided_by,voided_at,void_reason FROM employee_advances")
            assert len(rows) == 4 and all(all(row[key] is None for key in FIELDS) for row in rows)
            await conn.execute("UPDATE employee_advances SET status='voided',voided_by=1,voided_at='2026-10-19 12:00:00+07',void_reason='保留原因' WHERE id=1")
            saved = await conn.execute("SELECT * FROM employee_advances ORDER BY id")
            await conn.execute("BEGIN")
            await _migrate_employee_advance_void_columns(conn)
            await conn.execute("COMMIT")
            assert await conn.execute("SELECT * FROM employee_advances ORDER BY id") == saved
            print("ADVANCE_VOID_MIGRATION", {"columns": FIELDS, "old_rows": 4, "old_null_metadata": True,
                "idempotent": True, "failure": failure, "savepoints": conn.savepoints})
        finally:
            process.stdin.close()
            await process.wait()
    asyncio.run(run())

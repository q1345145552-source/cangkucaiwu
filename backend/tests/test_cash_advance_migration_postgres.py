"""启动建表语句在真实 PostgreSQL 引擎上重复执行和保存点回滚。"""
import asyncio
import os
from pathlib import Path
import pytest
from scripts.seed import _migrate_cash_advances
from tests.test_round12_migration_postgres import PostgreSQLConnection

pytestmark = pytest.mark.skipif(not os.environ.get("PGLITE_NODE"), reason="Requires embedded PostgreSQL")


@pytest.mark.parametrize("fail", [False, True])
def test_cash_advance_ddl_idempotency_data_and_savepoint(fail):
    async def run():
        proc = await asyncio.create_subprocess_exec(os.environ["PGLITE_NODE"], str(Path(__file__).with_name("postgres_bridge.cjs")), stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE)
        conn = PostgreSQLConnection(proc)
        try:
            await conn.execute("CREATE TABLE warehouses(id INTEGER PRIMARY KEY)")
            await conn.execute("CREATE TABLE users(id INTEGER PRIMARY KEY, display_name TEXT)")
            await conn.execute("INSERT INTO warehouses VALUES(1)")
            await conn.execute("INSERT INTO users VALUES(1,'老板'),(2,'主管')")
            await conn.execute("CREATE TABLE payroll_records(id INTEGER PRIMARY KEY,net_pay NUMERIC(14,2))")
            await conn.execute("INSERT INTO payroll_records VALUES(1,6046)")
            await conn.execute("BEGIN")
            await conn.execute("CREATE TABLE previous_migration_kept(id INTEGER)")
            if fail:
                execute = conn.execute
                async def broken(sql):
                    if str(sql).startswith("CREATE TABLE IF NOT EXISTS cash_advances"):
                        return await execute("SELECT * FROM deliberately_missing_table")
                    return await execute(sql)
                conn.execute = broken
                with pytest.raises(RuntimeError): await _migrate_cash_advances(conn)
                conn.execute = execute
                await conn.execute("SELECT * FROM previous_migration_kept")
            await _migrate_cash_advances(conn)
            await _migrate_cash_advances(conn)
            assert await conn.execute("SELECT * FROM cash_advances") == []
            fields = await conn.execute("SELECT column_name FROM information_schema.columns WHERE table_name='cash_advances'")
            assert len(fields) == 19
            await conn.execute("INSERT INTO cash_advances(warehouse_id,payer_id,payer_name,advance_date,amount,purpose,created_by_id,created_by_name,created_at) VALUES(1,2,'主管','2026-10-18',3000,'salary',2,'主管',now())")
            first = await conn.execute("SELECT * FROM cash_advances")
            assert first[0]["status"] == "pending" and float(first[0]["repaid_amount"]) == 0
            await conn.execute("COMMIT")
            await conn.execute("BEGIN")
            await _migrate_cash_advances(conn)
            assert await conn.execute("SELECT * FROM cash_advances") == first
            assert await conn.execute("SELECT * FROM payroll_records") == [{"id": 1, "net_pay": "6046.00"}]
            await conn.execute("COMMIT")
            print("CASH_ADVANCE_SCHEMA", {"columns": len(fields), "existing_preserved": True, "savepoint_failure_tested": fail})
        finally:
            proc.stdin.close(); await proc.wait()
    asyncio.run(run())

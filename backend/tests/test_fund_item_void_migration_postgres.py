"""真实 PostgreSQL 验证开销作废三列、逐列保存点和不回填旧数据。"""
import asyncio
import os
from pathlib import Path
import pytest
from scripts.seed import _migrate_fund_item_void_columns
from tests.test_round12_migration_postgres import PostgreSQLConnection

pytestmark=pytest.mark.skipif(not os.environ.get("PGLITE_NODE"),reason="Requires embedded PostgreSQL")
FIELDS=("voided_by","voided_at","void_reason")


@pytest.mark.parametrize("failure",[None,*FIELDS])
@pytest.mark.parametrize("partial",[False,True])
def test_new_columns_idempotence_old_values_and_savepoint(failure,partial):
    async def run():
        process=await asyncio.create_subprocess_exec(os.environ["PGLITE_NODE"],str(Path(__file__).with_name("postgres_bridge.cjs")),stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE)
        conn=PostgreSQLConnection(process)
        try:
            for sql in ("CREATE TABLE users(id INTEGER PRIMARY KEY)","INSERT INTO users VALUES(1)",
                "CREATE TABLE expense_fund_items(id INTEGER PRIMARY KEY,amount NUMERIC,category TEXT,receipt TEXT,review_status TEXT)",
                "INSERT INTO expense_fund_items VALUES(1,123,'旧耗材',NULL,'pending'),(2,456,'旧费用','/uploads/old.jpg','approved'),(3,789,'旧交通',NULL,'rejected')"):
                await conn.execute(sql)
            if partial:await conn.execute("ALTER TABLE expense_fund_items ADD COLUMN void_reason VARCHAR(500)")
            before=await conn.execute("SELECT id,amount,category,receipt,review_status FROM expense_fund_items ORDER BY id")
            await conn.execute("BEGIN");await conn.execute("CREATE TABLE previous_kept(id INTEGER)")
            execute=conn.execute
            if failure:
                async def broken(statement):
                    return await execute("SELECT * FROM deliberately_missing_table" if str(statement).startswith(f"ALTER TABLE expense_fund_items ADD COLUMN IF NOT EXISTS {failure} ") else statement)
                conn.execute=broken
                with pytest.raises(RuntimeError):await _migrate_fund_item_void_columns(conn)
                conn.execute=execute;await conn.execute("SELECT * FROM previous_kept")
            await _migrate_fund_item_void_columns(conn);await _migrate_fund_item_void_columns(conn)
            assert await conn.execute("SELECT id,amount,category,receipt,review_status FROM expense_fund_items ORDER BY id")==before
            assert all(all(row[key] is None for key in FIELDS) for row in await conn.execute("SELECT voided_by,voided_at,void_reason FROM expense_fund_items"))
            await conn.execute("UPDATE expense_fund_items SET review_status='voided',voided_by=1,voided_at='2026-10-19 12:00:00+07',void_reason='原样保留' WHERE id=1")
            saved=await conn.execute("SELECT * FROM expense_fund_items ORDER BY id")
            await conn.execute("COMMIT");await conn.execute("BEGIN");await _migrate_fund_item_void_columns(conn)
            assert await conn.execute("SELECT * FROM expense_fund_items ORDER BY id")==saved
            await conn.execute("COMMIT")
        finally:
            process.stdin.close();await process.wait()
    asyncio.run(run())

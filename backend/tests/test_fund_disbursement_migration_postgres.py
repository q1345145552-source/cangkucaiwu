"""真实PostgreSQL验证旧开销口径保留、新记录只记台账及逐语句保存点。"""
import asyncio
import os
from pathlib import Path

import pytest
from scripts.seed import _migrate_fund_disbursements
from tests.test_round12_migration_postgres import PostgreSQLConnection

pytestmark = pytest.mark.skipif(not os.environ.get("PGLITE_NODE"), reason="Requires embedded PostgreSQL")


@pytest.mark.parametrize("failure", [None, "cost_record_only", "legacy_item_basis", "new_item_default", "item_not_null", "disbursements", "expense_unique", "request_unique", "fund_index", "warehouse_date_index"])
def test_migration_idempotent_old_amounts_untouched_and_failure_recovery(failure):
    async def run():
        proc = await asyncio.create_subprocess_exec(os.environ["PGLITE_NODE"], str(Path(__file__).with_name("postgres_bridge.cjs")),
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE)
        conn = PostgreSQLConnection(proc)
        try:
            for sql in (
                "CREATE TABLE warehouses(id INTEGER PRIMARY KEY)", "INSERT INTO warehouses VALUES(1)",
                "CREATE TABLE users(id INTEGER PRIMARY KEY)", "INSERT INTO users VALUES(1)",
                "CREATE TABLE payment_accounts(id INTEGER PRIMARY KEY,opening_balance NUMERIC)", "INSERT INTO payment_accounts VALUES(1,20000)",
                "CREATE TABLE expense_records(id INTEGER PRIMARY KEY,amount NUMERIC)", "INSERT INTO expense_records VALUES(1,400)",
                "CREATE TABLE fund_recharge_requests(id INTEGER PRIMARY KEY)", "INSERT INTO fund_recharge_requests VALUES(1)",
                "CREATE TABLE expense_funds(id INTEGER PRIMARY KEY,amount NUMERIC,remaining_balance NUMERIC)", "INSERT INTO expense_funds VALUES(1,5000,5000)",
                "CREATE TABLE expense_fund_items(id INTEGER PRIMARY KEY,fund_id INTEGER,amount NUMERIC,review_status TEXT)",
                "INSERT INTO expense_fund_items VALUES(1,1,1000,'approved'),(2,1,300,'pending'),(3,1,200,'rejected')",
                "BEGIN", "CREATE TABLE prior_migration_kept(id INTEGER)",
            ): await conn.execute(sql)
            old = await conn.execute("SELECT * FROM expense_fund_items ORDER BY id")
            real = conn.execute
            targets = {
                "cost_record_only": "ALTER TABLE expense_fund_items ADD COLUMN",
                "legacy_item_basis": "UPDATE expense_fund_items",
                "new_item_default": "ALTER TABLE expense_fund_items ALTER COLUMN cost_record_only SET DEFAULT",
                "item_not_null": "ALTER TABLE expense_fund_items ALTER COLUMN cost_record_only SET NOT NULL",
                "disbursements": "CREATE TABLE IF NOT EXISTS expense_fund_disbursements",
                "expense_unique": "CREATE UNIQUE INDEX IF NOT EXISTS ix_expense_fund_disbursements_expense_record_id",
                "request_unique": "CREATE UNIQUE INDEX IF NOT EXISTS ix_expense_fund_disbursements_recharge_request_id",
                "fund_index": "CREATE INDEX IF NOT EXISTS ix_expense_fund_disbursements_fund_id",
                "warehouse_date_index": "CREATE INDEX IF NOT EXISTS ix_fund_disbursements_warehouse_date",
            }
            if failure:
                async def broken(statement):
                    return await real("SELECT * FROM deliberately_missing_table" if str(statement).startswith(targets[failure]) else statement)
                conn.execute = broken
                with pytest.raises(RuntimeError): await _migrate_fund_disbursements(conn)
                conn.execute = real
                await conn.execute("SELECT * FROM prior_migration_kept")
            await _migrate_fund_disbursements(conn)
            await _migrate_fund_disbursements(conn)
            await conn.execute("COMMIT")
            migrated = await conn.execute("SELECT * FROM expense_fund_items ORDER BY id")
            assert [{k: r[k] for k in old[0]} for r in migrated] == old
            assert all(r["cost_record_only"] is False for r in migrated)
            assert await conn.execute("SELECT * FROM payment_accounts") == [{"id": 1, "opening_balance": "20000"}]
            assert await conn.execute("SELECT * FROM expense_records") == [{"id": 1, "amount": "400"}]
            assert await conn.execute("SELECT * FROM expense_funds") == [{"id": 1, "amount": "5000", "remaining_balance": "5000"}]
            assert await conn.execute("SELECT count(*) n FROM expense_fund_disbursements") == [{"n": 0}]
            await conn.execute("INSERT INTO expense_fund_items(id,fund_id,amount,review_status) VALUES(4,1,2000,'approved')")
            assert await conn.execute("SELECT cost_record_only FROM expense_fund_items WHERE id=4") == [{"cost_record_only": True}]
            await conn.execute("BEGIN")
            await _migrate_fund_disbursements(conn)
            await conn.execute("COMMIT")
            assert await conn.execute("SELECT cost_record_only FROM expense_fund_items WHERE id=4") == [{"cost_record_only": True}]
            await conn.execute("INSERT INTO expense_fund_disbursements(warehouse_id,fund_id,amount,currency,disbursed_date,payment_account_id,account_name,expense_record_id,recharge_request_id,operator_name) VALUES(1,1,10000,'THB','2026-10-10',1,'现金',1,1,'测试管理员')")
            with pytest.raises(RuntimeError):
                await conn.execute("INSERT INTO expense_fund_disbursements(warehouse_id,fund_id,amount,currency,disbursed_date,payment_account_id,account_name,expense_record_id,recharge_request_id,operator_name) VALUES(1,1,10000,'THB','2026-10-10',1,'现金',1,1,'重复拨付')")
        finally:
            proc.stdin.close()
            await proc.wait()
    asyncio.run(run())

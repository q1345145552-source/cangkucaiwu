"""真实PostgreSQL建表保存点、幂等和历史成本/余额不回填。"""
import asyncio
import os
from pathlib import Path
import pytest
from scripts.seed import _migrate_cash_advance_repayments, _migrate_cash_advance_currency
from tests.test_round12_migration_postgres import PostgreSQLConnection

pytestmark = pytest.mark.skipif(not os.environ.get("PGLITE_NODE"), reason="Requires embedded PostgreSQL")


@pytest.mark.parametrize("fail", [False, True])
def test_repayment_migration_idempotency_and_savepoint(fail):
    async def run():
        proc = await asyncio.create_subprocess_exec(os.environ["PGLITE_NODE"], str(Path(__file__).with_name("postgres_bridge.cjs")), stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE)
        conn = PostgreSQLConnection(proc)
        try:
            await conn.execute("CREATE TABLE warehouses(id INTEGER PRIMARY KEY)")
            await conn.execute("CREATE TABLE users(id INTEGER PRIMARY KEY)")
            await conn.execute("CREATE TABLE payment_accounts(id INTEGER PRIMARY KEY, opening_balance NUMERIC(14,2))")
            await conn.execute("CREATE TABLE cash_advances(id INTEGER PRIMARY KEY, amount NUMERIC(14,2), repaid_amount NUMERIC(14,2), status TEXT)")
            await conn.execute("CREATE TABLE expense_records(id INTEGER PRIMARY KEY,amount NUMERIC(14,2))")
            await conn.execute("INSERT INTO warehouses VALUES(1)")
            await conn.execute("INSERT INTO users VALUES(1)")
            await conn.execute("INSERT INTO payment_accounts VALUES(1,10000)")
            await conn.execute("INSERT INTO cash_advances VALUES(1,3000,0,'confirmed')")
            await conn.execute("INSERT INTO expense_records VALUES(1,750)")
            before = {name: await conn.execute(f"SELECT * FROM {name}") for name in ("payment_accounts", "cash_advances", "expense_records")}
            await conn.execute("BEGIN")
            await conn.execute("CREATE TABLE earlier_migration_kept(id INTEGER)")
            if fail:
                real = conn.execute
                async def broken(sql):
                    if str(sql).startswith("CREATE TABLE IF NOT EXISTS cash_advance_repayments"):
                        return await real("SELECT * FROM deliberately_missing_table")
                    return await real(sql)
                conn.execute = broken
                with pytest.raises(RuntimeError): await _migrate_cash_advance_repayments(conn)
                conn.execute = real
                await conn.execute("SELECT * FROM earlier_migration_kept")
            await _migrate_cash_advance_currency(conn)
            await _migrate_cash_advance_currency(conn)
            await _migrate_cash_advance_repayments(conn)
            await _migrate_cash_advance_repayments(conn)
            assert await conn.execute("SELECT * FROM cash_advance_repayments") == []
            fields = await conn.execute("SELECT column_name FROM information_schema.columns WHERE table_name='cash_advance_repayments'")
            assert len(fields) == 20
            for name, rows in before.items():
                actual = await conn.execute(f"SELECT * FROM {name}")
                if name == "cash_advances":
                    assert actual[0]["currency"] == "THB"
                    actual = [{key: value for key, value in row.items() if key != "currency"} for row in actual]
                assert actual == rows
            await conn.execute("INSERT INTO cash_advance_repayments(cash_advance_id,warehouse_id,repayment_date,amount,account_id,account_name,currency,payment_method,voucher_path,created_by_id,created_by_name,created_at,request_key) VALUES(1,1,'2026-10-18',1000,1,'现金','THB','cash','uploads/test.png',1,'老板',now(),'test-key')")
            await conn.execute("UPDATE cash_advance_repayments SET status='revoked',revoked_by_id=1,revoked_by_name='老板',revoked_at=now(),revoke_reason='选错账户' WHERE id=1")
            saved = await conn.execute("SELECT * FROM cash_advance_repayments")
            await conn.execute("COMMIT")
            await conn.execute("BEGIN")
            await _migrate_cash_advance_repayments(conn)
            assert await conn.execute("SELECT * FROM cash_advance_repayments") == saved
            for name, rows in before.items():
                actual = await conn.execute(f"SELECT * FROM {name}")
                if name == "cash_advances":
                    assert actual[0]["currency"] == "THB"
                    actual = [{key: value for key, value in row.items() if key != "currency"} for row in actual]
                assert actual == rows
            await conn.execute("COMMIT")
            print("REPAYMENT_SCHEMA", {"fields": len(fields), "legacy_unchanged": True, "failure_tested": fail})
        finally:
            proc.stdin.close(); await proc.wait()
    asyncio.run(run())

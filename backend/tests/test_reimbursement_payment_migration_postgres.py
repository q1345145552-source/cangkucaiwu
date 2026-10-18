"""实际 PostgreSQL 加列/付款历史幂等、逐处保存点、老付款不回填。"""
import asyncio
import os
from pathlib import Path
from types import SimpleNamespace
from app.services.reimbursement_payment import backfill_reimbursement_categories
import pytest
from scripts.seed import _migrate_reimbursement_payments
from tests.test_round12_migration_postgres import PostgreSQLConnection

pytestmark = pytest.mark.skipif(not os.environ.get("PGLITE_NODE"), reason="Requires embedded PostgreSQL")


@pytest.mark.parametrize("failure", [None, *range(13)])
def test_reimbursement_payment_schema_idempotent_savepoint_and_legacy_unchanged(failure):
    async def run():
        proc = await asyncio.create_subprocess_exec(os.environ["PGLITE_NODE"], str(Path(__file__).with_name("postgres_bridge.cjs")), stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE)
        class Connection(PostgreSQLConnection):
            async def execute(self, statement, params=None):
                if params:
                    sql = str(statement.bindparams(**params).compile(compile_kwargs={"literal_binds": True}))
                    await super().execute(sql)
                    return SimpleNamespace(rowcount=-1)
                return await super().execute(statement)
        conn = Connection(proc)
        try:
            for sql in (
                "CREATE TABLE warehouses(id INTEGER PRIMARY KEY)", "CREATE TABLE users(id INTEGER PRIMARY KEY)",
                "CREATE TABLE income_expense_categories(id SERIAL PRIMARY KEY,warehouse_id INTEGER,type TEXT,name TEXT,category_group TEXT,status TEXT,sort_order INTEGER)",
                "CREATE TABLE payment_accounts(id INTEGER PRIMARY KEY,opening_balance NUMERIC(14,2))",
                "CREATE TABLE cash_advances(id INTEGER PRIMARY KEY,amount NUMERIC(14,2),repaid_amount NUMERIC(14,2))",
                "CREATE TABLE expense_records(id INTEGER PRIMARY KEY,amount NUMERIC(14,2))",
                "CREATE TABLE expense_funds(id INTEGER PRIMARY KEY)",
                "CREATE TABLE reimbursements(id INTEGER PRIMARY KEY,total_amount NUMERIC(14,2),status TEXT,payment_method VARCHAR(20))",
                "INSERT INTO warehouses VALUES(1)", "INSERT INTO users VALUES(1)", "INSERT INTO payment_accounts VALUES(1,10000)",
                "INSERT INTO cash_advances VALUES(1,10000,0)", "INSERT INTO expense_records VALUES(1,750)",
                "INSERT INTO reimbursements VALUES(1,2000,'paid','cash')",
            ): await conn.execute(sql)
            tables = ("payment_accounts", "cash_advances", "expense_records", "reimbursements")
            before = {name: await conn.execute(f"SELECT * FROM {name}") for name in tables}
            await conn.execute("BEGIN")
            await conn.execute("CREATE TABLE earlier_migration_kept(id INTEGER)")
            if failure is not None:
                real, count = conn.execute, 0
                async def broken(sql):
                    nonlocal count
                    if str(sql).startswith(("ALTER TABLE", "CREATE TABLE", "CREATE INDEX", "CREATE UNIQUE INDEX")):
                        i = count
                        count += 1
                        if i == failure: return await real("SELECT * FROM deliberately_missing_table")
                    return await real(sql)
                conn.execute = broken
                with pytest.raises(RuntimeError): await _migrate_reimbursement_payments(conn)
                conn.execute = real
                await conn.execute("SELECT * FROM earlier_migration_kept")
            await _migrate_reimbursement_payments(conn)
            await _migrate_reimbursement_payments(conn)
            assert await conn.execute("SELECT * FROM reimbursement_payments") == []
            await backfill_reimbursement_categories(conn)
            await backfill_reimbursement_categories(conn)
            assert await conn.execute("SELECT warehouse_id,name,category_group,count(*) AS count FROM income_expense_categories GROUP BY warehouse_id,name,category_group") == [{"warehouse_id": 1, "name": "报销", "category_group": "operating", "count": 1}]
            for name in tables:
                rows = await conn.execute(f"SELECT * FROM {name}")
                if name == "reimbursements":
                    for field in ("payment_account_id", "payment_voucher_path", "funding_source", "cash_advance_id", "expense_record_id"):
                        assert rows[0][field] is None
                    rows = [{k: v for k, v in row.items() if k in before[name][0]} for row in rows]
                assert rows == before[name]
            columns = await conn.execute("SELECT column_name FROM information_schema.columns WHERE table_name='reimbursement_payments'")
            assert len(columns) == 23
            insert = "INSERT INTO reimbursement_payments(reimbursement_id,warehouse_id,amount,currency,funding_source,payment_account_id,previous_status,paid_by_id,paid_by_name,paid_at) VALUES(1,1,2000,'THB','company_account',1,'approved',1,'管理员',now())"
            await conn.execute(insert)
            await conn.execute("COMMIT")
            await conn.execute("BEGIN")
            with pytest.raises(RuntimeError):
                async with conn.begin_nested():
                    await conn.execute(insert)
            await conn.execute("UPDATE reimbursement_payments SET status='revoked',revoke_reason='测试撤销',revoked_at=now(),revoked_by_id=1 WHERE id=1")
            await conn.execute(insert)
            saved = await conn.execute("SELECT * FROM reimbursement_payments ORDER BY id")
            await _migrate_reimbursement_payments(conn)
            assert await conn.execute("SELECT * FROM reimbursement_payments ORDER BY id") == saved
            await conn.execute("COMMIT")
            assert await conn.execute("SELECT opening_balance FROM payment_accounts") == [{"opening_balance": before["payment_accounts"][0]["opening_balance"]}]
            print("REIMB_SCHEMA", {"failure": failure, "fields": len(columns), "legacy_unchanged": True})
        finally:
            proc.stdin.close()
            await proc.wait()
    asyncio.run(run())

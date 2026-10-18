"""真实 PostgreSQL 验证垫款工资加列、无账户成本及保存点。"""
import asyncio
import os
from pathlib import Path

import pytest

from scripts.seed import _migrate_payroll_cash_advance_link
from tests.test_round12_migration_postgres import PostgreSQLConnection

pytestmark = pytest.mark.skipif(not os.environ.get("PGLITE_NODE"), reason="Requires embedded PostgreSQL")


@pytest.mark.parametrize("failure", [None, "cash_advance_id", "cash_advance_index", "expense_account_nullable"])
def test_idempotent_link_nullable_cost_and_savepoint_without_old_data_changes(failure):
    async def run():
        proc = await asyncio.create_subprocess_exec(os.environ["PGLITE_NODE"], str(Path(__file__).with_name("postgres_bridge.cjs")),
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE)
        conn = PostgreSQLConnection(proc)
        try:
            for statement in (
                "CREATE TABLE cash_advances(id INTEGER PRIMARY KEY,amount NUMERIC(14,2),repaid_amount NUMERIC(14,2))",
                "CREATE TABLE payment_accounts(id INTEGER PRIMARY KEY,opening_balance NUMERIC(14,2))",
                "CREATE TABLE expense_records(id INTEGER PRIMARY KEY,account_id INTEGER NOT NULL REFERENCES payment_accounts(id),amount DOUBLE PRECISION)",
                "CREATE TABLE payroll_records(id INTEGER PRIMARY KEY,disbursed BOOLEAN,net_pay DOUBLE PRECISION,expense_record_id INTEGER REFERENCES expense_records(id))",
                "INSERT INTO cash_advances VALUES(1,10000,0)",
                "INSERT INTO payment_accounts VALUES(1,10000)",
                "INSERT INTO expense_records VALUES(1,1,750)",
                "INSERT INTO payroll_records VALUES(1,true,750,1),(2,false,7000,NULL)",
            ): await conn.execute(statement)
            before = {name: await conn.execute(f"SELECT * FROM {name} ORDER BY id") for name in (
                "cash_advances", "payment_accounts", "expense_records", "payroll_records",
            )}
            await conn.execute("BEGIN")
            await conn.execute("CREATE TABLE earlier_migration_kept(id INTEGER)")
            real = conn.execute
            if failure:
                async def broken(statement):
                    sql = str(statement)
                    if ((failure == "cash_advance_id" and sql.startswith("ALTER TABLE payroll_records"))
                        or (failure == "cash_advance_index" and sql.startswith("CREATE INDEX"))
                        or (failure == "expense_account_nullable" and sql.startswith("ALTER TABLE expense_records"))):
                        return await real("SELECT * FROM deliberately_missing_table")
                    return await real(statement)
                conn.execute = broken
                with pytest.raises(RuntimeError): await _migrate_payroll_cash_advance_link(conn)
                conn.execute = real
                await conn.execute("SELECT * FROM earlier_migration_kept")
            await _migrate_payroll_cash_advance_link(conn)
            await _migrate_payroll_cash_advance_link(conn)
            await conn.execute("COMMIT")
            for name, expected in before.items():
                actual = await conn.execute(f"SELECT * FROM {name} ORDER BY id")
                if name == "payroll_records":
                    assert all(r["cash_advance_id"] is None for r in actual)
                    actual = [{k: v for k, v in r.items() if k != "cash_advance_id"} for r in actual]
                assert actual == expected
            assert (await conn.execute("SELECT is_nullable FROM information_schema.columns WHERE table_name='expense_records' AND column_name='account_id'")) == [{"is_nullable": "YES"}]
            # Cost is stored without any company account and remains outside the funds query.
            await conn.execute("INSERT INTO expense_records VALUES(2,NULL,7000)")
            await conn.execute("UPDATE payroll_records SET disbursed=true,expense_record_id=2,cash_advance_id=1 WHERE id=2")
            assert (await conn.execute("SELECT sum(amount) total FROM expense_records")) == [{"total": 7750}]
            funds_sql = "SELECT sum(er.amount) total FROM expense_records er WHERE NOT EXISTS(SELECT 1 FROM payroll_records pr WHERE pr.expense_record_id=er.id AND pr.cash_advance_id IS NOT NULL)"
            assert await conn.execute(funds_sql) == [{"total": 750}]
            await conn.execute("BEGIN")
            await _migrate_payroll_cash_advance_link(conn)
            await conn.execute("COMMIT")
            assert (await conn.execute("SELECT cash_advance_id FROM payroll_records WHERE id=2")) == [{"cash_advance_id": 1}]
            with pytest.raises(RuntimeError):
                await conn.execute("UPDATE payroll_records SET cash_advance_id=999 WHERE id=2")
            print("PAYROLL_ADVANCE_MIGRATION", {"failure": failure, "old_data_unchanged": True, "cost": 7750, "funds": 750})
        finally:
            proc.stdin.close()
            await proc.wait()
    asyncio.run(run())

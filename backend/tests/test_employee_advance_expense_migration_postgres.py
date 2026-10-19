"""真实 PostgreSQL 验证新旧预支隔离、分类幂等、唯一关联及独立保存点。"""
import asyncio
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import text
from sqlalchemy.dialects import postgresql

from scripts.seed import _migrate_employee_advance_expenses
from app.services.employee_advance_expense import backfill_advance_categories
from tests.test_round12_migration_postgres import PostgreSQLConnection

pytestmark = pytest.mark.skipif(not os.environ.get("PGLITE_NODE"), reason="Requires embedded PostgreSQL")


@pytest.mark.parametrize("failure", [None, "expense_tracking_enabled", "expense_record_id", "fund_item_id", "expense_index", "fund_item_index"])
def test_actual_migration_preserves_history_and_recovers_each_savepoint(failure):
    async def run():
        proc = await asyncio.create_subprocess_exec(os.environ["PGLITE_NODE"],
            str(Path(__file__).with_name("postgres_bridge.cjs")),
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE)
        conn = PostgreSQLConnection(proc)
        try:
            for sql in (
                "CREATE TABLE expense_records(id INTEGER PRIMARY KEY,amount DOUBLE PRECISION)",
                "INSERT INTO expense_records VALUES(1,50)",
                "CREATE TABLE expense_fund_items(id INTEGER PRIMARY KEY)",
                "INSERT INTO expense_fund_items VALUES(1)",
                "CREATE TABLE employee_advances(id INTEGER PRIMARY KEY,amount DOUBLE PRECISION,approval_status TEXT,deducted_amount DOUBLE PRECISION)",
                "INSERT INTO employee_advances VALUES(1,100,'approved',0),(2,200,'pending',0),(3,300,'rejected',0)",
                "BEGIN", "CREATE TABLE earlier_migration_kept(id INTEGER)",
            ): await conn.execute(sql)
            old = await conn.execute("SELECT * FROM employee_advances ORDER BY id")
            real = conn.execute
            if failure:
                async def broken(statement):
                    sql = str(statement)
                    target = {
                        "expense_index": "CREATE UNIQUE INDEX IF NOT EXISTS ix_employee_advances_expense_record_id",
                        "fund_item_index": "CREATE UNIQUE INDEX IF NOT EXISTS ix_employee_advances_fund_item_id",
                    }.get(failure, f"ALTER TABLE employee_advances ADD COLUMN IF NOT EXISTS {failure} ")
                    return await real("SELECT * FROM deliberately_missing_table" if sql.startswith(target) else statement)
                conn.execute = broken
                with pytest.raises(RuntimeError):
                    await _migrate_employee_advance_expenses(conn)
                conn.execute = real
                await conn.execute("SELECT * FROM earlier_migration_kept")
            await _migrate_employee_advance_expenses(conn)
            await _migrate_employee_advance_expenses(conn)
            await conn.execute("COMMIT")
            rows = await conn.execute("SELECT * FROM employee_advances ORDER BY id")
            assert [{k: r[k] for k in old[0]} for r in rows] == old
            assert all(r["expense_tracking_enabled"] is False and r["expense_record_id"] is None and r["fund_item_id"] is None for r in rows)
            assert await conn.execute("SELECT * FROM expense_records") == [{"id": 1, "amount": 50}]
            # 老待审批在上线后获批仍保留“不记新支出”的标记。
            await conn.execute("UPDATE employee_advances SET approval_status='approved' WHERE id=2")
            await conn.execute("INSERT INTO employee_advances VALUES(4,1000,'approved',0,true,1,1)")
            await conn.execute("BEGIN")
            await _migrate_employee_advance_expenses(conn)
            await conn.execute("COMMIT")
            assert (await conn.execute("SELECT expense_tracking_enabled,expense_record_id,fund_item_id FROM employee_advances WHERE id=4")) == [{"expense_tracking_enabled": True, "expense_record_id": 1, "fund_item_id": 1}]
            assert (await conn.execute("SELECT expense_tracking_enabled FROM employee_advances WHERE id=2")) == [{"expense_tracking_enabled": False}]
            for sql in (
                "INSERT INTO employee_advances(id,expense_record_id) VALUES(5,1)",
                "INSERT INTO employee_advances(id,fund_item_id) VALUES(5,1)",
                "INSERT INTO employee_advances(id,expense_record_id) VALUES(5,999)",
            ):
                with pytest.raises(RuntimeError): await conn.execute(sql)
            print("ADVANCE_EXPENSE_POSTGRES", {"failure": failure, "old_advances": 3,
                "old_links": 0, "original_expense_count": 1, "migrate_twice": "ok"})
        finally:
            proc.stdin.close()
            await proc.wait()
    asyncio.run(run())


def test_category_backfill_is_per_warehouse_idempotent_and_does_not_write_costs():
    async def run():
        proc = await asyncio.create_subprocess_exec(os.environ["PGLITE_NODE"],
            str(Path(__file__).with_name("postgres_bridge.cjs")),
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE)
        class Connection(PostgreSQLConnection):
            async def execute(self, statement, params=None):
                if params is not None:
                    query = text(str(statement)).bindparams(**params).compile(
                        dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
                    await super().execute(query)
                    return SimpleNamespace(rowcount=0)
                return await super().execute(statement)
        conn = Connection(proc)
        try:
            for sql in (
                "CREATE TABLE warehouses(id INTEGER PRIMARY KEY)",
                "INSERT INTO warehouses VALUES(1),(2)",
                "CREATE TABLE income_expense_categories(id SERIAL PRIMARY KEY,warehouse_id INTEGER,type TEXT,name TEXT,category_group TEXT,status TEXT,sort_order INTEGER)",
                "INSERT INTO income_expense_categories(warehouse_id,type,name,category_group,status) VALUES(1,'expense','员工预支','operating','active'),(1,'expense','员工工资','operating','active')",
                "BEGIN",
            ): await conn.execute(sql)
            await backfill_advance_categories(conn)
            await backfill_advance_categories(conn)
            await conn.execute("COMMIT")
            assert await conn.execute("SELECT warehouse_id,count(*) n FROM income_expense_categories WHERE name='员工预支' AND category_group='operating' AND type='expense' GROUP BY warehouse_id ORDER BY warehouse_id") == [{"warehouse_id": 1, "n": 1}, {"warehouse_id": 2, "n": 1}]
            assert await conn.execute("SELECT count(*) n FROM income_expense_categories WHERE name='员工工资'") == [{"n": 1}]
            await conn.execute("INSERT INTO warehouses VALUES(3)")
            await backfill_advance_categories(conn)
            assert await conn.execute("SELECT count(*) n FROM income_expense_categories WHERE name='员工预支'") == [{"n": 3}]
        finally:
            proc.stdin.close()
            await proc.wait()
    asyncio.run(run())

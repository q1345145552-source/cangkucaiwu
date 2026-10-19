"""真实 PostgreSQL：用途关联加表加列、部分迁移、重复启动与保存点失败。"""
import asyncio
import os
from pathlib import Path
import pytest
from scripts.seed import _migrate_cash_advance_documents
from tests.test_round12_migration_postgres import PostgreSQLConnection

pytestmark = pytest.mark.skipif(not os.environ.get("PGLITE_NODE"), reason="Requires embedded PostgreSQL")


@pytest.mark.parametrize("failure", [None, "amount_difference_note", "cash_advance_documents", "documents_index"])
def test_structure_idempotency_old_data_and_local_savepoints(failure):
    async def run():
        proc=await asyncio.create_subprocess_exec(os.environ["PGLITE_NODE"],str(Path(__file__).with_name("postgres_bridge.cjs")),stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE)
        conn=PostgreSQLConnection(proc)
        try:
            for sql in ("CREATE TABLE warehouses(id INTEGER PRIMARY KEY)","INSERT INTO warehouses VALUES(1)",
                "CREATE TABLE cash_advances(id INTEGER PRIMARY KEY, warehouse_id INTEGER, amount NUMERIC(14,2), status TEXT)",
                "INSERT INTO cash_advances VALUES(1,1,3000,'pending')","CREATE TABLE payroll_records(id INTEGER, net_pay NUMERIC(14,2))",
                "INSERT INTO payroll_records VALUES(2,6046)","BEGIN","CREATE TABLE previous_step_kept(id INTEGER)"):
                await conn.execute(sql)
            if failure:
                execute=conn.execute
                marker={"amount_difference_note":"ALTER TABLE cash_advances", "cash_advance_documents":"CREATE TABLE IF NOT EXISTS", "documents_index":"CREATE INDEX"}[failure]
                async def broken(sql):
                    if str(sql).startswith(marker): return await execute("SELECT * FROM deliberate_missing_table")
                    return await execute(sql)
                conn.execute=broken
                with pytest.raises(RuntimeError): await _migrate_cash_advance_documents(conn)
                conn.execute=execute
                await conn.execute("SELECT * FROM previous_step_kept")
            await _migrate_cash_advance_documents(conn)
            await _migrate_cash_advance_documents(conn)
            rows=await conn.execute("SELECT * FROM cash_advances")
            assert rows==[{"id":1,"warehouse_id":1,"amount":"3000.00","status":"pending","amount_difference_note":None}]
            assert await conn.execute("SELECT * FROM cash_advance_documents")==[]
            await conn.execute("INSERT INTO cash_advance_documents(cash_advance_id,warehouse_id,document_type,document_id,document_number,title,amount,currency) VALUES(1,1,'payroll',2,'工资单 #2','员工',7000,'THB')")
            before=await conn.execute("SELECT * FROM cash_advance_documents")
            await conn.execute("COMMIT"); await conn.execute("BEGIN")
            await _migrate_cash_advance_documents(conn)
            assert await conn.execute("SELECT * FROM cash_advance_documents")==before
            assert await conn.execute("SELECT * FROM cash_advances")==rows
            assert await conn.execute("SELECT * FROM payroll_records")==[{"id":2,"net_pay":"6046.00"}]
            await conn.execute("SAVEPOINT duplicate")
            with pytest.raises(RuntimeError):
                await conn.execute("INSERT INTO cash_advance_documents(cash_advance_id,warehouse_id,document_type,document_id,document_number,title,amount,currency) VALUES(1,1,'payroll',2,'工资单 #2','员工',7000,'THB')")
            await conn.execute("ROLLBACK TO SAVEPOINT duplicate")
            await conn.execute("COMMIT")
        finally:
            proc.stdin.close(); await proc.wait()
    asyncio.run(run())

"""在真实嵌入式 PostgreSQL 执行新字段迁移、默认值、重跑与保存点回滚。"""
import asyncio
import os
from pathlib import Path
import pytest
from scripts.seed import _migrate_makeup_quota_column
from tests.test_round12_migration_postgres import PostgreSQLConnection

pytestmark = pytest.mark.skipif(not os.environ.get("PGLITE_NODE"), reason="Set PGLITE_NODE and NODE_PATH for embedded PostgreSQL")


@pytest.mark.parametrize("fail", [False, True])
def test_old_records_default_true_and_batch_false_preserved(fail):
    async def run():
        process = await asyncio.create_subprocess_exec(os.environ["PGLITE_NODE"], str(Path(__file__).with_name("postgres_bridge.cjs")), stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE)
        class Connection(PostgreSQLConnection):
            async def execute(self, statement):
                if self.fail_column and str(statement).startswith("ALTER TABLE clock_in_records ADD COLUMN"):
                    return await super().execute("ALTER TABLE missing_table ADD COLUMN fail BOOLEAN")
                return await super().execute(statement)
        conn = Connection(process)
        try:
            await conn.execute("CREATE TABLE clock_in_records(id INTEGER PRIMARY KEY,is_makeup BOOLEAN,makeup_reason TEXT)")
            await conn.execute("INSERT INTO clock_in_records VALUES(1,true,'历史普通补卡'),(2,false,NULL)")
            before = await conn.execute("SELECT * FROM clock_in_records ORDER BY id")
            await conn.execute("BEGIN")
            await conn.execute("CREATE TABLE previous_migration_kept(id INTEGER)")
            if fail:
                conn.fail_column = True
                with pytest.raises(RuntimeError): await _migrate_makeup_quota_column(conn)
                await conn.execute("SELECT * FROM previous_migration_kept")
            conn.fail_column = None
            await _migrate_makeup_quota_column(conn)
            await _migrate_makeup_quota_column(conn)
            rows = await conn.execute("SELECT * FROM clock_in_records ORDER BY id")
            assert all(r["makeup_counts_toward_limit"] is True for r in rows)
            assert [{k: r[k] for k in before[0]} for r in rows] == before
            await conn.execute("INSERT INTO clock_in_records(id,is_makeup,makeup_reason,makeup_counts_toward_limit) VALUES(3,true,'系统故障',false)")
            await conn.execute("INSERT INTO clock_in_records(id,is_makeup) VALUES(4,true)")
            await conn.execute("COMMIT")
            await conn.execute("BEGIN")
            await _migrate_makeup_quota_column(conn)
            await conn.execute("COMMIT")
            final = await conn.execute("SELECT id,makeup_counts_toward_limit FROM clock_in_records ORDER BY id")
            assert final == [{"id": i, "makeup_counts_toward_limit": i != 3} for i in (1, 2, 3, 4)]
            print("BATCH_MIGRATION", final)
        finally:
            process.stdin.close()
            await process.wait()
    asyncio.run(run())

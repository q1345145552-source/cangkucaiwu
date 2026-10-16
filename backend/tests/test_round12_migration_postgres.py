"""Real startup helper on embedded PostgreSQL, including actual DDL/savepoint rollback.

Install @electric-sql/pglite outside the repo. Run with PGLITE_NODE=/path/to/node
and NODE_PATH=/path/to/temporary/node_modules; normal Python-only runs skip this suite.
"""
import asyncio
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
import pytest
from scripts.seed import _migrate_user_attendance_columns

pytestmark = pytest.mark.skipif(not os.environ.get('PGLITE_NODE'), reason='Optional embedded PostgreSQL: set PGLITE_NODE and NODE_PATH')
FIELDS = ('attendance_enabled', 'attendance_employee_id', 'attendance_enabled_at')


class PostgreSQLConnection:
    def __init__(self, process, fail_column=None):
        self.process, self.fail_column = process, fail_column
        self.savepoints = 0
        self.failures = 0
    async def execute(self, statement):
        sql = str(statement)
        if self.fail_column and sql.startswith('ALTER TABLE users ADD COLUMN') and f' {self.fail_column} ' in sql:
            sql = 'ALTER TABLE deliberately_missing_table ADD COLUMN fail INTEGER'
            self.failures += 1
        self.process.stdin.write((json.dumps({'sql':sql})+'\n').encode())
        await self.process.stdin.drain()
        line = await self.process.stdout.readline()
        assert line, 'Embedded PostgreSQL exited unexpectedly'
        result = json.loads(line)
        if 'error' in result:
            raise RuntimeError(result['error'])
        return result['rows']
    @asynccontextmanager
    async def begin_nested(self):
        self.savepoints += 1
        name = f'migration_{self.savepoints}'
        await self.execute(f'SAVEPOINT {name}')
        try:
            yield
        except Exception:
            await self.execute(f'ROLLBACK TO SAVEPOINT {name}')
            await self.execute(f'RELEASE SAVEPOINT {name}')
            raise
        else:
            await self.execute(f'RELEASE SAVEPOINT {name}')


@pytest.mark.parametrize('fail_column', [None, *FIELDS])
@pytest.mark.parametrize('partially_migrated', [False, True])
def test_real_postgres_migration(fail_column, partially_migrated):
    async def run():
        process = await asyncio.create_subprocess_exec(os.environ['PGLITE_NODE'], str(Path(__file__).with_name('postgres_bridge.cjs')),
                                                      stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE)
        conn = PostgreSQLConnection(process)
        try:
            await conn.execute('CREATE TABLE employees(id INTEGER PRIMARY KEY)')
            await conn.execute('CREATE TABLE users(id INTEGER PRIMARY KEY, role TEXT, display_name TEXT, extra_permissions JSONB)')
            for i, role in enumerate(('super_admin','warehouse_admin','supervisor','staff','warehouse_labor'),1):
                await conn.execute(f"INSERT INTO users VALUES({i}, '{role}', 'old', '[\"工资\"]')")
            if partially_migrated:
                await conn.execute('ALTER TABLE users ADD COLUMN attendance_enabled BOOLEAN NOT NULL DEFAULT false')
                await conn.execute('UPDATE users SET attendance_enabled=true WHERE id=3')
            before = await conn.execute('SELECT id,role,display_name,extra_permissions FROM users ORDER BY id')
            await conn.execute('BEGIN')
            await conn.execute("UPDATE users SET display_name='prior migration survived' WHERE id=1")
            conn.fail_column = fail_column
            await _migrate_user_attendance_columns(conn)
            assert conn.savepoints == 3
            assert conn.failures == (1 if fail_column else 0)
            assert (await conn.execute('SELECT display_name FROM users WHERE id=1'))[0]['display_name'] == 'prior migration survived'
            columns = await conn.execute("SELECT column_name FROM information_schema.columns WHERE table_name='users'")
            expected = set(FIELDS) - ({fail_column} if fail_column else set())
            if partially_migrated: expected.add('attendance_enabled')
            assert expected <= {c['column_name'] for c in columns}
            conn.fail_column = None
            await _migrate_user_attendance_columns(conn)
            await _migrate_user_attendance_columns(conn)
            await conn.execute('COMMIT')
            await conn.execute('BEGIN')
            await _migrate_user_attendance_columns(conn)
            await conn.execute('COMMIT')
            rows = await conn.execute('SELECT * FROM users ORDER BY id')
            for i, row in enumerate(rows):
                assert row['role'] == before[i]['role']
                assert row['extra_permissions'] == before[i]['extra_permissions']
                assert row['display_name'] == ('prior migration survived' if i == 0 else before[i]['display_name'])
                assert row['attendance_enabled'] is (partially_migrated and row['id']==3)
                assert row['attendance_employee_id'] is None and row['attendance_enabled_at'] is None
            await conn.execute("INSERT INTO users(id,role) VALUES(6,'staff')")
            assert (await conn.execute('SELECT attendance_enabled FROM users WHERE id=6'))[0]['attendance_enabled'] is False
            print('\nPostgreSQL迁移后的实际老账号值：', rows)
        finally:
            process.stdin.close()
            await process.wait()
    asyncio.run(run())

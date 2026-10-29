"""Exercise the actual seed entry point before the rest of the migrations."""
import asyncio
from contextlib import asynccontextmanager

import pytest

from scripts import seed


def test_clock_photo_schema_can_execute_at_start_of_seed(monkeypatch):
    statements = []

    class ReachedRemainingMigrations(Exception):
        pass

    class Connection:
        async def run_sync(self, callback):
            pass

        async def execute(self, statement):
            statements.append(str(statement))

    class Engine:
        @asynccontextmanager
        async def begin(self):
            yield Connection()

    async def stop_after_clock_schema(conn):
        raise ReachedRemainingMigrations

    monkeypatch.setattr(seed, "_get_engine", lambda: Engine())
    monkeypatch.setattr(seed, "_migrate_monthly_salary_template", stop_after_clock_schema)
    with pytest.raises(ReachedRemainingMigrations):
        asyncio.run(seed.seed())
    assert statements == [
        "ALTER TABLE clock_in_records ADD COLUMN IF NOT EXISTS photo_fingerprint VARCHAR(64)",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_clock_photo_warehouse_fingerprint "
        "ON clock_in_records (COALESCE(warehouse_id, 0), photo_fingerprint) "
        "WHERE photo_fingerprint IS NOT NULL",
    ]

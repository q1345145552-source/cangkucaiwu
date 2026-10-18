"""Disposable local test accounts and SQLite database for batch makeup UI."""
import asyncio
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
import pytest
import uvicorn
from sqlalchemy import select, event
from app.models import User
from app.core.security import hash_password
from app.main import app
from tests.test_round3_permissions import hr_environment
from tests.test_round2_permissions import set_perms
from tests.test_batch_makeup import seed_batch


async def main():
    patch = pytest.MonkeyPatch()
    directory = Path(tempfile.mkdtemp(prefix="batch-makeup-ui-"))
    async with hr_environment(directory, patch) as (engine, factory, _):
        @event.listens_for(engine.sync_engine, "connect")
        def sqlite_functions(conn, _):
            conn.create_function("to_char", 2, lambda value, fmt: str(value)[:7] if value else None)
        await engine.dispose()
        await seed_batch(factory, patch)
        await set_perms(factory, 4, ["考勤"])
        async with factory() as db:
            for user in (await db.execute(select(User))).scalars():
                user.password_hash = hash_password("test-password")
            await db.commit()
        print(f"Batch makeup fixture ready: {directory}", flush=True)
        await uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=18080, log_level="warning")).serve()
    patch.undo()


asyncio.run(main())

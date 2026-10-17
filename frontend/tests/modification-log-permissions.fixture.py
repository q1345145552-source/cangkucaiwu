"""Local isolated UI fixture; never connects to production."""
import asyncio
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
import pytest
import uvicorn
from sqlalchemy import select, event
from tests.test_round3_permissions import hr_environment
from tests.test_round2_permissions import set_perms
from tests.test_modification_log_permissions import seed_logs
from app.models import User
from app.core.security import hash_password
from app.main import app


async def main():
    patch = pytest.MonkeyPatch()
    directory = Path(tempfile.mkdtemp(prefix="history-ui-"))
    async with hr_environment(directory, patch) as (engine, factory, _):
        @event.listens_for(engine.sync_engine, "connect")
        def sqlite_functions(conn, _):
            conn.create_function("to_char", 2, lambda value, fmt: str(value)[:7] if value else None)

        await engine.dispose()
        await seed_logs(factory)
        for uid in (3, 4):
            await set_perms(factory, uid, ["修改日志"])
        async with factory() as db:
            for user in (await db.execute(select(User))).scalars():
                user.password_hash = hash_password("test-password")
            await db.commit()
        print(f"Isolated modification log fixture: {directory}", flush=True)
        await uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=18080, log_level="warning")).serve()
    patch.undo()


asyncio.run(main())

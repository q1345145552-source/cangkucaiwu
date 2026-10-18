"""本机垫款界面验收专用数据库，与生产数据隔离。"""
import asyncio
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
import pytest
import uvicorn
from sqlalchemy import select
from fastapi.staticfiles import StaticFiles
from app.main import app
from app.models import User
from app.core.security import hash_password
import app.api.v1.cash_advance as cash
from tests.test_round2_permissions import environment
from app.services.permission_migrations import backfill_cash_advances_permission


async def main():
    patch = pytest.MonkeyPatch()
    directory = Path(tempfile.mkdtemp(prefix="cash-advances-ui-"))
    async with environment(directory, patch) as (engine, factory, _):
        uploads = directory / "uploads"; uploads.mkdir()
        patch.setattr(cash, "UPLOAD_DIR", str(uploads))
        app.mount("/uploads", StaticFiles(directory=str(uploads)), name="cash-test-uploads")
        async with factory() as db:
            for user in (await db.execute(select(User))).scalars():
                user.password_hash = hash_password("test-password")
                user.display_name = {1: "测试老板", 2: "测试超管", 3: "测试财务", 4: "测试主管"}[user.id]
            await db.commit()
        async with engine.begin() as conn: await backfill_cash_advances_permission(conn)
        print(f"Isolated cash advance UI DB: {directory}", flush=True)
        await uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=18080, log_level="warning")).serve()
    patch.undo()


asyncio.run(main())

"""三张账本地一次性验收库；完全不连接生产。"""
import asyncio
import tempfile
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
import pytest
import uvicorn
from sqlalchemy import select
from app.main import app
from app.models import User
from app.core.security import hash_password
from tests.test_cost_funds_debt import environment
from tests.test_round2_permissions import set_perms

async def main():
    patch = pytest.MonkeyPatch()
    async with environment(Path(tempfile.mkdtemp(prefix="three-ledgers-ui-")), patch) as (_, f, c, aid):
        async with f() as db:
            for u in (await db.execute(select(User))).scalars(): u.password_hash = hash_password("test-password")
            (await db.get(User, 1)).display_name = "测试老板"
            await db.commit()
        await set_perms(f, 3, ["报表中心"])
        print("Isolated three-ledgers UI ready on 127.0.0.1:18080", flush=True)
        await uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=18080, log_level="warning")).serve()
    patch.undo()

asyncio.run(main())

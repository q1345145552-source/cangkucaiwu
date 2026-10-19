"""关联待付单据的浏览器验收环境，全部数据位于临时隔离库。"""
import asyncio
import json
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
import pytest
import uvicorn
from sqlalchemy import select
from app.main import app
from app.models import User
from app.core.security import hash_password
from tests.test_round3_permissions import hr_environment
from tests.test_cash_advance_documents import prepare
from tests.test_cash_advances import finance_snapshot


async def main():
    patch = pytest.MonkeyPatch()
    folder = Path(tempfile.mkdtemp(prefix="cash-documents-ui-"))
    async with hr_environment(folder, patch) as (_, factory, _):
        await prepare(factory)
        async with factory() as db:
            for user in (await db.execute(select(User))).scalars():
                user.password_hash = hash_password("test-password")
            await db.commit()
        Path("/tmp/cash-documents-ui-db").write_text(str(folder / "round2.db"))
        Path("/tmp/cash-documents-ui-before.json").write_text(json.dumps(await finance_snapshot(factory), default=str, ensure_ascii=False))
        print("Isolated cash document UI ready", folder, flush=True)
        await uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=18080, log_level="warning")).serve()
    patch.undo()


asyncio.run(main())

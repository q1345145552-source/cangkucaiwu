"""本地一次性备用金验收库，不连接生产；测试老板/主管密码 test-password。"""
import asyncio
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
from tests.test_fund_disbursement import environment, topup, spend, BASE
from tests.test_round2_permissions import auth


async def main():
    patch = pytest.MonkeyPatch()
    async with environment(Path(tempfile.mkdtemp(prefix="fund-disbursement-ui-")), patch) as (_, f, c, fid):
        async with f() as db:
            for u in (await db.execute(select(User))).scalars():
                u.password_hash = hash_password("test-password")
            (await db.get(User, 1)).display_name = "测试老板"
            (await db.get(User, 4)).display_name = "测试主管"
            await db.commit()
        assert (await topup(c, fid)).status_code == 200
        item = await spend(c, fid)
        assert (await c.post(BASE + "/review/batch", headers=auth(1), json={"item_ids": [item.json()["id"]], "action": "approve"})).status_code == 200
        print("Isolated fund-disbursement UI ready on 127.0.0.1:18080", flush=True)
        await uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=18080, log_level="warning")).serve()
    patch.undo()


asyncio.run(main())

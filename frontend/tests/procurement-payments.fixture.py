"""采购实付的本地一次性验收库；不连接生产。"""
import asyncio
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
import pytest
from sqlalchemy import select
import uvicorn

from app.main import app
from app.models import User, PaymentAccount
from app.core.security import hash_password
from tests.test_dashboard_procurement_payments import environment


async def main():
    patch = pytest.MonkeyPatch()
    directory = Path(tempfile.mkdtemp(prefix="procurement-payment-ui-"))
    async with environment(directory, patch) as (_, factory, _):
        async with factory() as db:
            for user in (await db.execute(select(User))).scalars():
                user.password_hash = hash_password("test-password")
                user.display_name = {1: "测试老板", 2: "测试超管", 3: "测试财务", 4: "测试主管", 5: "测试劳工", 6: "外仓劳工"}[user.id]
            (await db.get(PaymentAccount, 1)).opening_balance = 20000
            await db.commit()
        print("Isolated procurement-payment UI on 127.0.0.1:18080", flush=True)
        await uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=18080, log_level="warning")).serve()
    patch.undo()


asyncio.run(main())

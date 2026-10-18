"""独立本地工资资金来源验收数据，不连接生产数据库。"""
import asyncio
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
import pytest
import uvicorn
from sqlalchemy import select
from app.models import User
from app.models.payroll import PayrollRecord
from app.core.security import hash_password
from app.main import app
from tests.test_payroll_cash_advance import environment
from tests.test_cash_advance_repayments import approved
from tests.test_cash_advances import create


async def main():
    patch = pytest.MonkeyPatch()
    async with environment(Path(tempfile.mkdtemp(prefix="payroll-cash-advance-ui-")), patch) as (factory, c):
        async with factory() as db:
            for user in (await db.execute(select(User))).scalars():
                user.password_hash = hash_password("test-password")
            (await db.get(User, 1)).display_name = "测试老板"
            (await db.get(User, 4)).display_name = "测试主管"
            r = await db.get(PayrollRecord, 1)
            r.status, r.net_pay = "confirmed", 2000
            await db.commit()
        await approved(c, amount=10000, description="工资资金来源验收")
        await approved(c, amount=1000, description="余额不足验收")
        await approved(c, amount=10000, currency="CNY", description="币种不符，不应在工资下拉出现")
        await create(c, amount=10000, description="待确认，不应在工资下拉出现")
        print("Isolated payroll cash advance UI ready: 127.0.0.1:18080", flush=True)
        await uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=18080, log_level="warning")).serve()
    patch.undo()


asyncio.run(main())

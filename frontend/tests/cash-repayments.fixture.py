"""归还界面独立测试库：泰铢和人民币垫款、现金账户、750原有成本。"""
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
from app.models import User, PaymentAccount
from app.core.security import hash_password
from app.services.permission_migrations import backfill_cash_advances_permission
import app.api.v1.cash_advance as cash
from tests.test_cash_advance_repayments import environment, approved


async def main():
    patch = pytest.MonkeyPatch()
    directory = Path(tempfile.mkdtemp(prefix="cash-repayments-ui-"))
    async with environment(directory, patch) as (engine, factory, c):
        Path(cash.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
        app.mount("/uploads", StaticFiles(directory=cash.UPLOAD_DIR), name="repayment-test-uploads")
        async with factory() as db:
            for user in (await db.execute(select(User))).scalars():
                user.password_hash = hash_password("test-password")
                user.display_name = {1: "测试老板", 2: "测试超管", 3: "测试财务", 4: "测试主管", 5: "测试劳工", 6: "外仓劳工"}[user.id]
            db.add(PaymentAccount(id=3, warehouse_id=1, account_name="人民币现金", account_type="cash", account_number="CNY", currency="CNY", status="active", opening_balance=20000))
            await db.commit()
        async with engine.begin() as conn: await backfill_cash_advances_permission(conn)
        for description, currency in [("全额归还验收", "THB"), ("部分归还验收", "THB"), ("人民币垫款", "CNY")]:
            await approved(c, description=description, currency=currency)
        print(f"Repayment UI isolated DB: {directory}", flush=True)
        await uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=18080, log_level="warning")).serve()
    patch.undo()


asyncio.run(main())

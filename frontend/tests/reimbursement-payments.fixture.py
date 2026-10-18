"""本地报销付款界面验收；使用一次性 SQLite，不连接生产。"""
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
from app.services.permission_migrations import backfill_cash_advances_permission
from tests.test_reimbursement_payments import environment, approved
from tests.test_cash_advance_repayments import approved as loan
import app.services.reimbursement_payment as payments

async def main():
    patch = pytest.MonkeyPatch()
    directory = Path(tempfile.mkdtemp(prefix="reimbursement-payments-ui-"))
    async with environment(directory, patch) as (engine, factory, c):
        Path(payments.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
        app.mount("/uploads", StaticFiles(directory=payments.UPLOAD_DIR), name="reimbursement-test-uploads")
        async with factory() as db:
            for user in (await db.execute(select(User))).scalars(): user.password_hash = hash_password("test-password")
            (await db.get(User, 1)).display_name = "测试老板"
            (await db.get(User, 4)).display_name = "测试主管"
            await db.commit()
        async with engine.begin() as conn: await backfill_cash_advances_permission(conn)
        await loan(c, amount=10000, description="报销资金来源验收")
        await approved(c)
        await approved(c)
        await approved(c, fund=True)
        print(f"Reimbursement UI isolated DB: {directory}", flush=True)
        await uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=18080, log_level="warning")).serve()
    patch.undo()

asyncio.run(main())

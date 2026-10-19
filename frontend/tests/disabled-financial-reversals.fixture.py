"""三处撤销停用的本地界面库，包含有效和已撤销历史；不连接生产。"""
import asyncio
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
import pytest
from sqlalchemy import select
from fastapi.staticfiles import StaticFiles
import uvicorn

from app.main import app
from app.models import User
from app.core.security import hash_password
from app.api.v1.reimbursement import revoke_payment, RevokePayment
from app.api.v1.cash_advance import revoke_repayment, RevokeRepaymentRequest
from app.services import reimbursement_payment as service
from tests.test_disabled_financial_reversals import executed_records
from tests.test_reimbursement_payments import environment, approved, upload, pay
from tests.test_cash_advance_repayments import approved as loan, voucher, repay


async def main():
    patch = pytest.MonkeyPatch()
    directory = Path(tempfile.mkdtemp(prefix="disabled-financial-reversals-ui-"))
    async with environment(directory, patch) as (_, factory, c):
        async with factory() as db:
            for user in (await db.execute(select(User))).scalars():
                user.password_hash = hash_password("test-password")
                user.display_name = {1: "测试老板", 2: "测试超管", 3: "测试财务", 4: "测试主管", 5: "测试劳工", 6: "外仓劳工"}[user.id]
            await db.commit()
        await executed_records(c)
        rid = await approved(c, amount=500)
        assert (await pay(c, rid, await upload(c, rid))).status_code == 200
        aid = await loan(c, description="历史已撤销归还")
        repayment = await repay(c, aid, await voucher(c), amount="500")
        assert repayment.status_code == 200
        async with factory() as db:
            admin = await db.get(User, 1)
            admin._warehouse_ids = [1]
            # 只构造历史，正常 HTTP 入口的停用依赖未被覆盖。
            await revoke_payment(rid, RevokePayment(reason="历史付款撤销"), current_user=admin, db=db)
            await revoke_repayment(repayment.json()["repayment"]["id"], RevokeRepaymentRequest(reason="历史归还撤销"), user=admin, db=db)
            await db.commit()
        app.mount("/uploads", StaticFiles(directory=service.UPLOAD_DIR), name="disabled-reversal-test-uploads")
        print("Isolated reversal-disabled UI on 127.0.0.1:18080", flush=True)
        await uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=18080, log_level="warning")).serve()
    patch.undo()


asyncio.run(main())

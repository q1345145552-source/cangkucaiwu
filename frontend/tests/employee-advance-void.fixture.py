"""仅供本地界面验收的隔离库，固定测试密码；绝不连接生产。"""
import asyncio
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
import pytest
import uvicorn
from sqlalchemy import event, select
from app.main import app
from app.models import User, SalaryTemplate
from app.models.employee_advance import EmployeeAdvance
from app.core.security import hash_password
from tests.test_round2_permissions import auth
from tests.advance_funding_test_support import funded_hr_environment as hr_environment
from tests.test_employee_advance_expense import BODY, supervisor_self


async def main():
    patch = pytest.MonkeyPatch()
    folder = Path(tempfile.mkdtemp(prefix="advance-void-ui-"))
    async with hr_environment(folder, patch) as (engine, factory, client):
        @event.listens_for(engine.sync_engine, "connect")
        def sqlite_functions(conn, _):
            conn.create_function("to_char", 2, lambda value, fmt: str(value)[:7] if value else None)
        await engine.dispose()
        await supervisor_self(factory)
        async with factory() as db:
            for user in (await db.execute(select(User))).scalars():
                user.password_hash = hash_password("test-password")
            template = await db.get(SalaryTemplate, 1)
            template.type, template.amount = "monthly", 10000
            await db.commit()
        for amount, uid, remark in ((1000, 1, "界面作废测试"), (500, 4, "待审批示例"),
                                    (200, 1, "已作废示例"), (400, 1, "已结清示例")):
            result = await client.post("/api/v1/employee-advances", headers=auth(uid),
                json={**BODY, "amount": amount, "remark": remark})
            assert result.status_code == 200, result.text
            aid = result.json()["id"]
            if amount == 200:
                result = await client.request("DELETE", f"/api/v1/employee-advances/{aid}", headers=auth(1),
                    json={"void_reason": "历史示例：登记有误"})
                assert result.status_code == 200
            elif amount == 400:
                async with factory() as db:
                    advance = await db.get(EmployeeAdvance, aid)
                    advance.status, advance.deducted_amount = "deducted", 400
                    await db.commit()
        print(f"Isolated void fixture ready: {folder / 'round2.db'}", flush=True)
        await uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=18080, log_level="warning")).serve()
    patch.undo()


asyncio.run(main())

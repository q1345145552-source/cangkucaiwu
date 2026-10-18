"""Isolated read-only UI verification dataset: normal, legacy and mixed batch days."""
import asyncio
import sys
import tempfile
from datetime import date, datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
import pytest
import uvicorn
from sqlalchemy import select, delete, event
from app.models import User, Employee, ClockInRecord, RestDay
from app.core.security import hash_password
from app.core.timezone import THAI_TZ
from app.main import app
from tests.test_round3_permissions import hr_environment
from tests.test_round2_permissions import auth, set_perms


async def main():
    patch = pytest.MonkeyPatch()
    directory = Path(tempfile.mkdtemp(prefix="makeup-display-ui-"))
    async with hr_environment(directory, patch) as (engine, factory, client):
        @event.listens_for(engine.sync_engine, "connect")
        def sqlite_functions(conn, _):
            conn.create_function("to_char", 2, lambda value, fmt: str(value)[:7] if value else None)
        await engine.dispose()
        import app.api.v1.clock_in as clock
        patch.setattr(clock, "thai_today", lambda: date(2026, 10, 18))
        async with factory() as db:
            for user in (await db.execute(select(User))).scalars():
                user.password_hash = hash_password("test-password")
            (await db.get(User, 1)).display_name = "测试管理员"
            (await db.get(User, 4)).display_name = "测试主管"
            (await db.get(Employee, 1)).status = "regular"
            await db.execute(delete(RestDay).where(RestDay.employee_id == 1))
            for session, hour in [(1, 9), (2, 12), (3, 13), (4, 18)]:
                db.add(ClockInRecord(user_id=5, warehouse_id=1, clock_date=date(2026, 10, 16), session=session, clocked_in_at=datetime(2026, 10, 16, hour, tzinfo=THAI_TZ), status="normal"))
            db.add(ClockInRecord(user_id=5, warehouse_id=1, clock_date=date(2026, 10, 17), session=1, clocked_in_at=datetime(2026, 10, 17, 9, tzinfo=THAI_TZ), status="normal", is_makeup=True, makeup_by=4, makeup_at=datetime(2026, 10, 17, 10, 15, tzinfo=THAI_TZ), makeup_reason="人工单条补卡"))
            for session, hour in [(2, 12), (3, 13)]:
                db.add(ClockInRecord(user_id=5, warehouse_id=1, clock_date=date(2026, 10, 18), session=session, clocked_in_at=datetime(2026, 10, 18, hour, tzinfo=THAI_TZ), status="normal"))
            await db.commit()
        await set_perms(factory, 4, ["考勤"])
        created = await client.post("/api/v1/clock-in/batch-makeup", headers=auth(1), json={"employee_ids": [1], "sessions": [1, 4], "date": "2026-10-18", "reason": "系统故障补卡显示验证"})
        assert created.status_code == 200 and created.json()["created_count"] == 2, created.text
        print(f"Makeup display fixture: {directory}; batch={created.json()['batch_id']}", flush=True)
        await uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=18080, log_level="warning")).serve()
    patch.undo()


asyncio.run(main())

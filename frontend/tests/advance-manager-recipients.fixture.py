"""Disposable local UI fixture; never reads production credentials or databases."""
import asyncio, sys, tempfile
from datetime import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))
import pytest, uvicorn
from sqlalchemy import event, select
from tests.test_round3_permissions import hr_environment
from app.models import User, UserWarehouse, Employee
from app.core.security import hash_password
from app.main import app

async def main():
    patch = pytest.MonkeyPatch()
    folder = Path(tempfile.mkdtemp(prefix='advance-recipients-ui-'))
    async with hr_environment(folder, patch) as (engine, factory, _):
        @event.listens_for(engine.sync_engine, 'connect')
        def sqlite_functions(conn, _):
            conn.create_function('to_char', 2, lambda value, fmt: str(value)[:7] if value else None)
        await engine.dispose()
        async with factory() as db:
            for user in (await db.execute(select(User))).scalars():
                user.password_hash = hash_password('test-password')
            db.add(User(id=7, username='enabled_supervisor', display_name='开启考勤主管', role='supervisor',
                        warehouse_id=1, password_hash=hash_password('test-password'), attendance_enabled=True))
            db.add(UserWarehouse(user_id=7, warehouse_id=1))
            await db.flush()
            db.add(Employee(id=5, warehouse_id=1, user_id=7, name='开启考勤主管', position='仓库主管',
                            status='regular', hire_date=datetime(2026,10,1), salary_template_id=1, deduction_template_id=1))
            await db.flush()
            (await db.get(User,7)).attendance_employee_id=5
            await db.commit()
        print(f'Isolated fixture ready; SQLite evidence: {folder / "round2.db"}', flush=True)
        await uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=18080, log_level='warning')).serve()
    patch.undo()
asyncio.run(main())

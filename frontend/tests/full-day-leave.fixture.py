"""Disposable local UI fixture: approved full-day leave, no production access."""
import asyncio
import sys
import tempfile
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'backend'))
import pytest
import uvicorn
from sqlalchemy import select
from app.main import app
from app.core.security import hash_password
from app.models import User, LeaveRequest, Employee, UserWarehouse, ClockInRecord
from app.api.v1 import clock_in
from tests.test_round3_permissions import hr_environment


async def main():
    patch=pytest.MonkeyPatch()
    test_date=date(2026,10,19)
    patch.setattr(clock_in,'thai_today',lambda:test_date)
    async with hr_environment(Path(tempfile.mkdtemp(prefix='full-day-leave-ui-')),patch) as (_,factory,_):
        async with factory() as db:
            for user in (await db.execute(select(User))).scalars():
                user.password_hash=hash_password('test-password')
            db.add(LeaveRequest(warehouse_id=1,employee_id=1,leave_date=test_date,status='approved',duration_type='full',reviewed_by=1,reviewed_at=datetime(2026,10,19,8)))
            db.add(User(id=7,username='clocked-labor',display_name='已有打卡测试员工',password_hash=hash_password('test-password'),role='warehouse_labor',warehouse_id=1))
            db.add(UserWarehouse(user_id=7,warehouse_id=1))
            db.add(Employee(id=3,warehouse_id=1,name='已有打卡测试员工',user_id=7,hire_date=datetime(2026,10,1)))
            db.add(ClockInRecord(user_id=7,warehouse_id=1,clock_date=test_date,session=1,clocked_in_at=datetime(2026,10,19,9),status='normal'))
            db.add(LeaveRequest(warehouse_id=1,employee_id=3,leave_date=test_date,status='pending',duration_type='full'))
            await db.commit()
        print('Full day leave isolated UI ready',flush=True)
        await uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=18080,log_level='warning')).serve()
    patch.undo()


asyncio.run(main())

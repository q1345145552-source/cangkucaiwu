"""Keep legacy monetary assertions reachable using an independent authorized recorder.
Only synthetic recording actor changes; payer 4, amount, verifier 3, approver 1 stay.
"""
from contextlib import asynccontextmanager
from app.models import User, UserWarehouse
from tests.test_round3_permissions import hr_environment as original_environment
from tests.test_cash_advances import create as original_create

@asynccontextmanager
async def hr_environment(tmp_path, monkeypatch):
    async with original_environment(tmp_path, monkeypatch) as values:
        values[2].synthetic_factory=values[1]
        yield values

async def create(client, uid=1, **changes):
    if uid == 4:
        async with client.synthetic_factory() as db:
            if await db.get(User,94) is None:
                db.add(User(id=94,username='synthetic-independent-recorder',display_name='SYNTHETIC finance recorder',role='staff',warehouse_id=1,password_hash='unused',extra_permissions=['@wf-actions:1','cash_advances:operate']))
                await db.flush()
                db.add(UserWarehouse(user_id=94,warehouse_id=1))
                await db.commit()
        changes.setdefault('payer_id',4)
        uid=94
    return await original_create(client,uid,**changes)

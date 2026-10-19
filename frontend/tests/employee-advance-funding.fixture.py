"""预支资金来源的本地界面验收库；固定测试密码，不连接生产。"""
import asyncio
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))
import pytest
import uvicorn
from sqlalchemy import select
from app.main import app
from app.models import User
from app.core.security import hash_password
from tests.test_employee_advance_funding import environment, state, ledger
from tests.test_employee_advance_expense import supervisor_self


async def main():
    patch = pytest.MonkeyPatch()
    folder = Path(tempfile.mkdtemp(prefix='advance-funding-ui-'))
    async with environment(folder, patch) as (_, factory, client):
        await supervisor_self(factory)
        async with factory() as db:
            for user in (await db.execute(select(User))).scalars():
                user.password_hash = hash_password('test-password')
            await db.commit()
        before = {**await state(factory), 'ledger_count': (await ledger(client))['total'], 'database': str(folder/'round2.db')}
        Path('/tmp/advance-funding-ui-proof.json').write_text(json.dumps({'before': before}, ensure_ascii=False, indent=2))
        print('Isolated advance funding UI ready', before, flush=True)
        await uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=18080, log_level='warning')).serve()
    patch.undo()


asyncio.run(main())

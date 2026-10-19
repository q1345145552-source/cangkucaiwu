"""Round 15 browser fixture: disposable local database, no production connection."""
import asyncio
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))
import pytest
import uvicorn
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from app.main import app
from app.models import User
from app.core.security import hash_password
from app.services import reimbursement_payment as payments
from tests.test_cash_advance_references import seed
from tests.test_reimbursement_payments import environment


async def main():
    patch = pytest.MonkeyPatch()
    folder = Path(tempfile.mkdtemp(prefix='cash-reference-ui-'))
    async with environment(folder, patch) as (_, factory, client):
        ids = await seed(factory, client)
        async with factory() as db:
            for user in (await db.execute(select(User))).scalars():
                user.password_hash = hash_password('test-password')
            await db.commit()
        Path('/tmp/cash-reference-ui-proof.json').write_text(json.dumps(ids))
        Path('/tmp/cash-reference-ui-db').write_text(str(folder / 'round2.db'))
        app.mount('/uploads', StaticFiles(directory=payments.UPLOAD_DIR), name='cash-reference-test-uploads')
        print('Isolated reverse-reference UI ready', ids, folder, flush=True)
        await uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=18080, log_level='warning')).serve()
    patch.undo()


asyncio.run(main())

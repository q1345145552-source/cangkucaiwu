"""本机管理员/主管开销编辑作废验收，含一条不应被改变的旧已通过开销。"""
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
from datetime import datetime
folder=Path(tempfile.mkdtemp(prefix="fund-controls-ui-"))
uploads=folder/"fund-uploads";uploads.mkdir()
os.environ["UPLOAD_DIR"]=str(uploads)
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"backend"))
import pytest
import uvicorn
from sqlalchemy import select
from app.main import app
from app.models import User, ExpenseFundItem
from app.core.security import hash_password
from tests.test_fund_disbursement import environment, topup, spend
from tests.test_cash_advances import finance_snapshot


async def main():
    patch=pytest.MonkeyPatch()
    async with environment(folder,patch) as (_,factory,client,fid):
        assert (await topup(client,fid,amount=12000)).status_code==200
        assert (await spend(client,fid,amount=2000)).status_code==200
        async with factory() as db:
            for u in (await db.execute(select(User))).scalars():u.password_hash=hash_password("test-password")
            (await db.get(User,1)).display_name="测试老板"
            (await db.get(User,4)).display_name="测试主管"
            db.add(ExpenseFundItem(fund_id=fid,expense_date=datetime(2026,9,1),category="旧耗材",amount=2000,
                description="历史已通过开销，不得更改",receipt=None,review_status="approved",cost_record_only=False))
            await db.commit()
        Path('/tmp/fund-controls-ui-db').write_text(str(folder/'round2.db'))
        Path('/tmp/fund-controls-ui-before.json').write_text(json.dumps(await finance_snapshot(factory),default=str,ensure_ascii=False))
        print('Isolated fund item control UI ready',folder,flush=True)
        await uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=18080,log_level='warning')).serve()
    patch.undo()


asyncio.run(main())

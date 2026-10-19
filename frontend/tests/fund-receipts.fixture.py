"""本机临时验收库：保留三条旧无图开销，验证新开销必须先上传。"""
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
from datetime import datetime
folder=Path(tempfile.mkdtemp(prefix="fund-receipts-ui-"))
uploads=folder/"fund-uploads";uploads.mkdir()
os.environ["UPLOAD_DIR"]=str(uploads)
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"backend"))
import pytest
import uvicorn
from sqlalchemy import select
from PIL import Image, ImageDraw
from app.main import app
from app.models import User, ExpenseFundItem
from app.core.security import hash_password
from tests.test_fund_disbursement import environment, topup
from tests.test_cash_advances import finance_snapshot


async def main():
    patch=pytest.MonkeyPatch()
    async with environment(folder,patch) as (_,factory,client,fid):
        # 仅预置拨付及历史测试记录，待验收的新开销在浏览器中创建。
        assert (await topup(client,fid)).status_code==200
        async with factory() as db:
            for u in (await db.execute(select(User))).scalars():u.password_hash=hash_password("test-password")
            (await db.get(User,1)).display_name="测试老板"
            (await db.get(User,4)).display_name="测试主管"
            for status in ("pending","approved","rejected"):
                db.add(ExpenseFundItem(fund_id=fid,expense_date=datetime(2026,9,1),category="旧耗材",amount=123,
                    description="历史无凭证，保持原记录",receipt=None,review_status=status,cost_record_only=False))
            await db.commit()
        Path('/tmp/fund-receipts-ui-db').write_text(str(folder/'round2.db'))
        Path('/tmp/fund-receipts-ui-before.json').write_text(json.dumps(await finance_snapshot(factory),default=str,ensure_ascii=False))
        image=Image.new('RGB',(600,800),'white');draw=ImageDraw.Draw(image)
        draw.rectangle((20,20,580,780),outline='black',width=3)
        draw.text((50,70),'TEST EXPENSE RECEIPT\n\n2026-10-19\n\nPacking materials\n\n2,000 THB\n\nIsolated test data',fill='black',font_size=28)
        image.save('/tmp/fund-receipt-test.png')
        print('Isolated receipt UI ready',folder,flush=True)
        await uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=18080,log_level='warning')).serve()
    patch.undo()


asyncio.run(main())

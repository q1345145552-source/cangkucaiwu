import sys,os,asyncio,json,tempfile
from pathlib import Path
sys.path.insert(0,'/tmp/balance-warning-20261028/backend')
os.environ['SECRET_KEY']='isolated-balance-warning-test'
from pytest import MonkeyPatch
from tests.test_fund_disbursement import environment
from tests.test_round2_permissions import auth
from app.models import PaymentAccount,User
from app.main import app
import uvicorn
async def run():
 root=Path(tempfile.mkdtemp(prefix='balance-warning-browser-data-'))
 with MonkeyPatch.context() as mp:
  async with environment(root,mp) as (_,f,c,fid):
   async with f() as db:
    (await db.get(PaymentAccount,1)).opening_balance=-1000
    (await db.get(User,4)).extra_permissions=['备用金管理','员工预支','报销管理']
    await db.commit()
   Path('/tmp/balance-warning-browser-auth.json').write_text(json.dumps({'admin':auth(1),'staff':auth(4),'fund_id':fid}))
   await uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=19150,log_level='warning')).serve()
asyncio.run(run())

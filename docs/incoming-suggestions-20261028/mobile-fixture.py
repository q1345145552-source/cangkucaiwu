import sys,os,asyncio,tempfile,json
from pathlib import Path
sys.path.insert(0,'/tmp/incoming-match-suggestions-20261028/backend')
os.environ['SECRET_KEY']='isolated-incoming-test'
os.environ['INCOMING_TEST_DATABASE_URL']='postgresql+asyncpg://supplier_import@127.0.0.1:61135/postgres'
from pytest import MonkeyPatch
from tests.test_incoming_operations import environment
from tests.test_incoming_suggestions import seed
from tests.test_round2_permissions import auth
from app.main import app
import uvicorn
async def run():
 with MonkeyPatch.context() as mp:
  async with environment(Path(tempfile.mkdtemp(prefix='incoming-suggestion-mobile-')),mp) as (_,f,c):
   await seed(f)
   Path('/tmp/incoming-suggestions-browser-auth.json').write_text(json.dumps({'admin':auth(1),'staff':auth(3)}))
   await uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=19210,log_level='warning')).serve()
asyncio.run(run())

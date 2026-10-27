"""Run inherited real-route targets in an independent local cluster; preserve old evidence."""
import os,sys,runpy,asyncio
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
assert Path.cwd()==Path('/private/tmp/permissions-round5-env') and not Path('.env').exists()
name=sys.argv[1];assert name in ('round4','round3','round2','partial')
folder=ROOT/'backend/tests'/('permission_round2' if name=='partial' else 'permission_'+name)
sys.path.insert(0,str(folder))
var='ROUND2_DATABASE_URL' if name=='partial' else name.upper()+'_DATABASE_URL'
os.environ[var]='postgresql+asyncpg://round5@127.0.0.1:65489/'+('round2' if name=='partial' else name)
out=ROOT/'docs/permissions-round5-20261028'/'prior'/os.environ.get('ROUND5_RUN',name);out.mkdir(parents=True,exist_ok=True)
if name=='round4':
 import extra_scenarios
 from fix01_media import scenarios
 original=extra_scenarios.scenarios
 async def extended(factory,client,call,log,fail):
  await original(factory,client,call,log,fail)
  await scenarios(factory,client,log,out)
 extra_scenarios.scenarios=extended
filename='partial_acceptance.py' if name=='partial' else 'run_acceptance.py' if name=='round2' else 'acceptance.py'
g=runpy.run_path(str(folder/filename));g['main'].__globals__['OUT']=out
asyncio.run(g['main']())

"""Execute original prior targets against r04 source; write only new r04 evidence."""
import asyncio,json,os,runpy,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];OUT=ROOT/'docs/permissions-round4-20261028'
assert Path.cwd()==Path('/private/tmp/permissions-round4-env') and not Path('.env').exists()
name=sys.argv[1];assert name in ('round3','round2','partial')
folder=ROOT/'backend/tests'/('permission_round3' if name=='round3' else 'permission_round2')
script='acceptance.py' if name=='round3' else 'run_acceptance.py' if name=='round2' else 'partial_acceptance.py'
var='ROUND3_DATABASE_URL' if name=='round3' else 'ROUND2_DATABASE_URL'
os.environ[var]='postgresql+asyncpg://round4@127.0.0.1:65389/'+('round3' if name=='round3' else 'round2')
sys.path.insert(0,str(folder));sys.path.insert(0,str(ROOT/'backend'))
g=runpy.run_path(str(folder/script));dest=OUT/(name+'-final');dest.mkdir(exist_ok=True)
g['main'].__globals__['OUT']=dest
asyncio.run(g['main']())

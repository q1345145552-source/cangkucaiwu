"""Local-only fix01 evidence runner; preserves every original round-three artifact."""
import asyncio,json,os,runpy,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'docs/permissions-r03-fix01-20261028'
name=sys.argv[1]
assert Path.cwd()==Path('/private/tmp/permissions-r03-fix01-env')
assert not Path('.env').exists()
if name=='round3':
    folder=ROOT/'backend/tests/permission_round3';script='acceptance.py'
    os.environ['ROUND3_DATABASE_URL']='postgresql+asyncpg://round3@127.0.0.1:65379/round3'
else:
    assert name in ('round2','partial')
    folder=ROOT/'backend/tests/permission_round2';script='run_acceptance.py' if name=='round2' else 'partial_acceptance.py'
    os.environ['ROUND2_DATABASE_URL']='postgresql+asyncpg://round3@127.0.0.1:65379/round2'
sys.path.insert(0,str(folder));sys.path.insert(0,str(ROOT/'backend'))
g=runpy.run_path(str(folder/script));dest=OUT/name;dest.mkdir(exist_ok=True)
g['main'].__globals__['OUT']=dest
asyncio.run(g['main']())

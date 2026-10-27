import os,sys,runpy,asyncio
from pathlib import Path
root=Path('/private/tmp/permissions-round3-20261028')
sys.path.insert(0,str(root/'backend/tests/permission_round2'))
os.environ['ROUND2_DATABASE_URL']='postgresql+asyncpg://round3@127.0.0.1:65369/round2'
name=sys.argv[1]
g=runpy.run_path(str(root/'backend/tests/permission_round2'/name))
out=root/'docs/permissions-round3-20261028'/(name.replace('.py',''))
out.mkdir(exist_ok=True)
g['main'].__globals__['OUT']=out
asyncio.run(g['main']())

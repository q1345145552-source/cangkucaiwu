"""Preserve original evidence; rerun targets plus fixed media regression locally."""
import asyncio, os, runpy, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT/'docs/permissions-r04-fix01-20261028'
assert Path.cwd() == Path('/private/tmp/permissions-round4-env') and not Path('.env').exists()
name = sys.argv[1]
assert name in ('round4','round3','round2','partial')
if name == 'round4':
    os.environ['ROUND4_DATABASE_URL'] = 'postgresql+asyncpg://round4@127.0.0.1:65389/round4'
    import extra_scenarios
    from fix01_media import scenarios
    original = extra_scenarios.scenarios
    async def extended(factory,client,call,log,fail):
        await original(factory,client,call,log,fail)
        await scenarios(factory,client,log,OUT)
    extra_scenarios.scenarios = extended
    path = ROOT/'backend/tests/permission_round4/acceptance.py'
else:
    folder=ROOT/'backend/tests'/('permission_round3' if name=='round3' else 'permission_round2')
    sys.path.insert(0,str(folder))
    var='ROUND3_DATABASE_URL' if name=='round3' else 'ROUND2_DATABASE_URL'
    os.environ[var]='postgresql+asyncpg://round4@127.0.0.1:65389/'+('round3' if name=='round3' else 'round2')
    path=folder/('acceptance.py' if name=='round3' else 'run_acceptance.py' if name=='round2' else 'partial_acceptance.py')
g=runpy.run_path(str(path));dest=OUT/name;dest.mkdir(exist_ok=True)
g['main'].__globals__['OUT']=dest
asyncio.run(g['main']())

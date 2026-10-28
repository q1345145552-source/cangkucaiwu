import os,sys,time,json,subprocess
from pathlib import Path
name,*cmd=sys.argv[1:];base=Path('/tmp/balance-warning-20261028/docs/balance-warning-20261028');env=os.environ.copy()
env.update(INCOMING_TEST_DATABASE_URL='postgresql+asyncpg://supplier_import@127.0.0.1:61135/postgres',PYTHONPATH='/tmp/balance-warning-20261028/backend',SECRET_KEY='isolated-balance-warning-test',PYTHONDONTWRITEBYTECODE='1',NEXT_TELEMETRY_DISABLED='1',NODE_PATH='/tmp/excel-import-review-ui/node_modules')
env['PATH']='/Users/xiongliu/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:'+env['PATH'];start=time.time()
with (base/(name+'.log')).open('w') as out:r=subprocess.run(cmd,env=env,stdout=out,stderr=subprocess.STDOUT)
with (base/'commands.jsonl').open('a') as out:out.write(json.dumps({'name':name,'command':cmd,'cwd':os.getcwd(),'exit_code':r.returncode,'seconds':round(time.time()-start,2)})+'\n')
print(name,r.returncode);print((base/(name+'.log')).read_text()[-3000:]);sys.exit(r.returncode)

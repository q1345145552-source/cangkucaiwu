import os,sys,time,json,subprocess
from pathlib import Path
name,*cmd=sys.argv[1:]
base=Path('/Users/xiongliu/Desktop/海外仓财务系统/docs/excel-import-20261027');env=os.environ.copy()
env.update(INCOMING_TEST_DATABASE_URL='postgresql+asyncpg://supplier_import@127.0.0.1:61135/postgres',SECRET_KEY='isolated-excel-import-synthetic-secret',PYTHONPATH='/Users/xiongliu/Desktop/海外仓财务系统/backend',PYTHONDONTWRITEBYTECODE='1',NEXT_TELEMETRY_DISABLED='1',NODE_PATH='/tmp/excel-import-20261027-ui/node_modules')
env['PATH']='/Users/xiongliu/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:'+env['PATH']
start=time.time()
with (base/(name+'.log')).open('w') as log:r=subprocess.run(cmd,env=env,stdout=log,stderr=subprocess.STDOUT)
with (base/'commands.jsonl').open('a') as log:log.write(json.dumps({'name':name,'command':cmd,'cwd':os.getcwd(),'exit_code':r.returncode,'seconds':round(time.time()-start,2),'log':str(base/(name+'.log'))},ensure_ascii=False)+'\n')
print(name,r.returncode);print((base/(name+'.log')).read_text()[-3500:]);sys.exit(r.returncode)

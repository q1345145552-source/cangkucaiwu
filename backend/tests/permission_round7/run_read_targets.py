"""Serial dependent fixture runs; preserve each original assertion and all failures."""
from pathlib import Path
import os,sys,subprocess,json
root=Path(__file__).resolve().parents[3];logs=root/'docs/permissions-round7-20261028/raw-logs'
for version in ('versioned','legacy'):
 for suite in ('acceptance','attachment_acceptance','write_responses','history_fields'):
  name='reads-'+suite+'-'+version+'-01';target=logs/(name+'.log');assert not target.exists()
  cmd=[sys.executable,str(root/'backend/tests/permission_round7/prior_round5.py'),suite,version]
  env={**os.environ,'ROUND7_DATABASE_URL':'postgresql+asyncpg://round7@127.0.0.1:65519/round7','ROUND7_RUN':name}
  (logs/(name+'.command.json')).write_text(json.dumps({'cmd':cmd,'cwd':'/private/tmp/permissions-round7-env','mode':version}))
  with target.open('w') as f:r=subprocess.run(cmd,cwd='/private/tmp/permissions-round7-env',env=env,stdout=f,stderr=subprocess.STDOUT)
  (logs/(name+'.exit')).write_text(str(r.returncode));print(name,r.returncode,flush=True)
  if r.returncode:sys.exit(r.returncode)

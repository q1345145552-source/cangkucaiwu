"""Run every discovered backend test against isolated fixtures, preserving exact baseline."""
from pathlib import Path
import sys,subprocess,os,json,hashlib
def source_hashes(source):
 paths=list((source/'backend').rglob('*.py'))+list((source/'backend/app/core').glob('*.json'))
 paths+=list((source/'frontend/src').rglob('*'))
 paths += [source/'frontend'/n for n in ('package.json','package-lock.json','tsconfig.json','next.config.js','next.config.ts') if (source/'frontend'/n).is_file()]
 return {str(p.relative_to(source)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths) if p.is_file() and '__pycache__' not in p.parts}
ROOT=Path(__file__).resolve().parents[3];OUT=ROOT/'docs/permissions-round7-20261028/raw-logs'
label=sys.argv[1]; assert label in ('baseline','current')
suffix=next((x.split('=',1)[1] for x in sys.argv[2:] if x.startswith('--run=')), '')
assert not suffix or (suffix.isalnum() and label=='current')
name='full-'+label+('-'+suffix if suffix else '')+('-collect' if '--collect' in sys.argv else '')
source=Path('/private/tmp/permissions-round7-baseline-20261028') if label=='baseline' else ROOT
assert not (source/'.env').exists() and not (source/'backend/.env').exists()
url='postgresql+asyncpg://round7@127.0.0.1:65519/'+('round7baseline' if label=='baseline' else 'round7regression')
env={**os.environ,'DATABASE_URL':url,'INCOMING_TEST_DATABASE_URL':url,'SECRET_KEY':'synthetic-round7-only-signing-key-not-production','DEEPSEEK_API_KEY':'','LINE_CHANNEL_ACCESS_TOKEN':'','LINE_CHANNEL_SECRET':'','PYTHONPATH':'/private/tmp/permissions-round7-env/guard:'+str(source/'backend'),'PGLITE_NODE':'/Users/xiongliu/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node','NODE_PATH':'/private/tmp/import-integration-pglite/node_modules','UPLOAD_DIR':'/private/tmp/permissions-round7-env/uploads-'+label}
cmd=[sys.executable,'-m','pytest','--tb=short','-rA','--junitxml='+str(OUT/(name+'.xml'))]
if label=='current':
 env['ROUND7_ROUTE_TRACE']=str(OUT/(name+'-routes.jsonl.gz'))
 cmd.extend(['-p','tests.permission_round7.trace_routes'])
if '--collect' in sys.argv:cmd=[sys.executable,'-m','pytest','--collect-only','-q']
assert not (OUT/(name+'.log')).exists(),'Do not overwrite evidence'
(OUT/(name+'.command.json')).write_text(json.dumps({'command':cmd,'cwd':str(source/'backend'),'database':url,'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=source,text=True).strip(),'network_guard':'local_guard.py via sitecustomize; no role/auth substitute'},indent=2))
if label=='current':
 frozen=source_hashes(source)
 (OUT/(name+'.source-hashes.json')).write_text(json.dumps(frozen,indent=2))
with (OUT/(name+'.log')).open('w') as log:r=subprocess.run(cmd,cwd=source/'backend',env=env,stdout=log,stderr=subprocess.STDOUT)
if label=='current':
 after=source_hashes(source);changed=[p for p in sorted(set(frozen)|set(after)) if frozen.get(p)!=after.get(p)]
 (OUT/(name+'.freeze-check.json')).write_text(json.dumps({'changed':changed,'matched':not changed,'files':len(frozen)},indent=2))
 if changed:raise RuntimeError('Sources changed during suite: '+str(changed))
(OUT/(name+'.exit')).write_text(str(r.returncode));print(name,r.returncode);sys.exit(r.returncode)

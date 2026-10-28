"""Execute every collected test exactly once, grouped by file in four isolated pytest processes."""
from pathlib import Path
import os,sys,json,subprocess,hashlib,concurrent.futures,xml.etree.ElementTree as ET,gzip,shutil
ROOT=Path('/private/tmp/permissions-round7-20261028');OUT=ROOT/'docs/permissions-round7-20261028/raw-logs'
name=sys.argv[1];assert name.startswith('full-current-final') and name.replace('-','').isalnum()
assert not (OUT/(name+'.xml')).exists()
def hashes():
 paths=list((ROOT/'backend').rglob('*.py'))+list((ROOT/'backend/app/core').glob('*.json'))+list((ROOT/'frontend/src').rglob('*'))
 paths += [ROOT/'frontend'/n for n in ('package.json','package-lock.json','tsconfig.json','next.config.js','next.config.ts') if (ROOT/'frontend'/n).is_file()]
 return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths) if p.is_file() and '__pycache__' not in p.parts}
frozen=hashes();(OUT/(name+'.source-hashes.json')).write_text(json.dumps(frozen,indent=2))
url='postgresql+asyncpg://round7@127.0.0.1:65519/round7regression'
env={**os.environ,'DATABASE_URL':url,'INCOMING_TEST_DATABASE_URL':url,'SECRET_KEY':'synthetic-round7-only-signing-key-not-production','DEEPSEEK_API_KEY':'','LINE_CHANNEL_ACCESS_TOKEN':'','LINE_CHANNEL_SECRET':'','PYTHONPATH':'/private/tmp/permissions-round7-env/guard:'+str(ROOT/'backend'),'PGLITE_NODE':'/Users/xiongliu/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node','NODE_PATH':'/private/tmp/import-integration-pglite/node_modules','UPLOAD_DIR':'/private/tmp/permissions-round7-env/uploads-current'}
collect=subprocess.run([sys.executable,'-m','pytest','--collect-only','-q','-o','addopts='],cwd=ROOT/'backend',env=env,capture_output=True,text=True)
(OUT/(name+'-collect.log')).write_text(collect.stdout+collect.stderr);assert collect.returncode==0
nodes=[x for x in collect.stdout.splitlines() if x.startswith('tests/') and '::' in x];assert len(nodes)==len(set(nodes)) and len(nodes)>2900
files=sorted({n.split('::',1)[0] for n in nodes});weights={}
for t in ET.parse(OUT/'full-baseline.xml').iter('testcase'):
 key=t.get('classname','').replace('.','/')+'.py';weights[key]=weights.get(key,0)+float(t.get('time','0'))
groups=[[] for _ in range(4)];loads=[0.0]*4
for p in sorted(files,key=lambda x:weights.get(x,1),reverse=True):
 i=min(range(4),key=loads.__getitem__);groups[i].append(p);loads[i]+=weights.get(p,1)
(OUT/(name+'.command.json')).write_text(json.dumps({'cwd':str(ROOT/'backend'),'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'database':url,'collected':len(nodes),'files':files,'groups':groups,'estimated_seconds':loads,'network_guard':'sitecustomize local_guard; no authentication substitute','isolation':'Each legacy fixture creates UUID schema or temporary SQLite; PGlite child processes independent; no file split across pytest processes.'},indent=2))
(OUT/(name+'-collected.json')).write_text(json.dumps(nodes,indent=2))
def run(i):
 label=name+'-shard'+str(i+1)
 dbname='round7regression'+str(i+1)
 subprocess.run(['/private/tmp/supplier01-pgserver/pgserver/pginstall/bin/createdb','-h','127.0.0.1','-p','65519','-U','round7',dbname],check=True,capture_output=True,text=True)
 shard_url='postgresql+asyncpg://round7@127.0.0.1:65519/'+dbname
 e={**env,'DATABASE_URL':shard_url,'INCOMING_TEST_DATABASE_URL':shard_url,'UPLOAD_DIR':'/private/tmp/permissions-round7-env/uploads-'+label,'ROUND7_ROUTE_TRACE':str(OUT/(label+'-routes.jsonl.gz'))}
 (OUT/(label+'.environment.json')).write_text(json.dumps({'database':shard_url,'uploads':e['UPLOAD_DIR']}))
 cmd=[sys.executable,'-m','pytest',*groups[i],'--tb=short','-rA','--junitxml='+str(OUT/(label+'.xml')),'-p','tests.permission_round7.trace_routes']
 (OUT/(label+'.command.json')).write_text(json.dumps(cmd))
 with (OUT/(label+'.log')).open('w') as f:r=subprocess.run(cmd,cwd=ROOT/'backend',env=e,stdout=f,stderr=subprocess.STDOUT)
 (OUT/(label+'.exit')).write_text(str(r.returncode));print(label,r.returncode,flush=True);return r.returncode
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:codes=list(pool.map(run,range(4)))
root=ET.Element('testsuites');actual=[]
with (OUT/(name+'.log')).open('w') as log,(OUT/(name+'-routes.jsonl.gz')).open('wb') as trace:
 for i in range(4):
  label=name+'-shard'+str(i+1);data=ET.parse(OUT/(label+'.xml')).getroot()
  for s in data:root.append(s)
  for t in data.iter('testcase'):actual.append(t.get('classname','').replace('.','/')+'.py::'+t.get('name',''))
  log.write('\n'+label+'\n'+(OUT/(label+'.log')).read_text())
  with (OUT/(label+'-routes.jsonl.gz')).open('rb') as f:shutil.copyfileobj(f,trace)
ET.ElementTree(root).write(OUT/(name+'.xml'),encoding='utf-8',xml_declaration=True)
assert sorted(actual)==sorted(nodes),(len(actual),len(nodes),set(nodes)-set(actual),set(actual)-set(nodes))
after=hashes();changed=[p for p in sorted(set(frozen)|set(after)) if frozen.get(p)!=after.get(p)]
(OUT/(name+'.freeze-check.json')).write_text(json.dumps({'matched':not changed,'changed':changed,'files':len(frozen),'collected':len(nodes),'executed':len(actual),'unique_executed':len(set(actual))},indent=2))
assert not changed,changed
code=max(codes);(OUT/(name+'.exit')).write_text(str(code));print(name,code,flush=True);sys.exit(code)

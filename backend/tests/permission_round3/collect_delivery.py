"""Collect local-only evidence and route coverage; never converts a failed test to passed."""
from pathlib import Path
import json,re,hashlib,subprocess,shutil,ast
ROOT=Path(__file__).resolve().parents[3];OUT=ROOT/'docs/permissions-round3-20261028';ENV=Path('/private/tmp/permissions-round3-env')
raw=OUT/'raw-logs';raw.mkdir(exist_ok=True)
for p in (ENV/'logs').iterdir():
 if p.is_file():shutil.copy2(p,raw/p.name)
routes=json.loads((OUT/'registered-actions.json').read_text());calls=[]
for directory,name in [('', 'requests.json'),('run_acceptance','target-requests.json'),('partial_acceptance','requests.json')]:
 for r in json.loads((OUT/directory/name).read_text()):
  if 'requests' in r:
   for i,item in enumerate(r['requests']):calls.append({'id':r['id']+f'[{i}]','method':item[1],'path':item[2],'source':str(Path(directory)/name)})
  elif 'path' in r:calls.append({'id':r['id'],'method':r.get('method','POST'),'path':r['path'],'source':str(Path(directory)/name)})
for r in routes:r['actual_test_ids']=[]
for c in calls:
 path='/api/v1'+c['path'].split('?')[0]
 matches=[r for r in routes if c['method'] in r['methods'] and re.fullmatch(re.sub(r'\{[^}]+\}','[^/]+',r['path']),path)]
 if matches:
  chosen=sorted(matches,key=lambda r:(r['path'].count('{'),-len(r['path'])))[0];chosen['actual_test_ids'].append(c['source']+':'+c['id'])
coverage={'registered_actions':len(routes),'direct_http_covered':sum(bool(r['actual_test_ids']) for r in routes),'not_directly_exercised':[{'method':r['methods'],'path':r['path'],'handler':r['handler'],'scope':'静态盘查；页面GET可能覆盖，未算目标HTTP验收'} for r in routes if not r['actual_test_ids']],'actions':routes}
(OUT/'coverage.json').write_text(json.dumps(coverage,ensure_ascii=False,indent=2))
changed=subprocess.check_output(['git','diff','--name-only','e6cc888187d8ecf21abe56118565879edc4c0312'],cwd=ROOT,text=True).splitlines()
changed=[p for p in changed if p.startswith(('backend/','frontend/'))]
changed += ['backend/app/services/financial_authorization.py','frontend/src/components/FinancialIdentityBoundary.tsx']
hashes={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in changed if (ROOT/p).is_file()}
manifest={'marker':'permissions7-r03-resume01-20261028','worktree':str(ROOT),'branch':subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip(),'baseline':'e6cc888187d8ecf21abe56118565879edc4c0312','environment':str(ENV),'database':'127.0.0.1:65369 synthetic round3, round2, r3regression, r3baseline','local_services_stopped':(ENV/'logs/shutdown.exit').read_text().strip()=='0','auth':'actual JWT/get_current_user; only synthetic signing key; no permissive auth substitute','lifespan':'off for browser server; startup tasks not run','exit_codes':{p.stem:p.read_text().strip() for p in raw.glob('*.exit')},'target':json.loads((OUT/'status.json').read_text()),'round2_original':json.loads((OUT/'run_acceptance/target-status.json').read_text()),'round2_partial':json.loads((OUT/'partial_acceptance/status.json').read_text()),'browser':json.loads((OUT/'browser-results.json').read_text()),'source_sha256':hashes,'boundaries':{'production_access':False,'real_data':False,'push_fetch_deploy_ssh':False,'credentials_read':False,'models_changed':False,'migration':False,'inventory_valuation_changed':False,'other_chat_dispatch':False,'automations':False},'commands':['ROUND3_DATABASE_URL=postgresql+asyncpg://round3@127.0.0.1:65369/round3 python backend/tests/permission_round3/acceptance.py (absolute path; cwd isolated environment)','python run_round2_regression.py run_acceptance.py / partial_acceptance.py (separate round2 DB; output redirected to round3 docs)','related pytest commands and cwd are recorded in raw-logs/regression-*-02.command.json; final guards in guard-regression-final.log/xml','node frontend/node_modules/typescript/bin/tsc --noEmit --project frontend/tsconfig.json','node node_modules/next/dist/bin/next build (isolated frontend cwd, PATH local runtime)','node backend/tests/permission_round3/browser_acceptance.cjs','python -m compileall -q backend/app backend/tests/permission_round3','git diff --check']}
(OUT/'validation-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
print('coverage',coverage['direct_http_covered'],'/',len(routes))

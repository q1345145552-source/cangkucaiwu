"""Capture fix01 actual observations; failures are retained and never reclassified by name alone."""
import hashlib,json,shutil,subprocess
from pathlib import Path
from xml.etree import ElementTree as E
ROOT=Path(__file__).resolve().parents[3];OUT=ROOT/'docs/permissions-r03-fix01-20261028';LOG=Path('/private/tmp/permissions-r03-fix01-env/logs')
def git(*args,cwd=ROOT):return subprocess.check_output(['git',*args],cwd=cwd,text=True).strip()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def cases(p):
 r=E.parse(p).getroot();data={}
 for t in r.iter('testcase'):
  f=t.find('failure');err=t.find('error');skip=t.find('skipped')
  data[t.attrib['classname']+'::'+t.attrib['name']]={'result':'failure' if f is not None else 'error' if err is not None else 'skipped' if skip is not None else 'passed','failure':f.attrib['message'] if f is not None else '', 'trace':f.text if f is not None else ''}
 return {'suite':r[0].attrib,'cases':data}
for p in LOG.iterdir():
 if p.is_file():shutil.copy2(p,OUT/'raw-logs'/p.name)
current=cases(LOG/'regression-final.xml');base1=cases(LOG/'baseline-money-01.xml');base2=cases(LOG/'baseline-money-02.xml')
failures=[]
for test,value in current['cases'].items():
 if value['result']!='failure':continue
 key=test.replace('[3]','[1]') if 'disburse_reverse_reissue_and_reports' in test else test
 assert key in base2['cases'],key
 failures.append({'test':test,'current':value,'baseline_first_actual_assertion':base1['cases'].get(key),'baseline_later_assertions':base2['cases'][key], 'classification':'旧金额/成本或显示断言与基线同一实质差异；具体断言及后续失败保留，不宣称全部通过'})
(OUT/'failure-comparison.json').write_text(json.dumps({'baseline':'e6cc888187d8ecf21abe56118565879edc4c0312','adapter':'raw-logs/baseline-workflow-adapter.diff','baseline_helper':'raw-logs/baseline-round3_flow_support.py.txt','current_summary':current['suite'],'baseline_first_summary':base1['suite'],'baseline_second_summary':base2['suite'],'failures':failures},ensure_ascii=False,indent=2))
base=Path('/private/tmp/permissions-r03-fix01-baseline')
shutil.copy2(base/'backend/tests/round3_flow_support.py',OUT/'raw-logs/baseline-round3_flow_support.py.txt')
prior=json.loads((ROOT/'docs/permissions-round3-20261028/validation-manifest.json').read_text())
source={p:sha(ROOT/p) for p in prior['source_sha256']};assert source==prior['source_sha256'],'validated business/frontend source changed'
assert not git('diff','e51b636','--name-only','--','backend/app','backend/scripts','frontend')
tracked=git('diff','--name-only').splitlines();untracked=git('ls-files','--others','--exclude-standard').splitlines()
tests={p:sha(ROOT/p) for p in tracked+untracked if p.startswith('backend/tests/') and (ROOT/p).is_file()}
reused={}
for name in ('tsc-final-02','build-final-02'):
 p=ROOT/'docs/permissions-round3-20261028/raw-logs'/f'{name}.log';exitpath=p.with_suffix('.exit')
 assert exitpath.read_text().strip()=='0'
 reused[name]={'log':str(p),'sha256':sha(p),'exit_code':0,'reuse_reason':'Business and frontend source hashes exactly match validated version; no new tsc/build run.'}
assertion_map=json.loads((OUT/'assertion-map.json').read_text())
counts={'original_tests':len(assertion_map['tests']),'assertions':0,'same_parameter_reached':0,'other_parameter_reached':0,'unreached':0};unreached=[]
for t in assertion_map['tests']:
 for a in t['assertions']:
  counts['assertions']+=1
  if any(x['reached'] for x in a['current']):counts['same_parameter_reached']+=1
  elif a['sibling_parameter_execution']:counts['other_parameter_reached']+=1
  else:counts['unreached']+=1;unreached.append({'test':t['old_test'],'old_line':a['old_line'],'assertion':a['old_assertion'],'reason':'Baseline and current cash salary has no generated expense object. The mandatory cost assertion fails; dependent expense fields/protection not verified.'})
commands={
 'regression':json.loads((LOG/'regression-final.command.json').read_text()),
 'targets':{'cwd':'/private/tmp/permissions-r03-fix01-env','argv':['/tmp/supplier01-py312/bin/python',str(ROOT/'backend/tests/permission_round3/fix01_run.py'),'<round3|round2|partial>']},
 'baseline':{'cwd':str(base),'revision':git('rev-parse','HEAD',cwd=base),'selected_tests':list(base2['cases']),'runner':'/tmp/supplier01-py312/bin/python -m pytest -q -s --tb=short <selected tests> --junitxml=<log path>','database':'synthetic localhost65379; selected baseline tests actually use their temporary SQLite fixtures'},
 'compile':'python -m compileall -q changed Python tests/collectors','diff':'git diff --check'}
manifest={'marker':'permissions7-r03-fix01-resume02-20261028','worktree':str(ROOT),'branch':git('branch','--show-current'),'reviewed_head':git('rev-parse','HEAD'),'round3_original_business':'e4d7e05b21925345cb200973e7cbc0f55f1a4675','environment':'/private/tmp/permissions-r03-fix01-env','synthetic_postgres_port':65379,'local_postgres_stopped':(LOG/'shutdown.exit').read_text().strip()=='0','exit_codes':{p.stem:int(p.read_text()) for p in LOG.glob('*.exit')},'target_round3':json.loads((OUT/'round3/status.json').read_text()),'round2_original':json.loads((OUT/'round2/target-status.json').read_text()),'round2_partial':json.loads((OUT/'partial/status.json').read_text()),'regression':current['suite'],'assertion_mapping':counts,'unverified_assertions':unreached,'source_sha256':source,'changed_test_sha256':tests,'reused_typecheck_build':reused,'commands':commands,'boundaries':{'business_code_changed':False,'frontend_changed':False,'models_or_migrations_changed':False,'inventory_cost_opening_changed':False,'auth_override_added':False,'production_access':False,'push_fetch_deploy_ssh':False,'other_chat_dispatch':False,'old_raw_evidence_modified':False}}
(OUT/'validation.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
print(json.dumps({'regression':current['suite'],'assertion_mapping':counts,'source_hashes_match':True,'stopped':manifest['local_postgres_stopped']},ensure_ascii=False))

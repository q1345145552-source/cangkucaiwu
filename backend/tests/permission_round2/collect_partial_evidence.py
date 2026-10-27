"""Collect local fix01 logs and evidence; does not start services or contact remote systems."""
from pathlib import Path
import hashlib,json,shutil,subprocess,xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'docs/permissions-r02-fix01-20261028'
ENV=Path('/private/tmp/permissions-r02-fix01-env')
BASE='11d032a41d0d39d770285ce5367ea4d15a2e8e51'
def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT,text=True).strip()
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def xml(name):
    root=ET.parse(ENV/'logs'/f'{name}.xml').getroot();cases=root.findall('.//testcase')
    failures={c.attrib['classname']+'::'+c.attrib['name']:(c.find('failure').attrib.get('message','') if c.find('failure') is not None else c.find('error').attrib.get('message','')) for c in cases if c.find('failure') is not None or c.find('error') is not None}
    return {'total':len(cases),'passed':len(cases)-len(failures)-sum(c.find('skipped') is not None for c in cases),'failed':len(failures),'skipped':sum(c.find('skipped') is not None for c in cases),'failures':failures}
a,b=xml('regression-final'),xml('baseline')
assert set(a['failures'])==set(b['failures']), 'New regression failures require investigation'
assert a['total']==b['total'] and a['skipped']==b['skipped']==0
raw=OUT/'raw-logs';raw.mkdir(exist_ok=True)
for p in (ENV/'logs').iterdir():
    if p.suffix in ('.log','.exit','.xml'):shutil.copyfile(p,raw/p.name)
(OUT/'REGRESSION.md').write_text('# 受影响回归与候选基线对照\n\n补修最终81项：68通过、13失败、0跳过。未修改候选11d032a归档同样81项/68通过/13失败，无新增失败名。\n\n没有删除、skip或修改原回归断言；源码恒等类失败仍原样保留。真实原因/堆栈以两份原始日志为准，不能以失败名相同代替完整验收。\n\n|失败项|补修实际断言/错误|候选基线实际断言/错误|\n|---|---|---|\n'+'\n'.join('|`'+k+'`|'+a['failures'][k].replace('\n',' ').replace('|','／')[:500]+'|'+b['failures'][k].replace('\n',' ').replace('|','／')[:500]+'|' for k in sorted(a['failures']))+'\n\n[补修原始日志](raw-logs/regression-final.log)、[XML](raw-logs/regression-final.xml)、[候选基线原始日志](raw-logs/baseline.log)、[XML](raw-logs/baseline.xml)。两套pytest退出码均1。\n')
changed=git('diff','--name-only',BASE).splitlines()
allowed={'backend/app/api/v1/expense_fund.py','backend/app/api/v1/reimbursement.py','backend/app/services/fund_authorization.py'}
assert all(p in allowed or p.startswith(('backend/tests/permission_round2/','docs/permissions-r02-fix01-20261028/')) for p in changed),changed
frontend_mismatch=[str(p) for p in (ROOT/'frontend/src').rglob('*') if p.is_file() and p.suffix in ('.ts','.tsx','.js','.css') and digest(p)!=digest(Path('/private/tmp/permissions-round2-env/frontend')/p.relative_to(ROOT/'frontend'))]
assert not frontend_mismatch
manifest={'marker':'permissions7-r02-fix01-20261028','baseline':BASE,'branch':git('branch','--show-current'),'worktree':str(ROOT),'environment':str(ENV),'isolated_database':'postgresql+asyncpg://round2@127.0.0.1:65349/round2','target':json.loads((OUT/'status.json').read_text()),'original_target':json.loads((OUT/'original-target/target-status.json').read_text()),'regression':a,'candidate_baseline_regression':b,'new_failure_names':sorted(set(a['failures'])-set(b['failures'])),'exit_codes':{p.stem:int(p.read_text().strip()) for p in (ENV/'logs').glob('*.exit')},'frontend_runtime_matches_source':True,'business_changes':sorted(allowed),'source_sha256':{p:digest(ROOT/p) for p in sorted(allowed)},'independent_evidence_sha256':{p:digest(Path('/private/tmp/permission-r2-review-800p5mtu')/p) for p in ('partial_probe.py','partial-probe.json','partial-probe.log')},'code_diff_check':subprocess.run(['git','diff','--check',BASE,'--','backend'],cwd=ROOT,capture_output=True).returncode,'boundaries':{'models_changed':False,'migration':False,'inventory_cost_or_opening_changed':False,'production_access':False,'read_production_credentials':False,'push_fetch_deploy_ssh':False,'other_chat_dispatch':False,'old_evidence_modified':False},'local_postgres_stopped':(ENV/'logs/shutdown.exit').exists() and (ENV/'logs/shutdown.exit').read_text().strip()=='0'}
(OUT/'validation.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'target':manifest['target'],'original_target':manifest['original_target'],'regression':{k:v for k,v in a.items() if k!='failures'},'new_failures':manifest['new_failure_names'],'exit_codes':manifest['exit_codes'],'postgres_stopped':manifest['local_postgres_stopped']},ensure_ascii=False))

"""Artifact-only evidence index. Never changes application/test source or original logs."""
from pathlib import Path
import json,gzip,re,sys,subprocess,xml.etree.ElementTree as ET,hashlib
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).parent
suite=sys.argv[1]
# Use the committed collector, adding final named replays without modifying test code.
p=ROOT/'backend/tests/permission_round7/report_evidence.py'
source=p.read_text().replace("files=[]", "folders += [x.name for x in OUT.glob('*final06*') if x.is_dir() and x.name not in ('chain-final06','chain-final06b')]\nfolders += [x.name for x in OUT.glob('*final05*') if x.is_dir() and x.name not in ('chain-final05',)]\nfiles=[]")
sys.argv=[str(p),'--suite',suite,'--label','final'];exec(compile(source,str(p),'exec'),{'__name__':'__main__','__file__':str(p)})

def cases(path):
 result={}
 if not path.exists():return result
 for t in ET.parse(path).iter('testcase'):
  k=t.get('classname','').split('tests.',1)[-1]+'.'+t.get('name','')
  failure=t.find('failure');error=t.find('error');failure=failure if failure is not None else error
  result[k]={'name':t.get('name'),'class':t.get('classname'),'state':'failed' if failure is not None else 'skipped' if t.find('skipped') is not None else 'passed','failure':failure.text if failure is not None else None,'seconds':t.get('time')}
 return result
current=cases(OUT/'raw-logs'/f'{suite}.xml');baseline=cases(OUT/'raw-logs/full-baseline.xml');adapted=cases(OUT/'raw-logs/cost-baseline-final06.xml')
failed=[]
for k,v in current.items():
 if v['state']!='failed':continue
 base=baseline.get(k);adapt=adapted.get(k)
 failed.append({**v,'exact_baseline':base,'adapted_baseline':adapt,'classification':'Requires comparison of actual failing assertions, not merely test names; no failure is a pass.'})
(OUT/'FINAL-FAILURES.json').write_text(json.dumps(failed,ensure_ascii=False,indent=2))
lines=['# 全套失败与精确基线索引','原始失败完整文本见 FINAL-FAILURES.json。适配基线使用精确0e4d2f9业务源码与相同合法合成流程，未修改原基线工作树。','', '|用例|当前|原始基线|相同合法夹具基线|','|---|---|---|---|']
for f in failed:lines.append('|'+f['class']+'::'+f['name']+'|失败|'+str((f['exact_baseline'] or {}).get('state','未收集'))+'|'+str((f['adapted_baseline'] or {}).get('state','未单独适配'))+'|')
(OUT/'FINAL-FAILURES.md').write_text('\n'.join(lines)+'\n')
manifest=[]
for p in sorted(OUT.rglob('*')):
 if not p.is_file() or p.name in ('ARTIFACT-INDEX.json','ARTIFACT-INDEX.md'):continue
 manifest.append({'path':str(p.relative_to(OUT)),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
(OUT/'ARTIFACT-INDEX.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
exits={str(p.relative_to(OUT)):p.read_text().strip() for p in sorted((OUT/'raw-logs').glob('*.exit'))}
(OUT/'EXIT-CODES.json').write_text(json.dumps(exits,indent=2))
chain=subprocess.check_output(['git','log','--first-parent','--format=%H %P %s','854e389..HEAD'],cwd=ROOT,text=True)
(OUT/'COMMIT-CHAIN.txt').write_text(chain)
print('Artifact index:',len(manifest),'files; final failed:',len(failed))

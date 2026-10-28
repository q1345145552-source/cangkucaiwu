"""Mechanical evidence index, never treats a request as exhaustive business acceptance."""
from pathlib import Path
import json,re,hashlib,subprocess,xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[3]; OUT=ROOT/'docs/permissions-round6-20261028'
def write(name,data): (OUT/name).write_text(json.dumps(data,ensure_ascii=False,indent=2))
rows=json.loads((ROOT/'backend/app/core/action_catalog.json').read_text())['routes']
request_files=[]
for folder in ['matrix-final','extended-02','final-round3-legacy','final-round3-versioned','partial-final','round4-media-final','browser-final','disabled-category','logistics-contract','round2-versioned']+[f'final-r5-{v}-{s}' for v in ['legacy','versioned'] for s in ['acceptance','attachment_acceptance','write_responses','history_fields']]:
 request_files.extend(p for p in (OUT/folder).glob('*.json') if p.name in ('requests.json','target-requests.json','media-requests.json','results.json'))
evidence=[]
for p in request_files:
 data=json.loads(p.read_text());data=data.get('requests',[]) if isinstance(data,dict) else data
 for req in data:
  if not isinstance(req,dict) or not req.get('method') or not req.get('path'):continue
  path=req['path'].split('?')[0]
  if not path.startswith(('/api/','/uploads/')):path='/api/v1'+path
  evidence.append({'file':str(p.relative_to(ROOT)),'id':req.get('id',req.get('case')),'method':req['method'],'path':path,'status':req.get('actual',req.get('actual_status',req.get('status'))),'errors':req.get('errors',[])})
gates=json.loads((OUT/'frontend-gates.json').read_text());manual=json.loads((OUT/'frontend-manual-gates.json').read_text());front={}
for g in gates:
 for e in g['entries']:
  for a in e.get('actions',[]):front.setdefault(a.split('#')[0],set()).add(g['file'])
for g in manual:
 for a in g.get('actions',[]):front.setdefault(a.split('#')[0],set()).add(g['file'])
# FastAPI resolves the first matching registered route; avoid counting a static URL
# as evidence for a later parameterized route such as /{id}.
for e in evidence:
 e['matched_action']=next((r['id'] for r in rows if e['method'] in r['methods'] and re.fullmatch('^'+re.sub(r'\{[^}]+\}',r'[^/]+',r['path'])+'$',e['path'])),None)
coverage=[]
for row in rows:
 pattern='^'+re.sub(r'\{[^}]+\}',r'[^/]+',row['path'])+'$'
 hits=[e for e in evidence if e['matched_action']==row['id']]
 coverage.append({'id':row['id'],'methods':row['methods'],'path':row['path'],'mode':row['mode'],'tier':row['tier'],'frontend_files':sorted(front.get(row['id'],[])), 'evidence':hits,'coverage':'local requests (not all role/state combinations)' if hits else 'registered central guard + source inspection only; NOT directly tested', 'positive':sum(isinstance(e['status'],int) and e['status']<400 for e in hits),'rejected':sum(isinstance(e['status'],int) and e['status']>=400 for e in hits)})
write('action-coverage.json',coverage)
old=json.loads((ROOT/'docs/permissions-round5-20261028/coverage.json').read_text())
oldgaps=[]
for gap in old['uncovered']:
 found=[c for c in coverage if c['path']==gap['path'] and set(c['methods']) & set(gap['methods'])]
 oldgaps.append({**gap,'round6':found})
write('inherited-read-gaps.json',{'source_count':len(oldgaps),'coordinator_independent_count':167,'difference':'Repository round5 coverage: 215 minus 46 =169; independent 167 includes probes absent from this repository. No invented local evidence.','routes':oldgaps})
lines=['# 第六轮动作目录与证据','每行对应真实注册路由；完整输入、状态条件源码、关联服务和字段政策见 backend/app/core/action_catalog.json。角色名单是上限，不替代对象、仓库、状态和本人限制。未出现页面文件的动作由最小办理页或原上下文入口提供，未逐个浏览器验证。','', '|动作ID|模块/类别|方法与路径|角色上限|页面入口静态映射|本地请求/成功/拒绝|','|---|---|---|---|---|---|']
for row,c in zip(rows,coverage):
 roles='/'.join(row['roles']);variants=row.get('variants')
 if variants:roles=json.dumps(variants,ensure_ascii=False)
 lines.append('|'+ '|'.join([row['id'],row['module_key']+'/'+row['tier']+'/'+row['mode'],','.join(row['methods'])+' '+row['path'],roles,'<br>'.join(c['frontend_files']) or '最小办理/原上下文（未逐入口实测）',f"{len(c['evidence'])}/{c['positive']}/{c['rejected']}"])+'|')
(OUT/'ACTION-MATRIX.md').write_text('\n'.join(lines)+'\n')
comparisons=[]
for group in ['prior','related','reads']:
 def load(label):
  p=OUT/'raw-logs'/f'pytest-{group}-{label}.xml'
  if not p.exists():return None
  cases=list(ET.parse(p).iter('testcase'))
  return {'tests':len(cases),'failures':{c.get('classname')+'::'+c.get('name'):c.find('failure').text for c in cases if c.find('failure') is not None},'errors':{c.get('classname')+'::'+c.get('name'):c.find('error').text for c in cases if c.find('error') is not None},'skips':sum(c.find('skipped') is not None for c in cases)}
 base=load('baseline');cur=load('current-delivery') or load('current-lawful' if group=='prior' else 'current-final')
 if not cur:continue
 comparisons.append({'group':group,'baseline':base,'current':cur,'new_failure_names':sorted(set(cur['failures'])-set(base['failures'])),'removed_failure_names':sorted(set(base['failures'])-set(cur['failures'])),'warning':'Compare full assertion texts below, not merely names; changed setup may prevent older assertions being reached.'})
write('regression-comparison.json',comparisons)
write('coverage-summary.json',{'registered':len(rows),'with_request_evidence':sum(bool(c['evidence']) for c in coverage),'with_positive':sum(c['positive']>0 for c in coverage),'unmeasured':sum(not c['evidence'] for c in coverage),'evidence_records':len(evidence),'browser_results':json.loads((OUT/'browser-final/results.json').read_text())['results']})
files=subprocess.check_output(['git','diff','--name-only','HEAD'],cwd=ROOT,text=True).splitlines()+subprocess.check_output(['git','ls-files','--others','--exclude-standard'],cwd=ROOT,text=True).splitlines()
write('source-hashes.json',{'baseline':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'files':{f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files if f.startswith(('backend/','frontend/')) and (ROOT/f).is_file()}})
write('raw-log-index.json',[{'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'exit':p.with_suffix('.exit').read_text().strip() if p.with_suffix('.exit').exists() else None} for p in sorted((OUT/'raw-logs').glob('*')) if p.is_file()])
print((OUT/'coverage-summary.json').read_text())

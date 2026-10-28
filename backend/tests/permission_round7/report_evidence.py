"""Generate reviewable source/action/evidence matrices; reachability is not acceptance."""
from pathlib import Path
import argparse,json,gzip,re,hashlib,subprocess,xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[3];OUT=ROOT/'docs/permissions-round7-20261028'
p=argparse.ArgumentParser();p.add_argument('--suite',required=True);p.add_argument('--label',default='working');args=p.parse_args()
rows=json.loads((ROOT/'backend/app/core/action_catalog.json').read_text())['routes']
patterns=[(r,re.compile('^'+re.sub(r'\{[^}]+\}',lambda m:'.+' if ':path}' in m.group() else '[^/]+',r['path'])+'$')) for r in rows]
xml=OUT/'raw-logs'/f'{args.suite}.xml';outcomes={}
if xml.exists():
 for t in ET.parse(xml).iter('testcase'):
  name=t.get('classname','').replace('.','/')+'.py::'+t.get('name','')
  outcomes[name]='failed' if t.find('failure') is not None or t.find('error') is not None else 'skipped' if t.find('skipped') is not None else 'passed'
folders=['accounts-round2-v1-01','partial-01','chain-round3-v1-01','onsite-round4-v1-01','migration-extended-01','tiers-acceptance-01','selectors-10','warehouse-headers-03','breadth-03','gaps-02','receipt-form-01','gap-extra-01','remaining-bypasses-01']
folders += [x.name for x in OUT.glob('reads-*') if x.is_dir()]
files=[]
for folder in folders:
 files.extend(x for x in (OUT/folder).glob('*requests*') if x.suffix=='.json' or x.name.endswith('.jsonl.gz'))
trace=OUT/'raw-logs'/f'{args.suite}-routes.jsonl.gz'
if trace.exists():files.append(trace)
found={r['id']:[] for r in rows};excluded=[]
for source in files:
 with (gzip.open(source,'rt') if source.suffix=='.gz' else source.open()) as f:
  entries=(json.loads(line) for line in f) if source.suffix=='.gz' else iter(json.load(f))
  for line,e in enumerate(entries,1):
   if e.get('dependency_overrides'):
    excluded.append({'file':str(source.relative_to(OUT)),'line':line,'test':e.get('test'),'overrides':e['dependency_overrides']});continue
   method=e.get('method');path=e.get('path','').split('?')[0]
   if not path.startswith(('/api/','/uploads/')) and path not in ('/','/health'):path='/api/v1'+path
   match=next((r for r,pattern in patterns if method in r['methods'] and pattern.fullmatch(path)),None)
   if not match:continue
   status=e.get('actual_status',e.get('actual',e.get('status')))
   errors=e.get('errors',[]);test=e.get('test');outcome=outcomes.get(test,'unclassified') if source==trace else 'request-assertions-failed' if errors else 'request-assertions-passed'
   actor=e.get('actor',{});uid=actor.get('id',e.get('uid',e.get('user',e.get('subject'))))
   record={'file':str(source.relative_to(OUT)),'line':line,'case':e.get('id',test),'method':method,'path':path,'status':status,'expected':e.get('expected_status',e.get('expected')),'role':actor.get('role',e.get('role')),'user':uid,'warehouse':e.get('warehouse_header'),'outcome':outcome,'errors':errors,'database_evidence':'full before/after diff' if 'database_diff' in e else 'see named test assertions; route trace alone is not a side-effect assertion'}
   found[match['id']].append(record)
front={}
for name in ('frontend-gates.json','frontend-manual-gates.json'):
 for row in json.loads((ROOT/'docs/permissions-round6-20261028'/name).read_text()):
  for entry in row.get('entries',[row]):
   for action in entry.get('actions',[]):front.setdefault(action.split('#')[0],set()).add(row['file'])
index=OUT/f'{args.label}-request-index.jsonl.gz';matrix=[]
with gzip.open(index,'wt',encoding='utf-8') as f:
 for row in rows:
  ev=found[row['id']]
  for item in ev:f.write(json.dumps({'action':row['id'],**item},ensure_ascii=False,default=str)+'\n')
  def count(predicate):return sum(predicate(e) for e in ev if isinstance(e['status'],int))
  matrix.append({**row,'frontend_entries':sorted(front.get(row['id'],[])),'minimal_form':'only when page view is absent and allowed business operation exists; contract and entity map apply','request_count':len(ev),'success_responses':count(lambda e:200<=e['status']<300),'denied_responses':count(lambda e:e['status']>=400),'asserted_success':count(lambda e:200<=e['status']<300 and e['outcome'] in ('passed','request-assertions-passed')),'branch_keys':sorted(set(str((e['role'],e['user'],e['status'],e['warehouse'],e['outcome'])) for e in ev)),'evidence_index':index.name,'scope_note':'This records observed branches, not all state/field/role combinations.'})
(OUT/f'{args.label}-action-matrix.json').write_text(json.dumps(matrix,ensure_ascii=False,indent=2))
lines=['# 第七轮动作与实测分支矩阵','本表的角色是上限，不代替本人、父子单、仓库和业务状态限制。成功响应数不是业务验收数。完整输入字段、状态表达式、关联服务、权限交接、审计和分支见同名 JSON；每次请求见压缩索引。','', '|动作|方法与路径|角色/三档|页面入口（静态）|实测请求/2xx/拒绝/有断言2xx|','|---|---|---|---|---|']
for r in matrix:
 lines.append('|'+ '|'.join([r['id'],','.join(r['methods'])+' '+r['path'],json.dumps(r.get('variants') or {r['tier']:r['roles']},ensure_ascii=False),'<br>'.join(r['frontend_entries']) or '最小办理或原业务上下文；须参照页面实测清单',f"{r['request_count']}/{r['success_responses']}/{r['denied_responses']}/{r['asserted_success']}"])+'|')
(OUT/f'{args.label}-ACTION-MATRIX.md').write_text('\n'.join(lines)+'\n')
summary={'suite':args.suite,'test_outcomes':dict(__import__('collections').Counter(outcomes.values())),'registered':len(rows),'with_requests':sum(bool(r['request_count']) for r in matrix),'with_2xx':sum(bool(r['success_responses']) for r in matrix),'with_asserted_2xx':sum(bool(r['asserted_success']) for r in matrix),'without_2xx':[{'id':r['id'],'path':r['path'],'mode':r['mode']} for r in matrix if not r['success_responses']],'excluded_auth_override_records':len(excluded),'not_claimed':'Full state/role/field coverage, production verification, or independent acceptance.'}
(OUT/f'{args.label}-coverage-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
(OUT/f'{args.label}-excluded-overrides.json').write_text(json.dumps(excluded,ensure_ascii=False,indent=2))
print(json.dumps({k:v for k,v in summary.items() if k!='without_2xx'},ensure_ascii=False))

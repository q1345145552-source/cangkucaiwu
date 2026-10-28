"""Actual request reachability, distinct from final branch acceptance."""
import json,gzip,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];OUT=ROOT/'docs/permissions-round7-20261028'
catalog=json.loads((ROOT/'backend/app/core/action_catalog.json').read_text())['routes']
patterns=[(r,re.compile('^'+re.sub(r'\{[^}]+\}',lambda m:'.+' if ':path}' in m.group() else '[^/]+',r['path'])+'$')) for r in catalog]
found={r['id']:[] for r in catalog}
for p in [*OUT.rglob('*.jsonl.gz'),*OUT.rglob('*requests.json')]:
 try:
  with (gzip.open(p,'rt') if p.suffix=='.gz' else p.open()) as f:
   for i,line in enumerate(f if p.suffix=='.gz' else json.load(f)):
    e=json.loads(line) if isinstance(line,str) else line
    if e.get('dependency_overrides'):continue
    path=e.get('path','').split('?')[0]
    if path and not path.startswith(('/api/','/uploads')) and path not in ('/','/health'):path='/api/v1'+path
    for row,pattern in patterns:
     if e.get('method') in row['methods'] and pattern.fullmatch(path):
      found[row['id']].append({'source':str(p.relative_to(OUT)),'line':i+1,'test':e.get('test',e.get('id')),'status':e.get('status',e.get('actual')),'assertion_errors':e.get('errors'),'subject':e.get('subject',e.get('actor',{}).get('id',e.get('user')))});break
 except EOFError:pass # In-progress logs are never a final report.
rows=[{'id':r['id'],'methods':r['methods'],'path':r['path'],'mode':r['mode'],'requests':len(found[r['id']]),'positive':sum(200<=x['status']<300 for x in found[r['id']] if isinstance(x['status'],int)),'negative':sum(x['status']>=400 for x in found[r['id']] if isinstance(x['status'],int)),'evidence':found[r['id']]} for r in catalog]
(OUT/'coverage-working.json').write_text(json.dumps({'scope':'INTERMEDIATE reachability, not final acceptance; inspect actual assertions and test outcome','routes':rows},ensure_ascii=False,indent=2))
for r in rows:
 if not r['positive'] and r['mode'] not in ('disabled',):print(r['id'],','.join(r['methods']),r['path'],'requests',r['requests'])
print('TOTAL',len(rows),'with requests',sum(bool(r['requests']) for r in rows),'positive',sum(bool(r['positive']) for r in rows))

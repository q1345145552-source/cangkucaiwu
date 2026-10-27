"""Enumerate actual registered read/export/query routes without database access."""
import os,sys,json,inspect
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'backend'))
assert not Path('.env').exists()
os.environ.update(DATABASE_URL='postgresql+asyncpg://round5@127.0.0.1:65489/round5',SECRET_KEY='synthetic-round5-only-secret-key-not-production')
from app.main import app
from fastapi.routing import APIRoute
OUT=ROOT/'docs/permissions-round5-20261028'
def deps(d):return [{'name':getattr(x.call,'__qualname__',str(x.call)),'module':getattr(x.call,'__module__',''),'nested':deps(x)} for x in d.dependencies]
rows=[];catalog=[]
for r in app.routes:
 if not isinstance(r,APIRoute):continue
 actual=inspect.unwrap(r.endpoint)
 source=inspect.getsource(actual)
 catalog.append({'module':actual.__module__,'handler':actual.__name__,'methods':sorted(r.methods),'path':r.path})
 if not ('GET' in r.methods or r.endpoint.__name__ in ('ai_compare','ai_evaluate') or any(s in r.path for s in ('export','preview','search','query','download','print','backup'))):continue
 rows.append({'module':r.endpoint.__module__.rsplit('.',1)[-1],'path':r.path,'methods':sorted(r.methods),'handler':r.endpoint.__name__,'source':inspect.getsourcefile(actual),'line':inspect.getsourcelines(actual)[1],'guards':deps(r.dependant),'query':[{'name':f.name,'default':str(f.default),'required':f.required} for f in r.dependant.query_params],'body':[{'name':f.name,'schema':f.type_.model_json_schema() if hasattr(f.type_,'model_json_schema') else str(f.type_)} for f in r.dependant.body_params],'response_model':str(r.response_model),'implementation':source})
(OUT/'route-catalog.json').write_text(json.dumps(catalog,ensure_ascii=False,indent=2))
(OUT/'read-inventory.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
for r in rows:print(r['module'],','.join(r['methods']),r['path'],r['handler'])
print('COUNT',len(rows))

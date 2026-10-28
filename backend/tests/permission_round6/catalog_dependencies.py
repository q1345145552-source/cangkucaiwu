"""Capture real registered dependency metadata; never infer runtime grants from new routes."""
import os,sys,json,inspect
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'backend'))
assert Path.cwd()==Path('/private/tmp/permissions-round6-env') and not Path('.env').exists()
os.environ.update(DATABASE_URL='postgresql+asyncpg://round6@127.0.0.1:65509/round6',SECRET_KEY='synthetic-round6-only')
from app.main import app
from app.core.menu_registry import MENU_PERMISSIONS
from fastapi.routing import APIRoute
p=ROOT/'backend/app/core/action_catalog.json';catalog=json.loads(p.read_text());by={(r['path'],tuple(r['methods'])):r for r in catalog['routes']};labels={m.label:m.menu_key for m in MENU_PERMISSIONS}
def walk(dep):
 out=[]
 for d in dep.dependencies:
  fn=d.call;values={}
  for key,cell in zip(getattr(getattr(fn,'__code__',None),'co_freevars',()),getattr(fn,'__closure__',()) or ()):
   if key in ('perm_key','perm_keys','permissions'):
    v=cell.cell_contents
    if isinstance(v,str):values[key]=[v]
    elif isinstance(v,(list,tuple)) and all(isinstance(x,str) for x in v):values[key]=list(v)
  out.append({'name':getattr(fn,'__qualname__',str(fn)),'permission_groups':values,'nested':walk(d)})
 return out
def flatten(ds):
 out=[]
 for d in ds:
  for v in d['permission_groups'].values():out.extend(labels[x] for x in v if x in labels)
  out.extend(flatten(d['nested']))
 return out
for route in app.routes:
 if not isinstance(route,APIRoute):continue
 row=by[(route.path,tuple(sorted(route.methods)))];d=walk(route.dependant);row['guards']=d
 fn=inspect.unwrap(route.endpoint);row['source']=str(Path(inspect.getsourcefile(fn)).relative_to(ROOT));row['line']=inspect.getsourcelines(fn)[1]
 row['legacy_permission_modules']=sorted(set(flatten(d)))
 # Keep explicit per-route aliases for shared read utilities. Original dependency
 # groups still execute; a catalogue match never replaces their AND conditions.
 row.setdefault('grant_modules', [row['module_key']])  # Never overwrite reviewed cross-module mappings.
p.write_text(json.dumps(catalog,ensure_ascii=False,indent=2)+'\n');print('Captured',len(by),'route guards')

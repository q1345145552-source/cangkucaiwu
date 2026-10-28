from fixtures import *
from app.core.action_access import CATALOG
from app.core.action_forms import contract
from app.core.action_choices import binding
rows=[]
def walk(s,path):
 if not isinstance(s,dict):return
 if s.get('selector'):yield path,s['selector']
 for k,v in s.get('properties',{}).items():yield from walk(v,path+'.'+k)
 if 'items' in s:yield from walk(s['items'],path+'.[]')
 for v in s.get('anyOf',[])+s.get('allOf',[]):yield from walk(v,path)
for row in CATALOG['routes']:
 if row['mode']!='business' or row['tier']=='view':continue
 form=contract(app,row,'warehouse_admin')
 rows.append({'id':row['id'],'path':row['path'],'body':form['body'],'parameters':form['parameters'],'selectors':dict(walk(form['body'],'body'))})
(OUT/'forms.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
print(len(rows),'forms')

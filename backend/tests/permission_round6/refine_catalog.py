"""Conservative catalogue role intersection with direct, unconditional existing guards."""
import os,sys,ast,inspect,json,textwrap
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'backend'))
assert Path.cwd()==Path('/private/tmp/permissions-round6-env') and not Path('.env').exists()
os.environ.update(DATABASE_URL='postgresql+asyncpg://round6@127.0.0.1:65509/round6',SECRET_KEY='synthetic-round6-only')
from app.main import app
from app.core.action_forms import action_label
from fastapi.routing import APIRoute
p=ROOT/'backend/app/core/action_catalog.json';data=json.loads(p.read_text());by={(r['path'],tuple(sorted(r['methods']))):r for r in data['routes']};changes=[]
role_names={'SUPER_ADMIN':'super_admin','WAREHOUSE_ADMIN':'warehouse_admin','SUPERVISOR':'supervisor','STAFF':'staff','WAREHOUSE_LABOR':'warehouse_labor'}
def direct_denials(fn):
 try:node=ast.parse(textwrap.dedent(inspect.getsource(inspect.unwrap(fn)))).body[0]
 except (OSError,TypeError,IndentationError):return set()
 denied=set()
 for n in getattr(node,'body',[]):
  if not isinstance(n,ast.If) or not isinstance(n.test,ast.Compare) or not any(isinstance(b,ast.Raise) for b in n.body):continue
  c=n.test
  if not isinstance(c.left,ast.Attribute) or c.left.attr!='role' or len(c.ops)!=1:continue
  r=c.comparators[0];values=r.elts if isinstance(r,(ast.Tuple,ast.List,ast.Set)) else [r]
  vals={role_names[x.attr] for x in values if isinstance(x,ast.Attribute) and isinstance(x.value,ast.Name) and x.value.id=='Role' and x.attr in role_names}
  if not vals:continue
  for role in role_names.values():
   bad=role in vals if isinstance(c.ops[0],(ast.Eq,ast.In)) else role not in vals if isinstance(c.ops[0],(ast.NotEq,ast.NotIn)) else False
   if bad:denied.add(role)
 return denied

def guards(dep):
 result=direct_denials(dep.call)
 for d in dep.dependencies:result |= guards(d)
 return result
explicit={
 'employee_advance.verify_advance':['warehouse_admin','staff'], 'employee_advance.execute_advance':['warehouse_admin','staff'],
 'expense_approval.pay_approval':['warehouse_admin','staff'], 'reimbursement.verify_reimb':['warehouse_admin','staff'],
 'expense_fund.topup_account':[], 'payroll.revoke_disbursement':[], 'reimbursement.cancel_payment':[],
}
for route in app.routes:
 if not isinstance(route,APIRoute):continue
 row=by[(route.path,tuple(sorted(route.methods)))];row['label']=action_label(row,route.endpoint)
 if row['mode']!='business':continue
 denied=guards(route.dependant);old=row['roles'];row['roles']=[r for r in explicit.get(row['id'],old) if r not in denied]
 if old!=row['roles']:changes.append({'id':row['id'],'before':old,'after':row['roles'],'source':inspect.getsourcefile(route.endpoint),'reason':'explicit confirmed duty or direct existing role guard intersection'})
 if row.get('variants'):
  for v in row['variants']['values'].values():v['roles']=[r for r in v['roles'] if r not in denied]
p.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n');(ROOT/'docs/permissions-round6-20261028/catalog-role-review.json').write_text(json.dumps(changes,ensure_ascii=False,indent=2));print(len(changes),'role metadata corrections')

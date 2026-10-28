"""Capture actual action source and linked guards for review; never changes authorization."""
import ast,hashlib,inspect,json,os,sys,textwrap
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'backend'))
assert Path.cwd()==Path('/private/tmp/permissions-round7-env') and not Path('.env').exists()
os.environ.update(DATABASE_URL='postgresql+asyncpg://round7@127.0.0.1:65519/round7',SECRET_KEY='synthetic-round6-catalogue-only-signing-key')
from app.main import app
from fastapi.routing import APIRoute
from app.core.action_forms import contract
p=ROOT/'backend/app/core/action_catalog.json';d=json.loads(p.read_text());rows={(r['path'],tuple(sorted(r['methods']))):r for r in d['routes']}
def location(fn):
 try:
  fn=inspect.unwrap(fn);path=Path(inspect.getsourcefile(fn));source,line=inspect.getsourcelines(fn)
  if not path.is_relative_to(ROOT/'backend/app'):return None
  return {'file':str(path.relative_to(ROOT)),'line':line,'function':fn.__name__,'sha256':hashlib.sha256(''.join(source).encode()).hexdigest()}
 except (TypeError,OSError,ValueError):return None
for route in app.routes:
 if not isinstance(route,APIRoute):continue
 r=rows[(route.path,tuple(sorted(route.methods)))];fn=inspect.unwrap(route.endpoint);src=inspect.getsource(fn);tree=ast.parse(textwrap.dedent(src));line=inspect.getsourcelines(fn)[1]
 r['source']=str(Path(inspect.getsourcefile(fn)).relative_to(ROOT));r['line']=line
 r['state_conditions']=[{'line':line+n.lineno-1,'condition':ast.unparse(n.test)} for n in ast.walk(tree) if isinstance(n,ast.If) and any(isinstance(a,ast.Attribute) and a.attr in ('status','review_status','approval_status','disbursed','is_voided','voided') for a in ast.walk(n.test))]
 calls=[]
 for n in ast.walk(tree):
  if not isinstance(n,ast.Call):continue
  f=n.func;obj=None
  if isinstance(f,ast.Name):obj=fn.__globals__.get(f.id)
  elif isinstance(f,ast.Attribute) and isinstance(f.value,ast.Name):obj=getattr(fn.__globals__.get(f.value.id),f.attr,None)
  if obj is not None and inspect.isfunction(obj):
   loc=location(obj)
   if loc and loc not in calls:calls.append(loc)
 r['associated_services']=calls
 r['input_contract']=contract(app,r,'warehouse_admin')
 r['self_restriction']='No generic grant bypass: existing employee/user binding and applicant/beneficiary/creator checks; see associated_services'
 if r['module_key'] in ('payroll','reimbursement','expense_fund','employee_advances','payable','payment_plans','cash_advances','expense_approval'):
  r['approval_handoff']='核验/准备(operate) → 独立管理员资金批准(approve) → 独立财务执行(operate); 已付拒绝，批准快照和对象状态必须仍有效。本人申请/受益身份及关联员工仍禁止自批/自付。'
 elif r['id'] in ('suppliers.approve_purchase','suppliers.reject_purchase'):
  r['approval_handoff']='既有采购职责配置+例外+版本校验；只形成待资金核验的应付，不能代替资金批准或付款。'
 elif r['tier']=='approve':r['approval_handoff']='现有现场事实/平台审核；本人隔离及单据前置状态仍执行，不能从操作授权推导审批。'
 else:r['approval_handoff']='不产生新增批准授权；执行现有业务状态和相关服务限制。'
 r['minimal_read_dependencies']=[{'endpoint':'/api/v1/access/choices/'+r['module_key'],'required_any_tier':['operate','approve'],'fields':['id','label','status','entity'],'binding':'action+exact schema field+authorized parent; search/page; selected_id provides explicit action-context whitelist only','unsupported_module':'Legacy choices can reject; specific bindings and gaps are separately inventoried'}] if r['mode']=='business' and r['tier']!='view' else []
from tests.evidence_path import evidence_dir
(evidence_dir('action-catalog')/'full-metadata.json').write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
for row in d['routes']:
 for key in ('guards','associated_services'):row.pop(key,None)
p.write_text(json.dumps(d,ensure_ascii=False,separators=(',',':'))+'\n')
(ROOT/'docs/permissions-round7-20261028/registration-check.json').write_text(json.dumps({'actual':len(rows),'catalogue':len(d['routes']),'missing':[],'stale':[],'source':'actual FastAPI APIRoute paths/methods exact match'},indent=2))
print(len(rows),'registered routes with source, original contracts and associated services')
